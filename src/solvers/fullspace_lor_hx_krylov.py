"""Fixed Krylov requalification helpers for the native-complex LOR-HX PC.

This module is deliberately separate from the already-recorded one-apply L2
oracle.  It owns no physical operator and does not alter the frozen HX
sequence.  The PETSc shell only forwards matrix-free ``B_h`` actions and the
existing HX preconditioner; all qualification decisions use an explicit
matrix-free true residual.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any

import numpy as np
from petsc4py import PETSc


K0_GMRES_RESTART = 80
K0_GMRES_MAX_IT = 200
K0_GMRES_RTOL = 1.0e-8
K0_GMRES_ATOL = 0.0
K0_TRUE_RESIDUAL_LIMIT = 1.0e-8
K0_TRUE_RESIDUAL_FIRST_PASS_MAX_IT = 80
K0_CHECKPOINTS = (0, 1, 2, 5, 10, 20, 40, 80, 120, 160, 200)
K0_LINEARITY_LIMIT = 1.0e-12
K0_REPEAT_LIMIT = 1.0e-13
K0_ALPHA_PRODUCTION_APPLIED = False
K0_DIRECTION_COEFFICIENTS = (0.375 + 0.25j, -0.625 + 0.5j)
K0_DIRECTION_CONSTRUCTION = (
    "deterministic SHA256 parity of canonical full-space row keys"
)
K0_DIRECTION_INPUT_ROLE = (
    "full_fe_dual_canonical_packets_reconstructed_with_T_H_no_new_phase"
)


@dataclass(frozen=True)
class K0KrylovSettings:
    """The immutable PETSc settings required by the K0 contract."""

    ksp_type: str = "gmres"
    pc_side: str = "right"
    norm_type: str = "unpreconditioned"
    restart: int = K0_GMRES_RESTART
    max_it: int = K0_GMRES_MAX_IT
    rtol: float = K0_GMRES_RTOL
    atol: float = K0_GMRES_ATOL
    initial_guess_nonzero: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ksp_type": self.ksp_type,
            "pc_side": self.pc_side,
            "norm_type": self.norm_type,
            "restart": int(self.restart),
            "max_it": int(self.max_it),
            "rtol": float(self.rtol),
            "atol": float(self.atol),
            "initial_guess_nonzero": bool(self.initial_guess_nonzero),
        }


K0_SETTINGS = K0KrylovSettings()


def relative_error(left: Any, right: Any) -> float:
    """Return a scale-safe relative 2-norm difference."""

    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    if left_array.shape != right_array.shape:
        raise ValueError("relative-error operands have different shapes")
    denominator = max(float(np.linalg.norm(right_array)), np.finfo(float).tiny)
    return float(np.linalg.norm(left_array - right_array) / denominator)


def alpha_diagnostic(residual: Any, applied_output: Any) -> dict[str, Any]:
    """Measure the best scalar correction without applying it in production.

    For ``q=B_h z`` the reported scalar is ``<q,r>/<q,q>`` using the complex
    Euclidean inner product.  This helper is diagnostic only; the fixed PC and
    Krylov solve never call it to modify a vector.
    """

    residual_array = np.asarray(residual, dtype=np.complex128)
    output_array = np.asarray(applied_output, dtype=np.complex128)
    if residual_array.shape != output_array.shape:
        raise ValueError("alpha diagnostic operands have different shapes")
    if not np.all(np.isfinite(residual_array)) or not np.all(
        np.isfinite(output_array)
    ):
        raise ValueError("alpha diagnostic requires finite vectors")
    denominator = np.vdot(output_array, output_array)
    if abs(denominator) <= np.finfo(float).tiny:
        raise ValueError("alpha diagnostic has a zero output direction")
    alpha = np.vdot(output_array, residual_array) / denominator
    residual_norm = max(float(np.linalg.norm(residual_array)), np.finfo(float).tiny)
    rho_alpha = float(
        np.linalg.norm(residual_array - alpha * output_array) / residual_norm
    )
    return {
        "alpha_star": complex(alpha),
        "rho_alpha": rho_alpha,
        "production_pc_alpha_applied": K0_ALPHA_PRODUCTION_APPLIED,
    }


def _apply_array_preserving(
    apply: Callable[[np.ndarray], Any], vector: np.ndarray
) -> tuple[np.ndarray, bool]:
    before = np.asarray(vector, dtype=np.complex128).copy()
    result = np.asarray(apply(vector), dtype=np.complex128).copy()
    return result, bool(np.array_equal(vector, before))


def _canonical_key_bytes(key: Any) -> bytes:
    """Serialize a canonical key without using Python's randomized hash."""

    def jsonable(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(item): jsonable(entry) for item, entry in value.items()}
        if isinstance(value, (tuple, list)):
            return [jsonable(entry) for entry in value]
        if isinstance(value, np.generic):
            return jsonable(value.item())
        return value

    return json.dumps(
        jsonable(key), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _key_sequence(canonical_keys: Any) -> list[Any]:
    if isinstance(canonical_keys, np.ndarray):
        if canonical_keys.ndim != 1:
            raise ValueError("canonical direction keys must be one-dimensional")
        return canonical_keys.tolist()
    return list(canonical_keys)


def canonical_direction_mask(canonical_keys: Any) -> np.ndarray:
    """Return a partition-independent two-way mask for canonical row keys."""

    key_sequence = _key_sequence(canonical_keys)
    if len(key_sequence) < 2:
        raise ValueError("canonical direction keys must be a one-dimensional pair")
    serialized = [_canonical_key_bytes(key) for key in key_sequence]
    if len(set(serialized)) != len(serialized):
        raise ValueError("canonical direction keys must be unique")
    return np.asarray(
        [hashlib.sha256(value).digest()[0] & 1 for value in serialized], dtype=bool
    )


def canonical_key_set_sha256(canonical_keys: Any) -> str:
    serialized = sorted(
        _canonical_key_bytes(key) for key in _key_sequence(canonical_keys)
    )
    return hashlib.sha256(b"\0".join(serialized)).hexdigest()


def two_direction_linearity(
    apply: Callable[[np.ndarray], Any],
    residual: Any,
    canonical_keys: Any,
    output_keys: Any | None = None,
) -> dict[str, Any]:
    """Check a fixed, non-degenerate two-direction linearity identity.

    Canonical row keys, rather than local PETSc positions, choose the two
    directions.  The coefficients are frozen constants, so this is a single
    identity check rather than a fit or parameter scan.
    """

    original = np.asarray(residual, dtype=np.complex128).copy()
    if original.ndim != 1 or original.size < 2:
        raise ValueError("linearity check requires a one-dimensional vector")
    key_sequence = _key_sequence(canonical_keys)
    if len(key_sequence) != original.size:
        raise ValueError("canonical direction keys must align with residual values")
    output_key_sequence = (
        key_sequence if output_keys is None else _key_sequence(output_keys)
    )
    if len(output_key_sequence) < 1:
        raise ValueError("canonical output keys must not be empty")
    mask = canonical_direction_mask(key_sequence)
    first = np.zeros_like(original)
    first[mask] = original[mask]
    second = original - first
    if min(np.linalg.norm(first), np.linalg.norm(second)) <= np.finfo(float).tiny:
        raise ValueError("linearity split must contain two nonzero directions")
    coefficient_a, coefficient_b = K0_DIRECTION_COEFFICIENTS
    combined = coefficient_a * first + coefficient_b * second
    first_output, first_unchanged = _apply_array_preserving(apply, first)
    second_output, second_unchanged = _apply_array_preserving(apply, second)
    combined_output, combined_unchanged = _apply_array_preserving(apply, combined)
    repeated_output, repeated_unchanged = _apply_array_preserving(apply, combined)
    if any(
        output.size != len(output_key_sequence)
        for output in (first_output, second_output, combined_output, repeated_output)
    ):
        raise ValueError("canonical output keys do not align with PC outputs")
    expected = coefficient_a * first_output + coefficient_b * second_output
    return {
        "construction": K0_DIRECTION_CONSTRUCTION,
        "input_role": "dual",
        "output_role": "primal",
        "input_key_set_sha256": canonical_key_set_sha256(key_sequence),
        "output_key_set_sha256": canonical_key_set_sha256(output_key_sequence),
        "direction_mask": mask.tolist(),
        "coefficient_a": complex(coefficient_a),
        "coefficient_b": complex(coefficient_b),
        "direction_norms": [float(np.linalg.norm(first)), float(np.linalg.norm(second))],
        "relative": relative_error(combined_output, expected),
        "repeat_relative": relative_error(repeated_output, combined_output),
        "finite": bool(
            np.all(np.isfinite(first_output))
            and np.all(np.isfinite(second_output))
            and np.all(np.isfinite(combined_output))
        ),
        "input_unchanged": bool(
            np.array_equal(original, residual)
            and first_unchanged
            and second_unchanged
            and combined_unchanged
            and repeated_unchanged
        ),
        "direction_values": {
            "r1": first,
            "r2": second,
            "combined": combined,
            "p1": first_output,
            "p2": second_output,
            "pcombined": combined_output,
            "pcombined_repeat": repeated_output,
        },
    }


def _petsc_true_residual(rhs: PETSc.Vec, action: PETSc.Vec) -> PETSc.Vec:
    result = rhs.copy()
    result.axpy(PETSc.ScalarType(-1.0), action)
    return result


class K0HighActionContext:
    """Python matrix shell context for exact matrix-free ``B_h`` actions."""

    def __init__(self, fixture: Any) -> None:
        self.fixture = fixture
        self.matvec_count = 0

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        result = self.fixture.apply_high_action_copy(source)
        try:
            result.copy(target)
        finally:
            result.destroy()
        self.matvec_count += 1


class K0RightPCContext:
    """Python PC context forwarding the unchanged frozen v1 HX apply."""

    def __init__(self, fixture: Any) -> None:
        self.fixture = fixture
        self.apply_count = 0

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        result = self.fixture.apply_high_preconditioner(source)
        try:
            result.copy(target)
        finally:
            result.destroy()
        self.apply_count += 1


def build_k0_gmres_solver(fixture: Any) -> dict[str, Any]:
    """Build the fixed right-preconditioned GMRES shell without solving."""

    operator_context = K0HighActionContext(fixture)
    operator = PETSc.Mat().createPython(
        fixture.high_action.matrix.getSizes(),
        context=operator_context,
        comm=fixture.comm,
    )
    operator.setUp()
    pc_context = K0RightPCContext(fixture)
    ksp = PETSc.KSP().create(fixture.comm)
    ksp.setOperators(operator)
    ksp.setType("gmres")
    ksp.setGMRESRestart(K0_GMRES_RESTART)
    ksp.setPCSide(PETSc.PC.Side.RIGHT)
    ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
    ksp.setInitialGuessNonzero(False)
    ksp.setTolerances(
        rtol=K0_GMRES_RTOL, atol=K0_GMRES_ATOL, max_it=K0_GMRES_MAX_IT
    )
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.PYTHON)
    pc.setPythonContext(pc_context)
    ksp.setUp()
    return {
        "settings": K0_SETTINGS,
        "ksp": ksp,
        "operator": operator,
        "operator_context": operator_context,
        "pc_context": pc_context,
    }


