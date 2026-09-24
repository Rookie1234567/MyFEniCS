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

from src.solvers import physical_balanced_side_inverse as side_inverse_module
from src.solvers.hybrid_local_dtn_action import HybridLocalDtnActionSystem
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


def _scale_matrix(size: int, scale: complex) -> tuple[PETSc.Mat, _ScaleContext]:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    local_rows = size // comm.Get_size()
    context = _ScaleContext(scale)
    matrix = PETSc.Mat().createPython(
        ((local_rows, size), (local_rows, size)),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    del rank
    return matrix, context


class _IdentityCondensed:
    def __init__(self, size: int) -> None:
        comm = MPI.COMM_WORLD
        self.comm = comm
        self.active_rows = size
        self.full_rows = size
        self.owned_active_rows = size // comm.Get_size()
        first = self.owned_active_rows * comm.Get_rank()
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
        return {"pair_fine_to_coarse": [6, 4], "owner_local": True}

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
        correction_callback = diagnostic_kwargs.get("diagnostic_callback")
        rhs.copy(solution)
        self.solve_count += 1 + correction_steps
        self.last_solve = {
            "backsolve_count": 1 + correction_steps,
            "refinement_count": correction_steps,
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
        correction_callback = diagnostic_kwargs.get("diagnostic_callback")
        self.solve_count += 1 + correction_steps
        self.last_physical_rhs_norm = float(source.norm())
        self.last_solve = {
            "backsolve_count": 1 + correction_steps,
            "refinement_count": correction_steps,
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
    ) -> None:
        self.block = np.asarray(block, dtype=np.complex128)
        self.perturb_port = complex(perturb_port)
        self.perturb_fe = complex(perturb_fe)
        self.nonfinite_first_fe = bool(nonfinite_first_fe)
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
        values = np.asarray(port_rhs, dtype=np.complex128)
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
) -> tuple[PETSc.Mat, _DensePythonMatrix]:
    global _G2A_MATRIX_SEQUENCE
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    local_base = base_rows // comm.size + int(rank < base_rows % comm.size)
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
    }
    factor_matrix, factor_context = _dense_python_matrix(
        block,
        base_rows=2,
        appended_rows=1,
        purpose="augmented",
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
    def __init__(self, size: int) -> None:
        self.matrix, self.context = _scale_matrix(size, 1.0)
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
) -> tuple[SideBalancedInverse, dict[str, object]]:
    operator, operator_context = _scale_matrix(size, 2.0)
    condensed = _IdentityCondensed(size)
    side_system = SimpleNamespace(
        A=operator,
        cfg=SimpleNamespace(nedelec_degree=6),
        static_condensation=SimpleNamespace(condensed=condensed),
        side="bottom",
    )
    full_action = _FullAction(size)
    p4_factor = _IdentityP4(size) if p4_factor is None else p4_factor
    transfer = _IdentityTransfer()
    h6 = _IdentityH6()
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
    def fake_full_action(_side_system):
        action = _FullAction(2)
        action.V = object()
        action.floquet_data = object()
        captured["full_action"] = action
        return action

    def fake_p4(_side_system, *, lifecycle_callback=None):
        captured["p4_callback"] = lifecycle_callback
        factor = _IdentityP4(2)
        captured["p4"] = factor
        return factor

    def fake_condensed_p4(_side_system, *, lifecycle_callback=None):
        captured["condensed_p4_callback"] = lifecycle_callback
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
    ):
        transfer = _IdentityTransfer(
            default_variant=(
                "optimized"
                if optimization_profile == "task041_schur_speed_v2"
                else "legacy"
            )
        )
        captured["transfer"] = transfer
        captured["optimization_profile"] = optimization_profile
        captured["support_policy"] = support_policy
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
        assert "condensed_p4" in captured
        assert "p4" not in captured
        assert captured["condensed_p4_callback"] is None
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
    finally:
        if result is not None:
            result.destroy()
        _destroy_g2a_p4_fixture(fixture)


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
