"""Owner-local same-mesh p2-to-p6 H(curl) trace transfer.

This narrow M4a component maps independent p2 trace coordinates to
independent p6 trace coordinates on one structured hexahedral mesh.  The
local interpolation is the Basix p2-to-p6 operator surrounded by the actual
DOLFINx cell transforms.  Only owner-local row stencils are retained; no
global transfer matrix or global vector/basis sweep is created.  Each local
element transform is fixed and explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import basix
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    _distributed_trace_preallocation,
    _cell_trace_expansion,
    TraceConstraintMap,
)

__all__ = (
    "OwnerLocalTraceTransfer",
    "build_p2_galerkin_fine_matrix",
    "build_p2_to_p6_active_trace_transfer",
)

STRUCTURAL_ZERO_TOLERANCE = 1.0e-14


def _trace_and_interior_positions(function_space) -> tuple[np.ndarray, np.ndarray]:
    element = function_space.element.basix_element
    dimension = int(function_space.element.space_dimension)
    interior = np.asarray(element.entity_dofs[3][0], dtype=np.int32)
    trace = np.setdiff1d(
        np.arange(dimension, dtype=np.int32), interior, assume_unique=True
    )
    return trace, interior


def _validate_space(function_space, degree: int) -> None:
    if "hexahedron" not in str(function_space.mesh.basix_cell()).lower():
        raise NotImplementedError("M4a transfer supports hexahedra only")
    element = function_space.element.basix_element
    family = str(getattr(element.family, "name", element.family)).lower()
    if family not in {"n1curl", "n1e"}:
        raise NotImplementedError("M4a transfer supports N1curl only")
    if int(element.degree) != int(degree):
        raise ValueError(
            f"M4a transfer requires p{degree}; observed p{int(element.degree)}"
        )
    if int(function_space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("M4a transfer requires scalar-blocked dofs")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise NotImplementedError("M4a transfer requires complex128 PETSc")


def _global_cell_dofs(function_space, cell: int) -> np.ndarray:
    local = np.asarray(function_space.dofmap.cell_dofs(int(cell)), dtype=np.int32)
    return np.asarray(
        function_space.dofmap.index_map.local_to_global(local), dtype=np.int64
    )


def _oriented_trace_matrix(
    coarse_space,
    fine_space,
    interpolation: np.ndarray,
    coarse_positions: np.ndarray,
    fine_trace_positions: np.ndarray,
    cell_info: int,
) -> np.ndarray:
    """Return stored p2 coefficients to stored p6 trace rows for one cell."""

    coarse_element = coarse_space.element
    fine_element = fine_space.element
    info = np.asarray([int(cell_info)], dtype=np.uint32)
    result = np.empty(
        (len(fine_trace_positions), len(coarse_positions)),
        dtype=np.complex128,
    )
    for column, position in enumerate(coarse_positions):
        stored_coarse = np.zeros(
            int(coarse_element.space_dimension), dtype=np.complex128
        )
        stored_coarse[int(position)] = 1.0
        coarse_reference = np.ascontiguousarray(stored_coarse)
        coarse_element.Tt_apply(coarse_reference, info, 1)
        fine_reference = np.asarray(interpolation @ coarse_reference)
        stored_fine = np.ascontiguousarray(fine_reference, dtype=np.complex128)
        fine_element.T_apply(stored_fine, info, 1)
        result[:, column] = stored_fine[fine_trace_positions]
    return result


def _actual_p2_to_p6_interpolation(coarse_space, fine_space) -> np.ndarray:
    """Return the construction-time Basix p2-to-p6 interpolation operator."""

    coarse_basix_element = coarse_space.ufl_element().basix_element
    fine_basix_element = fine_space.ufl_element().basix_element
    interpolation = np.asarray(
        basix.compute_interpolation_operator(
            coarse_basix_element,
            fine_basix_element,
        ),
        dtype=np.complex128,
    )
    expected_shape = (
        int(fine_space.element.space_dimension),
        int(coarse_space.element.space_dimension),
    )
    if interpolation.shape != expected_shape:
        raise RuntimeError("Basix p2-to-p6 interpolation shape is inconsistent")
    return interpolation


def _row_entries(
    active_ids: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    combined: dict[int, complex] = {}
    for active, value in zip(active_ids, values, strict=True):
        combined[int(active)] = combined.get(int(active), 0.0j) + complex(value)
    discarded = tuple(
        abs(value)
        for _active, value in combined.items()
        if abs(value) <= STRUCTURAL_ZERO_TOLERANCE
    )
    entries = tuple(
        (active, value)
        for active, value in combined.items()
        if abs(value) > STRUCTURAL_ZERO_TOLERANCE
    )
    entries = tuple(sorted(entries))
    return (
        np.asarray([entry[0] for entry in entries], dtype=PETSc.IntType),
        np.asarray([entry[1] for entry in entries], dtype=np.complex128),
        len(discarded),
        max(discarded, default=0.0),
    )


def build_p2_galerkin_fine_matrix(
    fine_condensed,
    coarse_space,
    fine_space,
    coarse_constraints: TraceConstraintMap,
) -> tuple[PETSc.Mat, dict[str, Any]]:
    """Assemble ``F2 = P^H F6 P`` from retained p6 cell Schur blocks.

    ``fine_condensed`` must be the action-only p6 condensation.  The retained
    tensors use the stored, oriented p6 trace ordering.  Each owned cell is
    projected with the same construction-time Basix interpolation used by
    :func:`build_p2_to_p6_active_trace_transfer`; only the local projected
    block is held during PETSc insertion.
    """

    _validate_space(coarse_space, 2)
    _validate_space(fine_space, 6)
    if coarse_space.mesh is not fine_space.mesh:
        raise ValueError("p2 and p6 Galerkin spaces must share one mesh")
    if fine_condensed.matrix is not None:
        raise ValueError("p2 Galerkin projection requires no global p6 matrix")
    schurs = fine_condensed.retained_local_schur_by_class
    if schurs is None:
        raise ValueError("p2 Galerkin projection requires retained local Schur data")

    comm = coarse_space.mesh.comm
    topology = fine_space.mesh.topology
    topology.create_entity_permutations()
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    owned_cells = int(topology.index_map(topology.dim).size_local)
    if len(fine_condensed.cell_recovery_maps) != owned_cells:
        raise ValueError("retained p6 cells do not match owned mesh cells")
    if len(cell_info) < owned_cells:
        raise ValueError("p6 cell permutation metadata is incomplete")

    coarse_trace, coarse_interior = _trace_and_interior_positions(coarse_space)
    fine_trace, _fine_interior = _trace_and_interior_positions(fine_space)
    interpolation = _actual_p2_to_p6_interpolation(coarse_space, fine_space)
    active_counts = tuple(
        int(value)
        for value in comm.allgather(
            len(coarse_constraints.owned_active_original_dofs)
        )
    )
    active_rows = int(sum(active_counts))
    if active_rows != int(coarse_constraints.active_rows):
        raise ValueError("p2 active ownership does not match its constraint map")

    cell_active_ids: list[np.ndarray] = []
    for cell in range(owned_cells):
        coarse_global = _global_cell_dofs(coarse_space, cell)
        coarse_trace_global = coarse_global[coarse_trace]
        active_ids, _expansion, _identity = _cell_trace_expansion(
            coarse_trace_global,
            coarse_constraints,
        )
        if len(active_ids) == 0:
            raise ValueError("a p2 cell has no active trace rows")
        cell_active_ids.append(np.asarray(active_ids, dtype=PETSc.IntType))

    diagonal_nnz, off_diagonal_nnz, preallocation = (
        _distributed_trace_preallocation(
            comm,
            tuple(cell_active_ids),
            active_counts=active_counts,
            appended_global_rows=0,
            appended_support_owned_cell_groups=(),
            appended_support_group_by_row=(),
        )
    )
    local_rows = int(active_counts[comm.rank])
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, active_rows), (local_rows, active_rows)),
        nnz=(diagonal_nnz, off_diagonal_nnz),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)

    max_temporary_bytes_local = 0
    max_interior_dependency_local = 0.0
    projected_cells = 0
    for cell, active_ids in enumerate(cell_active_ids):
        recovery = fine_condensed.cell_recovery_maps[cell]
        schur = schurs.get(recovery.class_key)
        if schur is None:
            raise ValueError("retained p6 Schur class is missing")
        fine_global = _global_cell_dofs(fine_space, cell)
        fine_trace_global = fine_global[fine_trace]
        if not np.array_equal(
            np.asarray(recovery.trace_original_dofs, dtype=np.int64),
            np.asarray(fine_trace_global, dtype=np.int64),
        ):
            raise ValueError(
                "retained p6 trace ordering differs from stored fine trace DoFs"
            )
        if tuple(map(int, schur.shape)) != (len(fine_trace), len(fine_trace)):
            raise ValueError("retained p6 Schur shape does not match trace ordering")
        coarse_global = _global_cell_dofs(coarse_space, cell)
        coarse_trace_global = coarse_global[coarse_trace]
        coarse_active_ids, expansion, _identity = _cell_trace_expansion(
            coarse_trace_global,
            coarse_constraints,
        )
        if not np.array_equal(active_ids, coarse_active_ids):
            raise RuntimeError("p2 cell active ordering changed between projection passes")
        local_full = _oriented_trace_matrix(
            coarse_space,
            fine_space,
            interpolation,
            np.arange(int(coarse_space.element.space_dimension), dtype=np.int32),
            fine_trace,
            int(cell_info[cell]),
        )
        dependency = float(
            np.max(np.abs(local_full[:, coarse_interior]), initial=0.0)
        )
        max_interior_dependency_local = max(
            max_interior_dependency_local,
            dependency,
        )
        if dependency > 1.0e-12:
            raise NotImplementedError(
                "p2 cell-interior DoFs contribute to the p6 trace transfer"
            )
        G = np.asarray(
            local_full[:, coarse_trace] @ expansion.toarray(),
            dtype=np.complex128,
        )
        projected = np.asarray(G.conjugate().T @ schur @ G, dtype=np.complex128)
        matrix.setValues(
            active_ids,
            active_ids,
            np.asarray(projected, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        max_temporary_bytes_local = max(
            max_temporary_bytes_local,
            int(local_full.nbytes + G.nbytes + projected.nbytes),
        )
        projected_cells += 1
    matrix.assemble()

    info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    local_info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    nz_used = int(info.get("nz_used", 0.0))
    nz_allocated = int(info.get("nz_allocated", nz_used))
    memory_bytes = float(info.get("memory", 0.0))
    local_nz_used = int(local_info.get("nz_used", 0.0))
    local_rows = int(matrix.getLocalSize()[0])
    payload_lower_bound_bytes_local = int(
        local_nz_used
        * (np.dtype(PETSc.ScalarType).itemsize + np.dtype(PETSc.IntType).itemsize)
        + (local_rows + 1) * np.dtype(PETSc.IntType).itemsize
    )
    retained_count_local = len(schurs)
    retained_bytes_local = sum(int(value.nbytes) for value in schurs.values())
    audit = {
        "status": "p2_galerkin_from_retained_p6_cell_schur",
        "p2_active_rows": int(active_rows),
        "p6_active_rows": int(fine_condensed.active_rows),
        "owned_cells_local": int(projected_cells),
        "projected_cells_global": int(
            comm.allreduce(projected_cells, op=MPI.SUM)
        ),
        "global_p6_matrix_materialized": False,
        "global_p6_transfer_materialized": False,
        "global_basis_sweep": False,
        "local_projected_cell_block": True,
        "preallocation_status": "executed_existing_trace_preallocation",
        "preallocated_structural_nnz": int(
            preallocation["preallocated_structural_nnz"]
        ),
        "matrix_nnz_used": nz_used,
        "matrix_nnz_allocated": nz_allocated,
        "petsc_memory_bytes": int(memory_bytes),
        "petsc_memory_info_available": float(info.get("memory", 0.0)) > 0.0,
        "matrix_payload_lower_bound_bytes_local": payload_lower_bound_bytes_local,
        "matrix_payload_lower_bound_bytes_global": int(
            comm.allreduce(payload_lower_bound_bytes_local, op=MPI.SUM)
        ),
        "max_cell_temporary_bytes": int(
            comm.allreduce(max_temporary_bytes_local, op=MPI.MAX)
        ),
        "trace_interior_dependency_max": float(
            comm.allreduce(max_interior_dependency_local, op=MPI.MAX)
        ),
        "retained_p6_schur_class_count_local": int(retained_count_local),
        "retained_p6_schur_class_count_sum": int(
            comm.allreduce(retained_count_local, op=MPI.SUM)
        ),
        "retained_p6_schur_bytes_sum": int(
            comm.allreduce(retained_bytes_local, op=MPI.SUM)
        ),
    }
    return matrix, audit


@dataclass
class OwnerLocalTraceTransfer:
    """Owner-local active-trace transfer with an exact conjugate adjoint."""

    coarse_space: Any
    fine_space: Any
    coarse_constraints: TraceConstraintMap
    fine_constraints: TraceConstraintMap
    comm: MPI.Intracomm = field(repr=False)
    row_global_ids: np.ndarray
    row_offsets: np.ndarray
    column_ids: np.ndarray
    source_positions: np.ndarray
    values: np.ndarray
    coarse_needed_ids: np.ndarray
    coarse_owner_range: tuple[int, int]
    fine_owner_range: tuple[int, int]
    _scatter: PETSc.Scatter = field(repr=False)
    _coarse_source: PETSc.Vec = field(repr=False)
    _coarse_global_is: PETSc.IS = field(repr=False)
    _coarse_local_is: PETSc.IS = field(repr=False)
    audit: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def _check_vectors(self, coarse: PETSc.Vec, fine: PETSc.Vec) -> None:
        if int(coarse.getSize()) != int(self.coarse_constraints.active_rows):
            raise ValueError("p2 active vector has an unexpected global size")
        if int(fine.getSize()) != int(self.fine_constraints.active_rows):
            raise ValueError("p6 active vector has an unexpected global size")
        if tuple(map(int, coarse.getOwnershipRange())) != self.coarse_owner_range:
            raise ValueError("p2 active vector ownership does not match the transfer")
        if tuple(map(int, fine.getOwnershipRange())) != self.fine_owner_range:
            raise ValueError("p6 active vector ownership does not match the transfer")

    def apply(self, coarse: PETSc.Vec, fine: PETSc.Vec) -> None:
        """Apply ``q6 = P q2`` using only owner-local row stencils."""

        self._check_vectors(coarse, fine)
        self._scatter.scatter(
            coarse,
            self._coarse_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        source = self._coarse_source.getArray(readonly=True)
        output = fine.getArray()
        weighted = self.values * source[self.source_positions]
        output[:] = 0.0
        nonempty = np.flatnonzero(np.diff(self.row_offsets))
        if len(nonempty):
            output[nonempty] = np.add.reduceat(weighted, self.row_offsets[nonempty])
        fine.assemble()

    def apply_adjoint(self, fine: PETSc.Vec, coarse: PETSc.Vec) -> None:
        """Apply the exact conjugate transpose ``q2 = Pᴴ q6``."""

        self._check_vectors(coarse, fine)
        coarse.set(0.0)
        fine_values = fine.getArray(readonly=True)
        self._coarse_source.set(0.0)
        repeated_fine = np.repeat(fine_values, np.diff(self.row_offsets))
        np.add.at(
            self._coarse_source.getArray(),
            self.source_positions,
            np.conjugate(self.values) * repeated_fine,
        )
        self._scatter.scatter(
            self._coarse_source,
            coarse,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        coarse.assemble()

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._scatter.destroy()
        self._coarse_global_is.destroy()
        self._coarse_local_is.destroy()
        self._coarse_source.destroy()
        self._destroyed = True


def build_p2_to_p6_active_trace_transfer(
    coarse_space,
    fine_space,
    coarse_constraints: TraceConstraintMap,
    fine_constraints: TraceConstraintMap,
) -> OwnerLocalTraceTransfer:
    """Build the fixed p2-to-p6 active-trace stencil without materializing P."""

    _validate_space(coarse_space, 2)
    _validate_space(fine_space, 6)
    if coarse_space.mesh is not fine_space.mesh:
        raise ValueError("p2 and p6 transfer spaces must share one mesh")
    comm = coarse_space.mesh.comm
    coarse_trace, coarse_interior = _trace_and_interior_positions(coarse_space)
    fine_trace, _fine_interior = _trace_and_interior_positions(fine_space)
    interpolation = _actual_p2_to_p6_interpolation(coarse_space, fine_space)

    topology = fine_space.mesh.topology
    topology.create_entity_permutations()
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    cell_map = topology.index_map(topology.dim)
    owned_cell_count = int(cell_map.size_local)
    cell_count = int(cell_map.size_local + cell_map.num_ghosts)
    fine_owner_original = {
        int(value) for value in fine_constraints.owned_active_original_dofs
    }
    fine_owner_rows = {
        int(fine_constraints.original_to_active[original])
        for original in fine_owner_original
    }
    row_maps: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    cell_info_nonzero_owned = 0
    max_interior_dependency = 0.0
    structural_zero_discarded_local = 0
    structural_zero_discarded_max_local = 0.0

    for cell in range(cell_count):
        if cell < owned_cell_count and int(cell_info[cell]) != 0:
            cell_info_nonzero_owned += 1
        coarse_global = _global_cell_dofs(coarse_space, cell)
        fine_global = _global_cell_dofs(fine_space, cell)
        coarse_trace_global = coarse_global[coarse_trace]
        coarse_active_ids, expansion, _identity = _cell_trace_expansion(
            coarse_trace_global, coarse_constraints
        )
        local_matrix = _oriented_trace_matrix(
            coarse_space,
            fine_space,
            interpolation,
            np.arange(int(coarse_space.element.space_dimension), dtype=np.int32),
            fine_trace,
            int(cell_info[cell]),
        )
        max_interior_dependency = max(
            max_interior_dependency,
            float(np.max(np.abs(local_matrix[:, coarse_interior]), initial=0.0)),
        )
        active_matrix = local_matrix[:, coarse_trace] @ expansion.toarray()
        for local_row, original in enumerate(fine_global[fine_trace]):
            active_row = fine_constraints.original_to_active.get(int(original))
            if active_row not in fine_owner_rows:
                continue
            (
                columns,
                values,
                discarded_count,
                discarded_max,
            ) = _row_entries(coarse_active_ids, active_matrix[local_row])
            structural_zero_discarded_local += discarded_count
            structural_zero_discarded_max_local = max(
                structural_zero_discarded_max_local, discarded_max
            )
            previous = row_maps.get(int(active_row))
            if previous is not None:
                previous_columns, previous_values = previous
                union = np.union1d(previous_columns, columns)
                left = np.zeros(len(union), dtype=np.complex128)
                right = np.zeros(len(union), dtype=np.complex128)
                left[np.searchsorted(union, previous_columns)] = previous_values
                right[np.searchsorted(union, columns)] = values
                if float(np.max(np.abs(left - right), initial=0.0)) > 1.0e-12:
                    raise RuntimeError(
                        f"p6 active row {int(active_row)} has inconsistent cell stencils"
                    )
                continue
            row_maps[int(active_row)] = (columns, values)

    if max_interior_dependency > 1.0e-12:
        raise NotImplementedError(
            "p2 cell-interior DoFs contribute to the p6 trace interpolation"
        )
    coarse_layout = PETSc.Vec().createMPI(
        (
            len(coarse_constraints.owned_active_original_dofs),
            int(coarse_constraints.active_rows),
        ),
        comm=comm,
    )
    fine_layout = PETSc.Vec().createMPI(
        (
            len(fine_constraints.owned_active_original_dofs),
            int(fine_constraints.active_rows),
        ),
        comm=comm,
    )
    fine_owner_range = tuple(map(int, fine_layout.getOwnershipRange()))
    coarse_owner_range = tuple(map(int, coarse_layout.getOwnershipRange()))
    fine_layout.destroy()
    row_start, row_end = fine_owner_range
    row_ids = np.arange(row_start, row_end, dtype=PETSc.IntType)
    missing = [int(row) for row in row_ids if int(row) not in row_maps]
    if missing:
        coarse_layout.destroy()
        raise RuntimeError(
            f"p6 active owner rows lack designated cell stencils: {missing[:8]}"
        )
    ordered = [row_maps[int(row)] for row in row_ids]
    offsets = np.zeros(len(ordered) + 1, dtype=PETSc.IntType)
    offsets[1:] = np.cumsum([len(columns) for columns, _values in ordered])
    column_ids = np.asarray(
        np.concatenate([columns for columns, _values in ordered]), dtype=PETSc.IntType
    )
    values = np.asarray(
        np.concatenate([row_values for _columns, row_values in ordered]),
        dtype=np.complex128,
    )
    needed = np.unique(column_ids).astype(PETSc.IntType, copy=False)
    source = PETSc.Vec().createSeq(len(needed), comm=PETSc.COMM_SELF)
    global_is = PETSc.IS().createGeneral(needed, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        len(needed), first=0, step=1, comm=PETSc.COMM_SELF
    )
    scatter = PETSc.Scatter().create(coarse_layout, global_is, source, local_is)
    coarse_layout.destroy()
    source_positions = np.searchsorted(needed, column_ids).astype(PETSc.IntType)
    global_rows = int(comm.allreduce(len(row_ids), op=MPI.SUM))
    if global_rows != int(fine_constraints.active_rows):
        scatter.destroy()
        global_is.destroy()
        local_is.destroy()
        source.destroy()
        raise RuntimeError("p6 active row ownership does not cover all rows")
    return OwnerLocalTraceTransfer(
        coarse_space=coarse_space,
        fine_space=fine_space,
        coarse_constraints=coarse_constraints,
        fine_constraints=fine_constraints,
        comm=comm,
        row_global_ids=row_ids,
        row_offsets=offsets,
        column_ids=column_ids,
        source_positions=source_positions,
        values=values,
        coarse_needed_ids=needed,
        coarse_owner_range=coarse_owner_range,
        fine_owner_range=fine_owner_range,
        _scatter=scatter,
        _coarse_source=source,
        _coarse_global_is=global_is,
        _coarse_local_is=local_is,
        audit={
            "status": "owner_local_trace_stencil",
            "p2_global_active_rows": int(coarse_constraints.active_rows),
            "p6_global_active_rows": int(fine_constraints.active_rows),
            "local_owned_p6_rows": int(len(row_ids)),
            "local_stencil_nnz": int(len(column_ids)),
            "global_stencil_nnz": int(comm.allreduce(len(column_ids), op=MPI.SUM)),
            "owner_local_stencil_nbytes": int(
                row_ids.nbytes
                + offsets.nbytes
                + column_ids.nbytes
                + source_positions.nbytes
                + values.nbytes
            ),
            "source_staging_nbytes": int(
                source.getLocalSize() * np.dtype(np.complex128).itemsize
            ),
            "communication_index_nbytes": int(needed.nbytes),
            "structural_zero_tolerance": STRUCTURAL_ZERO_TOLERANCE,
            "structural_zero_discarded_candidate_count": int(
                comm.allreduce(structural_zero_discarded_local, op=MPI.SUM)
            ),
            "structural_zero_discarded_candidate_max_abs": float(
                comm.allreduce(structural_zero_discarded_max_local, op=MPI.MAX)
            ),
            "remote_coarse_columns_local": int(
                np.count_nonzero(
                    (column_ids < coarse_owner_range[0])
                    | (column_ids >= coarse_owner_range[1])
                )
            ),
            "cell_info_nonzero_count": int(
                comm.allreduce(cell_info_nonzero_owned, op=MPI.SUM)
            ),
            "trace_interior_dependency_max": float(
                comm.allreduce(max_interior_dependency, op=MPI.MAX)
            ),
            "global_transfer_matrix_materialized": False,
            "allgather_active_values": False,
            "global_basis_sweep": False,
        },
    )
