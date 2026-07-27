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

from dataclasses import dataclass
import hashlib
import json
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


def _entity_catalog(
    carrier: BrokenDyadicHexCarrier,
    *,
    degree: int,
    selected_p6_face_geometry_keys: set[tuple[int, ...]],
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
        entity_degree = (
            6
            if (
                int(dimension) == 2
                and identity[1] in selected_p6_face_geometry_keys
            )
            else degree
        )
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


def _face_full_rows(
    face: PhysicalTraceEntity,
    entities: Mapping[tuple[int, tuple[int, ...]], PhysicalTraceEntity],
) -> tuple[PhysicalTraceRowKey, ...]:
    if face.dimension != 2:
        raise ValueError("full face trace requires a face entity")
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
    degree: int,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[LinearTraceRelation, ...]:
    pair = build_hanging_face_reference_pair(degree)
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
        coarse_rows = _face_full_rows(coarse_face, entities)
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
            local_rows = _face_full_rows(fine_face, entities)
            aggregate_rows = pair.hcurl_child_rows[child]
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
) -> BrokenHexTraceConstraintAuthority:
    """Build actual physical hanging/Floquet relations and flatten them."""

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
    entities = _entity_catalog(
        carrier,
        degree=degree,
        selected_p6_face_geometry_keys=selected,
        origin=origin,
        tolerance=tolerance,
    )
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
    axes = (
        tuple(forest.periodic_axes)
        if periodic_axes is None
        else tuple(periodic_axes)
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
    entity_map = MappingProxyType(
        {
            (entity.dimension, entity.geometry_key): entity
            for entity in entities
        }
    )
    raw_rows = tuple(
        row for entity in entities for row in entity.rows
    )
    hanging = _build_hanging_relations(
        forest,
        entity_map,
        degree=degree,
        origin=origin,
        tolerance=tolerance,
    )
    hanging_slaves = {
        row
        for relation in hanging
        if relation.primary
        for row in relation.slave_rows
    }
    periodic, cycle_error = _build_periodic_relations(
        entities,
        axes=axes,
        phase_x=phase_x,
        phase_y=phase_y,
        domain_steps=domain_steps,
        hanging_slave_rows=hanging_slaves,
    )
    graph = compose_and_flatten_trace_constraints(
        raw_rows,
        (*hanging, *periodic),
    )
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
    physical_sha = _json_sha256(
        {
            "entities": entity_payload,
            "relations": relation_payload,
            "graph_sha256": graph.audit["graph_sha256"],
        }
    )
    sha_packets = carrier.mesh.comm.allgather(physical_sha)
    if len(set(sha_packets)) != 1:
        raise RuntimeError("MPI ranks disagree on physical trace authority")
    checks = {
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
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(
            f"broken trace constraint authority failed: {failures}"
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035d.broken-hexa-trace-authority.v1",
            "status": "broken_hexa_trace_constraint_component_pass",
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
    )
    return BrokenHexTraceConstraintAuthority(
        degree=degree,
        entities=entities,
        hanging_relations=hanging,
        periodic_relations=periodic,
        graph=graph,
        selected_p6_face_geometry_keys=tuple(sorted(selected)),
        audit=audit,
    )


__all__ = [
    "BrokenHexTraceConstraintAuthority",
    "PhysicalTraceEntity",
    "build_broken_hexa_entity_degree_arrays",
    "build_broken_hexa_trace_constraint_authority",
]
