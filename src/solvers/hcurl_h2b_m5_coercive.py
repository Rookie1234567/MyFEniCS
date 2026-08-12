"""Research-only M5 full-space right-FGMRES screen adapters.

The fixed M5 screen keeps the B0 form action matrix-free and uses the already
qualified M4Y packed-patch PC on the right of flexible GMRES.  This module
contains only the PETSc adapters, the fixed screen, and the three explicit
true-residual checkpoints.  It does not build a global matrix, a coarse
space, or a PDE/post-processing path.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from petsc4py import PETSc

__all__ = (
    "M5_CHECKPOINT_ITERATIONS",
    "M5_FIXED_MAX_IT",
    "M5_FIXED_RESTART",
    "M5_ONLINE_RSS_LIMIT_BYTES",
    "M5B0MatPythonContext",
    "M5M4YPCContext",
    "M5ResidualCheckpointWriter",
    "build_m5_b0_mat",
    "evaluate_m5_screen_gate",
    "run_m5_right_fgmres_screen",
)


M5_FIXED_RESTART = 20
M5_FIXED_MAX_IT = 100
M5_CHECKPOINT_ITERATIONS = (20, 50, 100)
M5_ONLINE_RSS_LIMIT_BYTES = 1_550_000_000
M5_TRUE_RESIDUAL_ITER20_LIMIT = 0.40
M5_TRUE_RESIDUAL_ITER100_LIMIT = 1.0e-3
M5_SCHEMA = "task037.extra.h2b.m5.coercive.v1"


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _finite_owned_array(vector: PETSc.Vec, name: str) -> np.ndarray:
    values = np.asarray(vector.getArray(readonly=True))
    if (
        values.dtype != np.dtype(np.complex128)
        or values.ndim != 1
        or not np.all(np.isfinite(values))
    ):
        raise ValueError(f"M5 {name} must be finite complex128 owned values")
    return values


def _copy_owned_array(vector: PETSc.Vec, name: str) -> np.ndarray:
    return np.array(_finite_owned_array(vector, name), dtype=np.complex128, copy=True)


class M5B0MatPythonContext:
    """Adapt ``HcurlRankOneMpcAction.mult`` to PETSc MatPython ``mult``."""

    def __init__(self, action: Any, *, owned_rows: int, global_rows: int) -> None:
        if not callable(getattr(action, "mult", None)):
            raise TypeError("M5 B0 MatPython context requires an action.mult method")
        if type(owned_rows) is not int or type(global_rows) is not int:
            raise TypeError("M5 B0 row counts must be int")
        if owned_rows <= 0 or global_rows < owned_rows:
            raise ValueError("M5 B0 row counts are invalid")
        self._action = action
        self._owned_rows = owned_rows
        self._global_rows = global_rows
        self._apply_count = 0

    def mult(
        self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if source.getLocalSize() != self._owned_rows or source.getSize() != self._global_rows:
            raise ValueError("M5 B0 source ownership differs from action")
        if target.getLocalSize() != self._owned_rows or target.getSize() != self._global_rows:
            raise ValueError("M5 B0 target ownership differs from action")
        result = self._action.mult(source)
        result_values = _finite_owned_array(result, "B0 result")
        if result_values.size != self._owned_rows:
            raise ValueError("M5 B0 action returned an incompatible owned result")
        np.copyto(target.getArray(), result_values)
        target.assemble()
        self._apply_count += 1

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": M5_SCHEMA,
            "owned_rows": self._owned_rows,
            "global_rows": self._global_rows,
            "mat_python": True,
            "global_matrix_materialized": False,
            "borrowed_action_output_copied": True,
            "apply_count": self._apply_count,
        }


def build_m5_b0_mat(
    action: Any,
    *,
    owned_rows: int,
    global_rows: int,
    comm: Any,
) -> tuple[PETSc.Mat, M5B0MatPythonContext]:
    context = M5B0MatPythonContext(
        action, owned_rows=owned_rows, global_rows=global_rows
    )
    matrix = PETSc.Mat().createPython(
        ((owned_rows, global_rows), (owned_rows, global_rows)),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    return matrix, context


class M5M4YPCContext:
    """Adapt the NumPy M4Y PC to a right-side PETSc Python PC."""

    def __init__(self, pc: Any, *, global_rows: int) -> None:
        if not callable(getattr(pc, "apply", None)):
            raise TypeError("M5 PC context requires an M4Y apply method")
        if type(global_rows) is not int or global_rows <= 0:
            raise ValueError("M5 PC global row count is invalid")
        self._pc = pc
        self._global_rows = global_rows
        self._apply_count = 0

    def apply(
        self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if source.getSize() != self._global_rows or target.getSize() != self._global_rows:
            raise ValueError("M5 PC vector size differs from full-space scope")
        if source.getComm().getSize() != 1:
            raise ValueError("M5 first screen PC adapter is fixed to MPI1")
        source_values = _copy_owned_array(source, "PC source")
        correction = np.asarray(self._pc.apply(source_values), dtype=np.complex128)
        if (
            correction.ndim != 1
            or correction.shape != source_values.shape
            or not np.all(np.isfinite(correction))
        ):
            raise ValueError("M5 M4Y PC returned invalid correction")
        np.copyto(target.getArray(), correction)
        target.assemble()
        self._apply_count += 1

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": M5_SCHEMA,
            "global_rows": self._global_rows,
            "pc_python": True,
            "pc_side": "right",
            "mpi_size": 1,
            "owned_values_copied": True,
            "apply_count": self._apply_count,
        }


class M5ResidualCheckpointWriter:
    """Write one owner-local checkpoint at a time and return SHA-bound metadata."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, path: Path, values: np.ndarray) -> dict[str, Any]:
        array = np.asarray(values, dtype=np.complex128)
        if array.ndim != 1 or not np.all(np.isfinite(array)):
            raise ValueError("M5 checkpoint arrays must be finite vectors")
        np.save(path, np.ascontiguousarray(array), allow_pickle=False)
        return {
            "path": path.name,
            "bytes": int(path.stat().st_size),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "array_sha256": _array_sha256(array),
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }

    def write_checkpoint(
        self,
        iteration: int,
        *,
        solution: PETSc.Vec,
        b0_action: PETSc.Vec,
        residual: PETSc.Vec,
        rhs: PETSc.Vec,
    ) -> dict[str, Any]:
        if iteration not in M5_CHECKPOINT_ITERATIONS:
            raise ValueError("M5 checkpoint iteration is not fixed")
        arrays = {
            "solution": _copy_owned_array(solution, "solution checkpoint"),
            "b0_action": _copy_owned_array(b0_action, "B0 checkpoint"),
            "residual": _copy_owned_array(residual, "residual checkpoint"),
            "rhs": _copy_owned_array(rhs, "RHS checkpoint"),
        }
        artifacts = {
            name: self._write(
                self._run_dir / f"m5_iter{iteration}_{name}.npy", values
            )
            for name, values in arrays.items()
        }
        relative = float(np.linalg.norm(arrays["residual"]) / max(
            np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny
        ))
        return {
            "iteration": int(iteration),
            "true_relative_residual": relative,
            "artifacts": artifacts,
        }


