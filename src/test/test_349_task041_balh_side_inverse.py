"""Focused small-PETSc checks for the H1e side BAL_H adapter."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from itertools import pairwise
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor

from src.solvers import physical_balanced_side_inverse as side_inverse_module
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    CellRecoveryMap,
    TraceConstraintMap,
)
from src.solvers.hybrid_local_dtn_action import HybridLocalDtnActionSystem
from src.solvers.p4_cell_condensed_inverse import P4CellCondensedInverse
from src.solvers.physical_balanced_h6 import FixedH6
from src.solvers.physical_balanced_physical_operator import (
    P4CondensedExactFactor,
    P4ExactFactor,
    P4PhysicalResidualGateError,
)
from src.solvers.physical_balanced_same_mesh_transfer import (
    SUPPORT_POLICY_ENTITY_CLOSURE,
    SUPPORT_POLICY_LEGACY,
)
from src.solvers.physical_balanced_side_inverse import SideBalancedInverse

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1e focused side-inverse tests are serial/MPI2 only",
)

# Native PETSc names the task's DIVERGED_ITS budget result DIVERGED_MAX_IT.
_DIVERGED_ITS = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)

_G2A_MATRIX_DIAGNOSTICS_ENV = "TASK041_G2A_MATRIX_DIAGNOSTICS"
_G2A_MATRIX_SEQUENCE = 0


class _ScaleContext:
    def __init__(self, scale: complex) -> None:
        self.scale = PETSc.ScalarType(scale)
        self.apply_count = 0
        self.destroyed = False

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self.destroyed:
            raise RuntimeError("scale matrix context has been destroyed")
        target.set(0.0)
        target.axpy(self.scale, source)
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True


def _local_rows_for_test_matrix(
    size: int,
    local_row_counts: tuple[int, ...] | None,
) -> int:
    comm = MPI.COMM_WORLD
    if local_row_counts is None:
        quotient, remainder = divmod(size, comm.size)
        return quotient + int(comm.rank < remainder)
    counts = tuple(int(value) for value in local_row_counts)
    if (
        len(counts) != comm.size
        or any(value < 0 for value in counts)
        or sum(counts) != size
    ):
        raise ValueError("test matrix local row counts must partition its rows")
    return counts[comm.rank]


def _scale_matrix(
    size: int,
    scale: complex,
    *,
    local_row_counts: tuple[int, ...] | None = None,
) -> tuple[PETSc.Mat, _ScaleContext]:
    comm = MPI.COMM_WORLD
    local_rows = _local_rows_for_test_matrix(size, local_row_counts)
    context = _ScaleContext(scale)
    matrix = PETSc.Mat().createPython(
        ((local_rows, size), (local_rows, size)),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    return matrix, context


class _IdentityCondensed:
    def __init__(
        self,
        size: int,
        *,
        local_row_counts: tuple[int, ...] | None = None,
    ) -> None:
        comm = MPI.COMM_WORLD
        self.comm = comm
        self.active_rows = size
        self.full_rows = size
        if local_row_counts is None:
            quotient, remainder = divmod(size, comm.size)
            counts = tuple(
                quotient + int(rank < remainder) for rank in range(comm.size)
            )
        else:
            counts = tuple(int(value) for value in local_row_counts)
        if (
            len(counts) != comm.size
            or any(value < 0 for value in counts)
            or sum(counts) != size
        ):
            raise ValueError("test condensed ownership must partition active rows")
        self.owned_active_rows = counts[comm.rank]
        first = sum(counts[: comm.rank])
        self.trace_constraints = SimpleNamespace(
            owned_active_original_dofs=np.arange(
                first,
                first + self.owned_active_rows,
                dtype=PETSc.IntType,
            )
        )

    def create_active_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (self.owned_active_rows, self.active_rows),
            comm=self.comm,
        )


class _IdentityTransfer:
    def __init__(self, default_variant: str = "legacy") -> None:
        self.apply_count = 0
        self.primal_apply_count = 0
        self.destroy_count = 0
        self._execution_variant = default_variant
        self._variant_context_active = False
        self.on_apply = None
        self._audit = {"pair_fine_to_coarse": [6, 4], "owner_local": True}

    @property
    def execution_variant(self) -> str:
        return self._execution_variant

    @contextmanager
    def variant_context(self, variant: str):
        if variant not in {"legacy", "optimized"}:
            raise ValueError("test transfer variant must be legacy or optimized")
        if self._variant_context_active:
            raise RuntimeError("test transfer variant cannot change while active")
        previous = self._execution_variant
        self._execution_variant = variant
        self._variant_context_active = True
        try:
            yield self
        finally:
            self._execution_variant = previous
            self._variant_context_active = False

    def _before_apply(self) -> None:
        if self.on_apply is not None:
            self.on_apply()

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def apply_adjoint(
        self,
        source: PETSc.Vec,
        *,
        timing: dict[str, float] | None = None,
    ) -> PETSc.Vec:
        self.apply_count += 1
        self._before_apply()
        if timing is not None:
            timing.update(
                {
                    "cell_adjoint_seconds": 1.0e-4,
                    "dual_reduce_seconds": 2.0e-4,
                    "mpi_exchange_seconds": 4.0e-4,
                    "ghost_mpc_prepare_seconds": 5.0e-4,
                    "ghost_mpc_check_seconds": 6.0e-4,
                }
            )
        return self._copy(source)

    def apply_primal(
        self,
        source: PETSc.Vec,
        *,
        timing: dict[str, float] | None = None,
    ) -> PETSc.Vec:
        self.apply_count += 1
        self.primal_apply_count += 1
        self._before_apply()
        if timing is not None:
            timing.update(
                {
                    "local_candidate_generation_seconds": 1.0e-4,
                    "route_sort_index_seconds": 2.0e-4,
                    "mpi_exchange_seconds": 3.0e-4,
                    "duplicate_row_check_seconds": 4.0e-4,
                    "ghost_mpc_prepare_seconds": 5.0e-4,
                    "ghost_mpc_check_seconds": 6.0e-4,
                }
            )
        return self._copy(source)

    @property
    def audit(self) -> dict[str, object]:
        return dict(self._audit)

    def destroy(self) -> None:
        self.destroy_count += 1


class _IdentityP4:
    def __init__(self, size: int) -> None:
        self.physical_action = SimpleNamespace(V=object(), floquet_data=object())
        self.solve_count = 0
        self.destroy_count = 0
        self.size = size
        self.last_solve: dict[str, object] = {"backsolve_count": 0}
        self.last_diagnostic_kwargs: dict[str, object] = {}

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def create_rhs(self, source: PETSc.Vec) -> PETSc.Vec:
        return self._copy(source)

    def solve_with_refinement(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        *,
        residual_tolerance: float,
        diagnostic_audit: bool = False,
        timing=None,
        **diagnostic_kwargs,
    ) -> dict[str, object]:
        del residual_tolerance, diagnostic_audit
        self.last_diagnostic_kwargs = dict(diagnostic_kwargs)
        correction_steps = int(diagnostic_kwargs.get("diagnostic_correction_steps", 0))
        target_tolerance = diagnostic_kwargs.get("refinement_target_tolerance")
        target_mode = target_tolerance is not None
        correction_callback = diagnostic_kwargs.get("diagnostic_callback")
        rhs.copy(solution)
        self.solve_count += 1 + correction_steps
        recorded_steps = correction_steps + 1 if correction_steps else int(target_mode)
        self.last_solve = {
            "backsolve_count": 1 + correction_steps,
            "refinement_count": correction_steps,
            "rhs_norm": 1.0,
            "physical_rhs_norm": 1.0,
            "diagnostic_correction_history": [
                {
                    "diagnostic_step_index": step,
                    "diagnostic_correction_count": step,
                    "diagnostic_correction_limit": (
                        2 if target_mode else correction_steps
                    ),
                    "backsolve_count": step + 1,
                    "refinement_count": step,
                    "status": "passed",
                    "physical_residual_norm": 0.0,
                    "physical_relative_residual": 0.0,
                    "augmented_residual_norm": 0.0,
                    "augmented_relative_residual": 0.0,
                    "physical_gate_passed": True,
                    "augmented_gate_passed": True,
                    "correction_from_previous_seconds": 0.001 * step,
                    "factor_solve_seconds_for_state": 0.001,
                    **(
                        {
                            "refinement_target_tolerance": float(target_tolerance),
                            "target_reached": True,
                            "stop_reason": "target_reached",
                            "actual_correction_count": 0,
                        }
                        if target_mode
                        else {}
                    ),
                }
                for step in range(recorded_steps)
            ],
            **(
                {
                    "refinement_target_tolerance": float(target_tolerance),
                    "target_reached": True,
                    "stop_reason": "target_reached",
                    "actual_correction_count": 0,
                    "status": "passed",
                    "physical_gate_passed": True,
                    "augmented_gate_passed": True,
                }
                if target_mode
                else {}
            ),
        }
        if correction_steps and correction_callback is not None:
            for step in range(correction_steps + 1):
                record = {
                    "diagnostic_step_index": step,
                    "backsolve_count": step + 1,
                }
                correction_callback(record, {"solution": solution, "fe_residual": rhs})
        if timing is not None:
            timing["factor_solve_seconds"] = 1.0e-3
            timing["A4_residual_refinement_seconds"] = 2.0e-3
            timing["physical_action_matrix_mult_seconds"] = 3.0e-4
        return dict(self.last_solve, relative_residual=0.0)

    def extract_fe_solution(self, solution: PETSc.Vec) -> PETSc.Vec:
        return self._copy(solution)

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "factor_creation_count": 1,
            "factor_destroy_count": int(self.destroy_count > 0),
            "last_solve": dict(self.last_solve),
            "research_factor": {
                "solve_count": self.solve_count,
                "direct_factor_count": int(self.destroy_count == 0),
                "factor_destroyed": bool(self.destroy_count),
            },
        }

    def destroy(self) -> None:
        self.destroy_count += 1


class _CellCondensedP4:
    def __init__(self, size: int) -> None:
        self.physical_action = SimpleNamespace(V=object(), floquet_data=object())
        self.size = size
        self.solve_count = 0
        self.destroy_count = 0
        self.apply_count = 0
        self.last_port_solution = np.empty(0, dtype=np.complex128)
        self.last_timing: dict[str, float | None] = {}
        self.last_physical_rhs_norm: float | None = None
        self.last_solve: dict[str, object] = {"backsolve_count": 0}
        self.last_diagnostic_kwargs: dict[str, object] = {}

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def apply(
        self,
        source: PETSc.Vec,
        *,
        timing: dict[str, float] | None = None,
        **diagnostic_kwargs,
    ) -> PETSc.Vec:
        self.apply_count += 1
        self.last_diagnostic_kwargs = dict(diagnostic_kwargs)
        correction_steps = int(diagnostic_kwargs.get("diagnostic_correction_steps", 0))
        target_tolerance = diagnostic_kwargs.get("refinement_target_tolerance")
        target_mode = target_tolerance is not None
        correction_callback = diagnostic_kwargs.get("diagnostic_callback")
        self.solve_count += 1 + correction_steps
        self.last_physical_rhs_norm = float(source.norm())
        recorded_steps = correction_steps + 1 if correction_steps else int(target_mode)
        self.last_solve = {
            "backsolve_count": 1 + correction_steps,
            "refinement_count": correction_steps,
            "rhs_norm": 1.0,
            "physical_rhs_norm": 1.0,
            "diagnostic_correction_history": [
                {
                    "diagnostic_step_index": step,
                    "diagnostic_correction_count": step,
                    "diagnostic_correction_limit": (
                        2 if target_mode else correction_steps
                    ),
                    "backsolve_count": step + 1,
                    "refinement_count": step,
                    "status": "passed",
                    "physical_residual_norm": 0.0,
                    "physical_relative_residual": 0.0,
                    "residual_norm": 0.0,
                    "relative_residual": 0.0,
                    "physical_gate_passed": True,
                    "augmented_gate_passed": True,
                    "correction_from_previous_seconds": 0.001 * step,
                    "factor_solve_seconds_for_state": 0.001,
                    **(
                        {
                            "refinement_target_tolerance": float(target_tolerance),
                            "target_reached": True,
                            "stop_reason": "target_reached",
                            "actual_correction_count": 0,
                        }
                        if target_mode
                        else {}
                    ),
                }
                for step in range(recorded_steps)
            ],
            **(
                {
                    "refinement_target_tolerance": float(target_tolerance),
                    "target_reached": True,
                    "stop_reason": "target_reached",
                    "actual_correction_count": 0,
                    "status": "passed",
                    "physical_gate_passed": True,
                    "augmented_gate_passed": True,
                }
                if target_mode
                else {}
            ),
        }
        self.last_timing = {
            "storage_rhs_reduction_seconds": 1.0e-4,
            "factor_backsolve_seconds": 2.0e-4,
            "solution_recovery_seconds": 3.0e-4,
            "inner_apply_seconds": 6.0e-4,
        }
        if timing is not None:
            for name, value in self.last_timing.items():
                timing[name] = timing.get(name, 0.0) + float(value)
        result = self._copy(source)
        if correction_callback is not None:
            for step in range(correction_steps + 1):
                record = {
                    "diagnostic_step_index": step,
                    "backsolve_count": step + 1,
                }
                correction_callback(record, {"solution": result, "fe_residual": source})
        return result

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "factor_solve_count": self.solve_count,
            "last_solve": dict(
                self.last_solve,
                physical_rhs_norm=self.last_physical_rhs_norm,
            ),
        }

    def destroy(self) -> None:
        self.destroy_count += 1


class _NonfiniteP4(_IdentityP4):
    def solve_with_refinement(
        self,
        rhs: PETSc.Vec,
        _solution: PETSc.Vec,
        *,
        residual_tolerance: float,
    ) -> dict[str, object]:
        self.solve_count += 1
        rhs_norm = float(rhs.norm())
        raise P4PhysicalResidualGateError(
            {
                "status": "failed_nonfinite_residual",
                "rhs_norm": rhs_norm,
                "residual_norm": float("nan"),
                "relative_residual": float("nan"),
                "residual_tolerance": float(residual_tolerance),
                "backsolve_count": self.solve_count,
                "refinement_count": 0,
            }
        )


class _RefinementFactor:
    def __init__(self) -> None:
        self.solve_count = 0
        self.destroy_count = 0

    def solve(self, _rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        self.solve_count += 1
        if self.solve_count <= 3:
            solution.set(0.0)
            return
        _rhs.copy(solution)
        solution.scale(PETSc.ScalarType(0.5))

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "solve_count": self.solve_count,
            "direct_factor_count": int(self.destroy_count == 0),
            "factor_destroyed": bool(self.destroy_count),
        }

    def destroy(self) -> None:
        self.destroy_count += 1


class _PhysicalP4Action:
    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.full_rows = 2
        self.modes: tuple[object, ...] = ()

    def destroy(self) -> None:
        self.matrix.destroy()


class _DensePythonMatrix:
    def __init__(self, dense: np.ndarray) -> None:
        self.dense = np.asarray(dense, dtype=np.complex128)
        self.apply_count = 0

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        values = _gather_dense_vector(source)
        first, last = (int(value) for value in target.getOwnershipRange())
        target.getArray()[:] = (self.dense @ values)[first:last]
        target.assemble()
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        return None


class _DenseBlockSolve:
    def __init__(
        self,
        block: np.ndarray,
        perturb_port: complex,
        *,
        perturb_fe: complex = 0.0 + 0.0j,
        nonfinite_first_fe: bool = False,
        correction_scales: tuple[float, ...] = (),
    ) -> None:
        self.block = np.asarray(block, dtype=np.complex128)
        self.perturb_port = complex(perturb_port)
        self.perturb_fe = complex(perturb_fe)
        self.nonfinite_first_fe = bool(nonfinite_first_fe)
        self.correction_scales = tuple(float(value) for value in correction_scales)
        self.solve_count = 0
        self.destroy_count = 0
        self.last_result: PETSc.Vec | None = None
        self.last_port_solution = np.zeros(1, dtype=np.complex128)
        self.last_timing: dict[str, float] = {}
        self.condensed = SimpleNamespace(
            active_rows=2,
            interior_rows=0,
            appended_rows=1,
            build_audit={},
        )
        self.factor = self

    def _solve(self, rhs: np.ndarray) -> np.ndarray:
        self.solve_count += 1
        values = np.linalg.solve(self.block, rhs)
        if self.solve_count > 1 and self.correction_scales:
            correction_index = min(
                self.solve_count - 2,
                len(self.correction_scales) - 1,
            )
            values *= self.correction_scales[correction_index]
        if self.solve_count == 1:
            values[-1] += self.perturb_port
            values[0] += self.perturb_fe
            if self.nonfinite_first_fe:
                values[0] = np.nan + 0.0j
        return values

    def solve(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        values = self._solve(_gather_dense_vector(rhs))
        first, last = (int(value) for value in solution.getOwnershipRange())
        solution.getArray()[:] = values[first:last]
        solution.assemble()

    @staticmethod
    def _prepare_port_rhs(port_rhs) -> np.ndarray:
        values = (
            np.zeros(1, dtype=np.complex128)
            if port_rhs is None
            else np.asarray(port_rhs, dtype=np.complex128)
        )
        if values.shape != (1,):
            raise ValueError("dense block fixture expects one port RHS")
        return values.copy()

    def apply(
        self,
        source: PETSc.Vec,
        *,
        port_rhs: np.ndarray | None = None,
    ) -> PETSc.Vec:
        values = self._solve(
            np.concatenate(
                (
                    _gather_dense_vector(source),
                    self._prepare_port_rhs(port_rhs),
                )
            )
        )
        self.last_port_solution = values[-1:].copy()
        result = source.duplicate()
        first, last = (int(value) for value in result.getOwnershipRange())
        result.getArray()[:] = values[first:last]
        result.assemble()
        self.last_result = result
        self.last_timing = {
            "storage_rhs_reduction_seconds": 0.0,
            "factor_backsolve_seconds": 0.0,
            "solution_recovery_seconds": 0.0,
            "inner_apply_seconds": 0.0,
        }
        return result

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "solve_count": self.solve_count,
            "factor_solve_count": self.solve_count,
        }

    def destroy(self) -> None:
        self.destroy_count += 1


def _gather_dense_vector(vector: PETSc.Vec) -> np.ndarray:
    first, _last = (int(value) for value in vector.getOwnershipRange())
    local = np.array(vector.getArray(readonly=True), dtype=np.complex128, copy=True)
    result = np.empty(int(vector.getSize()), dtype=np.complex128)
    for start, values in vector.getComm().tompi4py().allgather((first, local)):
        result[start : start + values.size] = values
    return result


def _g2a_matrix_diagnostic(
    metadata: dict[str, int | str] | None,
    event: str,
    *,
    resource: str = "Mat",
    role: str = "matrix",
) -> None:
    if os.environ.get(_G2A_MATRIX_DIAGNOSTICS_ENV) != "1" or metadata is None:
        return
    node = os.environ.get("PYTEST_CURRENT_TEST", "<unset>")
    print(
        "TASK041_G2A_MATRIX_DIAG "
        f"event={event} rank={MPI.COMM_WORLD.rank} pid={os.getpid()} "
        f"node={node!r} matrix_seq={metadata['sequence']} "
        f"purpose={metadata['purpose']} global_rows={metadata['global_rows']} "
        f"local_rows={metadata['local_rows']} resource={resource} role={role} "
        f"monotonic_ns={time.monotonic_ns()}",
        flush=True,
    )


def _dense_python_matrix(
    values: np.ndarray,
    *,
    base_rows: int,
    appended_rows: int = 0,
    purpose: str,
    local_row_counts: tuple[int, ...] | None = None,
) -> tuple[PETSc.Mat, _DensePythonMatrix]:
    global _G2A_MATRIX_SEQUENCE
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    local_base = _local_rows_for_test_matrix(base_rows, local_row_counts)
    local_rows = local_base + (appended_rows if rank == comm.size - 1 else 0)
    context = _DensePythonMatrix(values)
    matrix_metadata = None
    if os.environ.get(_G2A_MATRIX_DIAGNOSTICS_ENV) == "1":
        _G2A_MATRIX_SEQUENCE += 1
        matrix_metadata = {
            "sequence": _G2A_MATRIX_SEQUENCE,
            "purpose": purpose,
            "global_rows": int(values.shape[0]),
            "local_rows": int(local_rows),
        }
        context._g2a_matrix_metadata = matrix_metadata
        _g2a_matrix_diagnostic(matrix_metadata, "createPython.begin")
    matrix = PETSc.Mat().createPython(
        size=((local_rows, values.shape[0]), (local_rows, values.shape[1])),
        context=context,
        comm=comm,
    )
    _g2a_matrix_diagnostic(matrix_metadata, "createPython.end")
    _g2a_matrix_diagnostic(matrix_metadata, "setUp.begin")
    matrix.setUp()
    _g2a_matrix_diagnostic(matrix_metadata, "setUp.end")
    return matrix, context


def _set_dense_vector(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _g2a_p4_fixture(
    *,
    backend: str,
    zero_rhs: bool = False,
    perturb_initial_port: bool = True,
    perturb_initial_fe: complex = 0.0 + 0.0j,
    nonfinite_first_fe: bool = False,
    correction_scales: tuple[float, ...] = (),
    local_row_counts: tuple[int, ...] | None = None,
):
    A0 = np.asarray(
        [[3.2 + 0.4j, 0.7 - 0.2j], [-0.3 + 0.5j, 2.4 - 0.6j]],
        dtype=np.complex128,
    )
    traction = np.asarray([[0.6 + 0.3j], [-0.2 + 0.45j]])
    projection = np.asarray([[0.35 - 0.1j, -0.15 + 0.25j]])
    block = np.block(
        [[A0, -traction], [-projection, np.ones((1, 1), dtype=np.complex128)]]
    )
    physical_matrix_values = A0 - traction @ projection
    physical_matrix, physical_context = _dense_python_matrix(
        physical_matrix_values,
        base_rows=2,
        purpose="physical",
        local_row_counts=local_row_counts,
    )
    first, last = (int(value) for value in physical_matrix.getOwnershipRange())
    rows = np.arange(first, last, dtype=PETSc.IntType)
    modes = (
        SimpleNamespace(
            projection_rows=rows,
            projection_values=np.conjugate(projection[0, rows]),
            denominator=1.0,
            traction_rows=rows,
            traction_values=traction[rows, 0],
        ),
    )
    physical_action = SimpleNamespace(
        matrix=physical_matrix,
        full_rows=2,
        modes=modes,
        action=SimpleNamespace(modes=modes),
        audit={},
    )
    exact_fe = np.asarray([0.3 + 0.1j, -0.2 + 0.4j])
    port_rhs = np.asarray([0.21 - 0.08j], dtype=np.complex128)
    if zero_rhs:
        exact_fe = np.zeros(2, dtype=np.complex128)
        port_rhs[:] = 0.0
    exact_port = port_rhs + projection @ exact_fe
    block_solution = np.concatenate((exact_fe, exact_port))
    block_rhs = block @ block_solution
    fe_rhs = _new_vector(physical_matrix, block_rhs[:2])
    perturb = 0.08 - 0.05j if perturb_initial_port else 0.0 + 0.0j
    dense_options = {
        "perturb_fe": perturb_initial_fe,
        "nonfinite_first_fe": nonfinite_first_fe,
        "correction_scales": correction_scales,
    }
    factor_matrix, factor_context = _dense_python_matrix(
        block,
        base_rows=2,
        appended_rows=1,
        purpose="augmented",
        local_row_counts=local_row_counts,
    )
    factor_matrix_metadata = getattr(factor_context, "_g2a_matrix_metadata", None)
    if backend == "full":
        factor = _DenseBlockSolve(block, perturb, **dense_options)
        p4 = P4ExactFactor(
            physical_action=physical_action,
            matrix=factor_matrix,
            factor=factor,
            factor_events=["dense-nonhermitian-test"],
            owns_physical_action=False,
        )
        rhs = p4.create_rhs(fe_rhs)
        _set_dense_vector(rhs, block_rhs)
        solution = rhs.duplicate()
        solution.set(0.0)
        inverse = factor
    elif backend == "cell_condensed":
        _g2a_matrix_diagnostic(factor_matrix_metadata, "destroy.begin", role="temporary_augmented")
        factor_matrix.destroy()
        _g2a_matrix_diagnostic(factor_matrix_metadata, "destroy.end", role="temporary_augmented")
        inverse = _DenseBlockSolve(block, perturb, **dense_options)
        p4 = P4CondensedExactFactor(
            physical_action=physical_action,
            inverse=inverse,
            factor_events=["dense-nonhermitian-test"],
            owns_physical_action=False,
        )
        rhs = fe_rhs
        solution = None
    else:
        raise ValueError("backend must be full or cell_condensed")
    return {
        "backend": backend,
        "p4": p4,
        "inverse": inverse,
        "rhs": rhs,
        "fe_rhs": fe_rhs,
        "solution": solution,
        "block": block,
        "block_rhs": block_rhs,
        "exact_solution": block_solution,
        "traction": traction[:, 0].copy(),
        "port_rhs": port_rhs.copy(),
        "physical_context": physical_context,
        "physical_matrix": physical_matrix,
        "factor_matrix": factor_matrix if backend == "full" else None,
        "factor_matrix_metadata": factor_matrix_metadata,
    }


def _g2a_destroy_vec(
    vector: PETSc.Vec,
    metadata: dict[str, int | str] | None,
    role: str,
) -> None:
    _g2a_matrix_diagnostic(metadata, "destroy.begin", resource="Vec", role=role)
    vector.destroy()
    _g2a_matrix_diagnostic(metadata, "destroy.end", resource="Vec", role=role)


def _destroy_g2a_p4_fixture(fixture: dict[str, object]) -> None:
    solution = fixture["solution"]
    factor_metadata = fixture.get("factor_matrix_metadata")
    physical_context = fixture["physical_context"]
    physical_metadata = getattr(physical_context, "_g2a_matrix_metadata", None)
    rhs_metadata = factor_metadata if fixture["backend"] == "full" else physical_metadata
    if solution is not None:
        _g2a_destroy_vec(solution, factor_metadata, "full_solution")
    rhs = fixture["rhs"]
    fe_rhs = fixture["fe_rhs"]
    _g2a_destroy_vec(rhs, rhs_metadata, "rhs")
    if fe_rhs is not rhs:
        _g2a_destroy_vec(fe_rhs, physical_metadata, "fe_rhs")
    _g2a_matrix_diagnostic(
        factor_metadata,
        "p4.destroy.begin",
        role="p4_owned_augmented_mat" if fixture["backend"] == "full" else "p4_inverse",
    )
    fixture["p4"].destroy()
    _g2a_matrix_diagnostic(
        factor_metadata,
        "p4.destroy.end",
        role="p4_owned_augmented_mat" if fixture["backend"] == "full" else "p4_inverse",
    )
    _g2a_matrix_diagnostic(physical_metadata, "destroy.begin", role="physical_action_mat")
    fixture["physical_matrix"].destroy()
    _g2a_matrix_diagnostic(physical_metadata, "destroy.end", role="physical_action_mat")


class _TimingCondensedInverse:
    def __init__(self, *, always_inexact: bool) -> None:
        self.always_inexact = bool(always_inexact)
        self.solve_count = 0
        self.destroy_count = 0
        self.last_port_solution = np.empty(0, dtype=np.complex128)
        self.last_timing: dict[str, float | None] = {}
        self.condensed = SimpleNamespace(
            active_rows=2,
            interior_rows=0,
            appended_rows=0,
            build_audit={},
        )
        self.factor = SimpleNamespace()

    def _prepare_port_rhs(self, port_rhs) -> np.ndarray:
        if port_rhs is None:
            return np.empty(0, dtype=np.complex128)
        values = np.asarray(port_rhs, dtype=np.complex128)
        if values.size:
            raise ValueError("timing fixture has no port rows")
        return values.copy()

    def apply(
        self,
        source: PETSc.Vec,
        *,
        port_rhs: np.ndarray | None = None,
    ) -> PETSc.Vec:
        del port_rhs
        self.solve_count += 1
        self.last_timing = {
            "storage_rhs_reduction_seconds": 1.0e-3,
            "factor_backsolve_seconds": 2.0e-3,
            "solution_recovery_seconds": 3.0e-3,
            "inner_apply_seconds": 6.0e-3,
        }
        result = source.duplicate()
        source.copy(result)
        if self.always_inexact or self.solve_count == 1:
            result.scale(PETSc.ScalarType(0.5))
        return result

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "factor_solve_count": self.solve_count,
            "last_solve": {"backsolve_count": 1},
        }

    def destroy(self) -> None:
        self.destroy_count += 1


def _timing_condensed_factor(
    *,
    always_inexact: bool,
) -> tuple[P4CondensedExactFactor, _TimingCondensedInverse, PETSc.Mat]:
    matrix, _context = _scale_matrix(2, 1.0)
    physical_action = SimpleNamespace(
        matrix=matrix,
        full_rows=2,
        action=SimpleNamespace(modes=()),
        audit={},
    )
    inverse = _TimingCondensedInverse(always_inexact=always_inexact)
    factor = P4CondensedExactFactor(
        physical_action=physical_action,
        inverse=inverse,
        factor_events=["timing-fixture"],
        owns_physical_action=False,
    )
    return factor, inverse, matrix


class _IdentityH6:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroy_count = 0

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        self.apply_count += 1
        return self._copy(source)

    @property
    def audit(self) -> dict[str, object]:
        return {"factor_count": 0, "apply_count": self.apply_count}

    def destroy(self) -> None:
        self.destroy_count += 1


class _TinyFixedH6WindowAction:
    def __init__(
        self,
        size: int,
        local_row_counts: tuple[int, ...] | None,
    ) -> None:
        self.matrix, self.context = _scale_matrix(
            size, 2.0, local_row_counts=local_row_counts
        )
        self.audit = {"apply_count": 0}

    def apply_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.matrix.mult(source, target)
        self.audit["apply_count"] += 1

    def destroy(self) -> None:
        self.matrix.destroy()


def _tiny_fixed_h6(
    size: int = 2,
    *,
    local_row_counts: tuple[int, ...] | None = None,
) -> FixedH6:
    window_action = _TinyFixedH6WindowAction(size, local_row_counts)
    diagonal = window_action.matrix.createVecRight()
    diagonal.set(PETSc.ScalarType(2.0))
    diagonal.assemble()
    seed = window_action.matrix.createVecRight()
    first, last = (int(value) for value in seed.getOwnershipRange())
    seed.getArray()[:] = np.asarray(
        [1.0 + 0.5j + index * (0.2 - 0.1j) for index in range(first, last)],
        dtype=PETSc.ScalarType,
    )
    seed.assemble()
    try:
        return FixedH6(
            window_action,
            diagonal,
            seed,
            {"fixture": "tiny-positive-window"},
            {"fixture": "fixed-nonzero-seed"},
        )
    except BaseException:
        window_action.destroy()
        diagonal.destroy()
        raise
    finally:
        seed.destroy()


class _FailingH6(_IdentityH6):
    def apply(self, _source: PETSc.Vec) -> PETSc.Vec:
        raise RuntimeError("focused H1e H6 failure")


class _KspContractStub:
    def __init__(
        self,
        approximate: PETSc.Vec,
        reason: int,
        iterations: int,
        pc: PETSc.PC,
    ) -> None:
        self.approximate = approximate
        self.reason = int(reason)
        self.iterations = int(iterations)
        self.pc = pc

    def solve(self, _source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.approximate.copy(target)

    def getConvergedReason(self) -> int:
        return self.reason

    def getIterationNumber(self) -> int:
        return self.iterations

    def getPC(self) -> PETSc.PC:
        return self.pc


class _BufferRecordingComm:
    def __init__(self, comm) -> None:
        self.comm = comm
        self.scalar_allreduce_count = 0
        self.buffer_allreduce_count = 0

    def allreduce(self, value, *, op):
        self.scalar_allreduce_count += 1
        return self.comm.allreduce(value, op=op)

    def Allreduce(self, send, receive, *, op):
        self.buffer_allreduce_count += 1
        self.comm.Allreduce(send, receive, op=op)

    def Get_rank(self) -> int:
        return self.comm.Get_rank()


class _RepeatedPcKsp:
    def __init__(self, owner: SideBalancedInverse, pc: PETSc.PC) -> None:
        self.owner = owner
        self.pc = pc

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        work = target.duplicate()
        try:
            self.owner._apply_balanced_pc(source, work)
            self.owner._apply_balanced_pc(source, target)
        finally:
            work.destroy()

    def getConvergedReason(self) -> int:
        return 1

    def getIterationNumber(self) -> int:
        return 1

    def getPC(self) -> PETSc.PC:
        return self.pc


class _FullAction:
    def __init__(
        self,
        size: int,
        *,
        local_row_counts: tuple[int, ...] | None = None,
    ) -> None:
        self.matrix, self.context = _scale_matrix(
            size, 1.0, local_row_counts=local_row_counts
        )
        self.full_rows = size
        self.destroy_count = 0

    def destroy(self) -> None:
        self.destroy_count += 1
        self.matrix.destroy()


def _new_vector(operator: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = operator.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        denominator = float(right.norm())
        numerator = float(difference.norm())
        return numerator / denominator if denominator else numerator
    finally:
        difference.destroy()


def _build_fixture(
    size: int = 2,
    *,
    checkpoint_callback=None,
    audit_callback=None,
    p4_factor=None,
    detailed_timing: bool = False,
    record_iteration_history: bool = False,
    p4_inverse_backend: str = "full",
    diagnostic_callback=None,
    reuse_leading_ph_dual: bool = False,
    h6_action=None,
    local_row_counts: tuple[int, ...] | None = None,
    side_restart64_trial_state: dict[str, object] | None = None,
    side_restart64_memory_gate=None,
) -> tuple[SideBalancedInverse, dict[str, object]]:
    operator, operator_context = _scale_matrix(
        size, 2.0, local_row_counts=local_row_counts
    )
    condensed = _IdentityCondensed(size, local_row_counts=local_row_counts)
    side_system = SimpleNamespace(
        A=operator,
        cfg=SimpleNamespace(nedelec_degree=6),
        static_condensation=SimpleNamespace(condensed=condensed),
        side="bottom",
    )
    full_action = _FullAction(size, local_row_counts=local_row_counts)
    p4_factor = _IdentityP4(size) if p4_factor is None else p4_factor
    transfer = _IdentityTransfer()
    h6 = _IdentityH6() if h6_action is None else h6_action
    inverse = SideBalancedInverse(
        side_system,
        full_action,
        p4_factor,
        transfer,
        h6,
        checkpoint_callback=checkpoint_callback,
        audit_callback=audit_callback,
        diagnostic_callback=diagnostic_callback,
        detailed_timing=detailed_timing,
        record_iteration_history=record_iteration_history,
        p4_inverse_backend=p4_inverse_backend,
        reuse_leading_ph_dual=reuse_leading_ph_dual,
        side_restart64_trial_state=side_restart64_trial_state,
        side_restart64_memory_gate=side_restart64_memory_gate,
    )
    return inverse, {
        "operator": operator,
        "operator_context": operator_context,
        "full_action": full_action,
        "p4_factor": p4_factor,
        "transfer": transfer,
        "h6": h6,
        "side_system": side_system,
    }


def _builder_side_system(size: int = 2):
    operator, operator_context = _scale_matrix(size, 2.0)
    side_system = object.__new__(HybridLocalDtnActionSystem)
    side_system.A = operator
    side_system.cfg = SimpleNamespace(nedelec_degree=6)
    side_system.static_condensation = SimpleNamespace(
        condensed=_IdentityCondensed(size)
    )
    side_system.side = "bottom"
    b = operator.createVecLeft()
    b.set(PETSc.ScalarType(1.0 + 0.5j))
    b.assemble()
    side_system.b = b
    return side_system, operator, operator_context, b


def _assert_borrowed_stub_system_works(
    operator: PETSc.Mat,
    operator_context: _ScaleContext,
    b: PETSc.Vec,
    b_before: np.ndarray,
) -> None:
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    output = operator.createVecLeft()
    try:
        operator.mult(source, output)
        np.testing.assert_allclose(
            output.getArray(readonly=True),
            2.0 * source.getArray(readonly=True),
        )
        np.testing.assert_array_equal(
            b.getArray(readonly=True),
            b_before,
        )
        assert operator_context.destroyed is False
    finally:
        output.destroy()
        source.destroy()


def _install_stub_side_builders(monkeypatch, captured):
    def fake_full_action(_side_system, *, volume_action_context_factory=None):
        action = _FullAction(2)
        action.V = object()
        action.floquet_data = object()
        captured["full_action"] = action
        captured.setdefault("volume_action_context_factory_calls", []).append(
            volume_action_context_factory
        )
        if volume_action_context_factory is not None:
            action.action = SimpleNamespace(
                context=SimpleNamespace(
                    audit={
                        "local_kernel": {
                            "backend": (
                                "task041_opt_in_sum_factorized_physical_volume"
                            )
                        }
                    }
                )
            )
        return action

    def fake_p4(_side_system, *, lifecycle_callback=None):
        captured["p4_callback"] = lifecycle_callback
        factor = _IdentityP4(2)
        captured["p4"] = factor
        return factor

    def fake_condensed_p4(
        _side_system,
        *,
        lifecycle_callback=None,
        stage_factory=None,
        stage_identity=None,
        defer_numeric=False,
    ):
        captured["condensed_p4_callback"] = lifecycle_callback
        captured["condensed_p4_stage_factory"] = stage_factory
        captured["condensed_p4_stage_identity"] = stage_identity
        captured["condensed_p4_defer_numeric"] = defer_numeric
        factor = _CellCondensedP4(2)
        captured["condensed_p4"] = factor
        return factor

    def fake_transfer(
        _fine_v,
        _fine_floquet,
        _coarse_v,
        _coarse_floquet,
        *,
        optimization_profile=None,
        support_policy=SUPPORT_POLICY_LEGACY,
        reuse_primal_route_plan=False,
        compact_orientation=False,
    ):
        transfer = _IdentityTransfer(
            default_variant=(
                "optimized"
                if optimization_profile == "task041_schur_speed_v2"
                else "legacy"
            )
        )
        transfer._reuse_primal_route_plan = reuse_primal_route_plan
        transfer.comm = SimpleNamespace(
            rank=int(captured.get("route_snapshot_rank", 0)),
            size=int(captured.get("route_snapshot_comm_size", 1)),
        )

        def allgather(value):
            captured.setdefault("compact_inventory_allgather_values", []).append(
                value
            )
            if transfer.comm.size == 1:
                records = [value]
            else:
                remote_payload = value.get("payload") or {
                    "K_local": 1,
                    "record_unique_key_count_local": 1,
                    "record_count_local": 1,
                    "canonical_R_bytes_local": 16,
                    "nonidentity_transform_block_bytes_local": 24,
                    "entity_index_payload_bytes_local": 10,
                    "unique_numeric_array_payload_bytes_local": 50,
                    "seed_key_coarse_fine": [0, 0],
                    "seed_has_cell_record": True,
                    "owned_cell_count_local": 3,
                    "owned_plus_ghost_cell_count_local": 4,
                }
                records = [
                    value,
                    {"rank": 1, "error": None, "payload": remote_payload},
                ]
            captured.setdefault("compact_inventory_allgather_results", []).append(
                records
            )
            return records

        transfer.comm.allgather = allgather
        transfer._primal_route_plan = captured.get("route_plan")
        if compact_orientation:
            orientation_storage = {
                "representation": "compact_entity_blocks",
                "key_order": ["coarse_cell_info", "fine_cell_info"],
                "seed_key": [0, 0],
                "seed_included_in_unique_key_count": True,
                "seed_key_has_cell_record": True,
                "unique_key_count_including_seed": 1,
                "record_unique_key_count": 1,
                "record_count_local": 4,
                "canonical_R_bytes_local": 16,
                "nonidentity_transform_block_bytes_local": 24,
                "entity_index_bytes_local": 10,
                "unique_numeric_array_payload_bytes_local": 50,
            }
            if captured.get("invalid_compact_orientation_audit"):
                orientation_storage["representation"] = "invalid"
            transfer._audit = {
                **transfer.audit,
                "orientation_storage": orientation_storage,
            }
            transfer.mesh = SimpleNamespace(
                topology=SimpleNamespace(
                    dim=3,
                    index_map=lambda _dimension: SimpleNamespace(
                        size_local=3,
                        num_ghosts=1,
                    ),
                )
            )
        captured["transfer"] = transfer
        captured["optimization_profile"] = optimization_profile
        captured["support_policy"] = support_policy
        captured.setdefault("compact_orientation_calls", []).append(
            compact_orientation
        )
        captured.setdefault("reuse_primal_route_plan_calls", []).append(
            reuse_primal_route_plan
        )
        return transfer

    def fake_h6(_side_system, *, lifecycle_callback=None):
        captured["h6_callback"] = lifecycle_callback
        h6 = _IdentityH6()
        captured["h6"] = h6
        return h6

    monkeypatch.setattr(
        side_inverse_module,
        "build_fullspace_physical_dtn_action",
        fake_full_action,
    )
    monkeypatch.setattr(side_inverse_module, "build_p4_exact_factor", fake_p4)
    monkeypatch.setattr(
        side_inverse_module,
        "build_p4_condensed_exact_factor",
        fake_condensed_p4,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "build_same_mesh_hcurl_owner_transfer",
        fake_transfer,
    )
    monkeypatch.setattr(side_inverse_module, "build_balanced_h6", fake_h6)
    monkeypatch.setattr(
        side_inverse_module,
        "_full_action_inventory",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_owner_transfer_inventory",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_side_adapter_inventory",
        lambda *_args, **_kwargs: {},
    )


@pytest.mark.parametrize(
    "optimization_profile",
    [None, "task041_schur_speed_v2"],
    ids=["legacy", "task041_schur_speed_v2"],
)
@pytest.mark.parametrize(
    "support_policy",
    [SUPPORT_POLICY_LEGACY, SUPPORT_POLICY_ENTITY_CLOSURE],
    ids=["legacy_support", "entity_closure_support"],
)
@pytest.mark.parametrize("detailed_timing", [False, True])
def test_side_inverse_builder_default_callback_skips_inventory(
    monkeypatch, optimization_profile, support_policy, detailed_timing
):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    inventory_calls = []
    _install_stub_side_builders(monkeypatch, captured)

    def forbidden_inventory(*_args, **_kwargs):
        inventory_calls.append(True)
        raise AssertionError("default lifecycle callback read inventory")

    monkeypatch.setattr(
        side_inverse_module,
        "_full_action_inventory",
        forbidden_inventory,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_owner_transfer_inventory",
        forbidden_inventory,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_side_adapter_inventory",
        forbidden_inventory,
    )
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            detailed_timing=detailed_timing,
            performance_profile=optimization_profile,
            support_policy=support_policy,
        )
        assert captured["p4_callback"] is None
        assert captured["h6_callback"] is None
        assert captured["optimization_profile"] == optimization_profile
        assert captured["support_policy"] == support_policy
        assert captured["transfer"].execution_variant == (
            "optimized"
            if optimization_profile == "task041_schur_speed_v2"
            else "legacy"
        )
        assert inventory_calls == []
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


def test_side_inverse_builder_selects_explicit_cell_condensed_backend(monkeypatch):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            p4_inverse_backend="cell_condensed",
        )
        assert inverse.diagnostics["p4_inverse_backend"] == "cell_condensed"
        assert inverse.diagnostics["physical_action_backend"] == (
            "MpcFormActionContext"
        )
        assert captured["volume_action_context_factory_calls"] == [None]
        assert "condensed_p4" in captured
        assert "p4" not in captured
        assert captured["condensed_p4_callback"] is None
        assert captured["reuse_primal_route_plan_calls"] == [False]
        assert captured["compact_orientation_calls"] == [False]
        assert inverse._reuse_leading_ph_dual is False
        assert inverse._coupling._reuse_leading_ph is False
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


@pytest.mark.parametrize(
    ("reuse_primal_route_plan", "reuse_leading_ph_dual"),
    ((False, False), (True, False), (False, True), (True, True)),
)
def test_side_inverse_builder_forwards_reuse_flags_independently(
    monkeypatch, reuse_primal_route_plan, reuse_leading_ph_dual
):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            reuse_primal_route_plan=reuse_primal_route_plan,
            reuse_leading_ph_dual=reuse_leading_ph_dual,
        )
        assert captured["reuse_primal_route_plan_calls"] == [
            reuse_primal_route_plan
        ]
        assert captured["compact_orientation_calls"] == [False]
        assert captured["transfer"]._reuse_primal_route_plan is (
            reuse_primal_route_plan
        )
        assert inverse._reuse_leading_ph_dual is reuse_leading_ph_dual
        assert inverse._coupling._reuse_leading_ph is reuse_leading_ph_dual
        snapshot = inverse.primal_route_plan_snapshot()
        if reuse_primal_route_plan:
            assert snapshot["status"] == "not_captured_yet"
            assert snapshot["N_r"] is None
            assert snapshot["M_r"] is None
            assert snapshot["persistent_index_payload_bytes_local"] is None
        else:
            assert snapshot["status"] == "disabled"
            assert snapshot["captured"] is False
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


def test_side_inverse_builder_forwards_compact_orientation_only_for_deferred_stage(
    monkeypatch,
):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    inventory_owners = []
    lifecycle_events = []
    inventory_payloads = []

    def capture_inventory(owner, *, compact_orientation_inventory=None):
        inventory_owners.append(owner)
        inventory_payloads.append(compact_orientation_inventory)
        return {"fixture": True}

    monkeypatch.setattr(
        side_inverse_module,
        "_full_action_inventory",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_owner_transfer_inventory",
        capture_inventory,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_side_adapter_inventory",
        lambda *_args, **_kwargs: {},
    )
    inverse = None
    stage_factory = lambda **_kwargs: None
    try:
        with pytest.raises(ValueError, match="compact orientation is limited"):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                p4_inverse_backend="cell_condensed",
                compact_orientation=True,
                lifecycle_callback=lambda event, detail: lifecycle_events.append(
                    (event, detail)
                ),
            )

        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            p4_inverse_backend="cell_condensed",
            factor_stage_factory=stage_factory,
            defer_p4_numeric=True,
            compact_orientation=True,
            lifecycle_callback=lambda event, detail: lifecycle_events.append(
                (event, detail)
            ),
        )
        assert captured["compact_orientation_calls"] == [True]
        assert captured["condensed_p4_stage_factory"] is stage_factory
        assert captured["condensed_p4_defer_numeric"] is True
        assert len(inventory_owners) == 1
        assert len(captured["compact_inventory_allgather_values"]) == 1
        gathered_record = captured["compact_inventory_allgather_values"][0]
        assert gathered_record["error"] is None
        assert gathered_record["payload"]["K_local"] == 1
        assert inventory_payloads[0]["rank_records"][0][
            "owned_plus_ghost_cell_count_local"
        ] == 4
        assert inventory_payloads[0]["cross_rank_total"][
            "rank_local_unique_numeric_array_payload_bytes_sum"
        ] == 50
        assert any(event == "transfer_ready" for event, _detail in lifecycle_events)

        inverse.destroy()
        inverse = None
        captured["route_snapshot_comm_size"] = 2
        captured["invalid_compact_orientation_audit"] = True
        with pytest.raises(
            RuntimeError,
            match="rejected collectively after setup allgather",
        ):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                p4_inverse_backend="cell_condensed",
                factor_stage_factory=stage_factory,
                defer_p4_numeric=True,
                compact_orientation=True,
                lifecycle_callback=lambda event, detail: lifecycle_events.append(
                    (event, detail)
                ),
            )
        assert len(captured["compact_inventory_allgather_values"]) == 2
        assert captured["compact_inventory_allgather_values"][-1][
            "error"
        ] is not None
        gathered = captured["compact_inventory_allgather_results"][-1]
        assert gathered[0]["error"] is not None
        assert gathered[0]["payload"] is None
        assert gathered[1]["error"] is None
        assert isinstance(gathered[1]["payload"], dict)
        assert captured["transfer"].destroy_count == 1
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


def test_compact_owner_transfer_inventory_uses_scalar_audit_without_matrix_access():
    class MatrixMustNotBeRead:
        @property
        def matrix(self):
            raise AssertionError("compact inventory accessed the absent dense matrix")

    class InventoryComm:
        rank = 0
        size = 2

        def __init__(self):
            self.allgather_calls = 0

        def allgather(self, local_record):
            self.allgather_calls += 1
            remote_record = dict(local_record)
            remote_record.update(
                {
                    "rank": 1,
                    "K_local": 2,
                    "record_unique_key_count_local": 1,
                    "record_count_local": 5,
                    "canonical_R_bytes_local": 12,
                    "nonidentity_transform_block_bytes_local": 20,
                    "entity_index_payload_bytes_local": 8,
                    "unique_numeric_array_payload_bytes_local": 40,
                    "owned_cell_count_local": 3,
                    "owned_plus_ghost_cell_count_local": 5,
                }
            )
            return [local_record, remote_record]

    comm = InventoryComm()
    cell_map = SimpleNamespace(size_local=2, num_ghosts=1)
    owner_transfer = SimpleNamespace(
        audit={
            "orientation_storage": {
                "representation": "compact_entity_blocks",
                "key_order": ["coarse_cell_info", "fine_cell_info"],
                "seed_key": [0, 0],
                "seed_included_in_unique_key_count": True,
                "seed_key_has_cell_record": False,
                "unique_key_count_including_seed": 3,
                "record_unique_key_count": 2,
                "record_count_local": 4,
                "canonical_R_bytes_local": 16,
                "nonidentity_transform_block_bytes_local": 24,
                "entity_index_bytes_local": 10,
                "unique_numeric_array_payload_bytes_local": 50,
            }
        },
        local_transfer=MatrixMustNotBeRead(),
        comm=comm,
        mesh=SimpleNamespace(
            topology=SimpleNamespace(
                dim=3,
                index_map=lambda _dimension: cell_map,
            )
        ),
        _coarse_work=SimpleNamespace(
            x=SimpleNamespace(array=np.zeros(2, dtype=np.complex128))
        ),
        _fine_work=SimpleNamespace(
            x=SimpleNamespace(array=np.zeros(3, dtype=np.complex128))
        ),
        _dual_reduction_work=np.zeros(1, dtype=np.complex128),
        fine_space=SimpleNamespace(
            dofmap=SimpleNamespace(
                index_map=SimpleNamespace(size_global=8)
            )
        ),
        coarse_space=SimpleNamespace(
            dofmap=SimpleNamespace(
                index_map=SimpleNamespace(size_global=4)
            )
        ),
        _fine_owned_size=5,
        _coarse_owned_size=2,
    )

    local_record = side_inverse_module._compact_owner_transfer_storage_local_record(
        owner_transfer
    )
    remote_record = dict(local_record)
    remote_record.update(
        {
            "rank": 1,
            "payload": {
                **local_record["payload"],
                "K_local": 2,
                "record_unique_key_count_local": 1,
                "record_count_local": 5,
                "canonical_R_bytes_local": 12,
                "nonidentity_transform_block_bytes_local": 20,
                "entity_index_payload_bytes_local": 8,
                "unique_numeric_array_payload_bytes_local": 40,
                "owned_cell_count_local": 3,
                "owned_plus_ghost_cell_count_local": 5,
            },
        }
    )
    storage_payload = side_inverse_module._aggregate_compact_owner_transfer_storage_records(
        [local_record, remote_record], communicator_size=2
    )
    inventory = side_inverse_module._owner_transfer_inventory(
        owner_transfer,
        compact_orientation_inventory=storage_payload,
    )
    storage = inventory["compact_orientation_storage"]
    assert comm.allgather_calls == 0
    # The local inventory is collective-free; build_side_balanced_inverse owns it.
    assert inventory["stage_scope"] == "rank_local_with_setup_scalar_allgather"
    assert [record["K_local"] for record in storage["rank_records"]] == [3, 2]
    assert storage["rank_records"][0]["seed_key_coarse_fine"] == [0, 0]
    assert storage["rank_records"][0]["seed_has_cell_record"] is False
    assert storage["rank_records"][0]["owned_cell_count_local"] == 2
    assert storage["rank_records"][0]["owned_plus_ghost_cell_count_local"] == 3
    totals = storage["cross_rank_total"]
    assert totals["rank_local_K_sum"] == 5
    assert totals["rank_local_canonical_R_bytes_sum"] == 28
    assert totals["rank_local_nonidentity_transform_block_bytes_sum"] == 44
    assert totals["rank_local_entity_index_payload_bytes_sum"] == 18
    assert totals["rank_local_unique_numeric_array_payload_bytes_sum"] == 90
    assert totals["rank_local_owned_cell_count_sum"] == 5
    assert totals["rank_local_owned_plus_ghost_cell_count_sum"] == 8
    assert not any(
        record["label"] == "transfer.canonical_reference_map"
        for record in inventory["owned_objects"]
    )


def test_side_inverse_route_plan_snapshot_is_local_and_released(monkeypatch):
    captured = {
        "route_snapshot_rank": 2,
        "route_snapshot_comm_size": 4,
        "route_plan": None,
    }
    route_plan = SimpleNamespace(
        candidate_ids=np.arange(3, dtype=np.uint64),
        send_order=np.arange(3, dtype=np.int64),
        recv_order=np.arange(2, dtype=np.int64),
        recv_ids=np.arange(2, dtype=np.uint64),
        source_ranks=np.arange(2, dtype=np.int32),
        send_counts=np.arange(4, dtype=np.int32),
        send_displacements=np.arange(4, dtype=np.int32),
        recv_counts=np.arange(4, dtype=np.int32),
        recv_displacements=np.arange(4, dtype=np.int32),
    )
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            reuse_primal_route_plan=True,
        )
        before_capture = inverse.primal_route_plan_snapshot()
        assert before_capture["status"] == "not_captured_yet"
        assert before_capture["persistent_index_payload_bytes_local"] is None
        captured["route_plan"] = route_plan
        captured["transfer"]._primal_route_plan = route_plan
        snapshot = inverse.primal_route_plan_snapshot()
        assert snapshot["status"] == "captured"
        assert snapshot["rank"] == 2
        assert snapshot["communicator_size"] == 4
        assert snapshot["N_r"] == 3
        assert snapshot["M_r"] == 2
        assert snapshot["persistent_index_payload_bytes_local"] == 152
        assert snapshot["payload_formula_bytes_local"] == 152
        assert snapshot["payload_formula_matches"] is True
        assert captured["transfer"]._primal_route_plan is captured[
            "route_plan"
        ]
        inverse.destroy()
        destroyed = inverse.primal_route_plan_snapshot()
        assert destroyed["status"] == "destroyed"
        assert destroyed["captured"] is None
        assert destroyed["persistent_index_payload_bytes_local"] is None
    finally:
        if inverse is not None and not inverse._destroyed:
            inverse.destroy()
        b.destroy()
        operator.destroy()


def test_side_inverse_route_plan_requires_strict_bool_before_building():
    with pytest.raises(TypeError, match="reuse_primal_route_plan must be a boolean"):
        side_inverse_module.build_side_balanced_inverse(
            None,
            reuse_primal_route_plan=1,
        )


def test_side_inverse_leading_ph_reuse_requires_strict_bool_and_no_vector_observer(
    monkeypatch,
):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    try:
        with pytest.raises(
            TypeError,
            match="reuse_leading_ph_dual must be a boolean",
        ):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                reuse_leading_ph_dual=1,
            )
        with pytest.raises(
            ValueError,
            match="leading PH reuse is incompatible with mutable",
        ):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                diagnostic_callback=lambda _record: None,
                reuse_leading_ph_dual=True,
            )
        assert captured == {}
    finally:
        b.destroy()
        operator.destroy()


def test_side_inverse_builder_forwards_fused_physical_factory_only_when_selected(
    monkeypatch,
):
    from src.solvers.physical_balanced_fused_volume import (
        build_task041_fused_physical_volume_context,
    )

    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    _install_stub_side_builders(monkeypatch, captured)
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(
            side_system,
            p4_inverse_backend="cell_condensed",
            volume_action_context_factory=(
                build_task041_fused_physical_volume_context
            ),
        )
        assert captured["volume_action_context_factory_calls"] == [
            build_task041_fused_physical_volume_context
        ]
        assert inverse.operator is operator
        ksp_operator, _ = inverse._ksp.getOperators()
        assert int(ksp_operator.handle) == int(operator.handle)
        assert inverse._p4_factor is captured["condensed_p4"]
        assert inverse._h6 is captured["h6"]
        assert inverse.diagnostics["p4_inverse_backend"] == "cell_condensed"
        assert inverse.diagnostics["physical_action_backend"] == (
            "task041_opt_in_sum_factorized_physical_volume"
        )
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


def test_side_inverse_condensed_q_records_timing_and_solve_delta():
    p4_factor = _CellCondensedP4(2)
    inverse, owned = _build_fixture(
        p4_factor=p4_factor,
        detailed_timing=True,
        p4_inverse_backend="cell_condensed",
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    result = None
    try:
        assert inverse._diagnostic_callback is None
        result = inverse._apply_q_callback(source)
        assert p4_factor.apply_count == 1
        assert p4_factor.solve_count == 1
        assert inverse._p4_backsolve_count == 1
        assert inverse._p4_refinement_count == 0
        assert inverse._rhs_detail_seen["q_factor_solve_seconds"] is True
        assert inverse._rhs_detail_seconds["q_factor_solve_seconds"] == pytest.approx(
            2.0e-4
        )
        assert inverse._rhs_detail_seconds[
            "q_p4_storage_rhs_reduction_seconds"
        ] == pytest.approx(1.0e-4)
        assert inverse._rhs_detail_seconds[
            "q_p4_solution_recovery_seconds"
        ] == pytest.approx(3.0e-4)
        assert result.norm() > 0.0
    finally:
        if result is not None:
            result.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()
    assert p4_factor.destroy_count == 1


def test_diagnostic_p4_configuration_preserves_default_solver_state():
    inverse, owned = _build_fixture()
    try:
        assert inverse._ksp is not None
        original_ksp = inverse._ksp
        original_coupling = inverse._coupling
        inverse._p4_backsolve_count = 7
        inverse._p4_refinement_count = 3

        def observer(_audit, _vectors):
            return None

        inverse.configure_diagnostic_p4_corrections(2, observer)

        assert inverse._diagnostic_p4_correction_steps == 2
        assert inverse._diagnostic_p4_correction_callback is observer
        assert inverse._p4_backsolve_count == 7
        assert inverse._p4_refinement_count == 3
        assert inverse._ksp is original_ksp
        assert inverse._coupling is original_coupling
        inverse.configure_diagnostic_p4_corrections(0, None)
        assert inverse._diagnostic_p4_correction_steps == 0
        assert inverse._diagnostic_p4_correction_callback is None
    finally:
        inverse.destroy()
        owned["operator"].destroy()


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
@pytest.mark.parametrize(
    ("correction_steps", "with_observer"),
    [(0, False), (1, False), (1, True)],
)
def test_side_inverse_opt_in_correction_without_observer_uses_one_primal_action(
    backend: str,
    correction_steps: int,
    with_observer: bool,
) -> None:
    p4_factor = (
        _IdentityP4(2) if backend == "full" else _CellCondensedP4(2)
    )
    side_diagnostic_events: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        p4_factor=p4_factor,
        p4_inverse_backend=backend,
        detailed_timing=True,
        diagnostic_callback=lambda record: side_diagnostic_events.append(
            dict(record)
        ),
    )
    operator = owned["operator"]
    transfer = owned["transfer"]
    source = _new_vector(
        operator,
        np.asarray([0.5 + 0.25j, -0.125 + 0.375j]),
    )
    source_before = _gather_dense_vector(source)
    correction_events: list[dict[str, object]] = []
    result = None
    try:
        if correction_steps:
            observer = (
                (lambda record, _borrowed: correction_events.append(dict(record)))
                if with_observer
                else None
            )
            inverse.configure_diagnostic_p4_corrections(
                correction_steps,
                observer,
            )

        result = inverse._apply_q_callback(source)

        expected_kwargs: dict[str, object] = {}
        if correction_steps:
            expected_kwargs["diagnostic_correction_steps"] = correction_steps
            if with_observer:
                callback = p4_factor.last_diagnostic_kwargs.get(
                    "diagnostic_callback"
                )
                assert callable(callback)
                expected_kwargs["diagnostic_callback"] = callback
        assert p4_factor.last_diagnostic_kwargs == expected_kwargs
        assert p4_factor.solve_count == correction_steps + 1
        assert inverse._p4_backsolve_count == correction_steps + 1
        assert inverse._p4_refinement_count == correction_steps
        assert inverse._p_count == 1
        assert transfer.primal_apply_count == (
            1 + correction_steps + 1 if with_observer else 1
        )
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        assert result.norm() > 0.0

        if correction_steps:
            last_solve = p4_factor.diagnostics["last_solve"]
            assert last_solve["backsolve_count"] == correction_steps + 1
            p4_call_history = inverse.diagnostics["independent_p4_call_history"]
            assert len(p4_call_history) == 1
            scalar_history = p4_call_history[0][
                "last_solve_scalar_summary"
            ]["diagnostic_correction_history"]
            assert [
                step["diagnostic_step_index"] for step in scalar_history
            ] == list(range(correction_steps + 1))
            assert [step["refinement_count"] for step in scalar_history] == list(
                range(correction_steps + 1)
            )
            assert all(
                "physical_relative_residual" in step
                and "correction_from_previous_seconds" in step
                and "factor_solve_seconds_for_state" in step
                for step in scalar_history
            )
        if with_observer:
            assert [
                record["p4_audit"]["diagnostic_step_index"]
                for record in correction_events
            ] == list(range(correction_steps + 1))
    finally:
        if result is not None:
            result.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_side_inverse_residual_target_routes_without_extra_observer_or_primal(
    backend: str,
) -> None:
    p4_factor = _IdentityP4(2) if backend == "full" else _CellCondensedP4(2)
    inverse, owned = _build_fixture(
        p4_factor=p4_factor,
        p4_inverse_backend=backend,
        detailed_timing=True,
    )
    operator = owned["operator"]
    transfer = owned["transfer"]
    source = _new_vector(
        operator,
        np.asarray([0.5 + 0.25j, -0.125 + 0.375j]),
    )
    source_before = _gather_dense_vector(source)
    result = None
    try:
        inverse.configure_diagnostic_p4_corrections(
            0,
            None,
            refinement_target_tolerance=5.0e-13,
        )
        result = inverse._apply_q_callback(source)

        assert p4_factor.last_diagnostic_kwargs == {
            "refinement_target_tolerance": 5.0e-13
        }
        assert p4_factor.solve_count == 1
        assert inverse._p4_backsolve_count == 1
        assert inverse._p4_refinement_count == 0
        assert inverse._p_count == 1
        assert transfer.primal_apply_count == 1
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        call = inverse.diagnostics["independent_p4_call_history"][0]
        assert call["refinement_target_tolerance"] == 5.0e-13
        assert call["target_reached"] is True
        assert call["actual_correction_count"] == 0
        assert call["last_solve_scalar_summary"]["diagnostic_correction_history"][
            0
        ]["stop_reason"] == "target_reached"
    finally:
        if result is not None:
            result.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_opt_in_diagnostic_scope_labels_and_p4_norms():
    events: list[dict[str, object]] = []

    def collect(record):
        events.append(record)
        return False

    p4_factor = _CellCondensedP4(2)
    inverse, owned = _build_fixture(
        p4_factor=p4_factor,
        p4_inverse_backend="cell_condensed",
        diagnostic_callback=collect,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    result = None
    try:
        result = inverse._apply_q_callback(source)
        replay_input = next(event for event in events if event["event"] == "Q_input")
        assert replay_input["scope"] == "independent_replay"
        assert replay_input["q_call_index"] == 1
        assert "pc_apply_index" not in replay_input
        assert "ksp_iteration" not in replay_input
        ph_q_output = next(
            event for event in events if event["event"] == "PH_Q_output"
        )
        p_output = next(event for event in events if event["event"] == "P_output")
        assert ph_q_output["q_call_index"] == 1
        assert p_output["q_call_index"] == 1

        call = inverse.diagnostics["independent_p4_call_history"][0]
        assert call["ksp_iteration"] is None
        assert call["physical_rhs_norm"] == pytest.approx(float(source.norm()))
        assert call["solution_norm"] == pytest.approx(float(source.norm()))
        assert call["solution_norm_status"] == "measured"

        inverse._apply_in_progress = True
        inverse._active_ksp_iteration = 4
        inverse._active_pc_index = 3
        inverse._emit_diagnostic("PC_input")
        pc_input = events[-1]
        assert pc_input["scope"] == "side_apply"
        assert pc_input["pc_apply_index"] == 3
        assert "q_call_index" not in pc_input

        inverse._emit_diagnostic("Q_input", q_call_index=2)
        q_input = events[-1]
        assert q_input["scope"] == "side_apply"
        assert q_input["pc_apply_index"] == 3
        assert q_input["q_call_index"] == 2
        assert q_input["ksp_iteration"] == 4

        inverse._active_pc_index = None
        inverse._active_pc_q_count = 0
        inverse._monitor(None, 5, 0.25)
        monitor = events[-1]
        assert monitor["event"] == "ksp_monitor"
        assert monitor["scope"] == "side_apply"
        assert monitor["ksp_iteration"] == 5
        assert "pc_apply_index" not in monitor
        assert "q_call_index" not in monitor
    finally:
        inverse._apply_in_progress = False
        inverse._active_ksp_iteration = None
        if result is not None:
            result.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_direct_pc_uses_per_pc_q_labels_after_direct_q_history():
    events: list[dict[str, object]] = []

    def collect(record):
        events.append(dict(record))
        return False

    inverse, owned = _build_fixture(diagnostic_callback=collect)
    operator = owned["operator"]
    source = _new_vector(
        operator, np.asarray([0.5 + 0.25j, -0.125 + 0.375j])
    )
    pc_output = operator.createVecLeft()
    direct_q_output = None
    try:
        direct_q_output = inverse._apply_q_callback(source)
        first_q = next(
            event
            for event in events
            if event.get("event") == "Q_input"
        )
        assert first_q["scope"] == "independent_replay"
        assert first_q["q_call_index"] == 1

        inverse._apply_balanced_pc(source, pc_output)
        pc_q_events = [
            event
            for event in events
            if event.get("event") == "Q_input"
            and event.get("scope") == "direct_pc_apply"
        ]
        assert [event["q_call_index"] for event in pc_q_events] == [1, 2]
        assert all(event.get("pc_apply_index") is not None for event in pc_q_events)
        assert all(event.get("ksp_iteration") is None for event in pc_q_events)
    finally:
        if direct_q_output is not None:
            direct_q_output.destroy()
        pc_output.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_samples_true_residual_from_real_ksp_monitor():
    comm = MPI.COMM_WORLD
    samples: list[dict[str, object]] = []
    first_sample_solution_refs: list[PETSc.Vec] = []
    audit_records: list[dict[str, object]] = []

    def collect(record):
        if record.get("event") != "ksp_true_residual_sample":
            return
        vectors = record["borrowed_vectors"]
        sample_solution = vectors["solution"]
        lo, hi = sample_solution.getOwnershipRange()
        values = np.array(sample_solution.getArray(readonly=True), copy=True)
        residual = np.array(
            vectors["true_residual"].getArray(readonly=True), copy=True
        )
        source = np.array(vectors["rhs"].getArray(readonly=True), copy=True)
        diagonal = np.arange(lo + 2, hi + 2, dtype=np.float64)
        if record["sample_label"] == "first_iteration":
            first_sample_solution_refs.append(sample_solution)
        samples.append(
            {
                "iteration": record["iteration"],
                "sample_label": record["sample_label"],
                "true_residual_norm": record["true_residual_norm"],
                "finite": record["finite"],
                "local_residual_error": float(
                    np.max(np.abs(residual - (source - diagonal * values)))
                )
                if values.size
                else 0.0,
                "solution": values,
            }
        )

    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        diagnostic_callback=collect,
    )
    fixture_operator = owned["operator"]
    matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=1, comm=comm)
    matrix.setUp()
    first, last = matrix.getOwnershipRange()
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(2 + row))
    matrix.assemble()
    rhs = matrix.createVecRight()
    for index in range(*rhs.getOwnershipRange()):
        rhs.setValue(index, PETSc.ScalarType(1.0))
    rhs.assemble()
    solution = matrix.createVecRight()
    solution.set(0.0)
    solver = inverse._ksp
    assert solver is not None

    try:
        inverse._operator = matrix
        inverse._max_it = 5
        solver.setOperators(matrix)
        solver.setTolerances(rtol=1.0e-13, atol=0.0, max_it=5)
        solver.getPC().setType("none")
        inverse._rtol = 1.0e-13
        solver.setUp()
        assert solver.getType().lower() == "fgmres"
        assert solver.getPCSide() == PETSc.PC.Side.RIGHT
        assert side_inverse_module._live_gmres_restart(solver) == 32
        inverse.apply(rhs, solution)
        first_samples = [
            item for item in samples if item["sample_label"] == "first_iteration"
        ]
        assert len(first_samples) == 1
        assert first_samples[0]["iteration"] == 1
        assert first_samples[0]["true_residual_norm"] > 0.0
        assert first_samples[0]["finite"] is True
        assert first_samples[0]["local_residual_error"] < 1.0e-12
        assert all(item["iteration"] > 0 for item in samples)
        assert samples[-1]["sample_label"] == "final_iteration"
        assert samples[-1]["iteration"] == int(solver.getIterationNumber())
        assert len(first_sample_solution_refs) == 1
        assert int(first_sample_solution_refs[0].handle) == 0

        persisted = inverse.diagnostics["last_apply"]["true_residual_samples"]
        assert [item["sample_label"] for item in persisted] == [
            "first_iteration",
            "final_iteration",
        ]
        assert persisted[0]["iteration"] == 1
        assert persisted[-1]["iteration"] == int(solver.getIterationNumber())
        assert persisted == audit_records[-1]["true_residual_samples"]

        sampled_solution = matrix.createVecRight()
        try:
            sampled_solution.getArray()[:] = first_samples[0]["solution"]
            sampled_solution.assemble()
            sampled_residual = matrix.createVecLeft()
            try:
                matrix.mult(sampled_solution, sampled_residual)
                sampled_residual.axpy(PETSc.ScalarType(-1.0), rhs)
                assert sampled_residual.norm() == pytest.approx(
                    first_samples[0]["true_residual_norm"], rel=1.0e-12
                )
            finally:
                sampled_residual.destroy()
        finally:
            sampled_solution.destroy()
    finally:
        inverse._operator = fixture_operator
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
        inverse.destroy()
        fixture_operator.destroy()


def test_side_inverse_diagnostic_callback_failure_destroys_borrowed_vecs():
    class TrackedVec:
        def __init__(self, vector):
            self.vector = vector
            self.destroyed = False

        def destroy(self):
            self.destroyed = True
            self.vector.destroy()

    tracked: list[TrackedVec] = []

    def fail_after_transfer(record):
        if record["event"] == "PH_Q_output":
            raise RuntimeError("injected diagnostic callback failure")
        return False

    p4_factor = _CellCondensedP4(2)
    inverse, owned = _build_fixture(
        p4_factor=p4_factor,
        p4_inverse_backend="cell_condensed",
        diagnostic_callback=fail_after_transfer,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    transfer = owned["transfer"]
    original_apply_adjoint = transfer.apply_adjoint

    def tracked_apply_adjoint(vector, *, timing=None):
        borrowed = TrackedVec(original_apply_adjoint(vector, timing=timing))
        tracked.append(borrowed)
        return borrowed

    transfer.apply_adjoint = tracked_apply_adjoint
    try:
        with pytest.raises(RuntimeError, match="diagnostic callback failure"):
            inverse._apply_q_callback(source)
        assert len(tracked) == 1
        assert tracked[0].destroyed is True
        assert p4_factor.apply_count == 0
    finally:
        source.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_real_q_handoff_survives_and_cleans_finally_tail_error(
    monkeypatch,
):
    class TrackedVec:
        def __init__(self, vector):
            self.vector = vector
            self.destroy_count = 0

        def destroy(self):
            self.destroy_count += 1
            if self.destroy_count == 1:
                self.vector.destroy()

        def __getattr__(self, name):
            return getattr(self.vector, name)

    default_inverse, default_owned = _build_fixture(
        p4_factor=_CellCondensedP4(2),
        p4_inverse_backend="cell_condensed",
    )
    default_operator = default_owned["operator"]
    default_source = _new_vector(
        default_operator, np.asarray([0.75 + 0.25j, -0.5 + 0.875j])
    )
    default_result = None
    try:
        assert default_inverse._reuse_leading_ph_dual is False
        default_result = default_inverse._apply_q_callback(default_source)
        assert not isinstance(default_result, tuple)
    finally:
        if default_result is not None:
            default_result.destroy()
        default_source.destroy()
        default_inverse.destroy()
        default_operator.destroy()

    factor = _CellCondensedP4(2)
    inverse, owned = _build_fixture(
        p4_factor=factor,
        p4_inverse_backend="cell_condensed",
        detailed_timing=True,
        reuse_leading_ph_dual=True,
    )
    operator = owned["operator"]
    transfer = owned["transfer"]
    source = _new_vector(
        operator, np.asarray([1.0 + 0.5j, -0.25 + 0.75j])
    )
    source_before = _gather_dense_vector(source)
    leading_duals: list[TrackedVec] = []
    coarse_outputs: list[TrackedVec] = []
    p4_work_vectors: list[TrackedVec] = []
    p4_inputs: list[object] = []
    p4_input_values: list[tuple[np.ndarray, np.ndarray]] = []

    for method_name, tracked in (
        ("apply_adjoint", leading_duals),
        ("apply_primal", coarse_outputs),
    ):
        original_method = getattr(transfer, method_name)

        def track_transfer_result(
            vector, *, timing=None, _original=original_method, _tracked=tracked
        ):
            result = _original(vector, timing=timing)
            wrapped = TrackedVec(result)
            _tracked.append(wrapped)
            return wrapped

        setattr(transfer, method_name, track_transfer_result)

    original_p4_apply = factor.apply

    def track_p4_input(vector, **kwargs):
        before = _gather_dense_vector(vector)
        p4_inputs.append(vector)
        result = original_p4_apply(vector, **kwargs)
        after = _gather_dense_vector(vector)
        p4_input_values.append((before, after))
        wrapped = TrackedVec(result)
        p4_work_vectors.append(wrapped)
        return wrapped

    monkeypatch.setattr(factor, "apply", track_p4_input)
    original_record_timing = inverse._add_rhs_detail_seconds
    tail_failure = {"raised": False, "live_at_raise": None}

    # q_factor_solve_seconds is recorded by the real implementation's outer
    # finally, after P returned and the local handoff state holds both outputs.
    def fail_at_real_q_finally(name, elapsed):
        original_record_timing(name, elapsed)
        if name == "q_factor_solve_seconds" and not tail_failure["raised"]:
            tail_failure["raised"] = True
            tail_failure["live_at_raise"] = (
                leading_duals[-1].destroy_count,
                coarse_outputs[-1].destroy_count,
                p4_work_vectors[-1].destroy_count,
            )
            raise RuntimeError("injected Q finally timing failure")

    monkeypatch.setattr(inverse, "_add_rhs_detail_seconds", fail_at_real_q_finally)
    returned_vectors: list[TrackedVec] = []
    try:
        assert inverse._reuse_leading_ph_dual is True
        with pytest.raises(RuntimeError, match="Q finally timing failure"):
            inverse._apply_q_callback(source, return_leading_dual=True)

        assert tail_failure["raised"] is True
        assert tail_failure["live_at_raise"] == (0, 0, 1)
        assert len(leading_duals) == len(coarse_outputs) == len(p4_work_vectors) == 1
        assert p4_inputs[0] is leading_duals[0]
        assert p4_work_vectors[0].destroy_count == 1
        assert leading_duals[0].destroy_count == 1
        assert coarse_outputs[0].destroy_count == 1
        np.testing.assert_array_equal(p4_input_values[0][0], p4_input_values[0][1])
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)

        pair = inverse._apply_q_callback(source, return_leading_dual=True)
        assert isinstance(pair, tuple) and len(pair) == 2
        returned_vectors.extend(pair)
        assert pair[0] is coarse_outputs[1]
        assert pair[1] is leading_duals[1]
        assert p4_inputs[1] is leading_duals[1]
        assert p4_work_vectors[1].destroy_count == 1
        assert all(vector.destroy_count == 0 for vector in pair)
        assert pair[0].norm() > 0.0 and pair[1].norm() > 0.0
        np.testing.assert_array_equal(p4_input_values[1][0], p4_input_values[1][1])

        second_q = inverse._apply_q_callback(source)
        assert not isinstance(second_q, tuple)
        returned_vectors.append(second_q)
        assert second_q is coarse_outputs[2]
        assert leading_duals[2].destroy_count == 1
        assert p4_inputs[2] is leading_duals[2]
        assert p4_work_vectors[2].destroy_count == 1
        assert second_q.norm() > 0.0
        assert transfer.primal_apply_count == 3
        np.testing.assert_array_equal(p4_input_values[2][0], p4_input_values[2][1])
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
    finally:
        for vector in returned_vectors:
            if vector.destroy_count == 0:
                vector.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


@pytest.mark.parametrize("failure_event", ["full_action_ready", "adapter_ksp_ready"])
def test_side_inverse_builder_callback_failure_cleans_owned_only(
    monkeypatch, failure_event
):
    captured = {}
    side_system, operator, operator_context, b = _builder_side_system()
    b_before = np.asarray(b.getArray(readonly=True)).copy()
    _install_stub_side_builders(monkeypatch, captured)

    def failing_callback(event, _detail):
        if event == failure_event:
            raise RuntimeError(f"injected {failure_event}")

    try:
        with pytest.raises(RuntimeError, match=failure_event):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                lifecycle_callback=failing_callback,
            )
        _assert_borrowed_stub_system_works(
            operator, operator_context, b, b_before
        )
        assert captured["full_action"].destroy_count == 1
        if failure_event == "full_action_ready":
            assert "p4" not in captured
            assert "transfer" not in captured
            assert "h6" not in captured
        else:
            assert captured["p4"].destroy_count == 1
            assert captured["transfer"].destroy_count == 1
            assert captured["h6"].destroy_count == 1
    finally:
        b.destroy()
        operator.destroy()


def test_side_inverse_variant_context_rejects_switch_during_apply_and_restores():
    inverse, owned = _build_fixture()
    operator = owned["operator"]
    operator_context = owned["operator_context"]
    transfer = owned["transfer"]
    factor = owned["p4_factor"]
    ksp = inverse._ksp
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    target = operator.createVecLeft()
    output = operator.createVecLeft()
    factor_solves = factor.solve_count

    def switch_during_apply() -> None:
        with inverse.variant_context("optimized"):
            pass

    transfer.on_apply = switch_during_apply
    try:
        assert inverse._ksp.getInitialGuessNonzero() is False
        with pytest.raises(RuntimeError, match="cannot change during apply"):
            inverse.apply(source, target)
        assert inverse._variant_context_active is False
        assert inverse._active_variant is None
        assert transfer.execution_variant == "legacy"
        assert inverse.diagnostics["last_apply"]["execution_variant"] == "legacy"

        with pytest.raises(RuntimeError, match="sentinel variant failure"), inverse.variant_context(
            "optimized"
        ):
            assert transfer.execution_variant == "optimized"
            raise RuntimeError("sentinel variant failure")
        assert inverse._variant_context_active is False
        assert inverse._active_variant is None
        assert transfer.execution_variant == "legacy"

        transfer.on_apply = None
        source_before = np.asarray(
            source.getArray(readonly=True), dtype=np.complex128
        ).copy()
        for variant in ("legacy", "optimized", "legacy"):
            target.set(PETSc.ScalarType(3.0 - 0.5j))
            with inverse.variant_context(variant):
                assert inverse._ksp.getInitialGuessNonzero() is False
                inverse.apply(source, target)
                last_apply = inverse.diagnostics["last_apply"]
                assert last_apply["execution_variant"] == variant
                assert last_apply["explicit_true_target_reached"] is True
                assert last_apply["relative_residual"] <= inverse._rtol
            assert transfer.execution_variant == "legacy"
            assert inverse._active_variant is None
            np.testing.assert_allclose(
                target.getArray(readonly=True),
                0.5 * source.getArray(readonly=True),
                atol=1.0e-12,
                rtol=1.0e-12,
            )
            np.testing.assert_array_equal(
                source.getArray(readonly=True), source_before
            )

        assert inverse._p4_factor is factor
        assert inverse._ksp is ksp
        assert factor.solve_count > factor_solves
        assert inverse.diagnostics["p4_factor_created_count"] == 1
        assert inverse.diagnostics["nested_ksp_created_count"] == 1
        assert transfer.destroy_count == 0
        assert operator_context.destroyed is False
        inverse.destroy()
        operator.mult(source, output)
        np.testing.assert_allclose(
            output.getArray(readonly=True),
            2.0 * source.getArray(readonly=True),
        )
        assert operator_context.destroyed is False
        assert inverse.diagnostics["last_apply"]["execution_variant"] == "legacy"
    finally:
        output.destroy()
        target.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_live_ksp_contract_and_bounded_history():
    inverse, owned = _build_fixture(record_iteration_history=True)
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    target = operator.createVecLeft()
    try:
        contract = inverse._ksp_contract_audit()
        assert contract["pass"] is True
        assert contract["actual"]["restart"] == 32
        inverse._ksp.setGMRESRestart(17)
        try:
            changed_contract = inverse._ksp_contract_audit()
            assert changed_contract["actual"]["restart"] == 17
        finally:
            inverse._ksp.setGMRESRestart(32)
        restored_contract = inverse._ksp_contract_audit()
        assert restored_contract["actual"]["restart"] == 32
        assert contract["actual"]["pc_side"] == int(PETSc.PC.Side.RIGHT)
        assert contract["actual"]["norm_type"] == int(
            PETSc.KSP.NormType.UNPRECONDITIONED
        )
        assert contract["actual"]["initial_guess_nonzero"] is False

        inverse.apply(source, target)
        audit = inverse.diagnostics["last_apply"]
        assert audit["ksp_contract"]["collective_pass"] is True
        assert audit["ksp_contract"]["actual"]["pc_side"] == int(
            PETSc.PC.Side.RIGHT
        )
        assert audit["ksp_contract"]["actual"]["norm_type"] == int(
            PETSc.KSP.NormType.UNPRECONDITIONED
        )
        assert audit["ksp_contract"]["actual"]["initial_guess_nonzero"] is False
        history = audit["iteration_history"]
        assert isinstance(history, list)
        assert history
        assert all(
            isinstance(item.get("reported_residual"), (int, float))
            and np.isfinite(item["reported_residual"])
            for item in history
        )
        assert len(history) <= 129
        assert audit["iterations"] <= 128

        first_history_length = len(history)
        inverse.apply(source, target)
        second_audit = inverse.diagnostics["last_apply"]
        second_history = second_audit["iteration_history"]
        assert second_history
        assert len(second_history) == first_history_length
        assert second_history[0]["iteration"] == 0
        assert all(
            isinstance(item.get("reported_residual"), (int, float))
            and np.isfinite(item["reported_residual"])
            for item in second_history
        )
        assert len(second_history) <= 129
    finally:
        target.destroy()
        source.destroy()
        inverse.destroy()
        operator.destroy()


@pytest.mark.parametrize("detailed_timing", [False, True])
def test_side_inverse_right_pc_reuse_zero_and_cleanup(
    detailed_timing: bool,
) -> None:
    checkpoint_calls: list[None] = []
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        checkpoint_callback=lambda: checkpoint_calls.append(None),
        audit_callback=audit_records.append,
        detailed_timing=detailed_timing,
    )
    operator = owned["operator"]
    q1 = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    q2 = _new_vector(operator, np.asarray([0.3 - 0.5j, 0.8 + 0.1j]))
    q1_before = q1.copy()
    q2_before = q2.copy()
    y1 = operator.createVecLeft()
    y2 = operator.createVecLeft()
    y3 = operator.createVecLeft()
    zero = operator.createVecRight()
    zero.set(0.0)
    zero_out = operator.createVecLeft()
    bad = operator.createVecRight()
    bad.set(PETSc.ScalarType(np.nan))
    bad_out = operator.createVecLeft()
    expected: PETSc.Vec | None = None
    expected2: PETSc.Vec | None = None
    try:
        inverse.apply(q1, y1)
        inverse.apply(q2, y2)
        inverse.apply(q1, y3)
        with pytest.raises(RuntimeError, match="RHS norm is non-finite"):
            inverse.apply(bad, bad_out)
        failed = inverse.diagnostics["last_apply"]
        assert failed["status"] == "FAILED"
        assert failed["reason"] is None
        assert failed["iterations"] == 0
        assert failed["residual_norm"] == "not_measured"
        assert audit_records[-1]["status"] == "FAILED"
        inverse.apply(zero, zero_out)
        with pytest.raises(ValueError, match="source/target aliasing"):
            inverse.apply(q1, q1)
        expected = q1.copy()
        expected.scale(0.5)
        expected2 = q2.copy()
        expected2.scale(0.5)
        assert _relative_difference(y1, expected) <= 1.0e-12
        assert _relative_difference(y2, expected2) <= 1.0e-12
        assert _relative_difference(y3, y1) <= 1.0e-12
        assert _relative_difference(q1, q1_before) == 0.0
        assert _relative_difference(q2, q2_before) == 0.0
        assert zero_out.norm() == 0.0
        assert len(audit_records) == 5
        successful = audit_records[:3]
        assert len({record["iterations"] for record in successful}) == 1
        assert len(
            {
                record["counts"]["delta"]["checkpoint"]
                for record in successful
            }
        ) == 1
        assert len(checkpoint_calls) > 0
        last = inverse.diagnostics["last_apply"]
        assert last["status"] == "ZERO_RHS_EXACT"
        assert last["explicit_true_target_reached"] is True
        if detailed_timing:
            zero_timing = last["operation_seconds"]
            assert zero_timing["status"] == "measured_rank_max"
            assert all(
                value == "not_called"
                for value in zero_timing["detailed"]["measurement_status"].values()
            )
            assert all(
                value is None
                for value in zero_timing["detailed"]["max_rank_seconds"].values()
            )
        else:
            assert inverse.diagnostics["detailed_timing"] is False
            assert "detailed" not in last["operation_seconds"]
        diagnostics = inverse.diagnostics
        assert diagnostics["apply_count"] == 5
        assert diagnostics["p4_factor_count"] == 1
        assert inverse.diagnostics["p6_factor_count"] == 0
        assert inverse.diagnostics["nested_iterative_ksp_count"] == 1
        assert inverse.diagnostics["nested_ksp_created_count"] == 1
        assert diagnostics["research_only"] is True
        assert inverse.diagnostics["last_apply"]["reason"] is None
        assert diagnostics["counts"]["JH"] == diagnostics["counts"]["pc"]
        assert diagnostics["counts"]["PH_audit"] == 2 * diagnostics["counts"]["pc"]
        assert diagnostics["counts"]["p4_backsolve"] == diagnostics["counts"]["Q"]
    finally:
        if expected is not None:
            expected.destroy()
        if expected2 is not None:
            expected2.destroy()
        q1_before.destroy()
        q2_before.destroy()
        q1.destroy()
        q2.destroy()
        y1.destroy()
        y2.destroy()
        y3.destroy()
        zero.destroy()
        zero_out.destroy()
        bad.destroy()
        bad_out.destroy()
        inverse.destroy()
        after_destroy = inverse.diagnostics
        assert after_destroy["p4_factor_live"] == 0
        assert after_destroy["p4_factor_created_count"] == 1
        assert after_destroy["p4_factor_destroy_count"] == 1
        assert after_destroy["direct_factor_count"] == 0
        assert after_destroy["nested_iterative_ksp_count"] == 0
        assert after_destroy["nested_ksp_created_count"] == 1
        assert after_destroy["nested_ksp_destroy_count"] == 1
        assert after_destroy["nested_ksp_current_live"] is False
        assert after_destroy["p4_factor"]["factor_destroy_count"] == 1
        assert after_destroy["p4_factor"]["research_factor"]["direct_factor_count"] == 0
        assert after_destroy["p4_factor"]["research_factor"]["factor_destroyed"] is True
        assert owned["full_action"].destroy_count == 1
        assert owned["p4_factor"].destroy_count == 1
        assert owned["transfer"].destroy_count == 1
        assert owned["h6"].destroy_count == 1
        assert operator.getSize() == (2, 2)
        operator.destroy()


def test_side_inverse_dense_batch_bound_and_true_error_propagation() -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        detailed_timing=True,
    )
    operator = owned["operator"]
    comm = MPI.COMM_WORLD
    width = 3
    source_dense = PETSc.Mat().createDense(
        size=((operator.getOwnershipRange()[1] - operator.getOwnershipRange()[0], 2), width),
        comm=comm,
    )
    target_dense = source_dense.duplicate(copy=False)
    source_values = np.asarray(
        [
            [1.0 + 0.1j, 0.2 - 0.3j, -0.5 + 0.7j],
            [0.4 + 0.6j, -0.8 + 0.2j, 0.9 - 0.1j],
        ],
        dtype=np.complex128,
    )
    first, last = (int(value) for value in source_dense.getOwnershipRange())
    source_dense.getDenseArray()[:, :] = source_values[first:last, :]
    source_dense.assemble()
    original_dense = np.array(source_dense.getDenseArray(), copy=True)
    target_dense.zeroEntries()
    target_dense.assemble()
    try:
        inverse.apply_many(source_dense, target_dense)
        assert np.max(
            np.abs(target_dense.getDenseArray() - 0.5 * original_dense)
        ) <= 1.0e-12
        assert np.array_equal(source_dense.getDenseArray(), original_dense)
        too_wide = PETSc.Mat().createDense(
            size=((last - first, 2), 33),
            comm=comm,
        )
        too_wide.setUp()
        with pytest.raises(ValueError, match="batch aliasing"):
            inverse.apply_many(too_wide, too_wide)
        too_wide_target = too_wide.duplicate(copy=False)
        too_wide_target.zeroEntries()
        too_wide_target.assemble()
        with pytest.raises(ValueError, match="one to 32"):
            inverse.apply_many(too_wide, too_wide_target)
        too_wide_target.destroy()
        too_wide.destroy()

        old_h6 = inverse._h6
        inverse._h6 = _FailingH6()
        source = _new_vector(operator, np.asarray([1.0 + 0.2j, 0.4 - 0.1j]))
        source_before = source.copy()
        target = operator.createVecLeft()
        healthy_target = None
        try:
            with pytest.raises(RuntimeError, match="focused H1e H6 failure"):
                inverse.apply(source, target)
            failed = inverse.diagnostics["last_apply"]
            assert failed["status"] == "FAILED"
            assert failed["exception_type"] == "RuntimeError"
            assert failed["exception"] == "focused H1e H6 failure"
            assert int(failed["reason"]) < 0
            assert failed["residual_norm"] == "not_measured"
            assert inverse._pending_pc_exception is None
            failed_timing = failed["operation_seconds"]["detailed"]
            assert failed_timing["measurement_status"]["q_ph_seconds"] == "measured"
            assert failed_timing["per_rank_seconds"]["q_ph_seconds"] > 0.0
            assert failed_timing["max_rank_seconds"] is None
            for name in (
                "q_ph_route_sort_index_seconds",
                "q_ph_duplicate_row_check_seconds",
                "balance_ph_route_sort_index_seconds",
                "balance_ph_duplicate_row_check_seconds",
            ):
                assert failed_timing["measurement_status"][name] == "not_called"
                assert failed_timing["per_rank_seconds"][name] is None
            assert (
                failed_timing["measurement_status"]["balance_h6_seconds"]
                == "measured"
            )
            assert audit_records[-1]["status"] == "FAILED"
            inverse._h6 = old_h6
            healthy_target = operator.createVecLeft()
            inverse.apply(source, healthy_target)
            healthy = inverse.diagnostics["last_apply"]
            assert healthy["status"] == "KSP_CONVERGED"
            assert int(healthy["reason"]) > 0
            assert healthy["explicit_true_target_reached"] is True
            assert inverse._pending_pc_exception is None
            np.testing.assert_array_equal(
                source.getArray(readonly=True),
                source_before.getArray(readonly=True),
            )
        finally:
            source.destroy()
            source_before.destroy()
            target.destroy()
            if healthy_target is not None:
                healthy_target.destroy()
            inverse._h6 = old_h6
    finally:
        source_dense.destroy()
        target_dense.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_rank_local_pc_failure_is_collective_and_reusable() -> None:
    comm = MPI.COMM_WORLD
    if comm.Get_size() != 2:
        pytest.skip("rank-local PC failure contract is an MPI2 check")
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        detailed_timing=True,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, 0.4 - 0.1j]))
    source_before = source.copy()
    target = operator.createVecLeft()
    original_apply_balanced_pc = inverse._apply_balanced_pc

    def fail_after_collective(
        callback_source: PETSc.Vec,
        callback_target: PETSc.Vec,
    ) -> None:
        original_apply_balanced_pc(callback_source, callback_target)
        if comm.Get_rank() == 0:
            raise RuntimeError("rank-local PC boundary failure")

    inverse._apply_balanced_pc = fail_after_collective  # type: ignore[method-assign]
    healthy_target = None
    caught = None
    try:
        try:
            inverse.apply(source, target)
        except BaseException as exc:  # noqa: BLE001 - collect every rank's failure
            caught = exc
        local_failed = caught is not None
        assert comm.allreduce(local_failed, op=MPI.LAND)
        failed = inverse.diagnostics["last_apply"]
        failed_reasons = comm.allgather(int(failed["reason"]))
        failed_statuses = comm.allgather(str(failed["status"]))
        assert all(reason < 0 for reason in failed_reasons)
        assert all(status == "FAILED" for status in failed_statuses)
        assert comm.allreduce(
            inverse._pending_pc_exception is None,
            op=MPI.LAND,
        )
        exception_records = comm.allgather(
            {
                "type": type(caught).__name__ if caught is not None else None,
                "message": str(caught) if caught is not None else None,
            }
        )
        assert exception_records[0] == {
            "type": "RuntimeError",
            "message": "rank-local PC boundary failure",
        }
        assert exception_records[1]["type"] == "RuntimeError"
        assert exception_records[1]["message"] != "rank-local PC boundary failure"
        assert failed["exception_type"] == exception_records[comm.Get_rank()]["type"]
        assert failed["exception"] == exception_records[comm.Get_rank()]["message"]
        assert failed["operation_seconds"]["detailed"]
        inverse._apply_balanced_pc = original_apply_balanced_pc  # type: ignore[method-assign]
        healthy_target = operator.createVecLeft()
        inverse.apply(source, healthy_target)
        healthy = inverse.diagnostics["last_apply"]
        healthy_statuses = comm.allgather(str(healthy["status"]))
        healthy_reasons = comm.allgather(int(healthy["reason"]))
        healthy_targets = comm.allgather(
            bool(healthy["explicit_true_target_reached"])
        )
        assert all(status == "KSP_CONVERGED" for status in healthy_statuses)
        assert all(reason > 0 for reason in healthy_reasons)
        assert all(healthy_targets)
        assert inverse._pending_pc_exception is None
        np.testing.assert_array_equal(
            source.getArray(readonly=True),
            source_before.getArray(readonly=True),
        )
    finally:
        inverse._apply_balanced_pc = original_apply_balanced_pc  # type: ignore[method-assign]
        source.destroy()
        source_before.destroy()
        target.destroy()
        if healthy_target is not None:
            healthy_target.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_rhs_timing_uses_one_buffer_for_multiple_pc_calls() -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        detailed_timing=True,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    target = operator.createVecLeft()
    coupling = inverse._coupling
    assert coupling is not None
    real_coupling_apply = coupling.apply
    operation_facts: list[dict[str, float]] = []

    def spy_coupling_apply(value: PETSc.Vec) -> PETSc.Vec:
        result = real_coupling_apply(value)
        operation_facts.append(
            dict(coupling.last_apply_facts["operation_seconds"])
        )
        return result

    coupling.apply = spy_coupling_apply  # type: ignore[method-assign]
    real_ksp = inverse._ksp
    real_pc = real_ksp.getPC()
    real_comm = inverse._comm
    recording_comm = _BufferRecordingComm(real_comm)
    inverse._ksp = _RepeatedPcKsp(inverse, real_pc)  # type: ignore[assignment]
    inverse._comm = recording_comm  # type: ignore[assignment]
    try:
        unmeasured = inverse._rhs_operation_timing(0.0, reduce=False)
        assert all(
            value is None
            for value in unmeasured["detailed"]["per_rank_seconds"].values()
        )
        assert all(
            status == "not_called"
            for status in unmeasured["detailed"]["measurement_status"].values()
        )
        inverse.apply(source, target)
        first_record = inverse.diagnostics["last_apply"]
        first_timing = first_record["operation_seconds"]
        assert first_record["status"] == "KSP_CONVERGED"
        assert first_record["counts"]["delta"]["pc"] == 2
        assert first_record["counts"]["delta"]["Q"] == 4
        assert first_record["counts"]["delta"]["H6"] == 2
        assert first_record["counts"]["delta"]["A6"] == 4
        assert owned["p4_factor"].solve_count == 4
        assert owned["h6"].apply_count == 2
        assert owned["full_action"].context.apply_count == 4
        assert owned["operator_context"].apply_count == 1
        assert recording_comm.scalar_allreduce_count == 1
        assert recording_comm.buffer_allreduce_count == 1
        assert first_timing["status"] == "measured_rank_max"
        assert set(first_timing["max_rank_accumulated_seconds"]) == {
            "Q",
            "H6",
            "A6",
        }
        assert "max_rank_total_seconds" not in first_timing
        assert first_timing["max_rank_uncovered_seconds"] >= 0.0
        first_operation_facts = operation_facts[:]
        assert len(first_operation_facts) == 2
        first_detail = first_timing["detailed"]
        assert first_detail["logging_rank"] == MPI.COMM_WORLD.Get_rank()
        assert first_detail["local_scope"] == "logging_rank_only"
        measured_names = (
            "q_ph_seconds",
            "q_ph_cell_adjoint_seconds",
            "q_ph_dual_reduce_seconds",
            "q_ph_mpi_exchange_seconds",
            "q_ph_ghost_mpc_prepare_seconds",
            "q_ph_ghost_mpc_check_seconds",
            "q_p_seconds",
            "q_p_local_candidate_generation_seconds",
            "q_p_route_sort_index_seconds",
            "q_p_mpi_exchange_seconds",
            "q_p_duplicate_row_check_seconds",
            "q_p_ghost_mpc_prepare_seconds",
            "q_p_ghost_mpc_check_seconds",
            "q_augmented_rhs_extract_seconds",
            "q_factor_solve_seconds",
            "q_a4_residual_refinement_seconds",
            "q_physical_action_matrix_mult_seconds",
            "balance_ph_seconds",
            "balance_ph_cell_adjoint_seconds",
            "balance_ph_dual_reduce_seconds",
            "balance_ph_mpi_exchange_seconds",
            "balance_ph_ghost_mpc_prepare_seconds",
            "balance_ph_ghost_mpc_check_seconds",
            "balance_a6_seconds",
            "balance_h6_seconds",
            "balance_jh_inject_allocate_seconds",
        )
        assert all(
            first_detail["measurement_status"][name] == "measured"
            for name in measured_names
        )
        not_called_names = (
            "q_ph_route_sort_index_seconds",
            "q_ph_duplicate_row_check_seconds",
            "balance_ph_route_sort_index_seconds",
            "balance_ph_duplicate_row_check_seconds",
        )
        assert all(
            first_detail["measurement_status"][name] == "not_called"
            and first_detail["max_rank_seconds"][name] is None
            for name in not_called_names
        )
        assert first_detail["max_rank_seconds"]["q_factor_solve_seconds"] == pytest.approx(
            4.0e-3
        )
        assert first_detail["max_rank_seconds"][
            "q_a4_residual_refinement_seconds"
        ] == pytest.approx(8.0e-3)
        assert first_detail["max_rank_seconds"][
            "q_physical_action_matrix_mult_seconds"
        ] == pytest.approx(1.2e-3)
        assert first_detail["max_rank_seconds"][
            "q_ph_mpi_exchange_seconds"
        ] == pytest.approx(1.6e-3)
        assert first_detail["max_rank_seconds"][
            "q_p_local_candidate_generation_seconds"
        ] == pytest.approx(4.0e-4)
        assert first_detail["max_rank_seconds"][
            "balance_ph_mpi_exchange_seconds"
        ] == pytest.approx(1.6e-3)
        assert first_detail["max_rank_seconds"][
            "balance_jh_inject_allocate_seconds"
        ] >= 0.0
        for name in ("Q", "H6", "A6"):
            assert first_timing["per_rank_accumulated_seconds"][name] == pytest.approx(
                sum(facts[name] for facts in operation_facts),
                rel=1.0e-12,
                abs=1.0e-12,
            )
        inverse.apply(source, target)
        second_record = inverse.diagnostics["last_apply"]
        second_timing = second_record["operation_seconds"]
        assert second_record["counts"]["delta"]["pc"] == 2
        assert second_record["counts"]["delta"]["Q"] == 4
        assert second_timing["detailed"]["max_rank_seconds"][
            "q_factor_solve_seconds"
        ] == pytest.approx(4.0e-3)
        assert second_timing["detailed"]["max_rank_seconds"][
            "q_a4_residual_refinement_seconds"
        ] == pytest.approx(8.0e-3)
        assert recording_comm.scalar_allreduce_count == 2
        assert recording_comm.buffer_allreduce_count == 2
        assert len(operation_facts) == 4
        for timing, facts in (
            (first_timing, first_operation_facts),
            (second_timing, operation_facts[2:]),
        ):
            for name in ("Q", "H6", "A6"):
                assert timing["per_rank_accumulated_seconds"][name] == pytest.approx(
                    sum(item[name] for item in facts),
                    rel=1.0e-12,
                    abs=1.0e-12,
                )
        assert owned["p4_factor"].solve_count == 8
        assert owned["h6"].apply_count == 4
        assert owned["full_action"].context.apply_count == 8
        assert owned["operator_context"].apply_count == 2
        assert len(audit_records) == 2
    finally:
        coupling.apply = real_coupling_apply  # type: ignore[method-assign]
        inverse._ksp = real_ksp
        inverse._comm = real_comm
        source.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_preserves_current_nonfinite_p4_gate_audit() -> None:
    audit_records: list[dict[str, object]] = []
    failing_p4 = _NonfiniteP4(2)
    inverse, owned = _build_fixture(
        p4_factor=failing_p4,
        audit_callback=audit_records.append,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    source_before = source.copy()
    target = operator.createVecLeft()
    try:
        with pytest.raises((RuntimeError, PETSc.Error)):
            inverse.apply(source, target)
        record = inverse.diagnostics["last_apply"]
        assert record["status"] == "FAILED"
        assert record["failure_classification"] == "P4_PHYSICAL_RESIDUAL_GATE"
        assert record["relative_residual"] == "not_measured"
        assert record["p4_solve_audit"]["status"] == "failed_nonfinite_residual"
        assert np.isnan(record["p4_solve_audit"]["relative_residual"])
        assert record["p4_solve_audit"]["backsolve_count"] == 1
        assert _relative_difference(source, source_before) == 0.0
        assert audit_records[-1]["p4_solve_audit"]["rhs_norm"] > 0.0
    finally:
        source.destroy()
        source_before.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()


def test_p4_physical_gate_audit_uses_each_real_vec_rhs() -> None:
    physical_matrix, physical_context = _scale_matrix(2, 2.0)
    augmented_matrix, _augmented_context = _scale_matrix(2, 1.0)
    physical_action = _PhysicalP4Action(physical_matrix)
    factor = _RefinementFactor()
    p4 = P4ExactFactor(
        physical_action=physical_action,
        matrix=augmented_matrix,
        factor=factor,
        factor_events=["created"],
    )
    rhs1 = _new_vector(physical_matrix, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    augmented_rhs1 = p4.create_rhs(rhs1)
    solution1 = augmented_rhs1.duplicate()
    solution1.set(0.0)
    rhs2 = _new_vector(physical_matrix, np.asarray([2.0 - 0.1j, 0.25 + 0.5j]))
    augmented_rhs2 = p4.create_rhs(rhs2)
    solution2 = augmented_rhs2.duplicate()
    solution2.set(0.0)
    rhs3 = _new_vector(physical_matrix, np.asarray([-0.3 + 0.6j, 0.9 - 0.2j]))
    augmented_rhs3 = p4.create_rhs(rhs3)
    solution3 = augmented_rhs3.duplicate()
    solution3.set(0.0)
    try:
        with pytest.raises(P4PhysicalResidualGateError) as first_failure:
            p4.solve_with_refinement(augmented_rhs1, solution1)
        first_audit = first_failure.value.audit
        assert first_audit["status"] == "failed_gate"
        assert first_audit["residual_norm"] == pytest.approx(rhs1.norm())
        assert first_audit["relative_residual"] == pytest.approx(1.0)
        assert first_audit["backsolve_count"] == 3
        assert first_audit["refinement_count"] == 2

        second_audit = p4.solve_with_refinement(augmented_rhs2, solution2)
        assert second_audit["status"] == "passed"
        assert second_audit["rhs_norm"] == pytest.approx(rhs2.norm())
        assert second_audit["rhs_norm"] != first_audit["rhs_norm"]
        assert second_audit["backsolve_count"] == 1
        assert second_audit["refinement_count"] == 0

        physical_context.scale = PETSc.ScalarType(np.nan)
        with pytest.raises(P4PhysicalResidualGateError) as nonfinite_failure:
            p4.solve_with_refinement(augmented_rhs3, solution3)
        nonfinite_audit = nonfinite_failure.value.audit
        assert nonfinite_audit["status"] == "failed_nonfinite_residual"
        assert np.isnan(nonfinite_audit["relative_residual"])
        assert nonfinite_audit["backsolve_count"] == 1
        assert nonfinite_audit["refinement_count"] == 0
        assert factor.solve_count == 5
        last_audit = p4.diagnostics["last_solve"]
        assert last_audit["status"] == "failed_nonfinite_residual"
        assert last_audit["backsolve_count"] == 1
    finally:
        rhs1.destroy()
        augmented_rhs1.destroy()
        solution1.destroy()
        rhs2.destroy()
        augmented_rhs2.destroy()
        solution2.destroy()
        rhs3.destroy()
        augmented_rhs3.destroy()
        solution3.destroy()
        p4.destroy()


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
@pytest.mark.parametrize("correction_steps", [0, 1, 2])
def test_p4_opt_in_corrections_match_nonhermitian_augmented_block(
    backend: str,
    correction_steps: int,
) -> None:
    fixture = _g2a_p4_fixture(
        backend=backend,
        perturb_initial_port=correction_steps > 0,
    )
    p4 = fixture["p4"]
    rhs = fixture["rhs"]
    rhs_before = _gather_dense_vector(rhs)
    port_rhs = fixture["port_rhs"]
    port_rhs_before = port_rhs.copy()
    events: list[dict[str, object]] = []
    block = fixture["block"]
    block_rhs = fixture["block_rhs"]
    assert not np.allclose(block, block.conj().T)
    assert np.any(port_rhs != 0.0)

    def observe(record, borrowed) -> None:
        if backend == "full":
            block_solution = _gather_dense_vector(borrowed["solution"])
        else:
            fe_solution = _gather_dense_vector(borrowed["solution"])
            block_solution = np.concatenate(
                (fe_solution, np.asarray(borrowed["port_solution"]))
            )
        block_residual = block_rhs - block @ block_solution
        event = {
            "record": dict(record),
            "fe_residual": _gather_dense_vector(borrowed["fe_residual"]),
            "port_residual": np.array(
                borrowed["port_residual"], dtype=np.complex128, copy=True
            ),
            "port_solution": np.array(
                borrowed["port_solution"], dtype=np.complex128, copy=True
            ),
            "port_correction": (
                None
                if borrowed.get("port_correction") is None
                else np.array(
                    borrowed["port_correction"], dtype=np.complex128, copy=True
                )
            ),
            "block_residual": block_residual,
            "block_norm": float(np.linalg.norm(block_residual)),
        }
        if backend == "full":
            event["effective_physical_residual"] = _gather_dense_vector(
                borrowed["effective_physical_residual"]
            )
        events.append(event)

    result = None
    try:
        if backend == "full":
            audit = p4.solve_with_refinement(
                rhs,
                fixture["solution"],
                residual_tolerance=1.0e-12,
                diagnostic_correction_steps=correction_steps,
                diagnostic_callback=observe,
            )
            block_solution = _gather_dense_vector(fixture["solution"])
            solve_count = fixture["inverse"].solve_count
        else:
            result = p4.apply(
                rhs,
                port_rhs=port_rhs,
                diagnostic_correction_steps=correction_steps,
                diagnostic_callback=observe,
            )
            block_solution = np.concatenate(
                (_gather_dense_vector(result), p4.last_port_solution)
            )
            audit = p4.diagnostics["last_solve"]
            solve_count = fixture["inverse"].solve_count

        assert np.allclose(
            block_solution,
            fixture["exact_solution"],
            rtol=0.0,
            atol=1.0e-11,
        )
        assert solve_count == correction_steps + 1
        assert fixture["physical_context"].apply_count == correction_steps + 1
        assert len(events) == correction_steps + 1
        assert MPI.COMM_WORLD.allgather(len(events)) == [
            correction_steps + 1
        ] * MPI.COMM_WORLD.size
        assert events[0]["record"]["physical_gate_passed"] is True
        assert events[0]["record"]["augmented_gate_passed"] is (
            correction_steps == 0
        )
        assert events[-1]["record"]["status"] == "passed"
        for event in events:
            np.testing.assert_allclose(
                event["fe_residual"],
                event["block_residual"][:2],
                rtol=1.0e-12,
                atol=1.0e-13,
            )
            np.testing.assert_allclose(
                event["port_residual"],
                event["block_residual"][2:],
                rtol=1.0e-12,
                atol=1.0e-13,
            )
            assert event["record"].get(
                "augmented_residual_norm", event["record"].get("residual_norm")
            ) == pytest.approx(event["block_norm"])
            if backend == "full":
                effective_oracle = event["block_residual"][:2] + (
                    fixture["traction"] * event["block_residual"][2]
                )
                effective_norm = float(np.linalg.norm(effective_oracle))
                effective_rhs = (
                    block_rhs[:2] + fixture["traction"] * port_rhs[0]
                )
                effective_rhs_norm = float(np.linalg.norm(effective_rhs))
                np.testing.assert_allclose(
                    event["effective_physical_residual"],
                    effective_oracle,
                    rtol=1.0e-12,
                    atol=1.0e-13,
                )
                assert event["record"]["residual_norm"] == pytest.approx(
                    effective_norm
                )
                assert event["record"]["relative_residual"] == pytest.approx(
                    effective_norm / effective_rhs_norm
                )
                assert event["record"]["rhs_norm"] == pytest.approx(
                    effective_rhs_norm
                )
                assert event["record"]["bare_physical_relative_residual"] != pytest.approx(
                    event["record"]["relative_residual"]
                )
        assert audit["backsolve_count"] == correction_steps + 1
        assert len(audit["diagnostic_correction_history"]) == correction_steps + 1
        if backend == "full":
            assert events[0]["port_correction"] is None
            for previous, current in pairwise(events):
                assert current["port_correction"] is not None
                np.testing.assert_allclose(
                    current["port_correction"],
                    current["port_solution"] - previous["port_solution"],
                    rtol=1.0e-12,
                    atol=1.0e-13,
                )
        np.testing.assert_array_equal(_gather_dense_vector(rhs), rhs_before)
        np.testing.assert_array_equal(port_rhs, port_rhs_before)
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
@pytest.mark.parametrize(
    "scenario",
    [
        "already_met",
        "one_correction",
        "two_corrections",
        "target_not_reached",
        "original_gate_failure",
        "nonzero_port_correction",
        "zero_rhs",
        "nonfinite",
    ],
)
def test_p4_refinement_target_uses_original_nonhermitian_augmented_block(
    backend: str,
    scenario: str,
) -> None:
    fixture_options: dict[str, object] = {
        "backend": backend,
        "perturb_initial_port": False,
    }
    expected_corrections = {
        "already_met": 0,
        "one_correction": 1,
        "two_corrections": 2,
        "target_not_reached": 2,
        "original_gate_failure": 2,
        "nonzero_port_correction": 1,
        "zero_rhs": 0,
        "nonfinite": 0,
    }[scenario]
    if scenario in {"one_correction", "two_corrections", "target_not_reached"}:
        fixture_options["perturb_initial_fe"] = 2.0e-12
    elif scenario == "original_gate_failure":
        fixture_options.update(
            perturb_initial_port=True,
            correction_scales=(0.0, 0.0),
        )
    elif scenario == "nonzero_port_correction":
        fixture_options["perturb_initial_port"] = True
    elif scenario == "zero_rhs":
        fixture_options["zero_rhs"] = True
    elif scenario == "nonfinite":
        fixture_options["nonfinite_first_fe"] = True
    if scenario == "two_corrections":
        fixture_options["correction_scales"] = (0.5, 1.0)
    elif scenario == "target_not_reached":
        fixture_options["correction_scales"] = (0.25, 0.25)

    fixture = _g2a_p4_fixture(**fixture_options)
    p4 = fixture["p4"]
    rhs = fixture["rhs"]
    rhs_before = _gather_dense_vector(rhs)
    port_rhs_before = fixture["port_rhs"].copy()
    result = None
    raised = False
    try:
        try:
            if backend == "full":
                p4.solve_with_refinement(
                    rhs,
                    fixture["solution"],
                    residual_tolerance=1.0e-10,
                    refinement_target_tolerance=5.0e-13,
                )
            else:
                result = p4.apply(
                    rhs,
                    port_rhs=fixture["port_rhs"],
                    refinement_target_tolerance=5.0e-13,
                )
        except P4PhysicalResidualGateError:
            raised = True

        expected_failure = scenario in {"original_gate_failure", "nonfinite"}
        assert raised is expected_failure
        audit = p4.diagnostics["last_solve"]
        history = audit["diagnostic_correction_history"]
        assert len(history) == expected_corrections + 1
        assert len(history) <= 3
        assert audit["refinement_target_tolerance"] == 5.0e-13
        assert audit["actual_correction_count"] == expected_corrections
        assert audit["backsolve_count"] == expected_corrections + 1
        assert fixture["inverse"].solve_count == expected_corrections + 1
        assert fixture["physical_context"].apply_count == len(history)
        assert [step["diagnostic_step_index"] for step in history] == list(
            range(len(history))
        )
        assert [step["actual_correction_count"] for step in history] == list(
            range(len(history))
        )
        assert all("physical_relative_residual" in step for step in history)
        assert all(
            "augmented_relative_residual" in step
            if backend == "full"
            else "relative_residual" in step
            for step in history
        )

        if scenario in {"already_met", "zero_rhs"}:
            assert audit["status"] == "passed"
            assert audit["target_reached"] is True
            assert audit["stop_reason"] == "target_reached"
            assert audit["actual_correction_count"] == 0
        elif scenario in {
            "one_correction",
            "two_corrections",
            "nonzero_port_correction",
        }:
            assert audit["status"] == "passed"
            assert audit["target_reached"] is True
            assert audit["stop_reason"] == "target_reached"
            assert audit["physical_gate_passed"] is True
            assert audit["augmented_gate_passed"] is True
            if scenario == "two_corrections":
                augmented_field = (
                    "augmented_relative_residual"
                    if backend == "full"
                    else "relative_residual"
                )
                assert [step["target_reached"] for step in history] == [
                    False,
                    False,
                    True,
                ]
                assert all(
                    max(
                        float(step["physical_relative_residual"]),
                        float(step[augmented_field]),
                    )
                    > 5.0e-13
                    for step in history[:2]
                )
                assert max(
                    float(history[2]["physical_relative_residual"]),
                    float(history[2][augmented_field]),
                ) <= 5.0e-13
                assert [step["actual_correction_count"] for step in history] == [
                    0,
                    1,
                    2,
                ]
                assert [step["backsolve_count"] for step in history] == [1, 2, 3]
        elif scenario == "target_not_reached":
            assert raised is False
            assert audit["status"] == "passed"
            assert audit["target_reached"] is False
            assert audit["stop_reason"] == "max_corrections_target_not_reached"
            assert audit["physical_gate_passed"] is True
            assert audit["augmented_gate_passed"] is True
            summary_call = {
                "p4_call_index": 1,
                "status": audit["status"],
                "physical_relative_residual": audit[
                    "physical_relative_residual"
                ],
                "augmented_relative_residual": audit.get(
                    "augmented_relative_residual", audit.get("relative_residual")
                ),
                "augmented_gate_passed": audit["augmented_gate_passed"],
                "last_solve_scalar_summary": {
                    key: audit[key]
                    for key in (
                        "target_reached",
                        "stop_reason",
                        "actual_correction_count",
                    )
                },
            }
            call_summary = SideBalancedInverse._p4_call_summary([summary_call])
            assert call_summary["failed_or_unqualified_call_indices"] == []
            assert (
                summary_call["last_solve_scalar_summary"]["target_reached"]
                is False
            )
            assert (
                summary_call["last_solve_scalar_summary"]["stop_reason"]
                == "max_corrections_target_not_reached"
            )
        elif scenario == "original_gate_failure":
            assert audit["status"] in {"gate_failed", "failed_gate"}
            assert audit["target_reached"] is False
            assert audit["stop_reason"] == "original_residual_gate_failed"
            assert not (
                audit["physical_gate_passed"] and audit["augmented_gate_passed"]
            )
        else:
            assert audit["status"] == "failed_nonfinite_residual"
            assert audit["target_reached"] is False
            assert audit["stop_reason"] == "nonfinite_residual"
            assert audit["backsolve_count"] == 1

        if scenario == "zero_rhs":
            if backend == "full":
                assert audit["rhs_norm"] == 0.0
                assert audit["relative_residual"] == audit["residual_norm"]
                assert audit["augmented_relative_residual"] == audit[
                    "augmented_residual_norm"
                ]
            else:
                assert audit["physical_rhs_norm"] == 0.0
                assert audit["physical_relative_residual"] == audit[
                    "physical_residual_norm"
                ]
                assert audit["relative_residual"] == audit["residual_norm"]

        if scenario == "nonzero_port_correction":
            assert np.any(port_rhs_before != 0.0)
            assert history[0]["port_residual_norm"] > 0.0
        if not expected_failure:
            if backend == "full":
                final_solution = _gather_dense_vector(fixture["solution"])
            else:
                final_solution = np.concatenate(
                    (_gather_dense_vector(result), p4.last_port_solution)
                )
            block_residual = fixture["block_rhs"] - fixture["block"] @ final_solution
            expected_norm = float(np.linalg.norm(block_residual))
            actual_norm = audit.get(
                "augmented_residual_norm", audit.get("residual_norm")
            )
            assert actual_norm == pytest.approx(expected_norm, abs=2.0e-13)
            if scenario in {"already_met", "one_correction", "two_corrections", "nonzero_port_correction", "zero_rhs"}:
                np.testing.assert_allclose(
                    final_solution,
                    fixture["exact_solution"],
                    rtol=0.0,
                    atol=1.0e-11,
                )
        np.testing.assert_array_equal(_gather_dense_vector(rhs), rhs_before)
        np.testing.assert_array_equal(fixture["port_rhs"], port_rhs_before)
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)
    if scenario == "two_corrections" and MPI.COMM_WORLD.rank == 0:
        augmented_field = (
            "augmented_relative_residual"
            if backend == "full"
            else "relative_residual"
        )
        print(
            "G3_TARGET_TWO_CORRECTIONS_HISTORY "
            f"backend={backend} "
            f"steps={[(step['diagnostic_step_index'], step['physical_relative_residual'], step[augmented_field], step['target_reached'], step['actual_correction_count'], step['backsolve_count']) for step in history]!r}",
            flush=True,
        )


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_refinement_target_is_single_candidate_and_excludes_fixed_steps(
    backend: str,
) -> None:
    fixture = _g2a_p4_fixture(
        backend=backend,
        perturb_initial_port=False,
    )
    p4 = fixture["p4"]
    try:
        def solve(**kwargs):
            if backend == "full":
                return p4.solve_with_refinement(
                    fixture["rhs"], fixture["solution"], **kwargs
                )
            return p4.apply(
                fixture["rhs"], port_rhs=fixture["port_rhs"], **kwargs
            )
        with pytest.raises(ValueError, match="only supported refinement target"):
            solve(refinement_target_tolerance=4.0e-13)
        with pytest.raises(ValueError, match="mutually exclusive"):
            solve(
                diagnostic_correction_steps=1,
                refinement_target_tolerance=5.0e-13,
            )
        assert fixture["inverse"].solve_count == 0
    finally:
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_diagnostic_corrects_small_fe_error_even_when_original_gates_pass(
    backend: str,
) -> None:
    fixture = _g2a_p4_fixture(
        backend=backend,
        perturb_initial_port=False,
        perturb_initial_fe=2.0e-12,
    )
    p4 = fixture["p4"]
    records: list[dict[str, object]] = []
    solution_errors: list[float] = []
    dense_residuals: list[np.ndarray] = []

    def observe(record, borrowed) -> None:
        if backend == "full":
            block_solution = _gather_dense_vector(borrowed["solution"])
        else:
            block_solution = np.concatenate(
                (
                    _gather_dense_vector(borrowed["solution"]),
                    np.asarray(borrowed["port_solution"]),
                )
            )
        residual = fixture["block_rhs"] - fixture["block"] @ block_solution
        records.append(dict(record))
        dense_residuals.append(residual)
        solution_errors.append(
            float(np.linalg.norm(block_solution - fixture["exact_solution"]))
        )

    result = None
    try:
        if backend == "full":
            audit = p4.solve_with_refinement(
                fixture["rhs"],
                fixture["solution"],
                residual_tolerance=1.0e-10,
                diagnostic_correction_steps=1,
                diagnostic_callback=observe,
            )
        else:
            result = p4.apply(
                fixture["rhs"],
                port_rhs=fixture["port_rhs"],
                diagnostic_correction_steps=1,
                diagnostic_callback=observe,
            )
            audit = p4.diagnostics["last_solve"]

        assert len(records) == 2
        assert records[0]["physical_gate_passed"] is True
        assert records[0]["augmented_gate_passed"] is True
        assert records[0]["diagnostic_correction_limit"] == 1
        assert audit["backsolve_count"] == 2
        assert fixture["inverse"].solve_count == 2
        assert solution_errors[0] > 0.0
        assert solution_errors[1] < solution_errors[0] * 1.0e-4
        assert audit["status"] == "passed"
        for record, residual in zip(records, dense_residuals, strict=True):
            residual_norm = float(np.linalg.norm(residual))
            assert record.get(
                "augmented_residual_norm", record.get("residual_norm")
            ) == pytest.approx(residual_norm)
            assert record.get(
                "augmented_relative_residual", record.get("relative_residual")
            ) == pytest.approx(
                residual_norm / float(np.linalg.norm(fixture["block_rhs"]))
            )
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_correction_without_observer_retains_real_core_a4_history(
    backend: str,
) -> None:
    fixture = _g2a_p4_fixture(
        backend=backend,
        perturb_initial_port=True,
    )
    p4 = fixture["p4"]
    rhs = fixture["rhs"]
    rhs_before = _gather_dense_vector(rhs)
    port_rhs_before = fixture["port_rhs"].copy()
    result = None
    try:
        if backend == "full":
            audit = p4.solve_with_refinement(
                rhs,
                fixture["solution"],
                diagnostic_correction_steps=1,
            )
        else:
            result = p4.apply(
                rhs,
                port_rhs=fixture["port_rhs"],
                diagnostic_correction_steps=1,
            )
            audit = p4.diagnostics["last_solve"]

        history = audit["diagnostic_correction_history"]
        assert [entry["diagnostic_step_index"] for entry in history] == [0, 1]
        assert audit["backsolve_count"] == 2
        augmented_norm_key = (
            "augmented_residual_norm" if backend == "full" else "residual_norm"
        )
        augmented_relative_key = (
            "augmented_relative_residual"
            if backend == "full"
            else "relative_residual"
        )
        for entry in history:
            assert entry["residual_tolerance"] == pytest.approx(1.0e-10)
            for key in (
                "physical_residual_norm",
                "physical_relative_residual",
                "augmented_fe_residual_norm",
                augmented_norm_key,
                augmented_relative_key,
            ):
                assert np.isfinite(entry[key])
            assert entry["physical_gate_passed"] is True
        assert history[0]["augmented_gate_passed"] is False
        assert history[1]["augmented_gate_passed"] is True
        np.testing.assert_array_equal(_gather_dense_vector(rhs), rhs_before)
        np.testing.assert_array_equal(fixture["port_rhs"], port_rhs_before)
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_diagnostic_zero_rhs_keeps_absolute_residual_semantics(
    backend: str,
) -> None:
    # The zero-RHS case deliberately perturbs the initial port solution.  The
    # first augmented residual is therefore nonzero and must retain the
    # absolute-residual interpretation before the one requested correction.
    fixture = _g2a_p4_fixture(backend=backend, zero_rhs=True)
    p4 = fixture["p4"]
    records: list[dict[str, object]] = []
    result = None
    try:
        if backend == "full":
            audit = p4.solve_with_refinement(
                fixture["rhs"],
                fixture["solution"],
                residual_tolerance=1.0e-12,
                diagnostic_correction_steps=1,
                diagnostic_callback=lambda record, _borrowed: records.append(
                    dict(record)
                ),
            )
        else:
            result = p4.apply(
                fixture["rhs"],
                port_rhs=fixture["port_rhs"],
                diagnostic_correction_steps=1,
                diagnostic_callback=lambda record, _borrowed: records.append(
                    dict(record)
                ),
            )
            audit = p4.diagnostics["last_solve"]
        first = records[0]
        if backend == "full":
            assert first["augmented_rhs_norm"] == 0.0
            assert first["augmented_relative_residual"] == pytest.approx(
                first["augmented_residual_norm"]
            )
            assert first["physical_rhs_norm"] == 0.0
            assert first["physical_relative_residual"] == pytest.approx(
                first["physical_residual_norm"]
            )
        else:
            assert first["augmented_rhs_norm"] == 0.0
            assert first["relative_residual"] == pytest.approx(
                first["residual_norm"]
            )
            assert first["physical_rhs_norm"] == 0.0
            assert first["physical_relative_residual"] == pytest.approx(
                first["physical_residual_norm"]
            )
        assert audit["status"] == "passed"
        zero_history = audit["diagnostic_correction_history"]
        assert len(zero_history) == 2
        assert [step["backsolve_count"] for step in zero_history] == [1, 2]
        assert [step["refinement_count"] for step in zero_history] == [0, 1]
        assert zero_history[0]["physical_rhs_norm"] == 0.0
        assert zero_history[0]["augmented_rhs_norm"] == 0.0
        assert zero_history[0]["correction_from_previous_seconds"] is None
        assert zero_history[1]["correction_from_previous_seconds"] >= 0.0
        assert zero_history[0]["augmented_gate_passed"] is False
        assert zero_history[1]["augmented_gate_passed"] is True
        augmented_relative_key = (
            "augmented_relative_residual"
            if backend == "full"
            else "relative_residual"
        )
        augmented_residual_key = (
            "augmented_residual_norm" if backend == "full" else "residual_norm"
        )
        assert zero_history[0][augmented_relative_key] == pytest.approx(
            zero_history[0][augmented_residual_key]
        )
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_diagnostic_exact_zero_rhs_records_one_requested_correction(
    backend: str,
) -> None:
    # This fixture uses the dense oracle factor, which executes on a zero
    # RHS. The production condensed inverse's direct-zero path is 0/0 and is
    # covered by the supervisor protocol fixture.
    fixture = _g2a_p4_fixture(
        backend=backend,
        zero_rhs=True,
        perturb_initial_port=False,
    )
    p4 = fixture["p4"]
    records: list[dict[str, object]] = []
    result = None
    try:
        assert np.linalg.norm(fixture["block_rhs"]) == 0.0
        assert np.linalg.norm(fixture["port_rhs"]) == 0.0
        if backend == "full":
            audit = p4.solve_with_refinement(
                fixture["rhs"],
                fixture["solution"],
                diagnostic_correction_steps=1,
                diagnostic_callback=lambda record, _borrowed: records.append(
                    dict(record)
                ),
            )
        else:
            result = p4.apply(
                fixture["rhs"],
                port_rhs=fixture["port_rhs"],
                diagnostic_correction_steps=1,
                diagnostic_callback=lambda record, _borrowed: records.append(
                    dict(record)
                ),
            )
            audit = p4.diagnostics["last_solve"]

        assert audit["status"] == "passed"
        history = audit["diagnostic_correction_history"]
        assert len(history) == len(records) == 2
        assert [step["diagnostic_step_index"] for step in history] == [0, 1]
        assert [step["backsolve_count"] for step in history] == [1, 2]
        assert [step["refinement_count"] for step in history] == [0, 1]
        assert [step["physical_rhs_norm"] for step in history] == [0.0, 0.0]
        assert [step["augmented_rhs_norm"] for step in history] == [0.0, 0.0]
        assert history[0]["correction_from_previous_seconds"] is None
        assert history[1]["correction_from_previous_seconds"] >= 0.0
        assert all(step["physical_gate_passed"] for step in history)
        assert all(step["augmented_gate_passed"] for step in history)
        assert fixture["inverse"].solve_count == 2
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


class _TinyCellCondensedLuFactor:
    """Real PETSc LU handle used by the focused P4Cell inverse fixture."""

    def __init__(self, matrix: PETSc.Mat) -> None:
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.solve_count = 0
        self.destroyed = False
        try:
            self.ksp.setOperators(matrix)
            self.ksp.setType("preonly")
            pc = self.ksp.getPC()
            pc.setType("lu")
            if matrix.getComm().tompi4py().size > 1:
                pc.setFactorSolverType("mumps")
            self.ksp.setUp()
        except BaseException:
            self.ksp.destroy()
            self.destroyed = True
            raise

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "factor_state": "numeric_ready",
            "factor_solve_count": int(self.solve_count),
        }

    def solve_repeated(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("tiny cell-condensed LU factor is destroyed")
        self.ksp.solve(rhs, solution)
        reason = int(self.ksp.getConvergedReason())
        if reason <= 0:
            raise RuntimeError(f"tiny cell-condensed LU did not converge: {reason}")
        self.solve_count += 1

    def destroy(self) -> None:
        if not self.destroyed:
            self.ksp.destroy()
            self.destroyed = True


def _fixed_q_real_cell_condensed_fixture(
    *,
    physical_trace_scale: float = 1.0,
    empty_owner: bool = False,
    side_restart64_trial_state: dict[str, object] | None = None,
    side_restart64_memory_gate=None,
):
    """Build a one-cell real P4Cell inverse and the fixed-Q side callback."""

    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("the real fixed-Q fixture is serial/MPI2 only")
    if empty_owner and comm.size != 2:
        pytest.skip("the empty-owner fixed-Q case requires MPI2")
    if not np.isfinite(physical_trace_scale) or physical_trace_scale <= 0.0:
        raise ValueError("tiny physical trace scale must be finite and positive")

    cell_ranks = (1,) if empty_owner else tuple(range(comm.size))
    slot_by_rank = {rank: slot for slot, rank in enumerate(cell_ranks)}
    cell_count = len(cell_ranks)
    full_rows = 2 * cell_count
    full_local_rows = (
        (0, 2) if empty_owner else (2,) * comm.size
    )
    active_local_rows = (
        (0, cell_count) if empty_owner else (1,) * comm.size
    )
    local_active_rows = active_local_rows[comm.rank]

    condensed_matrix = None
    condensed_factor = None
    condensed_system = None
    cell_inverse = None
    physical_matrix = None
    p4 = None
    h6 = _tiny_fixed_h6(full_rows, local_row_counts=full_local_rows)
    side_inverse = None
    side_owned = None
    try:
        condensed_matrix = PETSc.Mat().createAIJ(
            size=((local_active_rows, cell_count), (local_active_rows, cell_count)),
            nnz=1,
            comm=comm,
        )
        active_start, active_end = map(int, condensed_matrix.getOwnershipRange())
        for row in range(active_start, active_end):
            condensed_matrix.setValues(
                np.asarray([row], dtype=PETSc.IntType),
                np.asarray([row], dtype=PETSc.IntType),
                np.asarray([[1.0 + 0.0j]], dtype=PETSc.ScalarType),
            )
        condensed_matrix.assemble()
        condensed_factor = _TinyCellCondensedLuFactor(condensed_matrix)

        original_to_trace = {
            2 * slot + 1: slot for slot in range(cell_count)
        }
        expansion_by_original = {
            2 * slot + 1: (
                np.asarray([slot], dtype=PETSc.IntType),
                np.asarray([1.0 + 0.0j], dtype=np.complex128),
            )
            for slot in range(cell_count)
        }
        owned_active_originals = np.asarray(
            [
                2 * slot_by_rank[comm.rank] + 1
            ]
            if comm.rank in slot_by_rank
            else [],
            dtype=PETSc.IntType,
        )
        trace_constraints = TraceConstraintMap(
            owned_active_original_dofs=owned_active_originals.copy(),
            original_to_active=dict(original_to_trace),
            expansion_by_original=expansion_by_original,
            full_trace_rows=cell_count,
            active_rows=cell_count,
            slave_rows=0,
            build_audit={"fixture": "one-cell-identity-trace-expansion"},
        )
        local_cells = ()
        interior_from_trace: dict[tuple[int, ...], np.ndarray] = {}
        interior_lu: dict[tuple[int, ...], tuple[np.ndarray, np.ndarray]] = {}
        interior_rhs_projection: dict[tuple[int, ...], np.ndarray] = {}
        interior_solution_embedding: dict[tuple[int, ...], np.ndarray] = {}
        trace_from_interior_rhs: dict[tuple[int, ...], np.ndarray] = {}
        interior_residual_projection: dict[tuple[int, ...], np.ndarray] = {}
        if comm.rank in slot_by_rank:
            slot = slot_by_rank[comm.rank]
            class_key = (slot,)
            local_cells = (
                CellRecoveryMap(
                    interior_original_dofs=np.asarray(
                        [2 * slot], dtype=PETSc.IntType
                    ),
                    trace_original_dofs=np.asarray(
                        [2 * slot + 1], dtype=PETSc.IntType
                    ),
                    class_key=class_key,
                ),
            )
            interior_from_trace[class_key] = np.zeros(
                (1, 1), dtype=np.complex128
            )
            interior_lu[class_key] = lu_factor(
                np.asarray([[2.0 + 0.0j]], dtype=np.complex128)
            )
            interior_rhs_projection[class_key] = np.eye(
                1, dtype=np.complex128
            )
            interior_solution_embedding[class_key] = np.eye(
                1, dtype=np.complex128
            )
            trace_from_interior_rhs[class_key] = np.zeros(
                (1, 1), dtype=np.complex128
            )
            interior_residual_projection[class_key] = np.eye(
                1, dtype=np.complex128
            )
        condensed_system = AssemblyTimeCondensedSystem(
            matrix=condensed_matrix,
            owned_trace_original_dofs=owned_active_originals.copy(),
            original_to_trace=dict(original_to_trace),
            trace_constraints=trace_constraints,
            cell_recovery_maps=local_cells,
            interior_from_trace_by_class=interior_from_trace,
            interior_lu_by_class=interior_lu,
            interior_rhs_projection_by_class=interior_rhs_projection,
            interior_solution_embedding_by_class=interior_solution_embedding,
            trace_from_interior_rhs_by_class=trace_from_interior_rhs,
            interior_residual_projection_by_class=interior_residual_projection,
            full_rows=full_rows,
            trace_rows=cell_count,
            active_rows=cell_count,
            appended_rows=0,
            interior_rows=cell_count,
            active_interior_rows=cell_count,
            build_audit={"fixture": "actual-P4CellCondensedInverse-one-cell"},
            comm=comm,
            owned_active_rows=local_active_rows,
            owned_appended_rows=0,
            retained_local_schur_by_class=None,
        )
        cell_inverse = P4CellCondensedInverse(
            condensed_system,
            condensed_factor,
            owns_condensed=True,
            owns_factor=True,
        )
        condensed_matrix = None
        condensed_system = None
        condensed_factor = None

        physical_values = np.zeros((full_rows, full_rows), dtype=np.complex128)
        for slot in range(cell_count):
            physical_values[2 * slot, 2 * slot] = 2.0
            physical_values[2 * slot + 1, 2 * slot + 1] = (
                physical_trace_scale
            )
        physical_matrix, physical_context = _dense_python_matrix(
            physical_values,
            base_rows=full_rows,
            purpose="real-cell-condensed-fixed-q-A4",
            local_row_counts=full_local_rows,
        )
        physical_action = SimpleNamespace(
            matrix=physical_matrix,
            full_rows=full_rows,
            modes=(),
            action=SimpleNamespace(modes=()),
            audit={"fixture": "diagonal-original-A4"},
        )
        p4 = P4CondensedExactFactor(
            physical_action=physical_action,
            inverse=cell_inverse,
            factor_events=["actual-P4CellCondensedInverse"],
            residual_tolerance=1.0e-10,
            owns_physical_action=False,
        )
        cell_inverse = None

        side_inverse, side_owned = _build_fixture(
            size=full_rows,
            p4_factor=p4,
            p4_inverse_backend="cell_condensed",
            h6_action=h6,
            local_row_counts=full_local_rows,
            side_restart64_trial_state=side_restart64_trial_state,
            side_restart64_memory_gate=side_restart64_memory_gate,
        )
        p4 = None
        old_full_action = side_owned["full_action"].matrix
        old_full_action.destroy()
        side_owned["full_action"].matrix = physical_matrix
        side_owned["full_action"].context = physical_context
        physical_matrix = None
        side_inverse.configure_diagnostic_p4_corrections(
            0, None, refinement_target_tolerance=5.0e-13
        )
        return side_inverse, side_owned
    except BaseException:
        if side_inverse is not None:
            side_inverse.destroy()
            if side_owned is not None:
                side_owned["operator"].destroy()
        else:
            h6.destroy()
        if side_inverse is None and p4 is not None:
            p4.destroy()
            if physical_matrix is not None:
                physical_matrix.destroy()
        elif side_inverse is None and cell_inverse is not None:
            cell_inverse.destroy()
            if physical_matrix is not None:
                physical_matrix.destroy()
        elif side_inverse is None:
            if condensed_factor is not None:
                condensed_factor.destroy()
            if condensed_system is not None:
                condensed_system.destroy()
            elif condensed_matrix is not None:
                condensed_matrix.destroy()
            if physical_matrix is not None:
                physical_matrix.destroy()
        raise


def _fixed_physical_balh_cell_fixture(
    *,
    zero_rhs: bool = False,
    correction_scales: tuple[float, ...] = (),
    local_row_counts: tuple[int, ...] | None = None,
    align_a6_with_p4: bool = True,
):
    p4_fixture = _g2a_p4_fixture(
        backend="cell_condensed",
        zero_rhs=zero_rhs,
        perturb_initial_port=not zero_rhs,
        correction_scales=correction_scales,
        local_row_counts=local_row_counts,
    )
    h6 = _tiny_fixed_h6(2, local_row_counts=local_row_counts)
    inverse = None
    owned = None
    try:
        inverse, owned = _build_fixture(
            size=2,
            p4_factor=p4_fixture["p4"],
            p4_inverse_backend="cell_condensed",
            h6_action=h6,
            local_row_counts=local_row_counts,
        )
        if align_a6_with_p4:
            old_a6 = owned["full_action"].matrix
            a6_values = np.array(
                p4_fixture["physical_context"].dense,
                dtype=np.complex128,
                copy=True,
            )
            new_a6, new_a6_context = _dense_python_matrix(
                a6_values,
                base_rows=2,
                purpose="a6-aligned-to-independent-p4-physical-matrix",
                local_row_counts=local_row_counts,
            )
            owned["full_action"].matrix = new_a6
            owned["full_action"].context = new_a6_context
            old_a6.destroy()
        inverse.configure_diagnostic_p4_corrections(
            0, None, refinement_target_tolerance=5.0e-13
        )
    except BaseException:
        if inverse is None:
            h6.destroy()
        else:
            inverse.destroy()
            owned["operator"].destroy()
        _destroy_g2a_p4_fixture(p4_fixture)
        raise
    return inverse, owned, p4_fixture


def _assert_fixed_q_original_a_residual(
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> float:
    applied = matrix.createVecLeft()
    residual = rhs.duplicate()
    try:
        matrix.mult(solution, applied)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), applied)
        residual_norm = float(residual.norm())
        rhs_norm = float(rhs.norm())
        relative = residual_norm / rhs_norm if rhs_norm > 0.0 else residual_norm
        assert np.isfinite(relative)
        assert relative <= 1.0e-10
        return relative
    finally:
        residual.destroy()
        applied.destroy()


@pytest.mark.parametrize(
    "case,trace_scale,expected_statuses,expected_deltas",
    [
        (
            "global_exact_zero",
            1.0,
            ("ZERO_RHS_DIRECT_ZERO", "ZERO_RHS_DIRECT_ZERO"),
            (0, 0),
        ),
        (
            "nonzero_q_input_ph_zero",
            1.0,
            ("ZERO_RHS_DIRECT_ZERO", "ZERO_RHS_DIRECT_ZERO"),
            (0, 0),
        ),
        (
            "nonzero_initial_exact_zero_correction",
            1.0,
            ("SOLVE_COMPLETED", "ZERO_RHS_DIRECT_ZERO"),
            (1, 0),
        ),
        (
            "nonzero_initial_and_correction",
            1.0 + 1.0e-6,
            ("SOLVE_COMPLETED", "SOLVE_COMPLETED"),
            (1, 1),
        ),
        (
            "mpi2_empty_owner_global_nonzero",
            1.0,
            ("SOLVE_COMPLETED", "ZERO_RHS_DIRECT_ZERO"),
            (1, 0),
        ),
    ],
)
def test_fixed_physical_q_real_cell_inverse_audits_exact_solve_branches(
    case: str,
    trace_scale: float,
    expected_statuses: tuple[str, str],
    expected_deltas: tuple[int, int],
) -> None:
    empty_owner = case == "mpi2_empty_owner_global_nonzero"
    if empty_owner and MPI.COMM_WORLD.size != 2:
        pytest.skip("the empty-owner fixed-Q branch is MPI2-only")
    inverse, owned = _fixed_q_real_cell_condensed_fixture(
        physical_trace_scale=trace_scale,
        empty_owner=empty_owner,
    )
    p4 = owned["p4_factor"]
    assert isinstance(p4, P4CondensedExactFactor)
    assert isinstance(p4.inverse, P4CellCondensedInverse)
    action = inverse.create_fixed_physical_balh_active_trace_action()
    source_values = np.asarray(
        [0.5 + 0.25j + 0.1j * index for index in range(p4.full_rows)],
        dtype=np.complex128,
    )
    if case == "global_exact_zero":
        source_values.fill(0.0)
    source = _new_vector(p4.physical_action.matrix, source_values)
    source_before = _gather_dense_vector(source)
    target = None
    expected_rhs = None
    apply_kwargs: list[dict[str, object]] = []
    original_p4_apply = p4.apply

    def capture_p4_apply(rhs: PETSc.Vec, **kwargs):
        apply_kwargs.append(dict(kwargs))
        return original_p4_apply(rhs, **kwargs)

    p4.apply = capture_p4_apply
    if case == "nonzero_q_input_ph_zero":
        def zero_adjoint(rhs: PETSc.Vec, *, timing=None) -> PETSc.Vec:
            del timing
            zero = rhs.duplicate()
            zero.set(PETSc.ScalarType(0.0))
            zero.assemble()
            return zero

        owned["transfer"].apply_adjoint = zero_adjoint
    try:
        assert inverse._p4_refinement_target_tolerance == 5.0e-13
        if case == "global_exact_zero":
            assert float(source.norm()) == 0.0
        else:
            assert float(source.norm()) > 0.0
        if empty_owner:
            assert source.getLocalSize() == (0 if MPI.COMM_WORLD.rank == 0 else 2)
            assert float(source.norm()) > 0.0
        target = action._apply_q_once(source)
        q_audit = inverse._last_fixed_q_solve_audit
        assert isinstance(q_audit, dict)
        assert q_audit["mathematical_correction_steps"] == 1
        assert q_audit["q_input_global_exact_zero"] is (
            case == "global_exact_zero"
        )
        assert q_audit["factor_solve_deltas_by_step"] == expected_deltas
        history = q_audit["inverse_apply_history"]
        assert len(history) == 2
        assert tuple(entry["step"] for entry in history) == (
            "initial",
            "correction_1",
        )
        assert tuple(entry["status"] for entry in history) == expected_statuses
        assert tuple(entry["factor_solve_delta"] for entry in history) == expected_deltas
        assert all(
            entry["factor_identity_local"] == id(p4.inverse.factor)
            for entry in history
        )
        assert q_audit["factor_solve_call_delta"] == sum(expected_deltas)
        assert p4.inverse.solve_count == sum(expected_deltas)
        assert apply_kwargs == [
            {"diagnostic_correction_steps": 1, "timing": None}
        ]
        assert "refinement_target_tolerance" not in apply_kwargs[0]
        assert inverse._p4_refinement_target_tolerance == 5.0e-13

        if case == "nonzero_q_input_ph_zero":
            assert q_audit["q_input_global_norm"] > 0.0
            assert all(
                entry["global_rhs_exact_zero"]
                and entry["port_rhs_exact_zero"]
                for entry in history
            )
            expected_rhs = source.duplicate()
            expected_rhs.set(PETSc.ScalarType(0.0))
            expected_rhs.assemble()
        else:
            expected_rhs = source
        residual_relative = _assert_fixed_q_original_a_residual(
            p4.physical_action.matrix,
            expected_rhs,
            target,
        )
        assert residual_relative <= 1.0e-10
        last_solve = p4.diagnostics["last_solve"]
        assert last_solve["physical_gate_passed"] is True
        assert last_solve["augmented_gate_passed"] is True
        assert last_solve["residual_tolerance"] == 1.0e-10
        assert last_solve["backsolve_count"] == sum(expected_deltas)
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
    finally:
        if expected_rhs is not None and expected_rhs is not source:
            expected_rhs.destroy()
        if target is not None:
            target.destroy()
        source.destroy()
        action.destroy()
        inverse.destroy()
        owned["operator"].destroy()


def test_fixed_physical_q_real_cell_inverse_full_action_global_zero_records_all_direct_zero_steps() -> None:
    inverse, owned = _fixed_q_real_cell_condensed_fixture()
    p4 = owned["p4_factor"]
    assert isinstance(p4, P4CondensedExactFactor)
    assert isinstance(p4.inverse, P4CellCondensedInverse)
    action = inverse.create_fixed_physical_balh_active_trace_action()
    source = _new_vector(
        p4.physical_action.matrix,
        np.zeros(int(p4.full_rows), dtype=np.complex128),
    )
    source_before = _gather_dense_vector(source)
    target = owned["operator"].createVecLeft()
    try:
        action.apply(source, target)
        assert float(source.norm()) == 0.0
        assert float(target.norm()) == 0.0
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        assert _assert_fixed_q_original_a_residual(
            p4.physical_action.matrix,
            source,
            target,
        ) == 0.0
        assert p4.inverse.solve_count == 0
        audit = action.audit
        assert audit["last_q_factor_solve_deltas"] == [0, 0]
        assert audit["last_q_factor_step_solve_deltas"] == [[0, 0], [0, 0]]
        assert audit["mathematical_p4_correction_steps_per_q"] == 1
        q_audits = audit["last_q_solve_audits"]
        assert len(q_audits) == 2
        assert all(
            q_audit["mathematical_correction_steps"] == 1
            and q_audit["q_input_global_exact_zero"] is True
            and q_audit["factor_solve_call_delta"] == 0
            and q_audit["factor_solve_deltas_by_step"] == (0, 0)
            and q_audit["factor_solve_count_before"] == 0
            and q_audit["factor_solve_count_after"] == 0
            for q_audit in q_audits
        )
        for q_audit in q_audits:
            inverse_history = q_audit["inverse_apply_history"]
            assert len(inverse_history) == 2
            assert tuple(entry["step"] for entry in inverse_history) == (
                "initial",
                "correction_1",
            )
            assert all(
                entry["status"] == "ZERO_RHS_DIRECT_ZERO"
                and entry["global_rhs_exact_zero"] is True
                and entry["port_rhs_exact_zero"] is True
                and entry["factor_solve_delta"] == 0
                and entry["factor_solve_count_before"] == 0
                and entry["factor_solve_count_after"] == 0
                and entry["inverse_audit"]["slave_zero"] is True
                and entry["inverse_audit"]["port_rhs_zero"] is True
                for entry in inverse_history
            )
        coupling_counts = audit["last_balh_coupling"]["counts"]
        assert coupling_counts["Q"] == 2
        assert coupling_counts["A6"] == 2
        assert coupling_counts["H6"] == 1
        assert audit["a6_apply_count"] == 2
        assert audit["h6_apply_count"] == 1
    finally:
        target.destroy()
        source.destroy()
        action.destroy()
        inverse.destroy()
        owned["operator"].destroy()


def test_fixed_physical_q_real_cell_inverse_rejects_audit_counter_mismatch() -> None:
    inverse, owned = _fixed_q_real_cell_condensed_fixture()
    p4 = owned["p4_factor"]
    action = inverse.create_fixed_physical_balh_active_trace_action()
    source_values = np.asarray([0.25 + 0.5j, -0.125 + 0.375j], dtype=np.complex128)
    source = _new_vector(p4.physical_action.matrix, source_values)
    cell_inverse = p4.inverse
    original_apply = cell_inverse.apply

    def mismatch_solve_counter_audit(rhs: PETSc.Vec, *, port_rhs=None):
        result = original_apply(rhs, port_rhs=port_rhs)
        if cell_inverse.last_audit.get("status") == "SOLVE_COMPLETED":
            cell_inverse.last_audit = {
                **cell_inverse.last_audit,
                "factor_solve_call_delta": 0,
            }
        return result

    cell_inverse.apply = mismatch_solve_counter_audit
    try:
        with pytest.raises(
            RuntimeError,
            match="fixed P4 inverse audit validation failed",
        ):
            action._apply_q_once(source)
        assert cell_inverse.solve_count == 1
        assert p4.diagnostics["last_solve"]["error_type"] == "RuntimeError"
    finally:
        source.destroy()
        action.destroy()
        inverse.destroy()
        owned["operator"].destroy()


def test_fixed_physical_q_real_cell_inverse_is_complex_linear_with_original_a_residual() -> None:
    inverse, owned = _fixed_q_real_cell_condensed_fixture()
    p4 = owned["p4_factor"]
    action = inverse.create_fixed_physical_balh_active_trace_action()
    row_count = int(p4.full_rows)
    x_values = np.asarray(
        [0.3 + 0.2j * index for index in range(row_count)], dtype=np.complex128
    )
    y_values = np.asarray(
        [-0.15 + 0.25j * (index + 1) for index in range(row_count)],
        dtype=np.complex128,
    )
    alpha = 0.25 + 0.375j
    beta = -0.125 + 0.2j
    combined_values = alpha * x_values + beta * y_values
    vectors = [
        _new_vector(p4.physical_action.matrix, values)
        for values in (x_values, y_values, combined_values)
    ]
    outputs: list[PETSc.Vec] = []
    try:
        for source in vectors:
            output = action._apply_q_once(source)
            outputs.append(output)
            assert _assert_fixed_q_original_a_residual(
                p4.physical_action.matrix,
                source,
                output,
            ) <= 1.0e-10
        actual = _gather_dense_vector(outputs[2])
        expected = (
            alpha * _gather_dense_vector(outputs[0])
            + beta * _gather_dense_vector(outputs[1])
        )
        assert np.linalg.norm(actual - expected) <= 1.0e-12 * max(
            float(np.linalg.norm(expected)), 1.0
        )
        assert p4.inverse.solve_count == 3
        assert inverse._p4_refinement_target_tolerance == 5.0e-13
        assert action.audit["last_q_factor_step_solve_deltas"] == [
            [1, 0],
            [1, 0],
        ]
    finally:
        for output in outputs:
            output.destroy()
        for source in vectors:
            source.destroy()
        action.destroy()
        inverse.destroy()
        owned["operator"].destroy()


def _sample_galerkin_a6(
    inverse: SideBalancedInverse,
    action,
    p4_fixture: dict[str, object],
) -> tuple[np.ndarray, np.ndarray]:
    """Measure P^H A6 P through the fixture's actual transfer/action callbacks."""

    size = int(inverse._operator.getSize()[0])
    sampled = np.empty((size, size), dtype=np.complex128)
    p4_action = np.empty((size, size), dtype=np.complex128)
    p4_matrix = p4_fixture["physical_matrix"]
    for column in range(size):
        basis_values = np.zeros(size, dtype=np.complex128)
        basis_values[column] = 1.0
        basis = _new_vector(inverse._operator, basis_values)
        primal = a6_image = dual_image = p4_image = None
        try:
            primal = inverse._owner_transfer.apply_primal(basis)
            a6_image = action._apply_a6(primal)
            dual_image = action._apply_ph(a6_image)
            p4_image = p4_matrix.createVecLeft()
            p4_matrix.mult(basis, p4_image)
            sampled[:, column] = _gather_dense_vector(dual_image)
            p4_action[:, column] = _gather_dense_vector(p4_image)
        finally:
            for vector in (p4_image, dual_image, a6_image, primal, basis):
                if vector is not None:
                    vector.destroy()
    return sampled, p4_action


