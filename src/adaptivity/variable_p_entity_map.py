"""Inactive-row-free global entity numbering for Task035d variable-p.

The numbering is canonical by topological dimension and global entity id.
Only the mode count requested on each physical edge, face, and cell receives
rows.  This makes serial/MPI fixture identities directly comparable and keeps
inactive p6 coefficients out of the global matrix contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy import sparse

from .exact_sequence_variable_p import HexaEntityDegreeMap


_QUALIFIED_DEGREES = (4, 5, 6)


def _mode_count(dimension: int, degree: int) -> int:
    degree = int(degree)
    if degree not in _QUALIFIED_DEGREES:
        raise ValueError("Task035d entity numbering supports p4/p5/p6 only")
    if dimension == 1:
        return degree
    if dimension == 2:
        return 2 * degree * (degree - 1)
    if dimension == 3:
        return 3 * degree * (degree - 1) ** 2
    raise ValueError(f"H(curl) has no numbered modes on dimension {dimension}")


@dataclass(frozen=True)
class VariablePCellDofMap:
    """Active rows and orientation identity for one locally owned cell."""

    local_cell: int
    global_cell: int
    degree_map: HexaEntityDegreeMap
    active_rows: np.ndarray
    trace_rows: np.ndarray
    interior_rows: np.ndarray
    cell_info: int
    entity_ids: Mapping[int, tuple[int, ...]]


@dataclass(frozen=True)
class VariablePGlobalEntityMap:
    """Canonical active numbering shared by every MPI partition."""

    mesh: Any
    global_degrees: Mapping[int, np.ndarray]
    global_entity_rows: Mapping[int, tuple[np.ndarray, ...]]
    local_entity_rows: Mapping[int, tuple[np.ndarray, ...]]
    owned_cells: tuple[VariablePCellDofMap, ...]
    active_rows: int
    active_trace_rows: int
    active_cell_interior_rows: int
    uniform_p6_rows: int
    uniform_p6_trace_rows: int
    audit: Mapping[str, Any]


def _validate_local_degrees(
    msh: Any,
    *,
    dimension: int,
    values: np.ndarray,
) -> np.ndarray:
    index_map = msh.topology.index_map(dimension)
    if index_map is None:
        raise RuntimeError(
            f"mesh topology has no index map for dimension {dimension}"
        )
    local_size = int(index_map.size_local + index_map.num_ghosts)
    degrees = np.asarray(values, dtype=np.int32)
    if degrees.shape != (local_size,):
        raise ValueError(
            f"dimension {dimension} degree array shape {degrees.shape} "
            f"does not match local+ghost entity count {(local_size,)}"
        )
    if not np.all(np.isin(degrees, _QUALIFIED_DEGREES)):
        raise ValueError(
            f"dimension {dimension} degrees contain values outside p4/p5/p6"
        )
    return np.ascontiguousarray(degrees)


def _global_degree_table(
    msh: Any,
    *,
    dimension: int,
    local_degrees: np.ndarray,
) -> np.ndarray:
    comm = msh.comm
    index_map = msh.topology.index_map(dimension)
    owned = int(index_map.size_local)
    owned_local = np.arange(owned, dtype=np.int32)
    owned_global = np.asarray(
        index_map.local_to_global(owned_local),
        dtype=np.int64,
    )
    packet = tuple(
        (int(global_id), int(degree))
        for global_id, degree in zip(
            owned_global,
            local_degrees[:owned],
            strict=True,
        )
    )
    gathered = comm.allgather(packet)
    table = np.full(int(index_map.size_global), -1, dtype=np.int32)
    for rank_packet in gathered:
        for global_id, degree in rank_packet:
            if not 0 <= global_id < len(table):
                raise RuntimeError("global mesh entity id is out of range")
            if table[global_id] != -1:
                raise RuntimeError(
                    "one global mesh entity has multiple owning degree records"
                )
            table[global_id] = degree
    if np.any(table < 0):
        raise RuntimeError("global entity degree table is incomplete")
    all_local = np.arange(len(local_degrees), dtype=np.int32)
    all_global = np.asarray(
        index_map.local_to_global(all_local),
        dtype=np.int64,
    )
    mismatch = local_degrees != table[all_global]
    if np.any(mismatch):
        raise RuntimeError(
            "shared/ghost entity degrees disagree with the owning rank"
        )
    table.setflags(write=False)
    return table


def _row_table(
    *,
    dimension: int,
    degrees: np.ndarray,
    base: int,
) -> tuple[tuple[np.ndarray, ...], int]:
    counts = np.asarray(
        [_mode_count(dimension, degree) for degree in degrees],
        dtype=np.int64,
    )
    offsets = np.empty(len(counts) + 1, dtype=np.int64)
    offsets[0] = int(base)
    np.cumsum(counts, out=offsets[1:])
    offsets[1:] += int(base)
    rows: list[np.ndarray] = []
    for entity in range(len(counts)):
        values = np.arange(
            offsets[entity],
            offsets[entity + 1],
            dtype=np.int64,
        )
        values.setflags(write=False)
        rows.append(values)
    return tuple(rows), int(offsets[-1])


def _canonical_identity(
    global_degrees: Mapping[int, np.ndarray],
) -> str:
    payload = {
        str(dimension): list(map(int, global_degrees[dimension]))
        for dimension in (1, 2, 3)
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def build_variable_p_global_entity_map(
    msh: Any,
    *,
    edge_degrees: np.ndarray,
    face_degrees: np.ndarray,
    cell_degrees: np.ndarray,
) -> VariablePGlobalEntityMap:
    """Build an exact-sequence-closed canonical active numbering."""

    if int(msh.topology.dim) != 3:
        raise ValueError("variable-p entity numbering requires a 3D mesh")
    if "hexahedron" not in str(msh.topology.cell_type).lower():
        raise ValueError("variable-p entity numbering requires hexahedra")
    topology = msh.topology
    for dimension in (1, 2):
        topology.create_entities(dimension)
    for dimension in (1, 2, 3):
        topology.create_connectivity(3, dimension)
    topology.create_entity_permutations()

    local_degrees = {
        1: _validate_local_degrees(
            msh,
            dimension=1,
            values=edge_degrees,
        ),
        2: _validate_local_degrees(
            msh,
            dimension=2,
            values=face_degrees,
        ),
        3: _validate_local_degrees(
            msh,
            dimension=3,
            values=cell_degrees,
        ),
    }
    global_degrees = {
        dimension: _global_degree_table(
            msh,
            dimension=dimension,
            local_degrees=local_degrees[dimension],
        )
        for dimension in (1, 2, 3)
    }

    global_rows: dict[int, tuple[np.ndarray, ...]] = {}
    next_row = 0
    trace_end = 0
    for dimension in (1, 2, 3):
        rows, next_row = _row_table(
            dimension=dimension,
            degrees=global_degrees[dimension],
            base=next_row,
        )
        global_rows[dimension] = rows
        if dimension == 2:
            trace_end = next_row

    local_entity_rows: dict[int, tuple[np.ndarray, ...]] = {}
    for dimension in (1, 2, 3):
        index_map = topology.index_map(dimension)
        local_count = int(index_map.size_local + index_map.num_ghosts)
        local_global = np.asarray(
            index_map.local_to_global(
                np.arange(local_count, dtype=np.int32)
            ),
            dtype=np.int64,
        )
        local_entity_rows[dimension] = tuple(
            global_rows[dimension][int(global_id)]
            for global_id in local_global
        )

    cell_map = topology.index_map(3)
    owned_cell_count = int(cell_map.size_local)
    cell_global_ids = np.asarray(
        cell_map.local_to_global(
            np.arange(owned_cell_count, dtype=np.int32)
        ),
        dtype=np.int64,
    )
    cell_info = np.asarray(
        topology.get_cell_permutation_info(),
        dtype=np.uint32,
    )
    owned_cells: list[VariablePCellDofMap] = []
    local_used_rows: list[np.ndarray] = []
    pattern_signatures: set[str] = set()
    for cell in range(owned_cell_count):
        entity_ids: dict[int, tuple[int, ...]] = {}
        degrees_by_dimension: dict[int, tuple[int, ...]] = {}
        rows_by_dimension: dict[int, list[np.ndarray]] = {}
        for dimension in (1, 2, 3):
            connectivity = topology.connectivity(3, dimension)
            entities = tuple(map(int, connectivity.links(cell)))
            expected = {1: 12, 2: 6, 3: 1}[dimension]
            if len(entities) != expected:
                raise RuntimeError(
                    "cell-to-entity connectivity does not match a hexahedron"
                )
            entity_ids[dimension] = entities
            degrees_by_dimension[dimension] = tuple(
                int(local_degrees[dimension][entity])
                for entity in entities
            )
            rows_by_dimension[dimension] = [
                local_entity_rows[dimension][entity]
                for entity in entities
            ]
        degree_map = HexaEntityDegreeMap(
            edges=degrees_by_dimension[1],
            faces=degrees_by_dimension[2],
            cell=degrees_by_dimension[3][0],
        )
        pattern_signatures.add(degree_map.signature)
        trace_rows = np.concatenate(
            (*rows_by_dimension[1], *rows_by_dimension[2])
        )
        interior_rows = np.asarray(rows_by_dimension[3][0])
        active_rows = np.concatenate((trace_rows, interior_rows))
        if len(np.unique(active_rows)) != len(active_rows):
            raise RuntimeError("one active cell map contains duplicate rows")
        local_used_rows.append(active_rows)
        for values in (trace_rows, interior_rows, active_rows):
            values.setflags(write=False)
        owned_cells.append(
            VariablePCellDofMap(
                local_cell=cell,
                global_cell=int(cell_global_ids[cell]),
                degree_map=degree_map,
                active_rows=active_rows,
                trace_rows=trace_rows,
                interior_rows=interior_rows,
                cell_info=int(cell_info[cell]),
                entity_ids=MappingProxyType(
                    {
                        dimension: entity_ids[dimension]
                        for dimension in (1, 2, 3)
                    }
                ),
            )
        )

    local_used = (
        np.unique(np.concatenate(local_used_rows))
        if local_used_rows
        else np.empty(0, dtype=np.int64)
    )
    packets = msh.comm.allgather(local_used)
    global_used = (
        np.unique(np.concatenate(packets))
        if packets
        else np.empty(0, dtype=np.int64)
    )
    if not np.array_equal(global_used, np.arange(next_row, dtype=np.int64)):
        raise RuntimeError(
            "active global numbering contains an isolated or missing row"
        )

    uniform_p6_rows = sum(
        len(global_degrees[dimension]) * _mode_count(dimension, 6)
        for dimension in (1, 2, 3)
    )
    uniform_p6_trace_rows = sum(
        len(global_degrees[dimension]) * _mode_count(dimension, 6)
        for dimension in (1, 2)
    )
    canonical_sha = _canonical_identity(global_degrees)
    sha_packets = msh.comm.allgather(canonical_sha)
    if len(set(sha_packets)) != 1:
        raise RuntimeError("MPI ranks disagree on the canonical degree map")
    active_cell_rows = int(next_row - trace_end)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.variable-p-global-entity-map.v1",
            "status": "inactive_row_free_entity_numbering_pass",
            "pass": True,
            "mpi_size": int(msh.comm.size),
            "global_entity_counts": {
                str(dimension): len(global_degrees[dimension])
                for dimension in (1, 2, 3)
            },
            "active_rows": int(next_row),
            "active_trace_rows": int(trace_end),
            "active_cell_interior_rows": active_cell_rows,
            "uniform_p6_rows": int(uniform_p6_rows),
            "uniform_p6_trace_rows": int(uniform_p6_trace_rows),
            "inactive_p6_rows": int(uniform_p6_rows - next_row),
            "inactive_p6_trace_rows": int(
                uniform_p6_trace_rows - trace_end
            ),
            "cell_pattern_count": len(pattern_signatures),
            "cell_pattern_signatures": sorted(pattern_signatures),
            "canonical_degree_map_sha256": canonical_sha,
            "canonical_numbering_partition_independent": True,
            "all_active_rows_reached_by_owned_cells": True,
            "inactive_modes_globally_numbered": False,
            "full_p6_global_matrix_constructed": False,
            "ordinary_default_changed": False,
        }
    )
    frozen_degrees = MappingProxyType(global_degrees)
    frozen_global_rows = MappingProxyType(global_rows)
    frozen_rows = MappingProxyType(local_entity_rows)
    return VariablePGlobalEntityMap(
        mesh=msh,
        global_degrees=frozen_degrees,
        global_entity_rows=frozen_global_rows,
        local_entity_rows=frozen_rows,
        owned_cells=tuple(owned_cells),
        active_rows=int(next_row),
        active_trace_rows=int(trace_end),
        active_cell_interior_rows=active_cell_rows,
        uniform_p6_rows=int(uniform_p6_rows),
        uniform_p6_trace_rows=int(uniform_p6_trace_rows),
        audit=audit,
    )


def structural_sparsity_audit(
    entity_map: VariablePGlobalEntityMap,
    *,
    condensed_trace: bool,
) -> dict[str, Any]:
    """Build the exact small-fixture cell-coupling CSR pattern."""

    row_count = (
        entity_map.active_trace_rows
        if condensed_trace
        else entity_map.active_rows
    )
    local_row_packets: list[np.ndarray] = []
    local_column_packets: list[np.ndarray] = []
    for cell in entity_map.owned_cells:
        rows = cell.trace_rows if condensed_trace else cell.active_rows
        local_row_packets.append(np.repeat(rows, len(rows)))
        local_column_packets.append(np.tile(rows, len(rows)))
    local_rows = (
        np.concatenate(local_row_packets)
        if local_row_packets
        else np.empty(0, dtype=np.int64)
    )
    local_columns = (
        np.concatenate(local_column_packets)
        if local_column_packets
        else np.empty(0, dtype=np.int64)
    )
    packets = entity_map.mesh.comm.allgather((local_rows, local_columns))
    rows = (
        np.concatenate([packet[0] for packet in packets])
        if packets
        else np.empty(0, dtype=np.int64)
    )
    columns = (
        np.concatenate([packet[1] for packet in packets])
        if packets
        else np.empty(0, dtype=np.int64)
    )
    matrix = sparse.coo_matrix(
        (
            np.ones(len(rows), dtype=np.int8),
            (rows, columns),
        ),
        shape=(row_count, row_count),
    ).tocsr()
    matrix.data[:] = 1
    widths = np.diff(matrix.indptr)
    isolated = int(np.count_nonzero(widths == 0))
    passed = matrix.shape == (row_count, row_count) and isolated == 0
    return {
        "schema_version": "task035d.variable-p-structural-sparsity.v1",
        "status": (
            "variable_p_structural_sparsity_pass"
            if passed
            else "variable_p_structural_sparsity_fail"
        ),
        "pass": passed,
        "condensed_trace": bool(condensed_trace),
        "rows": int(row_count),
        "structural_nnz": int(matrix.nnz),
        "average_row_width": float(matrix.nnz / max(row_count, 1)),
        "max_row_width": int(np.max(widths, initial=0)),
        "isolated_rows": isolated,
        "inactive_p6_rows_globally_numbered": False,
        "full_p6_global_matrix_constructed": False,
    }


__all__ = [
    "VariablePCellDofMap",
    "VariablePGlobalEntityMap",
    "build_variable_p_global_entity_map",
    "structural_sparsity_audit",
]
