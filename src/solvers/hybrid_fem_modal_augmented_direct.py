"""Task032 augmented direct reference for 13.5 nm Hybrid FEM-modal solves.

Last-rank modal ownership and local MUMPS LU are current-scale experimental
choices.  This module must not be selected as a 0.7 nm production solver or an
ordinary default without a distributed modal core and iterative local solver.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .common_3d_solve import _petsc_matrix_stats
from .dtn_port_3d import (
    _auxiliary_direct_tangential_projection_audit,
    _gather_auxiliary_values,
    _mode_boundary_phase,
    _mode_power_at_boundary,
    _port_power_metrics,
)
from .hybrid_local_dtn import HybridLocalDtnSystem
from .hybrid_static_field_recovery import (
    HybridStaticRecoveredLocalField,
    recover_hybrid_static_local_field,
)


def _int(values) -> np.ndarray:
    return np.asarray(values, dtype=PETSc.IntType)


@dataclass(frozen=True)
class HybridAugmentedLayout:
    """Rank-major ownership for ``[bottom, top, internal modes]``.

    PETSc requires each rank to own one contiguous interval.  The two local
    FEM matrices already have independent distributed layouts, so a simple
    process-global ``bottom then top`` concatenation would not preserve that
    requirement.  The monolithic matrix therefore stores, on every rank, its
    bottom-owned rows followed by its top-owned rows.  The small modal block
    is appended on the final rank.
    """

    comm: MPI.Intracomm
    bottom_ranges: tuple[tuple[int, int], ...]
    top_ranges: tuple[tuple[int, int], ...]
    combined_offsets: tuple[int, ...]
    bottom_local_sizes: tuple[int, ...]
    top_local_sizes: tuple[int, ...]
    modal_count: int
    modal_owner: int

    @classmethod
    def build(
        cls,
        bottom: HybridLocalDtnSystem,
        top: HybridLocalDtnSystem,
        modal_count: int,
    ) -> HybridAugmentedLayout:
        comm = bottom.local_mesh.mesh.comm
        if top.local_mesh.mesh.comm.size != comm.size:
            raise ValueError("Bottom and top local systems use different MPI sizes.")
        bottom_ranges = tuple(
            (int(first), int(last))
            for first, last in comm.allgather(bottom.A.getOwnershipRange())
        )
        top_ranges = tuple(
            (int(first), int(last))
            for first, last in comm.allgather(top.A.getOwnershipRange())
        )
        bottom_sizes = tuple(last - first for first, last in bottom_ranges)
        top_sizes = tuple(last - first for first, last in top_ranges)
        modal_owner = comm.size - 1
        local_sizes = tuple(
            bottom_sizes[rank]
            + top_sizes[rank]
            + (modal_count if rank == modal_owner else 0)
            for rank in range(comm.size)
        )
        offsets: list[int] = []
        offset = 0
        for size in local_sizes:
            offsets.append(offset)
            offset += size
        expected = bottom.global_size + top.global_size + modal_count
        if offset != expected:
            raise RuntimeError(
                f"Hybrid layout size {offset} does not match expected {expected}."
            )
        return cls(
            comm=comm,
            bottom_ranges=bottom_ranges,
            top_ranges=top_ranges,
            combined_offsets=tuple(offsets),
            bottom_local_sizes=bottom_sizes,
            top_local_sizes=top_sizes,
            modal_count=int(modal_count),
            modal_owner=modal_owner,
        )

    @property
    def global_size(self) -> int:
        return int(
            sum(self.bottom_local_sizes)
            + sum(self.top_local_sizes)
            + self.modal_count
        )

    @property
    def local_size(self) -> int:
        rank = self.comm.rank
        return int(
            self.bottom_local_sizes[rank]
            + self.top_local_sizes[rank]
            + (self.modal_count if rank == self.modal_owner else 0)
        )

    @property
    def local_bottom_slice(self) -> slice:
        return slice(0, self.bottom_local_sizes[self.comm.rank])

    @property
    def local_top_slice(self) -> slice:
        start = self.bottom_local_sizes[self.comm.rank]
        return slice(start, start + self.top_local_sizes[self.comm.rank])

    @property
    def local_modal_slice(self) -> slice:
        start = (
            self.bottom_local_sizes[self.comm.rank]
            + self.top_local_sizes[self.comm.rank]
        )
        size = self.modal_count if self.comm.rank == self.modal_owner else 0
        return slice(start, start + size)

    @property
    def modal_global_start(self) -> int:
        owner = self.modal_owner
        return int(
            self.combined_offsets[owner]
            + self.bottom_local_sizes[owner]
            + self.top_local_sizes[owner]
        )

    def _map_distributed(
        self,
        indices,
        ranges: tuple[tuple[int, int], ...],
        within_rank_offset: tuple[int, ...],
    ) -> np.ndarray:
        values = np.asarray(indices, dtype=np.int64)
        if values.size == 0:
            return np.empty(0, dtype=PETSc.IntType)
        starts = np.asarray([first for first, _last in ranges], dtype=np.int64)
        ends = np.asarray([last for _first, last in ranges], dtype=np.int64)
        owners = np.searchsorted(ends, values, side="right")
        if np.any(owners >= len(ranges)) or np.any(values < starts[owners]):
            raise IndexError("A distributed block index lies outside its ownership map.")
        offsets = np.asarray(self.combined_offsets, dtype=np.int64)[owners]
        local_offsets = np.asarray(within_rank_offset, dtype=np.int64)[owners]
        mapped = offsets + local_offsets + values - starts[owners]
        return np.asarray(mapped, dtype=PETSc.IntType)

    def map_bottom(self, indices) -> np.ndarray:
        return self._map_distributed(
            indices,
            self.bottom_ranges,
            tuple(0 for _ in self.bottom_ranges),
        )

    def map_top(self, indices) -> np.ndarray:
        return self._map_distributed(
            indices,
            self.top_ranges,
            self.bottom_local_sizes,
        )

    def map_modal(self, indices) -> np.ndarray:
        values = np.asarray(indices, dtype=np.int64)
        if np.any(values < 0) or np.any(values >= self.modal_count):
            raise IndexError("A modal index lies outside the internal modal block.")
        return np.asarray(self.modal_global_start + values, dtype=PETSc.IntType)

    def create_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (self.local_size, self.global_size), comm=self.comm
        )

    def pack(
        self,
        bottom: PETSc.Vec,
        top: PETSc.Vec,
        modal_values,
    ) -> PETSc.Vec:
        modal = np.asarray(modal_values, dtype=PETSc.ScalarType)
        if modal.shape != (self.modal_count,):
            raise ValueError(
                f"Modal values must have shape ({self.modal_count},), got {modal.shape}."
            )
        vector = self.create_vector()
        local = vector.getArray()
        bottom_values = np.asarray(bottom.getArray(readonly=True))
        top_values = np.asarray(top.getArray(readonly=True))
        if len(bottom_values) != self.bottom_local_sizes[self.comm.rank]:
            vector.destroy()
            raise ValueError("Bottom vector ownership does not match hybrid layout.")
        if len(top_values) != self.top_local_sizes[self.comm.rank]:
            vector.destroy()
            raise ValueError("Top vector ownership does not match hybrid layout.")
        local[self.local_bottom_slice] = bottom_values
        local[self.local_top_slice] = top_values
        if self.comm.rank == self.modal_owner:
            local[self.local_modal_slice] = modal
        vector.assemble()
        return vector

    def split(
        self,
        vector: PETSc.Vec,
        bottom_template: PETSc.Vec,
        top_template: PETSc.Vec,
    ) -> tuple[PETSc.Vec, PETSc.Vec, np.ndarray]:
        if vector.getSize() != self.global_size:
            raise ValueError("Monolithic vector size does not match hybrid layout.")
        local = np.asarray(vector.getArray(readonly=True))
        bottom = bottom_template.duplicate()
        top = None
        try:
            top = top_template.duplicate()
            bottom.getArray()[:] = local[self.local_bottom_slice]
            top.getArray()[:] = local[self.local_top_slice]
            modal_local = (
                np.asarray(local[self.local_modal_slice], dtype=np.complex128).copy()
                if self.comm.rank == self.modal_owner
                else None
            )
            modal = np.asarray(
                self.comm.bcast(modal_local, root=self.modal_owner),
                dtype=np.complex128,
            )
            return bottom, top, modal
        except Exception:
            bottom.destroy()
            if top is not None:
                top.destroy()
            raise


def internal_modal_constraint_matrix(
    coupling: HybridInternalModeCoupling,
) -> np.ndarray:
    """Return the small ``2M x 2M`` E-trace/propagation constraint block."""

    mode_count = coupling.mode_count_per_direction
    negative_map = np.asarray(
        coupling.negative_trace_to_positive, dtype=np.complex128
    )
    if negative_map.shape != (mode_count, mode_count):
        raise ValueError("Negative trace mapping has the wrong shape.")
    forward = np.asarray(coupling.propagation.forward.factors, dtype=np.complex128)
    backward = np.asarray(
        coupling.propagation.backward.factors, dtype=np.complex128
    )
    identity = np.eye(mode_count, dtype=np.complex128)
    base = np.block(
        [
            [-identity, -(negative_map @ np.diag(backward))],
            [-np.diag(forward), -negative_map],
        ]
    )
    bottom_correction = np.hstack(
        (
            np.asarray(
                coupling.bottom.positive_interior_correction,
                dtype=np.complex128,
            ),
            np.asarray(
                coupling.bottom.negative_interior_correction,
                dtype=np.complex128,
            )
            @ np.diag(backward),
        )
    )
    top_correction = np.hstack(
        (
            np.asarray(
                coupling.top.positive_interior_correction,
                dtype=np.complex128,
            )
            @ np.diag(forward),
            np.asarray(
                coupling.top.negative_interior_correction,
                dtype=np.complex128,
            ),
        )
    )
    correction = np.vstack((bottom_correction, top_correction))
    if correction.shape != base.shape:
        raise ValueError("Hybrid modal interior correction has the wrong shape.")
    return base + correction


def internal_modal_rhs_correction(
    coupling: HybridInternalModeCoupling,
) -> np.ndarray:
    """Return the cell-interior elimination RHS for both modal equations."""

    correction = np.concatenate(
        (
            np.asarray(
                coupling.bottom.modal_rhs_correction,
                dtype=np.complex128,
            ),
            np.asarray(
                coupling.top.modal_rhs_correction,
                dtype=np.complex128,
            ),
        )
    )
    expected = coupling.internal_equation_count
    if correction.shape != (expected,):
        raise ValueError("Hybrid modal RHS interior correction has the wrong shape.")
    return correction


def _copy_block(
    target: PETSc.Mat,
    source: PETSc.Mat,
    map_rows: Callable[[np.ndarray], np.ndarray],
    map_columns: Callable[[np.ndarray], np.ndarray],
    *,
    column_factors: np.ndarray | None = None,
) -> int:
    inserted = 0
    first, last = source.getOwnershipRange()
    for row in range(first, last):
        columns, values = source.getRow(row)
        if len(columns) == 0:
            continue
        columns_array = np.asarray(columns, dtype=np.int64)
        scaled = np.asarray(values, dtype=PETSc.ScalarType)
        if column_factors is not None:
            scaled = scaled * column_factors[columns_array]
        target.setValues(
            map_rows(_int([row])),
            map_columns(columns_array),
            scaled.reshape(1, -1),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        inserted += len(columns_array)
    return inserted


@dataclass
class HybridAugmentedDirectSystem:
    A: PETSc.Mat
    b: PETSc.Vec
    layout: HybridAugmentedLayout
    modal_constraint: np.ndarray
    matrix_stats: dict
    block_shapes: dict[str, tuple[int, int]]
    inserted_nnz_by_block: dict[str, int]
    dense_interface_square_formed: bool = False
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        self._destroyed = True


@dataclass
class HybridAugmentedDirectSolution:
    x: PETSc.Vec | None
    ksp: PETSc.KSP | None
    bottom: PETSc.Vec
    top: PETSc.Vec
    modal_amplitudes: np.ndarray
    relative_residual: float
    setup_seconds: float
    solve_seconds: float
    converged_reason: int
    factor_solver: str = "mumps"
    bottom_recovered: HybridStaticRecoveredLocalField | None = None
    top_recovered: HybridStaticRecoveredLocalField | None = None
    _factorization_released: bool = field(
        default=False,
        init=False,
        repr=False,
    )
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

    def release_factorization(self) -> dict[str, object]:
        """Release the monolithic solution carrier and MUMPS factor only."""

        if self._factorization_released:
            return {
                "released": False,
                "already_released": True,
                "retained_physical_fields": True,
            }
        if self.x is not None:
            self.x.destroy()
            self.x = None
        if self.ksp is not None:
            self.ksp.destroy()
            self.ksp = None
        self._factorization_released = True
        return {
            "released": True,
            "already_released": False,
            "released_objects": [
                "monolithic_solution_carrier",
                "KSP_MUMPS_factor",
            ],
            "retained_physical_fields": True,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom.destroy()
        self.top.destroy()
        self.bottom_recovered = None
        self.top_recovered = None
        self.release_factorization()
        self._destroyed = True


def build_hybrid_augmented_direct_system(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
) -> HybridAugmentedDirectSystem:
    """Assemble the Task32 monolithic AIJ matrix without solving it."""

    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Hybrid local systems must be ordered bottom, top.")
    mode_count = coupling.mode_count_per_direction
    internal_count = 2 * mode_count
    layout = HybridAugmentedLayout.build(
        bottom_system, top_system, internal_count
    )
    matrix = PETSc.Mat().createAIJ(
        size=(
            (layout.local_size, layout.global_size),
            (layout.local_size, layout.global_size),
        ),
        comm=layout.comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    inserted: dict[str, int] = {}
    inserted["A_bottom"] = _copy_block(
        matrix,
        bottom_system.A,
        layout.map_bottom,
        layout.map_bottom,
    )
    inserted["A_top"] = _copy_block(
        matrix,
        top_system.A,
        layout.map_top,
        layout.map_top,
    )

    forward = np.asarray(coupling.propagation.forward.factors, dtype=np.complex128)
    backward = np.asarray(
        coupling.propagation.backward.factors, dtype=np.complex128
    )
    inserted["C_bottom_positive"] = _copy_block(
        matrix,
        coupling.bottom.positive_traction,
        layout.map_bottom,
        lambda columns: layout.map_modal(columns),
    )
    inserted["C_bottom_negative"] = _copy_block(
        matrix,
        coupling.bottom.negative_traction,
        layout.map_bottom,
        lambda columns: layout.map_modal(mode_count + columns),
        column_factors=backward,
    )
    inserted["C_top_positive"] = _copy_block(
        matrix,
        coupling.top.positive_traction,
        layout.map_top,
        lambda columns: layout.map_modal(columns),
        column_factors=forward,
    )
    inserted["C_top_negative"] = _copy_block(
        matrix,
        coupling.top.negative_traction,
        layout.map_top,
        lambda columns: layout.map_modal(mode_count + columns),
    )

    inserted["D_bottom"] = _copy_block(
        matrix,
        coupling.bottom.projection,
        lambda rows: layout.map_modal(rows),
        layout.map_bottom,
    )
    inserted["D_top"] = _copy_block(
        matrix,
        coupling.top.projection,
        lambda rows: layout.map_modal(mode_count + rows),
        layout.map_top,
    )

    modal_constraint = internal_modal_constraint_matrix(coupling)
    if layout.comm.rank == layout.modal_owner:
        modal_indices = layout.map_modal(np.arange(internal_count))
        matrix.setValues(
            modal_indices,
            modal_indices,
            modal_constraint,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    inserted["H_modal"] = int(np.count_nonzero(modal_constraint))
    matrix.assemble()
    rhs = layout.pack(
        bottom_system.b,
        top_system.b,
        internal_modal_rhs_correction(coupling),
    )
    block_shapes = {
        "A_bottom": bottom_system.A.getSize(),
        "A_top": top_system.A.getSize(),
        "C_bottom": (bottom_system.global_size, internal_count),
        "C_top": (top_system.global_size, internal_count),
        "D_bottom": (mode_count, bottom_system.global_size),
        "D_top": (mode_count, top_system.global_size),
        "H_modal": (internal_count, internal_count),
        "monolithic": matrix.getSize(),
    }
    return HybridAugmentedDirectSystem(
        A=matrix,
        b=rhs,
        layout=layout,
        modal_constraint=modal_constraint,
        matrix_stats=_petsc_matrix_stats(matrix, assemble=False),
        block_shapes=block_shapes,
        inserted_nnz_by_block=inserted,
    )


def solve_hybrid_augmented_direct(
    system: HybridAugmentedDirectSystem,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling | None = None,
) -> HybridAugmentedDirectSolution:
    """Factor and solve the assembled hybrid system with direct MUMPS LU."""

    comm = system.layout.comm
    ksp = PETSc.KSP().create(comm)
    x = None
    bottom = None
    top = None
    bottom_recovered = None
    top_recovered = None
    try:
        ksp.setType(PETSc.KSP.Type.PREONLY)
        ksp.setErrorIfNotConverged(True)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.LU)
        pc.setFactorSolverType("mumps")
        ksp.setOperators(system.A)
        setup_started = time.perf_counter()
        ksp.setUp()
        setup_seconds = float(
            comm.allreduce(time.perf_counter() - setup_started, op=MPI.MAX)
        )
        x = system.b.duplicate()
        solve_started = time.perf_counter()
        ksp.solve(system.b, x)
        solve_seconds = float(
            comm.allreduce(time.perf_counter() - solve_started, op=MPI.MAX)
        )
        residual = system.b.duplicate()
        try:
            system.A.mult(x, residual)
            residual.axpy(PETSc.ScalarType(-1.0), system.b)
            relative_residual = float(
                residual.norm() / max(system.b.norm(), 1.0e-30)
            )
        finally:
            residual.destroy()
        bottom, top, modal = system.layout.split(
            x, bottom_system.b, top_system.b
        )
        static_requested = (
            bottom_system.static_condensation is not None
            or top_system.static_condensation is not None
        )
        if static_requested:
            if (
                bottom_system.static_condensation is None
                or top_system.static_condensation is None
            ):
                raise ValueError(
                    "Hybrid bottom/top local assembly backends must match."
                )
            if coupling is None:
                raise ValueError(
                    "Condensed Hybrid augmented recovery requires its coupling."
                )
            bottom_recovered = recover_hybrid_static_local_field(
                bottom_system,
                coupling,
                bottom,
                modal,
            )
            top_recovered = recover_hybrid_static_local_field(
                top_system,
                coupling,
                top,
                modal,
            )
        result = HybridAugmentedDirectSolution(
            x=x,
            ksp=ksp,
            bottom=bottom,
            top=top,
            modal_amplitudes=modal,
            relative_residual=relative_residual,
            setup_seconds=setup_seconds,
            solve_seconds=solve_seconds,
            converged_reason=int(ksp.getConvergedReason()),
            bottom_recovered=bottom_recovered,
            top_recovered=top_recovered,
        )
        x = None
        ksp = None
        bottom = None
        top = None
        return result
    except Exception:
        bottom_recovered = None
        top_recovered = None
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        if x is not None:
            x.destroy()
        if ksp is not None:
            ksp.destroy()
        raise


def _replicated_small_vector(vector: PETSc.Vec) -> np.ndarray:
    """Replicate one mode-count vector whose rows live on the final rank."""

    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    size = int(vector.getSize())
    local = None
    if comm.rank == owner:
        local = np.asarray(
            vector.getValues(np.arange(size, dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)


def _modal_action(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    source = matrix.createVecRight()
    source.set(0.0)
    first, last = source.getOwnershipRange()
    if last > first:
        source.setValues(
            np.arange(first, last, dtype=PETSc.IntType),
            np.asarray(values[first:last], dtype=PETSc.ScalarType),
        )
    source.assemble()
    result = matrix.createVecLeft()
    try:
        matrix.mult(source, result)
    finally:
        source.destroy()
    return result


def _relative_array_residual(actual: np.ndarray, expected: np.ndarray) -> float:
    scale = max(
        float(np.linalg.norm(actual)),
        float(np.linalg.norm(expected)),
        1.0e-30,
    )
    return float(np.linalg.norm(actual - expected) / scale)


def _fe_traction_equilibrium_diagnostics(
    local_system: HybridLocalDtnSystem,
    field: PETSc.Vec,
    positive_traction: PETSc.Mat,
    positive_values: np.ndarray,
    negative_traction: PETSc.Mat,
    negative_values: np.ndarray,
) -> dict[str, float | str]:
    residual = local_system.A.createVecLeft()
    positive = _modal_action(positive_traction, positive_values)
    negative = _modal_action(negative_traction, negative_values)
    try:
        local_system.A.mult(field, residual)
        operator_norm = float(residual.norm())
        residual.axpy(PETSc.ScalarType(-1.0), local_system.b)
        residual.axpy(PETSc.ScalarType(1.0), positive)
        residual.axpy(PETSc.ScalarType(1.0), negative)
        absolute = float(residual.norm())
        rhs_norm = float(local_system.b.norm())
        positive_norm = float(positive.norm())
        negative_norm = float(negative.norm())
        scale = max(
            operator_norm,
            rhs_norm,
            positive_norm,
            negative_norm,
            1.0e-30,
        )
        return {
            "method": "exact_variational_conormal_functional_dual",
            "absolute_dual_coefficient_norm": absolute,
            "relative_dual": float(absolute / scale),
            "comparison_scale_dual": scale,
            "local_operator_action_norm": operator_norm,
            "local_rhs_norm": rhs_norm,
            "positive_modal_traction_load_norm": positive_norm,
            "negative_modal_traction_load_norm": negative_norm,
        }
    finally:
        residual.destroy()
        positive.destroy()
        negative.destroy()


def _fe_traction_equilibrium_residual(
    local_system: HybridLocalDtnSystem,
    field: PETSc.Vec,
    positive_traction: PETSc.Mat,
    positive_values: np.ndarray,
    negative_traction: PETSc.Mat,
    negative_values: np.ndarray,
) -> tuple[float, float]:
    """Backward-compatible scalar view of the exact conormal dual audit."""

    diagnostics = _fe_traction_equilibrium_diagnostics(
        local_system,
        field,
        positive_traction,
        positive_values,
        negative_traction,
        negative_values,
    )
    return (
        float(diagnostics["absolute_dual_coefficient_norm"]),
        float(diagnostics["relative_dual"]),
    )


def _external_diffraction_order_rows(
    cfg: SimulationConfig3D,
    systems: tuple[HybridLocalDtnSystem, ...],
    auxiliary: tuple[np.ndarray, ...],
    *,
    incident_power: float,
) -> list[dict]:
    rows: list[dict] = []
    auxiliary_index = 0
    for system, values in zip(systems, auxiliary):
        for local_index, (mode, value, incident) in enumerate(
            zip(system.external_modes, values, system.incident_projections)
        ):
            outgoing = (
                complex(value - incident)
                if mode.side == "top"
                else complex(value)
            )
            boundary_amplitude = outgoing * _mode_boundary_phase(mode, cfg)
            modal_power = _mode_power_at_boundary(mode, cfg, outgoing)
            power_ratio = float(modal_power / incident_power)
            rows.append(
                {
                    "auxiliary_index": auxiliary_index,
                    "local_auxiliary_index": local_index,
                    "side": mode.side,
                    "m": int(mode.m),
                    "n": int(mode.n),
                    "polarization": mode.polarization,
                    "propagating": bool(mode.propagating),
                    "rayleigh_warning": bool(mode.rayleigh_warning),
                    "beta_per_nm": complex(mode.beta),
                    "total_projection": complex(value),
                    "incident_projection": complex(incident),
                    "outgoing_amplitude": outgoing,
                    "outgoing_amplitude_at_boundary": boundary_amplitude,
                    "power_ratio": power_ratio,
                    "R": (
                        power_ratio
                        if mode.side == "top" and mode.propagating
                        else 0.0
                    ),
                    "T": (
                        power_ratio
                        if mode.side == "bottom" and mode.propagating
                        else 0.0
                    ),
                }
            )
            auxiliary_index += 1
    return rows


def evaluate_hybrid_recovered_direct_projection_audit(
    cfg: SimulationConfig3D,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    solution: Any,
) -> dict[str, Any]:
    """Audit Hybrid auxiliary amplitudes against recovered local FE traces.

    The audit is opt-in and reuses the independent tangential projection used
    by Full3D.  It deliberately runs on the recovered physical fields rather
    than the condensed trace carriers.
    """

    if not cfg.dtn_auxiliary_direct_projection_audit:
        return {
            "requested": False,
            "status": "not_requested",
            "scope": "hybrid_candidate",
            "pass": None,
            "ordinary_default_changed": False,
        }
    if solution.bottom_recovered is None or solution.top_recovered is None:
        raise ValueError(
            "Task036 Hybrid direct projection audit requires static-condensation "
            "recovered bottom and top FE fields; standard/nonrecovered Hybrid "
            "direct projection audit is not qualified."
        )

    systems = {
        "bottom": bottom_system,
        "top": top_system,
    }
    fields = {
        "bottom": solution.bottom_physical,
        "top": solution.top_physical,
    }
    vectors = {
        "bottom": solution.bottom,
        "top": solution.top,
    }
    side_audits: dict[str, dict] = {}
    rows: list[dict] = []
    side_mode_count: dict[str, int] = {}
    quadrature_degree_by_side: dict[str, int | None] = {}
    for side in ("bottom", "top"):
        system = systems[side]
        auxiliary = _gather_auxiliary_values(
            vectors[side],
            system.n_fe,
            system.n_external_aux,
            system.local_mesh.mesh.comm,
        )
        audit = _auxiliary_direct_tangential_projection_audit(
            fields[side],
            system.external_modes,
            auxiliary,
            system.incident_projections,
            system.local_mesh.mesh_data,
            cfg,
            quadrature_degree=system.dtn_quadrature_degree,
        )
        side_audits[side] = audit
        rows.extend(audit["orders"])
        side_mode_count[side] = len(system.external_modes)
        quadrature_degree_by_side[side] = system.dtn_quadrature_degree

    expected_mode_count = int(sum(side_mode_count.values()))
    max_total = max(
        (
            float(row["absolute_total_projection_difference"])
            for row in rows
        ),
        default=0.0,
    )
    max_outgoing = max(
        (
            float(row["absolute_outgoing_projection_difference"])
            for row in rows
        ),
        default=0.0,
    )
    tolerance = float(cfg.dtn_auxiliary_direct_projection_tolerance)
    passed = bool(
        len(rows) == expected_mode_count
        and all(audit["pass"] is True for audit in side_audits.values())
        and max_outgoing <= tolerance
    )
    return {
        "requested": True,
        "status": "pass" if passed else "failed",
        "scope": "hybrid_candidate",
        "method": (
            "independent recovered-FE tangential trace projection; official "
            "Hybrid auxiliary amplitudes are unchanged"
        ),
        "field_source": (
            "static_condensation_recovered_full_local_fe_fields"
        ),
        "official_auxiliary_amplitudes_unchanged": True,
        "ordinary_default_changed": False,
        "absolute_error_only_for_near_zero_channels": True,
        "tolerance": tolerance,
        "quadrature_degree_by_side": quadrature_degree_by_side,
        "expected_mode_count": expected_mode_count,
        "audited_mode_count": len(rows),
        "side_mode_count": side_mode_count,
        "max_absolute_total_projection_difference": max_total,
        "max_absolute_outgoing_projection_difference": max_outgoing,
        "side_pass": {
            side: bool(audit["pass"])
            for side, audit in side_audits.items()
        },
        "pass": passed,
        "orders": rows,
    }


def evaluate_hybrid_augmented_solution(
    cfg: SimulationConfig3D,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    solution: HybridAugmentedDirectSolution,
) -> dict:
    """Evaluate algebraic interface contracts and external modal R/T/A.

    The FE residuals verify the variational traction coupling used by the
    augmented matrix.  They are not presented as a pointwise H-field jump;
    a later physical field reconstruction must provide that stronger Gate.
    """

    mode_count = coupling.mode_count_per_direction
    modal = np.asarray(solution.modal_amplitudes, dtype=np.complex128)
    if modal.shape != (2 * mode_count,):
        raise ValueError("The solved internal modal vector has the wrong shape.")
    bottom_incident = modal[:mode_count]
    top_incident = modal[mode_count:]
    forward = np.asarray(
        coupling.propagation.forward.factors, dtype=np.complex128
    )
    backward = np.asarray(
        coupling.propagation.backward.factors, dtype=np.complex128
    )
    negative_map = np.asarray(
        coupling.negative_trace_to_positive, dtype=np.complex128
    )

    bottom_projection = coupling.bottom.projection.createVecLeft()
    top_projection = coupling.top.projection.createVecLeft()
    try:
        coupling.bottom.projection.mult(solution.bottom, bottom_projection)
        coupling.top.projection.mult(solution.top, top_projection)
        bottom_actual = _replicated_small_vector(bottom_projection)
        top_actual = _replicated_small_vector(top_projection)
    finally:
        bottom_projection.destroy()
        top_projection.destroy()
    bottom_expected = bottom_incident + negative_map @ (
        backward * top_incident
    )
    top_expected = forward * bottom_incident + negative_map @ top_incident
    bottom_e_relative = _relative_array_residual(
        bottom_actual, bottom_expected
    )
    top_e_relative = _relative_array_residual(top_actual, top_expected)
    combined_actual = np.concatenate((bottom_actual, top_actual))
    combined_expected = np.concatenate((bottom_expected, top_expected))

    bottom_fe_dual = (
        _fe_traction_equilibrium_diagnostics(
            bottom_system,
            solution.bottom,
            coupling.bottom.positive_traction,
            bottom_incident,
            coupling.bottom.negative_traction,
            backward * top_incident,
        )
    )
    top_fe_dual = _fe_traction_equilibrium_diagnostics(
        top_system,
        solution.top,
        coupling.top.positive_traction,
        forward * bottom_incident,
        coupling.top.negative_traction,
        top_incident,
    )

    bottom_aux = _gather_auxiliary_values(
        solution.bottom,
        bottom_system.n_fe,
        bottom_system.n_external_aux,
        bottom_system.local_mesh.mesh.comm,
    )
    top_aux = _gather_auxiliary_values(
        solution.top,
        top_system.n_fe,
        top_system.n_external_aux,
        top_system.local_mesh.mesh.comm,
    )
    port_power = _port_power_metrics(
        cfg,
        [*bottom_system.external_modes, *top_system.external_modes],
        np.concatenate((bottom_aux, top_aux)),
        [
            *np.asarray(
                bottom_system.incident_projections, dtype=np.complex128
            ),
            *np.asarray(top_system.incident_projections, dtype=np.complex128),
        ],
    )
    external_orders = _external_diffraction_order_rows(
        cfg,
        (bottom_system, top_system),
        (bottom_aux, top_aux),
        incident_power=float(port_power["incident_power_code_units"]),
    )
    return {
        "interface_e_projection": {
            "bottom_relative_residual": bottom_e_relative,
            "top_relative_residual": top_e_relative,
            "combined_relative_residual": _relative_array_residual(
                combined_actual, combined_expected
            ),
        },
        "fe_modal_traction_equilibrium": {
            "interpretation": (
                "variational_FE_rows_with_modal_traction_not_pointwise_H_jump"
            ),
            "bottom_absolute_residual": bottom_fe_dual[
                "absolute_dual_coefficient_norm"
            ],
            "bottom_relative_residual": bottom_fe_dual["relative_dual"],
            "top_absolute_residual": top_fe_dual[
                "absolute_dual_coefficient_norm"
            ],
            "top_relative_residual": top_fe_dual["relative_dual"],
            "bottom_dual": bottom_fe_dual,
            "top_dual": top_fe_dual,
        },
        "external_auxiliary_amplitudes": {
            "bottom": bottom_aux,
            "top": top_aux,
        },
        "external_diffraction_orders": external_orders,
        "port_power": port_power,
    }