def _sample_fixed_h6_matrix(inverse: SideBalancedInverse) -> np.ndarray:
    size = int(inverse._operator.getSize()[0])
    sampled = np.empty((size, size), dtype=np.complex128)
    for column in range(size):
        basis_values = np.zeros(size, dtype=np.complex128)
        basis_values[column] = 1.0
        basis = _new_vector(inverse._operator, basis_values)
        response = None
        try:
            response = inverse._h6.apply(basis)
            sampled[:, column] = _gather_dense_vector(response)
        finally:
            if response is not None:
                response.destroy()
            basis.destroy()
    return sampled


def test_side_inverse_fixed_physical_balh_cell_condensed_q_uses_one_correction_per_input() -> None:
    local_row_counts = (2, 0) if MPI.COMM_WORLD.size == 2 else None
    # Preserve the former synthetic mismatch as a negative control: A4 is
    # non-Hermitian while the old full-action A6 is identity, so the real
    # BAL_H initial balance gate must reject before H6 is called.
    wrong_inverse, wrong_owned, wrong_p4_fixture = (
        _fixed_physical_balh_cell_fixture(
            local_row_counts=local_row_counts,
            align_a6_with_p4=False,
        )
    )
    wrong_action = None
    wrong_source = None
    wrong_target = None
    try:
        wrong_action = wrong_inverse.create_fixed_physical_balh_active_trace_action()
        wrong_source = wrong_p4_fixture["rhs"].duplicate()
        wrong_p4_fixture["rhs"].copy(wrong_source)
        wrong_target = wrong_owned["operator"].createVecLeft()
        wrong_galerkin_a6, wrong_p4_action = _sample_galerkin_a6(
            wrong_inverse, wrong_action, wrong_p4_fixture
        )
        assert np.linalg.norm(
            wrong_galerkin_a6 - wrong_p4_action
        ) > 1.0e-8
        with pytest.raises(
            side_inverse_module.BalancedConstraintRejected
        ) as caught:
            wrong_action.apply(wrong_source, wrong_target)
        assert caught.value.facts["relative"] > 1.0e-8
        assert wrong_inverse._h6.apply_count == 0
    finally:
        for vector in (wrong_target, wrong_source):
            if vector is not None:
                vector.destroy()
        if wrong_action is not None:
            wrong_action.destroy()
        wrong_inverse.destroy()
        wrong_owned["operator"].destroy()
        _destroy_g2a_p4_fixture(wrong_p4_fixture)

    inverse, owned, p4_fixture = _fixed_physical_balh_cell_fixture(
        local_row_counts=local_row_counts
    )
    p4 = p4_fixture["p4"]
    assert isinstance(p4, P4CondensedExactFactor)
    action = inverse.create_fixed_physical_balh_active_trace_action()
    solve_records: list[dict[str, object]] = []
    original_apply = p4.apply

    def capture_apply(rhs: PETSc.Vec, **kwargs):
        result = original_apply(rhs, **kwargs)
        last = dict(p4.diagnostics["last_solve"])
        solve_records.append({"kwargs": dict(kwargs), "audit": last})
        return result

    p4.apply = capture_apply
    source = p4_fixture["rhs"].duplicate()
    p4_fixture["rhs"].copy(source)
    source_before = _gather_dense_vector(source)
    target = owned["operator"].createVecLeft()
    zero_source = source.duplicate()
    zero_source.set(PETSc.ScalarType(0.0))
    zero_source.assemble()
    zero_target = owned["operator"].createVecLeft()
    try:
        assert inverse._p4_refinement_target_tolerance == 5.0e-13
        assert float(source.norm()) > 0.0
        galerkin_a6, p4_action = _sample_galerkin_a6(
            inverse, action, p4_fixture
        )
        physical_matrix = np.asarray(
            p4_fixture["physical_context"].dense, dtype=np.complex128
        )
        np.testing.assert_allclose(
            galerkin_a6,
            p4_action,
            rtol=1.0e-13,
            atol=1.0e-13,
        )
        np.testing.assert_allclose(
            p4_action, physical_matrix, rtol=1.0e-13, atol=1.0e-13
        )
        h6_matrix = _sample_fixed_h6_matrix(inverse)
        q_matrix = np.linalg.inv(physical_matrix)
        identity = np.eye(physical_matrix.shape[0], dtype=np.complex128)
        dense_balh = q_matrix + (identity - q_matrix @ galerkin_a6) @ h6_matrix @ (
            identity - galerkin_a6 @ q_matrix
        )
        expected = dense_balh @ source_before
        action.apply(source, target)
        assert np.isfinite(float(target.norm()))
        assert float(target.norm()) > 0.0
        actual = _gather_dense_vector(target)
        response_relative = float(
            np.linalg.norm(actual - expected)
            / max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
        )
        assert response_relative <= 1.0e-10
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        assert len(solve_records) == 2
        assert all(
            row["kwargs"].get("diagnostic_correction_steps") == 1
            and "refinement_target_tolerance" not in row["kwargs"]
            for row in solve_records
        )
        for row in solve_records:
            audit = row["audit"]
            assert audit["status"] == "passed"
            assert audit["residual_tolerance"] == pytest.approx(1.0e-10)
            assert audit["physical_gate_passed"] is True
            assert audit["augmented_gate_passed"] is True
            assert audit["relative_residual"] <= 1.0e-10
            assert audit["backsolve_count"] == 2
            assert audit["diagnostic_correction_limit"] == 1
            assert len(audit["diagnostic_correction_history"]) == 2
        assert p4.inverse.solve_count == 4
        assert action.audit["last_q_factor_solve_deltas"] == [2, 2]
        assert action.audit["p4_refinement_target_tolerance_used"] is None
        assert action.audit["ordinary_side_refinement_target_tolerance"] == (
            5.0e-13
        )
        assert inverse._p4_refinement_target_tolerance == 5.0e-13

        action.apply(zero_source, zero_target)
        assert float(zero_source.norm()) == 0.0
        assert float(zero_target.norm()) == 0.0
        assert p4.inverse.solve_count == 8
        assert action.audit["last_q_factor_solve_deltas"] == [2, 2]
        assert len(solve_records) == 4
        assert inverse._p4_refinement_target_tolerance == 5.0e-13
        if local_row_counts is not None:
            assert owned["side_system"].static_condensation.condensed.owned_active_rows == (
                2 if MPI.COMM_WORLD.rank == 0 else 0
            )
            assert source.getLocalSize() == (
                2 if MPI.COMM_WORLD.rank == 0 else 0
            )
    finally:
        zero_target.destroy()
        zero_source.destroy()
        target.destroy()
        source.destroy()
        action.destroy()
        assert p4._destroyed is False
        inverse.destroy()
        owned["operator"].destroy()
        _destroy_g2a_p4_fixture(p4_fixture)


