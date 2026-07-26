"""Bind physical local-h trace constraints to DOLFINx entity ordering.

The physical constraint graph in :mod:`hcurl_broken_trace_graph` deliberately
does not depend on DOLFINx global entity numbers.  Compiled cell tensors,
however, are oriented into the DOLFINx-owned edge and face coefficient order
before insertion.  This module is the explicit bridge between those two
authorities:

* every DOLFINx edge/face is matched to one quantized physical entity;
* canonical physical coefficients are transformed into the DOLFINx entity
  ordering exactly once;
* hanging and Floquet slaves are substituted to partition-independent root
  rows; and
* each owned cell receives one dense local expansion suitable for
  ``C_K^H S_K C_K`` insertion.

No full p6 trace matrix and no hanging/Floquet slave row is introduced by this
binding.  The module remains opt-in and does not change the ordinary assembly
default.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from dolfinx import mesh as dmesh
from mpi4py import MPI
import numpy as np
from scipy import sparse

from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)

from .dyadic_hexa_broken_mesh import BrokenDyadicHexCarrier
from .dyadic_hexa_refinement import BalancedDyadicHexForest
from .hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
)
from .exact_sequence_variable_p import build_variable_p_reference_space
from .variable_p_entity_map import VariablePGlobalEntityMap


@dataclass(frozen=True)
class BrokenHexTraceEntityBlock:
    """One DOLFINx trace entity expressed by physical independent roots."""

    dimension: int
    global_entity: int
    physical_entity: PhysicalTraceEntity
    full_rows: np.ndarray
    independent_rows: np.ndarray
    full_from_independent: np.ndarray
    physical_from_independent: np.ndarray
    canonical_to_dolfinx: np.ndarray


@dataclass(frozen=True)
class BrokenHexCellTraceMap:
    """One owned cell's oriented trace expansion."""

    local_cell: int
    global_cell: int
    canonical_leaf: int
    independent_rows: np.ndarray
    full_trace_from_independent: np.ndarray


@dataclass(frozen=True)
class BrokenHexCellTraceConstraintMap:
    """Actual cell/PETSc binding for physical hanging and Floquet constraints."""

    entity_map: VariablePGlobalEntityMap
    authority: BrokenHexTraceConstraintAuthority
    entity_blocks: Mapping[tuple[int, int], BrokenHexTraceEntityBlock]
    owned_cells: tuple[BrokenHexCellTraceMap, ...]
    independent_trace_rows: int
    component_gram: np.ndarray | sparse.csr_matrix
    audit: Mapping[str, Any]


