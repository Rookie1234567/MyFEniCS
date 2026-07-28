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
) -> VariablePCellDegreePlan:
    """Close geometry-bound cell degrees onto conforming edge/face modes."""

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
    if previous_cell_degree_by_box is not None:
        previous = {
            tuple(map(float, box)): int(degree)
            for box, degree in previous_cell_degree_by_box.items()
        }
        if set(previous) != set(boxes):
            raise ValueError("previous cell degree plan has another geometry")
        illegal_transitions = [
            (box, previous[box], normalized[box])
            for box in boxes
            if normalized[box] not in {
                previous[box],
                previous[box] - 1,
            }
        ]
        if illegal_transitions:
            raise ValueError(
                "one p-adaptive cycle may only keep or lower one degree: "
                f"{illegal_transitions[:2]}"
            )

    degrees_by_entity_key: dict[
        int,
        dict[EntityGeometryKey, int],
    ] = {1: {}, 2: {}}
    incident_cell_degrees_by_face: dict[
        EntityGeometryKey,
        list[int],
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
                    incident_cell_degrees_by_face.setdefault(
                        key,
                        [],
                    ).append(degree)
    adjacent_jumps = [
        max(degrees) - min(degrees)
        for degrees in incident_cell_degrees_by_face.values()
        if len(degrees) == 2
    ]
    maximum_adjacent_jump = max(adjacent_jumps, default=0)
    if maximum_adjacent_jump > 1:
        raise ValueError(
            "adjacent cells differ by more than one p level"
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
    cell_plan_sha = hashlib.sha256(
        json.dumps(
            [
                {"box": list(box), "degree": normalized[box]}
                for box in boxes
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    counts = {
        f"p{degree}": sum(
            value == degree for value in normalized.values()
        )
        for degree in _QUALIFIED_DEGREES
    }
    audit = MappingProxyType(
        {
            "schema_version": "task035d.variable-p-cell-degree-plan.v1",
            "status": "geometry_bound_cell_degree_plan_closed",
            "pass": True,
            "mpi_size": int(msh.comm.size),
            "mesh_cell_box_catalog_sha256": (
                cell_box_catalog_sha256(boxes)
            ),
            "cell_degree_plan_sha256": cell_plan_sha,
            "cell_count": len(boxes),
            "cell_degree_counts": counts,
            "maximum_adjacent_cell_degree_jump": (
                maximum_adjacent_jump
            ),
            "transition_from_previous_checked": (
                previous_cell_degree_by_box is not None
            ),
            "entity_degree_closure": (
                "face=min(incident cell); edge=min(incident cell)"
            ),
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
    """Load and validate a geometry-bound Task035d degree-plan JSON."""

    resolved = Path(path).expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("schema_version") != (
        "task035d.variable-p-cell-degree-plan.v1"
    ):
        raise ValueError("variable-p degree plan has an unknown schema")
    rows = payload.get("cells")
    if not isinstance(rows, list) or not rows:
        raise ValueError("variable-p degree plan has no cells")
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
    boxes = cell_box_catalog(msh)
    expected_geometry_sha = payload.get(
        "mesh_cell_box_catalog_sha256"
    )
    actual_geometry_sha = cell_box_catalog_sha256(boxes)
    if expected_geometry_sha != actual_geometry_sha:
        raise ValueError(
            "degree-plan geometry SHA differs from the actual mesh"
        )
    result = build_variable_p_cell_degree_plan(msh, plan)
    expected_plan_sha = payload.get("cell_degree_plan_sha256")
    if (
        expected_plan_sha is not None
        and expected_plan_sha
        != result.audit["cell_degree_plan_sha256"]
    ):
        raise ValueError("degree-plan content SHA is invalid")
    return result


def variable_p_cell_degree_plan_payload(
    msh: Any,
    cell_degree_by_box: Mapping[CellBoxKey, int],
    *,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a JSON-ready, hash-bound plan after full closure validation."""

    plan = build_variable_p_cell_degree_plan(
        msh,
        cell_degree_by_box,
    )
    boxes = cell_box_catalog(msh)
    return {
        "schema_version": "task035d.variable-p-cell-degree-plan.v1",
        "status": "geometry_bound_cell_degree_plan",
        "mesh_cell_box_catalog_sha256": plan.audit[
            "mesh_cell_box_catalog_sha256"
        ],
        "cell_degree_plan_sha256": plan.audit[
            "cell_degree_plan_sha256"
        ],
        "cells": [
            {
                "lower": list(box[:3]),
                "upper": list(box[3:]),
                "degree": int(plan.cell_degree_by_box[box]),
            }
            for box in boxes
        ],
        "closure_audit": dict(plan.audit),
        "provenance": dict(provenance),
        "ordinary_default_changed": False,
    }


__all__ = [
    "CellBoxKey",
    "VariablePCellDegreePlan",
    "build_variable_p_cell_degree_plan",
    "cell_box_catalog",
    "cell_box_catalog_sha256",
    "load_variable_p_cell_degree_plan",
    "variable_p_cell_degree_plan_payload",
]
