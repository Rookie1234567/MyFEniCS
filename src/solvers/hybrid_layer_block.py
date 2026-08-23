"""Layer-aware sparse block action for the Task39 V8 graph audit.

The operator keeps the original distributed matrix layout.  Each local block
owns only the rows owned by that MPI rank and the selected layer columns. Six
distributed layer workspaces are shared by the sixteen D/L/U blocks; a
``VecScatter`` gathers each layer once and scatters each layer result back with
additive insertion. The source matrix and the system that produced it are
borrowed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse

__all__ = (
    "ExactBlockSchurAction",
    "FixedTwoLayerSupernodeAction",
    "LayerBlockOperator",
    "LayerSweepAction",
    "audit_layer_block_action",
    "build_fixed_two_layer_supernode_action",
    "build_real_layer_labels",
    "build_layer_block_operator",
    "build_layer_sweep_action",
    "minimum_layer_labels",
    "relative_matvec_residual",
    "audit_supernode_factor_paths",
    "run_v10_right_preconditioned_fgmres_checkpoints",
    "run_v1_1_right_preconditioned_fgmres_batch",
)


def minimum_layer_labels(
    local_labels: np.ndarray, global_rows: int, comm: MPI.Intracomm
) -> np.ndarray:
    sentinel = np.iinfo(np.int32).max
    local = np.asarray(local_labels, dtype=np.int32)
    if local.shape != (int(global_rows),) or not local.flags.c_contiguous:
        raise ValueError("V6 layer label buffer shape is invalid")
    if np.any((local < 0) & (local != sentinel)):
        raise ValueError("V6 layer label is outside the global row space")
    labels = np.full(int(global_rows), sentinel, dtype=np.int32)
    comm.Allreduce(local, labels, op=MPI.MIN)
    if np.any(labels == sentinel):
        raise ValueError("V6 layer graph does not cover every active F row")
    return labels


def relative_matvec_residual(
    operator: Any, rhs: PETSc.Vec, solution: PETSc.Vec
) -> float:
    """Return ``||rhs-operator*solution||/||rhs||`` for one real action.

    The caller owns ``rhs`` and ``solution``.  The temporary result vector is
    local to this measurement, so this helper does not retain an operator or
    any solver state.  It is used by the V9 bare-F diagnostic to keep the
    residual definition separate from reference-solution comparison.
    """

    applied = operator.createVecLeft()
    try:
        operator.mult(solution, applied)
        applied.axpy(PETSc.ScalarType(-1.0), rhs)
        return float(applied.norm()) / max(float(rhs.norm()), 1.0e-30)
    finally:
        applied.destroy()


class _V10RightPreconditionerContext:
    """Borrow one fixed action as the PETSc right-PC context for V10."""

    def __init__(self, action: Any) -> None:
        self.action: Any | None = action
        self.apply_count = 0

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.action is None:
            raise RuntimeError("V10 right preconditioner has been destroyed")
        self.action.apply(source, target)
        self.apply_count += 1

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.action = None


def run_v10_right_preconditioned_fgmres_checkpoints(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    right_preconditioner: Any,
    *,
    label: str,
    resource_gate: Callable[[], bool] | None = None,
    checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one V10 right-FGMRES solve with conditional continuation at 16.

    The KSP is created once with restart/max-it 32 and a zero initial guess.
    At iteration 16 the convergence callback either returns ``DIVERGED_ITS``
    (the auditable, conservative 16-stop) or lets the same KSP continue to
    32.  This is deliberately a single-RHS helper; the orchestration layer
    owns the five-RHS worst-trend decision and evidence aggregation.
    """

    if not isinstance(operator, PETSc.Mat):
        raise TypeError("V10 FGMRES requires a PETSc operator matrix")
    if not callable(getattr(right_preconditioner, "apply", None)):
        raise TypeError("V10 FGMRES requires a fixed right action")
    if resource_gate is None:

        def resource_gate() -> bool:
            return True

    comm = operator.getComm()
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    residual = operator.createVecLeft()
    solution.set(0.0)
    monitor_solution.set(0.0)
    residual.set(0.0)
    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
        solution.destroy()
        monitor_solution.destroy()
        residual.destroy()
        raise ValueError("V10 mandatory FGMRES RHS must be finite and nonzero")
    denominator = max(rhs_norm, 1.0e-30)
    started = time.perf_counter()
    history: list[dict[str, Any]] = []
    checkpoints: dict[int, dict[str, Any]] = {}
    state = {
        "continued_to_32": False,
        "stop_at_16": False,
        "first_nonfinite_stage": None,
        "explicit_true_residual_matvec_count": 0,
    }
    reported_history: list[dict[str, Any]] = []
    pc_context = _V10RightPreconditionerContext(right_preconditioner)
    ksp = PETSc.KSP().create(comm)
    result: dict[str, Any] | None = None

    def operator_context_apply_count() -> int | str:
        try:
            if str(operator.getType()).lower() != "python":
                return "not_available"
            context = operator.getPythonContext()
        except Exception:
            return "not_available"
        value = getattr(context, "apply_count", None)
        return int(value) if isinstance(value, (int, np.integer)) else "not_available"

    operator_count_before = operator_context_apply_count()
    bounded_max_it_reason = int(
        getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)
    )
    bounded_its_reason = int(
        getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", bounded_max_it_reason)
    )

    def emit(row: Mapping[str, Any]) -> None:
        row_copy = dict(row)
        history.append(row_copy)
        checkpoints[int(row_copy["iteration"])] = row_copy
        if checkpoint_callback is not None:
            checkpoint_callback(row_copy)

    def true_residual_row(
        iteration: int,
        reported_relative_residual: float,
        current_solution: PETSc.Vec,
    ) -> dict[str, Any]:
        if iteration > 0:
            residual.set(0.0)
            operator.mult(current_solution, residual)
            state["explicit_true_residual_matvec_count"] += 1
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            true_value = float(residual.norm()) / denominator
        else:
            true_value = float(rhs_norm) / denominator
        finite = bool(
            np.isfinite(float(reported_relative_residual))
            and np.isfinite(float(true_value))
        )
        if not finite and state["first_nonfinite_stage"] is None:
            state["first_nonfinite_stage"] = f"iteration_{iteration}"
        return {
            "label": label,
            "iteration": int(iteration),
            "reported_relative_residual": float(reported_relative_residual),
            "explicit_true_residual": float(true_value),
            "finite": finite,
            "j1_apply_count": int(pc_context.apply_count),
            "a_side_true_residual_matvec_count": int(
                state["explicit_true_residual_matvec_count"]
            ),
            "elapsed_seconds": float(time.perf_counter() - started),
        }

    try:
        zero_row = true_residual_row(0, 1.0 if rhs_norm > 1.0e-30 else 0.0, solution)
        emit(zero_row)
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=32)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setUp()

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            reported_history.append(
                {
                    "iteration": int(iteration),
                    "reported_relative_residual": float(residual_norm) / denominator,
                }
            )
            if int(iteration) not in (4, 8, 16, 32):
                return 0
            solution_view = current.buildSolution(monitor_solution)
            if solution_view is None:
                solution_view = monitor_solution
            reported = float(residual_norm) / denominator
            row = true_residual_row(int(iteration), reported, solution_view)
            if int(iteration) == 16:
                r4 = checkpoints.get(4, {}).get("explicit_true_residual")
                r8 = checkpoints.get(8, {}).get("explicit_true_residual")
                r16 = row["explicit_true_residual"]
                trend_pass = bool(
                    row["finite"]
                    and isinstance(r4, (int, float))
                    and isinstance(r8, (int, float))
                    and np.isfinite(float(r4))
                    and np.isfinite(float(r8))
                    and np.isfinite(float(r16))
                    and float(r16) < float(r8)
                    and float(r16) <= 0.5 * float(r4)
                )
                resource_pass = bool(resource_gate())
                state["continued_to_32"] = bool(trend_pass and resource_pass)
                row["trend_pass"] = trend_pass
                row["resource_gate_pass"] = resource_pass
                row["continue_to_32_authorized"] = state["continued_to_32"]
            emit(row)
            if int(iteration) == 16:
                if not state["continued_to_32"]:
                    state["stop_at_16"] = True
                    return bounded_its_reason
            return 0

        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        if iterations >= 32 and 32 not in checkpoints:
            row = true_residual_row(
                32, float(ksp.getResidualNorm()) / denominator, solution
            )
            emit(row)
        solution.copy(monitor_solution)
        residual.set(0.0)
        operator.mult(monitor_solution, residual)
        state["explicit_true_residual_matvec_count"] += 1
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        final_true_residual = float(residual.norm()) / denominator
        if (
            not np.isfinite(final_true_residual)
            and state["first_nonfinite_stage"] is None
        ):
            state["first_nonfinite_stage"] = "postsolve_true_residual"
        operator_count_after = operator_context_apply_count()
        if isinstance(operator_count_before, int) and isinstance(
            operator_count_after, int
        ):
            total_operator_apply_count: int | str = (
                operator_count_after - operator_count_before
            )
        else:
            total_operator_apply_count = "not_available"
        bounded_reasons = {
            bounded_its_reason,
            bounded_max_it_reason,
        }
        ksp_breakdown = bool(
            reason < 0 and not state["stop_at_16"] and reason not in bounded_reasons
        )
        result = {
            "label": label,
            "ksp_type": str(ksp.getType()),
            "pc_side": "right",
            "right_pc_identity": type(right_preconditioner).__name__,
            "restart": 32,
            "max_it": 32,
            "zero_initial_guess": True,
            "zero_initial_guess_count": 1,
            "ksp_reason": reason,
            "ksp_breakdown": ksp_breakdown,
            "iterations": iterations,
            "reported_residual_history": [dict(row) for row in reported_history],
            "history": [dict(row) for row in history],
            "checkpoints": {
                str(key): dict(value) for key, value in checkpoints.items()
            },
            "continued_to_32": bool(state["continued_to_32"]),
            "stop_at_16": bool(state["stop_at_16"]),
            "first_nonfinite_stage": state["first_nonfinite_stage"],
            "j1_apply_count": int(pc_context.apply_count),
            "a_side_apply_count": total_operator_apply_count,
            "a_side_true_residual_matvec_count": int(
                state["explicit_true_residual_matvec_count"]
            ),
            "final_independent_true_residual": final_true_residual,
            "wall_seconds": float(time.perf_counter() - started),
            "ksp_destroyed": False,
            "research_only": True,
        }
    finally:
        ksp.destroy()
        pc_context.destroy()
        residual.set(0.0)
        residual.destroy()
        monitor_solution.set(0.0)
        monitor_solution.destroy()
        solution.set(0.0)
        solution.destroy()
        if result is not None:
            result["ksp_destroyed"] = True

    if result is None:
        raise RuntimeError("V10 FGMRES did not produce a result")
    return result