def test_side_inverse_fixed_physical_balh_cell_condensed_q_rejects_actual_residual() -> None:
    inverse, owned, p4_fixture = _fixed_physical_balh_cell_fixture(
        correction_scales=(0.0,)
    )
    p4 = p4_fixture["p4"]
    assert isinstance(p4, P4CondensedExactFactor)
    action = inverse.create_fixed_physical_balh_active_trace_action()
    source = p4_fixture["rhs"].duplicate()
    p4_fixture["rhs"].copy(source)
    source_before = _gather_dense_vector(source)
    target = owned["operator"].createVecLeft()
    try:
        with pytest.raises(P4PhysicalResidualGateError) as caught:
            action.apply(source, target)
        residual = float(caught.value.audit["relative_residual"])
        assert np.isfinite(residual)
        assert residual > 1.0e-10
        assert caught.value.audit["status"] == "gate_failed"
        assert caught.value.audit["physical_gate_passed"] is False or (
            caught.value.audit["augmented_gate_passed"] is False
        )
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        assert p4._destroyed is False
        assert inverse._destroyed is False
    finally:
        target.destroy()
        source.destroy()
        action.destroy()
        assert p4._destroyed is False
        inverse.destroy()
        owned["operator"].destroy()
        _destroy_g2a_p4_fixture(p4_fixture)


