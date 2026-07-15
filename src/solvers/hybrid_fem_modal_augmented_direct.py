from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .common_3d_solve import _petsc_matrix_stats
from .hybrid_local_dtn import HybridLocalDtnSystem


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
    return np.block(
        [
            [-identity, -(negative_map @ np.diag(backward))],
            [-np.diag(forward), -negative_map],
        ]
    )


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
    x: PETSc.Vec
    ksp: PETSc.KSP
    bottom: PETSc.Vec
    top: PETSc.Vec
    modal_amplitudes: np.ndarray
    relative_residual: float
    setup_seconds: float
    solve_seconds: float
    converged_reason: int
    factor_solver: str = "mumps"
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom.destroy()
        self.top.destroy()
        self.x.destroy()
        self.ksp.destroy()
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
        np.zeros(internal_count, dtype=np.complex128),
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
) -> HybridAugmentedDirectSolution:
    """Factor and solve the assembled hybrid system with direct MUMPS LU."""

    comm = system.layout.comm
    ksp = PETSc.KSP().create(comm)
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
    return HybridAugmentedDirectSolution(
        x=x,
        ksp=ksp,
        bottom=bottom,
        top=top,
        modal_amplitudes=modal,
        relative_residual=relative_residual,
        setup_seconds=setup_seconds,
        solve_seconds=solve_seconds,
        converged_reason=int(ksp.getConvergedReason()),
    )