def run_v1_1_right_preconditioned_fgmres_batch(
    operator: PETSc.Mat,
    rhs_by_label: Mapping[str, PETSc.Vec],
    right_preconditioner: Any,
    *,
    labels: Sequence[str],
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the opt-in V1-1 two-phase batch right-FGMRES screen.

    One KSP/PC setup and one fixed right action are reused for all RHS.  The
    first phase runs every RHS from zero through checkpoint 16.  Only after a
    collective trend/resource decision does the same setup run every RHS from
    zero again through checkpoint 32.  This helper is intentionally separate
    from the legacy V10 single-RHS ``0.5*r4`` continuation contract.
    """

    if not isinstance(operator, PETSc.Mat):
        raise TypeError("V1-1 FGMRES requires a PETSc operator matrix")
    labels = tuple(labels)
    if not labels or tuple(rhs_by_label) != labels:
        raise ValueError("V1-1 RHS labels must be ordered and exact")
    if not callable(getattr(right_preconditioner, "apply", None)):
        raise TypeError("V1-1 FGMRES requires a fixed right action")
    matrix_rows, matrix_cols = operator.getSize()
    if matrix_rows != matrix_cols or any(
        not isinstance(rhs_by_label[label], PETSc.Vec)
        or rhs_by_label[label].getSize() != matrix_rows
        for label in labels
    ):
        raise ValueError("V1-1 RHS/operator layout is invalid")

    comm = operator.getComm().tompi4py()
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    residual = operator.createVecLeft()
    pc_context = _V10RightPreconditionerContext(right_preconditioner)
    ksp = PETSc.KSP().create(comm)
    phase_one: dict[str, dict[str, Any]] = {}
    phase_two: dict[str, dict[str, Any]] = {}
    result: dict[str, Any] | None = None
    setup_count = 0

    def solve_one(
        label: str,
        rhs: PETSc.Vec,
        *,
        phase: str,
        max_it: int,
    ) -> dict[str, Any]:
        solution.set(0.0)
        monitor_solution.set(0.0)
        residual.set(0.0)
        rhs_norm = float(rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
            raise ValueError(f"V1-1 mandatory RHS {label} is zero or nonfinite")
        denominator = max(rhs_norm, 1.0e-30)
        checkpoints: dict[str, dict[str, Any]] = {
            "0": {
                "label": label,
                "phase": phase,
                "iteration": 0,
                "reported_relative_residual": 1.0,
                "true_residual_relative": 1.0,
                "finite": True,
            }
        }
        reported_history: list[dict[str, Any]] = []
        true_residual_matvec_count = 0
        started_apply_count = pc_context.apply_count
        first_nonfinite_stage: str | None = None

        def checkpoint_row(
            iteration: int, reported_relative: float, current_solution: PETSc.Vec
        ) -> dict[str, Any]:
            nonlocal true_residual_matvec_count, first_nonfinite_stage
            residual.set(0.0)
            operator.mult(current_solution, residual)
            true_residual_matvec_count += 1
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            true_value = float(residual.norm()) / denominator
            finite = bool(np.isfinite(reported_relative) and np.isfinite(true_value))
            if not finite and first_nonfinite_stage is None:
                first_nonfinite_stage = f"iteration_{iteration}"
            return {
                "label": label,
                "phase": phase,
                "iteration": int(iteration),
                "reported_relative_residual": float(reported_relative),
                "true_residual_relative": true_value,
                "finite": finite,
            }

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            reported = float(residual_norm) / denominator
            reported_history.append(
                {"iteration": int(iteration), "relative_residual": reported}
            )
            if int(iteration) in (4, 8, 16, 32):
                solution_view = current.buildSolution(monitor_solution)
                if solution_view is None:
                    solution_view = monitor_solution
                row = checkpoint_row(int(iteration), reported, solution_view)
                checkpoints[str(iteration)] = row
                if checkpoint_callback is not None:
                    checkpoint_callback(row)
            return 0

        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=int(max_it))
        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        bounded_reasons = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
        }
        ksp_breakdown = bool(reason < 0 and reason not in bounded_reasons)
        return {
            "label": label,
            "phase": phase,
            "ksp_type": str(ksp.getType()),
            "pc_side": "right",
            "restart": 32,
            "max_it": int(max_it),
            "zero_initial_guess": True,
            "zero_initial_guess_count": 1,
            "ksp_reason": reason,
            "ksp_breakdown": ksp_breakdown,
            "iterations": iterations,
            "reported_residual_history": reported_history,
            "checkpoints": checkpoints,
            "first_nonfinite_stage": first_nonfinite_stage,
            "right_pc_apply_count": pc_context.apply_count - started_apply_count,
            "true_residual_matvec_count": true_residual_matvec_count,
            "shared_ksp": True,
            "research_only": True,
        }

    try:
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=16)
        ksp.setUp()
        setup_count = 1
        for label in labels:
            phase_one[label] = solve_one(
                label, rhs_by_label[label], phase="phase1_to_16", max_it=16
            )
        trend_limit = 10.0 ** (-0.25)
        phase_one_gate = {}
        for label in labels:
            checkpoints = phase_one[label]["checkpoints"]
            r8 = checkpoints.get("8", {}).get("true_residual_relative")
            r16 = checkpoints.get("16", {}).get("true_residual_relative")
            phase_one_gate[label] = bool(
                all(
                    checkpoints.get(str(iteration), {}).get("finite") is True
                    for iteration in (4, 8, 16)
                )
                and isinstance(r8, (int, float))
                and isinstance(r16, (int, float))
                and np.isfinite(float(r8))
                and np.isfinite(float(r16))
                and float(r16) <= trend_limit * float(r8)
                and not phase_one[label]["ksp_breakdown"]
            )
        phase1_r16_values = [
            phase_one[label]["checkpoints"].get("16", {}).get("true_residual_relative")
            for label in labels
        ]
        all_five_r16_ge_0p9 = bool(
            all(
                isinstance(value, (int, float))
                and np.isfinite(float(value))
                and float(value) >= 0.9
                for value in phase1_r16_values
            )
        )
        resource = (
            dict(resource_callback())
            if resource_callback is not None
            else {"status": "not_provided", "pass": False}
        )
        resource_pass = bool(resource.get("pass") is True)
        conditional_32_authorized = bool(
            all(phase_one_gate.values()) and resource_pass and not all_five_r16_ge_0p9
        )
        if conditional_32_authorized:
            for label in labels:
                phase_two[label] = solve_one(
                    label, rhs_by_label[label], phase="phase2_to_32", max_it=32
                )
        result = {
            "schema": "task040.v1_1.right_fgmres_batch.v1",
            "labels": list(labels),
            "phase1": phase_one,
            "phase1_gate": phase_one_gate,
            "phase1_trend_limit": trend_limit,
            "all_five_r16_ge_0p9": all_five_r16_ge_0p9,
            "resource_at_phase_boundary": resource,
            "conditional_32_authorized": conditional_32_authorized,
            "phase2": phase_two,
            "phase2_not_run_reason": (
                None
                if conditional_32_authorized
                else (
                    "all_five_r16_ge_0p9"
                    if all_five_r16_ge_0p9
                    else "phase1_all_source_or_resource_gate_failed"
                )
            ),
            "ksp_setup_count": setup_count,
            "ksp_destroy_count": 0,
            "ksp_destroyed": False,
            "right_pc_apply_count": pc_context.apply_count,
            "single_right_pc_setup": True,
            "zero_initial_guess_all_rhs": True,
            "research_only": True,
        }
    finally:
        ksp.destroy()
        pc_context.destroy()
        residual.destroy()
        monitor_solution.destroy()
        solution.destroy()
        if result is not None:
            result["ksp_destroy_count"] = 1
            result["ksp_destroyed"] = True

    if result is None:
        raise RuntimeError("V1-1 FGMRES batch did not produce a result")
    return result


def _supernode_factor_matrix_evidence(matrix: PETSc.Mat) -> dict[str, Any]:
    comm = matrix.getComm().tompi4py()
    row_start, row_end = map(int, matrix.getOwnershipRange())
    row_ptr, columns, values = matrix.getValuesCSR()
    row_lengths = np.diff(row_ptr)
    local_finite = bool(np.all(np.isfinite(values)))
    local_zero_rows = int(np.count_nonzero(row_lengths == 0))
    info = matrix.getInfo()
    ownership_ranges = comm.allgather([row_start, row_end])
    norm_one: float | str
    norm_infinity: float | str
    try:
        norm_one = float(matrix.norm(PETSc.NormType.NORM_1))
        norm_infinity = float(matrix.norm(PETSc.NormType.NORM_INFINITY))
    except Exception:
        norm_one = "not_available"
        norm_infinity = "not_available"
    diagonal_min: float | str = "not_available"
    diagonal_max: float | str = "not_available"
    diagonal = None
    try:
        diagonal = matrix.createVecLeft()
        matrix.getDiagonal(diagonal)
        local_diagonal = np.abs(
            np.asarray(diagonal.getArray(readonly=True), dtype=np.complex128)
        )
        local_diagonal_min = (
            float(np.min(local_diagonal)) if local_diagonal.size else float("inf")
        )
        local_diagonal_max = (
            float(np.max(local_diagonal)) if local_diagonal.size else float("-inf")
        )
        global_diagonal_min = comm.allreduce(local_diagonal_min, op=MPI.MIN)
        global_diagonal_max = comm.allreduce(local_diagonal_max, op=MPI.MAX)
        if np.isfinite(global_diagonal_min) and np.isfinite(global_diagonal_max):
            diagonal_min = float(global_diagonal_min)
            diagonal_max = float(global_diagonal_max)
    except Exception:
        diagonal_min = "not_available"
        diagonal_max = "not_available"
    finally:
        if diagonal is not None:
            diagonal.destroy()
    diagonal_nnz_local = int(
        sum(
            any(
                int(column) == row_start + local_row
                for column in columns[row_ptr[local_row] : row_ptr[local_row + 1]]
            )
            for local_row in range(row_end - row_start)
        )
    )
    return {
        "global_shape": [int(value) for value in matrix.getSize()],
        "local_shape": [int(value) for value in matrix.getLocalSize()],
        "ownership_range": [row_start, row_end],
        "ownership_ranges": ownership_ranges,
        "nnz_local": int(len(columns)),
        "nnz_global": int(comm.allreduce(len(columns), op=MPI.SUM)),
        "diagonal_nnz_local": diagonal_nnz_local,
        "diagonal_nnz_global": int(comm.allreduce(diagonal_nnz_local, op=MPI.SUM)),
        "zero_row_count": int(comm.allreduce(local_zero_rows, op=MPI.SUM)),
        "matrix_norm_1": norm_one,
        "matrix_norm_infinity": norm_infinity,
        "finite_values": bool(comm.allreduce(local_finite, op=MPI.LAND)),
        "diagonal_abs_min": diagonal_min,
        "diagonal_abs_max": diagonal_max,
        "csr_nnz_used": int(info.get("nz_used", len(columns))),
        "mumps_diagnostics": "not_available",
    }


def audit_supernode_factor_paths(
    matrix: PETSc.Mat,
    rhs_vectors: dict[str, PETSc.Vec],
    *,
    lifecycle_callback: Any = None,
) -> dict[str, Any]:
    """Compare conventional and detached factor solves without co-residence.

    The caller owns ``matrix`` and all RHS vectors.  Each path owns one
    temporary factor at a time; every solution and residual workspace is
    cleared before use and destroyed before the next RHS/path.
    """

    if not rhs_vectors:
        raise ValueError("supernode factor forensic requires at least one RHS")
    matrix_evidence = _supernode_factor_matrix_evidence(matrix)
    paths: dict[str, dict[str, Any]] = {}
    first_nonfinite_stage: dict[str, Any] | None = None
    for path_name, factor_only_storage in (
        ("A_conventional_ksp", False),
        ("B_factor_only_detached", True),
    ):
        if lifecycle_callback is not None:
            lifecycle_callback(
                "factor_forensic_path_begin",
                {"path": path_name, "factor_only_storage": factor_only_storage},
            )
        factor = None
        reports: list[dict[str, Any]] = []
        factor_setup_error: dict[str, Any] | None = None
        ready_diagnostics: dict[str, Any] | str = "not_available"
        try:
            factor = ResearchExactFactorInverse(
                matrix,
                factor_solver_type="mumps",
                factor_only_storage=factor_only_storage,
            )
            if factor_only_storage:
                factor.release_borrowed_matrix()
            ready_diagnostics = dict(factor.diagnostics)
            if ready_diagnostics.get("factor_matrix_stats") is None:
                ready_diagnostics["factor_matrix_stats"] = "not_available"
            if lifecycle_callback is not None:
                lifecycle_callback(
                    "factor_forensic_path_ready",
                    {
                        "path": path_name,
                        "factor_only_storage": factor_only_storage,
                        "factor_matrix_stats": ready_diagnostics.get(
                            "factor_matrix_stats"
                        )
                        or "not_available",
                    },
                )
            for label, rhs in rhs_vectors.items():
                solution = matrix.createVecLeft()
                residual = solution.duplicate()
                solution.set(0.0)
                residual.set(0.0)
                rhs_work = rhs.duplicate()
                rhs_work.set(0.0)
                rhs.copy(rhs_work)
                rhs_norm: float | None = None
                solution_norm: float | None = None
                try:
                    rhs_norm_value = float(rhs_work.norm())
                    rhs_norm = rhs_norm_value if np.isfinite(rhs_norm_value) else None
                    if rhs_norm is None:
                        report = {
                            "label": label,
                            "status": "nonfinite_rhs_norm",
                            "finite": False,
                            "mandatory": label == "zero_rhs",
                            "degenerate": False,
                            "rhs_norm": None,
                            "solution_norm": None,
                            "relative_residual": None,
                            "norm_amplification": None,
                            "first_nonfinite_stage": "rhs_norm",
                        }
                        reports.append(report)
                        if first_nonfinite_stage is None:
                            first_nonfinite_stage = {
                                "path": path_name,
                                "label": label,
                                "stage": "rhs_norm",
                            }
                        continue
                    factor.solve(rhs_work, solution)
                    solution_norm_value = float(solution.norm())
                    solution_norm = (
                        solution_norm_value
                        if np.isfinite(solution_norm_value)
                        else None
                    )
                    local_values = np.asarray(
                        solution.getArray(readonly=True), dtype=np.complex128
                    )
                    solution_values_finite = bool(
                        matrix.getComm()
                        .tompi4py()
                        .allreduce(bool(np.all(np.isfinite(local_values))), op=MPI.LAND)
                    )
                    if not solution_values_finite:
                        report = {
                            "label": label,
                            "status": "nonfinite_solution",
                            "finite": False,
                            "mandatory": label == "zero_rhs" or rhs_norm != 0.0,
                            "degenerate": bool(rhs_norm == 0.0),
                            "rhs_norm": rhs_norm,
                            "solution_norm": solution_norm,
                            "relative_residual": None,
                            "norm_amplification": None,
                            "first_nonfinite_stage": "solve_output",
                        }
                        if first_nonfinite_stage is None:
                            first_nonfinite_stage = {
                                "path": path_name,
                                "label": label,
                                "stage": "solve_output",
                            }
                    elif solution_norm is None:
                        report = {
                            "label": label,
                            "status": "nonfinite_solution_norm",
                            "finite": False,
                            "mandatory": label == "zero_rhs" or rhs_norm != 0.0,
                            "degenerate": bool(rhs_norm == 0.0),
                            "rhs_norm": rhs_norm,
                            "solution_norm": None,
                            "relative_residual": None,
                            "norm_amplification": None,
                            "first_nonfinite_stage": "solution_norm",
                        }
                        reports.append(report)
                        if first_nonfinite_stage is None:
                            first_nonfinite_stage = {
                                "path": path_name,
                                "label": label,
                                "stage": "solution_norm",
                            }
                        continue
                    else:
                        residual.set(0.0)
                        matrix.mult(solution, residual)
                        residual.axpy(PETSc.ScalarType(-1.0), rhs_work)
                        denominator = max(rhs_norm_value, 1.0e-30)
                        residual_value = float(residual.norm()) / denominator
                        amplification = solution_norm_value / denominator
                        residual_finite = bool(np.isfinite(residual_value))
                        amplification_finite = bool(np.isfinite(amplification))
                        finite = bool(
                            rhs_norm is not None
                            and solution_norm is not None
                            and residual_finite
                            and amplification_finite
                        )
                        degenerate = bool(rhs_norm_value <= 1.0e-30)
                        first_report_nonfinite_stage = None
                        if not residual_finite:
                            first_report_nonfinite_stage = "residual"
                        elif not amplification_finite:
                            first_report_nonfinite_stage = "amplification"
                        if (
                            first_report_nonfinite_stage is not None
                            and first_nonfinite_stage is None
                        ):
                            first_nonfinite_stage = {
                                "path": path_name,
                                "label": label,
                                "stage": first_report_nonfinite_stage,
                            }
                        report = {
                            "label": label,
                            "status": (
                                "degenerate_zero_map"
                                if degenerate and finite
                                else "measured"
                                if finite
                                else f"nonfinite_{first_report_nonfinite_stage}"
                            ),
                            "finite": finite,
                            "mandatory": label == "zero_rhs" or not degenerate,
                            "degenerate": degenerate,
                            "rhs_norm": rhs_norm,
                            "solution_norm": solution_norm,
                            "relative_residual": (
                                residual_value if residual_finite else None
                            ),
                            "norm_amplification": (
                                amplification if amplification_finite else None
                            ),
                            "first_nonfinite_stage": first_report_nonfinite_stage,
                        }
                    reports.append(report)
                except Exception as exc:
                    reports.append(
                        {
                            "label": label,
                            "status": "explicit_solve_failure",
                            "finite": False,
                            "mandatory": label == "zero_rhs" or rhs_norm != 0.0,
                            "degenerate": bool(rhs_norm == 0.0),
                            "rhs_norm": rhs_norm,
                            "solution_norm": solution_norm,
                            "relative_residual": None,
                            "norm_amplification": None,
                            "first_nonfinite_stage": "solve_exception",
                            "exception_type": type(exc).__name__,
                        }
                    )
                finally:
                    residual.destroy()
                    solution.destroy()
                    rhs_work.destroy()
        except Exception as exc:
            factor_setup_error = {
                "status": "explicit_factor_setup_failure",
                "exception_type": type(exc).__name__,
            }
            reports = [
                {
                    "label": label,
                    "status": "not_run_factor_setup_failure",
                    "finite": False,
                    "mandatory": label == "zero_rhs",
                    "degenerate": False,
                    "rhs_norm": None,
                    "solution_norm": None,
                    "relative_residual": None,
                    "norm_amplification": None,
                    "first_nonfinite_stage": "factor_setup",
                }
                for label in rhs_vectors
            ]
        finally:
            after_diagnostics: dict[str, Any] | str = "not_available"
            if factor is not None:
                factor.destroy()
                after_diagnostics = dict(factor.diagnostics)
                if after_diagnostics.get("factor_matrix_stats") is None:
                    after_diagnostics["factor_matrix_stats"] = "not_available"
            if lifecycle_callback is not None:
                lifecycle_callback(
                    "factor_forensic_path_cleanup",
                    {
                        "path": path_name,
                        "factor_count_after_cleanup": (
                            after_diagnostics.get("exact_factor_count", "not_available")
                            if isinstance(after_diagnostics, dict)
                            else "not_available"
                        ),
                        "co_resident_factor_count": 0,
                    },
                )
        nonzero_reports = [
            report for report in reports if report["label"] != "zero_rhs"
        ]

        def _report_pass(report: Mapping[str, Any]) -> bool:
            if report.get("finite") is not True:
                return False
            if report.get("label") == "zero_rhs":
                solution_norm = report.get("solution_norm")
                return solution_norm is not None and solution_norm <= 1.0e-13
            if report.get("degenerate") is True:
                return True
            return bool(
                report.get("norm_amplification") is not None
                and np.isfinite(report["norm_amplification"])
                and report.get("relative_residual") is not None
                and report["relative_residual"] <= 1.0e-9
            )

        for report in reports:
            report["gate_pass"] = _report_pass(report)
        path_pass = bool(all(report["gate_pass"] for report in reports))
        paths[path_name] = {
            "factor_only_storage": factor_only_storage,
            "reports": reports,
            "path_pass": path_pass,
            "factor_setup": factor_setup_error or {"status": "measured"},
            "factor_diagnostics_ready": ready_diagnostics,
            "factor_diagnostics_after_cleanup": after_diagnostics,
            "nonzero_report_count": len(nonzero_reports),
            "factor_count_after_cleanup": 0,
            "co_resident_factor_count": 0,
        }
    return {
        "matrix_evidence": matrix_evidence,
        "paths": paths,
        "path_order": ["A_conventional_ksp", "B_factor_only_detached"],
        "paths_strictly_serial": True,
        "first_nonfinite_stage": first_nonfinite_stage,
        "mumps_info": "not_available",
    }


def build_real_layer_labels(
    matrix: PETSc.Mat, system: Any
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build the deterministic assembly-time trace-row layer mapping.

    Cell geometry and the retained cell recovery/constraint maps are the
    authority.  A trace row shared by cells is assigned the minimum incident
    z-layer.  Only the compact int32 label array is reduced across MPI.
    """

    condensed = system.static_condensation.condensed
    constraints = condensed.trace_constraints
    z_values = np.asarray(system.local_mesh.z_values, dtype=np.float64)
    if z_values.ndim != 1 or len(z_values) < 2 or np.any(np.diff(z_values) <= 0):
        raise ValueError("layer mapping requires a strictly ordered z axis")
    global_rows = int(matrix.getSize()[0])
    sentinel = np.iinfo(np.int32).max
    partial = np.full(global_rows, sentinel, dtype=np.int32)
    geometry = system.local_mesh.mesh.geometry
    for cell, recovery in enumerate(condensed.cell_recovery_maps):
        geometry_indices = np.asarray(geometry.dofmap[cell], dtype=np.int64)
        centroid_z = float(np.mean(geometry.x[geometry_indices, 2]))
        layer = int(np.searchsorted(z_values, centroid_z, side="right") - 1)
        if layer < 0 or layer >= len(z_values) - 1:
            raise ValueError("cell centroid is outside the real z-layer axis")
        for original in recovery.trace_original_dofs:
            expansion = constraints.expansion_by_original.get(int(original))
            if expansion is None:
                raise ValueError("trace row has no assembly-time expansion")
            active_ids = np.asarray(expansion[0], dtype=np.int64)
            for active_id in active_ids:
                active = int(active_id)
                if active < 0 or active >= global_rows:
                    raise ValueError("active trace row is outside F")
                partial[active] = min(partial[active], layer)
    comm = matrix.getComm().tompi4py()
    labels = minimum_layer_labels(partial, global_rows, comm)
    metadata = {
        "z_layer_boundaries": [float(value) for value in z_values],
        "mapping_source": (
            "owned_cell_recovery_maps + trace_constraints.expansion_by_original "
            "+ local_mesh.geometry.z_values"
        ),
        "shared_trace_row_rule": "minimum_incident_owned_cell_layer",
    }
    del partial
    return labels, metadata


def _hash_array(hasher: Any, values: np.ndarray) -> None:
    raw = np.asarray(values)
    hasher.update(str(raw.dtype).encode("ascii"))
    hasher.update(np.asarray(raw.shape, dtype=np.int64).tobytes())
    view = np.ascontiguousarray(raw).view(np.uint8)
    for start in range(0, view.size, 1 << 20):
        hasher.update(view[start : start + (1 << 20)])


def _csr_hash(
    row_ptr: np.ndarray, columns: np.ndarray, values: np.ndarray
) -> tuple[str, int]:
    hasher = hashlib.sha256()
    _hash_array(hasher, row_ptr)
    _hash_array(hasher, columns)
    _hash_array(hasher, values)
    return hasher.hexdigest(), int(row_ptr.nbytes + columns.nbytes + values.nbytes)


@dataclass
class _LayerBlock:
    name: str
    row_layer: int
    column_layer: int
    rows_owned_local: int
    columns_owned_local: int
    matrix: PETSc.Mat | None
    local_nnz: int
    csr_bytes: int
    local_hash: str

    def destroy(self) -> None:
        if self.matrix is not None:
            self.matrix.destroy()
            self.matrix = None


@dataclass
class _LayerWorkspace:
    layer: int
    x: PETSc.Vec
    y: PETSc.Vec
    temp: PETSc.Vec
    scatter: PETSc.Scatter

    def destroy(self) -> None:
        self.scatter.destroy()
        self.temp.destroy()
        self.y.destroy()
        self.x.destroy()


class LayerBlockOperator:
    """Distributed sparse ``D_i/L_i/U_i`` action over the original F layout."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        global_layer_labels: np.ndarray,
        *,
        layer_count: int,
        mapping_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._matrix = matrix
        self._comm = matrix.getComm().tompi4py()
        self._destroyed = False
        global_rows, global_cols = map(int, matrix.getSize())
        if global_rows != global_cols:
            raise ValueError("layer block operator requires a square F")
        labels = np.asarray(global_layer_labels, dtype=np.int32)
        if labels.shape != (global_rows,) or np.any(labels < 0):
            raise ValueError("global layer labels do not match F")
        if np.any(labels >= int(layer_count)):
            raise ValueError("global layer label exceeds layer count")
        self._labels = np.array(labels, dtype=np.int32, copy=True)
        self._layer_count = int(layer_count)
        self._permutation = np.argsort(self._labels, kind="stable").astype(
            PETSc.IntType, copy=False
        )
        self._inverse_permutation = np.empty_like(self._permutation)
        self._inverse_permutation[self._permutation] = np.arange(
            global_rows, dtype=PETSc.IntType
        )
        row_start, row_end = map(int, matrix.getOwnershipRange())
        local_labels = self._labels[row_start:row_end]
        self._row_ids_by_layer = tuple(
            np.flatnonzero(local_labels == layer).astype(PETSc.IntType) + row_start
            for layer in range(self._layer_count)
        )
        self._column_ids_by_layer = self._row_ids_by_layer
        self._parent_template = matrix.createVecRight()
        self._layer_is: tuple[PETSc.IS, ...] = tuple(
            PETSc.IS().createGeneral(ids, comm=matrix.getComm())
            for ids in self._column_ids_by_layer
        )
        self._blocks: list[_LayerBlock] = []
        self._workspaces: list[_LayerWorkspace] = []
        self._diagnostics = {
            "status": "construction_failed",
            "construction_marker": "started",
            "destroy_marker": "pending",
        }
        try:
            row_ptr, columns, values = matrix.getValuesCSR()
            self._graph = self._graph_stats(row_ptr, columns)
            self._original_nnz_local = int(len(columns))
            self._original_nnz_global = int(
                self._comm.allreduce(self._original_nnz_local, op=MPI.SUM)
            )
            for row_layer, column_layer, name in self._block_specs():
                self._blocks.append(self._build_block(row_layer, column_layer, name))
            self._workspaces = [
                self._build_workspace(layer) for layer in range(self._layer_count)
            ]
            self._diagnostics = self._make_diagnostics(
                mapping_metadata=mapping_metadata or {},
            )
        except Exception:
            self.destroy()
            raise

    def _block_specs(self):
        for layer in range(self._layer_count):
            yield layer, layer, f"D_{layer}"
        for layer in range(self._layer_count - 1):
            yield layer + 1, layer, f"L_{layer + 1}"
        for layer in range(self._layer_count - 1):
            yield layer, layer + 1, f"U_{layer}"

    def _build_block(self, row_layer: int, column_layer: int, name: str) -> _LayerBlock:
        row_ids = self._row_ids_by_layer[row_layer]
        column_ids = self._column_ids_by_layer[column_layer]
        submatrix = self._matrix.createSubMatrix(
            self._layer_is[row_layer], self._layer_is[column_layer]
        )
        row_ptr, columns, values = submatrix.getValuesCSR()
        local_hash, csr_bytes = _csr_hash(row_ptr, columns, values)
        return _LayerBlock(
            name=name,
            row_layer=row_layer,
            column_layer=column_layer,
            rows_owned_local=len(row_ids),
            columns_owned_local=len(column_ids),
            matrix=submatrix,
            local_nnz=int(len(columns)),
            csr_bytes=csr_bytes,
            local_hash=local_hash,
        )

    def _build_workspace(self, layer: int) -> _LayerWorkspace:
        diagonal = self._blocks[layer].matrix
        x = diagonal.createVecRight()
        y = diagonal.createVecLeft()
        temp = y.duplicate()
        local_start, local_end = map(int, x.getOwnershipRange())
        layer_positions = PETSc.IS().createStride(
            local_end - local_start,
            first=local_start,
            step=1,
            comm=self._matrix.getComm(),
        )
        try:
            scatter = PETSc.Scatter().create(
                self._parent_template,
                self._layer_is[layer],
                x,
                layer_positions,
            )
        except Exception:
            temp.destroy()
            y.destroy()
            x.destroy()
            raise
        finally:
            layer_positions.destroy()
        return _LayerWorkspace(layer=layer, x=x, y=y, temp=temp, scatter=scatter)

    def _graph_stats(self, row_ptr: np.ndarray, columns: np.ndarray) -> dict[str, Any]:
        local_labels = self._labels[
            self._matrix.getOwnershipRange()[0] : self._matrix.getOwnershipRange()[1]
        ]
        pair = np.zeros((self._layer_count, self._layer_count), dtype=np.int64)
        rows = np.bincount(local_labels, minlength=self._layer_count).astype(np.int64)
        same = adjacent = long_range = bandwidth = 0
        for local_row, row_layer in enumerate(local_labels):
            cols = columns[row_ptr[local_row] : row_ptr[local_row + 1]]
            col_layers = self._labels[cols]
            deltas = np.abs(col_layers - int(row_layer))
            np.add.at(pair[int(row_layer)], col_layers, 1)
            same += int(np.count_nonzero(deltas == 0))
            adjacent += int(np.count_nonzero(deltas == 1))
            long_range += int(np.count_nonzero(deltas > 1))
            if len(deltas):
                bandwidth = max(bandwidth, int(np.max(deltas)))
        pair = np.asarray(self._comm.allreduce(pair, op=MPI.SUM))
        rows = np.asarray(self._comm.allreduce(rows, op=MPI.SUM))
        classes = np.asarray(
            self._comm.allreduce(
                np.asarray([same, adjacent, long_range], dtype=np.int64),
                op=MPI.SUM,
            )
        )
        bandwidth = int(self._comm.allreduce(bandwidth, op=MPI.MAX))
        total = int(np.sum(pair))
        return {
            "rows_global": int(np.sum(rows)),
            "rows_by_layer": [int(value) for value in rows],
            "layer_pair_nnz": pair.tolist(),
            "nnz_total": total,
            "same_layer_nnz": int(classes[0]),
            "adjacent_layer_nnz": int(classes[1]),
            "long_range_nnz": int(classes[2]),
            "block_half_bandwidth": bandwidth,
        }

    def _make_diagnostics(self, *, mapping_metadata: dict[str, Any]) -> dict[str, Any]:
        local_rows = [len(ids) for ids in self._row_ids_by_layer]
        ownership = self._comm.allgather(local_rows)
        block_records: dict[str, Any] = {}
        for block in self._blocks:
            global_nnz = int(self._comm.allreduce(block.local_nnz, op=MPI.SUM))
            global_csr_bytes = int(self._comm.allreduce(block.csr_bytes, op=MPI.SUM))
            hashes = self._comm.allgather(block.local_hash)
            rank_inventory = self._comm.allgather(
                {
                    "rank": self._comm.rank,
                    "rows_owned_local": block.rows_owned_local,
                    "columns_owned_local": block.columns_owned_local,
                    "nnz_local": block.local_nnz,
                    "csr_bytes_local": block.csr_bytes,
                    "hash": block.local_hash,
                }
            )
            hash_bytes = json.dumps(hashes, separators=(",", ":")).encode()
            block_records[block.name] = {
                "row_layer": block.row_layer,
                "column_layer": block.column_layer,
                "rows_owned_local": block.rows_owned_local,
                "columns_owned_local": block.columns_owned_local,
                "rows_global": self._graph["rows_by_layer"][block.row_layer],
                "nnz_local": block.local_nnz,
                "nnz_global": global_nnz,
                "csr_bytes_local": block.csr_bytes,
                "csr_bytes_global": global_csr_bytes,
                "per_rank": rank_inventory,
                "hash": hashlib.sha256(hash_bytes).hexdigest(),
            }
        block_nnz = sum(record["nnz_global"] for record in block_records.values())
        return {
            "status": "measured",
            "layer_count": self._layer_count,
            "row_coverage_exact": bool(
                sum(self._graph["rows_by_layer"]) == self._graph["rows_global"]
                and all(value >= 0 for value in self._graph["rows_by_layer"])
            ),
            "per_layer_ownership": ownership,
            "layer_workspace_count": len(self._workspaces),
            "layer_workspace_layouts": [
                {
                    "layer": workspace.layer,
                    "global_size": workspace.x.getSize(),
                    "local_size": workspace.x.getLocalSize(),
                    "ownership_range": list(map(int, workspace.x.getOwnershipRange())),
                }
                for workspace in self._workspaces
            ],
            "permutation_hash": hashlib.sha256(self._permutation.tobytes()).hexdigest(),
            "inverse_permutation_hash": hashlib.sha256(
                self._inverse_permutation.tobytes()
            ).hexdigest(),
            "blocks": block_records,
            "nnz_partition": {
                "original_f_global": self._original_nnz_global,
                "diagonal_and_adjacent_blocks_global": block_nnz,
                "partition_exact": block_nnz == self._original_nnz_global,
            },
            "graph": self._graph,
            "long_range_nnz": self._graph["long_range_nnz"],
            "block_half_bandwidth": self._graph["block_half_bandwidth"],
            "construction_marker": "completed",
            "destroy_marker": "pending",
            "borrowed_f_matrix": True,
            "factor_count": 0,
            "qep_count": 0,
            "outer_ksp_count": 0,
            **mapping_metadata,
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        return self._diagnostics

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("layer block operator has been destroyed")
        if source.getSize() != self._matrix.getSize()[1]:
            raise ValueError("source vector does not match F layout")
        if target.getSize() != self._matrix.getSize()[0]:
            raise ValueError("target vector does not match F layout")
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.x,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            workspace.y.set(0.0)
        for block in self._blocks:
            block.matrix.mult(
                self._workspaces[block.column_layer].x,
                self._workspaces[block.row_layer].temp,
            )
            self._workspaces[block.row_layer].y.axpy(
                PETSc.ScalarType(1.0), self._workspaces[block.row_layer].temp
            )
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def destroy(self) -> None:
        if self._destroyed:
            return
        for block in self._blocks:
            block.destroy()
        self._blocks.clear()
        for workspace in self._workspaces:
            workspace.destroy()
        self._workspaces.clear()
        for layer_is in getattr(self, "_layer_is", ()):
            layer_is.destroy()
        self._layer_is = ()
        self._parent_template.destroy()
        self._labels = None
        self._permutation = None
        self._inverse_permutation = None
        self._diagnostics["destroy_marker"] = "completed"
        self._diagnostics["factor_count"] = 0
        self._diagnostics["qep_count"] = 0
        self._diagnostics["outer_ksp_count"] = 0
        self._destroyed = True


def _normalise_tiny_block_chain(
    diagonal_blocks: Any, lower_blocks: Any, upper_blocks: Any
) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    diagonal = tuple(
        np.array(block, dtype=np.complex128, copy=True, order="F")
        for block in diagonal_blocks
    )
    lower = tuple(
        np.array(block, dtype=np.complex128, copy=True, order="F")
        for block in lower_blocks
    )
    upper = tuple(
        np.array(block, dtype=np.complex128, copy=True, order="F")
        for block in upper_blocks
    )
    if not diagonal:
        raise ValueError("At least one diagonal block is required")
    block_count = len(diagonal)
    if len(lower) != block_count - 1 or len(upper) != block_count - 1:
        raise ValueError("Off-diagonal block counts must be block_count - 1")
    block_size = diagonal[0].shape[0]
    if any(
        block.ndim != 2 or block.shape != (block_size, block_size) for block in diagonal
    ):
        raise ValueError("Diagonal blocks must be equally sized square matrices")
    if any(block.shape != (block_size, block_size) for block in (*lower, *upper)):
        raise ValueError("Off-diagonal blocks must match diagonal block size")
    return diagonal, lower, upper


def _tiny_rhs_blocks(
    rhs: Any, block_count: int, block_size: int
) -> tuple[np.ndarray, bool]:
    values = np.asarray(rhs, dtype=np.complex128)
    if values.ndim == 1:
        if values.size != block_count * block_size:
            raise ValueError("Tiny block RHS has the wrong size")
        return (
            np.array(
                values.reshape(block_count, block_size, 1),
                dtype=np.complex128,
                order="F",
                copy=True,
            ),
            True,
        )
    if values.ndim == 2 and values.shape[0] == block_count * block_size:
        return (
            np.array(
                values.reshape(block_count, block_size, values.shape[1]),
                dtype=np.complex128,
                order="F",
                copy=True,
            ),
            False,
        )
    raise ValueError("Tiny block RHS must be a vector or a row-stacked matrix")


def _tiny_stack_solution(solution: list[np.ndarray], vector_rhs: bool) -> np.ndarray:
    stacked = np.vstack(solution)
    return stacked[:, 0] if vector_rhs else stacked


class ExactBlockSchurAction:
    """Research-only exact block Thomas action for tiny dense algebra.

    The input blocks are copied only for this tiny oracle.  Diagonal blocks are
    immediately reduced to LU factors and are not retained as explicit
    diagonal matrices.  This class is intentionally not the h4 distributed
    route; it provides an independent Schur formula authority for V9-2.
    """

    def __init__(
        self,
        diagonal_blocks: Any,
        lower_blocks: Any,
        upper_blocks: Any,
        *,
        lifecycle_callback: Any = None,
    ) -> None:
        diagonal, lower, upper = _normalise_tiny_block_chain(
            diagonal_blocks, lower_blocks, upper_blocks
        )
        self._block_count = len(diagonal)
        self._block_size = diagonal[0].shape[0]
        self._lower = lower
        self._upper = upper
        self._factors: list[tuple[np.ndarray, np.ndarray]] = []
        self._lifecycle_callback = lifecycle_callback
        self._destroyed = False
        self._apply_count = 0
        try:
            self._factors.append(
                lu_factor(diagonal[0], overwrite_a=True, check_finite=False)
            )
            for index in range(1, self._block_count):
                previous = self._factors[index - 1]
                upper_solve = lu_solve(previous, upper[index - 1], check_finite=False)
                schur = diagonal[index] - lower[index - 1] @ upper_solve
                self._factors.append(
                    lu_factor(schur, overwrite_a=True, check_finite=False)
                )
                if lifecycle_callback is not None:
                    lifecycle_callback(
                        "exact_block_schur_factor_ready", {"block": index}
                    )
        except Exception:
            self._factors.clear()
            self._lower = ()
            self._upper = ()
            raise
        finally:
            del diagonal

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "schema": "task039.v9.tiny.exact_block_schur.v1",
            "kind": "exact_block_thomas_schur",
            "block_count": self._block_count,
            "block_size": self._block_size,
            "factor_count_ready": 0 if self._destroyed else len(self._factors),
            "factor_count_after_cleanup": 0 if self._destroyed else None,
            "retained_explicit_diagonal_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "apply_count": self._apply_count,
            "destroy_marker": "completed" if self._destroyed else "pending",
            "factor_only_storage": True,
        }

    @property
    def factor_only_storage(self) -> bool:
        return True

    def apply(self, rhs: Any) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("exact block Schur action has been destroyed")
        rhs_blocks, vector_rhs = _tiny_rhs_blocks(
            rhs, self._block_count, self._block_size
        )
        reduced_rhs = [rhs_blocks[0].copy(order="F")]
        for index in range(1, self._block_count):
            previous = self._factors[index - 1]
            previous_solution = lu_solve(
                previous, reduced_rhs[index - 1], check_finite=False
            )
            reduced_rhs.append(
                rhs_blocks[index] - self._lower[index - 1] @ previous_solution
            )
        solution: list[np.ndarray] = [
            np.empty_like(reduced_rhs[0]) for _ in range(self._block_count)
        ]
        solution[-1] = lu_solve(self._factors[-1], reduced_rhs[-1], check_finite=False)
        for index in range(self._block_count - 2, -1, -1):
            solution[index] = lu_solve(
                self._factors[index],
                reduced_rhs[index] - self._upper[index] @ solution[index + 1],
                check_finite=False,
            )
        self._apply_count += 1
        return _tiny_stack_solution(solution, vector_rhs)

    def solve(self, rhs: Any) -> np.ndarray:
        return self.apply(rhs)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._factors.clear()
        self._lower = ()
        self._upper = ()
        self._destroyed = True
        if self._lifecycle_callback is not None:
            self._lifecycle_callback("exact_block_schur_destroyed", self.diagnostics)


@dataclass
class _SupernodeWorkspace:
    group: int
    rhs: PETSc.Vec
    y: PETSc.Vec
    temp: PETSc.Vec
    correction: PETSc.Vec
    scatter: PETSc.Scatter

    def destroy(self) -> None:
        self.scatter.destroy()
        self.correction.destroy()
        self.temp.destroy()
        self.y.destroy()
        self.rhs.destroy()


class FixedTwoLayerSupernodeAction:
    """Distributed fixed SN2-J/SN2-SGS action over the real sparse ``F``.

    The groups are frozen to ``[0, 1]``, ``[2, 3]`` and ``[4, 5]``.  Three
    parallel PETSc submatrices are factorized once with factor-only storage;
    the original matrix is borrowed and is never retained by this action.
    ``SN2-SGS`` is ``(B+U)^-1 B (B+L)^-1`` with sparse cross-supernode
    couplings only at layer boundaries 1↔2 and 3↔4.
    """

    GROUPS = ((0, 1), (2, 3), (4, 5))
    METHODS = ("SN2-J", "SN2-SGS")

    def __init__(
        self,
        *,
        factors: list[ResearchExactFactorInverse],
        lower: list[PETSc.Mat],
        upper: list[PETSc.Mat],
        workspaces: list[_SupernodeWorkspace],
        group_is: tuple[PETSc.IS, ...],
        parent_template: PETSc.Vec,
        factor_records: list[dict[str, Any]],
        supernode_rows_global: list[int],
        supernode_row_coverage_exact: bool,
        lifecycle_callback: Any,
    ) -> None:
        self._factors = factors
        self._lower = lower
        self._upper = upper
        self._workspaces = workspaces
        self._group_is = group_is
        self._parent_template = parent_template
        self._factor_records = factor_records
        self._lifecycle_callback = lifecycle_callback
        self._destroyed = False
        self._apply_count = {method: 0 for method in self.METHODS}
        self._factor_solve_count = {method: 0 for method in self.METHODS}
        self._diagnostics = {
            "schema": "task039.v9.fixed_two_layer_supernode.v1",
            "kind": "fixed_two_layer_supernode",
            "groups": [list(group) for group in self.GROUPS],
            "candidate_methods": list(self.METHODS),
            "supernode_factor_count_ready": len(factors),
            "factor_count_ready": len(factors),
            "factor_count_after_cleanup": None,
            "factor_count": len(factors),
            "factor_set_build_count": 1,
            "single_factor_set": True,
            "factor_records": factor_records,
            "supernode_rows_global": list(supernode_rows_global),
            "supernode_row_coverage_exact": bool(supernode_row_coverage_exact),
            "cross_lower_block_count": len(lower),
            "cross_upper_block_count": len(upper),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "method_apply_count": dict(self._apply_count),
            "method_factor_solve_count": dict(self._factor_solve_count),
            "destroy_marker": "pending",
        }

    @classmethod
    def from_matrix(
        cls,
        matrix: PETSc.Mat,
        global_layer_labels: np.ndarray,
        *,
        layer_count: int = 6,
        lifecycle_callback: Any = None,
    ) -> "FixedTwoLayerSupernodeAction":
        if layer_count != 6:
            raise ValueError("V9-2 supernodes require exactly six layers")
        rows, cols = map(int, matrix.getSize())
        if rows != cols:
            raise ValueError("V9-2 supernode action requires a square matrix")
        labels = np.asarray(global_layer_labels, dtype=np.int32)
        if labels.shape != (rows,) or np.any(labels < 0) or np.any(labels >= 6):
            raise ValueError("V9-2 supernode labels do not match the matrix")
        comm = matrix.getComm()
        comm4py = comm.tompi4py()
        row_start, row_end = map(int, matrix.getOwnershipRange())
        local_labels = labels[row_start:row_end]
        group_ids = tuple(
            np.flatnonzero(
                np.logical_or(
                    local_labels == first,
                    local_labels == second,
                )
            ).astype(PETSc.IntType)
            + row_start
            for first, second in cls.GROUPS
        )
        group_is = tuple(PETSc.IS().createGeneral(ids, comm=comm) for ids in group_ids)
        parent_template = matrix.createVecRight()
        factors: list[ResearchExactFactorInverse] = []
        lower: list[PETSc.Mat] = []
        upper: list[PETSc.Mat] = []
        workspaces: list[_SupernodeWorkspace] = []
        factor_records: list[dict[str, Any]] = []
        supernode_rows_global = [
            int(comm4py.allreduce(len(ids), op=MPI.SUM)) for ids in group_ids
        ]
        supernode_row_coverage_exact = sum(supernode_rows_global) == rows and all(
            value >= 0 for value in supernode_rows_global
        )

        def cleanup_partial() -> None:
            for workspace in reversed(workspaces):
                workspace.destroy()
            workspaces.clear()
            for block in reversed(lower):
                block.destroy()
            lower.clear()
            for block in reversed(upper):
                block.destroy()
            upper.clear()
            for factor in reversed(factors):
                factor.destroy()
            factors.clear()
            for group_is_item in group_is:
                group_is_item.destroy()
            parent_template.destroy()

        try:
            for group, (first, second) in enumerate(cls.GROUPS):
                if lifecycle_callback is not None:
                    lifecycle_callback(
                        "supernode_factor_setup_begin",
                        {"supernode": group, "layers": [first, second]},
                    )
                diagonal = matrix.createSubMatrix(group_is[group], group_is[group])
                factor = None
                try:
                    factor = ResearchExactFactorInverse(
                        diagonal,
                        factor_solver_type="mumps",
                        factor_only_storage=True,
                    )
                    factor.release_borrowed_matrix()
                    factors.append(factor)
                    local_rows = int(diagonal.getLocalSize()[0])
                    nnz_local = int(diagonal.getInfo()["nz_used"])
                    factor_records.append(
                        {
                            "supernode": group,
                            "layers": [first, second],
                            "rows_owned_local": local_rows,
                            "rows_global": int(diagonal.getSize()[0]),
                            "nnz_local": nnz_local,
                            "nnz_global": int(comm4py.allreduce(nnz_local, op=MPI.SUM)),
                            "factor_matrix_stats": factor.diagnostics[
                                "factor_matrix_stats"
                            ],
                            "factor_only_storage": True,
                            "borrowed_matrix_released": True,
                            "factor_matrix_alive": True,
                        }
                    )
                except Exception:
                    if factor is not None:
                        factor.destroy()
                    raise
                finally:
                    diagonal.destroy()
                if lifecycle_callback is not None:
                    lifecycle_callback(
                        "supernode_factor_ready",
                        {"supernode": group, "factor_only_storage": True},
                    )

            for group in range(2):
                lower.append(
                    matrix.createSubMatrix(group_is[group + 1], group_is[group])
                )
                upper.append(
                    matrix.createSubMatrix(group_is[group], group_is[group + 1])
                )

            for group, factor in enumerate(factors):
                factor_matrix = factor.operator
                if factor_matrix is None:
                    raise RuntimeError(f"Supernode {group} factor has no operator")
                rhs = factor_matrix.createVecRight()
                y = factor_matrix.createVecLeft()
                temp = y.duplicate()
                correction = y.duplicate()
                first, last = map(int, rhs.getOwnershipRange())
                positions = PETSc.IS().createStride(
                    last - first,
                    first=first,
                    step=1,
                    comm=comm,
                )
                try:
                    scatter = PETSc.Scatter().create(
                        parent_template,
                        group_is[group],
                        rhs,
                        positions,
                    )
                except Exception:
                    correction.destroy()
                    temp.destroy()
                    y.destroy()
                    rhs.destroy()
                    raise
                finally:
                    positions.destroy()
                workspaces.append(
                    _SupernodeWorkspace(
                        group=group,
                        rhs=rhs,
                        y=y,
                        temp=temp,
                        correction=correction,
                        scatter=scatter,
                    )
                )
            action = cls(
                factors=factors,
                lower=lower,
                upper=upper,
                workspaces=workspaces,
                group_is=group_is,
                parent_template=parent_template,
                factor_records=factor_records,
                supernode_rows_global=supernode_rows_global,
                supernode_row_coverage_exact=supernode_row_coverage_exact,
                lifecycle_callback=lifecycle_callback,
            )
            return action
        except Exception:
            cleanup_partial()
            raise

    @property
    def diagnostics(self) -> dict[str, Any]:
        diagnostics = dict(self._diagnostics)
        diagnostics["factor_count_ready"] = 0 if self._destroyed else len(self._factors)
        diagnostics["supernode_factor_count_ready"] = diagnostics["factor_count_ready"]
        diagnostics["factor_count"] = diagnostics["factor_count_ready"]
        diagnostics["factor_count_after_cleanup"] = 0 if self._destroyed else None
        diagnostics["method_apply_count"] = dict(self._apply_count)
        diagnostics["method_factor_solve_count"] = dict(self._factor_solve_count)
        diagnostics["destroy_marker"] = "completed" if self._destroyed else "pending"
        return diagnostics

    @property
    def factor_only_storage(self) -> bool:
        return True

    def _solve_factor(
        self, group: int, source: PETSc.Vec, target: PETSc.Vec, method: str
    ) -> None:
        self._factors[group].solve(source, target)
        self._factor_solve_count[method] += 1

    def _gather(self, source: PETSc.Vec) -> None:
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.rhs,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )

    def _forward(self, method: str) -> None:
        for group, workspace in enumerate(self._workspaces):
            if group:
                self._lower[group - 1].mult(
                    self._workspaces[group - 1].y,
                    workspace.temp,
                )
                workspace.rhs.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve_factor(group, workspace.rhs, workspace.y, method)

    def _scatter_solution(self, target: PETSc.Vec) -> None:
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def apply_checkpoint(
        self,
        method: str,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("two-layer supernode action has been destroyed")
        if method not in self.METHODS:
            raise ValueError(f"Unsupported V9-2 supernode method: {method}")
        expected_size = self._parent_template.getSize()
        if source.getSize() != expected_size or target.getSize() != expected_size:
            raise ValueError("supernode vector does not match matrix layout")
        self._gather(source)
        if method == "SN2-J":
            for group, workspace in enumerate(self._workspaces):
                self._solve_factor(group, workspace.rhs, workspace.y, method)
        else:
            self._forward(method)
            for group in (1, 0):
                workspace = self._workspaces[group]
                self._upper[group].mult(
                    self._workspaces[group + 1].y,
                    workspace.temp,
                )
                self._solve_factor(
                    group,
                    workspace.temp,
                    workspace.correction,
                    method,
                )
                workspace.y.axpy(PETSc.ScalarType(-1.0), workspace.correction)
        self._scatter_solution(target)
        self._apply_count[method] += 1

    def solve(self, method: str, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply_checkpoint(method, source, target)

    def destroy(self) -> None:
        if self._destroyed:
            return
        for workspace in reversed(self._workspaces):
            workspace.destroy()
        self._workspaces.clear()
        for block in reversed(self._lower):
            block.destroy()
        self._lower.clear()
        for block in reversed(self._upper):
            block.destroy()
        self._upper.clear()
        for factor in reversed(self._factors):
            factor.destroy()
        self._factors.clear()
        for group_is_item in self._group_is:
            group_is_item.destroy()
        self._group_is = ()
        self._parent_template.destroy()
        self._parent_template = None
        self._destroyed = True
        if self._lifecycle_callback is not None:
            self._lifecycle_callback("supernode_action_destroyed", self.diagnostics)


def build_fixed_two_layer_supernode_action(
    matrix: PETSc.Mat,
    global_layer_labels: np.ndarray,
    *,
    layer_count: int = 6,
    lifecycle_callback: Any = None,
) -> FixedTwoLayerSupernodeAction:
    """Build the fixed distributed V9-2 three-factor supernode action."""

    return FixedTwoLayerSupernodeAction.from_matrix(
        matrix,
        global_layer_labels,
        layer_count=layer_count,
        lifecycle_callback=lifecycle_callback,
    )


class LayerSweepAction:
    """Fixed layer-triangular sweep with sequential factor-only ownership."""

    _METHODS = ("J1", "F1", "FB1", "FB2", "FB4")

    def __init__(
        self,
        *,
        method: str,
        factors: list[ResearchExactFactorInverse],
        lower: dict[int, PETSc.Mat],
        upper: dict[int, PETSc.Mat],
        workspaces: list[_LayerWorkspace],
        parent_template: PETSc.Vec,
        factor_records: list[dict[str, Any]],
        fine_action: Any,
        lifecycle_callback: Any,
    ) -> None:
        self._method = method
        self._factors = factors
        self._lower = lower
        self._upper = upper
        self._workspaces = workspaces
        self._parent_template = parent_template
        self._factor_records = factor_records
        self._current = parent_template.duplicate()
        self._residual = parent_template.duplicate()
        self._correction = parent_template.duplicate()
        self._fine_action = fine_action
        self._lifecycle_callback = lifecycle_callback
        self._destroyed = False
        self._apply_count = 0
        self._fb_sweep_count = 0
        self._fine_action_count = 0
        self._layer_solve_count = [0 for _ in factors]
        self._diagnostics = {
            "method": method,
            "layer_count": len(factors),
            "layer_factor_count": len(factors),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "fine_action_callback": fine_action is not None,
            "fine_action_is_explicit_matrix": isinstance(fine_action, PETSc.Mat),
            "factor_only_storage": True,
            "retained_explicit_diagonal_count": 0,
            "retained_lower_block_count": len(lower),
            "retained_upper_block_count": len(upper),
            "layer_factor_lifecycle": [
                {
                    "layer": layer,
                    "construction_marker": "completed",
                    "destroy_marker": "pending",
                }
                for layer in range(len(factors))
            ],
            "layer_factors": factor_records,
            "apply_count": 0,
            "fb_sweep_count": 0,
            "fine_action_count": 0,
            "layer_solve_count": [0 for _ in factors],
            "destroy_marker": "pending",
        }

    @classmethod
    def from_matrix(
        cls,
        matrix: PETSc.Mat,
        global_layer_labels: np.ndarray,
        *,
        layer_count: int,
        method: str,
        fine_action: Any = None,
        lifecycle_callback: Any = None,
    ) -> "LayerSweepAction":
        """Build one fixed sweep and release each explicit diagonal block."""

        if method not in cls._METHODS:
            raise ValueError(f"Unsupported fixed layer sweep method: {method}")
        if method in ("FB2", "FB4") and fine_action is None:
            raise ValueError(f"{method} requires a fine action callback")
        rows, cols = map(int, matrix.getSize())
        if rows != cols:
            raise ValueError("Layer sweep requires a square matrix")
        labels = np.asarray(global_layer_labels, dtype=np.int32)
        if (
            labels.shape != (rows,)
            or np.any(labels < 0)
            or np.any(labels >= layer_count)
        ):
            raise ValueError("Layer sweep labels do not match the matrix")
        comm = matrix.getComm()
        row_start, row_end = map(int, matrix.getOwnershipRange())
        local_labels = labels[row_start:row_end]
        row_ids = tuple(
            np.flatnonzero(local_labels == layer).astype(PETSc.IntType) + row_start
            for layer in range(layer_count)
        )
        layer_is = tuple(PETSc.IS().createGeneral(ids, comm=comm) for ids in row_ids)
        parent_template = matrix.createVecRight()
        factors: list[ResearchExactFactorInverse] = []
        factor_records: list[dict[str, Any]] = []
        lower: dict[int, PETSc.Mat] = {}
        upper: dict[int, PETSc.Mat] = {}
        workspaces: list[_LayerWorkspace] = []

        def cleanup_partial() -> None:
            for workspace in reversed(workspaces):
                workspace.destroy()
            workspaces.clear()
            for block in reversed(tuple(lower.values())):
                block.destroy()
            lower.clear()
            for block in reversed(tuple(upper.values())):
                block.destroy()
            upper.clear()
            for factor in reversed(factors):
                factor.destroy()
            factors.clear()
            for layer_is_item in layer_is:
                layer_is_item.destroy()
            parent_template.destroy()

        try:
            for layer in range(layer_count - 1):
                upper[layer] = matrix.createSubMatrix(
                    layer_is[layer], layer_is[layer + 1]
                )
                lower[layer + 1] = matrix.createSubMatrix(
                    layer_is[layer + 1], layer_is[layer]
                )
            for layer in range(layer_count):
                diagonal = matrix.createSubMatrix(layer_is[layer], layer_is[layer])
                factor = None
                try:
                    if lifecycle_callback is not None:
                        lifecycle_callback("layer_factor_setup_begin", {"layer": layer})
                    factor = ResearchExactFactorInverse(
                        diagonal,
                        factor_solver_type="mumps",
                        factor_only_storage=True,
                    )
                    factor.release_borrowed_matrix()
                    factors.append(factor)
                    factor_diagnostics = factor.diagnostics
                    local_rows, _ = map(int, diagonal.getLocalSize())
                    nnz_local = int(diagonal.getInfo()["nz_used"])
                    nnz_global = int(
                        matrix.getComm().tompi4py().allreduce(nnz_local, op=MPI.SUM)
                    )
                    factor_records.append(
                        {
                            "layer": layer,
                            "rows_owned_local": local_rows,
                            "rows_global": int(diagonal.getSize()[0]),
                            "nnz_local": nnz_local,
                            "nnz_global": nnz_global,
                            "factor_matrix_stats": factor_diagnostics[
                                "factor_matrix_stats"
                            ],
                            "factor_only_storage": bool(
                                factor_diagnostics["factor_only_storage"]
                            ),
                            "borrowed_matrix_released": bool(
                                factor_diagnostics["borrowed_matrix_released"]
                            ),
                            "factor_matrix_alive": bool(
                                factor_diagnostics["factor_matrix_alive"]
                            ),
                        }
                    )
                    if lifecycle_callback is not None:
                        lifecycle_callback(
                            "layer_factor_ready",
                            {"layer": layer, "factor_only_storage": True},
                        )
                except Exception:
                    if factor is not None:
                        factor.destroy()
                    raise
                finally:
                    diagonal.destroy()
            for layer, factor in enumerate(factors):
                factor_matrix = factor.operator
                if factor_matrix is None:
                    raise RuntimeError(f"Layer {layer} factor has no retained matrix")
                x = factor_matrix.createVecRight()
                y = factor_matrix.createVecLeft()
                temp = y.duplicate()
                first, last = map(int, x.getOwnershipRange())
                positions = PETSc.IS().createStride(
                    last - first, first=first, step=1, comm=comm
                )
                try:
                    scatter = PETSc.Scatter().create(
                        parent_template,
                        layer_is[layer],
                        x,
                        positions,
                    )
                except Exception:
                    temp.destroy()
                    y.destroy()
                    x.destroy()
                    raise
                finally:
                    positions.destroy()
                workspaces.append(
                    _LayerWorkspace(layer=layer, x=x, y=y, temp=temp, scatter=scatter)
                )
            action = cls(
                method=method,
                factors=factors,
                lower=lower,
                upper=upper,
                workspaces=workspaces,
                parent_template=parent_template,
                factor_records=factor_records,
                fine_action=fine_action,
                lifecycle_callback=lifecycle_callback,
            )
            for layer_is_item in layer_is:
                layer_is_item.destroy()
            layer_is = ()
            return action
        except Exception:
            cleanup_partial()
            raise

    @property
    def diagnostics(self) -> dict[str, Any]:
        diagnostics = dict(self._diagnostics)
        diagnostics["layer_factor_count"] = 0 if self._destroyed else len(self._factors)
        diagnostics["apply_count"] = self._apply_count
        diagnostics["fb_sweep_count"] = self._fb_sweep_count
        diagnostics["fine_action_count"] = self._fine_action_count
        diagnostics["layer_solve_count"] = list(self._layer_solve_count)
        diagnostics["layer_factors"] = [
            {**record, "solve_count": self._layer_solve_count[record["layer"]]}
            for record in self._factor_records
        ]
        diagnostics["destroyed"] = self._destroyed
        return diagnostics

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    @property
    def factor_only_storage(self) -> bool:
        """The action retains layer factors, not explicit diagonal matrices."""

        return True

    def _gather(self, source: PETSc.Vec) -> None:
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.x,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )

    def _forward(self) -> None:
        for layer, workspace in enumerate(self._workspaces):
            if layer:
                self._lower[layer].mult(self._workspaces[layer - 1].y, workspace.temp)
                workspace.x.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve_layer(layer, workspace.x, workspace.y)

    def _backward(self) -> None:
        for layer in range(len(self._workspaces) - 1, -1, -1):
            workspace = self._workspaces[layer]
            if layer < len(self._workspaces) - 1:
                self._upper[layer].mult(self._workspaces[layer + 1].y, workspace.temp)
                workspace.x.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve_layer(layer, workspace.x, workspace.y)

    def _solve_layer(self, layer: int, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._factors[layer].solve(source, target)
        self._layer_solve_count[layer] += 1

    def _scatter_solution(self, target: PETSc.Vec) -> None:
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def _apply_fb1(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._gather(source)
        self._forward()
        self._backward()
        self._scatter_solution(target)
        self._fb_sweep_count += 1

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply_checkpoint(self._method, source, target)

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Expose the fixed action through the base-inverse solve protocol."""

        self.apply(source, target)

    def apply_checkpoint(
        self, method: str, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._destroyed:
            raise RuntimeError("layer sweep action has been destroyed")
        if method not in self._METHODS:
            raise ValueError(f"Unsupported fixed layer sweep method: {method}")
        if method in ("FB2", "FB4") and self._fine_action is None:
            raise ValueError(f"{method} requires a fine action callback")
        expected_size = self._parent_template.getSize()
        if source.getSize() != expected_size or target.getSize() != expected_size:
            raise ValueError("layer sweep vector does not match matrix layout")
        self._apply_count += 1
        if method == "J1":
            self._gather(source)
            for layer, workspace in enumerate(self._workspaces):
                self._solve_layer(layer, workspace.x, workspace.y)
            self._scatter_solution(target)
            return
        if method == "F1":
            self._gather(source)
            self._forward()
            self._scatter_solution(target)
            return
        if method == "FB1":
            self._apply_fb1(source, target)
            return

        target.set(0.0)
        self._current.set(0.0)
        applications = 2 if method == "FB2" else 4
        for iteration in range(applications):
            if iteration == 0:
                source.copy(self._residual)
            else:
                self._fine_action(self._current, self._residual)
                self._fine_action_count += 1
                self._residual.scale(PETSc.ScalarType(-1.0))
                self._residual.axpy(PETSc.ScalarType(1.0), source)
            self._apply_fb1(self._residual, self._correction)
            self._current.axpy(PETSc.ScalarType(1.0), self._correction)
        self._current.copy(target)

    def destroy(self) -> None:
        if self._destroyed:
            return
        for vector in (self._correction, self._residual, self._current):
            vector.destroy()
        self._correction = None
        self._residual = None
        self._current = None
        for workspace in reversed(self._workspaces):
            workspace.destroy()
        self._workspaces.clear()
        for block in reversed(tuple(self._lower.values())):
            block.destroy()
        self._lower.clear()
        for block in reversed(tuple(self._upper.values())):
            block.destroy()
        self._upper.clear()
        for layer, factor in reversed(tuple(enumerate(self._factors))):
            factor.destroy()
            self._diagnostics["layer_factor_lifecycle"][layer]["destroy_marker"] = (
                "completed"
            )
        self._factors.clear()
        self._parent_template.destroy()
        self._parent_template = None
        self._diagnostics["layer_factor_count"] = 0
        self._diagnostics["destroy_marker"] = "completed"
        self._destroyed = True
        if self._lifecycle_callback is not None:
            self._lifecycle_callback("layer_sweep_destroyed", self.diagnostics)


def build_layer_sweep_action(
    matrix: PETSc.Mat,
    global_layer_labels: np.ndarray,
    *,
    layer_count: int,
    method: str,
    fine_action: Any = None,
    lifecycle_callback: Any = None,
) -> LayerSweepAction:
    """Build a fixed J1/F1/FB1/FB2/FB4 factor-only layer action."""

    return LayerSweepAction.from_matrix(
        matrix,
        global_layer_labels,
        layer_count=layer_count,
        method=method,
        fine_action=fine_action,
        lifecycle_callback=lifecycle_callback,
    )


def _relative_vec_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    expected.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), actual)
    error = float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    difference.destroy()
    return error