def test_p4_condensed_diagnostic_rejects_nonfinite_before_next_backsolve() -> None:
    fixture = _g2a_p4_fixture(
        backend="cell_condensed",
        perturb_initial_port=False,
        nonfinite_first_fe=True,
    )
    p4 = fixture["p4"]
    records: list[dict[str, object]] = []
    try:
        with pytest.raises(P4PhysicalResidualGateError):
            p4.apply(
                fixture["rhs"],
                port_rhs=fixture["port_rhs"],
                diagnostic_correction_steps=1,
                diagnostic_callback=lambda record, _borrowed: records.append(
                    dict(record)
                ),
            )
        assert len(records) == 1
        assert records[0]["status"] == "failed_nonfinite_residual"
        assert fixture["inverse"].solve_count == 1
        assert p4.diagnostics["last_solve"]["backsolve_count"] == 1
    finally:
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_default_refinement_path_does_not_enable_diagnostic_callbacks(
    backend: str,
) -> None:
    fixture = _g2a_p4_fixture(backend=backend, zero_rhs=True)
    p4 = fixture["p4"]
    result = None
    try:
        if backend == "full":
            audit = p4.solve_with_refinement(fixture["rhs"], fixture["solution"])
            assert audit["backsolve_count"] == 1
            assert "augmented_gate_passed" not in audit
            assert fixture["inverse"].solve_count == 1
            assert fixture["physical_context"].apply_count == 1
        else:
            result = p4.apply(fixture["rhs"], port_rhs=fixture["port_rhs"])
            audit = p4.diagnostics["last_solve"]
            assert audit["backsolve_count"] == 2
            assert "diagnostic_correction_history" not in audit
            assert fixture["inverse"].solve_count == 2
            assert fixture["physical_context"].apply_count == 2
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


