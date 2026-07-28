"""Physical-key hanging and Floquet graph for a broken dyadic-hexa carrier.

The DOLFINx carrier intentionally does not join one coarse face to four fine
faces.  This module ignores partition-dependent DOLFINx entity IDs and rebuilds
the H(curl) trace universe from quantized physical edge/face geometry:

* fine-patch coefficients depend on the coarse trace through the qualified
  p4/p5/p6 restriction;
* x/y boundary entities form canonical Floquet stars; and
* hanging/Floquet chains are flattened before any global matrix numbering.

The result closes Task035d Attempt 1 at physical-graph level.  It still does
not bind the flattened expansion to compiled cell tensors, so it grants no PDE
accuracy credit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

import basix
from dolfinx import mesh
import numpy as np

from .dyadic_hexa_broken_mesh import BrokenDyadicHexCarrier
from .dyadic_hexa_refinement import BalancedDyadicHexForest, Box
from .hcurl_hanging_trace import build_hanging_face_reference_pair
from .hcurl_trace_constraint_graph import (
    FlattenedTraceConstraintMap,
    LinearTraceRelation,
    PhysicalTraceRowKey,
    compose_and_flatten_trace_constraints,
)


@dataclass(frozen=True, order=True)
class PhysicalTraceEntity:
    """One geometry-canonical edge or face-interior coefficient block."""

    dimension: int
    geometry_key: tuple[int, ...]
    degree: int
    canonical_points: tuple[tuple[int, int, int], ...]
    rows: tuple[PhysicalTraceRowKey, ...]

    def __post_init__(self) -> None:
        dimension = int(self.dimension)
        geometry_key = tuple(map(int, self.geometry_key))
        degree = int(self.degree)
        rows = tuple(self.rows)
        if dimension not in {1, 2} or degree not in {4, 5, 6}:
            raise ValueError("physical trace entity degree is invalid")
        if len(rows) != _mode_count(dimension, degree):
            raise ValueError(
                "physical trace entity row count differs from its degree"
            )
        if any(
            row.entity_dimension != dimension
            or row.entity_geometry_key != geometry_key
            or row.degree != degree
            for row in rows
        ):
            raise ValueError(
                "physical trace entity rows disagree with its identity"
            )
        object.__setattr__(self, "dimension", dimension)
        object.__setattr__(self, "geometry_key", geometry_key)
        object.__setattr__(self, "degree", degree)
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True)
class BrokenHexTraceConstraintAuthority:
    """Physical entities, actual relations, and their flattened graph."""

    degree: int
    entities: tuple[PhysicalTraceEntity, ...]
    hanging_relations: tuple[LinearTraceRelation, ...]
    periodic_relations: tuple[LinearTraceRelation, ...]
    graph: FlattenedTraceConstraintMap
    selected_p6_face_geometry_keys: tuple[tuple[int, ...], ...]
    audit: Mapping[str, Any]
    cell_degree_by_box: Mapping[Box, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    edge_degree_by_geometry_key: Mapping[tuple[int, ...], int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    face_degree_by_geometry_key: Mapping[tuple[int, ...], int] = field(
        default_factory=lambda: MappingProxyType({})
    )


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _mode_count(dimension: int, degree: int) -> int:
    if dimension == 1:
        return int(degree)
    if dimension == 2:
        return 2 * int(degree) * (int(degree) - 1)
    raise ValueError("H(curl) trace entity must be edge or face")


def _quantize_point(
    point: np.ndarray | tuple[float, ...],
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


def _entity_geometry_key(
    dimension: int,
    points: tuple[tuple[int, int, int], ...],
) -> tuple[int, ...]:
    dimension = int(dimension)
    if dimension == 1:
        if len(points) != 2:
            raise RuntimeError("edge geometry must contain two vertices")
        return tuple(value for point in sorted(points) for value in point)
    if dimension != 2 or len(points) != 4:
        raise RuntimeError("face geometry must contain four vertices")
    values = np.asarray(points, dtype=np.int64)
    fixed = [
        axis
        for axis in range(3)
        if int(np.ptp(values[:, axis])) == 0
    ]
    if len(fixed) != 1:
        raise RuntimeError("physical face is not axis aligned")
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


def _canonical_face_points(
    geometry_key: tuple[int, ...],
) -> tuple[tuple[int, int, int], ...]:
    axis, plane, u0, u1, v0, v1 = map(int, geometry_key)
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    result = []
    for u, v in ((u0, v0), (u1, v0), (u0, v1), (u1, v1)):
        point = [0, 0, 0]
        point[axis] = plane
        point[tangential[0]] = u
        point[tangential[1]] = v
        result.append(tuple(point))
    return tuple(result)


def _physical_face_key_from_box(
    box: Box,
    *,
    axis: int,
    side: int,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[int, ...]:
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    plane = box[axis + 3] if side else box[axis]
    points = []
    for u, v in (
        (box[tangential[0]], box[tangential[1]]),
        (box[tangential[0] + 3], box[tangential[1]]),
        (box[tangential[0]], box[tangential[1] + 3]),
        (box[tangential[0] + 3], box[tangential[1] + 3]),
    ):
        point = [0.0, 0.0, 0.0]
        point[axis] = plane
        point[tangential[0]] = u
        point[tangential[1]] = v
        points.append(
            _quantize_point(
                point,
                origin=origin,
                tolerance=tolerance,
            )
        )
    return _entity_geometry_key(2, tuple(points))


def _canonical_box(values: Any) -> Box:
    try:
        row = tuple(round(float(value), 12) for value in values)
    except TypeError as exc:
        raise ValueError(
            "cell degree keys must be six-coordinate leaf boxes"
        ) from exc
    if len(row) != 6 or any(
        row[axis] >= row[axis + 3] for axis in range(3)
    ):
        raise ValueError(
            "cell degree keys must be valid six-coordinate leaf boxes"
        )
    return row  # type: ignore[return-value]


def _face_edge_geometry_keys(
    face_geometry_key: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    points = _canonical_face_points(face_geometry_key)
    return tuple(
        _entity_geometry_key(
            1,
            tuple(points[int(vertex)] for vertex in vertices),
        )
        for vertices in basix.topology(basix.CellType.quadrilateral)[1]
    )


def _cell_physical_entity_keys(
    box: Box,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> Mapping[int, tuple[tuple[int, ...], ...]]:
    reference_geometry = np.asarray(
        basix.geometry(basix.CellType.hexahedron),
        dtype=np.float64,
    )
    lower = np.asarray(box[:3], dtype=np.float64)
    upper = np.asarray(box[3:], dtype=np.float64)
    points = tuple(
        _quantize_point(
            lower + (upper - lower) * reference_point,
            origin=origin,
            tolerance=tolerance,
        )
        for reference_point in reference_geometry
    )
    topology = basix.topology(basix.CellType.hexahedron)
    result: dict[int, tuple[tuple[int, ...], ...]] = {}
    for dimension in (1, 2):
        result[dimension] = tuple(
            _entity_geometry_key(
                dimension,
                tuple(points[int(vertex)] for vertex in vertices),
            )
            for vertices in topology[dimension]
        )
    return MappingProxyType(result)


def _normalize_cell_degree_by_box(
    forest: BalancedDyadicHexForest,
    values: Mapping[Box, int],
) -> Mapping[Box, int]:
    normalized: dict[Box, int] = {}
    for raw_box, raw_degree in values.items():
        box = _canonical_box(raw_box)
        if box in normalized:
            raise ValueError(
                "cell degree map contains duplicate normalized leaf boxes"
            )
        degree = int(raw_degree)
        if degree not in {4, 5, 6}:
            raise ValueError(
                "variable trace cell degrees must be p4, p5, or p6"
            )
        normalized[box] = degree
    expected = {cell.box for cell in forest.leaves}
    observed = set(normalized)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra:
        raise ValueError(
            "cell degree map must cover every forest leaf exactly; "
            f"missing={missing[:2]}, extra={extra[:2]}"
        )
    return MappingProxyType(
        {box: normalized[box] for box in sorted(normalized)}
    )


def _physical_entity_incidence(
    forest: BalancedDyadicHexForest,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[
    Mapping[tuple[int, tuple[int, ...]], tuple[Box, ...]],
    Mapping[Box, Mapping[int, tuple[tuple[int, ...], ...]]],
]:
    incident: dict[
        tuple[int, tuple[int, ...]],
        set[Box],
    ] = {}
    by_cell: dict[
        Box,
        Mapping[int, tuple[tuple[int, ...], ...]],
    ] = {}
    for cell in forest.leaves:
        entity_keys = _cell_physical_entity_keys(
            cell.box,
            origin=origin,
            tolerance=tolerance,
        )
        by_cell[cell.box] = entity_keys
        for dimension in (1, 2):
            for geometry_key in entity_keys[dimension]:
                incident.setdefault(
                    (dimension, geometry_key),
                    set(),
                ).add(cell.box)
    return (
        MappingProxyType(
            {
                identity: tuple(sorted(boxes))
                for identity, boxes in sorted(incident.items())
            }
        ),
        MappingProxyType(by_cell),
    )


def _periodic_entity_pairs(
    identities: set[tuple[int, tuple[int, ...]]],
    *,
    axes: tuple[str, ...],
    domain_steps: tuple[int, int, int],
) -> tuple[
    tuple[
        tuple[int, tuple[int, ...]],
        tuple[int, tuple[int, ...]],
    ],
    ...,
]:
    normalized_axes = tuple(dict.fromkeys(str(axis).lower() for axis in axes))
    if any(axis not in {"x", "y"} for axis in normalized_axes):
        raise ValueError("Task035e variable trace closure supports x/y only")
    axis_indices = {"x": 0, "y": 1}
    pairs: set[
        tuple[
            tuple[int, tuple[int, ...]],
            tuple[int, tuple[int, ...]],
        ]
    ] = set()
    for identity in sorted(identities):
        dimension, geometry_key = identity
        canonical_points = (
            tuple(
                tuple(geometry_key[3 * index : 3 * index + 3])
                for index in range(2)
            )
            if dimension == 1
            else _canonical_face_points(geometry_key)
        )
        for axis_name in normalized_axes:
            axis = axis_indices[axis_name]
            maximum = int(domain_steps[axis])
            if not all(
                point[axis] == maximum for point in canonical_points
            ):
                continue
            translated = []
            for point in canonical_points:
                values = list(point)
                values[axis] -= maximum
                translated.append(tuple(values))
            master = (
                dimension,
                _entity_geometry_key(
                    dimension,
                    tuple(translated),
                ),
            )
            if master not in identities:
                raise RuntimeError(
                    "periodic variable-trace entity has no translated master"
                )
            pairs.add(tuple(sorted((master, identity))))
    return tuple(sorted(pairs))


def _hanging_entity_groups(
    forest: BalancedDyadicHexForest,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[tuple[tuple[int, tuple[int, ...]], ...], ...]:
    cells = forest.leaf_by_key
    groups: list[tuple[tuple[int, tuple[int, ...]], ...]] = []
    for patch in forest.hanging_faces:
        coarse = cells[patch.coarse]
        coarse_key = _physical_face_key_from_box(
            coarse.box,
            axis=patch.axis,
            side=patch.side,
            origin=origin,
            tolerance=tolerance,
        )
        identities: set[tuple[int, tuple[int, ...]]] = {
            (2, coarse_key),
            *((1, key) for key in _face_edge_geometry_keys(coarse_key)),
        }
        for fine_cell_key in patch.fine:
            fine = cells[fine_cell_key]
            plane = coarse_key[1]
            lower_step = int(
                round(
                    (fine.box[patch.axis] - origin[patch.axis])
                    / tolerance
                )
            )
            upper_step = int(
                round(
                    (fine.box[patch.axis + 3] - origin[patch.axis])
                    / tolerance
                )
            )
            if lower_step == plane:
                fine_side = 0
            elif upper_step == plane:
                fine_side = 1
            else:
                raise RuntimeError(
                    "fine hanging cell misses its coarse physical plane"
                )
            fine_key = _physical_face_key_from_box(
                fine.box,
                axis=patch.axis,
                side=fine_side,
                origin=origin,
                tolerance=tolerance,
            )
            identities.add((2, fine_key))
            identities.update(
                (1, key)
                for key in _face_edge_geometry_keys(fine_key)
            )
        groups.append(tuple(sorted(identities)))
    return tuple(groups)


def _face_adjacent_cell_pairs(
    forest: BalancedDyadicHexForest,
    *,
    tolerance: float,
) -> tuple[tuple[Box, Box], ...]:
    leaves = tuple(forest.leaves)
    pairs: list[tuple[Box, Box]] = []
    for left_index, left in enumerate(leaves):
        for right in leaves[left_index + 1 :]:
            for axis in range(3):
                touches = (
                    abs(left.box[axis + 3] - right.box[axis]) <= tolerance
                    or abs(right.box[axis + 3] - left.box[axis]) <= tolerance
                )
                if not touches:
                    continue
                tangential = tuple(
                    candidate for candidate in range(3) if candidate != axis
                )
                if all(
                    min(
                        left.box[value + 3],
                        right.box[value + 3],
                    )
                    - max(left.box[value], right.box[value])
                    > tolerance
                    for value in tangential
                ):
                    pairs.append((left.box, right.box))
                    break
    return tuple(pairs)


def _variable_trace_degree_maps(
    forest: BalancedDyadicHexForest,
    *,
    cell_degree_by_box: Mapping[Box, int],
    origin: np.ndarray,
    tolerance: float,
    domain_steps: tuple[int, int, int],
    axes: tuple[str, ...],
) -> tuple[
    Mapping[Box, int],
    Mapping[tuple[int, ...], int],
    Mapping[tuple[int, ...], int],
    Mapping[str, Any],
]:
    cells = _normalize_cell_degree_by_box(
        forest,
        cell_degree_by_box,
    )
    incidence, by_cell = _physical_entity_incidence(
        forest,
        origin=origin,
        tolerance=tolerance,
    )
    identities = set(incidence)
    initial = {
        identity: min(cells[box] for box in incident_boxes)
        for identity, incident_boxes in incidence.items()
    }
    periodic_pairs = _periodic_entity_pairs(
        identities,
        axes=axes,
        domain_steps=domain_steps,
    )
    hanging_groups = _hanging_entity_groups(
        forest,
        origin=origin,
        tolerance=tolerance,
    )
    equality_pairs = set(periodic_pairs)
    for group in hanging_groups:
        missing = set(group) - identities
        if missing:
            raise RuntimeError(
                "hanging degree closure contains absent physical entities"
            )
        anchor = group[0]
        equality_pairs.update(
            tuple(sorted((anchor, member)))
            for member in group[1:]
        )
    degrees = dict(initial)
    lowering_iterations = 0
    while True:
        next_degrees = dict(degrees)
        for left, right in sorted(equality_pairs):
            shared = min(degrees[left], degrees[right])
            next_degrees[left] = min(next_degrees[left], shared)
            next_degrees[right] = min(next_degrees[right], shared)
        if next_degrees == degrees:
            break
        degrees = next_degrees
        lowering_iterations += 1
        if lowering_iterations > len(degrees):
            raise RuntimeError(
                "variable trace degree closure did not reach a fixed point"
            )

    adjacency = _face_adjacent_cell_pairs(
        forest,
        tolerance=tolerance,
    )
    adjacent_jumps = [
        abs(cells[left] - cells[right]) for left, right in adjacency
    ]
    periodic_cell_jumps: list[int] = []
    for left, right in periodic_pairs:
        if left[0] != 2:
            continue
        for left_box in incidence[left]:
            for right_box in incidence[right]:
                periodic_cell_jumps.append(
                    abs(cells[left_box] - cells[right_box])
                )
    maximum_cell_jump = max(
        (*adjacent_jumps, *periodic_cell_jumps),
        default=0,
    )
    if maximum_cell_jump > 1:
        raise ValueError(
            "adjacent or periodic cell p jump exceeds one: "
            f"maximum={maximum_cell_jump}"
        )

    exact_sequence_violations: list[str] = []
    for box, entity_keys in by_cell.items():
        cell_degree = cells[box]
        for face_key in entity_keys[2]:
            face_degree = degrees[(2, face_key)]
            edge_degrees = [
                degrees[(1, edge_key)]
                for edge_key in _face_edge_geometry_keys(face_key)
            ]
            if face_degree > cell_degree:
                exact_sequence_violations.append(
                    f"face p{face_degree} exceeds cell p{cell_degree}"
                )
            if max(edge_degrees) > face_degree:
                exact_sequence_violations.append(
                    "face degree is below one incident edge degree"
                )
    if exact_sequence_violations:
        raise RuntimeError(
            "variable trace degree map is not exact-sequence closed: "
            f"{exact_sequence_violations[:2]}"
        )

    hanging_patch_degrees: list[int] = []
    for group in hanging_groups:
        patch_degrees = {degrees[identity] for identity in group}
        if len(patch_degrees) != 1:
            raise RuntimeError(
                "hanging trace participants do not share one degree"
            )
        hanging_patch_degrees.append(next(iter(patch_degrees)))
    if any(degrees[left] != degrees[right] for left, right in periodic_pairs):
        raise RuntimeError("periodic trace degree closure did not converge")
    incident_bound = all(
        degrees[identity]
        <= min(cells[box] for box in incident_boxes)
        for identity, incident_boxes in incidence.items()
    )
    if not incident_bound:
        raise RuntimeError("trace degree exceeds an incident cell degree")

    edge_map = MappingProxyType(
        {
            geometry_key: degrees[(1, geometry_key)]
            for dimension, geometry_key in sorted(degrees)
            if dimension == 1
        }
    )
    face_map = MappingProxyType(
        {
            geometry_key: degrees[(2, geometry_key)]
            for dimension, geometry_key in sorted(degrees)
            if dimension == 2
        }
    )
    cell_rows = [
        {"box": list(box), "degree": int(value)}
        for box, value in cells.items()
    ]
    edge_rows = [
        {"geometry_key": list(key), "degree": int(value)}
        for key, value in edge_map.items()
    ]
    face_rows = [
        {"geometry_key": list(key), "degree": int(value)}
        for key, value in face_map.items()
    ]
    canonical_sha = _json_sha256(
        {
            "cells": cell_rows,
            "edges": edge_rows,
            "faces": face_rows,
        }
    )
    audit = MappingProxyType(
        {
            "cell_degree_values": sorted(set(cells.values())),
            "cell_degree_counts": {
                f"p{candidate}": sum(
                    value == candidate for value in cells.values()
                )
                for candidate in (4, 5, 6)
            },
            "edge_degree_counts": {
                f"p{candidate}": sum(
                    value == candidate for value in edge_map.values()
                )
                for candidate in (4, 5, 6)
            },
            "face_degree_counts": {
                f"p{candidate}": sum(
                    value == candidate for value in face_map.values()
                )
                for candidate in (4, 5, 6)
            },
            "fixed_point_lowering_iterations": lowering_iterations,
            "periodic_degree_pair_count": len(periodic_pairs),
            "hanging_degree_group_count": len(hanging_groups),
            "hanging_patch_degrees": hanging_patch_degrees,
            "maximum_adjacent_or_periodic_cell_p_jump": maximum_cell_jump,
            "geometry_canonical_cell_degrees": cell_rows,
            "geometry_canonical_edge_degrees": edge_rows,
            "geometry_canonical_face_degrees": face_rows,
            "geometry_canonical_entity_degree_sha256": canonical_sha,
            "entity_degree_bounded_by_incident_cells": incident_bound,
            "periodic_entity_degree_closure": all(
                degrees[left] == degrees[right]
                for left, right in periodic_pairs
            ),
            "hanging_entity_degree_closure": all(
                len({degrees[identity] for identity in group}) == 1
                for group in hanging_groups
            ),
            "exact_sequence_monotone": not exact_sequence_violations,
            "inactive_high_order_trace_rows_globally_numbered": False,
        }
    )
    return cells, edge_map, face_map, audit


def _entity_catalog(
    carrier: BrokenDyadicHexCarrier,
    *,
    degree: int,
    selected_p6_face_geometry_keys: set[tuple[int, ...]],
    degree_by_identity: Mapping[
        tuple[int, tuple[int, ...]],
        int,
    ]
    | None,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[PhysicalTraceEntity, ...]:
    msh = carrier.mesh
    topology = msh.topology
    local_packets: list[tuple[int, tuple[int, ...], tuple[Any, ...]]] = []
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, 3)
        index_map = topology.index_map(dimension)
        owned = int(index_map.size_local)
        entities = np.arange(owned, dtype=np.int32)
        geometry = mesh.entities_to_geometry(
            msh,
            dimension,
            entities,
            permute=True,
        )
        for dofs in geometry:
            ordered_points = tuple(
                _quantize_point(
                    point,
                    origin=origin,
                    tolerance=tolerance,
                )
                for point in msh.geometry.x[np.asarray(dofs), :3]
            )
            key = _entity_geometry_key(dimension, ordered_points)
            canonical_points = (
                tuple(sorted(ordered_points))
                if dimension == 1
                else _canonical_face_points(key)
            )
            local_packets.append(
                (dimension, key, canonical_points)
            )
    gathered = [
        row
        for packet in msh.comm.allgather(tuple(local_packets))
        for row in packet
    ]
    by_key: dict[tuple[int, tuple[int, ...]], PhysicalTraceEntity] = {}
    for dimension, geometry_key, canonical_points in gathered:
        identity = (int(dimension), tuple(map(int, geometry_key)))
        if identity in by_key:
            raise RuntimeError(
                "physical trace entity geometry has duplicate owners"
            )
        if degree_by_identity is None:
            entity_degree = (
                6
                if (
                    int(dimension) == 2
                    and identity[1] in selected_p6_face_geometry_keys
                )
                else degree
            )
        else:
            try:
                entity_degree = int(degree_by_identity[identity])
            except KeyError as exc:
                raise RuntimeError(
                    "carrier trace entity is absent from the variable "
                    "geometry degree authority"
                ) from exc
        rows = tuple(
            PhysicalTraceRowKey(
                entity_dimension=int(dimension),
                entity_geometry_key=identity[1],
                degree=entity_degree,
                mode=mode,
            )
            for mode in range(
                _mode_count(int(dimension), entity_degree)
            )
        )
        by_key[identity] = PhysicalTraceEntity(
            dimension=int(dimension),
            geometry_key=identity[1],
            degree=entity_degree,
            canonical_points=tuple(canonical_points),
            rows=rows,
        )
    if degree_by_identity is not None:
        unknown = set(degree_by_identity) - set(by_key)
        if unknown:
            raise RuntimeError(
                "variable geometry degree authority contains entities absent "
                f"from the carrier: {sorted(unknown)[:2]}"
            )
    return tuple(sorted(by_key.values()))


def _hanging_face_geometry_keys(
    forest: BalancedDyadicHexForest,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> set[tuple[int, ...]]:
    cells = forest.leaf_by_key
    result: set[tuple[int, ...]] = set()
    for patch in forest.hanging_faces:
        coarse = cells[patch.coarse]
        coarse_key = _physical_face_key_from_box(
            coarse.box,
            axis=patch.axis,
            side=patch.side,
            origin=origin,
            tolerance=tolerance,
        )
        result.add(coarse_key)
        for fine_cell_key in patch.fine:
            fine = cells[fine_cell_key]
            plane = coarse_key[1]
            lower_step = int(
                round(
                    (fine.box[patch.axis] - origin[patch.axis])
                    / tolerance
                )
            )
            upper_step = int(
                round(
                    (fine.box[patch.axis + 3] - origin[patch.axis])
                    / tolerance
                )
            )
            if lower_step == plane:
                fine_side = 0
            elif upper_step == plane:
                fine_side = 1
            else:
                raise RuntimeError(
                    "fine hanging cell misses its coarse physical plane"
                )
            result.add(
                _physical_face_key_from_box(
                    fine.box,
                    axis=patch.axis,
                    side=fine_side,
                    origin=origin,
                    tolerance=tolerance,
                )
            )
    return result


def _periodic_face_orbits(
    entities: tuple[PhysicalTraceEntity, ...],
    *,
    axes: tuple[str, ...],
    domain_steps: tuple[int, int, int],
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    normalized_axes = tuple(dict.fromkeys(str(axis).lower() for axis in axes))
    if any(axis not in {"x", "y"} for axis in normalized_axes):
        raise ValueError("Task035d periodic trace graph supports x/y only")
    axis_indices = {"x": 0, "y": 1}
    faces = {
        entity.geometry_key: entity
        for entity in entities
        if entity.dimension == 2
    }
    parent = {key: key for key in faces}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for geometry_key, entity in faces.items():
        for axis_name in normalized_axes:
            axis = axis_indices[axis_name]
            maximum = int(domain_steps[axis])
            if not all(
                point[axis] == maximum
                for point in entity.canonical_points
            ):
                continue
            translated = []
            for point in entity.canonical_points:
                values = list(point)
                values[axis] -= maximum
                translated.append(tuple(values))
            master_key = _entity_geometry_key(
                2,
                tuple(translated),
            )
            if master_key not in faces:
                raise RuntimeError(
                    "periodic physical face has no translated master"
                )
            union(master_key, geometry_key)
    groups: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    for key in faces:
        groups.setdefault(find(key), []).append(key)
    return tuple(
        tuple(sorted(group))
        for group in sorted(groups.values(), key=lambda row: min(row))
    )


def build_broken_hexa_entity_degree_arrays(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    authority: BrokenHexTraceConstraintAuthority,
) -> tuple[np.ndarray, np.ndarray]:
    """Bind physical entity degrees to local and ghost DOLFINx entities."""

    if authority.audit["pass"] is not True:
        raise ValueError("physical trace authority must pass")
    if str(carrier.audit["leaf_catalog_sha256"]) != str(
        forest.audit["leaf_catalog_sha256"]
    ):
        raise ValueError("forest and carrier leaf identities differ")
    bounds = forest.domain_bounds
    origin = np.asarray(bounds[:3], dtype=np.float64)
    extent = np.asarray(
        [bounds[axis + 3] - bounds[axis] for axis in range(3)],
        dtype=np.float64,
    )
    tolerance = max(float(np.max(extent)), 1.0) * 1.0e-11
    by_identity = {
        (entity.dimension, entity.geometry_key): entity
        for entity in authority.entities
    }
    arrays: dict[int, np.ndarray] = {}
    for dimension in (1, 2):
        topology = carrier.mesh.topology
        topology.create_entities(dimension)
        index_map = topology.index_map(dimension)
        local_count = int(index_map.size_local + index_map.num_ghosts)
        entities = np.arange(local_count, dtype=np.int32)
        geometry = mesh.entities_to_geometry(
            carrier.mesh,
            dimension,
            entities,
            permute=True,
        )
        values = np.empty(local_count, dtype=np.int32)
        for local_entity, dofs in enumerate(geometry):
            points = tuple(
                _quantize_point(
                    point,
                    origin=origin,
                    tolerance=tolerance,
                )
                for point in carrier.mesh.geometry.x[
                    np.asarray(dofs),
                    :3,
                ]
            )
            key = _entity_geometry_key(dimension, points)
            physical = by_identity.get((dimension, key))
            if physical is None:
                raise RuntimeError(
                    "DOLFINx entity has no physical degree authority"
                )
            values[local_entity] = int(physical.degree)
        arrays[dimension] = values
    return arrays[1], arrays[2]


def physical_face_closure_rows(
    face: PhysicalTraceEntity,
    entities: Mapping[tuple[int, tuple[int, ...]], PhysicalTraceEntity],
) -> tuple[PhysicalTraceRowKey, ...]:
    """Return canonical edge-plus-face rows for one physical face closure."""

    if face.dimension != 2:
        raise ValueError("physical face closure requires a face entity")
    topology = basix.topology(basix.CellType.quadrilateral)
    points = face.canonical_points
    rows: list[PhysicalTraceRowKey] = []
    for vertices in topology[1]:
        edge_points = tuple(points[int(vertex)] for vertex in vertices)
        edge_key = _entity_geometry_key(1, edge_points)
        edge = entities.get((1, edge_key))
        if edge is None:
            raise RuntimeError("face boundary edge is absent from carrier")
        rows.extend(edge.rows)
    rows.extend(face.rows)
    return tuple(rows)


def _build_hanging_relations(
    forest: BalancedDyadicHexForest,
    entities: Mapping[tuple[int, tuple[int, ...]], PhysicalTraceEntity],
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[LinearTraceRelation, ...]:
    cells = forest.leaf_by_key
    relations: list[LinearTraceRelation] = []
    produced_rows: set[PhysicalTraceRowKey] = set()
    for patch_index, patch in enumerate(forest.hanging_faces):
        coarse = cells[patch.coarse]
        coarse_key = _physical_face_key_from_box(
            coarse.box,
            axis=patch.axis,
            side=patch.side,
            origin=origin,
            tolerance=tolerance,
        )
        coarse_face = entities.get((2, coarse_key))
        if coarse_face is None:
            raise RuntimeError("hanging coarse face is absent from carrier")
        coarse_rows = physical_face_closure_rows(coarse_face, entities)
        patch_degree = int(coarse_face.degree)
        if any(row.degree != patch_degree for row in coarse_rows):
            raise RuntimeError(
                "hanging coarse-face closure mixes trace degrees"
            )
        pair = build_hanging_face_reference_pair(patch_degree)
        fine_unique: list[PhysicalTraceRowKey | None] = [
            None
        ] * pair.hcurl_unique_fine_from_coarse.shape[0]
        for child, (fine_cell_key, _offset) in enumerate(
            zip(patch.fine, patch.child_offsets, strict=True)
        ):
            fine = cells[fine_cell_key]
            plane = coarse_key[1]
            lower_step = int(
                round((fine.box[patch.axis] - origin[patch.axis]) / tolerance)
            )
            upper_step = int(
                round(
                    (fine.box[patch.axis + 3] - origin[patch.axis])
                    / tolerance
                )
            )
            if lower_step == plane:
                fine_side = 0
            elif upper_step == plane:
                fine_side = 1
            else:
                raise RuntimeError("fine hanging cell misses coarse plane")
            fine_key = _physical_face_key_from_box(
                fine.box,
                axis=patch.axis,
                side=fine_side,
                origin=origin,
                tolerance=tolerance,
            )
            fine_face = entities.get((2, fine_key))
            if fine_face is None:
                raise RuntimeError("hanging fine face is absent from carrier")
            local_rows = physical_face_closure_rows(fine_face, entities)
            if any(row.degree != patch_degree for row in local_rows):
                raise RuntimeError(
                    "hanging fine-face closure differs from coarse degree"
                )
            aggregate_rows = pair.hcurl_child_rows[child]
            if len(local_rows) != len(aggregate_rows):
                raise RuntimeError(
                    "hanging trace restriction row count differs from the "
                    "physical fine-face closure"
                )
            for local_row, aggregate_row in enumerate(aggregate_rows):
                physical_row = local_rows[local_row]
                previous = fine_unique[int(aggregate_row)]
                if previous is not None and previous != physical_row:
                    raise RuntimeError(
                        "shared fine edge has inconsistent physical identity"
                    )
                fine_unique[int(aggregate_row)] = physical_row
        if any(row is None for row in fine_unique):
            raise RuntimeError("hanging fine-patch trace catalog is incomplete")
        fine_rows = tuple(row for row in fine_unique if row is not None)
        if len(set(fine_rows)) != len(fine_rows):
            raise RuntimeError("hanging fine-patch rows are not unique")
        provenance = {
            "patch_index": patch_index,
            "axis": patch.axis,
            "side": patch.side,
            "coarse": patch.coarse.to_dict(),
            "fine": [key.to_dict() for key in patch.fine],
        }
        primary_indices = [
            index
            for index, row in enumerate(fine_rows)
            if row not in produced_rows
        ]
        secondary_indices = [
            index
            for index, row in enumerate(fine_rows)
            if row in produced_rows
        ]
        if primary_indices:
            relations.append(
                LinearTraceRelation(
                    kind="hanging",
                    slave_rows=tuple(
                        fine_rows[index] for index in primary_indices
                    ),
                    master_rows=coarse_rows,
                    slave_from_master=pair.hcurl_unique_fine_from_coarse[
                        primary_indices
                    ],
                    primary=True,
                    provenance={
                        **provenance,
                        "equation_class": "primary",
                    },
                )
            )
            produced_rows.update(
                fine_rows[index] for index in primary_indices
            )
        if secondary_indices:
            relations.append(
                LinearTraceRelation(
                    kind="hanging_compatibility",
                    slave_rows=tuple(
                        fine_rows[index] for index in secondary_indices
                    ),
                    master_rows=coarse_rows,
                    slave_from_master=pair.hcurl_unique_fine_from_coarse[
                        secondary_indices
                    ],
                    primary=False,
                    provenance={
                        **provenance,
                        "equation_class": "secondary_shared_edge",
                    },
                )
            )
    return tuple(relations)


def _build_periodic_relations(
    entities: tuple[PhysicalTraceEntity, ...],
    *,
    axes: tuple[str, ...],
    phase_x: complex,
    phase_y: complex,
    domain_steps: tuple[int, int, int],
    hanging_slave_rows: set[PhysicalTraceRowKey],
) -> tuple[tuple[LinearTraceRelation, ...], float]:
    normalized_axes = tuple(dict.fromkeys(str(axis).lower() for axis in axes))
    if any(axis not in {"x", "y"} for axis in normalized_axes):
        raise ValueError("Task035d periodic trace graph supports x/y only")
    axis_data = {
        "x": (0, complex(phase_x)),
        "y": (1, complex(phase_y)),
    }
    nodes = {
        (entity.dimension, entity.geometry_key): entity
        for entity in entities
    }
    parent = {node: node for node in nodes}
    adjacency: dict[
        tuple[int, tuple[int, ...]],
        list[tuple[tuple[int, tuple[int, ...]], complex, str]],
    ] = {node: [] for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for entity in entities:
        node = (entity.dimension, entity.geometry_key)
        for axis_name in normalized_axes:
            axis, phase = axis_data[axis_name]
            maximum = int(domain_steps[axis])
            if not all(
                point[axis] == maximum
                for point in entity.canonical_points
            ):
                continue
            translated = []
            for point in entity.canonical_points:
                values = list(point)
                values[axis] -= maximum
                translated.append(tuple(values))
            master_key = _entity_geometry_key(
                entity.dimension,
                tuple(translated),
            )
            master_node = (entity.dimension, master_key)
            if master_node not in nodes:
                raise RuntimeError(
                    "periodic physical entity has no translated master"
                )
            union(master_node, node)
            adjacency[master_node].append((node, phase, axis_name))
            adjacency[node].append((master_node, 1.0 / phase, axis_name))

    components: dict[Any, list[Any]] = {}
    for node in nodes:
        components.setdefault(find(node), []).append(node)
    output: list[LinearTraceRelation] = []
    maximum_cycle_error = 0.0
    for members in components.values():
        if len(members) == 1:
            continue
        component = tuple(sorted(members))
        root = component[0]
        potentials = {root: 1.0 + 0.0j}
        path_axes: dict[Any, set[str]] = {root: set()}
        queue = [root]
        while queue:
            current = queue.pop(0)
            for neighbor, coefficient, axis_name in adjacency[current]:
                candidate = coefficient * potentials[current]
                if neighbor in potentials:
                    maximum_cycle_error = max(
                        maximum_cycle_error,
                        abs(candidate - potentials[neighbor]),
                    )
                else:
                    potentials[neighbor] = candidate
                    path_axes[neighbor] = path_axes[current] | {axis_name}
                    queue.append(neighbor)
        if set(potentials) != set(component):
            raise RuntimeError("periodic physical orbit traversal is incomplete")
        root_entity = nodes[root]
        for node in component[1:]:
            entity = nodes[node]
            if len(entity.rows) != len(root_entity.rows):
                raise RuntimeError("periodic orbit mixes trace mode counts")
            slave_hanging = [
                row in hanging_slave_rows for row in entity.rows
            ]
            if any(slave_hanging) and not all(slave_hanging):
                raise RuntimeError(
                    "periodic entity is only partially constrained by hanging"
                )
            output.append(
                LinearTraceRelation(
                    kind="floquet_star",
                    slave_rows=entity.rows,
                    master_rows=root_entity.rows,
                    slave_from_master=potentials[node]
                    * np.eye(len(entity.rows), dtype=np.complex128),
                    primary=not all(slave_hanging),
                    provenance={
                        "axes": sorted(path_axes[node]),
                        "orbit_size": len(component),
                        "root_geometry_key": list(root_entity.geometry_key),
                        "member_geometry_key": list(entity.geometry_key),
                    },
                )
            )
    if maximum_cycle_error > 5.0e-11:
        raise RuntimeError(
            "physical Floquet orbit phase cycle does not close: "
            f"{maximum_cycle_error:.6e}"
        )
    return tuple(output), float(maximum_cycle_error)


def build_broken_hexa_trace_constraint_authority(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    *,
    degree: int = 4,
    periodic_axes: tuple[str, ...] | None = None,
    phase_x: complex = 1.0 + 0.0j,
    phase_y: complex = 1.0 + 0.0j,
    selected_p6_face_geometry_keys: tuple[tuple[int, ...], ...] = (),
    cell_degree_by_box: Mapping[Box, int] | None = None,
) -> BrokenHexTraceConstraintAuthority:
    """Build actual physical hanging/Floquet relations and flatten them.

    ``cell_degree_by_box`` is an explicit Task035e opt-in.  It must name
    every current forest leaf and uses ``degree`` as its maximum container
    order.  Edge and face orders start at the minimum incident-cell order,
    then are lowered to a fixed point across Floquet orbits and complete
    coarse/fine hanging-face closures.  The legacy uniform and selective-p6
    paths do not enter this branch.
    """

    authority_started = perf_counter()
    validation_started = perf_counter()
    degree = int(degree)
    if degree not in {4, 5, 6}:
        raise ValueError("Task035d broken trace graph qualifies p4/p5/p6")
    if carrier.audit["pass"] is not True or forest.audit["pass"] is not True:
        raise ValueError("forest and carrier must pass before trace graph")
    if str(carrier.audit["leaf_catalog_sha256"]) != str(
        forest.audit["leaf_catalog_sha256"]
    ):
        raise ValueError("carrier and forest leaf identities differ")
    selected_rows = tuple(
        tuple(map(int, geometry_key))
        for geometry_key in selected_p6_face_geometry_keys
    )
    if len(set(selected_rows)) != len(selected_rows):
        raise ValueError("selected p6 physical face keys are duplicated")
    selected = set(selected_rows)
    variable_trace = cell_degree_by_box is not None
    if variable_trace and selected:
        raise ValueError(
            "cell-driven variable trace and legacy selected-p6 faces are "
            "mutually exclusive"
        )
    if selected and degree != 5:
        raise ValueError(
            "selective whole-face p6 recovery requires a p5 trace base"
        )
    bounds = forest.domain_bounds
    origin = np.asarray(bounds[:3], dtype=np.float64)
    extent = np.asarray(
        [bounds[axis + 3] - bounds[axis] for axis in range(3)],
        dtype=np.float64,
    )
    tolerance = max(float(np.max(extent)), 1.0) * 1.0e-11
    domain_steps = tuple(
        np.rint(extent / tolerance).astype(np.int64).tolist()
    )
    axes = (
        tuple(forest.periodic_axes)
        if periodic_axes is None
        else tuple(periodic_axes)
    )
    validation_seconds = perf_counter() - validation_started
    variable_cell_map: Mapping[Box, int] = MappingProxyType({})
    variable_edge_map: Mapping[tuple[int, ...], int] = MappingProxyType({})
    variable_face_map: Mapping[tuple[int, ...], int] = MappingProxyType({})
    variable_audit: Mapping[str, Any] = MappingProxyType({})
    degree_by_identity = None
    variable_degree_started = perf_counter()
    if cell_degree_by_box is not None:
        (
            variable_cell_map,
            variable_edge_map,
            variable_face_map,
            variable_audit,
        ) = _variable_trace_degree_maps(
            forest,
            cell_degree_by_box=cell_degree_by_box,
            origin=origin,
            tolerance=tolerance,
            domain_steps=domain_steps,
            axes=axes,
        )
        maximum_cell_degree = max(variable_cell_map.values())
        if degree < maximum_cell_degree:
            raise ValueError(
                "variable trace container degree is below the maximum "
                f"cell degree p{maximum_cell_degree}"
            )
        degree_by_identity = MappingProxyType(
            {
                **{
                    (1, key): value
                    for key, value in variable_edge_map.items()
                },
                **{
                    (2, key): value
                    for key, value in variable_face_map.items()
                },
            }
        )
    variable_degree_seconds = perf_counter() - variable_degree_started
    entity_catalog_started = perf_counter()
    entities = _entity_catalog(
        carrier,
        degree=degree,
        selected_p6_face_geometry_keys=selected,
        degree_by_identity=degree_by_identity,
        origin=origin,
        tolerance=tolerance,
    )
    entity_catalog_seconds = perf_counter() - entity_catalog_started
    selection_audit_started = perf_counter()
    physical_face_keys = {
        entity.geometry_key
        for entity in entities
        if entity.dimension == 2
    }
    unknown_selected = selected - physical_face_keys
    if unknown_selected:
        raise ValueError(
            "selected p6 face keys are absent from the carrier: "
            f"{sorted(unknown_selected)[:2]}"
        )
    hanging_face_keys = _hanging_face_geometry_keys(
        forest,
        origin=origin,
        tolerance=tolerance,
    )
    selected_hanging = selected & hanging_face_keys
    if selected_hanging:
        raise ValueError(
            "selective p6 face recovery does not support a hanging "
            f"participant: {sorted(selected_hanging)[:2]}"
        )
    periodic_face_orbits = _periodic_face_orbits(
        entities,
        axes=axes,
        domain_steps=domain_steps,
    )
    partial_orbits = [
        orbit
        for orbit in periodic_face_orbits
        if 0 < len(selected.intersection(orbit)) < len(orbit)
    ]
    if partial_orbits:
        raise ValueError(
            "selected p6 faces do not contain a complete periodic orbit: "
            f"{partial_orbits[:1]}"
        )
    selected_periodic_orbits = tuple(
        orbit
        for orbit in periodic_face_orbits
        if len(orbit) > 1 and set(orbit).issubset(selected)
    )
    selection_audit_seconds = perf_counter() - selection_audit_started
    relation_build_started = perf_counter()
    entity_map = MappingProxyType(
        {
            (entity.dimension, entity.geometry_key): entity
            for entity in entities
        }
    )
    raw_rows = tuple(
        row for entity in entities for row in entity.rows
    )
    hanging_started = perf_counter()
    hanging = _build_hanging_relations(
        forest,
        entity_map,
        origin=origin,
        tolerance=tolerance,
    )
    hanging_seconds = perf_counter() - hanging_started
    hanging_slaves = {
        row
        for relation in hanging
        if relation.primary
        for row in relation.slave_rows
    }
    periodic_started = perf_counter()
    periodic, cycle_error = _build_periodic_relations(
        entities,
        axes=axes,
        phase_x=phase_x,
        phase_y=phase_y,
        domain_steps=domain_steps,
        hanging_slave_rows=hanging_slaves,
    )
    periodic_seconds = perf_counter() - periodic_started
    flatten_started = perf_counter()
    graph = compose_and_flatten_trace_constraints(
        raw_rows,
        (*hanging, *periodic),
    )
    flatten_seconds = perf_counter() - flatten_started
    relation_build_seconds = perf_counter() - relation_build_started
    identity_started = perf_counter()
    entity_payload = [
        (
            entity.dimension,
            entity.geometry_key,
            entity.canonical_points,
            len(entity.rows),
        )
        for entity in entities
    ]
    relation_payload = [
        {
            "kind": relation.kind,
            "primary": relation.primary,
            "slave_count": len(relation.slave_rows),
            "master_count": len(relation.master_rows),
            "matrix_sha256": hashlib.sha256(
                np.ascontiguousarray(
                    relation.slave_from_master
                ).view(np.uint8)
            ).hexdigest(),
            "provenance": dict(relation.provenance),
        }
        for relation in (*hanging, *periodic)
    ]
    physical_identity_payload = {
        "entities": entity_payload,
        "relations": relation_payload,
        "graph_sha256": graph.audit["graph_sha256"],
    }
    if variable_trace:
        physical_identity_payload[
            "geometry_canonical_entity_degree_sha256"
        ] = variable_audit[
            "geometry_canonical_entity_degree_sha256"
        ]
    physical_sha = _json_sha256(physical_identity_payload)
    sha_packets = carrier.mesh.comm.allgather(physical_sha)
    if len(set(sha_packets)) != 1:
        raise RuntimeError("MPI ranks disagree on physical trace authority")
    checks: dict[str, bool] = {
        "forest_carrier_identity": True,
        "all_hanging_patches_have_relations": {
            int(relation.provenance["patch_index"])
            for relation in hanging
        }
        == set(range(len(forest.hanging_faces))),
        "periodic_cycle_closure": cycle_error <= 5.0e-11,
        "flattened_graph_pass": graph.audit["pass"] is True,
        "no_slave_rows_numbered": (
            graph.audit[
                "hanging_or_periodic_slave_rows_globally_numbered"
            ]
            is False
        ),
        "mpi_physical_authority_identity": len(set(sha_packets)) == 1,
        "selected_p6_faces_exist": not unknown_selected,
        "selected_p6_faces_are_not_hanging": not selected_hanging,
        "selected_p6_faces_close_periodic_orbits": not partial_orbits,
    }
    if variable_trace:
        checks.update(
            {
                "variable_cell_degree_map_is_complete": (
                    len(variable_cell_map) == len(forest.leaves)
                ),
                "adjacent_cell_p_jump_at_most_one": (
                    variable_audit[
                        "maximum_adjacent_or_periodic_cell_p_jump"
                    ]
                    <= 1
                ),
                "entity_degree_bounded_by_incident_cells": bool(
                    variable_audit[
                        "entity_degree_bounded_by_incident_cells"
                    ]
                ),
                "periodic_entity_degree_closure": bool(
                    variable_audit[
                        "periodic_entity_degree_closure"
                    ]
                ),
                "hanging_entity_degree_closure": bool(
                    variable_audit[
                        "hanging_entity_degree_closure"
                    ]
                ),
                "exact_sequence_monotone": bool(
                    variable_audit["exact_sequence_monotone"]
                ),
                "inactive_high_order_trace_rows_not_numbered": (
                    variable_audit[
                        "inactive_high_order_trace_rows_globally_numbered"
                    ]
                    is False
                ),
            }
        )
    else:
        checks.update(
            {
                "all_edges_remain_at_base_degree": all(
                    entity.degree == degree
                    for entity in entities
                    if entity.dimension == 1
                ),
                "only_selected_faces_use_p6": all(
                    entity.degree
                    == (6 if entity.geometry_key in selected else degree)
                    for entity in entities
                    if entity.dimension == 2
                ),
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(
            f"broken trace constraint authority failed: {failures}"
        )
    identity_seconds = perf_counter() - identity_started
    phase_timing_local = {
        "input_and_geometry_validation": validation_seconds,
        "variable_entity_degree_fixed_point": variable_degree_seconds,
        "physical_entity_catalog": entity_catalog_seconds,
        "selection_periodic_orbit_audit": selection_audit_seconds,
        "hanging_relation_build": hanging_seconds,
        "periodic_relation_build": periodic_seconds,
        "constraint_flatten": flatten_seconds,
        "relation_build_envelope": relation_build_seconds,
        "physical_identity_and_checks": identity_seconds,
        "physical_trace_authority_total_before_audit_publish": (
            perf_counter() - authority_started
        ),
    }
    phase_timing_packets = carrier.mesh.comm.allgather(
        phase_timing_local
    )
    phase_timing_keys = tuple(phase_timing_local)
    if any(
        tuple(packet) != phase_timing_keys
        for packet in phase_timing_packets
    ):
        raise RuntimeError("MPI trace-authority timing phase catalogs differ")
    phase_timings_by_rank = {
        key: [float(packet[key]) for packet in phase_timing_packets]
        for key in phase_timing_keys
    }
    phase_timings_max = {
        key: max(values)
        for key, values in phase_timings_by_rank.items()
    }
    uniform_container_trace_rows = sum(
        _mode_count(entity.dimension, degree) for entity in entities
    )
    audit_payload = {
        "schema_version": (
            "task035e.broken-hexa-variable-trace-authority.v1"
            if variable_trace
            else "task035d.broken-hexa-trace-authority.v1"
        ),
        "status": (
            "broken_hexa_variable_trace_constraint_component_pass"
            if variable_trace
            else "broken_hexa_trace_constraint_component_pass"
        ),
        "pass": True,
        "mpi_size": int(carrier.mesh.comm.size),
        "degree": degree,
        "trace_degree_values": sorted(
            {entity.degree for entity in entities}
        ),
        "periodic_axes": list(axes),
        "phase_x": [float(np.real(phase_x)), float(np.imag(phase_x))],
        "phase_y": [float(np.real(phase_y)), float(np.imag(phase_y))],
        "physical_edge_count": sum(
            entity.dimension == 1 for entity in entities
        ),
        "physical_face_count": sum(
            entity.dimension == 2 for entity in entities
        ),
        "selected_p6_face_count": len(selected),
        "selected_p6_face_geometry_keys": [
            list(key) for key in sorted(selected)
        ],
        "selected_p6_periodic_orbit_count": len(
            selected_periodic_orbits
        ),
        "selected_p6_periodic_orbits": [
            [list(key) for key in orbit]
            for orbit in selected_periodic_orbits
        ],
        "hanging_face_participant_count": len(
            hanging_face_keys
        ),
        "selective_trace_full3d_dof_delta": 20 * len(selected),
        "variable_trace_opt_in": variable_trace,
        "variable_trace_row_delta_from_uniform_container": (
            len(raw_rows) - uniform_container_trace_rows
        ),
        "uniform_container_trace_rows": uniform_container_trace_rows,
        "raw_trace_rows": len(raw_rows),
        "hanging_relation_count": len(hanging),
        "hanging_patch_count": len(forest.hanging_faces),
        "hanging_primary_relation_count": sum(
            relation.primary for relation in hanging
        ),
        "hanging_secondary_relation_count": sum(
            not relation.primary for relation in hanging
        ),
        "hanging_slave_rows": sum(
            len(relation.slave_rows)
            for relation in hanging
            if relation.primary
        ),
        "periodic_relation_count": len(periodic),
        "periodic_primary_relation_count": sum(
            relation.primary for relation in periodic
        ),
        "periodic_secondary_relation_count": sum(
            not relation.primary for relation in periodic
        ),
        "periodic_cycle_error": cycle_error,
        "independent_trace_rows": graph.audit[
            "independent_trace_rows"
        ],
        "maximum_chain_depth": graph.audit["maximum_chain_depth"],
        "maximum_relation_residual": graph.audit[
            "maximum_relation_residual"
        ],
        "entity_catalog_sha256": _json_sha256(entity_payload),
        "physical_authority_sha256": physical_sha,
        "flattened_graph_sha256": graph.audit["graph_sha256"],
        "phase_timing_semantics": (
            "perf_counter wall seconds; by-rank values plus MPI maximum; "
            "diagnostic only and excluded from physical authority hashes"
        ),
        "phase_timings_seconds_by_rank": phase_timings_by_rank,
        "phase_timings_seconds_max": phase_timings_max,
        "checks": checks,
        "failures": failures,
        "partition_independent_physical_keys": True,
        "compiled_cell_tensor_binding_complete": False,
        "mpi_physical_catalog_identity_qualified": True,
        "mpi_constraint_row_ownership_qualified": False,
        "mpi_ghost_expansion_qualified": False,
        "distributed_scalability_qualified": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    if variable_trace:
        audit_payload["variable_trace_degree_audit"] = dict(variable_audit)
        audit_payload["geometry_canonical_entity_degree_sha256"] = (
            variable_audit[
                "geometry_canonical_entity_degree_sha256"
            ]
        )
        audit_payload["hanging_patch_degrees"] = list(
            variable_audit["hanging_patch_degrees"]
        )
    audit = MappingProxyType(audit_payload)
    edge_degree_output = MappingProxyType(
        {
            entity.geometry_key: int(entity.degree)
            for entity in entities
            if entity.dimension == 1
        }
    )
    face_degree_output = MappingProxyType(
        {
            entity.geometry_key: int(entity.degree)
            for entity in entities
            if entity.dimension == 2
        }
    )
    return BrokenHexTraceConstraintAuthority(
        degree=degree,
        entities=entities,
        hanging_relations=hanging,
        periodic_relations=periodic,
        graph=graph,
        selected_p6_face_geometry_keys=tuple(sorted(selected)),
        audit=audit,
        cell_degree_by_box=variable_cell_map,
        edge_degree_by_geometry_key=edge_degree_output,
        face_degree_by_geometry_key=face_degree_output,
    )


__all__ = [
    "BrokenHexTraceConstraintAuthority",
    "PhysicalTraceEntity",
    "build_broken_hexa_entity_degree_arrays",
    "build_broken_hexa_trace_constraint_authority",
    "physical_face_closure_rows",
]