def _fill_audit_source(vector: PETSc.Vec, index: int) -> tuple[str, str]:
    first, last = map(int, vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    values = np.sin(0.013 * rows + 0.17 * index) + 1j * np.cos(
        0.009 * rows - 0.23 * index
    )
    vector.getArray()[:] = np.asarray(values, dtype=PETSc.ScalarType)
    vector.assemble()
    local_hash = hashlib.sha256(
        np.ascontiguousarray(vector.getArray(readonly=True)).view(np.uint8)
    ).hexdigest()
    comm = vector.getComm().tompi4py()
    partition_digest = hashlib.sha256(
        json.dumps(
            comm.allgather(
                {
                    "ownership_range": [first, last],
                    "local_hash": local_hash,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    generator_digest = hashlib.sha256(
        f"global_row_sin_cos_v1:{index}:{vector.getSize()}:"
        f"{np.dtype(PETSc.ScalarType).str}".encode("ascii")
    ).hexdigest()
    return partition_digest, generator_digest


def audit_layer_block_action(
    matrix: PETSc.Mat, operator: LayerBlockOperator, *, vector_count: int = 8
) -> dict[str, Any]:
    """Compare a block action with ``matrix`` on fixed value-hashed vectors.

    The vectors are generated from global row numbers, so their values do not
    depend on the MPI partition.  Only local PETSc arrays are materialized.
    This is an audit helper, not a solver or a source of physical fields.
    """

    if vector_count != 8:
        raise ValueError("V8 layer action audit requires exactly eight vectors")
    retained_sources: list[PETSc.Vec] = []
    retained_actual: list[PETSc.Vec] = []
    reports: list[dict[str, Any]] = []
    try:
        for index in range(vector_count):
            source = matrix.createVecRight()
            f_result = matrix.createVecLeft()
            block_result = matrix.createVecLeft()
            try:
                source_hash, generator_hash = _fill_audit_source(source, index)
                matrix.mult(source, f_result)
                operator.apply(source, block_result)
                f_norm = float(f_result.norm())
                block_norm = float(block_result.norm())
                relative_error = _relative_vec_error(block_result, f_result)
                reports.append(
                    {
                        "index": index,
                        "source_value_hash": source_hash,
                        "generator_contract_sha256": generator_hash,
                        "hash_scheme": "rank_local_sha256_allgather_v1",
                        "rank_partition_bound": True,
                        "f_norm": f_norm,
                        "block_norm": block_norm,
                        "relative_error": relative_error,
                        "finite": bool(
                            np.isfinite(relative_error)
                            and np.isfinite(f_norm)
                            and np.isfinite(block_norm)
                        ),
                    }
                )
                if index < 2:
                    retained_sources.append(source)
                    retained_actual.append(block_result)
                    source = None
                    block_result = None
            finally:
                f_result.destroy()
                if source is not None:
                    source.destroy()
                if block_result is not None:
                    block_result.destroy()
        repeat = retained_actual[0].duplicate()
        operator.apply(retained_sources[0], repeat)
        repeat_error = _relative_vec_error(repeat, retained_actual[0])
        linear_expected = retained_actual[0].duplicate()
        retained_actual[0].copy(linear_expected)
        linear_expected.scale(PETSc.ScalarType(1.1 - 0.4j))
        linear_expected.axpy(PETSc.ScalarType(-0.7 + 0.2j), retained_actual[1])
        combination = retained_sources[0].duplicate()
        retained_sources[0].copy(combination)
        combination.scale(PETSc.ScalarType(1.1 - 0.4j))
        combination.axpy(PETSc.ScalarType(-0.7 + 0.2j), retained_sources[1])
        combination_actual = matrix.createVecLeft()
        operator.apply(combination, combination_actual)
        linearity_error = _relative_vec_error(combination_actual, linear_expected)
        repeat.destroy()
        linear_expected.destroy()
        combination.destroy()
        combination_actual.destroy()
        return {
            "vector_count": vector_count,
            "vectors": reports,
            "max_relative_error": max(
                float(report["relative_error"]) for report in reports
            ),
            "repeat_relative_error": repeat_error,
            "linearity_relative_error": linearity_error,
            "relative_error_limit": 1.0e-12,
            "repeat_limit": 1.0e-13,
            "linearity_limit": 1.0e-13,
            "value_hash_bound": True,
            "source_generator": "global_row_sin_cos_v1",
            "source_hash_rank_partition_bound": True,
        }
    finally:
        for vector in (*retained_actual, *retained_sources):
            vector.destroy()


def build_layer_block_operator(
    matrix: PETSc.Mat,
    global_layer_labels: np.ndarray,
    *,
    layer_count: int,
    mapping_metadata: dict[str, Any] | None = None,
) -> LayerBlockOperator:
    """Construct the V8 layer block action without taking ownership of ``matrix``."""

    return LayerBlockOperator(
        matrix,
        global_layer_labels,
        layer_count=layer_count,
        mapping_metadata=mapping_metadata,
    )