@pytest.mark.parametrize("backend", ["full", "cell_condensed"])
def test_p4_diagnostic_callback_failure_is_synchronized_and_cleaned(
    backend: str,
) -> None:
    fixture = _g2a_p4_fixture(
        backend=backend,
        zero_rhs=True,
        perturb_initial_port=False,
    )
    p4 = fixture["p4"]
    rhs_before = _gather_dense_vector(fixture["rhs"])
    port_rhs_before = fixture["port_rhs"].copy()
    caller_solution = fixture["solution"] if backend == "full" else None
    caller_rhs = fixture["rhs"]
    native_refs_before = (
        {
            "solution": int(caller_solution.getRefCount()),
            "rhs": int(caller_rhs.getRefCount()),
        }
        if caller_solution is not None
        else None
    )

    def fail_on_one_rank(_record, _borrowed) -> None:
        if MPI.COMM_WORLD.rank == 0:
            raise ValueError("intentional diagnostic callback failure")

    try:
        with pytest.raises(
            RuntimeError,
            match="callback failed on at least one rank",
        ) as caught:
            if backend == "full":
                p4.solve_with_refinement(
                    fixture["rhs"],
                    fixture["solution"],
                    diagnostic_correction_steps=1,
                    diagnostic_callback=fail_on_one_rank,
                )
            else:
                p4.apply(
                    fixture["rhs"],
                    port_rhs=fixture["port_rhs"],
                    diagnostic_correction_steps=1,
                    diagnostic_callback=fail_on_one_rank,
                )
        np.testing.assert_array_equal(
            _gather_dense_vector(fixture["rhs"]), rhs_before
        )
        np.testing.assert_array_equal(fixture["port_rhs"], port_rhs_before)
        assert p4.diagnostics["last_solve"]["error_type"] == "RuntimeError"
        if backend == "full":
            assert caller_solution is not None
            assert caller_solution.getSize() == fixture["block"].shape[0]
            assert np.isfinite(float(caller_solution.norm()))
            assert native_refs_before is not None
            native_refs_after = {
                "solution": int(caller_solution.getRefCount()),
                "rhs": int(caller_rhs.getRefCount()),
            }
            print(
                "G2a_view_lifetime_refcounts "
                f"rank={MPI.COMM_WORLD.rank} pid={os.getpid()} "
                f"before={native_refs_before} after={native_refs_after}",
                flush=True,
            )
            assert native_refs_after == native_refs_before
            if MPI.COMM_WORLD.rank == 0:
                assert isinstance(caught.value.__cause__, ValueError)
                assert str(caught.value.__cause__) == (
                    "intentional diagnostic callback failure"
                )
            else:
                assert caught.value.__cause__ is None
        else:
            owned_solution = fixture["inverse"].last_result
            assert owned_solution is not None
            assert int(owned_solution.handle) == 0
    finally:
        _destroy_g2a_p4_fixture(fixture)


