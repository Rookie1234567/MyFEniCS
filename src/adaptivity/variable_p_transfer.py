"""Matrix-free global transfer between active variable-p and p6 storage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from .exact_sequence_variable_p import (
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


@dataclass(frozen=True)
class VariablePGlobalTransfer:
    """Partition-aware, matrix-free active/p6 expansion authority."""

    entity_map: VariablePGlobalEntityMap
    p6_space: Any
    cells: tuple[VariablePCellTransfer, ...]
    active_counts: tuple[int, ...]
    audit: Mapping[str, Any]


def _balanced_counts(total: int, size: int) -> tuple[int, ...]:
    quotient, remainder = divmod(int(total), int(size))
    return tuple(
        quotient + (1 if rank < remainder else 0)
        for rank in range(size)
    )


def _global_active_values(
    transfer: VariablePGlobalTransfer,
    values: PETSc.Vec | np.ndarray,
) -> np.ndarray:
    if isinstance(values, PETSc.Vec):
        if values.getSize() != transfer.entity_map.active_rows:
            raise ValueError("active vector has the wrong global size")
        owned = np.asarray(
            values.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        packets = transfer.entity_map.mesh.comm.allgather(owned)
        result = np.concatenate(packets)
    else:
        result = np.asarray(values, dtype=np.complex128)
    if result.shape != (transfer.entity_map.active_rows,):
        raise ValueError("active coefficient array has the wrong global size")
    return result


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
    occurrence_dofs: list[np.ndarray] = []
    occurrence_cells: list[np.ndarray] = []
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
        occurrence_dofs.append(global_dofs)
        occurrence_cells.append(
            np.full(882, cell.global_cell, dtype=np.int64)
        )
    local_occurrence_dofs = (
        np.concatenate(occurrence_dofs)
        if occurrence_dofs
        else np.empty(0, dtype=np.int64)
    )
    local_occurrence_cells = (
        np.concatenate(occurrence_cells)
        if occurrence_cells
        else np.empty(0, dtype=np.int64)
    )
    packets = msh.comm.allgather(
        (local_occurrence_dofs, local_occurrence_cells)
    )
    p6_rows = int(dofmap.index_map.size_global)
    sentinel = np.iinfo(np.int64).max
    designated_cell = np.full(p6_rows, sentinel, dtype=np.int64)
    for packet_dofs, packet_cells in packets:
        np.minimum.at(designated_cell, packet_dofs, packet_cells)
    if np.any(designated_cell == sentinel):
        raise RuntimeError("one or more global p6 rows have no incident cell")

    transfers: list[VariablePCellTransfer] = []
    local_designated_rows: list[np.ndarray] = []
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
        selected_mask = np.zeros(882, dtype=bool)
        selected_mask[selected] = True
        for positions in entity_positions:
            count = int(np.count_nonzero(selected_mask[positions]))
            if count not in {0, len(positions)}:
                block_designation_violations += 1
        local_designated_rows.append(global_dofs[selected])
        for values in (local_dofs, global_dofs, selected):
            values.setflags(write=False)
        transfers.append(
            VariablePCellTransfer(
                cell=cell,
                p6_local_dofs=local_dofs,
                p6_global_dofs=global_dofs,
                designated_local_positions=selected,
            )
        )
    selected_packets = msh.comm.allgather(
        np.concatenate(local_designated_rows)
        if local_designated_rows
        else np.empty(0, dtype=np.int64)
    )
    selected_global = np.concatenate(selected_packets)
    if (
        len(selected_global) != p6_rows
        or not np.array_equal(
            np.sort(selected_global),
            np.arange(p6_rows, dtype=np.int64),
        )
    ):
        raise RuntimeError("global p6 row designation is not one-to-one")
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
            "designated_p6_row_count": len(selected_global),
            "designation_is_one_to_one": True,
            "entity_blocks_never_split_between_designating_cells": True,
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


def extract_active_full_from_p6_field(
    transfer: VariablePGlobalTransfer,
    p6_field: Any,
    *,
    shared_row_tolerance: float = 5.0e-10,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Primal-extract one p6 field into a nested active variable-p space.

    Each owned cell uses its verified Basix p6-to-active interpolation. Shared
    active rows are reconciled collectively before trace constraints or p6
    recovery are considered.
    """

    mesh = transfer.entity_map.mesh
    if mesh.comm.size != 1:
        raise ValueError("parent-to-candidate primal extraction is serial-only")
    if p6_field.function_space.mesh is not mesh:
        raise ValueError("p6 field and transfer must use the same mesh")
    dofmap = transfer.p6_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise ValueError("p6 primal extraction requires scalar-blocked H(curl)")
    local_coefficients = np.asarray(
        p6_field.x.array,
        dtype=np.complex128,
    )
    expected_local_size = int(
        dofmap.index_map.size_local + dofmap.index_map.num_ghosts
    )
    if local_coefficients.shape != (expected_local_size,):
        raise ValueError("p6 field local coefficient layout differs from transfer")
    tolerance = float(shared_row_tolerance)
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("shared active-row tolerance must be finite and nonnegative")

    cache_before = build_variable_p_reference_space.cache_info()
    unique_maps = {cell.cell.degree_map for cell in transfer.cells}
    row_packets: list[np.ndarray] = []
    value_packets: list[np.ndarray] = []
    local_interpolation_error = 0.0
    for cell_transfer in transfer.cells:
        reference_space = build_variable_p_reference_space(
            cell_transfer.cell.degree_map
        )
        local_active, interpolation_audit = (
            reference_space.extract_hcurl_coefficients_from_p6(
                local_coefficients[cell_transfer.p6_local_dofs],
                cell_info=cell_transfer.cell.cell_info,
            )
        )
        row_packets.append(
            np.asarray(cell_transfer.cell.active_rows, dtype=np.int64)
        )
        value_packets.append(np.asarray(local_active, dtype=np.complex128))
        local_interpolation_error = max(
            local_interpolation_error,
            float(interpolation_audit["p6_to_active_identity_error_max"]),
        )

    comm = mesh.comm
    gathered_rows = comm.allgather(
        np.concatenate(row_packets)
        if row_packets
        else np.empty(0, dtype=np.int64)
    )
    gathered_values = comm.allgather(
        np.concatenate(value_packets)
        if value_packets
        else np.empty(0, dtype=np.complex128)
    )
    active = np.zeros(transfer.entity_map.active_rows, dtype=np.complex128)
    assigned = np.zeros(transfer.entity_map.active_rows, dtype=bool)
    maximum_shared_error = 0.0
    maximum_scale = 1.0
    for rows, values in zip(gathered_rows, gathered_values, strict=True):
        if rows.shape != values.shape:
            raise RuntimeError("primal transfer row/value packets differ in shape")
        if np.any(rows < 0) or np.any(rows >= transfer.entity_map.active_rows):
            raise RuntimeError("primal transfer contains an out-of-range active row")
        if not np.isfinite(values.real).all() or not np.isfinite(values.imag).all():
            raise RuntimeError("p6-to-active primal extraction produced non-finite values")
        for raw_row, raw_value in zip(rows, values, strict=True):
            row = int(raw_row)
            value = complex(raw_value)
            maximum_scale = max(maximum_scale, abs(value))
            if assigned[row]:
                error = abs(active[row] - value)
                maximum_shared_error = max(maximum_shared_error, error)
                if error > tolerance * max(1.0, abs(active[row]), abs(value)):
                    raise RuntimeError(
                        "parent p6 field gives inconsistent shared active rows: "
                        f"row={row}, error={error:.6e}"
                    )
            else:
                active[row] = value
                assigned[row] = True
    if not np.all(assigned):
        raise RuntimeError(
            "p6-to-active extraction left active rows unset: "
            f"missing={int(np.count_nonzero(~assigned))}"
        )

    cache_after = build_variable_p_reference_space.cache_info()
    return active, {
        "schema_version": "task035d.variable-p-p6-primal-extraction.v1",
        "status": "primal_active_extraction_pass",
        "pass": True,
        "active_global_rows": int(transfer.entity_map.active_rows),
        "owned_cells": int(transfer.audit["owned_cell_count_global"]),
        "unique_cell_degree_maps": len(unique_maps),
        "maximum_p6_to_active_identity_error": local_interpolation_error,
        "maximum_shared_active_row_absolute_error": maximum_shared_error,
        "maximum_shared_active_row_relative_error": (
            maximum_shared_error / maximum_scale
        ),
        "shared_row_tolerance": tolerance,
        "reference_space_cache_before": {
            "hits": cache_before.hits,
            "misses": cache_before.misses,
            "maxsize": cache_before.maxsize,
            "currsize": cache_before.currsize,
        },
        "reference_space_cache_after": {
            "hits": cache_after.hits,
            "misses": cache_after.misses,
            "maxsize": cache_after.maxsize,
            "currsize": cache_after.currsize,
        },
        "reference_space_cache_delta": {
            "hits": cache_after.hits - cache_before.hits,
            "misses": cache_after.misses - cache_before.misses,
        },
        "global_embedding_matrix_allocated": False,
    }