def _explicit_relative_residual(rhs: np.ndarray, b0_action: np.ndarray) -> float:
    residual = np.asarray(rhs, dtype=np.complex128) - np.asarray(
        b0_action, dtype=np.complex128
    )
    return float(
        np.linalg.norm(residual)
        / max(np.linalg.norm(rhs), np.finfo(float).tiny)
    )


def evaluate_m5_screen_gate(
    samples: Mapping[str, Any],
    *,
    online_peak_rss_bytes: int,
    online_swap_bytes: int,
    processes_gone: bool,
) -> dict[str, Any]:
    """Evaluate only the fixed first-screen gates; missing data fails closed."""

    problems: list[str] = []
    required = {str(iteration) for iteration in M5_CHECKPOINT_ITERATIONS}
    if not isinstance(samples, Mapping) or set(samples) != required:
        problems.append("checkpoint_set")
    values: dict[str, float] = {}
    if not problems:
        for key in sorted(required, key=int):
            item = samples[key]
            if not isinstance(item, Mapping) or "true_relative_residual" not in item:
                problems.append(f"checkpoint_{key}")
                continue
            value = item["true_relative_residual"]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not np.isfinite(value):
                problems.append(f"checkpoint_{key}")
            else:
                values[key] = float(value)
    if not problems:
        if values["20"] > M5_TRUE_RESIDUAL_ITER20_LIMIT:
            problems.append("true_residual_iter20")
        if values["100"] > M5_TRUE_RESIDUAL_ITER100_LIMIT:
            problems.append("true_residual_iter100")
        if not values["100"] < values["50"]:
            problems.append("true_residual_decline_50_to_100")
    resource_ok = (
        type(online_peak_rss_bytes) is int
        and online_peak_rss_bytes < M5_ONLINE_RSS_LIMIT_BYTES
        and online_swap_bytes == 0
        and processes_gone is True
    )
    if not resource_ok:
        problems.append("online_resource")
    return {
        "pass": not problems,
        "problems": problems,
        "true_residuals": values,
        "resource_gate": resource_ok,
        "limits": {
            "iteration20": M5_TRUE_RESIDUAL_ITER20_LIMIT,
            "iteration100": M5_TRUE_RESIDUAL_ITER100_LIMIT,
            "online_peak_rss_bytes": M5_ONLINE_RSS_LIMIT_BYTES,
        },
    }