def test_p4_condensed_timing_accumulates_one_refinement() -> None:
    factor, inverse, matrix = _timing_condensed_factor(always_inexact=False)
    rhs = _new_vector(matrix, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    solution = None
    timing: dict[str, float] = {}
    try:
        solution = factor.apply(rhs, timing=timing)
        assert inverse.solve_count == 2
        assert timing["storage_rhs_reduction_seconds"] == pytest.approx(2.0e-3)
        assert timing["factor_backsolve_seconds"] == pytest.approx(4.0e-3)
        assert timing["solution_recovery_seconds"] == pytest.approx(6.0e-3)
        assert timing["inner_apply_seconds"] == pytest.approx(1.2e-2)
        assert timing["native_action_and_residual_seconds"] > 0.0
        assert timing["native_action_matrix_mult_seconds"] > 0.0
        assert factor.diagnostics["last_solve"]["status"] == "passed"
        assert len(factor.diagnostics["last_solve"]["history"]) == 2
    finally:
        if solution is not None:
            solution.destroy()
        rhs.destroy()
        factor.destroy()
        matrix.destroy()


def test_p4_condensed_timing_survives_gate_failure() -> None:
    factor, inverse, matrix = _timing_condensed_factor(always_inexact=True)
    rhs = _new_vector(matrix, np.asarray([1.0 - 0.3j, 0.25 + 0.5j]))
    timing: dict[str, float] = {}
    try:
        with pytest.raises(P4PhysicalResidualGateError):
            factor.apply(rhs, timing=timing)
        assert inverse.solve_count == 3
        assert timing["storage_rhs_reduction_seconds"] == pytest.approx(3.0e-3)
        assert timing["factor_backsolve_seconds"] == pytest.approx(6.0e-3)
        assert timing["solution_recovery_seconds"] == pytest.approx(9.0e-3)
        assert timing["inner_apply_seconds"] == pytest.approx(1.8e-2)
        assert timing["native_action_and_residual_seconds"] > 0.0
        assert timing["native_action_matrix_mult_seconds"] > 0.0
        assert factor.diagnostics["last_solve"]["status"] == "gate_failed"
        assert len(factor.diagnostics["last_solve"]["history"]) == 3
    finally:
        rhs.destroy()
        factor.destroy()
        matrix.destroy()


@pytest.mark.parametrize(
    ("reason", "iterations", "accepted"),
    [
        (_DIVERGED_ITS, 128, True),
        (_DIVERGED_ITS, 127, False),
        (_DIVERGED_ITS, 129, False),
        (int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN), 128, False),
    ],
)
def test_side_inverse_fixed_ksp_budget_contract(
    reason: int,
    iterations: int,
    accepted: bool,
) -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(audit_callback=audit_records.append)
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    source_before = source.copy()
    target = operator.createVecLeft()
    approximate = source.copy()
    approximate.scale(0.25)
    real_ksp = inverse._ksp
    stub = _KspContractStub(approximate, reason, iterations, real_ksp.getPC())
    inverse._ksp = stub  # type: ignore[assignment]
    try:
        if accepted:
            inverse.apply(source, target)
            record = inverse.diagnostics["last_apply"]
            assert record["status"] == "INNER_APPROXIMATE_RETURN"
            assert record["reason"] == reason
            assert record["iterations"] == iterations
            assert record["ksp_positive"] is False
            assert record["explicit_true_target_reached"] is False
            assert record["relative_residual"] == pytest.approx(0.5)
            assert np.isfinite(record["residual_norm"])
            assert len(audit_records) == 1
            assert audit_records[0]["status"] == "INNER_APPROXIMATE_RETURN"
            assert _relative_difference(source, source_before) == 0.0
        else:
            with pytest.raises(RuntimeError):
                inverse.apply(source, target)
            record = inverse.diagnostics["last_apply"]
            assert record["status"] == "FAILED"
            assert record["reason"] == reason
            assert record["iterations"] == iterations
            assert record["explicit_true_target_reached"] == "not_measured"
            assert record["residual_norm"] == "not_measured"
            assert len(audit_records) == 1
            assert audit_records[0]["status"] == "FAILED"
            assert _relative_difference(source, source_before) == 0.0
    finally:
        inverse._ksp = real_ksp
        restored_real_ksp = inverse._ksp is real_ksp
        source.destroy()
        source_before.destroy()
        approximate.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()
    assert restored_real_ksp is True
    assert inverse._ksp is None