def _checkpoint_statuses(
    iterations: int, first_true_pass: int | None, reason: int
) -> dict[int, str]:
    statuses: dict[int, str] = {}
    for checkpoint in K0_CHECKPOINTS:
        if checkpoint <= iterations:
            statuses[checkpoint] = "measured"
        elif reason < 0:
            statuses[checkpoint] = "not_reached"
        elif first_true_pass is not None and checkpoint > first_true_pass:
            statuses[checkpoint] = "not_run_after_convergence"
        else:
            statuses[checkpoint] = "not_reached"
    return statuses


def run_k0_gmres(fixture: Any, rhs: PETSc.Vec) -> dict[str, Any]:
    """Run fixed GMRES and retain only required checkpoint vector copies."""

    solver = build_k0_gmres_solver(fixture)
    ksp = solver["ksp"]
    operator = solver["operator"]
    operator_context = solver["operator_context"]
    pc_context = solver["pc_context"]
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    solution.set(0.0 + 0.0j)
    monitor_solution.set(0.0 + 0.0j)
    rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
    history: list[dict[str, Any]] = []
    checkpoints: dict[int, dict[str, PETSc.Vec]] = {}
    started = time.perf_counter()
    first_true_pass: int | None = None
    monitor_action_count = 0

    def snapshot(iteration: int, reported_norm: float, current: PETSc.KSP | None) -> dict[str, Any]:
        nonlocal first_true_pass, monitor_action_count
        iteration = int(iteration)
        for row in history:
            if int(row["iteration"]) == iteration:
                return row
        if current is None:
            solution.copy(monitor_solution)
            current_solution = monitor_solution
        else:
            current_solution = current.buildSolution(monitor_solution)
        action = fixture.apply_high_action_copy(current_solution)
        monitor_action_count += 1
        true_residual = _petsc_true_residual(rhs, action)
        explicit_relative = float(true_residual.norm() / rhs_norm)
        if (
            first_true_pass is None
            and explicit_relative <= K0_TRUE_RESIDUAL_LIMIT
        ):
            first_true_pass = iteration
        row = {
            "iteration": iteration,
            "reported_unpreconditioned_relative": float(reported_norm / rhs_norm),
            "explicit_true_residual": explicit_relative,
            "matvec_count": int(operator_context.matvec_count),
            "pc_apply_count": int(pc_context.apply_count),
            "monitor_action_count": int(monitor_action_count),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        history.append(row)
        if iteration in K0_CHECKPOINTS:
            checkpoints[iteration] = {
                "solution": current_solution.copy(),
                "action": action.copy(),
                "true_residual": true_residual.copy(),
            }
        action.destroy()
        true_residual.destroy()
        return row

    snapshot(0, rhs_norm, None)

    def convergence_test(
        current: PETSc.KSP, iteration: int, reported_norm: float
    ) -> int:
        row = snapshot(int(iteration), float(reported_norm), current)
        if (
            row["explicit_true_residual"] <= K0_TRUE_RESIDUAL_LIMIT
            and int(iteration) <= K0_TRUE_RESIDUAL_FIRST_PASS_MAX_IT
        ):
            return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
        return 0

    try:
        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        if not any(int(row["iteration"]) == iterations for row in history):
            snapshot(iterations, float(ksp.getResidualNorm()), None)
    except Exception:
        destroy_k0_gmres_result(
            {
                **solver,
                "solution": solution,
                "monitor_solution": monitor_solution,
                "checkpoints": checkpoints,
            }
        )
        raise

    late_true_pass = next(
        (
            int(row["iteration"])
            for row in history
            if int(row["iteration"]) > K0_TRUE_RESIDUAL_FIRST_PASS_MAX_IT
            and float(row["explicit_true_residual"]) <= K0_TRUE_RESIDUAL_LIMIT
        ),
        None,
    )
    checkpoint_status = _checkpoint_statuses(iterations, first_true_pass, reason)
    return {
        **solver,
        "solution": solution,
        "monitor_solution": monitor_solution,
        "history": history,
        "checkpoints": checkpoints,
        "checkpoint_status": checkpoint_status,
        "reason": reason,
        "iterations": iterations,
        "first_true_pass_iteration": first_true_pass,
        "late_true_pass_iteration": late_true_pass,
        "qualification_pass": bool(
            first_true_pass is not None
            and first_true_pass <= K0_TRUE_RESIDUAL_FIRST_PASS_MAX_IT
        ),
        "reported_final_residual": float(ksp.getResidualNorm() / rhs_norm),
        "rhs_norm": rhs_norm,
        "monitor_action_count": int(monitor_action_count),
    }


def destroy_k0_gmres_result(result: dict[str, Any]) -> None:
    """Destroy owned checkpoint vectors, KSP, and shell in dependency order."""

    checkpoints = result.pop("checkpoints", {})
    for vectors in checkpoints.values():
        for vector in vectors.values():
            vector.destroy()
    for name in ("monitor_solution", "solution"):
        vector = result.pop(name, None)
        if vector is not None:
            vector.destroy()
    ksp = result.pop("ksp", None)
    if ksp is not None:
        ksp.destroy()
    operator = result.pop("operator", None)
    if operator is not None:
        operator.destroy()