def audit_full_active_trace_constraints(
    active_values: np.ndarray,
    trace_constraints: Any,
    *,
    tolerance: float = 5.0e-10,
) -> dict[str, Any]:
    """Check a full active trace vector against one serial flattened authority.

    Independent values are recovered only from physical root entity blocks.
    Every edge and face block, including periodic slaves, is then checked
    against its stored full-from-independent expansion.
    """

    comm = trace_constraints.entity_map.mesh.comm
    if comm.size != 1:
        raise ValueError("parent-to-candidate trace transfer audit is serial-only")
    values = np.asarray(active_values, dtype=np.complex128)
    entity_map = trace_constraints.entity_map
    if values.shape != (entity_map.active_rows,):
        raise ValueError("full active vector has the wrong entity-map size")
    if not np.isfinite(values.real).all() or not np.isfinite(values.imag).all():
        raise ValueError("full active vector contains non-finite values")
    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("trace constraint tolerance must be finite and nonnegative")

    authority_root_rows = set(trace_constraints.authority.graph.root_rows)
    independent_rows = int(trace_constraints.independent_trace_rows)
    independent_values = np.zeros(independent_rows, dtype=np.complex128)
    assigned = np.zeros(independent_rows, dtype=bool)
    root_block_count = 0
    blocks = tuple(trace_constraints.entity_blocks.values())
    for block in blocks:
        root_flags = [
            row in authority_root_rows for row in block.physical_entity.rows
        ]
        if any(root_flags) and not all(root_flags):
            raise ValueError(
                "mixed root/slave entity block is outside the serial p-only transfer audit"
            )
        if not all(root_flags):
            continue
        full_rows = np.asarray(block.full_rows, dtype=np.int64)
        roots = np.asarray(block.independent_rows, dtype=np.int64)
        expansion = np.asarray(block.full_from_independent, dtype=np.complex128)
        if (
            len(full_rows) != len(roots)
            or expansion.shape != (len(full_rows), len(roots))
            or np.linalg.matrix_rank(expansion) != len(roots)
        ):
            raise RuntimeError("physical root entity block is not invertible")
        root_values = np.linalg.solve(expansion, values[full_rows])
        for row, value in zip(roots, root_values, strict=True):
            index = int(row)
            if index < 0 or index >= independent_rows:
                raise RuntimeError("root entity block has an invalid independent row")
            if assigned[index]:
                error = abs(independent_values[index] - value)
                if error > tolerance * max(
                    1.0,
                    abs(independent_values[index]),
                    abs(value),
                ):
                    raise RuntimeError(
                        "physical root blocks disagree on an independent trace value"
                    )
            else:
                independent_values[index] = value
                assigned[index] = True
        root_block_count += 1
    if not np.all(assigned):
        raise RuntimeError(
            "physical root entity blocks do not cover all independent trace rows"
        )

    maximum_error = 0.0
    scale = max(
        1.0,
        float(
            np.max(
                np.abs(values[: entity_map.active_trace_rows]),
                initial=0.0,
            )
        ),
    )
    for block in blocks:
        full_rows = np.asarray(block.full_rows, dtype=np.int64)
        roots = np.asarray(block.independent_rows, dtype=np.int64)
        predicted = (
            np.asarray(block.full_from_independent, dtype=np.complex128)
            @ independent_values[roots]
        )
        maximum_error = max(
            maximum_error,
            float(np.max(np.abs(values[full_rows] - predicted), initial=0.0)),
        )
    relative_error = maximum_error / scale
    if relative_error > tolerance:
        raise RuntimeError(
            "candidate full trace violates hanging/Floquet constraints: "
            f"relative_error={relative_error:.6e}"
        )
    return {
        "schema_version": "task035d.variable-p-p6-trace-transfer-audit.v1",
        "status": "full_active_trace_constraint_pass",
        "pass": True,
        "mpi_size": 1,
        "independent_trace_rows": independent_rows,
        "physical_entity_block_count": len(blocks),
        "independent_root_block_count": root_block_count,
        "full_active_trace_rows": int(entity_map.active_trace_rows),
        "maximum_absolute_constraint_error": maximum_error,
        "maximum_relative_constraint_error": relative_error,
        "tolerance": tolerance,
    }


def recover_active_full_to_p6_field(
    transfer: VariablePGlobalTransfer,
    active_values: PETSc.Vec | np.ndarray,
    *,
    conformity_tolerance: float = 5.0e-10,
) -> tuple[Any, dict[str, Any]]:
    """Recover one conforming p6 storage field from active coefficients."""

    active = _global_active_values(transfer, active_values)
    field = fem.Function(transfer.p6_space)
    vector = field.x.petsc_vec
    vector.set(PETSc.ScalarType(0.0))
    for cell_transfer in transfer.cells:
        cell = cell_transfer.cell
        space = build_variable_p_reference_space(cell.degree_map)
        local_active = active[cell.active_rows]
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
            active[cell.active_rows],
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
        "global_embedding_matrix_allocated": False,
        "ordinary_default_changed": False,
    }


__all__ = [
    "VariablePCellTransfer",
    "VariablePGlobalTransfer",
    "audit_full_active_trace_constraints",
    "build_variable_p_global_transfer",
    "extract_active_full_from_p6_field",
    "project_p6_dual_to_active_full",
    "recover_active_full_to_p6_field",
]