def test_v12_restart64_selection_requires_same_rhs_residual_and_wall_cost():
    """Synthetic scalar timings exercise the fixed restart64 choice boundary."""

    def evidence(
        eta32: float,
        eta64: float,
        baseline_seconds: tuple[float, ...],
        trial_seconds: tuple[float, ...],
        setup_seconds: tuple[float, ...],
    ) -> dict[str, object]:
        rank_count = len(baseline_seconds)
        baseline_max = max(baseline_seconds)
        setup_max = max(setup_seconds)
        trial_max = max(trial_seconds)
        baseline = [
            {
                "rank": rank,
                "rank_local_elapsed_seconds": baseline_seconds[rank],
                "max_rank_elapsed_seconds": baseline_max,
            }
            for rank in range(rank_count)
        ]
        trial = [
            {
                "rank": rank,
                "elapsed_local_seconds": trial_seconds[rank],
                "ksp_setup_elapsed_local_seconds": setup_seconds[rank],
            }
            for rank in range(rank_count)
        ]
        return side_inverse_module._v12_restart64_selection_evidence(
            eta32,
            eta64,
            baseline,
            trial,
            trial_elapsed_max_rank_seconds=trial_max,
            trial_setup_elapsed_max_rank_seconds=setup_max,
        )

    improved = evidence(0.8, 0.4, (0.20, 0.18), (0.15, 0.14), (0.01, 0.02))
    assert improved["eligible_for_64"] is True
    assert improved["residual_improved_by_at_least_10_percent"] is True
    assert improved["max_rank_trial_wall_with_one_setup_not_higher"] is True
    assert improved["log_residual_reduction_per_wall_not_lower"] is True
    assert improved["restart64_max_rank_trial_wall_with_setup_seconds"] == pytest.approx(
        0.16
    )

    # The eta is slightly better, but the same-RHS max-rank trial cost is much
    # worse; retaining restart32 is required even though eta64 < eta32.
    slower = evidence(0.8, 0.76, (0.20, 0.18), (2.0, 1.8), (0.1, 0.1))
    assert slower["eligible_for_64"] is False
    assert slower["max_rank_trial_wall_with_one_setup_not_higher"] is False

    baseline_missing = [
        {
            "rank": 0,
            "rank_local_elapsed_seconds": None,
            "max_rank_elapsed_seconds": None,
        }
    ]
    trial_one = [
        {
            "rank": 0,
            "elapsed_local_seconds": 0.1,
            "ksp_setup_elapsed_local_seconds": 0.01,
        }
    ]
    missing_cost = side_inverse_module._v12_restart64_selection_evidence(
        0.8,
        0.4,
        baseline_missing,
        trial_one,
        trial_elapsed_max_rank_seconds=0.1,
        trial_setup_elapsed_max_rank_seconds=0.01,
    )
    assert missing_cost["eligible_for_64"] is False
    assert missing_cost["restart32_max_rank_side_wall_seconds"] is None

    nonfinite_trial = [dict(trial_one[0], elapsed_local_seconds=float("nan"))]
    nonfinite_cost = side_inverse_module._v12_restart64_selection_evidence(
        0.8,
        0.4,
        [
            {
                "rank": 0,
                "rank_local_elapsed_seconds": 0.2,
                "max_rank_elapsed_seconds": 0.2,
            }
        ],
        nonfinite_trial,
        trial_elapsed_max_rank_seconds=0.1,
        trial_setup_elapsed_max_rank_seconds=0.01,
    )
    assert nonfinite_cost["eligible_for_64"] is False

    assert side_inverse_module._V12_RESTART64_SELECTION_RULE.startswith(
        "same_rhs_eta64_at_most_0.9_eta32"
    )


