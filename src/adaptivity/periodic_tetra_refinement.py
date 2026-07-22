"""Periodic-mate closure and conforming marked tetra refinement for Task035."""

from __future__ import annotations

import hashlib
from itertools import combinations
from typing import Any

import numpy as np
import ufl
from basix.ufl import element

from dolfinx import default_real_type, mesh

from src.geometry.mesh_builder_3d import (
    AirBox3DMesh,
    rebuild_airbox_mesh_data_3d,
)
from src.geometry.tetra_mesh_audit import (
    audit_periodic_tetra_mesh,
    canonical_entity_key,
    geometry_key_sha256,
    mesh_coordinate_tolerance,
    owned_tetra_cell_geometry,
)


def _integer_bounds(cfg: Any, tolerance: float) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            int(round(minimum / tolerance)),
            int(round(maximum / tolerance)),
        )
        for minimum, maximum in (
            (cfg.x_min, cfg.x_max),
            (cfg.y_min, cfg.y_max),
        )
    )


def _id_sha256(global_cell_ids: list[int]) -> str:
    values = np.asarray(sorted(global_cell_ids), dtype="<i8")
    return hashlib.sha256(values.tobytes()).hexdigest()


def close_periodic_marked_cells(
    msh: mesh.Mesh,
    cfg: Any,
    marked_global_cell_ids: list[int] | np.ndarray,
) -> dict[str, Any]:
    """Add translated boundary-cell mates to a global marked-cell set.

    The returned global-id list is useful inside the current run. Geometry
    hashes, not DOLFINx numbering, are the partition-independent authority.
    """

    if msh.topology.cell_type != mesh.CellType.tetrahedron:
        raise ValueError("periodic marked-cell closure requires tetrahedra")
    comm = msh.comm
    tolerance = mesh_coordinate_tolerance(msh)
    local_records = owned_tetra_cell_geometry(msh, tolerance=tolerance)
    packets = comm.allgather(
        [(record.global_index, record.key) for record in local_records]
    )
    records = [record for packet in packets for record in packet]
    id_to_key = {global_index: key for global_index, key in records}
    key_to_id = {key: global_index for global_index, key in records}
    if len(id_to_key) != len(records) or len(key_to_id) != len(records):
        raise RuntimeError("global tetra cell identity is not one-to-one")

    integer_bounds = _integer_bounds(cfg, tolerance)
    boundary_faces_by_cell: dict[int, list[tuple[int, int, tuple[int, ...]]]] = {}
    incident_cell_by_face: dict[tuple[int, int, tuple[int, ...]], int] = {}
    for global_index, key in records:
        points = np.asarray(key, dtype=np.int64)
        for vertex_indices in combinations(range(4), 3):
            face = points[np.asarray(vertex_indices)]
            for axis, (minimum, maximum) in enumerate(integer_bounds):
                for side, boundary in enumerate((minimum, maximum)):
                    if not np.all(face[:, axis] == boundary):
                        continue
                    normalized = face.copy()
                    if side == 1:
                        normalized[:, axis] -= maximum - minimum
                    normalized_key = tuple(
                        component
                        for point in sorted(
                            tuple(int(value) for value in row)
                            for row in normalized
                        )
                        for component in point
                    )
                    face_identity = (axis, side, normalized_key)
                    if face_identity in incident_cell_by_face:
                        raise RuntimeError(
                            "periodic boundary face has multiple incident cells"
                        )
                    incident_cell_by_face[face_identity] = global_index
                    boundary_faces_by_cell.setdefault(global_index, []).append(
                        face_identity
                    )

    initial = {int(value) for value in marked_global_cell_ids}
    unknown = sorted(initial - set(id_to_key))
    if unknown:
        raise ValueError(f"marked global cells are absent from this mesh: {unknown}")
    closed = set(initial)
    missing_mates: list[dict[str, int]] = []
    changed = True
    while changed:
        changed = False
        for global_index in tuple(sorted(closed)):
            for axis, side, normalized_key in boundary_faces_by_cell.get(
                global_index, []
            ):
                mate = incident_cell_by_face.get((axis, 1 - side, normalized_key))
                if mate is None:
                    missing_mates.append(
                        {
                            "global_cell_id": global_index,
                            "axis": axis,
                            "side": side,
                        }
                    )
                elif mate not in closed:
                    closed.add(mate)
                    changed = True
    if missing_mates:
        raise RuntimeError(
            "periodic boundary cell has no translated tetra mate: "
            f"{missing_mates[:8]}"
        )
    initial_keys = [id_to_key[index] for index in sorted(initial)]
    closed_keys = [id_to_key[index] for index in sorted(closed)]
    added = closed - initial
    return {
        "schema_version": "task035.periodic-marked-cell-closure.v1",
        "status": "pass",
        "mpi_size": comm.size,
        "initial_count": len(initial),
        "closed_count": len(closed),
        "periodic_mates_added": len(added),
        "initial_global_cell_ids_sha256": _id_sha256(sorted(initial)),
        "closed_global_cell_ids_sha256": _id_sha256(sorted(closed)),
        "initial_geometry_sha256": geometry_key_sha256(initial_keys),
        "closed_geometry_sha256": geometry_key_sha256(closed_keys),
        "closed_global_cell_ids": sorted(closed),
        "partition_independent_identity": "canonical_quantized_cell_geometry",
    }