def _matrix_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).view(np.uint8)
    ).hexdigest()


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _quantize_point(
    point: np.ndarray,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[int, int, int]:
    return tuple(
        np.rint(
            (np.asarray(point, dtype=np.float64)[:3] - origin)
            / tolerance
        )
        .astype(np.int64)
        .tolist()
    )


def _geometry_key(
    dimension: int,
    points: tuple[tuple[int, int, int], ...],
) -> tuple[int, ...]:
    if int(dimension) == 1:
        if len(points) != 2:
            raise RuntimeError("edge geometry must contain two vertices")
        return tuple(value for point in sorted(points) for value in point)
    if int(dimension) != 2 or len(points) != 4:
        raise RuntimeError("face geometry must contain four vertices")
    values = np.asarray(points, dtype=np.int64)
    fixed = [
        axis
        for axis in range(3)
        if int(np.ptp(values[:, axis])) == 0
    ]
    if len(fixed) != 1:
        raise RuntimeError("physical trace face is not axis aligned")
    axis = fixed[0]
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    return (
        axis,
        int(values[0, axis]),
        int(np.min(values[:, tangential[0]])),
        int(np.max(values[:, tangential[0]])),
        int(np.min(values[:, tangential[1]])),
        int(np.max(values[:, tangential[1]])),
    )


def _canonical_to_dolfinx_transform(
    entity: PhysicalTraceEntity,
    ordered_points: tuple[tuple[int, int, int], ...],
    *,
    degree: int,
) -> tuple[np.ndarray, tuple[int, ...]]:
    try:
        permutation = tuple(
            entity.canonical_points.index(point) for point in ordered_points
        )
    except ValueError as exc:
        raise RuntimeError(
            "DOLFINx entity vertices differ from the physical trace entity"
        ) from exc
    if entity.dimension == 1:
        if permutation not in {(0, 1), (1, 0)}:
            raise RuntimeError("DOLFINx edge orientation is invalid")
        transform = edge_coefficient_transform(
            degree,
            reversed_orientation=permutation == (1, 0),
        )
    elif entity.dimension == 2:
        transform = face_coefficient_transform(degree, permutation)
    else:  # pragma: no cover - guarded by PhysicalTraceEntity
        raise RuntimeError("H(curl) trace entity must be an edge or face")
    return np.ascontiguousarray(transform), permutation


def _selected_graph_rows(
    authority: BrokenHexTraceConstraintAuthority,
    physical_rows: tuple[Any, ...],
) -> tuple[np.ndarray, np.ndarray]:
    row_index = {
        row: index for index, row in enumerate(authority.graph.raw_rows)
    }
    try:
        indices = np.asarray(
            [row_index[row] for row in physical_rows],
            dtype=np.int64,
        )
    except KeyError as exc:
        raise RuntimeError(
            "physical entity row is absent from the flattened trace graph"
        ) from exc
    graph = authority.graph.raw_from_independent
    if sparse.issparse(graph):
        selected = sparse.csr_matrix(graph)[indices].tocsr()
        independent = np.unique(selected.indices).astype(np.int64)
        values = np.asarray(
            selected[:, independent].toarray(),
            dtype=np.complex128,
        )
    else:
        selected = np.asarray(graph[indices], dtype=np.complex128)
        independent = np.flatnonzero(
            np.max(np.abs(selected), axis=0) > 0.0
        ).astype(np.int64)
        values = np.ascontiguousarray(selected[:, independent])
    if not len(independent):
        raise RuntimeError("one physical trace entity has no independent root")
    return independent, values


def _entity_records(
    entity_map: VariablePGlobalEntityMap,
    authority: BrokenHexTraceConstraintAuthority,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[
    dict[tuple[int, int], BrokenHexTraceEntityBlock],
    list[dict[str, Any]],
    float,
]:
    msh = entity_map.mesh
    topology = msh.topology
    by_physical = {
        (entity.dimension, entity.geometry_key): entity
        for entity in authority.entities
    }
    blocks: dict[tuple[int, int], BrokenHexTraceEntityBlock] = {}
    canonical_records: list[dict[str, Any]] = []
    maximum_orthogonality_error = 0.0
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, 3)
        index_map = topology.index_map(dimension)
        owned = int(index_map.size_local)
        local_entities = np.arange(owned, dtype=np.int32)
        global_entities = np.asarray(
            index_map.local_to_global(local_entities),
            dtype=np.int64,
        )
        geometry = dmesh.entities_to_geometry(
            msh,
            dimension,
            local_entities,
            permute=True,
        )
        packet: list[dict[str, Any]] = []
        for local_entity, global_entity, dofs in zip(
            local_entities,
            global_entities,
            geometry,
            strict=True,
        ):
            ordered_points = tuple(
                _quantize_point(
                    point,
                    origin=origin,
                    tolerance=tolerance,
                )
                for point in msh.geometry.x[np.asarray(dofs), :3]
            )
            geometry_key = _geometry_key(dimension, ordered_points)
            physical = by_physical.get((dimension, geometry_key))
            if physical is None:
                raise RuntimeError(
                    "DOLFINx trace entity has no physical graph identity"
                )
            transform, permutation = _canonical_to_dolfinx_transform(
                physical,
                ordered_points,
                degree=authority.degree,
            )
            independent, physical_expansion = _selected_graph_rows(
                authority,
                physical.rows,
            )
            expansion = np.ascontiguousarray(
                transform @ physical_expansion
            )
            full_rows = np.asarray(
                entity_map.global_entity_rows[dimension][int(global_entity)],
                dtype=np.int64,
            )
            if len(full_rows) != expansion.shape[0]:
                raise RuntimeError(
                    "DOLFINx entity rows and physical mode count disagree"
                )
            orthogonality_error = float(
                np.max(
                    np.abs(
                        transform.conj().T @ transform
                        - np.eye(transform.shape[0])
                    ),
                    initial=0.0,
                )
            )
            maximum_orthogonality_error = max(
                maximum_orthogonality_error,
                orthogonality_error,
            )
            packet.append(
                {
                    "dimension": int(dimension),
                    "global_entity": int(global_entity),
                    "geometry_key": physical.geometry_key,
                    "ordered_points": ordered_points,
                    "permutation": permutation,
                    "full_rows": full_rows,
                    "independent_rows": independent,
                    "expansion": expansion,
                    "physical_expansion": physical_expansion,
                    "transform": transform,
                }
            )
        for rank_packet in msh.comm.allgather(tuple(packet)):
            for record in rank_packet:
                identity = (
                    int(record["dimension"]),
                    int(record["global_entity"]),
                )
                if identity in blocks:
                    raise RuntimeError(
                        "one DOLFINx trace entity has multiple owners"
                    )
                physical = by_physical[
                    (
                        identity[0],
                        tuple(record["geometry_key"]),
                    )
                ]
                full_rows = np.ascontiguousarray(record["full_rows"])
                independent = np.ascontiguousarray(
                    record["independent_rows"]
                )
                expansion = np.ascontiguousarray(record["expansion"])
                physical_expansion = np.ascontiguousarray(
                    record["physical_expansion"]
                )
                transform = np.ascontiguousarray(record["transform"])
                for values in (
                    full_rows,
                    independent,
                    expansion,
                    physical_expansion,
                    transform,
                ):
                    values.setflags(write=False)
                blocks[identity] = BrokenHexTraceEntityBlock(
                    dimension=identity[0],
                    global_entity=identity[1],
                    physical_entity=physical,
                    full_rows=full_rows,
                    independent_rows=independent,
                    full_from_independent=expansion,
                    physical_from_independent=physical_expansion,
                    canonical_to_dolfinx=transform,
                )
                canonical_records.append(
                    {
                        "dimension": identity[0],
                        "geometry_key": list(physical.geometry_key),
                        "independent_rows": list(map(int, independent)),
                        "permutation": list(record["permutation"]),
                        "expansion_sha256": _matrix_sha256(expansion),
                    }
                )
    expected = sum(
        int(entity_map.mesh.topology.index_map(dimension).size_global)
        for dimension in (1, 2)
    )
    if len(blocks) != expected:
        raise RuntimeError("DOLFINx trace entity binding is incomplete")
    if len(canonical_records) != len(authority.entities):
        raise RuntimeError("physical and DOLFINx trace catalogs differ")
    return blocks, canonical_records, maximum_orthogonality_error


def _cell_expansion(
    entity_blocks: Mapping[tuple[int, int], BrokenHexTraceEntityBlock],
    entity_map: VariablePGlobalEntityMap,
    *,
    local_cell: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cell = entity_map.owned_cells[local_cell]
    selected: list[BrokenHexTraceEntityBlock] = []
    for dimension in (1, 2):
        index_map = entity_map.mesh.topology.index_map(dimension)
        local_entities = np.asarray(
            cell.entity_ids[dimension],
            dtype=np.int32,
        )
        global_entities = np.asarray(
            index_map.local_to_global(local_entities),
            dtype=np.int64,
        )
        selected.extend(
            entity_blocks[(dimension, int(global_entity))]
            for global_entity in global_entities
        )
    full_rows = np.concatenate([block.full_rows for block in selected])
    if not np.array_equal(full_rows, cell.trace_rows):
        raise RuntimeError(
            "cell trace entity sequence differs from active reference ordering"
        )
    independent = np.unique(
        np.concatenate([block.independent_rows for block in selected])
    ).astype(np.int64)
    local_column = {
        int(global_row): local_row
        for local_row, global_row in enumerate(independent)
    }
    expansion = np.zeros(
        (len(full_rows), len(independent)),
        dtype=np.complex128,
    )
    canonical_expansion = np.zeros_like(expansion)
    row_start = 0
    for block in selected:
        row_stop = row_start + len(block.full_rows)
        columns = np.asarray(
            [local_column[int(row)] for row in block.independent_rows],
            dtype=np.int64,
        )
        expansion[np.ix_(np.arange(row_start, row_stop), columns)] = (
            block.full_from_independent
        )
        canonical_expansion[
            np.ix_(np.arange(row_start, row_stop), columns)
        ] = block.physical_from_independent
        row_start = row_stop
    if np.any(
        np.max(np.abs(expansion), axis=1)
        <= np.finfo(np.float64).tiny
    ):
        raise RuntimeError("cell trace expansion contains an empty physical row")
    return (
        independent,
        np.ascontiguousarray(expansion),
        np.ascontiguousarray(canonical_expansion),
    )


def _canonical_cell_chart_error(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    *,
    local_cell: int,
) -> float:
    leaf = forest.leaves[
        int(carrier.canonical_leaf_by_local_cell[local_cell])
    ]
    box = leaf.box
    expected = np.asarray(
        [
            (
                box[3] if dx else box[0],
                box[4] if dy else box[1],
                box[5] if dz else box[2],
            )
            for dz in (0, 1)
            for dy in (0, 1)
            for dx in (0, 1)
        ],
        dtype=np.float64,
    )
    geometry_dofs = dmesh.entities_to_geometry(
        carrier.mesh,
        3,
        np.asarray([local_cell], dtype=np.int32),
        permute=False,
    )[0]
    observed = np.asarray(
        carrier.mesh.geometry.x[np.asarray(geometry_dofs), :3],
        dtype=np.float64,
    )
    return float(
        np.max(np.abs(observed - expected), initial=0.0)
    )


def build_broken_hexa_cell_trace_constraint_map(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    entity_map: VariablePGlobalEntityMap,
    authority: BrokenHexTraceConstraintAuthority,
) -> BrokenHexCellTraceConstraintMap:
    """Bind the flattened physical graph to actual owned cell trace rows."""

    if carrier.mesh is not entity_map.mesh:
        raise ValueError("carrier and entity map use different DOLFINx meshes")
    if authority.audit["pass"] is not True:
        raise ValueError("physical trace authority must pass before binding")
    if str(carrier.audit["leaf_catalog_sha256"]) != str(
        forest.audit["leaf_catalog_sha256"]
    ):
        raise ValueError("forest and carrier identities differ")
    if str(authority.audit["physical_authority_sha256"]) == "":
        raise ValueError("physical trace authority identity is missing")
    degree = int(authority.degree)
    for dimension in (1, 2):
        if np.any(entity_map.global_degrees[dimension] != degree):
            raise ValueError(
                "broken local-h binding currently requires one trace degree"
            )

    bounds = forest.domain_bounds
    origin = np.asarray(bounds[:3], dtype=np.float64)
    extent = np.asarray(
        [bounds[axis + 3] - bounds[axis] for axis in range(3)],
        dtype=np.float64,
    )
    tolerance = max(float(np.max(extent)), 1.0) * 1.0e-11
    blocks, canonical_records, orthogonality_error = _entity_records(
        entity_map,
        authority,
        origin=origin,
        tolerance=tolerance,
    )

    owned_cells: list[BrokenHexCellTraceMap] = []
    local_cell_records: list[dict[str, Any]] = []
    maximum_local_condition = 0.0
    maximum_cell_transform_error = 0.0
    maximum_canonical_chart_error = 0.0
    maximum_trace_interior_mixing_error = 0.0
    local_rank_failures = 0
    local_cell_expansion_bytes = 0
    for local_cell, cell in enumerate(entity_map.owned_cells):
        independent, expansion, canonical_expansion = _cell_expansion(
            blocks,
            entity_map,
            local_cell=local_cell,
        )
        space = build_variable_p_reference_space(cell.degree_map)
        reference_values = np.zeros(
            (space.hcurl_dimension, len(independent)),
            dtype=np.complex128,
        )
        reference_values[
            np.asarray(space.trace_dofs, dtype=np.int32)
        ] = canonical_expansion
        transformed = space.apply_hcurl_dof_transform(
            reference_values,
            cell_info=cell.cell_info,
        )
        expected_expansion = transformed[
            np.asarray(space.trace_dofs, dtype=np.int32)
        ]
        trace_interior_mixing_error = float(
            np.max(
                np.abs(
                    transformed[
                        np.asarray(space.interior_dofs, dtype=np.int32)
                    ]
                ),
                initial=0.0,
            )
        )
        maximum_trace_interior_mixing_error = max(
            maximum_trace_interior_mixing_error,
            trace_interior_mixing_error,
        )
        transform_error = float(
            np.max(
                np.abs(expected_expansion - expansion),
                initial=0.0,
            )
        )
        maximum_cell_transform_error = max(
            maximum_cell_transform_error,
            transform_error,
        )
        # DOLFINx cell_info is the orientation authority.  The independently
        # geometry-bound entity expansion above is retained as a mandatory
        # cross-check, while the cell map itself uses the direct T_K G_K path.
        expansion = np.ascontiguousarray(expected_expansion)
        chart_error = _canonical_cell_chart_error(
            forest,
            carrier,
            local_cell=cell.local_cell,
        )
        maximum_canonical_chart_error = max(
            maximum_canonical_chart_error,
            chart_error,
        )
        singular_values = np.linalg.svd(
            expansion,
            compute_uv=False,
        )
        positive = singular_values[
            singular_values
            > max(
                expansion.shape
            )
            * np.finfo(np.float64).eps
            * singular_values[0]
        ]
        if len(positive) != len(independent):
            local_rank_failures += 1
            condition = float("inf")
        else:
            condition = float(positive[0] / positive[-1])
        maximum_local_condition = max(maximum_local_condition, condition)
        local_cell_expansion_bytes += int(
            expansion.nbytes + independent.nbytes
        )
        expansion.setflags(write=False)
        independent.setflags(write=False)
        canonical_leaf = int(
            carrier.canonical_leaf_by_local_cell[cell.local_cell]
        )
        owned_cells.append(
            BrokenHexCellTraceMap(
                local_cell=cell.local_cell,
                global_cell=cell.global_cell,
                canonical_leaf=canonical_leaf,
                independent_rows=independent,
                full_trace_from_independent=expansion,
            )
        )
        local_cell_records.append(
            {
                "canonical_leaf": canonical_leaf,
                "independent_rows": list(map(int, independent)),
                "canonical_expansion_sha256": _matrix_sha256(
                    canonical_expansion
                ),
                "dolfinx_expansion_sha256": _matrix_sha256(expansion),
                "condition": condition,
                "cell_transform_error": transform_error,
                "trace_interior_mixing_error": (
                    trace_interior_mixing_error
                ),
                "canonical_chart_error": chart_error,
            }
        )

    gathered_cells = [
        row
        for packet in carrier.mesh.comm.allgather(tuple(local_cell_records))
        for row in packet
    ]
    if sorted(record["canonical_leaf"] for record in gathered_cells) != list(
        range(len(forest.leaves))
    ):
        raise RuntimeError("cell trace binding does not cover each forest leaf")
    independent_rows = len(authority.graph.root_rows)
    used_roots = np.unique(
        np.concatenate(
            [cell.independent_rows for cell in owned_cells]
            or [np.empty(0, dtype=np.int64)]
        )
    )
    all_used_roots = np.unique(
        np.concatenate(carrier.mesh.comm.allgather(used_roots))
    )
    if not np.array_equal(
        all_used_roots,
        np.arange(independent_rows, dtype=np.int64),
    ):
        raise RuntimeError("one independent physical trace root is unused")
    maximum_condition = float(
        carrier.mesh.comm.allreduce(maximum_local_condition, op=MPI.MAX)
    )
    rank_failures = int(
        carrier.mesh.comm.allreduce(local_rank_failures, op=MPI.SUM)
    )
    if rank_failures:
        raise RuntimeError(
            "one broken-hexa cell trace expansion is rank deficient"
        )
    maximum_orthogonality = float(
        carrier.mesh.comm.allreduce(orthogonality_error, op=MPI.MAX)
    )
    maximum_transform_error = float(
        carrier.mesh.comm.allreduce(
            maximum_cell_transform_error,
            op=MPI.MAX,
        )
    )
    maximum_chart_error = float(
        carrier.mesh.comm.allreduce(
            maximum_canonical_chart_error,
            op=MPI.MAX,
        )
    )
    maximum_mixing_error = float(
        carrier.mesh.comm.allreduce(
            maximum_trace_interior_mixing_error,
            op=MPI.MAX,
        )
    )
    canonical_cell_graph_payload = [
        {
            "canonical_leaf": int(record["canonical_leaf"]),
            "independent_rows": record["independent_rows"],
            "canonical_expansion_sha256": record[
                "canonical_expansion_sha256"
            ],
        }
        for record in sorted(
            gathered_cells,
            key=lambda value: int(value["canonical_leaf"]),
        )
    ]
    canonical_cell_graph_sha256 = _json_sha256(
        canonical_cell_graph_payload
    )
    graph_hashes = carrier.mesh.comm.allgather(
        canonical_cell_graph_sha256
    )
    entity_block_bytes = sum(
        int(
            block.full_rows.nbytes
            + block.independent_rows.nbytes
            + block.full_from_independent.nbytes
            + block.physical_from_independent.nbytes
            + block.canonical_to_dolfinx.nbytes
        )
        for block in blocks.values()
    )
    component_gram = authority.graph.component_gram
    if sparse.issparse(component_gram):
        component_gram_bytes = int(
            component_gram.data.nbytes
            + component_gram.indices.nbytes
            + component_gram.indptr.nbytes
        )
    else:
        component_gram_bytes = int(component_gram.nbytes)
    cell_expansion_bytes_by_rank = carrier.mesh.comm.allgather(
        local_cell_expansion_bytes
    )
    checks = {
        "forest_carrier_identity": True,
        "all_physical_entities_bound_once": (
            len(canonical_records) == len(authority.entities)
        ),
        "entity_transform_orthogonality": (
            maximum_orthogonality <= 5.0e-11
        ),
        "cell_transform_matches_dolfinx_cell_info": (
            maximum_transform_error <= 5.0e-11
        ),
        "unpermuted_cell_chart_matches_forest": (
            maximum_chart_error <= 5.0e-11
        ),
        "trace_transform_does_not_mix_cell_interior": (
            maximum_mixing_error <= 5.0e-11
        ),
        "canonical_cell_graph_mpi_identity": (
            len(set(graph_hashes)) == 1
        ),
        "all_owned_cells_bound": (
            len(owned_cells) == len(entity_map.owned_cells)
        ),
        "cell_expansions_full_column_rank": rank_failures == 0,
        "all_independent_roots_reached": (
            len(all_used_roots) == independent_rows
        ),
        "no_slave_rows_numbered": (
            independent_rows < int(authority.audit["raw_trace_rows"])
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(
            f"broken cell trace binding failed: {failures}"
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035d.broken-hexa-cell-trace-map.v1",
            "status": "broken_hexa_cell_trace_binding_pass",
            "pass": True,
            "mpi_size": int(carrier.mesh.comm.size),
            "degree": degree,
            "constraint_kinds": [
                kind
                for kind, present in (
                    ("hanging", bool(authority.hanging_relations)),
                    ("floquet", bool(authority.periodic_relations)),
                )
                if present
            ],
            "contains_hanging_constraints": bool(
                authority.hanging_relations
            ),
            "contains_floquet_constraints": bool(
                authority.periodic_relations
            ),
            "global_cell_count": len(gathered_cells),
            "raw_trace_rows": int(authority.audit["raw_trace_rows"]),
            "independent_trace_rows": independent_rows,
            "eliminated_hanging_or_floquet_rows": int(
                authority.audit["raw_trace_rows"] - independent_rows
            ),
            "hanging_slave_rows": sum(
                len(relation.slave_rows)
                for relation in authority.hanging_relations
                if relation.primary
            ),
            "periodic_slave_rows": sum(
                len(relation.slave_rows)
                for relation in authority.periodic_relations
                if relation.primary
            ),
            "maximum_entity_transform_orthogonality_error": (
                maximum_orthogonality
            ),
            "maximum_cell_expansion_condition": maximum_condition,
            "maximum_cell_transform_error": maximum_transform_error,
            "maximum_unpermuted_cell_chart_error": maximum_chart_error,
            "maximum_trace_interior_mixing_error": maximum_mixing_error,
            "physical_authority_sha256": str(
                authority.audit["physical_authority_sha256"]
            ),
            "flattened_graph_sha256": str(
                authority.audit["flattened_graph_sha256"]
            ),
            "canonical_cell_graph_sha256": canonical_cell_graph_sha256,
            "replicated_entity_block_bytes_per_rank": entity_block_bytes,
            "replicated_component_gram_bytes_per_rank": (
                component_gram_bytes
            ),
            "owned_cell_expansion_bytes_by_rank": (
                cell_expansion_bytes_by_rank
            ),
            "owned_cell_expansion_bytes_global_sum": int(
                sum(cell_expansion_bytes_by_rank)
            ),
            "checks": checks,
            "failures": failures,
            "canonical_root_numbering_partition_independent": True,
            "dolfinx_entity_order_bound_exactly_once": True,
            "compiled_cell_tensor_binding_complete": False,
            "petsc_constraint_row_ownership_qualified": False,
            "entity_catalog_distribution": "allgather_replicated",
            "dense_cell_expansion_retained": True,
            "cell_expansion_svd_used_for_rank_audit": True,
            "cell_expansion_inverse_used": False,
            "distributed_scalability_qualified": False,
            "full_p6_trace_matrix_constructed": False,
            "hanging_or_floquet_slave_rows_globally_numbered": False,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    return BrokenHexCellTraceConstraintMap(
        entity_map=entity_map,
        authority=authority,
        entity_blocks=MappingProxyType(blocks),
        owned_cells=tuple(owned_cells),
        independent_trace_rows=independent_rows,
        component_gram=authority.graph.component_gram,
        audit=audit,
    )


__all__ = [
    "BrokenHexCellTraceConstraintMap",
    "BrokenHexCellTraceMap",
    "BrokenHexTraceEntityBlock",
    "build_broken_hexa_cell_trace_constraint_map",
]
