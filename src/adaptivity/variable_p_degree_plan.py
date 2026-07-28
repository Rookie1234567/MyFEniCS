"""Geometry-bound cell plans and exact-sequence entity-degree closure."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from dolfinx import mesh as dmesh

from .variable_p_entity_map import (
    VariablePGlobalEntityMap,
    build_variable_p_global_entity_map,
)


CellBoxKey = tuple[float, float, float, float, float, float]
EntityGeometryKey = tuple[tuple[float, float, float], ...]
_QUALIFIED_DEGREES = (4, 5, 6)
LEGACY_DOWNWARD_TRANSITION_POLICY = "keep_or_lower_one"
BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY = "one_step_bidirectional"
_TRANSITION_POLICIES = (
    LEGACY_DOWNWARD_TRANSITION_POLICY,
    BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY,
)
_LEGACY_PLAN_SCHEMA = "task035d.variable-p-cell-degree-plan.v1"
_TRANSITION_PLAN_SCHEMA = "task035e.variable-p-cell-degree-plan.v2"


@dataclass(frozen=True)
class VariablePCellDegreePlan:
    """One geometry-bound cell policy closed onto mesh trace entities."""

    cell_degree_by_box: Mapping[CellBoxKey, int]
    edge_degrees: np.ndarray
    face_degrees: np.ndarray
    cell_degrees: np.ndarray
    entity_map: VariablePGlobalEntityMap
    audit: Mapping[str, Any]


def _rounded_point(values: np.ndarray) -> tuple[float, float, float]:
    return tuple(
        float(value)
        for value in np.round(
            np.asarray(values, dtype=np.float64),
            decimals=12,
        )
    )


def _box_key_from_points(points: np.ndarray) -> CellBoxKey:
    coordinates = np.asarray(points, dtype=np.float64)
    if coordinates.ndim != 2 or coordinates.shape[1] < 3:
        raise ValueError("cell geometry points must have three coordinates")
    lower = _rounded_point(np.min(coordinates[:, :3], axis=0))
    upper = _rounded_point(np.max(coordinates[:, :3], axis=0))
    if any(right <= left for left, right in zip(lower, upper, strict=True)):
        raise ValueError("cell box has a non-positive axis extent")
    return (*lower, *upper)


def _entity_key_from_points(points: np.ndarray) -> EntityGeometryKey:
    return tuple(
        sorted(
            _rounded_point(point)
            for point in np.asarray(points, dtype=np.float64)
        )
    )


def _box_vertices(box: CellBoxKey) -> tuple[tuple[float, float, float], ...]:
    lower = box[:3]
    upper = box[3:]
    return tuple(
        (
            upper[0] if x else lower[0],
            upper[1] if y else lower[1],
            upper[2] if z else lower[2],
        )
        for x in (0, 1)
        for y in (0, 1)
        for z in (0, 1)
    )


def _box_entity_keys(
    box: CellBoxKey,
    *,
    dimension: int,
) -> tuple[EntityGeometryKey, ...]:
    vertices = _box_vertices(box)
    bits = tuple(
        (x, y, z)
        for x in (0, 1)
        for y in (0, 1)
        for z in (0, 1)
    )
    if dimension == 1:
        keys = {
            tuple(sorted((vertices[left], vertices[right])))
            for left, left_bits in enumerate(bits)
            for right, right_bits in enumerate(bits)
            if sum(
                int(a != b)
                for a, b in zip(left_bits, right_bits, strict=True)
            )
            == 1
        }
        expected = 12
    elif dimension == 2:
        keys = {
            tuple(
                sorted(
                    vertices[index]
                    for index, vertex_bits in enumerate(bits)
                    if vertex_bits[axis] == side
                )
            )
            for axis in range(3)
            for side in (0, 1)
        }
        expected = 6
    else:
        raise ValueError("cell boxes expose only edge and face keys")
    if len(keys) != expected:
        raise RuntimeError("axis-aligned box entity enumeration failed")
    return tuple(sorted(keys))


def cell_box_catalog(msh: Any) -> tuple[CellBoxKey, ...]:
    """Return the partition-independent sorted physical cell catalog."""

    topology = msh.topology
    cell_map = topology.index_map(3)
    owned = int(cell_map.size_local)
    local = tuple(
        _box_key_from_points(
            msh.geometry.x[
                np.asarray(msh.geometry.dofmap[cell], dtype=np.int32)
            ]
        )
        for cell in range(owned)
    )
    packets = msh.comm.allgather(local)
    boxes = tuple(sorted(box for packet in packets for box in packet))
    if len(boxes) != int(cell_map.size_global):
        raise RuntimeError("physical cell box catalog is incomplete")
    if len(set(boxes)) != len(boxes):
        raise RuntimeError("physical cell boxes are not unique")
    return boxes


def cell_box_catalog_sha256(boxes: tuple[CellBoxKey, ...]) -> str:
    encoded = json.dumps(
        [list(box) for box in boxes],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _cell_degree_plan_sha256(
    boxes: tuple[CellBoxKey, ...],
    degree_by_box: Mapping[CellBoxKey, int],
) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                {"box": list(box), "degree": degree_by_box[box]}
                for box in boxes
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _transition_context_sha256(
    *,
    geometry_sha256: str,
    cell_degree_plan_sha256: str,
    previous_cell_degree_plan_sha256: str | None,
    transition_policy: str,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "cell_degree_plan_sha256": cell_degree_plan_sha256,
                "mesh_cell_box_catalog_sha256": geometry_sha256,
                "previous_cell_degree_plan_sha256": (
                    previous_cell_degree_plan_sha256
                ),
                "transition_policy": transition_policy,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _plan_from_payload_rows(
    rows: Any,
    *,
    label: str,
) -> dict[CellBoxKey, int]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"variable-p degree plan has no {label}")
    plan: dict[CellBoxKey, int] = {}
    for row in rows:
        lower = tuple(map(float, row["lower"]))
        upper = tuple(map(float, row["upper"]))
        if len(lower) != 3 or len(upper) != 3:
            raise ValueError("degree-plan cell bounds must be 3D")
        box = (*lower, *upper)
        if box in plan:
            raise ValueError("degree-plan cell box is duplicated")
        plan[box] = int(row["degree"])
    return plan


def _payload_cell_rows(
    boxes: tuple[CellBoxKey, ...],
    degree_by_box: Mapping[CellBoxKey, int],
) -> list[dict[str, Any]]:
    return [
        {
            "lower": list(box[:3]),
            "upper": list(box[3:]),
            "degree": int(degree_by_box[box]),
        }
        for box in boxes
    ]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _translated_entity_key(
    key: EntityGeometryKey,
    *,
    axis: int,
    offset: float,
) -> EntityGeometryKey:
    translated: list[tuple[float, float, float]] = []
    for point in key:
        values = list(point)
        values[axis] += float(offset)
        translated.append(_rounded_point(np.asarray(values)))
    return tuple(sorted(translated))


def _entity_degree_payload(
    degrees: Mapping[int, Mapping[EntityGeometryKey, int]],
) -> list[dict[str, Any]]:
    return [
        {
            "dimension": dimension,
            "geometry_key": [list(point) for point in key],
            "degree": int(degrees[dimension][key]),
        }
        for dimension in (1, 2)
        for key in sorted(degrees[dimension])
    ]


def _periodic_xy_entity_degree_closure(
    boxes: tuple[CellBoxKey, ...],
    raw_degrees: Mapping[int, Mapping[EntityGeometryKey, int]],
    incident_cells_by_face: Mapping[
        EntityGeometryKey,
        tuple[CellBoxKey, ...],
    ],
    cell_degree_by_box: Mapping[CellBoxKey, int],
) -> tuple[dict[int, dict[EntityGeometryKey, int]], dict[str, Any]]:
    """Close x/y Floquet entity orbits before canonical active numbering."""

    lower = tuple(min(box[axis] for box in boxes) for axis in range(3))
    upper = tuple(
        max(box[axis + 3] for box in boxes) for axis in range(3)
    )
    relations: list[
        tuple[str, int, EntityGeometryKey, EntityGeometryKey]
    ] = []
    relation_records: list[dict[str, Any]] = []
    relation_counts: dict[str, int] = {}
    for axis_name, axis in (("x", 0), ("y", 1)):
        period = float(upper[axis] - lower[axis])
        if period <= 0.0:
            raise RuntimeError("periodic variable-p domain has zero extent")
        for dimension in (1, 2):
            available = raw_degrees[dimension]
            for slave in sorted(available):
                if not all(
                    point[axis] == upper[axis] for point in slave
                ):
                    continue
                master = _translated_entity_key(
                    slave,
                    axis=axis,
                    offset=-period,
                )
                if master not in available:
                    raise RuntimeError(
                        "periodic variable-p boundary entity has no "
                        f"translated {axis_name} master"
                    )
                relations.append(
                    (axis_name, dimension, master, slave)
                )
                relation_counts[f"{axis_name}.dim{dimension}"] = (
                    relation_counts.get(
                        f"{axis_name}.dim{dimension}",
                        0,
                    )
                    + 1
                )
                relation_records.append(
                    {
                        "axis": axis_name,
                        "dimension": dimension,
                        "master_geometry_key": [
                            list(point) for point in master
                        ],
                        "slave_geometry_key": [
                            list(point) for point in slave
                        ],
                    }
                )
    relations.sort()
    relation_records.sort(
        key=lambda row: (
            row["axis"],
            row["dimension"],
            row["master_geometry_key"],
            row["slave_geometry_key"],
        )
    )

    periodic_cell_records: list[dict[str, Any]] = []
    for axis_name, dimension, master, slave in relations:
        if dimension != 2:
            continue
        master_cells = incident_cells_by_face.get(master, ())
        slave_cells = incident_cells_by_face.get(slave, ())
        if len(master_cells) != 1 or len(slave_cells) != 1:
            raise RuntimeError(
                "periodic boundary face does not have one incident cell"
            )
        master_cell = master_cells[0]
        slave_cell = slave_cells[0]
        master_degree = int(cell_degree_by_box[master_cell])
        slave_degree = int(cell_degree_by_box[slave_cell])
        periodic_cell_records.append(
            {
                "axis": axis_name,
                "master_cell": list(master_cell),
                "slave_cell": list(slave_cell),
                "master_degree": master_degree,
                "slave_degree": slave_degree,
                "jump": abs(master_degree - slave_degree),
            }
        )
    periodic_cell_records.sort(
        key=lambda row: (
            row["axis"],
            row["master_cell"],
            row["slave_cell"],
        )
    )
    maximum_periodic_cell_jump = max(
        (int(row["jump"]) for row in periodic_cell_records),
        default=0,
    )
    if maximum_periodic_cell_jump > 1:
        violations = [
            row
            for row in periodic_cell_records
            if int(row["jump"]) > 1
        ]
        raise ValueError(
            "periodic cells differ by more than one p level: "
            f"{violations[:2]}"
        )

    closed = {
        dimension: {
            key: int(degree)
            for key, degree in raw_degrees[dimension].items()
        }
        for dimension in (1, 2)
    }
    fixed_point_iterations = 0
    while True:
        updated = {
            dimension: dict(closed[dimension])
            for dimension in (1, 2)
        }
        for _axis_name, dimension, master, slave in relations:
            shared = min(
                closed[dimension][master],
                closed[dimension][slave],
            )
            updated[dimension][master] = min(
                updated[dimension][master],
                shared,
            )
            updated[dimension][slave] = min(
                updated[dimension][slave],
                shared,
            )
        if updated == closed:
            break
        closed = updated
        fixed_point_iterations += 1
        if fixed_point_iterations > sum(
            len(closed[dimension]) for dimension in (1, 2)
        ):
            raise RuntimeError(
                "periodic variable-p entity degree closure did not converge"
            )
    if any(
        closed[dimension][master] != closed[dimension][slave]
        for _axis_name, dimension, master, slave in relations
    ):
        raise RuntimeError(
            "periodic variable-p entity degrees did not reach a fixed point"
        )

    parent: dict[
        tuple[int, EntityGeometryKey],
        tuple[int, EntityGeometryKey],
    ] = {}

    def find(
        node: tuple[int, EntityGeometryKey],
    ) -> tuple[int, EntityGeometryKey]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(
        left: tuple[int, EntityGeometryKey],
        right: tuple[int, EntityGeometryKey],
    ) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parent[high] = low

    for _axis_name, dimension, master, slave in relations:
        union((dimension, master), (dimension, slave))
    orbit_members: dict[
        tuple[int, EntityGeometryKey],
        list[tuple[int, EntityGeometryKey]],
    ] = {}
    for node in sorted(parent):
        orbit_members.setdefault(find(node), []).append(node)
    orbit_records = [
        {
            "dimension": members[0][0],
            "size": len(members),
            "geometry_keys": [
                [list(point) for point in key]
                for _dimension, key in sorted(members)
            ],
        }
        for members in sorted(
            orbit_members.values(),
            key=lambda values: tuple(sorted(values)),
        )
    ]

    changes = [
        {
            "dimension": dimension,
            "geometry_key": [list(point) for point in key],
            "raw_degree": int(raw_degrees[dimension][key]),
            "closed_degree": int(closed[dimension][key]),
        }
        for dimension in (1, 2)
        for key in sorted(closed[dimension])
        if int(raw_degrees[dimension][key])
        != int(closed[dimension][key])
    ]
    degree_change_counts: dict[str, int] = {}
    for row in changes:
        label = f"p{row['raw_degree']}_to_p{row['closed_degree']}"
        degree_change_counts[label] = degree_change_counts.get(label, 0) + 1
    jump_histogram: dict[str, int] = {}
    for row in periodic_cell_records:
        label = str(row["jump"])
        jump_histogram[label] = jump_histogram.get(label, 0) + 1
    audit = {
        "schema_version": (
            "task035e.variable-p-periodic-entity-degree-closure.v1"
        ),
        "status": "periodic_xy_entity_degree_fixed_point_closed",
        "pass": True,
        "periodic_axes": ["x", "y"],
        "relation_count": len(relations),
        "relation_counts_by_axis_dimension": dict(
            sorted(relation_counts.items())
        ),
        "relation_sha256": _json_sha256(relation_records),
        "boundary_orbit_count": len(orbit_records),
        "maximum_boundary_orbit_size": max(
            (int(row["size"]) for row in orbit_records),
            default=0,
        ),
        "orbit_sha256": _json_sha256(orbit_records),
        "fixed_point_iterations": fixed_point_iterations,
        "raw_entity_degree_sha256": _json_sha256(
            _entity_degree_payload(raw_degrees)
        ),
        "closed_entity_degree_sha256": _json_sha256(
            _entity_degree_payload(closed)
        ),
        "lowered_entity_count": len(changes),
        "degree_change_counts": dict(sorted(degree_change_counts.items())),
        "degree_change_sha256": _json_sha256(changes),
        "degree_change_examples": changes[:8],
        "periodic_cell_pair_count": len(periodic_cell_records),
        "periodic_cell_pair_sha256": _json_sha256(
            periodic_cell_records
        ),
        "periodic_cell_jump_histogram": dict(
            sorted(jump_histogram.items())
        ),
        "maximum_periodic_cell_degree_jump": (
            maximum_periodic_cell_jump
        ),
        "periodic_cell_jump_checked_before_entity_lowering": True,
        "periodic_relation_degrees_closed": True,
        "ordinary_default_changed": False,
    }
    return closed, audit


def _local_entity_degrees(
    msh: Any,
    *,
    dimension: int,
    degree_by_key: Mapping[EntityGeometryKey, int],
) -> np.ndarray:
    topology = msh.topology
    topology.create_entities(dimension)
    topology.create_connectivity(dimension, 3)
    topology.create_entity_permutations()
    index_map = topology.index_map(dimension)
    local_count = int(index_map.size_local + index_map.num_ghosts)
    entities = np.arange(local_count, dtype=np.int32)
    geometry_dofs = dmesh.entities_to_geometry(
        msh,
        dimension,
        entities,
        permute=True,
    )
    values = np.empty(local_count, dtype=np.int32)
    for entity, dofs in enumerate(geometry_dofs):
        key = _entity_key_from_points(msh.geometry.x[dofs, :3])
        try:
            values[entity] = int(degree_by_key[key])
        except KeyError as exc:
            raise RuntimeError(
                f"dimension-{dimension} mesh entity is absent from plan"
            ) from exc
    return values


def build_variable_p_cell_degree_plan(
    msh: Any,
    cell_degree_by_box: Mapping[CellBoxKey, int],
    *,
    previous_cell_degree_by_box: Mapping[CellBoxKey, int] | None = None,
    transition_policy: str = LEGACY_DOWNWARD_TRANSITION_POLICY,
) -> VariablePCellDegreePlan:
    """Close cell degrees onto conforming and x/y-periodic trace modes."""

    if transition_policy not in _TRANSITION_POLICIES:
        raise ValueError(
            "unknown variable-p transition policy: "
            f"{transition_policy!r}"
        )
    if (
        transition_policy == BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
        and previous_cell_degree_by_box is None
    ):
        raise ValueError(
            "bidirectional one-step transition policy requires a "
            "previous cell degree plan"
        )
    boxes = cell_box_catalog(msh)
    normalized = {
        tuple(map(float, box)): int(degree)
        for box, degree in cell_degree_by_box.items()
    }
    if set(normalized) != set(boxes):
        missing = sorted(set(boxes) - set(normalized))
        extra = sorted(set(normalized) - set(boxes))
        raise ValueError(
            "cell degree plan does not exactly match mesh geometry: "
            f"missing={missing[:2]}, extra={extra[:2]}"
        )
    invalid = sorted(
        {
            degree
            for degree in normalized.values()
            if degree not in _QUALIFIED_DEGREES
        }
    )
    if invalid:
        raise ValueError(
            f"cell degree plan contains values outside p4/p5/p6: {invalid}"
        )
    previous: dict[CellBoxKey, int] | None = None
    if previous_cell_degree_by_box is not None:
        previous = {
            tuple(map(float, box)): int(degree)
            for box, degree in previous_cell_degree_by_box.items()
        }
        if set(previous) != set(boxes):
            raise ValueError("previous cell degree plan has another geometry")
        invalid_previous = sorted(
            {
                degree
                for degree in previous.values()
                if degree not in _QUALIFIED_DEGREES
            }
        )
        if invalid_previous:
            raise ValueError(
                "previous cell degree plan contains values outside "
                f"p4/p5/p6: {invalid_previous}"
            )
        if transition_policy == LEGACY_DOWNWARD_TRANSITION_POLICY:
            illegal_transitions = [
                (box, previous[box], normalized[box])
                for box in boxes
                if normalized[box]
                not in {previous[box], previous[box] - 1}
            ]
            transition_error = (
                "one p-adaptive cycle may only keep or lower one degree"
            )
        else:
            illegal_transitions = [
                (box, previous[box], normalized[box])
                for box in boxes
                if abs(normalized[box] - previous[box]) > 1
            ]
            transition_error = (
                "one bidirectional p-adaptive cycle may only change "
                "one degree"
            )
        if illegal_transitions:
            raise ValueError(
                f"{transition_error}: {illegal_transitions[:2]}"
            )

    degrees_by_entity_key: dict[
        int,
        dict[EntityGeometryKey, int],
    ] = {1: {}, 2: {}}
    incident_cells_by_face: dict[
        EntityGeometryKey,
        list[CellBoxKey],
    ] = {}
    for box in boxes:
        degree = normalized[box]
        for dimension in (1, 2):
            for key in _box_entity_keys(box, dimension=dimension):
                current = degrees_by_entity_key[dimension].get(key, 6)
                degrees_by_entity_key[dimension][key] = min(
                    current,
                    degree,
                )
                if dimension == 2:
                    incident_cells_by_face.setdefault(
                        key,
                        [],
                    ).append(box)
    adjacent_jumps = [
        max(normalized[box] for box in incident_cells)
        - min(normalized[box] for box in incident_cells)
        for incident_cells in incident_cells_by_face.values()
        if len(incident_cells) == 2
    ]
    maximum_adjacent_jump = max(adjacent_jumps, default=0)
    if maximum_adjacent_jump > 1:
        raise ValueError(
            "adjacent cells differ by more than one p level"
        )
    degrees_by_entity_key, periodic_degree_audit = (
        _periodic_xy_entity_degree_closure(
            boxes,
            degrees_by_entity_key,
            {
                key: tuple(sorted(incident_cells))
                for key, incident_cells in incident_cells_by_face.items()
            },
            normalized,
        )
    )

    edge_degrees = _local_entity_degrees(
        msh,
        dimension=1,
        degree_by_key=degrees_by_entity_key[1],
    )
    face_degrees = _local_entity_degrees(
        msh,
        dimension=2,
        degree_by_key=degrees_by_entity_key[2],
    )
    cell_map = msh.topology.index_map(3)
    local_cell_count = int(
        cell_map.size_local + cell_map.num_ghosts
    )
    cell_degrees = np.empty(local_cell_count, dtype=np.int32)
    for cell in range(local_cell_count):
        box = _box_key_from_points(
            msh.geometry.x[
                np.asarray(msh.geometry.dofmap[cell], dtype=np.int32)
            ]
        )
        cell_degrees[cell] = normalized[box]

    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=cell_degrees,
    )
    geometry_sha = cell_box_catalog_sha256(boxes)
    cell_plan_sha = _cell_degree_plan_sha256(boxes, normalized)
    previous_plan_sha = (
        None
        if previous is None
        else _cell_degree_plan_sha256(boxes, previous)
    )
    transition_context_sha = _transition_context_sha256(
        geometry_sha256=geometry_sha,
        cell_degree_plan_sha256=cell_plan_sha,
        previous_cell_degree_plan_sha256=previous_plan_sha,
        transition_policy=transition_policy,
    )
    counts = {
        f"p{degree}": sum(
            value == degree for value in normalized.values()
        )
        for degree in _QUALIFIED_DEGREES
    }
    audit = MappingProxyType(
        {
            "schema_version": (
                _TRANSITION_PLAN_SCHEMA
                if transition_policy
                == BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
                else _LEGACY_PLAN_SCHEMA
            ),
            "status": "geometry_bound_cell_degree_plan_closed",
            "pass": True,
            "mpi_size": int(msh.comm.size),
            "mesh_cell_box_catalog_sha256": geometry_sha,
            "cell_degree_plan_sha256": cell_plan_sha,
            "previous_cell_degree_plan_sha256": previous_plan_sha,
            "transition_policy": transition_policy,
            "transition_context_sha256": transition_context_sha,
            "cell_count": len(boxes),
            "cell_degree_counts": counts,
            "maximum_adjacent_cell_degree_jump": (
                maximum_adjacent_jump
            ),
            "maximum_periodic_cell_degree_jump": (
                periodic_degree_audit[
                    "maximum_periodic_cell_degree_jump"
                ]
            ),
            "maximum_adjacent_or_periodic_cell_degree_jump": max(
                maximum_adjacent_jump,
                int(
                    periodic_degree_audit[
                        "maximum_periodic_cell_degree_jump"
                    ]
                ),
            ),
            "transition_from_previous_checked": (
                previous_cell_degree_by_box is not None
            ),
            "entity_degree_closure": (
                "face=min(incident cell); edge=min(incident cell); "
                "x/y periodic entity orbits=fixed-point minimum"
            ),
            "periodic_entity_degree_closure": periodic_degree_audit,
            "active_rows": entity_map.active_rows,
            "active_trace_rows": entity_map.active_trace_rows,
            "inactive_p6_rows": int(
                entity_map.uniform_p6_rows - entity_map.active_rows
            ),
            "inactive_p6_trace_rows": int(
                entity_map.uniform_p6_trace_rows
                - entity_map.active_trace_rows
            ),
            "geometry_bound_not_global_entity_id_bound": True,
            "ordinary_default_changed": False,
        }
    )
    return VariablePCellDegreePlan(
        cell_degree_by_box=MappingProxyType(normalized),
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=cell_degrees,
        entity_map=entity_map,
        audit=audit,
    )


def load_variable_p_cell_degree_plan(
    msh: Any,
    path: str | Path,
) -> VariablePCellDegreePlan:
    """Load a geometry-bound Task035d/Task035e degree-plan JSON."""

    resolved = Path(path).expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    schema_version = payload.get("schema_version")
    if schema_version not in {
        _LEGACY_PLAN_SCHEMA,
        _TRANSITION_PLAN_SCHEMA,
    }:
        raise ValueError("variable-p degree plan has an unknown schema")
    plan = _plan_from_payload_rows(
        payload.get("cells"),
        label="cells",
    )
    boxes = cell_box_catalog(msh)
    expected_geometry_sha = payload.get(
        "mesh_cell_box_catalog_sha256"
    )
    actual_geometry_sha = cell_box_catalog_sha256(boxes)
    if expected_geometry_sha != actual_geometry_sha:
        raise ValueError(
            "degree-plan geometry SHA differs from the actual mesh"
        )
    if schema_version == _TRANSITION_PLAN_SCHEMA:
        previous = _plan_from_payload_rows(
            payload.get("previous_cells"),
            label="previous cells",
        )
        transition_policy = payload.get("transition_policy")
        if not isinstance(transition_policy, str):
            raise ValueError(
                "variable-p transition policy must be a string"
            )
    else:
        previous = None
        transition_policy = LEGACY_DOWNWARD_TRANSITION_POLICY
    result = build_variable_p_cell_degree_plan(
        msh,
        plan,
        previous_cell_degree_by_box=previous,
        transition_policy=transition_policy,
    )
    expected_plan_sha = payload.get("cell_degree_plan_sha256")
    if (
        expected_plan_sha is not None
        and expected_plan_sha
        != result.audit["cell_degree_plan_sha256"]
    ):
        raise ValueError("degree-plan content SHA is invalid")
    if schema_version == _TRANSITION_PLAN_SCHEMA:
        if (
            payload.get("previous_cell_degree_plan_sha256")
            != result.audit["previous_cell_degree_plan_sha256"]
        ):
            raise ValueError(
                "previous degree-plan content SHA is invalid"
            )
        if (
            payload.get("transition_context_sha256")
            != result.audit["transition_context_sha256"]
        ):
            raise ValueError(
                "degree-plan transition context SHA is invalid"
            )
    return result


def variable_p_cell_degree_plan_payload(
    msh: Any,
    cell_degree_by_box: Mapping[CellBoxKey, int],
    *,
    provenance: Mapping[str, Any],
    previous_cell_degree_by_box: Mapping[CellBoxKey, int] | None = None,
    transition_policy: str = LEGACY_DOWNWARD_TRANSITION_POLICY,
) -> dict[str, Any]:
    """Return a JSON-ready, hash-bound plan after full closure validation."""

    plan = build_variable_p_cell_degree_plan(
        msh,
        cell_degree_by_box,
        previous_cell_degree_by_box=previous_cell_degree_by_box,
        transition_policy=transition_policy,
    )
    boxes = cell_box_catalog(msh)
    payload: dict[str, Any] = {
        "schema_version": (
            _LEGACY_PLAN_SCHEMA
            if previous_cell_degree_by_box is None
            else _TRANSITION_PLAN_SCHEMA
        ),
        "status": "geometry_bound_cell_degree_plan",
        "mesh_cell_box_catalog_sha256": plan.audit[
            "mesh_cell_box_catalog_sha256"
        ],
        "cell_degree_plan_sha256": plan.audit[
            "cell_degree_plan_sha256"
        ],
        "cells": _payload_cell_rows(
            boxes,
            plan.cell_degree_by_box,
        ),
        "closure_audit": dict(plan.audit),
        "provenance": dict(provenance),
        "ordinary_default_changed": False,
    }
    if previous_cell_degree_by_box is not None:
        previous = {
            tuple(map(float, box)): int(degree)
            for box, degree in previous_cell_degree_by_box.items()
        }
        payload.update(
            {
                "transition_policy": transition_policy,
                "previous_cells": _payload_cell_rows(
                    boxes,
                    previous,
                ),
                "previous_cell_degree_plan_sha256": plan.audit[
                    "previous_cell_degree_plan_sha256"
                ],
                "transition_context_sha256": plan.audit[
                    "transition_context_sha256"
                ],
            }
        )
    return payload


__all__ = [
    "BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY",
    "CellBoxKey",
    "LEGACY_DOWNWARD_TRANSITION_POLICY",
    "VariablePCellDegreePlan",
    "build_variable_p_cell_degree_plan",
    "cell_box_catalog",
    "cell_box_catalog_sha256",
    "load_variable_p_cell_degree_plan",
    "variable_p_cell_degree_plan_payload",
]
