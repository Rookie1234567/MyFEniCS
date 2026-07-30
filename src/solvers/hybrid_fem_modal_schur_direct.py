"""Task032 Modal-Schur direct reference with explicit scalability limits.

The fast/minimal paths validate current-scale algebra and lifecycle behavior.
Their replicated dense modal block, all-mode dense multi-RHS, and local direct
LU are not scalable to the 0.7 nm service target without redesign.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .common_3d_solve import _petsc_factor_inventory
from .hybrid_fem_modal_augmented_direct import (
    internal_modal_constraint_matrix,
    internal_modal_rhs_correction,
)
from .hybrid_local_dtn import HybridLocalDtnSystem
from .hybrid_static_field_recovery import (
    HybridStaticRecoveredLocalField,
    recover_hybrid_static_local_field,
)


MUMPS_WORKSPACE_RELAXATION_PERCENT = 100


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _modal_vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    vector.set(0.0)
    first, last = vector.getOwnershipRange()
    if last > first:
        vector.setValues(
            np.arange(first, last, dtype=PETSc.IntType),
            np.asarray(values[first:last], dtype=PETSc.ScalarType),
        )
    vector.assemble()
    return vector


def _replicated_modal_vector(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    local = None
    if comm.rank == owner:
        local = np.asarray(
            vector.getValues(np.arange(vector.getSize(), dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)


def _factor_local(matrix: PETSc.Mat) -> tuple[PETSc.KSP, float]:
    comm = matrix.getComm().tompi4py()
    ksp = PETSc.KSP().create(comm)
    ksp.setType(PETSc.KSP.Type.PREONLY)
    ksp.setErrorIfNotConverged(True)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.LU)
    pc.setFactorSolverType("mumps")
    ksp.setOperators(matrix)
    pc.setFactorSetUpSolverType()
    factor = pc.getFactorMatrix()
    factor.setMumpsIcntl(14, MUMPS_WORKSPACE_RELAXATION_PERCENT)
    started = time.perf_counter()
    ksp.setUp()
    return ksp, _max_elapsed(comm, started)


def _local_factor_inventory(ksp: PETSc.KSP) -> dict:
    inventory = _petsc_factor_inventory(ksp)
    inventory["mumps_icntl_14_requested_percent"] = (
        MUMPS_WORKSPACE_RELAXATION_PERCENT
    )
    try:
        observed = int(
            ksp.getPC().getFactorMatrix().getMumpsIcntl(14)
        )
    except Exception:
        observed = None
    inventory["mumps_icntl_14_observed_percent"] = observed
    inventory["mumps_workspace_relaxation_verified"] = (
        observed == MUMPS_WORKSPACE_RELAXATION_PERCENT
    )
    return inventory


def _insert_dense_columns(
    dense_local: np.ndarray,
    row_start: int,
    matrix: PETSc.Mat,
    destination_start: int,
    factors: np.ndarray,
) -> None:
    first, last = matrix.getOwnershipRange()
    if first != row_start or last - first != dense_local.shape[0]:
        raise ValueError("Local traction and FEM matrix row ownership differ.")
    for row in range(first, last):
        columns, values = matrix.getRow(row)
        if len(columns):
            column_array = np.asarray(columns, dtype=np.int64)
            dense_local[row - first, destination_start + column_array] += (
                np.asarray(values, dtype=np.complex128) * factors[column_array]
            )


def _multi_rhs_matrix(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
) -> PETSc.Mat:
    """Create [f, C] as one distributed dense RHS matrix for sparse LU."""

    count = coupling.mode_count_per_direction
    internal_count = 2 * count
    row_start, row_end = system.A.getOwnershipRange()
    dense = PETSc.Mat().createDense(
        size=((row_end - row_start, system.global_size), internal_count + 1),
        comm=system.local_mesh.mesh.comm,
    )
    local = dense.getDenseArray()
    local[:] = 0.0
    rhs = np.asarray(system.b.getArray(readonly=True), dtype=np.complex128)
    if rhs.shape != (row_end - row_start,):
        dense.destroy()
        raise ValueError("Local RHS ownership differs from its FEM matrix.")
    local[:, 0] = rhs
    if system.side == "bottom":
        block = coupling.bottom
        positive_factors = np.ones(count, dtype=np.complex128)
        negative_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
    else:
        block = coupling.top
        positive_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        negative_factors = np.ones(count, dtype=np.complex128)
    _insert_dense_columns(
        local, row_start, block.positive_traction, 1, positive_factors
    )
    _insert_dense_columns(
        local,
        row_start,
        block.negative_traction,
        1 + count,
        negative_factors,
    )
    dense.assemble()
    return dense


def _project_multi_rhs(
    projection: PETSc.Mat,
    solved: PETSc.Mat,
) -> np.ndarray:
    result = np.empty(
        (projection.getSize()[0], solved.getSize()[1]), dtype=np.complex128
    )
    projected = projection.createVecLeft()
    try:
        for column in range(solved.getSize()[1]):
            field = solved.getColumnVector(column)
            try:
                projection.mult(field, projected)
                result[:, column] = _replicated_modal_vector(projected)
            finally:
                field.destroy()
    finally:
        projected.destroy()
    return result


def _local_schur_response(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    factor: PETSc.KSP,
) -> tuple[np.ndarray, float, int]:
    """Return D A^-1 [f,C] using one MatMatSolve call."""

    right_hand_sides = _multi_rhs_matrix(system, coupling)
    solved = right_hand_sides.duplicate(copy=False)
    started = time.perf_counter()
    factor.matSolve(right_hand_sides, solved)
    elapsed = _max_elapsed(system.local_mesh.mesh.comm, started)
    projection = coupling.bottom.projection if system.side == "bottom" else coupling.top.projection
    try:
        response = _project_multi_rhs(projection, solved)
        payload_bytes = int(
            2
            * system.global_size
            * right_hand_sides.getSize()[1]
            * np.dtype(np.complex128).itemsize
        )
    finally:
        solved.destroy()
        right_hand_sides.destroy()
    return response, elapsed, payload_bytes


@dataclass
class HybridModalSchurDirectSystem:
    modal_schur: np.ndarray
    modal_rhs: np.ndarray
    modal_constraint: np.ndarray
    bottom_contribution: np.ndarray
    top_contribution: np.ndarray
    bottom_factor: PETSc.KSP | None
    top_factor: PETSc.KSP | None
    factor_setup_seconds: dict[str, float]
    multi_rhs_solve_seconds: dict[str, float]
    multi_rhs_count: int
    transient_dense_rhs_solution_bytes: dict[str, int]
    factor_inventory: dict[str, dict]
    modal_schur_condition: float
    lifecycle_strategy: str = "fast_direct"
    recovery_refactor_required: bool = False
    dense_interface_square_formed: bool = False
    full_field_or_mode_gathered: bool = False
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self.bottom_factor is not None:
            self.bottom_factor.destroy()
            self.bottom_factor = None
        if self.top_factor is not None:
            self.top_factor.destroy()
            self.top_factor = None
        self._destroyed = True


@dataclass
class HybridModalSchurDirectSolution:
    bottom: PETSc.Vec
    top: PETSc.Vec
    modal_amplitudes: np.ndarray
    relative_residual: float
    bottom_relative_residual: float
    top_relative_residual: float
    modal_relative_residual: float
    modal_solve_seconds: float
    recovery_seconds: float
    recovery_factor_setup_seconds: dict[str, float] = field(default_factory=dict)
    converged_reason: int = 1
    factor_solver: str = "mumps_multi_rhs_modal_schur"
    bottom_recovered: HybridStaticRecoveredLocalField | None = None
    top_recovered: HybridStaticRecoveredLocalField | None = None
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def bottom_physical(self):
        return (
            self.bottom_recovered.electric_field
            if self.bottom_recovered is not None
            else self.bottom
        )

    @property
    def top_physical(self):
        return (
            self.top_recovered.electric_field
            if self.top_recovered is not None
            else self.top
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom.destroy()
        self.top.destroy()
        self._destroyed = True


def build_hybrid_modal_schur_direct_system(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> HybridModalSchurDirectSystem:
    """Factor both sparse local blocks and assemble only the small modal Schur."""

    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Hybrid local systems must be ordered bottom, top.")
    if stage_callback is not None:
        stage_callback("bottom_local_factor")
    bottom_factor, bottom_setup = _factor_local(bottom_system.A)
    top_factor = None
    try:
        if stage_callback is not None:
            stage_callback("bottom_schur_contribution")
        bottom_response, bottom_solve, bottom_bytes = _local_schur_response(
            bottom_system, coupling, bottom_factor
        )
        if stage_callback is not None:
            stage_callback("top_local_factor")
        top_factor, top_setup = _factor_local(top_system.A)
        if stage_callback is not None:
            stage_callback("top_schur_contribution")
        top_response, top_solve, top_bytes = _local_schur_response(
            top_system, coupling, top_factor
        )
        factor_inventory = {
            "bottom": _local_factor_inventory(bottom_factor),
            "top": _local_factor_inventory(top_factor),
        }
        count = coupling.mode_count_per_direction
        internal_count = 2 * count
        bottom_contribution = np.zeros(
            (internal_count, internal_count + 1), dtype=np.complex128
        )
        top_contribution = np.zeros_like(bottom_contribution)
        bottom_contribution[:count, :] = bottom_response
        top_contribution[count:, :] = top_response
        modal_constraint = internal_modal_constraint_matrix(coupling)
        modal_schur = (
            modal_constraint
            - bottom_contribution[:, 1:]
            - top_contribution[:, 1:]
        )
        modal_rhs = (
            internal_modal_rhs_correction(coupling)
            - bottom_contribution[:, 0]
            - top_contribution[:, 0]
        )
        condition = float(np.linalg.cond(modal_schur))
        if not np.isfinite(condition):
            raise RuntimeError("The Task32 modal Schur matrix is singular or non-finite.")
        return HybridModalSchurDirectSystem(
            modal_schur=modal_schur,
            modal_rhs=modal_rhs,
            modal_constraint=modal_constraint,
            bottom_contribution=bottom_contribution,
            top_contribution=top_contribution,
            bottom_factor=bottom_factor,
            top_factor=top_factor,
            factor_setup_seconds={"bottom": bottom_setup, "top": top_setup},
            multi_rhs_solve_seconds={"bottom": bottom_solve, "top": top_solve},
            multi_rhs_count=internal_count + 1,
            transient_dense_rhs_solution_bytes={
                "bottom": bottom_bytes,
                "top": top_bytes,
            },
            factor_inventory=factor_inventory,
            modal_schur_condition=condition,
            lifecycle_strategy="fast_direct",
            recovery_refactor_required=False,
        )
    except Exception:
        bottom_factor.destroy()
        if top_factor is not None:
            top_factor.destroy()
        raise


def build_hybrid_modal_schur_memory_minimal_system(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> HybridModalSchurDirectSystem:
    """Build the modal Schur while retaining no local sparse LU factor.

    The bottom and top factors are formed sequentially, used for their dense
    multi-RHS Schur contribution, and released immediately. Field recovery
    therefore refactors each local block once after the modal solve. This is
    the explicit Task32 memory-minimal lifecycle; it trades setup time for a
    lower simultaneous factor footprint without changing the algebra.
    """

    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Hybrid local systems must be ordered bottom, top.")
    bottom_factor = None
    top_factor = None
    try:
        if stage_callback is not None:
            stage_callback("bottom_local_factor")
        bottom_factor, bottom_setup = _factor_local(bottom_system.A)
        if stage_callback is not None:
            stage_callback("bottom_schur_contribution")
        bottom_response, bottom_solve, bottom_bytes = _local_schur_response(
            bottom_system, coupling, bottom_factor
        )
        bottom_inventory = _local_factor_inventory(bottom_factor)
    finally:
        if bottom_factor is not None:
            bottom_factor.destroy()
            bottom_factor = None
    try:
        if stage_callback is not None:
            stage_callback("top_local_factor")
        top_factor, top_setup = _factor_local(top_system.A)
        if stage_callback is not None:
            stage_callback("top_schur_contribution")
        top_response, top_solve, top_bytes = _local_schur_response(
            top_system, coupling, top_factor
        )
        top_inventory = _local_factor_inventory(top_factor)
    finally:
        if top_factor is not None:
            top_factor.destroy()
            top_factor = None

    count = coupling.mode_count_per_direction
    internal_count = 2 * count
    bottom_contribution = np.zeros(
        (internal_count, internal_count + 1), dtype=np.complex128
    )
    top_contribution = np.zeros_like(bottom_contribution)
    bottom_contribution[:count, :] = bottom_response
    top_contribution[count:, :] = top_response
    modal_constraint = internal_modal_constraint_matrix(coupling)
    modal_schur = (
        modal_constraint
        - bottom_contribution[:, 1:]
        - top_contribution[:, 1:]
    )
    modal_rhs = (
        internal_modal_rhs_correction(coupling)
        - bottom_contribution[:, 0]
        - top_contribution[:, 0]
    )
    condition = float(np.linalg.cond(modal_schur))
    if not np.isfinite(condition):
        raise RuntimeError("The Task32 modal Schur matrix is singular or non-finite.")
    return HybridModalSchurDirectSystem(
        modal_schur=modal_schur,
        modal_rhs=modal_rhs,
        modal_constraint=modal_constraint,
        bottom_contribution=bottom_contribution,
        top_contribution=top_contribution,
        bottom_factor=None,
        top_factor=None,
        factor_setup_seconds={"bottom": bottom_setup, "top": top_setup},
        multi_rhs_solve_seconds={"bottom": bottom_solve, "top": top_solve},
        multi_rhs_count=internal_count + 1,
        transient_dense_rhs_solution_bytes={
            "bottom": bottom_bytes,
            "top": top_bytes,
        },
        factor_inventory={
            "bottom": bottom_inventory,
            "top": top_inventory,
        },
        modal_schur_condition=condition,
        lifecycle_strategy="memory_minimal_direct",
        recovery_refactor_required=True,
    )


def _coupling_action(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    modal: np.ndarray,
) -> PETSc.Vec:
    count = coupling.mode_count_per_direction
    if system.side == "bottom":
        block = coupling.bottom
        positive_values = modal[:count]
        negative_values = (
            np.asarray(coupling.propagation.backward.factors) * modal[count:]
        )
    else:
        block = coupling.top
        positive_values = (
            np.asarray(coupling.propagation.forward.factors) * modal[:count]
        )
        negative_values = modal[count:]
    positive_source = _modal_vector(block.positive_traction, positive_values)
    negative_source = _modal_vector(block.negative_traction, negative_values)
    result = block.positive_traction.createVecLeft()
    temporary = block.negative_traction.createVecLeft()
    try:
        block.positive_traction.mult(positive_source, result)
        block.negative_traction.mult(negative_source, temporary)
        result.axpy(PETSc.ScalarType(1.0), temporary)
    finally:
        positive_source.destroy()
        negative_source.destroy()
        temporary.destroy()
    return result


def _recover_local_field(
    system: HybridLocalDtnSystem,
    factor: PETSc.KSP,
    coupling: HybridInternalModeCoupling,
    modal: np.ndarray,
) -> PETSc.Vec:
    coupling_value = _coupling_action(system, coupling, modal)
    rhs = system.b.duplicate()
    solution = system.b.duplicate()
    try:
        system.b.copy(rhs)
        rhs.axpy(PETSc.ScalarType(-1.0), coupling_value)
        factor.solve(rhs, solution)
    finally:
        coupling_value.destroy()
        rhs.destroy()
    return solution


def _local_relative_residual(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    field: PETSc.Vec,
    modal: np.ndarray,
) -> tuple[float, float]:
    residual = system.A.createVecLeft()
    coupling_value = _coupling_action(system, coupling, modal)
    try:
        system.A.mult(field, residual)
        operator_norm = float(residual.norm())
        residual.axpy(PETSc.ScalarType(1.0), coupling_value)
        residual.axpy(PETSc.ScalarType(-1.0), system.b)
        absolute = float(residual.norm())
        scale = max(
            operator_norm,
            float(coupling_value.norm()),
            float(system.b.norm()),
            1.0e-30,
        )
        return absolute, float(absolute / scale)
    finally:
        coupling_value.destroy()
        residual.destroy()


def _modal_residual(
    system: HybridModalSchurDirectSystem,
    coupling: HybridInternalModeCoupling,
    bottom: PETSc.Vec,
    top: PETSc.Vec,
    modal: np.ndarray,
) -> tuple[float, float]:
    bottom_projection = coupling.bottom.projection.createVecLeft()
    top_projection = coupling.top.projection.createVecLeft()
    try:
        coupling.bottom.projection.mult(bottom, bottom_projection)
        coupling.top.projection.mult(top, top_projection)
        actual = np.concatenate(
            (
                _replicated_modal_vector(bottom_projection),
                _replicated_modal_vector(top_projection),
            )
        ) + system.modal_constraint @ modal
    finally:
        bottom_projection.destroy()
        top_projection.destroy()
    absolute = float(np.linalg.norm(actual))
    scale = max(
        float(np.linalg.norm(system.modal_constraint @ modal)),
        float(np.linalg.norm(actual)),
        1.0e-30,
    )
    return absolute, float(absolute / scale)


def solve_hybrid_modal_schur_direct(
    system: HybridModalSchurDirectSystem,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> HybridModalSchurDirectSolution:
    """Solve the dense modal Schur and recover two sparse local FEM fields."""

    comm = bottom_system.local_mesh.mesh.comm
    if stage_callback is not None:
        stage_callback("modal_schur_solve")
    started = time.perf_counter()
    modal = np.asarray(
        np.linalg.solve(system.modal_schur, system.modal_rhs), dtype=np.complex128
    )
    modal_seconds = _max_elapsed(comm, started)
    if stage_callback is not None:
        stage_callback("field_recovery")
    started = time.perf_counter()
    recovery_factor_setup: dict[str, float] = {}
    bottom_recovery_factor = system.bottom_factor
    top_recovery_factor = system.top_factor
    if bottom_recovery_factor is None:
        bottom_recovery_factor, elapsed = _factor_local(bottom_system.A)
        recovery_factor_setup["bottom"] = elapsed
    try:
        bottom = _recover_local_field(
            bottom_system, bottom_recovery_factor, coupling, modal
        )
    finally:
        if system.bottom_factor is None:
            bottom_recovery_factor.destroy()
    if top_recovery_factor is None:
        top_recovery_factor, elapsed = _factor_local(top_system.A)
        recovery_factor_setup["top"] = elapsed
    try:
        top = _recover_local_field(
            top_system, top_recovery_factor, coupling, modal
        )
    finally:
        if system.top_factor is None:
            top_recovery_factor.destroy()
    recovery_seconds = _max_elapsed(comm, started)
    bottom_absolute, bottom_relative = _local_relative_residual(
        bottom_system, coupling, bottom, modal
    )
    top_absolute, top_relative = _local_relative_residual(
        top_system, coupling, top, modal
    )
    modal_absolute, modal_relative = _modal_residual(
        system, coupling, bottom, top, modal
    )
    combined_absolute = float(
        np.sqrt(bottom_absolute**2 + top_absolute**2 + modal_absolute**2)
    )
    combined_scale = max(
        float(bottom_system.b.norm()),
        float(top_system.b.norm()),
        1.0e-30,
    )
    bottom_recovered = (
        recover_hybrid_static_local_field(
            bottom_system,
            coupling,
            bottom,
            modal,
        )
        if bottom_system.static_condensation is not None
        else None
    )
    top_recovered = (
        recover_hybrid_static_local_field(
            top_system,
            coupling,
            top,
            modal,
        )
        if top_system.static_condensation is not None
        else None
    )
    if (bottom_recovered is None) != (top_recovered is None):
        bottom.destroy()
        top.destroy()
        raise ValueError("Hybrid bottom/top local assembly backends must match.")
    recovery_seconds = _max_elapsed(comm, started)
    return HybridModalSchurDirectSolution(
        bottom=bottom,
        top=top,
        modal_amplitudes=modal,
        relative_residual=float(combined_absolute / combined_scale),
        bottom_relative_residual=bottom_relative,
        top_relative_residual=top_relative,
        modal_relative_residual=modal_relative,
        modal_solve_seconds=modal_seconds,
        recovery_seconds=recovery_seconds,
        recovery_factor_setup_seconds=recovery_factor_setup,
        bottom_recovered=bottom_recovered,
        top_recovered=top_recovered,
    )
