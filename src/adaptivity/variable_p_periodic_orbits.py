"""Geometry-bound Floquet orbit audit for variable-p trace entities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable

import numpy as np
from dolfinx import mesh as dmesh
from mpi4py import MPI

from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)

from .variable_p_entity_map import VariablePGlobalEntityMap


@dataclass(frozen=True)
class VariablePPeriodicRelation:
    """One physical master-to-slave trace relation."""

    dimension: int
    axis: str
    master_entity: int
    slave_entity: int
    degree: int
    vertex_permutation: tuple[int, ...]
    coefficient_transform: np.ndarray


def _quantized_point(
    point: np.ndarray,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[int, int, int]:
    return tuple(
        np.rint((np.asarray(point) - origin) / tolerance)
        .astype(np.int64)
        .tolist()
    )


def _matrix_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _entity_records(
    entity_map: VariablePGlobalEntityMap,
    *,
    dimension: int,
    origin: np.ndarray,
    tolerance: float,
) -> dict[int, dict[str, Any]]:
    msh = entity_map.mesh
    topology = msh.topology
    topology.create_connectivity(dimension, 0)
    topology.create_connectivity(dimension, 3)
    index_map = topology.index_map(dimension)
    owned = int(index_map.size_local)
    local_entities = np.arange(owned, dtype=np.int32)
    global_entities = np.asarray(
        index_map.local_to_global(local_entities),
        dtype=np.int64,
    )
    geometry_dofs = dmesh.entities_to_geometry(
        msh,
        dimension,
        local_entities,
        permute=True,
    )
    local_packet: list[dict[str, Any]] = []
    for local_entity, global_entity, dofs in zip(
        local_entities,
        global_entities,
        geometry_dofs,
        strict=True,
    ):
        points = np.asarray(msh.geometry.x[np.asarray(dofs), :3])
        ordered = tuple(
            _quantized_point(
                point,
                origin=origin,
                tolerance=tolerance,
            )
            for point in points
        )
        local_packet.append(
            {
                "global_entity": int(global_entity),
                "degree": int(
                    entity_map.global_degrees[dimension][global_entity]
                ),
                "ordered_points": ordered,
                "geometry_key": tuple(sorted(ordered)),
                "local_owner_rank": int(msh.comm.rank),
                "local_entity": int(local_entity),
            }
        )
    records: dict[int, dict[str, Any]] = {}
    for packet in msh.comm.allgather(tuple(local_packet)):
        for record in packet:
            global_entity = int(record["global_entity"])
            if global_entity in records:
                raise RuntimeError(
                    "periodic entity catalog contains duplicate owners"
                )
            records[global_entity] = record
    if len(records) != int(index_map.size_global):
        raise RuntimeError("periodic entity catalog is incomplete")
    return records


def _vertex_permutation(
    *,
    master_points: tuple[tuple[int, int, int], ...],
    slave_points: tuple[tuple[int, int, int], ...],
    axis: int,
    period_steps: int,
) -> tuple[int, ...]:
    translated: list[tuple[int, int, int]] = []
    for point in slave_points:
        values = list(point)
        values[axis] -= int(period_steps)
        translated.append(tuple(values))
    try:
        return tuple(master_points.index(point) for point in translated)
    except ValueError as exc:
        raise RuntimeError(
            "periodic entity vertex ordering cannot be matched"
        ) from exc


def _relation_transform(
    *,
    dimension: int,
    degree: int,
    permutation: tuple[int, ...],
    phase: complex,
) -> np.ndarray:
    if dimension == 1:
        if permutation not in {(0, 1), (1, 0)}:
            raise RuntimeError("periodic edge permutation is invalid")
        transform = edge_coefficient_transform(
            degree,
            reversed_orientation=permutation == (1, 0),
        )
    elif dimension == 2:
        transform = face_coefficient_transform(degree, permutation)
    else:
        raise ValueError("periodic H(curl) trace uses edges and faces only")
    return np.ascontiguousarray(complex(phase) * transform)


def _orbit_cycle_audit(
    nodes: Iterable[tuple[int, int]],
    relations: tuple[VariablePPeriodicRelation, ...],
) -> tuple[list[list[tuple[int, int]]], float]:
    parent = {node: node for node in nodes}

    def find(node: tuple[int, int]) -> tuple[int, int]:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: tuple[int, int], right: tuple[int, int]) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for relation in relations:
        union(
            (relation.dimension, relation.master_entity),
            (relation.dimension, relation.slave_entity),
        )
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    nontrivial = [
        sorted(group)
        for group in groups.values()
        if len(group) > 1
    ]

    adjacency: dict[
        tuple[int, int],
        list[tuple[tuple[int, int], np.ndarray]],
    ] = {node: [] for node in parent}
    for relation in relations:
        master = (relation.dimension, relation.master_entity)
        slave = (relation.dimension, relation.slave_entity)
        transform = np.asarray(relation.coefficient_transform)
        adjacency[master].append((slave, transform))
        adjacency[slave].append((master, np.linalg.inv(transform)))

    max_cycle_error = 0.0
    for orbit in nontrivial:
        root = orbit[0]
        mode_count = adjacency[root][0][1].shape[0]
        potentials = {root: np.eye(mode_count, dtype=np.complex128)}
        queue = [root]
        while queue:
            current = queue.pop(0)
            for neighbor, transform in adjacency[current]:
                candidate = transform @ potentials[current]
                if neighbor in potentials:
                    max_cycle_error = max(
                        max_cycle_error,
                        float(
                            np.max(
                                np.abs(candidate - potentials[neighbor]),
                                initial=0.0,
                            )
                        ),
                    )
                else:
                    potentials[neighbor] = candidate
                    queue.append(neighbor)
    return nontrivial, max_cycle_error


def audit_variable_p_periodic_orbits(
    entity_map: VariablePGlobalEntityMap,
    *,
    axes: tuple[str, ...],
    phase_x: complex = 1.0 + 0.0j,
    phase_y: complex = 1.0 + 0.0j,
    tolerance: float | None = None,
) -> dict[str, Any]:
    """Pair x/y boundary entities and close their variable-p Floquet orbits."""

    normalized_axes = tuple(dict.fromkeys(str(axis).lower() for axis in axes))
    if not normalized_axes or any(axis not in {"x", "y"} for axis in normalized_axes):
        raise ValueError("periodic axes must be a nonempty subset of x/y")
    msh = entity_map.mesh
    local_min = np.min(msh.geometry.x[:, :3], axis=0)
    local_max = np.max(msh.geometry.x[:, :3], axis=0)
    global_min = np.empty(3, dtype=np.float64)
    global_max = np.empty(3, dtype=np.float64)
    msh.comm.Allreduce(
        np.asarray(local_min, dtype=np.float64),
        global_min,
        op=MPI.MIN,
    )
    msh.comm.Allreduce(
        np.asarray(local_max, dtype=np.float64),
        global_max,
        op=MPI.MAX,
    )
    extent = global_max - global_min
    resolved_tolerance = (
        max(float(np.max(extent)), 1.0) * 1.0e-11
        if tolerance is None
        else float(tolerance)
    )
    if not np.isfinite(resolved_tolerance) or resolved_tolerance <= 0.0:
        raise ValueError("periodic geometry tolerance must be positive")
    period_steps = np.rint(extent / resolved_tolerance).astype(np.int64)
    axis_data = {
        "x": (0, complex(phase_x)),
        "y": (1, complex(phase_y)),
    }
    relations: list[VariablePPeriodicRelation] = []
    relation_records: list[dict[str, Any]] = []
    all_nodes: set[tuple[int, int]] = set()
    degree_mismatches: list[dict[str, Any]] = []
    for dimension in (1, 2):
        records = _entity_records(
            entity_map,
            dimension=dimension,
            origin=global_min,
            tolerance=resolved_tolerance,
        )
        by_key = {
            record["geometry_key"]: record for record in records.values()
        }
        if len(by_key) != len(records):
            raise RuntimeError("physical entity geometry keys are not unique")
        all_nodes.update((dimension, entity) for entity in records)
        for axis_name in normalized_axes:
            axis, phase = axis_data[axis_name]
            maximum_step = int(period_steps[axis])
            for slave in records.values():
                if not all(
                    point[axis] == maximum_step
                    for point in slave["ordered_points"]
                ):
                    continue
                target_key_values: list[tuple[int, int, int]] = []
                for point in slave["geometry_key"]:
                    values = list(point)
                    values[axis] -= maximum_step
                    target_key_values.append(tuple(values))
                target_key = tuple(sorted(target_key_values))
                master = by_key.get(target_key)
                if master is None:
                    raise RuntimeError(
                        "periodic boundary entity has no translated master"
                    )
                if int(master["degree"]) != int(slave["degree"]):
                    degree_mismatches.append(
                        {
                            "dimension": dimension,
                            "axis": axis_name,
                            "master": int(master["global_entity"]),
                            "slave": int(slave["global_entity"]),
                            "master_degree": int(master["degree"]),
                            "slave_degree": int(slave["degree"]),
                        }
                    )
                    continue
                permutation = _vertex_permutation(
                    master_points=master["ordered_points"],
                    slave_points=slave["ordered_points"],
                    axis=axis,
                    period_steps=maximum_step,
                )
                transform = _relation_transform(
                    dimension=dimension,
                    degree=int(master["degree"]),
                    permutation=permutation,
                    phase=phase,
                )
                relation = VariablePPeriodicRelation(
                    dimension=dimension,
                    axis=axis_name,
                    master_entity=int(master["global_entity"]),
                    slave_entity=int(slave["global_entity"]),
                    degree=int(master["degree"]),
                    vertex_permutation=permutation,
                    coefficient_transform=transform,
                )
                relations.append(relation)
                relation_records.append(
                    {
                        "dimension": dimension,
                        "axis": axis_name,
                        "master_entity": relation.master_entity,
                        "slave_entity": relation.slave_entity,
                        "degree": relation.degree,
                        "mode_count": int(transform.shape[0]),
                        "vertex_permutation": list(permutation),
                        "transform_condition_number": float(
                            np.linalg.cond(transform)
                        ),
                        "transform_sha256": _matrix_sha256(transform),
                    }
                )
    if degree_mismatches:
        raise RuntimeError(
            "periodic variable-p orbit degrees are not synchronized: "
            f"{degree_mismatches[:4]}"
        )
    relation_tuple = tuple(relations)
    orbits, cycle_error = _orbit_cycle_audit(all_nodes, relation_tuple)
    orbit_records: list[dict[str, Any]] = []
    removed_rows = 0
    relation_lookup = {
        (relation.dimension, relation.master_entity): relation
        for relation in relation_tuple
    }
    relation_lookup.update(
        {
            (relation.dimension, relation.slave_entity): relation
            for relation in relation_tuple
        }
    )
    for orbit in orbits:
        degrees = {
            int(
                entity_map.global_degrees[dimension][entity]
            )
            for dimension, entity in orbit
        }
        if len(degrees) != 1:
            raise RuntimeError("one periodic orbit contains mixed degrees")
        degree = degrees.pop()
        dimension = orbit[0][0]
        example = relation_lookup[orbit[0]]
        mode_count = int(example.coefficient_transform.shape[0])
        removed_rows += (len(orbit) - 1) * mode_count
        orbit_records.append(
            {
                "dimension": dimension,
                "degree": degree,
                "member_entities": [entity for _, entity in orbit],
                "member_count": len(orbit),
                "mode_count": mode_count,
            }
        )
    max_condition = max(
        (
            record["transform_condition_number"]
            for record in relation_records
        ),
        default=1.0,
    )
    checks = {
        "all_boundary_entities_paired": len(relations) > 0,
        "periodic_degrees_synchronized": True,
        "transforms_square_and_invertible": max_condition < 1.0e8,
        "double_periodic_cycles_close": cycle_error <= 2.0e-11,
        "orbit_rows_reduce_trace_numbering": removed_rows > 0,
    }
    passed = all(checks.values())
    return {
        "schema_version": "task035d.variable-p-periodic-orbits.v1",
        "status": (
            "variable_p_periodic_orbit_audit_pass"
            if passed
            else "variable_p_periodic_orbit_audit_fail"
        ),
        "pass": passed,
        "mpi_size": int(msh.comm.size),
        "axes": list(normalized_axes),
        "geometry_tolerance": resolved_tolerance,
        "relation_count": len(relations),
        "orbit_count": len(orbits),
        "edge_relation_count": sum(
            relation.dimension == 1 for relation in relations
        ),
        "face_relation_count": sum(
            relation.dimension == 2 for relation in relations
        ),
        "maximum_orbit_size": max(
            (len(orbit) for orbit in orbits),
            default=1,
        ),
        "cycle_closure_error_max": cycle_error,
        "transform_condition_number_max": max_condition,
        "active_trace_rows_before_periodic_elimination": (
            entity_map.active_trace_rows
        ),
        "periodic_slave_rows": int(removed_rows),
        "independent_periodic_trace_rows": int(
            entity_map.active_trace_rows - removed_rows
        ),
        "relations": relation_records,
        "orbits": orbit_records,
        "checks": checks,
        "inactive_p6_rows_globally_numbered": False,
        "ordinary_default_changed": False,
    }


__all__ = [
    "VariablePPeriodicRelation",
    "audit_variable_p_periodic_orbits",
]
