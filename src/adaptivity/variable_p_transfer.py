"""Matrix-free global transfer between active variable-p and p6 storage."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc
from scipy import linalg as dense_linalg

from .exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from .variable_p_entity_map import (
    VariablePCellDofMap,
    VariablePGlobalEntityMap,
)


@dataclass(frozen=True)
class VariablePCellTransfer:
    """One owned cell's p6 occurrence and canonical row designation."""

    cell: VariablePCellDofMap
    p6_local_dofs: np.ndarray
    p6_global_dofs: np.ndarray
    designated_local_positions: np.ndarray
    designated_active_local_positions: np.ndarray


@dataclass(frozen=True)
class VariablePGlobalTransfer:
    """Partition-aware, matrix-free active/p6 expansion authority."""

    entity_map: VariablePGlobalEntityMap
    p6_space: Any
    cells: tuple[VariablePCellTransfer, ...]
    active_counts: tuple[int, ...]
    audit: Mapping[str, Any]


@dataclass
class PETScSelectedRowLayout:
    """Reusable PETSc scatter for one rank-local set of global rows."""

    global_rows: np.ndarray
    global_size: int
    local_size: int
    ownership_range: tuple[int, int]
    requested_row_count: int
    source_is: PETSc.IS
    destination_is: PETSc.IS
    destination: PETSc.Vec
    scatter: PETSc.Scatter
    _destroyed: bool = False

    @classmethod
    def create(
        cls,
        template: PETSc.Vec,
        global_rows: np.ndarray,
    ) -> PETScSelectedRowLayout:
        """Build one duplicate-tolerant selected-row scatter collectively."""

        requested = np.asarray(global_rows)
        if requested.ndim != 1 or not np.issubdtype(
            requested.dtype,
            np.integer,
        ):
            raise ValueError("selected PETSc rows must be a one-dimensional integer array")
        rows = np.unique(requested.astype(np.int64, copy=False))
        global_size = int(template.getSize())
        if np.any(rows < 0) or np.any(rows >= global_size):
            raise ValueError("selected PETSc row is outside the global vector")
        petsc_rows = np.asarray(rows, dtype=PETSc.IntType)
        source_is = PETSc.IS().createGeneral(
            petsc_rows,
            comm=template.comm,
        )
        destination = PETSc.Vec().createSeq(
            len(rows),
            comm=PETSc.COMM_SELF,
        )
        destination_is = PETSc.IS().createStride(
            len(rows),
            first=0,
            step=1,
            comm=PETSc.COMM_SELF,
        )
        scatter = PETSc.Scatter().create(
            template,
            source_is,
            destination,
            destination_is,
        )
        rows.setflags(write=False)
        return cls(
            global_rows=rows,
            global_size=global_size,
            local_size=int(template.getLocalSize()),
            ownership_range=tuple(map(int, template.getOwnershipRange())),
            requested_row_count=int(len(requested)),
            source_is=source_is,
            destination_is=destination_is,
            destination=destination,
            scatter=scatter,
        )

    def gather(self, vector: PETSc.Vec) -> np.ndarray:
        """Return only selected values, preserving sorted global-row order."""

        if self._destroyed:
            raise RuntimeError("selected-row layout is already destroyed")
        if (
            int(vector.getSize()) != self.global_size
            or int(vector.getLocalSize()) != self.local_size
            or tuple(map(int, vector.getOwnershipRange()))
            != self.ownership_range
        ):
            raise ValueError("selected-row vector layout differs from its template")
        self.scatter.scatter(
            vector,
            self.destination,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        return np.asarray(
            self.destination.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()

    def positions(self, global_rows: np.ndarray) -> np.ndarray:
        """Map a selected global-row subset to gathered-array positions."""

        requested = np.asarray(global_rows)
        if requested.ndim != 1 or not np.issubdtype(
            requested.dtype,
            np.integer,
        ):
            raise ValueError("requested row positions must be an integer array")
        requested = requested.astype(np.int64, copy=False)
        positions = np.searchsorted(self.global_rows, requested)
        if np.any(positions >= len(self.global_rows)) or not np.array_equal(
            self.global_rows[positions],
            requested,
        ):
            raise ValueError("requested row was not included in the layout")
        return positions

    @property
    def audit(self) -> dict[str, Any]:
        """Describe selected storage without counting full-vector replication."""

        scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
        return {
            "schema_version": "task035e.petsc-selected-row-layout.v1",
            "status": "owner_local_selected_row_scatter_built",
            "pass": True,
            "global_vector_rows": self.global_size,
            "requested_row_count_local": self.requested_row_count,
            "selected_unique_row_count_local": len(self.global_rows),
            "duplicate_request_count_local": (
                self.requested_row_count - len(self.global_rows)
            ),
            "selected_value_bytes_local": (
                len(self.global_rows) * scalar_bytes
            ),
            "replicated_full_vector_bytes_per_rank": 0,
            "full_vector_allgather_used": False,
            "petsc_is_scatter_used": True,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.scatter.destroy()
        self.destination_is.destroy()
        self.destination.destroy()
        self.source_is.destroy()
        self._destroyed = True

    def __enter__(self) -> PETScSelectedRowLayout:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


def _balanced_counts(total: int, size: int) -> tuple[int, ...]:
    quotient, remainder = divmod(int(total), int(size))
    return tuple(
        quotient + (1 if rank < remainder else 0)
        for rank in range(size)
    )


def _owned_cell_active_values(
    transfer: VariablePGlobalTransfer,
    values: PETSc.Vec | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    required = np.unique(
        np.concatenate(
            [cell.cell.active_rows for cell in transfer.cells]
            or [np.empty(0, dtype=np.int64)]
        )
    ).astype(np.int64, copy=False)
    if isinstance(values, PETSc.Vec):
        if values.getSize() != transfer.entity_map.active_rows:
            raise ValueError("active vector has the wrong global size")
        with PETScSelectedRowLayout.create(values, required) as layout:
            result = layout.gather(values)
            audit = dict(layout.audit)
        input_kind = "distributed_petsc_vec"
    else:
        global_values = np.asarray(values, dtype=np.complex128)
        if global_values.shape != (transfer.entity_map.active_rows,):
            raise ValueError("active coefficient array has the wrong global size")
        result = np.asarray(global_values[required], dtype=np.complex128)
        audit = {
            "schema_version": "task035e.petsc-selected-row-layout.v1",
            "status": "caller_supplied_global_numpy_array",
            "pass": True,
            "global_vector_rows": transfer.entity_map.active_rows,
            "requested_row_count_local": len(required),
            "selected_unique_row_count_local": len(required),
            "duplicate_request_count_local": 0,
            "selected_value_bytes_local": int(result.nbytes),
            "replicated_full_vector_bytes_per_rank": int(
                global_values.nbytes
            ),
            "full_vector_allgather_used": False,
            "petsc_is_scatter_used": False,
        }
        input_kind = "global_numpy_array"
    audit["input_kind"] = input_kind
    return required, result, audit


def build_variable_p_global_transfer(
    entity_map: VariablePGlobalEntityMap,
    p6_space: Any,
) -> VariablePGlobalTransfer:
    """Choose one physical-cell definition for every global p6 coefficient."""

    msh = entity_map.mesh
    if p6_space.mesh is not msh:
        raise ValueError("p6 transfer space must use the entity-map mesh")
    dofmap = p6_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise ValueError("p6 transfer requires scalar-blocked H(curl)")
    element = p6_space.element.basix_element
    if (
        int(element.dim) != 882
        or "hexahedron" not in str(element.cell_type).lower()
        or "covariant" not in str(element.map_type).lower()
    ):
        raise ValueError("transfer storage must be hexahedral N1curl p6")
    cells = entity_map.owned_cells
    local_dofs_by_cell: list[np.ndarray] = []
    global_dofs_by_cell: list[np.ndarray] = []
    p6_rows = int(dofmap.index_map.size_global)
    sentinel = np.iinfo(np.int64).max
    local_designated_cell = np.full(
        p6_rows,
        sentinel,
        dtype=np.int64,
    )
    local_active_designated_cell = np.full(
        entity_map.active_rows,
        sentinel,
        dtype=np.int64,
    )
    for cell in cells:
        local_dofs = np.asarray(
            dofmap.cell_dofs(cell.local_cell),
            dtype=np.int32,
        )
        if local_dofs.shape != (882,):
            raise RuntimeError("p6 cell dofmap does not contain 882 entries")
        global_dofs = np.asarray(
            dofmap.index_map.local_to_global(local_dofs),
            dtype=np.int64,
        )
        local_dofs_by_cell.append(local_dofs)
        global_dofs_by_cell.append(global_dofs)
        np.minimum.at(
            local_designated_cell,
            global_dofs,
            np.int64(cell.global_cell),
        )
        np.minimum.at(
            local_active_designated_cell,
            cell.active_rows,
            np.int64(cell.global_cell),
        )
    designated_cell = np.empty_like(local_designated_cell)
    msh.comm.Allreduce(
        local_designated_cell,
        designated_cell,
        op=MPI.MIN,
    )
    if np.any(designated_cell == sentinel):
        raise RuntimeError("one or more global p6 rows have no incident cell")
    active_designated_cell = np.empty_like(
        local_active_designated_cell
    )
    msh.comm.Allreduce(
        local_active_designated_cell,
        active_designated_cell,
        op=MPI.MIN,
    )
    if np.any(active_designated_cell == sentinel):
        raise RuntimeError("one or more active rows have no incident cell")

    transfers: list[VariablePCellTransfer] = []
    local_designated_rows: list[np.ndarray] = []
    local_designated_active_rows: list[np.ndarray] = []
    block_designation_violations = 0
    entity_positions = [
        np.asarray(entity, dtype=np.int32)
        for dimension in (1, 2, 3)
        for entity in element.entity_dofs[dimension]
    ]
    for cell, local_dofs, global_dofs in zip(
        cells,
        local_dofs_by_cell,
        global_dofs_by_cell,
        strict=True,
    ):
        selected = np.flatnonzero(
            designated_cell[global_dofs] == cell.global_cell
        ).astype(np.int32)
        selected_active = np.flatnonzero(
            active_designated_cell[cell.active_rows] == cell.global_cell
        ).astype(np.int32)
        selected_mask = np.zeros(882, dtype=bool)
        selected_mask[selected] = True
        for positions in entity_positions:
            count = int(np.count_nonzero(selected_mask[positions]))
            if count not in {0, len(positions)}:
                block_designation_violations += 1
        local_designated_rows.append(global_dofs[selected])
        local_designated_active_rows.append(
            cell.active_rows[selected_active]
        )
        for values in (
            local_dofs,
            global_dofs,
            selected,
            selected_active,
        ):
            values.setflags(write=False)
        transfers.append(
            VariablePCellTransfer(
                cell=cell,
                p6_local_dofs=local_dofs,
                p6_global_dofs=global_dofs,
                designated_local_positions=selected,
                designated_active_local_positions=selected_active,
            )
        )
    local_selected_global = (
        np.concatenate(local_designated_rows)
        if local_designated_rows
        else np.empty(0, dtype=np.int64)
    )
    local_designation_counts = np.zeros(p6_rows, dtype=np.int32)
    np.add.at(local_designation_counts, local_selected_global, 1)
    global_designation_counts = np.empty_like(local_designation_counts)
    msh.comm.Allreduce(
        local_designation_counts,
        global_designation_counts,
        op=MPI.SUM,
    )
    selected_row_count = int(
        msh.comm.allreduce(len(local_selected_global), op=MPI.SUM)
    )
    if selected_row_count != p6_rows or not np.all(
        global_designation_counts == 1
    ):
        raise RuntimeError("global p6 row designation is not one-to-one")
    local_active_designation_counts = np.zeros(
        entity_map.active_rows,
        dtype=np.int32,
    )
    np.add.at(
        local_active_designation_counts,
        (
            np.concatenate(local_designated_active_rows)
            if local_designated_active_rows
            else np.empty(0, dtype=np.int64)
        ),
        1,
    )
    global_active_designation_counts = np.empty_like(
        local_active_designation_counts
    )
    msh.comm.Allreduce(
        local_active_designation_counts,
        global_active_designation_counts,
        op=MPI.SUM,
    )
    if not np.all(global_active_designation_counts == 1):
        raise RuntimeError(
            "global active row designation is not one-to-one"
        )
    global_block_violations = int(
        msh.comm.allreduce(block_designation_violations)
    )
    if global_block_violations:
        raise RuntimeError(
            "p6 row designation split one topological entity block"
        )
    active_counts = _balanced_counts(entity_map.active_rows, msh.comm.size)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.variable-p-global-transfer.v1",
            "status": "matrix_free_active_p6_transfer_built",
            "pass": True,
            "mpi_size": int(msh.comm.size),
            "p6_global_rows": p6_rows,
            "active_global_rows": entity_map.active_rows,
            "owned_cell_count_global": int(
                msh.comm.allreduce(len(cells), op=MPI.SUM)
            ),
            "designated_p6_row_count": selected_row_count,
            "designation_is_one_to_one": True,
            "entity_blocks_never_split_between_designating_cells": True,
            "designation_build_collective": (
                "dense_row_owner_min_and_count_allreduce"
            ),
            "designation_occurrence_allgather_used": False,
            "designation_dense_owner_bytes_per_rank": int(
                designated_cell.nbytes
            ),
            "designation_dense_count_bytes_per_rank": int(
                global_designation_counts.nbytes
            ),
            "active_primal_designation_dense_owner_bytes_per_rank": int(
                active_designated_cell.nbytes
            ),
            "active_primal_designation_is_one_to_one": True,
            "designation_dense_collective_peak_bytes_per_rank": int(
                2
                * (
                    designated_cell.nbytes
                    + global_designation_counts.nbytes
                    + active_designated_cell.nbytes
                    + global_active_designation_counts.nbytes
                )
            ),
            "global_embedding_matrix_allocated": False,
            "full_p6_global_operator_allocated": False,
            "inactive_p6_rows_in_active_operator": False,
            "ordinary_default_changed": False,
        }
    )
    return VariablePGlobalTransfer(
        entity_map=entity_map,
        p6_space=p6_space,
        cells=tuple(transfers),
        active_counts=active_counts,
        audit=audit,
    )


@lru_cache(maxsize=12)
def _p6_primal_normal_factor(
    degree_map: HexaEntityDegreeMap,
) -> tuple[np.ndarray, float, float]:
    """Cache one small normal-equation factor per active degree class."""

    space = build_variable_p_reference_space(degree_map)
    expansion = np.asarray(space.hcurl_to_p6)
    gram = np.ascontiguousarray(expansion.conj().T @ expansion)
    cholesky = np.linalg.cholesky(gram)
    factor_error = float(
        np.max(
            np.abs(
                cholesky @ cholesky.conj().T - gram
            ),
            initial=0.0,
        )
        / max(float(np.max(np.abs(gram), initial=0.0)), 1.0)
    )
    condition = float(np.sqrt(np.linalg.cond(gram)))
    cholesky = np.ascontiguousarray(cholesky)
    cholesky.setflags(write=False)
    return cholesky, factor_error, condition


def _project_p6_oriented_primal_local(
    cell: VariablePCellDofMap,
    p6_values: np.ndarray,
) -> tuple[np.ndarray, float, float, int]:
    space = build_variable_p_reference_space(cell.degree_map)
    p6_space = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(6)
    )
    p6_reference = p6_space.apply_hcurl_dof_transform(
        np.asarray(p6_values, dtype=np.complex128),
        cell_info=cell.cell_info,
        transpose=True,
    )
    cholesky, factor_error, condition = _p6_primal_normal_factor(
        cell.degree_map
    )
    expansion = np.asarray(space.hcurl_to_p6)
    right_hand_side = expansion.conj().T @ p6_reference
    intermediate = dense_linalg.solve_triangular(
        cholesky,
        right_hand_side,
        lower=True,
        check_finite=False,
    )
    active_reference = dense_linalg.solve_triangular(
        cholesky.conj().T,
        intermediate,
        lower=False,
        check_finite=False,
    )
    active = space.apply_hcurl_dof_transform(
        active_reference,
        cell_info=cell.cell_info,
    )
    return (
        np.asarray(active, dtype=np.complex128),
        factor_error,
        condition,
        int(cholesky.nbytes),
    )


def project_p6_primal_to_active_full(
    transfer: VariablePGlobalTransfer,
    p6_vector: PETSc.Vec,
    *,
    require_exact_nested: bool = False,
    exact_tolerance: float = 5.0e-10,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Inject p6 primal coefficients by a local coefficient-L2 projection.

    If the source is contractually nested in the shadow active range,
    ``require_exact_nested`` makes both the local round trip and shared-row
    agreement fail closed. A nonmatching source remains an explicitly
    approximate projection and receives no exact-transfer credit.
    """

    p6_rows = int(transfer.p6_space.dofmap.index_map.size_global)
    if p6_vector.getSize() != p6_rows:
        raise ValueError("p6 primal vector has the wrong global size")
    tolerance = float(exact_tolerance)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("exact nested tolerance must be positive and finite")
    p6_vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    with p6_vector.localForm() as local_form:
        local_p6_values = np.asarray(
            local_form.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
    comm = transfer.entity_map.mesh.comm
    active = PETSc.Vec().createMPI(
        (
            transfer.active_counts[comm.rank],
            transfer.entity_map.active_rows,
        ),
        comm=comm,
    )
    active.set(PETSc.ScalarType(0.0))
    local_factor_error = 0.0
    local_left_inverse_condition = 0.0
    local_factor_bytes_max = 0
    for cell_transfer in transfer.cells:
        cell = cell_transfer.cell
        local_active, factor_error, condition, factor_bytes = (
            _project_p6_oriented_primal_local(
                cell,
                local_p6_values[cell_transfer.p6_local_dofs],
            )
        )
        local_factor_error = max(local_factor_error, factor_error)
        local_left_inverse_condition = max(
            local_left_inverse_condition,
            condition,
        )
        local_factor_bytes_max = max(
            local_factor_bytes_max,
            factor_bytes,
        )
        selected = cell_transfer.designated_active_local_positions
        active.setValues(
            np.asarray(cell.active_rows[selected], dtype=PETSc.IntType),
            np.asarray(local_active[selected], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    active.assemble()

    requested_active_rows = np.concatenate(
        [cell.cell.active_rows for cell in transfer.cells]
        or [np.empty(0, dtype=np.int64)]
    )
    with PETScSelectedRowLayout.create(
        active,
        requested_active_rows,
    ) as layout:
        selected_active = layout.gather(active)
        selected_row_audit = dict(layout.audit)
        local_shared_error = 0.0
        local_shared_scale = 0.0
        local_projection_error_sq = 0.0
        local_p6_sq = 0.0
        for cell_transfer in transfer.cells:
            cell = cell_transfer.cell
            local_p6 = local_p6_values[cell_transfer.p6_local_dofs]
            (
                predicted_active,
                _factor_error,
                _condition,
                _factor_bytes,
            ) = (
                _project_p6_oriented_primal_local(cell, local_p6)
            )
            observed_active = selected_active[
                layout.positions(cell.active_rows)
            ]
            local_shared_error = max(
                local_shared_error,
                float(
                    np.max(
                        np.abs(observed_active - predicted_active),
                        initial=0.0,
                    )
                ),
            )
            local_shared_scale = max(
                local_shared_scale,
                float(
                    np.max(np.abs(predicted_active), initial=0.0)
                ),
            )
            space = build_variable_p_reference_space(cell.degree_map)
            round_trip = space.active_to_p6_oriented(
                observed_active,
                cell_info=cell.cell_info,
            )
            difference = round_trip - local_p6
            local_projection_error_sq += float(
                np.vdot(difference, difference).real
            )
            local_p6_sq += float(np.vdot(local_p6, local_p6).real)
    shared_error = float(
        comm.allreduce(local_shared_error, op=MPI.MAX)
    )
    shared_scale = float(
        comm.allreduce(local_shared_scale, op=MPI.MAX)
    )
    shared_relative_error = shared_error / max(shared_scale, 1.0e-30)
    projection_error = float(
        np.sqrt(comm.allreduce(local_projection_error_sq, op=MPI.SUM))
    )
    p6_norm = float(np.sqrt(comm.allreduce(local_p6_sq, op=MPI.SUM)))
    projection_relative_error = projection_error / max(p6_norm, 1.0e-30)
    factor_error = float(
        comm.allreduce(local_factor_error, op=MPI.MAX)
    )
    left_inverse_condition = float(
        comm.allreduce(local_left_inverse_condition, op=MPI.MAX)
    )
    factor_bytes_max = int(
        comm.allreduce(local_factor_bytes_max, op=MPI.MAX)
    )
    exact_nested_pass = bool(
        shared_relative_error <= tolerance
        and projection_relative_error <= tolerance
        and factor_error <= tolerance
    )
    audit = {
        "schema_version": "task035e.variable-p-p6-primal-projection.v1",
        "status": (
            "exact_nested_primal_round_trip_pass"
            if exact_nested_pass
            else "nonmatching_coefficient_l2_projection_completed"
        ),
        "pass": exact_nested_pass if require_exact_nested else True,
        "projection_semantics": (
            "local coefficient-L2 least-squares left inverse"
        ),
        "exact_nested_source_required": bool(require_exact_nested),
        "exact_nested_round_trip_pass": exact_nested_pass,
        "exact_nested_tolerance": tolerance,
        "shared_active_prediction_error_max": shared_error,
        "shared_active_prediction_relative_error_max": (
            shared_relative_error
        ),
        "p6_round_trip_error_l2": projection_error,
        "p6_round_trip_relative_error_l2": projection_relative_error,
        "normal_factorization_relative_error_max": factor_error,
        "left_inverse_condition_max": left_inverse_condition,
        "normal_factor_cached_by_degree_map": True,
        "normal_factor_cache_entries": (
            _p6_primal_normal_factor.cache_info().currsize
        ),
        "normal_factor_bytes_per_degree_class_max": factor_bytes_max,
        "active_selected_rows": selected_row_audit,
        "replicated_full_active_vector_bytes_per_rank": 0,
        "replicated_full_p6_vector_bytes_per_rank": 0,
        "full_vector_allgather_used": False,
        "nonmatching_projection_receives_exact_transfer_credit": False,
        "ordinary_default_changed": False,
    }
    if require_exact_nested and not exact_nested_pass:
        active.destroy()
        raise RuntimeError(
            "p6 primal source is outside the required nested active range: "
            f"shared={shared_relative_error:.6e}, "
            f"round_trip={projection_relative_error:.6e}, "
            f"normal_factor={factor_error:.6e}"
        )
    return active, audit


def project_p6_dual_to_active_full(
    transfer: VariablePGlobalTransfer,
    p6_vector: PETSc.Vec,
) -> PETSc.Vec:
    """Apply the global expansion's Hermitian transpose without storing it."""

    p6_rows = int(transfer.p6_space.dofmap.index_map.size_global)
    if p6_vector.getSize() != p6_rows:
        raise ValueError("p6 dual vector has the wrong global size")
    p6_vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    with p6_vector.localForm() as local_form:
        local_values = np.asarray(
            local_form.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
    comm = transfer.entity_map.mesh.comm
    active = PETSc.Vec().createMPI(
        (
            transfer.active_counts[comm.rank],
            transfer.entity_map.active_rows,
        ),
        comm=comm,
    )
    for cell_transfer in transfer.cells:
        selected = cell_transfer.designated_local_positions
        local_p6 = np.zeros(882, dtype=np.complex128)
        local_p6[selected] = local_values[
            cell_transfer.p6_local_dofs[selected]
        ]
        space = build_variable_p_reference_space(
            cell_transfer.cell.degree_map
        )
        local_active = space.project_p6_oriented_dual(
            local_p6,
            cell_info=cell_transfer.cell.cell_info,
        )
        active.setValues(
            np.asarray(
                cell_transfer.cell.active_rows,
                dtype=PETSc.IntType,
            ),
            np.asarray(local_active, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    active.assemble()
    return active


def recover_active_full_to_p6_field(
    transfer: VariablePGlobalTransfer,
    active_values: PETSc.Vec | np.ndarray,
    *,
    conformity_tolerance: float = 5.0e-10,
) -> tuple[Any, dict[str, Any]]:
    """Recover one conforming p6 storage field from active coefficients."""

    selected_rows, active, selected_row_audit = (
        _owned_cell_active_values(transfer, active_values)
    )

    def cell_active(cell: VariablePCellDofMap) -> np.ndarray:
        positions = np.searchsorted(selected_rows, cell.active_rows)
        if (
            np.any(positions >= len(selected_rows))
            or not np.array_equal(
                selected_rows[positions],
                cell.active_rows,
            )
        ):
            raise RuntimeError(
                "owned-cell active rows escaped the selected-row layout"
            )
        return active[positions]

    field = fem.Function(transfer.p6_space)
    vector = field.x.petsc_vec
    vector.set(PETSc.ScalarType(0.0))
    for cell_transfer in transfer.cells:
        cell = cell_transfer.cell
        space = build_variable_p_reference_space(cell.degree_map)
        local_active = cell_active(cell)
        local_p6 = space.active_to_p6_oriented(
            local_active,
            cell_info=cell.cell_info,
        )
        selected = cell_transfer.designated_local_positions
        vector.setValues(
            np.asarray(
                cell_transfer.p6_global_dofs[selected],
                dtype=PETSc.IntType,
            ),
            np.asarray(local_p6[selected], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    vector.assemble()
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    local_values = np.asarray(field.x.array, dtype=np.complex128)
    local_error = 0.0
    local_scale = 0.0
    for cell_transfer in transfer.cells:
        cell = cell_transfer.cell
        space = build_variable_p_reference_space(cell.degree_map)
        predicted = space.active_to_p6_oriented(
            cell_active(cell),
            cell_info=cell.cell_info,
        )
        observed = local_values[cell_transfer.p6_local_dofs]
        local_error = max(
            local_error,
            float(np.max(np.abs(observed - predicted), initial=0.0)),
        )
        local_scale = max(
            local_scale,
            float(np.max(np.abs(predicted), initial=0.0)),
        )
    comm = transfer.entity_map.mesh.comm
    error = float(comm.allreduce(local_error, op=MPI.MAX))
    scale = float(comm.allreduce(local_scale, op=MPI.MAX))
    relative_error = error / max(scale, 1.0e-30)
    if relative_error > float(conformity_tolerance):
        raise RuntimeError(
            "active-to-p6 recovery is not shared-entity conforming: "
            f"relative_error={relative_error:.3e}"
        )
    return field, {
        "schema_version": "task035d.variable-p-p6-recovery.v1",
        "status": "conforming_p6_storage_recovery_pass",
        "pass": True,
        "absolute_shared_coefficient_error_max": error,
        "relative_shared_coefficient_error_max": relative_error,
        "conformity_tolerance": float(conformity_tolerance),
        "active_selected_rows": selected_row_audit,
        "active_selected_row_count_local": len(selected_rows),
        "full_active_vector_replicated_bytes_per_rank": int(
            selected_row_audit[
                "replicated_full_vector_bytes_per_rank"
            ]
        ),
        "selected_row_scatter_cache_count": (
            1
            if selected_row_audit["petsc_is_scatter_used"]
            else 0
        ),
        "selected_values_reused_for_recovery_and_conformity_audit": True,
        "global_embedding_matrix_allocated": False,
        "ordinary_default_changed": False,
    }


__all__ = [
    "PETScSelectedRowLayout",
    "VariablePCellTransfer",
    "VariablePGlobalTransfer",
    "build_variable_p_global_transfer",
    "project_p6_primal_to_active_full",
    "project_p6_dual_to_active_full",
    "recover_active_full_to_p6_field",
]