def _closed_periodic_edge_indices(
    msh: mesh.Mesh,
    cfg: Any,
    marked_owned_cells: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Close the actual refinement-edge set across both periodic axes."""

    tdim = msh.topology.dim
    msh.topology.create_entities(1)
    msh.topology.create_connectivity(tdim, 1)
    msh.topology.create_connectivity(1, tdim)
    initial_local_edges = mesh.compute_incident_entities(
        msh.topology, marked_owned_cells, tdim, 1
    )
    edge_map = msh.topology.index_map(1)
    all_local_edges = np.arange(
        edge_map.size_local + edge_map.num_ghosts, dtype=np.int32
    )
    edge_geometry = mesh.entities_to_geometry(msh, 1, all_local_edges, False)
    tolerance = mesh_coordinate_tolerance(msh)
    local_key_by_edge = {
        int(edge): canonical_entity_key(msh.geometry.x[indices], tolerance)
        for edge, indices in zip(all_local_edges, edge_geometry, strict=True)
    }
    initial_local_keys = {
        local_key_by_edge[int(edge)] for edge in initial_local_edges
    }
    initial_keys = {
        key
        for packet in msh.comm.allgather(initial_local_keys)
        for key in packet
    }
    owned_keys = {
        local_key_by_edge[int(edge)]
        for edge in range(edge_map.size_local)
    }
    global_edge_keys = {
        key for packet in msh.comm.allgather(owned_keys) for key in packet
    }
    integer_bounds = _integer_bounds(cfg, tolerance)
    closed_keys = set(initial_keys)
    missing: list[dict[str, int]] = []
    changed = True
    while changed:
        changed = False
        for key in tuple(sorted(closed_keys)):
            points = np.asarray(key, dtype=np.int64)
            for axis, (minimum, maximum) in enumerate(integer_bounds):
                for side, boundary in enumerate((minimum, maximum)):
                    if not np.all(points[:, axis] == boundary):
                        continue
                    mate_points = points.copy()
                    mate_points[:, axis] += (
                        maximum - minimum if side == 0 else minimum - maximum
                    )
                    mate_key = tuple(
                        sorted(
                            tuple(int(value) for value in point)
                            for point in mate_points
                        )
                    )
                    if mate_key not in global_edge_keys:
                        missing.append({"axis": axis, "side": side})
                    elif mate_key not in closed_keys:
                        closed_keys.add(mate_key)
                        changed = True
    if missing:
        raise RuntimeError(
            f"periodic refinement edge has no translated mate: {missing[:8]}"
        )
    local_closed_edges = np.asarray(
        [
            edge
            for edge in range(edge_map.size_local)
            if local_key_by_edge[edge] in closed_keys
        ],
        dtype=np.int32,
    )
    return local_closed_edges, {
        "schema_version": "task035.periodic-refinement-edge-closure.v1",
        "status": "pass",
        "initial_edge_count": len(initial_keys),
        "closed_edge_count": len(closed_keys),
        "periodic_edge_mates_added": len(closed_keys - initial_keys),
        "initial_geometry_sha256": geometry_key_sha256(initial_keys),
        "closed_geometry_sha256": geometry_key_sha256(closed_keys),
        "owned_closed_edge_counts_by_rank": msh.comm.allgather(
            int(len(local_closed_edges))
        ),
    }


def _positively_oriented_tetra_copy(
    msh: mesh.Mesh,
) -> tuple[mesh.Mesh, dict[str, Any]]:
    """Rebuild a refined mesh with an explicitly positive affine map per cell."""

    tolerance = mesh_coordinate_tolerance(msh)
    local_records = owned_tetra_cell_geometry(msh, tolerance=tolerance)
    packets = msh.comm.allgather(
        [(record.key, record.coordinates.tolist()) for record in local_records]
    )
    global_records = sorted(
        [record for packet in packets for record in packet], key=lambda item: item[0]
    )
    point_coordinates: dict[tuple[int, int, int], tuple[float, float, float]] = {}
    oriented_cells: list[list[tuple[int, int, int]]] = []
    negative_input_count = 0
    for _, coordinate_values in global_records:
        coordinates = np.asarray(coordinate_values, dtype=np.float64)
        determinant = float(
            np.linalg.det(
                np.column_stack(
                    (
                        coordinates[1] - coordinates[0],
                        coordinates[2] - coordinates[0],
                        coordinates[3] - coordinates[0],
                    )
                )
            )
        )
        if determinant < 0.0:
            coordinates[[1, 2]] = coordinates[[2, 1]]
            negative_input_count += 1
        keys = [
            tuple(int(value) for value in np.rint(point / tolerance))
            for point in coordinates
        ]
        for key, point in zip(keys, coordinates, strict=True):
            value = tuple(float(component) for component in point)
            previous = point_coordinates.get(key)
            if previous is not None and not np.allclose(
                previous, value, atol=tolerance, rtol=0.0
            ):
                raise RuntimeError("quantized refined vertices are not unique")
            if previous is None or value < previous:
                point_coordinates[key] = value
        oriented_cells.append(keys)
    point_keys = sorted(point_coordinates)
    point_index = {key: index for index, key in enumerate(point_keys)}
    points = np.asarray(
        [point_coordinates[key] for key in point_keys], dtype=default_real_type
    )
    start = len(oriented_cells) * msh.comm.rank // msh.comm.size
    stop = len(oriented_cells) * (msh.comm.rank + 1) // msh.comm.size
    local_cells = np.asarray(
        [
            [point_index[key] for key in oriented_cells[index]]
            for index in range(start, stop)
        ],
        dtype=np.int64,
    ).reshape(-1, 4)
    coordinate_element = element(
        "Lagrange", "tetrahedron", 1, shape=(3,), dtype=default_real_type
    )
    domain = ufl.Mesh(coordinate_element)
    partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    rebuilt = mesh.create_mesh(
        msh.comm, local_cells, domain, points, partitioner=partitioner
    )
    return rebuilt, {
        "input_negative_oriented_cell_count": negative_input_count,
        "reconstructed_global_cell_count": len(oriented_cells),
        "coordinate_tolerance": tolerance,
    }


def refine_periodic_marked_tetra_mesh(
    mesh_data: AirBox3DMesh,
    cfg: Any,
    marked_global_cell_ids: list[int] | np.ndarray,
) -> tuple[AirBox3DMesh, dict[str, Any]]:
    """Refine a Dörfler cell set after fail-closed periodic-mate expansion."""

    msh = mesh_data.mesh
    closure = close_periodic_marked_cells(msh, cfg, marked_global_cell_ids)
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    closed_ids = np.asarray(
        closure["closed_global_cell_ids"], dtype=np.int64
    )
    local_cells = cell_map.global_to_local(closed_ids)
    owned_cells = np.unique(
        local_cells[(local_cells >= 0) & (local_cells < cell_map.size_local)]
    ).astype(np.int32)
    edges, edge_closure = _closed_periodic_edge_indices(
        msh, cfg, owned_cells
    )
    refined_mesh, parent_cells, _ = mesh.refine(msh, edges)
    oriented_mesh, orientation_rebuild = _positively_oriented_tetra_copy(refined_mesh)
    rebuilt = rebuild_airbox_mesh_data_3d(oriented_mesh, cfg, mesh_data)
    audit = audit_periodic_tetra_mesh(
        rebuilt.mesh, rebuilt.cell_tags, rebuilt.facet_tags, cfg
    )
    local_edge_count = int(len(edges))
    refined_count = int(refined_mesh.topology.index_map(tdim).size_global)
    passed = (
        closure["status"] == "pass"
        and len(closure["closed_global_cell_ids"]) > 0
        and refined_count > int(cell_map.size_global)
        and audit["pass"]
    )
    report = {
        "schema_version": "task035.periodic-marked-tetra-refinement.v1",
        "status": "pass" if passed else "fail",
        "mpi_size": msh.comm.size,
        "parent_global_cells": int(cell_map.size_global),
        "refined_global_cells": refined_count,
        "locally_owned_marked_cells_by_rank": msh.comm.allgather(
            int(len(owned_cells))
        ),
        "incident_edge_counts_by_rank": msh.comm.allgather(local_edge_count),
        "parent_cell_map_entries_by_rank": msh.comm.allgather(
            int(len(parent_cells))
        ),
        "periodic_closure": closure,
        "periodic_edge_closure": edge_closure,
        "orientation_rebuild": orientation_rebuild,
        "refined_mesh_audit": audit,
        "pass": passed,
    }
    return rebuilt, report


__all__ = [
    "close_periodic_marked_cells",
    "refine_periodic_marked_tetra_mesh",
]