@pytest.mark.parametrize(
    ("history_case", "reason", "captured"),
    [
        ("two_windows_stalled", _DIVERGED_ITS, True),
        ("second_window_improves", _DIVERGED_ITS, False),
        ("positive_runtime_reason", 2, False),
    ],
    ids=["eligible", "ineligible_progress", "ineligible_reason"],
)
@pytest.mark.parametrize(
    "empty_owner", [False, True], ids=["owned_layout", "mpi2_empty_owner"]
)
def test_v12_restart32_candidate_capture_uses_armed_entry_and_owned_rhs(
    history_case: str,
    reason: int,
    captured: bool,
    empty_owner: bool,
) -> None:
    """Run the real armed capture entry with an explicitly synthetic scalar history.

    The PETSc Vec, production candidate method, rank-local copy/hash, and gate
    callback are real fixture paths.  Only the 64..128 residual scalars are
    synthetic; this is not evidence of a 128-step FE stagnation.
    """

    comm = MPI.COMM_WORLD
    if empty_owner and comm.size != 2:
        pytest.skip("the empty-owner capture layout requires MPI2")
    state: dict[str, object] = {
        "schema": "task041.v12.side_restart64_trial_state.v1",
        "policy_id": "task041_v12_bounded_inexact_modal_once_backup",
        "status": "capture_armed",
        "resolved": False,
        "pending": False,
        "trial_count": 0,
        "backup_method_active": True,
        "backup_commit_count": 1,
        "post_backup_side_solve_seen": {"bottom": False, "top": False},
        "outer_stagnation_confirmed": True,
        "capture_armed": True,
    }
    gate_requests: list[dict[str, object]] = []

    def tiny_fresh_gate(request):
        gate_requests.append(dict(request))
        return {
            "schema": "tiny_fixture_only_side_restart_memory_gate.v1",
            "pass": True,
            "status": "admitted_for_tiny_test_only",
            "phase": request["phase"],
            "restart": request["restart"],
        }

    inverse, owned = _fixed_q_real_cell_condensed_fixture(
        empty_owner=empty_owner,
        side_restart64_trial_state=state,
        side_restart64_memory_gate=tiny_fresh_gate,
    )
    source = inverse._operator.createVecRight()
    source_local_before = None
    source_global_before = None
    candidate = None
    try:
        local = source.getArray()
        local[:] = np.asarray(
            [0.75 - 0.25j + 0.1 * index for index in range(local.size)],
            dtype=PETSc.ScalarType,
        )
        source.assemble()
        source_local_before = np.array(
            source.getArray(readonly=True), dtype=np.complex128, copy=True
        )
        source_global_before = _gather_dense_vector(source)
        rhs_norm = float(source.norm())
        assert np.isfinite(rhs_norm) and rhs_norm > 0.0
        assert inverse._side_restart64_capture_is_armed() is True

        samples = []
        for iteration in range(64, 129):
            if history_case == "second_window_improves" and iteration >= 96:
                eta = 0.4
            else:
                eta = 0.5
            samples.append(
                {
                    "iteration": iteration,
                    "reported_residual": None,
                    "original_D_true_residual_norm": eta * rhs_norm,
                    "original_D_rhs_norm": rhs_norm,
                    "original_D_true_relative_residual": eta,
                    "finite": True,
                    "scope": "synthetic_scalar_history_for_capture_boundary_only",
                }
            )
        final_eta = float(samples[-1]["original_D_true_relative_residual"])
        solve_record = {
            "rank": int(comm.rank),
            "status": "INNER_APPROXIMATE_RETURN",
            "reason": int(reason),
            "iterations": 128,
            "elapsed_local_seconds": 0.2 + 0.01 * int(comm.rank),
            "elapsed_seconds": 0.2 + 0.01 * (comm.size - 1),
            "counts": {"delta": {"Q": 128, "H6": 128, "A6": 128}},
            "operation_seconds": {
                "per_rank_accumulated_seconds": {
                    "Q": 0.01,
                    "H6": 0.02,
                    "A6": 0.03,
                }
            },
            "p4_call_history": [],
        }
        result = inverse._consider_restart32_candidate(
            source,
            reason=int(reason),
            iterations=128,
            residual_audit={
                "rhs_norm": rhs_norm,
                "residual_norm": final_eta * rhs_norm,
                "relative_residual": final_eta,
            },
            samples=samples,
            solve_record=solve_record,
        )
        assert (result is not None) is captured
        np.testing.assert_array_equal(
            source.getArray(readonly=True), source_local_before
        )
        np.testing.assert_array_equal(_gather_dense_vector(source), source_global_before)
        if captured:
            assert result["status"] == "candidate_captured"
            assert state["status"] == "candidate_captured"
            assert state["candidate"]["captured_owner_sharded"] is True
            assert state["candidate"]["restart32_evidence"]["window_end_iterations"] == [
                [64, 96],
                [96, 128],
            ]
            work_rows = state["candidate"]["restart32_evidence"][
                "restart32_reference_work_by_rank"
            ]
            assert len(work_rows) == comm.size
            assert [row["rank"] for row in work_rows] == list(range(comm.size))
            candidate = inverse._side_restart64_candidate_rhs
            assert candidate is not None
            assert candidate.getSize() == source.getSize()
            assert candidate.getOwnershipRange() == source.getOwnershipRange()
            np.testing.assert_array_equal(
                candidate.getArray(readonly=True), source_local_before
            )
            assert len(gate_requests) == 1
            request = gate_requests[0]
            assert request["phase"] == "capture_restart32_rhs"
            assert request["rhs_local_sha256"] == (
                side_inverse_module._local_complex_vec_sha256(source)
            )
            assert request["rhs_local_sha256"] == (
                side_inverse_module._local_complex_vec_sha256(candidate)
            )
            layout = comm.allgather(
                {
                    "rank": comm.rank,
                    "local_size": int(request["local_vector_size"]),
                    "range": list(request["rhs_ownership_range"]),
                    "global_size": int(request["rhs_global_size"]),
                }
            )
            assert sum(row["local_size"] for row in layout) == source.getSize()
            assert layout[0]["range"][0] == 0
            assert layout[-1]["range"][1] == source.getSize()
            if empty_owner:
                assert [row["local_size"] for row in layout] == [0, 2]
            same_candidate = candidate
            second_result = inverse._consider_restart32_candidate(
                source,
                reason=int(reason),
                iterations=128,
                residual_audit={"relative_residual": final_eta},
                samples=samples,
                solve_record=solve_record,
            )
            assert second_result is None
            assert inverse._side_restart64_candidate_rhs is same_candidate
            assert len(gate_requests) == 1
        else:
            assert state["status"] == "capture_armed"
            assert inverse._side_restart64_candidate_rhs is None
            assert gate_requests == []
    finally:
        if candidate is not None:
            candidate.destroy()
            inverse._side_restart64_candidate_rhs = None
        source.destroy()
        inverse.destroy()
        owned["operator"].destroy()


@pytest.mark.parametrize(
    "empty_owner", [False, True], ids=["serial_layout", "mpi2_empty_owner"]
)
@pytest.mark.parametrize(
    "restore_refused", [False, True], ids=["restart32_restored", "restore_gate_refused"]
)
def test_v12_side_restart64_capacity_refusal_retains_real_cell_restart32_and_factor(
    empty_owner: bool,
    restore_refused: bool,
) -> None:
    """A denied tiny gate destroys the old KSP before restoring or refusing KSP32.

    The captured-candidate state is deliberately seeded to reach the post-capture
    safe boundary; this does not claim that the tiny solve met production capture
    eligibility or that the fixture callback is a real resource admission. The
    refusal branch retains the P4 factor and returns a typed no-KSP state for the
    outer safe-stop path; it does not bypass the restore gate.
    """

    comm = MPI.COMM_WORLD
    if empty_owner and comm.size != 2:
        pytest.skip("the empty-owner side-trial case requires MPI2")
    gate_requests: list[dict[str, object]] = []
    state: dict[str, object] = {
        "schema": "task041.v12.side_restart64_trial_state.v1",
        "policy_id": "task041_v12_bounded_inexact_modal_once_backup",
        "status": "armed",
        "resolved": False,
        "pending": False,
        "trial_count": 0,
    }

    def deny_tiny_workspace(request):
        gate_requests.append(dict(request))
        return {
            "schema": "tiny_fixture_only_side_restart_memory_gate.v1",
            "pass": request["phase"] == "restore_restart32" and not restore_refused,
            "status": (
                "admitted_for_tiny_test_only"
                if request["phase"] == "restore_restart32" and not restore_refused
                else "refused"
            ),
            "phase": request["phase"],
            "restart": request["restart"],
            "reason": "fixture refuses restart64 then admits a fresh restart32 workspace",
        }

    inverse, owned = _fixed_q_real_cell_condensed_fixture(
        empty_owner=empty_owner,
        side_restart64_trial_state=state,
        side_restart64_memory_gate=deny_tiny_workspace,
    )
    p4 = owned["p4_factor"]
    source = inverse._operator.createVecRight()
    source.set(PETSc.ScalarType(1.0 + 0.25j))
    candidate = source.duplicate()
    source.copy(candidate)
    restart32_handle = inverse._ksp
    try:
        assert isinstance(p4, P4CondensedExactFactor)
        assert isinstance(p4.inverse, P4CellCondensedInverse)
        assert restart32_handle is not None
        assert inverse._gmres_restart == 32
        state.update(
            {
                "status": "candidate_captured",
                "resolved": False,
                "pending": True,
                "trial_count": 0,
                "candidate_side": "bottom",
                "candidate": {
                    "side": "bottom",
                    "original_D_relative_residual": 0.25,
                    "original_D_rhs_norm": float(candidate.norm()),
                    # This branch seeds the post-capture state directly. Keep
                    # the production candidate schema without inventing solve
                    # timings or claiming a real restart32 solve occurred.
                    "restart32_evidence": {
                        "restart32_reference_work_by_rank": [
                            {"rank": int(rank), "fixture_seeded": True}
                            for rank in range(comm.size)
                        ]
                    },
                },
            }
        )
        inverse._side_restart64_candidate_rhs = candidate

        result = inverse.run_side_restart64_trial()
        candidate = None
        assert result["status"] == (
            "capacity_gate_refused_restart32_restore"
            if restore_refused
            else "capacity_gate_refused"
        )
        assert result["stage"] == (
            "restore_restart32" if restore_refused else "allocate_restart64"
        )
        assert result["restart32_original_handle_destroyed"] is True
        assert result["restart32_handle_retained"] is False
        assert result["restart32_restore_required"] is restore_refused
        assert result["restart32_restored"] is not restore_refused
        assert result["restart32_restored_handle_live"] is not restore_refused
        assert result["restart32_restore_gate"]["phase"] == "restore_restart32"
        assert result["restart32_restore_gate"]["pass"] is not restore_refused
        assert result["candidate_rhs_binding"]["restart32_reference_work_by_rank"] == (
            state["candidate"]["restart32_evidence"][
                "restart32_reference_work_by_rank"
            ]
        )
        assert result["factor_handle_retained"] is True
        assert state["trial_count"] == 1
        assert state["resolved"] is False
        assert (inverse._ksp is None) is restore_refused
        if not restore_refused:
            assert inverse._ksp is not restart32_handle
        assert inverse._gmres_restart == 32
        assert inverse._nested_ksp_created_count == (1 if restore_refused else 2)
        assert inverse._nested_ksp_destroy_count == 1
        assert inverse._p4_factor is p4
        assert p4._destroyed is False
        assert p4.inverse.destroyed is False
        assert len(gate_requests) == 2
        request = gate_requests[0]
        assert request["phase"] == "allocate_restart64"
        assert request["existing_restart32_ksp_live"] is False
        assert request["candidate_rhs_live"] is True
        assert request["workspace_lifecycle"] == (
            "restart32_ksp_destroyed_plus_candidate_rhs_live_plus_full_new_restart64_workspace"
        )
        assert request["restart"] == 64
        restore_request = gate_requests[1]
        assert restore_request["phase"] == "restore_restart32"
        assert restore_request["existing_restart32_ksp_live"] is False
        assert restore_request["candidate_rhs_live"] is False
        assert restore_request["workspace_lifecycle"] == (
            "restart64_ksp_and_candidate_rhs_destroyed_plus_full_new_restart32_workspace"
        )
        assert restore_request["restart"] == 32
        local_range = list(map(int, request["rhs_ownership_range"]))
        assert local_range[1] - local_range[0] == request["local_vector_size"]
        operator_local_rows, operator_local_columns = map(
            int,
            (
                request["operator_local_rows"],
                request["operator_local_columns"],
            ),
        )
        assert operator_local_columns == request["local_vector_size"]
        assert operator_local_rows >= 0
        owner_rows = comm.allgather(
            {
                "rank": comm.rank,
                "range": local_range,
                "local_size": request["local_vector_size"],
                "operator_local_rows": operator_local_rows,
                "operator_local_columns": operator_local_columns,
                "global_size": request["rhs_global_size"],
            }
        )
        if empty_owner:
            assert [row["local_size"] for row in owner_rows] == [0, 2]
        assert owner_rows[0]["range"][0] == 0
        assert owner_rows[-1]["range"][1] == owner_rows[0]["global_size"]
        assert sum(row["operator_local_rows"] for row in owner_rows) == owner_rows[0]["global_size"]
        assert sum(row["operator_local_columns"] for row in owner_rows) == owner_rows[0]["global_size"]
        with pytest.raises(RuntimeError, match="not at its sealed safe boundary"):
            inverse.run_side_restart64_trial()
        assert (inverse._ksp is None) is restore_refused
        if not restore_refused:
            assert inverse._ksp is not restart32_handle
        assert inverse._p4_factor is p4
    finally:
        if candidate is not None:
            candidate.destroy()
        source.destroy()
        inverse.destroy()
        owned["operator"].destroy()


@pytest.mark.parametrize("empty_owner", [False, True], ids=["serial_layout", "mpi2_empty_owner"])
def test_v12_side_restart64_trial_borrows_p4_and_records_real_original_D_residual(
    empty_owner: bool,
) -> None:
    """The tiny admitted trial solves the same RHS and audits the original D.

    The candidate transition is seeded; the restart32/apply and restart64 solves,
    same-factor use, and original-D residuals are actual fixture operations. The
    memory callback only admits this tiny test and is not a fresh-capacity proof.
    """

    comm = MPI.COMM_WORLD
    if empty_owner and comm.size != 2:
        pytest.skip("the empty-owner side-trial case requires MPI2")
    gate_requests: list[dict[str, object]] = []
    state: dict[str, object] = {
        "schema": "task041.v12.side_restart64_trial_state.v1",
        "policy_id": "task041_v12_bounded_inexact_modal_once_backup",
        "status": "armed",
        "resolved": False,
        "pending": False,
        "trial_count": 0,
    }

    def admit_tiny_workspace(request):
        gate_requests.append(dict(request))
        return {
            "schema": "tiny_fixture_only_side_restart_memory_gate.v1",
            "pass": True,
            "status": "admitted_for_tiny_test_only",
            "phase": request["phase"],
            "restart": request["restart"],
        }

    inverse, owned = _fixed_q_real_cell_condensed_fixture(
        empty_owner=empty_owner,
        side_restart64_trial_state=state,
        side_restart64_memory_gate=admit_tiny_workspace,
    )
    p4 = owned["p4_factor"]
    source = inverse._operator.createVecRight()
    source.set(PETSc.ScalarType(0.75 - 0.2j))
    source_before = _gather_dense_vector(source)
    solution32 = inverse._operator.createVecRight()
    candidate = None
    restart32_handle = inverse._ksp
    try:
        assert isinstance(p4, P4CondensedExactFactor)
        assert isinstance(p4.inverse, P4CellCondensedInverse)
        assert restart32_handle is not None
        assert inverse._gmres_restart == 32
        inverse.apply(source, solution32)
        restart32_residual = inverse._explicit_residual(source, solution32)
        assert np.isfinite(restart32_residual["relative_residual"])
        assert restart32_residual["rhs_norm"] > 0.0
        restart32_work_by_rank = comm.allgather(
            inverse._restart32_reference_work(inverse._last_apply)
        )
        assert [row["rank"] for row in restart32_work_by_rank] == list(
            range(comm.size)
        )

        candidate = source.duplicate()
        source.copy(candidate)
        np.testing.assert_array_equal(
            _gather_dense_vector(candidate), source_before
        )
        inverse._side_restart64_candidate_rhs = candidate
        state.update(
            {
                "status": "candidate_captured",
                "resolved": False,
                "pending": True,
                "trial_count": 0,
                "candidate_side": "bottom",
                "candidate": {
                    "side": "bottom",
                    "original_D_relative_residual": float(
                        restart32_residual["relative_residual"]
                    ),
                    "original_D_rhs_norm": float(restart32_residual["rhs_norm"]),
                    "global_size": int(source.getSize()),
                    "captured_owner_sharded": True,
                    "restart32_evidence": {
                        "restart32_reference_work_by_rank": restart32_work_by_rank
                    },
                },
            }
        )
        record = inverse.run_side_restart64_trial()
        candidate = None
        assert record["status"] in {
            "trial_completed_selected_64",
            "trial_completed_retained_32",
        }
        assert record["same_p4_factor_handle_all_ranks"] is True
        selection = record["selection_evidence"]
        assert selection["eligible_for_64"] is (
            record["status"] == "trial_completed_selected_64"
        )
        assert selection["rule_id"] == side_inverse_module._V12_RESTART64_SELECTION_RULE
        if record["selected_restart"] == 64:
            assert selection["residual_improved_by_at_least_10_percent"] is True
            assert selection["max_rank_trial_wall_with_one_setup_not_higher"] is True
            assert selection["log_residual_reduction_per_wall_not_lower"] is True
        assert record["trial_transition_wall_including_one_setup_max_rank_seconds"] == pytest.approx(
            selection["restart64_max_rank_trial_wall_with_setup_seconds"]
        )
        assert record[
            "cumulative_side_wall_seconds_including_transition_setup"
        ] == pytest.approx(
            record["cumulative_side_apply_seconds"]
            + record["cumulative_restart_transition_ksp_setup_seconds"]
        )
        assert record["restart32_relative_residual"] == restart32_residual[
            "relative_residual"
        ]
        assert record["candidate_rhs_binding"]["original_D_rhs_norm"] == source.norm()
        assert record["restart64_mgs_setup"]["preallocate_vectors"] is True
        assert record["restart64_mgs_setup"]["orthogonalization"] == (
            "modified_gram_schmidt"
        )
        assert record["restart64_mgs_setup"]["readback_matches"] is True
        residual = record["restart64_original_D_residual"]
        assert set(residual) == {
            "rhs_norm",
            "solution_norm",
            "residual_norm",
            "relative_residual",
        }
        assert all(
            np.isfinite(float(residual[key])) and float(residual[key]) >= 0.0
            for key in residual
        )
        assert residual["rhs_norm"] == source.norm()
        assert residual["relative_residual"] == record[
            "restart64_relative_residual"
        ]
        assert np.isclose(
            residual["relative_residual"],
            residual["residual_norm"] / residual["rhs_norm"],
            rtol=1.0e-12,
            atol=1.0e-15,
        )
        rank_records = record["restart64_rank_records"]
        assert len(rank_records) == comm.size
        assert all(
            row["same_p4_factor_handle_local"] is True
            and row["candidate_rhs_unchanged_local"] is True
            and row["original_D_residual"] == residual
            for row in rank_records
        )
        restart32_work = record["candidate_rhs_binding"][
            "restart32_reference_work_by_rank"
        ]
        assert isinstance(restart32_work, list)
        assert len(restart32_work) == comm.size
        for rank, row in enumerate(restart32_work):
            assert row["rank"] == rank
            assert type(row["iterations"]) is int
            assert row["iterations"] >= 0
            assert isinstance(row["reason"], int)
            for timing_key in (
                "rank_local_elapsed_seconds",
                "max_rank_elapsed_seconds",
            ):
                assert np.isfinite(float(row[timing_key]))
                assert float(row[timing_key]) >= 0.0
            assert set(row["rank_local_operation_seconds"]) == {"Q", "H6", "A6"}
            assert isinstance(row["rank_local_count_delta"], dict)
            assert isinstance(row["p4_costs"], dict)
            assert type(row["p4_costs"]["call_count"]) is int
        for rank, row in enumerate(rank_records):
            assert row["rank"] == rank
            assert np.isfinite(float(row["elapsed_local_seconds"]))
            assert np.isfinite(float(row["ksp_setup_elapsed_local_seconds"]))
            assert row["ksp_setup_elapsed_local_seconds"] >= 0.0
            assert set(row["operation_seconds"]["per_rank_accumulated_seconds"]) == {
                "Q",
                "H6",
                "A6",
            }
            assert isinstance(row["rank_local_count_delta"], dict)
            assert isinstance(row["p4_costs"], dict)
            assert type(row["p4_costs"]["call_count"]) is int
        assert inverse._p4_factor is p4
        assert p4._destroyed is False
        assert p4.inverse.destroyed is False
        assert inverse._side_restart64_candidate_rhs is None
        assert state["trial_count"] == 1
        assert len(gate_requests) == (
            1 if record["status"] == "trial_completed_selected_64" else 2
        )
        assert gate_requests[0]["phase"] == "allocate_restart64"
        assert gate_requests[0]["existing_restart32_ksp_live"] is False
        assert gate_requests[0]["candidate_rhs_live"] is True
        assert gate_requests[0]["operator_local_columns"] == gate_requests[0]["local_vector_size"]
        if empty_owner:
            expected_range = [0, 0] if comm.rank == 0 else [0, 2]
            assert gate_requests[0]["rhs_ownership_range"] == expected_range
        np.testing.assert_array_equal(_gather_dense_vector(source), source_before)
        if record["status"] == "trial_completed_retained_32":
            assert inverse._ksp is not restart32_handle
            assert inverse._gmres_restart == 32
            assert record["restart32_original_handle_destroyed"] is True
            assert record["restart32_handle_retained"] is False
            assert record["restart32_restore_required"] is False
            assert record["restart32_restored"] is True
            assert record["restart32_restore_gate"]["phase"] == "restore_restart32"
            assert record["restart32_restore_gate"]["pass"] is True
            assert gate_requests[1]["phase"] == "restore_restart32"
            assert gate_requests[1]["candidate_rhs_live"] is False
            assert gate_requests[1]["existing_restart32_ksp_live"] is False
            expected_restart = 32
        else:
            assert inverse._ksp is not restart32_handle
            assert inverse._gmres_restart == 64
            assert record["restart32_original_handle_destroyed"] is True
            assert record["restart32_handle_retained"] is False
            assert record["restart32_restore_required"] is False
            assert record["restart64_handle_retained"] is True
            expected_restart = 64
        contract = inverse._ksp_contract_audit()
        assert contract["pass"] is True
        assert contract["actual"]["restart"] == expected_restart
        if record["status"] == "trial_completed_retained_32":
            assert inverse._nested_ksp_created_count == 3
            assert inverse._nested_ksp_destroy_count == 2
        else:
            assert inverse._nested_ksp_created_count == 2
            assert inverse._nested_ksp_destroy_count == 1
        with pytest.raises(RuntimeError, match="not at its sealed safe boundary"):
            inverse.run_side_restart64_trial()
        assert inverse._p4_factor is p4
    finally:
        if candidate is not None:
            candidate.destroy()
        source.destroy()
        solution32.destroy()
        inverse.destroy()
        owned["operator"].destroy()