def run_m5_right_fgmres_screen(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    *,
    pc_context: M5M4YPCContext,
    checkpoint_dir: Path,
    operator_context: M5B0MatPythonContext | None = None,
) -> dict[str, Any]:
    """Run the fixed MPI1 right-FGMRES screen and write three true checkpoints."""

    if rhs.getComm().getSize() != 1:
        raise ValueError("M5 first screen is fixed to MPI1")
    rows = int(rhs.getSize())
    if operator.getSize() != (rows, rows):
        raise ValueError("M5 operator and RHS sizes differ")
    writer = M5ResidualCheckpointWriter(checkpoint_dir)
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    action_work = operator.createVecLeft()
    residual_work = rhs.duplicate()
    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
        raise ValueError("M5 RHS norm must be positive and finite")
    samples: dict[str, Any] = {}
    ksp = PETSc.KSP().create(rhs.getComm())
    try:
        solution.set(0.0)
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(M5_FIXED_RESTART)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=M5_FIXED_MAX_IT)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setUp()
        actual_rtol, actual_atol, _actual_dtol, actual_max_it = ksp.getTolerances()
        actual_restart = M5_FIXED_RESTART

        def sample(current: PETSc.KSP, iteration: int) -> None:
            key = str(iteration)
            if iteration not in M5_CHECKPOINT_ITERATIONS or key in samples:
                return
            current.buildSolution(monitor_solution)
            operator.mult(monitor_solution, action_work)
            residual_work.waxpy(PETSc.ScalarType(-1.0), action_work, rhs)
            checkpoint = writer.write_checkpoint(
                iteration,
                solution=monitor_solution,
                b0_action=action_work,
                residual=residual_work,
                rhs=rhs,
            )
            checkpoint["reported_relative_residual"] = float(
                current.getResidualNorm() / max(rhs_norm, np.finfo(float).tiny)
            )
            samples[key] = checkpoint

        def monitor(current: PETSc.KSP, iteration: int, _reported: float) -> None:
            sample(current, int(iteration))

        ksp.setMonitor(monitor)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        final_reason = int(ksp.getConvergedReason())
        if iterations < M5_FIXED_MAX_IT and "100" not in samples:
            operator.mult(solution, action_work)
            residual_work.waxpy(PETSc.ScalarType(-1.0), action_work, rhs)
            final = {
                "true_relative_residual": _explicit_relative_residual(
                    _copy_owned_array(rhs, "RHS"),
                    _copy_owned_array(action_work, "final B0 action"),
                ),
                "reported_relative_residual": float(
                    ksp.getResidualNorm() / max(rhs_norm, np.finfo(float).tiny)
                ),
            }
        else:
            final = None
        return {
            "schema": M5_SCHEMA,
            "rows": rows,
            "ksp_type": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": M5_FIXED_RESTART,
            "max_it": M5_FIXED_MAX_IT,
            "iterations": iterations,
            "converged_reason": final_reason,
            "rhs_norm": rhs_norm,
            "samples": samples,
            "final": final,
            "operator_apply_count": None if operator_context is None else operator_context.apply_count,
            "pc_apply_count": pc_context.apply_count,
            "sample_action_count": len(samples) + (1 if final is not None else 0),
            "fixed_screen": True,
            "rtol": float(actual_rtol),
            "atol": float(actual_atol),
            "restart_set": int(actual_restart),
            "max_it_actual": int(actual_max_it),
        }
    finally:
        ksp.destroy()
        solution.destroy()
        monitor_solution.destroy()
        action_work.destroy()
        residual_work.destroy()
