from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import numpy as np
from mpi4py import MPI

from dolfinx import cpp, mesh

from ..common.config_3d import SimulationConfig3D


@dataclass
class DoubleFloquet3DData:
    """Bookkeeping returned by the low-level 3D H(curl) Floquet builder."""

    mpc: Any
    local_slave_dofs: np.ndarray
    num_local_slaves: int
    num_local_slave_records_seen: int
    num_local_ghost_slave_constraints: int
    num_global_ghost_slave_constraints: int
    num_local_ghost_slave_records_skipped: int
    num_global_ghost_slave_records_skipped: int
    constraint_mode_resolved: str
    phase_x: complex
    phase_y: complex
    phase_corner: complex
    max_face_pairing_coordinate_error: float
    edge_corner_phase_mismatch: float
    orientation_factor_stats: dict[str, object]
    timings_seconds: dict[str, float]
    raw_map_nnz: int
    max_masters_per_slave: int
    estimated_constraint_memory_mb: float
    num_slave_edges: int
    num_matched_master_edges: int
    num_constraints: int
    max_edge_midpoint_pairing_error: float
    num_x_constraints: int
    num_y_constraints: int
    num_corner_constraints: int
    num_slave_faces: int = 0
    num_matched_master_faces: int = 0
    num_edge_constraints: int = 0
    num_face_constraints: int = 0
    max_face_midpoint_pairing_error: float = 0.0


def _mesh_is_hexahedron(msh) -> bool:
    return "hexahedron" in str(msh.basix_cell()).lower()


def _resolve_constraint_mode(V, cfg: SimulationConfig3D) -> str:
    requested = cfg.floquet_constraint_mode_requested
    degree = int(cfg.nedelec_degree)
    if requested in {"topological_edges", "sparse_facet"}:
        requested = "topological_edges_p1"
    if requested == "auto":
        if degree == 1:
            return "topological_edges_p1"
        if degree == 2:
            return "topological_trace_p2"
        raise NotImplementedError(
            "3D explicit Floquet high-order constraints currently support only degree=1 or degree=2 "
            f"N1curl on hexahedra. Requested degree={cfg.nedelec_degree}."
        )
    if requested == "topological_edges_p1":
        if degree != 1:
            raise NotImplementedError("floquet_constraint_mode='topological_edges_p1' requires nedelec_degree=1.")
        return requested
    if requested == "topological_trace_p2":
        if degree != 2:
            raise NotImplementedError("floquet_constraint_mode='topological_trace_p2' requires nedelec_degree=2.")
        return requested
    raise RuntimeError(
        "3D Floquet dense probe/pseudo-inverse constraint construction is disabled. "
        "Use floquet_constraint_mode='auto', 'topological_edges_p1', or 'topological_trace_p2'."
    )


def _require_supported_topological_edges(V, cfg: SimulationConfig3D) -> None:
    if int(cfg.nedelec_degree) != 1:
        raise NotImplementedError(
            "3D explicit Floquet edge topology constraints currently support only degree=1 N1curl. "
            f"Requested degree={cfg.nedelec_degree}."
        )


def _require_supported_topological_trace_p2(V, cfg: SimulationConfig3D) -> None:
    if int(cfg.nedelec_degree) != 2:
        raise NotImplementedError(
            "3D explicit high-order Floquet trace constraints currently support only degree=2 N1curl. "
            f"Requested degree={cfg.nedelec_degree}."
        )
    allowed_stage_cases = {"floquet_airbox", "pml_airbox", "fresnel_interface"}
    if cfg.stage_case not in allowed_stage_cases:
        raise NotImplementedError(
            "The high-order 3D Floquet trace implementation is currently enabled only for "
            "Stage 2A/2B/2C: stage_case in "
            f"{sorted(allowed_stage_cases)!r}. Stage 4 will be enabled after p=2 Stage 2 validation."
        )
    if not _mesh_is_hexahedron(V.mesh):
        raise NotImplementedError("3D high-order Floquet trace constraints require a hexahedron mesh.")
    edge_entity_dofs = V.element.basix_element.entity_dofs[1]
    face_entity_dofs = V.element.basix_element.entity_dofs[2]
    if any(len(dofs) != 2 for dofs in edge_entity_dofs):
        raise NotImplementedError("Expected exactly two N1curl p=2 dofs on every hexahedron edge.")
    if any(len(dofs) != 4 for dofs in face_entity_dofs):
        raise NotImplementedError("Expected exactly four N1curl p=2 interior dofs on every hexahedron face.")


def _geometry_tolerance(cfg: SimulationConfig3D) -> float:
    span = max(
        abs(cfg.x_max - cfg.x_min),
        abs(cfg.y_max - cfg.y_min),
        abs(cfg.domain_z_max - cfg.domain_z_min),
        1.0,
    )
    return max(1.0e-8, 1.0e-10 * span)


def _edge_match_key(point: np.ndarray, tangent: np.ndarray, tol: float) -> tuple[int, int, int, int]:
    dominant_axis = int(np.argmax(np.abs(tangent)))
    return (
        int(round(float(point[0]) / tol)),
        int(round(float(point[1]) / tol)),
        int(round(float(point[2]) / tol)),
        dominant_axis,
    )


def _face_match_key(point: np.ndarray, normal_axis: int, tol: float) -> tuple[int, int, int, int]:
    return (
        int(round(float(point[0]) / tol)),
        int(round(float(point[1]) / tol)),
        int(round(float(point[2]) / tol)),
        int(normal_axis),
    )


def _local_dof_global_info(V, dofs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index_map = V.dofmap.index_map
    bs = V.dofmap.index_map_bs
    comm = V.mesh.comm
    dofs = np.asarray(dofs, dtype=np.int64)
    blocks = dofs // bs
    components = dofs % bs
    global_blocks = index_map.local_to_global(blocks.astype(np.int32)).astype(np.int64)
    global_dofs = global_blocks * bs + components
    owned = blocks < index_map.size_local
    owners = np.empty(len(dofs), dtype=np.int32)
    owners[owned] = comm.rank
    if np.any(~owned):
        ghost_owners = np.asarray(index_map.owners, dtype=np.int32)
        owners[~owned] = ghost_owners[blocks[~owned] - index_map.size_local]
    return global_dofs.astype(np.int64), owners, owned


def _build_edge_dof_map_p1(V) -> dict[int, dict[str, object]]:
    """Map each local mesh edge to its single degree-1 N1curl dof."""

    msh = V.mesh
    tdim = msh.topology.dim
    msh.topology.create_connectivity(tdim, 1)
    msh.topology.create_connectivity(1, tdim)
    cell_to_edge = msh.topology.connectivity(tdim, 1)
    cell_map = msh.topology.index_map(tdim)
    num_cells = cell_map.size_local + cell_map.num_ghosts
    edge_entity_dofs = [V.dofmap.dof_layout.entity_dofs(1, i) for i in range(12)]

    edge_dof_map: dict[int, dict[str, object]] = {}
    for cell in range(num_cells):
        cell_is_owned = cell < cell_map.size_local
        cell_edges = cell_to_edge.links(cell)
        cell_dofs = V.dofmap.cell_dofs(cell)
        if len(cell_edges) != len(edge_entity_dofs):
            raise RuntimeError(
                f"Expected {len(edge_entity_dofs)} reference hexahedron edges, "
                f"but local cell {cell} reports {len(cell_edges)} edges."
            )
        for local_edge, edge in enumerate(cell_edges):
            local_entity_dofs = edge_entity_dofs[local_edge]
            if len(local_entity_dofs) != 1:
                raise NotImplementedError("Only one edge dof per N1curl edge is supported.")
            local_dof = int(cell_dofs[int(local_entity_dofs[0])])
            global_dof, owner, owned = _local_dof_global_info(
                V, np.asarray([local_dof], dtype=np.int32)
            )
            record = {
                "edge": int(edge),
                "local_dof": local_dof,
                "global_dof": int(global_dof[0]),
                "owner": int(owner[0]),
                "owned": bool(owned[0]),
                "touches_owned_cell": bool(cell_is_owned),
            }
            current = edge_dof_map.get(int(edge))
            if current is not None and int(current["global_dof"]) != int(record["global_dof"]):
                raise RuntimeError(
                    "Inconsistent N1curl dof assignment for mesh edge "
                    f"{int(edge)}: {current['global_dof']} vs {record['global_dof']}."
                )
            if current is None:
                edge_dof_map[int(edge)] = record
            else:
                record["touches_owned_cell"] = bool(record["touches_owned_cell"]) or bool(
                    current.get("touches_owned_cell", False)
                )
                if bool(record["owned"]) and not bool(current["owned"]):
                    edge_dof_map[int(edge)] = record
                else:
                    current["touches_owned_cell"] = bool(current.get("touches_owned_cell", False)) or bool(
                        record["touches_owned_cell"]
                    )
    return edge_dof_map


def _build_entity_dof_map(V, entity_dim: int, expected_entity_dofs: int) -> dict[int, dict[str, object]]:
    """Map mesh entities to their N1curl dofs for one topological dimension."""

    msh = V.mesh
    tdim = msh.topology.dim
    msh.topology.create_connectivity(tdim, entity_dim)
    msh.topology.create_connectivity(entity_dim, tdim)
    cell_to_entity = msh.topology.connectivity(tdim, entity_dim)
    cell_map = msh.topology.index_map(tdim)
    num_cells = cell_map.size_local + cell_map.num_ghosts
    local_entity_count = {1: 12, 2: 6}[entity_dim]
    entity_dofs = [V.dofmap.dof_layout.entity_dofs(entity_dim, i) for i in range(local_entity_count)]

    entity_dof_map: dict[int, dict[str, object]] = {}
    for cell in range(num_cells):
        cell_is_owned = cell < cell_map.size_local
        cell_entities = cell_to_entity.links(cell)
        cell_dofs = V.dofmap.cell_dofs(cell)
        if len(cell_entities) != local_entity_count:
            raise RuntimeError(
                f"Expected {local_entity_count} reference hexahedron entities of dim={entity_dim}, "
                f"but local cell {cell} reports {len(cell_entities)}."
            )
        for local_entity, entity in enumerate(cell_entities):
            local_entity_dofs = np.asarray(entity_dofs[local_entity], dtype=np.int32)
            if len(local_entity_dofs) != expected_entity_dofs:
                raise NotImplementedError(
                    f"Expected {expected_entity_dofs} N1curl dofs on entity dim={entity_dim}, "
                    f"local entity={local_entity}; found {len(local_entity_dofs)}."
                )
            local_dofs = np.asarray([int(cell_dofs[int(i)]) for i in local_entity_dofs], dtype=np.int32)
            global_dofs, owners, owned = _local_dof_global_info(V, local_dofs)
            record = {
                "entity": int(entity),
                "local_entity": int(local_entity),
                "local_dofs": local_dofs,
                "global_dofs": global_dofs.astype(np.int64),
                "owners": owners.astype(np.int32),
                "owned": owned.astype(bool),
                "touches_owned_cell": bool(cell_is_owned),
            }
            current = entity_dof_map.get(int(entity))
            if current is not None and not np.array_equal(current["global_dofs"], record["global_dofs"]):
                raise RuntimeError(
                    f"Inconsistent N1curl dof assignment for mesh entity dim={entity_dim}, id={int(entity)}."
                )
            if current is None:
                entity_dof_map[int(entity)] = record
            else:
                current["touches_owned_cell"] = bool(current.get("touches_owned_cell", False)) or bool(
                    record["touches_owned_cell"]
                )
                # Prefer a record that owns at least one dof, but keep the
                # first record if ownership is the same.  Boundary entities
                # should have consistent global dof arrays across adjacent
                # local/ghost cells.
                if bool(np.any(record["owned"])) and not bool(np.any(current["owned"])):
                    record["touches_owned_cell"] = bool(record["touches_owned_cell"]) or bool(
                        current.get("touches_owned_cell", False)
                    )
                    entity_dof_map[int(entity)] = record
    return entity_dof_map


def _periodic_boundary_edges(mesh_data, cfg: SimulationConfig3D) -> np.ndarray:
    msh = mesh_data.mesh
    fdim = msh.topology.dim - 1
    msh.topology.create_connectivity(fdim, 1)
    facet_to_edge = msh.topology.connectivity(fdim, 1)
    facets: list[int] = []
    for tag in (cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max):
        facets.extend(int(value) for value in np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32))
    if not facets:
        return np.asarray([], dtype=np.int32)
    edges = np.unique(
        np.concatenate([facet_to_edge.links(int(facet)) for facet in facets]).astype(np.int32)
    )
    return edges.astype(np.int32)


def _periodic_boundary_faces(mesh_data, cfg: SimulationConfig3D) -> np.ndarray:
    faces: list[int] = []
    for tag in (cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max):
        faces.extend(int(value) for value in np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32))
    return np.unique(np.asarray(faces, dtype=np.int32)).astype(np.int32)


def _merge_edge_records(
    gathered: list[dict[tuple[int, int, int, int], dict[str, object]]]
) -> dict[tuple[int, int, int, int], dict[str, object]]:
    merged: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for records in gathered:
        for key, record in records.items():
            current = merged.get(key)
            if current is not None and int(current["global_dof"]) != int(record["global_dof"]):
                raise RuntimeError(
                    "Periodic face mesh is not one-to-one at edge key "
                    f"{key}: global dofs {current['global_dof']} and {record['global_dof']} collide."
                )
            if current is None:
                merged[key] = record
            elif bool(record["owned"]) and not bool(current["owned"]):
                merged[key] = record
            elif bool(record["owned"]) == bool(current["owned"]) and int(record["rank"]) < int(current["rank"]):
                merged[key] = record
    return merged


def _merge_entity_records(
    gathered: list[dict[tuple[int, int, int, int], dict[str, object]]],
    *,
    dof_key: str,
) -> dict[tuple[int, int, int, int], dict[str, object]]:
    merged: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for records in gathered:
        for key, record in records.items():
            current = merged.get(key)
            if current is not None and not np.array_equal(current[dof_key], record[dof_key]):
                raise RuntimeError(
                    "Periodic face mesh is not one-to-one at entity key "
                    f"{key}: global dofs {current[dof_key]} and {record[dof_key]} collide."
                )
            if current is None:
                merged[key] = record
            elif bool(np.any(record.get("owned", False))) and not bool(np.any(current.get("owned", False))):
                merged[key] = record
            elif bool(np.any(record.get("owned", False))) == bool(np.any(current.get("owned", False))) and int(
                record["rank"]
            ) < int(current["rank"]):
                merged[key] = record
    return merged


def _build_topological_edge_context(V, mesh_data, cfg: SimulationConfig3D) -> dict[str, object]:
    """Collect all local periodic boundary edge records and globally keyed masters."""

    _require_supported_topological_edges(V, cfg)
    msh = mesh_data.mesh
    comm = msh.comm
    tol = _geometry_tolerance(cfg)
    periodic_edges = _periodic_boundary_edges(mesh_data, cfg)
    if len(periodic_edges) == 0:
        raise RuntimeError("No periodic x/y boundary edges were found for 3D Floquet constraints.")
    edge_dof_map = _build_edge_dof_map_p1(V)

    msh.topology.create_connectivity(1, 0)
    midpoints = mesh.compute_midpoints(msh, 1, periodic_edges)
    # ``permute=True`` returns geometry dofs in the oriented entity order used
    # by DOLFINx.  For Nedelec constraints the sign must follow this topological
    # edge orientation, not an arbitrary unpermuted geometry ordering.
    msh.topology.create_entity_permutations()
    edge_geometry = cpp.mesh.entities_to_geometry(msh._cpp_object, 1, periodic_edges, True)

    local_records: list[dict[str, object]] = []
    local_by_key: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for edge, midpoint, geometry_dofs in zip(periodic_edges, midpoints, edge_geometry):
        edge_info = edge_dof_map.get(int(edge))
        if edge_info is None:
            raise RuntimeError(f"No degree-1 N1curl edge dof was found for periodic mesh edge {int(edge)}.")
        geometry_dofs = np.asarray(geometry_dofs, dtype=np.int64)
        if len(geometry_dofs) < 2:
            raise RuntimeError(f"Mesh edge {int(edge)} does not expose two geometry points.")
        tangent = np.asarray(
            msh.geometry.x[int(geometry_dofs[1])] - msh.geometry.x[int(geometry_dofs[0])],
            dtype=np.float64,
        )
        if float(np.linalg.norm(tangent)) <= 1.0e-30:
            raise RuntimeError(f"Mesh edge {int(edge)} has near-zero geometric tangent.")
        midpoint = np.asarray(midpoint, dtype=np.float64)
        key = _edge_match_key(midpoint, tangent, tol)
        record = {
            "rank": comm.rank,
            "edge": int(edge),
            "midpoint": midpoint,
            "tangent": tangent,
            "local_dof": int(edge_info["local_dof"]),
            "global_dof": int(edge_info["global_dof"]),
            "owner": int(edge_info["owner"]),
            "owned": bool(edge_info["owned"]),
            "touches_owned_cell": bool(edge_info.get("touches_owned_cell", False)),
            "key": key,
        }
        current = local_by_key.get(key)
        if current is not None and int(current["global_dof"]) != int(record["global_dof"]):
            raise RuntimeError(
                "Two different local periodic boundary edges share the same rounded midpoint/direction key "
                f"{key}: global dofs {current['global_dof']} and {record['global_dof']}."
            )
        local_by_key[key] = record
        local_records.append(record)

    global_by_key = _merge_edge_records(comm.allgather(local_by_key))
    return {
        "local_records": local_records,
        "global_by_key": global_by_key,
        "tol": tol,
    }


def _build_topological_trace_context_p2(V, mesh_data, cfg: SimulationConfig3D) -> dict[str, object]:
    """Collect p=2 edge and face-interior trace records on periodic boundaries."""

    _require_supported_topological_trace_p2(V, cfg)
    msh = mesh_data.mesh
    comm = msh.comm
    tol = _geometry_tolerance(cfg)

    periodic_edges = _periodic_boundary_edges(mesh_data, cfg)
    periodic_faces = _periodic_boundary_faces(mesh_data, cfg)
    if len(periodic_edges) == 0 or len(periodic_faces) == 0:
        raise RuntimeError("No periodic x/y boundary edge or face entities were found for p=2 Floquet constraints.")

    edge_dof_map = _build_entity_dof_map(V, 1, 2)
    face_dof_map = _build_entity_dof_map(V, 2, 4)

    msh.topology.create_connectivity(1, 0)
    msh.topology.create_connectivity(2, 0)
    msh.topology.create_entity_permutations()

    edge_midpoints = mesh.compute_midpoints(msh, 1, periodic_edges)
    edge_geometry = cpp.mesh.entities_to_geometry(msh._cpp_object, 1, periodic_edges, True)
    edge_records: list[dict[str, object]] = []
    edge_by_key: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for edge, midpoint, geometry_dofs in zip(periodic_edges, edge_midpoints, edge_geometry):
        edge_info = edge_dof_map.get(int(edge))
        if edge_info is None:
            raise RuntimeError(f"No p=2 N1curl edge dofs were found for periodic mesh edge {int(edge)}.")
        geometry_dofs = np.asarray(geometry_dofs, dtype=np.int64)
        tangent = np.asarray(
            msh.geometry.x[int(geometry_dofs[1])] - msh.geometry.x[int(geometry_dofs[0])],
            dtype=np.float64,
        )
        midpoint = np.asarray(midpoint, dtype=np.float64)
        key = _edge_match_key(midpoint, tangent, tol)
        record = {
            "rank": comm.rank,
            "edge": int(edge),
            "midpoint": midpoint,
            "tangent": tangent,
            "local_dofs": np.asarray(edge_info["local_dofs"], dtype=np.int32),
            "global_dofs": np.asarray(edge_info["global_dofs"], dtype=np.int64),
            "owners": np.asarray(edge_info["owners"], dtype=np.int32),
            "owned": np.asarray(edge_info["owned"], dtype=bool),
            "touches_owned_cell": bool(edge_info.get("touches_owned_cell", False)),
            "key": key,
        }
        current = edge_by_key.get(key)
        if current is not None and not np.array_equal(current["global_dofs"], record["global_dofs"]):
            raise RuntimeError(
                "Two different local periodic boundary p=2 edges share the same rounded key "
                f"{key}: global dofs {current['global_dofs']} and {record['global_dofs']}."
            )
        edge_by_key[key] = record
        edge_records.append(record)

    face_midpoints = mesh.compute_midpoints(msh, 2, periodic_faces)
    face_geometry = cpp.mesh.entities_to_geometry(msh._cpp_object, 2, periodic_faces, True)
    face_records: list[dict[str, object]] = []
    face_by_key: dict[tuple[int, int, int, int], dict[str, object]] = {}
    for face, midpoint, geometry_dofs in zip(periodic_faces, face_midpoints, face_geometry):
        face_info = face_dof_map.get(int(face))
        if face_info is None:
            raise RuntimeError(f"No p=2 N1curl face-interior dofs were found for periodic mesh face {int(face)}.")
        geometry_dofs = np.asarray(geometry_dofs, dtype=np.int64)
        coords = np.asarray(msh.geometry.x[geometry_dofs], dtype=np.float64)
        if coords.shape[0] < 4:
            raise RuntimeError(f"Periodic mesh face {int(face)} does not expose four geometry points.")
        tangent0 = coords[1] - coords[0]
        tangent1 = coords[2] - coords[0]
        normal = np.cross(tangent0, tangent1)
        normal_axis = int(np.argmax(np.abs(normal)))
        midpoint = np.asarray(midpoint, dtype=np.float64)
        key = _face_match_key(midpoint, normal_axis, tol)
        record = {
            "rank": comm.rank,
            "face": int(face),
            "midpoint": midpoint,
            "normal": normal,
            "normal_axis": normal_axis,
            "geometry_coords": coords,
            "local_dofs": np.asarray(face_info["local_dofs"], dtype=np.int32),
            "global_dofs": np.asarray(face_info["global_dofs"], dtype=np.int64),
            "owners": np.asarray(face_info["owners"], dtype=np.int32),
            "owned": np.asarray(face_info["owned"], dtype=bool),
            "touches_owned_cell": bool(face_info.get("touches_owned_cell", False)),
            "key": key,
        }
        current = face_by_key.get(key)
        if current is not None and not np.array_equal(current["global_dofs"], record["global_dofs"]):
            raise RuntimeError(
                "Two different local periodic boundary p=2 faces share the same rounded key "
                f"{key}: global dofs {current['global_dofs']} and {record['global_dofs']}."
            )
        face_by_key[key] = record
        face_records.append(record)

    return {
        "edge_records": edge_records,
        "edge_global_by_key": _merge_entity_records(comm.allgather(edge_by_key), dof_key="global_dofs"),
        "face_records": face_records,
        "face_global_by_key": _merge_entity_records(comm.allgather(face_by_key), dof_key="global_dofs"),
        "tol": tol,
        "basix_interval_transform": np.asarray(
            V.element.basix_element.entity_transformations()["interval"][0], dtype=np.complex128
        ),
        "basix_quadrilateral_transforms": np.asarray(
            V.element.basix_element.entity_transformations()["quadrilateral"], dtype=np.complex128
        ),
    }


def _edge_boundary_flags(point: np.ndarray, cfg: SimulationConfig3D, tol: float) -> dict[str, bool]:
    return {
        "x_min": abs(float(point[0]) - cfg.x_min) <= tol,
        "x_max": abs(float(point[0]) - cfg.x_max) <= tol,
        "y_min": abs(float(point[1]) - cfg.y_min) <= tol,
        "y_max": abs(float(point[1]) - cfg.y_max) <= tol,
    }


def _target_for_kind(
    record: dict[str, object], cfg: SimulationConfig3D, kind: str
) -> tuple[np.ndarray, complex]:
    midpoint = np.asarray(record["midpoint"], dtype=np.float64)
    target = midpoint.copy()
    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)
    if kind == "x":
        target[0] -= cfg.x_max - cfg.x_min
        return target, phase_x
    if kind == "y":
        target[1] -= cfg.y_max - cfg.y_min
        return target, phase_y
    if kind == "corner":
        target[0] -= cfg.x_max - cfg.x_min
        target[1] -= cfg.y_max - cfg.y_min
        return target, phase_x * phase_y
    raise ValueError("kind must be 'x', 'y', or 'corner'.")


def _record_is_slave_kind(record: dict[str, object], cfg: SimulationConfig3D, tol: float, kind: str) -> bool:
    flags = _edge_boundary_flags(np.asarray(record["midpoint"], dtype=np.float64), cfg, tol)
    if kind == "corner":
        return flags["x_max"] and flags["y_max"]
    if kind == "x":
        return flags["x_max"] and not flags["y_max"]
    if kind == "y":
        return flags["y_max"] and not flags["x_max"]
    raise ValueError("kind must be 'x', 'y', or 'corner'.")


def _nearest_edge_error(
    point: np.ndarray,
    tangent: np.ndarray,
    global_by_key: dict[tuple[int, int, int, int], dict[str, object]],
) -> float | None:
    if not global_by_key:
        return None
    dominant = int(np.argmax(np.abs(tangent)))
    errors = [
        float(np.linalg.norm(point - np.asarray(record["midpoint"], dtype=np.float64)))
        for key, record in global_by_key.items()
        if int(key[3]) == dominant
    ]
    return min(errors) if errors else None


def _nearest_face_error(
    point: np.ndarray,
    normal_axis: int,
    global_by_key: dict[tuple[int, int, int, int], dict[str, object]],
) -> float | None:
    if not global_by_key:
        return None
    errors = [
        float(np.linalg.norm(point - np.asarray(record["midpoint"], dtype=np.float64)))
        for key, record in global_by_key.items()
        if int(key[3]) == int(normal_axis)
    ]
    return min(errors) if errors else None


def _record_is_face_slave_kind(record: dict[str, object], cfg: SimulationConfig3D, tol: float, kind: str) -> bool:
    flags = _edge_boundary_flags(np.asarray(record["midpoint"], dtype=np.float64), cfg, tol)
    if kind == "x":
        return flags["x_max"]
    if kind == "y":
        return flags["y_max"]
    raise ValueError("p=2 face-interior dofs support only kind='x' or kind='y'.")


def _nonzero_terms(
    master_globals: np.ndarray,
    master_owners: np.ndarray,
    coeffs: np.ndarray,
    *,
    tol: float = 1.0e-14,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = np.abs(coeffs) > tol
    if not np.any(mask):
        raise RuntimeError("A 3D Floquet local block row has no nonzero master coefficients.")
    return (
        np.asarray(master_globals[mask], dtype=np.int64),
        np.asarray(master_owners[mask], dtype=np.int32),
        np.asarray(coeffs[mask], dtype=np.complex128),
    )


def _emit_block_constraint_rows(
    *,
    record: dict[str, object],
    master: dict[str, object],
    transform: np.ndarray,
    phase: complex,
    kind: str,
    entity_label: str,
    owned_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]],
) -> tuple[int, int, list[complex]]:
    """Emit one local block of H(curl) Floquet constraints.

    For p=2 edges this is usually a 2x2 local block.  For p=2 face-interior
    dofs it is a 4x4 block.  Only owned slave dofs emit global constraints;
    p=2 deliberately emits only owned slave dofs into the local MPC map.  This
    avoids giving dolfinx_mpc the same global high-order trace slave from more
    than one rank, which otherwise changes nonzero-RHS parallel solves on some
    dolfinx_mpc/PETSc builds.  Ghost slave rows are still counted for diagnostics.
    """

    slave_globals = np.asarray(record["global_dofs"], dtype=np.int64)
    slave_locals = np.asarray(record["local_dofs"], dtype=np.int32)
    slave_owned = np.asarray(record["owned"], dtype=bool)
    master_globals = np.asarray(master["global_dofs"], dtype=np.int64)
    master_owners = np.asarray(master["owners"], dtype=np.int32)
    transform = np.asarray(transform, dtype=np.complex128)
    if transform.shape != (len(slave_globals), len(master_globals)):
        raise RuntimeError(
            f"Invalid {entity_label} Floquet transform shape {transform.shape}; "
            f"expected {(len(slave_globals), len(master_globals))}."
        )

    ghost_rows_for_owned_cells = 0
    ghost_rows_skipped = 0
    coefficients_seen: list[complex] = []
    for row, (slave_global, slave_local, is_owned) in enumerate(
        zip(slave_globals, slave_locals, slave_owned)
    ):
        masters, owners, coeffs = _nonzero_terms(
            master_globals,
            master_owners,
            phase * transform[row, :],
        )
        coefficients_seen.extend(complex(value) for value in coeffs)
        slave_global = int(slave_global)
        slave_local = int(slave_local)
        terms = (masters, owners, coeffs)
        if bool(is_owned):
            if slave_local in local_maps:
                raise RuntimeError(
                    f"Owned local 3D Floquet {entity_label} slave dof {slave_local} "
                    f"would be constrained twice in kind={kind}."
                )
            if slave_global in owned_raw_maps:
                raise RuntimeError(
                    f"3D Floquet {entity_label} slave dof {slave_global} "
                    f"would be constrained twice in kind={kind}."
                )
            owned_raw_maps[slave_global] = terms
            local_maps[slave_local] = (slave_global, *terms)
        elif bool(record.get("touches_owned_cell", False)):
            ghost_rows_for_owned_cells += 1
        else:
            ghost_rows_skipped += 1
    return ghost_rows_for_owned_cells, ghost_rows_skipped, coefficients_seen


def _edge_transform_p2(context: dict[str, object], record: dict[str, object], master: dict[str, object]) -> np.ndarray:
    tangent = np.asarray(record["tangent"], dtype=np.float64)
    master_tangent = np.asarray(master["tangent"], dtype=np.float64)
    tangent_dot = float(np.dot(tangent, master_tangent))
    tangent_norm = float(np.linalg.norm(tangent) * np.linalg.norm(master_tangent))
    if tangent_norm <= 1.0e-30 or abs(tangent_dot) / tangent_norm < 0.99:
        raise RuntimeError(
            "Periodic p=2 edge tangent mismatch while building 3D Floquet constraints: "
            f"slave_edge={record['edge']}, master_edge={master['edge']}."
        )
    if tangent_dot >= 0.0:
        return np.eye(2, dtype=np.complex128)
    return np.asarray(context["basix_interval_transform"], dtype=np.complex128)


def _face_coords_match_ordered(
    shifted_slave_coords: np.ndarray,
    master_coords: np.ndarray,
    tol: float,
) -> bool:
    if shifted_slave_coords.shape != master_coords.shape:
        return False
    errors = np.linalg.norm(shifted_slave_coords - master_coords, axis=1)
    return bool(float(np.max(errors, initial=0.0)) <= 10.0 * tol)


def _face_coords_match_unordered(
    shifted_slave_coords: np.ndarray,
    master_coords: np.ndarray,
    tol: float,
) -> bool:
    if shifted_slave_coords.shape != master_coords.shape:
        return False
    rounded_slave = sorted(tuple(np.round(row / tol).astype(np.int64)) for row in shifted_slave_coords)
    rounded_master = sorted(tuple(np.round(row / tol).astype(np.int64)) for row in master_coords)
    return rounded_slave == rounded_master


def _face_vertex_permutation(
    shifted_slave_coords: np.ndarray,
    master_coords: np.ndarray,
    tol: float,
) -> tuple[int, int, int, int]:
    if shifted_slave_coords.shape != master_coords.shape or shifted_slave_coords.shape[0] != 4:
        raise RuntimeError("p=2 quadrilateral face transform expects four face geometry vertices.")
    permutation: list[int] = []
    used: set[int] = set()
    for slave_point in shifted_slave_coords:
        distances = np.linalg.norm(master_coords - slave_point, axis=1)
        master_index = int(np.argmin(distances))
        if float(distances[master_index]) > 10.0 * tol or master_index in used:
            raise RuntimeError(
                "Could not build a one-to-one p=2 quadrilateral face vertex permutation "
                "for periodic Floquet pairing."
            )
        used.add(master_index)
        permutation.append(master_index)
    return tuple(permutation)  # type: ignore[return-value]


def _compose_vertex_permutation(
    outer: tuple[int, int, int, int],
    inner: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return tuple(int(outer[index]) for index in inner)  # type: ignore[return-value]


def _quadrilateral_transform_for_permutation(
    context: dict[str, object],
    permutation: tuple[int, int, int, int],
) -> np.ndarray:
    """Compose Basix quadrilateral entity transformations for one face permutation.

    Basix exposes two local quadrilateral generators.  With the tensor-product
    vertex ordering used by DOLFINx hexahedra, these correspond to swapping the
    two face coordinates and reversing the first face coordinate.  Their small
    4x4 matrices generate the full D4 face-orientation group without any
    whole-plane fitting.
    """

    quad_transforms = np.asarray(context["basix_quadrilateral_transforms"], dtype=np.complex128)
    if quad_transforms.shape != (2, 4, 4):
        raise RuntimeError(f"Unexpected Basix quadrilateral transform shape: {quad_transforms.shape}.")
    generators = [
        ((0, 2, 1, 3), quad_transforms[0]),
        ((1, 0, 3, 2), quad_transforms[1]),
    ]
    identity_perm = (0, 1, 2, 3)
    identity_matrix = np.eye(4, dtype=np.complex128)
    queue: list[tuple[tuple[int, int, int, int], np.ndarray]] = [(identity_perm, identity_matrix)]
    seen: dict[tuple[int, int, int, int], np.ndarray] = {}
    while queue:
        current_perm, current_matrix = queue.pop(0)
        if current_perm in seen:
            continue
        seen[current_perm] = current_matrix
        for generator_perm, generator_matrix in generators:
            queue.append(
                (
                    _compose_vertex_permutation(generator_perm, current_perm),
                    generator_matrix @ current_matrix,
                )
            )
    transform = seen.get(permutation)
    if transform is None:
        raise NotImplementedError(
            "The p=2 periodic face permutation is outside the Basix quadrilateral D4 transform table: "
            f"{permutation}. No dense/probe fallback is allowed."
        )
    return np.asarray(transform, dtype=np.complex128)


def _face_transform_p2(
    context: dict[str, object],
    record: dict[str, object],
    master: dict[str, object],
    cfg: SimulationConfig3D,
    kind: str,
    tol: float,
) -> np.ndarray:
    """Return the p=2 local face-interior block transform.

    The first supported high-order path remains local and topology based:
    identity-oriented faces use an identity 4x4 block, while rotated/reflected
    tensor-product faces are mapped with the small Basix quadrilateral D4
    transform table.  No point probes or pseudo-inverse fitting are used.
    """

    shift = np.zeros(3, dtype=np.float64)
    if kind == "x":
        shift[0] = cfg.x_max - cfg.x_min
    elif kind == "y":
        shift[1] = cfg.y_max - cfg.y_min
    else:
        raise ValueError("p=2 face-interior constraints support only kind='x' or kind='y'.")
    shifted = np.asarray(record["geometry_coords"], dtype=np.float64) - shift
    master_coords = np.asarray(master["geometry_coords"], dtype=np.float64)
    if _face_coords_match_ordered(shifted, master_coords, tol):
        return np.eye(4, dtype=np.complex128)
    if _face_coords_match_unordered(shifted, master_coords, tol):
        permutation = _face_vertex_permutation(shifted, master_coords, tol)
        return _quadrilateral_transform_for_permutation(context, permutation)
    raise RuntimeError(
        "Periodic p=2 face mesh mismatch while building 3D Floquet constraints: "
        f"kind={kind}, slave_face={record['face']}, master_face={master['face']}."
    )


def _validate_owned_constraint_coverage(
    *,
    comm,
    local_slave_globals: list[int],
    owned_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    kind: str,
    entity_label: str,
) -> tuple[dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]], int]:
    gathered_maps = comm.allgather(owned_raw_maps)
    global_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for maps in gathered_maps:
        for slave_global, terms in maps.items():
            if int(slave_global) in global_raw_maps:
                raise RuntimeError(
                    f"3D Floquet {entity_label} slave dof {int(slave_global)} was emitted by multiple ranks."
                )
            global_raw_maps[int(slave_global)] = terms

    gathered_slave_globals = comm.allgather(local_slave_globals)
    global_slave_count = len({int(value) for packet in gathered_slave_globals for value in packet})
    global_constraints = len(global_raw_maps)
    if global_constraints != global_slave_count:
        raise RuntimeError(
            "3D Floquet owned constraint emission is incomplete: "
            f"kind={kind}, entity={entity_label}, emitted_constraints={global_constraints}, "
            f"slave_dofs={global_slave_count}. This usually means the owner rank did not see its "
            "periodic boundary trace dof."
        )
    return global_raw_maps, global_slave_count


def _build_p2_edge_constraints_for_kind(
    context: dict[str, object],
    cfg: SimulationConfig3D,
    kind: str,
    comm,
) -> dict[str, object]:
    """Create p=2 edge trace constraints for x-only, y-only, or corner slave edges."""

    tol = float(context["tol"])
    global_by_key = context["edge_global_by_key"]
    owned_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
    transform_values: list[complex] = []
    pair_errors: list[float] = []
    local_slave_globals: list[int] = []
    local_slave_entity_keys: list[tuple[int, int, int, int]] = []
    local_master_entity_keys: list[tuple[int, int, int, int]] = []
    local_ghost_slave_records = 0
    local_ghost_slave_records_for_owned_cells = 0

    for record in context["edge_records"]:
        if not _record_is_slave_kind(record, cfg, tol, kind):
            continue
        target, phase = _target_for_kind(record, cfg, kind)
        tangent = np.asarray(record["tangent"], dtype=np.float64)
        target_key = _edge_match_key(target, tangent, tol)
        master = global_by_key.get(target_key)
        if master is None:
            nearest = _nearest_edge_error(target, tangent, global_by_key)
            nearest_text = "none" if nearest is None else f"{nearest:.3e} nm"
            raise RuntimeError(
                "Periodic p=2 edge mesh mismatch while building 3D Floquet constraints: "
                f"kind={kind}, slave_edge={record['edge']}, target={target.tolist()}, "
                f"target_key={target_key}, nearest_same_direction_error={nearest_text}. "
                "No dense/probe fallback is allowed."
            )

        pair_error = float(np.linalg.norm(target - np.asarray(master["midpoint"], dtype=np.float64)))
        if pair_error > 10.0 * tol:
            raise RuntimeError(
                "Periodic p=2 edge pairing error exceeds tolerance while building 3D Floquet constraints: "
                f"kind={kind}, slave_edge={record['edge']}, master_edge={master['edge']}, "
                f"pair_error={pair_error:.3e} nm, tolerance={tol:.3e} nm."
            )
        transform = _edge_transform_p2(context, record, master)
        for slave_global in np.asarray(record["global_dofs"], dtype=np.int64):
            local_slave_globals.append(int(slave_global))
        local_slave_entity_keys.append(tuple(record["key"]))
        local_master_entity_keys.append(tuple(master["key"]))
        pair_errors.append(pair_error)
        ghost_for_owned, ghost_skipped, coeffs_seen = _emit_block_constraint_rows(
            record=record,
            master=master,
            transform=transform,
            phase=phase,
            kind=kind,
            entity_label="p2 edge",
            owned_raw_maps=owned_raw_maps,
            local_maps=local_maps,
        )
        local_ghost_slave_records_for_owned_cells += ghost_for_owned
        local_ghost_slave_records += ghost_skipped
        transform_values.extend(coeffs_seen)

    global_raw_maps, global_slave_dof_count = _validate_owned_constraint_coverage(
        comm=comm,
        local_slave_globals=local_slave_globals,
        owned_raw_maps=owned_raw_maps,
        kind=kind,
        entity_label="p2 edge",
    )
    gathered_slave_entities = comm.allgather(local_slave_entity_keys)
    gathered_master_entities = comm.allgather(local_master_entity_keys)
    global_slave_entities = len({tuple(value) for packet in gathered_slave_entities for value in packet})
    global_master_entities = len({tuple(value) for packet in gathered_master_entities for value in packet})

    return {
        "global_raw_maps": global_raw_maps,
        "local_maps": local_maps,
        "orientation_values": np.asarray(transform_values, dtype=np.complex128),
        "pair_error": float(comm.allreduce(max(pair_errors, default=0.0), op=MPI.MAX)),
        "num_local_slave_records_seen": len(local_slave_globals),
        "num_local_ghost_slave_records_skipped": local_ghost_slave_records,
        "num_local_ghost_slave_records_for_owned_cells": local_ghost_slave_records_for_owned_cells,
        "num_global_ghost_slave_records_skipped": int(comm.allreduce(local_ghost_slave_records, op=MPI.SUM)),
        "num_global_ghost_slave_records_for_owned_cells": int(
            comm.allreduce(local_ghost_slave_records_for_owned_cells, op=MPI.SUM)
        ),
        "num_slave_edges": int(global_slave_entities),
        "num_matched_master_edges": int(global_master_entities),
        "num_slave_faces": 0,
        "num_matched_master_faces": 0,
        "num_constraints": int(global_slave_dof_count),
        "num_edge_constraints": int(global_slave_dof_count),
        "num_face_constraints": 0,
        "face_pair_error": 0.0,
    }


def _build_p2_face_constraints_for_kind(
    context: dict[str, object],
    cfg: SimulationConfig3D,
    kind: str,
    comm,
) -> dict[str, object]:
    """Create p=2 face-interior trace constraints for x or y periodic faces."""

    tol = float(context["tol"])
    global_by_key = context["face_global_by_key"]
    owned_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
    transform_values: list[complex] = []
    pair_errors: list[float] = []
    local_slave_globals: list[int] = []
    local_slave_entity_keys: list[tuple[int, int, int, int]] = []
    local_master_entity_keys: list[tuple[int, int, int, int]] = []
    local_ghost_slave_records = 0
    local_ghost_slave_records_for_owned_cells = 0

    for record in context["face_records"]:
        if not _record_is_face_slave_kind(record, cfg, tol, kind):
            continue
        target, phase = _target_for_kind(record, cfg, kind)
        normal_axis = int(record["normal_axis"])
        target_key = _face_match_key(target, normal_axis, tol)
        master = global_by_key.get(target_key)
        if master is None:
            nearest = _nearest_face_error(target, normal_axis, global_by_key)
            nearest_text = "none" if nearest is None else f"{nearest:.3e} nm"
            raise RuntimeError(
                "Periodic p=2 face mesh mismatch while building 3D Floquet constraints: "
                f"kind={kind}, slave_face={record['face']}, target={target.tolist()}, "
                f"target_key={target_key}, nearest_same_normal_error={nearest_text}. "
                "No dense/probe fallback is allowed."
            )

        pair_error = float(np.linalg.norm(target - np.asarray(master["midpoint"], dtype=np.float64)))
        if pair_error > 10.0 * tol:
            raise RuntimeError(
                "Periodic p=2 face pairing error exceeds tolerance while building 3D Floquet constraints: "
                f"kind={kind}, slave_face={record['face']}, master_face={master['face']}, "
                f"pair_error={pair_error:.3e} nm, tolerance={tol:.3e} nm."
            )
        transform = _face_transform_p2(context, record, master, cfg, kind, tol)
        for slave_global in np.asarray(record["global_dofs"], dtype=np.int64):
            local_slave_globals.append(int(slave_global))
        local_slave_entity_keys.append(tuple(record["key"]))
        local_master_entity_keys.append(tuple(master["key"]))
        pair_errors.append(pair_error)
        ghost_for_owned, ghost_skipped, coeffs_seen = _emit_block_constraint_rows(
            record=record,
            master=master,
            transform=transform,
            phase=phase,
            kind=kind,
            entity_label="p2 face",
            owned_raw_maps=owned_raw_maps,
            local_maps=local_maps,
        )
        local_ghost_slave_records_for_owned_cells += ghost_for_owned
        local_ghost_slave_records += ghost_skipped
        transform_values.extend(coeffs_seen)

    global_raw_maps, global_slave_dof_count = _validate_owned_constraint_coverage(
        comm=comm,
        local_slave_globals=local_slave_globals,
        owned_raw_maps=owned_raw_maps,
        kind=kind,
        entity_label="p2 face",
    )
    gathered_slave_entities = comm.allgather(local_slave_entity_keys)
    gathered_master_entities = comm.allgather(local_master_entity_keys)
    global_slave_entities = len({tuple(value) for packet in gathered_slave_entities for value in packet})
    global_master_entities = len({tuple(value) for packet in gathered_master_entities for value in packet})

    return {
        "global_raw_maps": global_raw_maps,
        "local_maps": local_maps,
        "orientation_values": np.asarray(transform_values, dtype=np.complex128),
        "pair_error": 0.0,
        "face_pair_error": float(comm.allreduce(max(pair_errors, default=0.0), op=MPI.MAX)),
        "num_local_slave_records_seen": len(local_slave_globals),
        "num_local_ghost_slave_records_skipped": local_ghost_slave_records,
        "num_local_ghost_slave_records_for_owned_cells": local_ghost_slave_records_for_owned_cells,
        "num_global_ghost_slave_records_skipped": int(comm.allreduce(local_ghost_slave_records, op=MPI.SUM)),
        "num_global_ghost_slave_records_for_owned_cells": int(
            comm.allreduce(local_ghost_slave_records_for_owned_cells, op=MPI.SUM)
        ),
        "num_slave_edges": 0,
        "num_matched_master_edges": 0,
        "num_slave_faces": int(global_slave_entities),
        "num_matched_master_faces": int(global_master_entities),
        "num_constraints": int(global_slave_dof_count),
        "num_edge_constraints": 0,
        "num_face_constraints": int(global_slave_dof_count),
    }


def _merge_constraint_data_blocks(label: str, blocks: list[dict[str, object]]) -> dict[str, object]:
    merged_raw: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    merged_local: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
    orientation_values: list[np.ndarray] = []
    for block_index, block in enumerate(blocks):
        for slave_global, terms in block["global_raw_maps"].items():
            if int(slave_global) in merged_raw:
                raise RuntimeError(
                    f"3D Floquet slave dof {int(slave_global)} would be constrained twice inside {label}."
                )
            merged_raw[int(slave_global)] = terms
        for slave_local, terms in block["local_maps"].items():
            if int(slave_local) in merged_local:
                raise RuntimeError(
                    f"Local 3D Floquet slave dof {int(slave_local)} would be constrained twice inside {label}."
                )
            merged_local[int(slave_local)] = terms
        orientation_values.append(np.asarray(block["orientation_values"], dtype=np.complex128))
    return {
        "global_raw_maps": merged_raw,
        "local_maps": merged_local,
        "orientation_values": np.concatenate(orientation_values) if orientation_values else np.asarray([], dtype=np.complex128),
        "pair_error": max(float(block.get("pair_error", 0.0)) for block in blocks),
        "face_pair_error": max(float(block.get("face_pair_error", 0.0)) for block in blocks),
        "num_local_slave_records_seen": sum(int(block["num_local_slave_records_seen"]) for block in blocks),
        "num_local_ghost_slave_records_skipped": sum(
            int(block["num_local_ghost_slave_records_skipped"]) for block in blocks
        ),
        "num_local_ghost_slave_records_for_owned_cells": sum(
            int(block["num_local_ghost_slave_records_for_owned_cells"]) for block in blocks
        ),
        "num_global_ghost_slave_records_skipped": sum(
            int(block["num_global_ghost_slave_records_skipped"]) for block in blocks
        ),
        "num_global_ghost_slave_records_for_owned_cells": sum(
            int(block["num_global_ghost_slave_records_for_owned_cells"]) for block in blocks
        ),
        "num_slave_edges": sum(int(block["num_slave_edges"]) for block in blocks),
        "num_matched_master_edges": sum(int(block["num_matched_master_edges"]) for block in blocks),
        "num_slave_faces": sum(int(block["num_slave_faces"]) for block in blocks),
        "num_matched_master_faces": sum(int(block["num_matched_master_faces"]) for block in blocks),
        "num_constraints": sum(int(block["num_constraints"]) for block in blocks),
        "num_edge_constraints": sum(int(block["num_edge_constraints"]) for block in blocks),
        "num_face_constraints": sum(int(block["num_face_constraints"]) for block in blocks),
    }


def _assemble_constraint_arrays_from_data_blocks(
    blocks: list[tuple[str, dict[str, object]]],
) -> tuple[
    list[int],
    list[int],
    list[int],
    list[complex],
    list[int],
    int,
    int,
    float,
]:
    maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
    for label, data in blocks:
        for slave_global, terms in data["global_raw_maps"].items():
            if int(slave_global) in maps:
                raise RuntimeError(
                    f"3D Floquet slave dof {int(slave_global)} would be constrained twice after {label} merge."
                )
            maps[int(slave_global)] = terms
        for slave_local, local_terms in data["local_maps"].items():
            if int(slave_local) in local_maps:
                raise RuntimeError(f"Local 3D Floquet slave dof {int(slave_local)} would be constrained twice.")
            local_maps[int(slave_local)] = local_terms

    slave_dofs: list[int] = []
    master_dofs: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets: list[int] = [0]
    for slave_local, local_terms in sorted(local_maps.items()):
        slave_global, masters, owners, coeffs = local_terms
        global_terms = maps.get(int(slave_global))
        if global_terms is None:
            raise RuntimeError(
                f"Local 3D Floquet slave dof {int(slave_local)} maps to global dof "
                f"{int(slave_global)}, but no owned global constraint was emitted."
            )
        if not (
            np.array_equal(global_terms[0], masters)
            and np.array_equal(global_terms[1], owners)
            and np.allclose(global_terms[2], coeffs)
        ):
            raise RuntimeError(f"Local/global 3D Floquet terms disagree for slave global dof {int(slave_global)}.")
        slave_dofs.append(int(slave_local))
        master_dofs.extend(int(value) for value in masters)
        master_owners.extend(int(value) for value in owners)
        coefficients.extend(complex(value) for value in coeffs)
        offsets.append(len(master_dofs))
    raw_map_nnz, max_masters_per_slave, estimated_memory_mb = _map_stats(maps)
    return (
        slave_dofs,
        master_dofs,
        master_owners,
        coefficients,
        offsets,
        raw_map_nnz,
        max_masters_per_slave,
        estimated_memory_mb,
    )


def _build_constraints_for_kind(
    context: dict[str, object],
    cfg: SimulationConfig3D,
    kind: str,
    comm,
) -> dict[str, object]:
    """Create one-master edge constraints for x-only, y-only, or corner slave edges."""

    tol = float(context["tol"])
    global_by_key = context["global_by_key"]
    owned_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
    orientation_values: list[complex] = []
    pair_errors: list[float] = []
    local_slave_globals: list[int] = []
    local_matched_master_globals: list[int] = []
    local_ghost_slave_records = 0
    local_ghost_slave_records_for_owned_cells = 0

    for record in context["local_records"]:
        if not _record_is_slave_kind(record, cfg, tol, kind):
            continue
        target, phase = _target_for_kind(record, cfg, kind)
        tangent = np.asarray(record["tangent"], dtype=np.float64)
        target_key = _edge_match_key(target, tangent, tol)
        master = global_by_key.get(target_key)
        if master is None:
            nearest = _nearest_edge_error(target, tangent, global_by_key)
            nearest_text = "none" if nearest is None else f"{nearest:.3e} nm"
            raise RuntimeError(
                "Periodic face mesh mismatch while building 3D Floquet constraints: "
                f"kind={kind}, slave_edge={record['edge']}, target={target.tolist()}, "
                f"target_key={target_key}, nearest_same_direction_error={nearest_text}. "
                "No dense/probe fallback is allowed."
            )

        pair_error = float(np.linalg.norm(target - np.asarray(master["midpoint"], dtype=np.float64)))
        if pair_error > 10.0 * tol:
            raise RuntimeError(
                "Periodic face mesh mismatch exceeds tolerance while building 3D Floquet constraints: "
                f"kind={kind}, slave_edge={record['edge']}, master_edge={master['edge']}, "
                f"pair_error={pair_error:.3e} nm, tolerance={tol:.3e} nm."
            )

        master_tangent = np.asarray(master["tangent"], dtype=np.float64)
        tangent_dot = float(np.dot(tangent, master_tangent))
        tangent_norm = float(np.linalg.norm(tangent) * np.linalg.norm(master_tangent))
        if tangent_norm <= 1.0e-30 or abs(tangent_dot) / tangent_norm < 0.99:
            raise RuntimeError(
                "Periodic edge tangent mismatch while building 3D Floquet constraints: "
                f"kind={kind}, slave_edge={record['edge']}, master_edge={master['edge']}."
            )
        orientation_sign = 1.0 if tangent_dot >= 0.0 else -1.0

        slave_global = int(record["global_dof"])
        master_global = int(master["global_dof"])
        slave_local = int(record["local_dof"])
        local_slave_globals.append(slave_global)
        local_matched_master_globals.append(master_global)
        pair_errors.append(pair_error)
        orientation_values.append(orientation_sign + 0.0j)

        terms = (
            np.asarray([master_global], dtype=np.int64),
            np.asarray([int(master["owner"])], dtype=np.int32),
            np.asarray([phase * orientation_sign], dtype=np.complex128),
        )

        if bool(record["owned"]):
            if slave_local in local_maps:
                raise RuntimeError(
                    f"Owned local 3D Floquet slave dof {slave_local} would be constrained twice in kind={kind}."
                )
            if slave_global in owned_raw_maps:
                raise RuntimeError(
                    f"3D Floquet slave dof {slave_global} would be constrained twice in kind={kind}."
                )
            owned_raw_maps[slave_global] = terms
            local_maps[slave_local] = (slave_global, *terms)
        else:
            # dolfinx_mpc.add_constraint expects the local slave dofs needed by
            # this process' element assembly.  That includes ghost slaves that
            # appear on owned cells, but excludes boundary edges seen only via
            # ghost cells from neighboring ranks.
            if bool(record.get("touches_owned_cell", False)):
                if slave_local in local_maps:
                    raise RuntimeError(
                        f"Ghost local 3D Floquet slave dof {slave_local} would be constrained twice in kind={kind}."
                    )
                local_maps[slave_local] = (slave_global, *terms)
                local_ghost_slave_records_for_owned_cells += 1
            else:
                local_ghost_slave_records += 1

    gathered_slave_globals = comm.allgather(local_slave_globals)
    gathered_master_globals = comm.allgather(local_matched_master_globals)
    global_slave_edges = sorted({int(value) for packet in gathered_slave_globals for value in packet})
    global_matched_master_edges = sorted({int(value) for packet in gathered_master_globals for value in packet})

    gathered_maps = comm.allgather(owned_raw_maps)
    global_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for maps in gathered_maps:
        for slave_global, terms in maps.items():
            if int(slave_global) in global_raw_maps:
                raise RuntimeError(f"3D Floquet slave dof {int(slave_global)} was emitted by multiple ranks.")
            global_raw_maps[int(slave_global)] = terms

    global_constraints = len(global_raw_maps)
    global_slave_count = len(global_slave_edges)
    global_matched_count = len(global_matched_master_edges)
    if global_slave_count != global_matched_count:
        raise RuntimeError(
            "3D Floquet edge pairing is not one-to-one: "
            f"kind={kind}, slave_edges={global_slave_count}, matched_master_edges={global_matched_count}."
        )
    if global_constraints != global_slave_count:
        raise RuntimeError(
            "3D Floquet owned constraint emission is incomplete: "
            f"kind={kind}, emitted_constraints={global_constraints}, slave_edges={global_slave_count}. "
            "This usually means the owner rank did not see its periodic boundary edge."
        )

    return {
        "global_raw_maps": global_raw_maps,
        "local_maps": local_maps,
        "orientation_values": np.asarray(orientation_values, dtype=np.complex128),
        "pair_error": float(comm.allreduce(max(pair_errors, default=0.0), op=MPI.MAX)),
        "num_local_slave_records_seen": len(local_slave_globals),
        "num_local_ghost_slave_records_skipped": local_ghost_slave_records,
        "num_local_ghost_slave_records_for_owned_cells": local_ghost_slave_records_for_owned_cells,
        "num_global_ghost_slave_records_skipped": int(comm.allreduce(local_ghost_slave_records, op=MPI.SUM)),
        "num_global_ghost_slave_records_for_owned_cells": int(
            comm.allreduce(local_ghost_slave_records_for_owned_cells, op=MPI.SUM)
        ),
        "num_slave_edges": global_slave_count,
        "num_matched_master_edges": global_matched_count,
        "num_constraints": global_constraints,
    }


def _map_stats(maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]) -> tuple[int, int, float]:
    counts = [len(value[0]) for value in maps.values()]
    nnz = int(sum(counts))
    max_masters = int(max(counts, default=0))
    estimated_bytes = len(maps) * (4 + 4) + nnz * (8 + 4 + 16)
    return nnz, max_masters, float(estimated_bytes / (1024.0 * 1024.0))


def _orientation_stats(values: np.ndarray) -> dict[str, object]:
    if values.size == 0:
        return {
            "count": 0,
            "unique_rounded_real": [],
            "max_abs": None,
            "note": "Explicit edge topology mapping produced no orientation factors.",
        }
    rounded = np.unique(np.round(values.real, 6))
    return {
        "count": int(values.size),
        "unique_rounded_real": rounded.tolist(),
        "max_abs": float(np.max(np.abs(values))),
        "note": "Orientation factors are explicit edge tangent signs; no probe/pseudo-inverse fitting is used.",
    }


def _disabled_probe_values(*args, **kwargs):
    raise RuntimeError(
        "3D Floquet probe-value mapping is disabled. "
        "The formal Stage 2 path uses explicit degree=1 N1curl edge topology constraints only."
    )


def _disabled_transform(*args, **kwargs):
    raise RuntimeError(
        "3D Floquet pseudo-inverse transform mapping is disabled. "
        "Each slave edge dof must map to exactly one master edge dof."
    )


def _disabled_axis_raw_maps_plane(*args, **kwargs):
    raise RuntimeError(
        "3D Floquet dense whole-plane fitting is disabled because it has O(N^2) memory growth. "
        "Use the explicit topological edge builder instead."
    )


# Backward-compatible names are kept only to fail loudly if older code calls them.
_probe_values = _disabled_probe_values
_transform = _disabled_transform
_axis_raw_maps_plane = _disabled_axis_raw_maps_plane


def _build_double_floquet_mpc_p2_trace(
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    dolfinx_mpc,
    log=None,
) -> DoubleFloquet3DData:
    """Create p=2 double-periodic Floquet MPC from edge and face trace topology."""

    comm = V.mesh.comm
    timings: dict[str, float] = {}
    comm.barrier()
    total_start = time.perf_counter()
    constraint_mode_resolved = "topological_trace_p2"

    context_cache: dict[str, object] = {}

    def _context() -> dict[str, object]:
        if "value" not in context_cache:
            context_cache["value"] = _build_topological_trace_context_p2(V, mesh_data, cfg)
        return context_cache["value"]

    def _timed_step(key: str, message: str, callback):
        if log is not None:
            log(message)
        comm.barrier()
        step_start = time.perf_counter()
        result = callback()
        elapsed = float(comm.allreduce(time.perf_counter() - step_start, op=MPI.MAX))
        timings[key] = elapsed
        if log is not None:
            log(f"{message} seconds = {elapsed:.3f}")
        return result

    _timed_step(
        "floquet_build_topological_trace_context_p2",
        "building 3D Floquet p=2 topological trace context",
        _context,
    )

    def _x_constraints():
        context = _context()
        return _merge_constraint_data_blocks(
            "p2 x-direction trace",
            [
                _build_p2_edge_constraints_for_kind(context, cfg, "x", comm),
                _build_p2_face_constraints_for_kind(context, cfg, "x", comm),
            ],
        )

    def _y_constraints():
        context = _context()
        return _merge_constraint_data_blocks(
            "p2 y-direction trace",
            [
                _build_p2_edge_constraints_for_kind(context, cfg, "y", comm),
                _build_p2_face_constraints_for_kind(context, cfg, "y", comm),
            ],
        )

    x_data = _timed_step(
        "floquet_build_x_constraints",
        "building 3D Floquet x-direction low-level constraints",
        _x_constraints,
    )
    y_data = _timed_step(
        "floquet_build_y_constraints",
        "building 3D Floquet y-direction low-level constraints",
        _y_constraints,
    )
    corner_data = _timed_step(
        "floquet_resolve_corner_master_chains",
        "resolving 3D double-Floquet corner/master chain",
        lambda: _build_p2_edge_constraints_for_kind(_context(), cfg, "corner", comm),
    )

    (
        slave_dofs,
        master_dofs,
        master_owners,
        coefficients,
        offsets,
        raw_map_nnz,
        max_masters_per_slave,
        estimated_constraint_memory_mb,
    ) = _timed_step(
        "floquet_build_mpc_arrays",
        "assembling 3D p=2 topological trace Floquet MPC arrays",
        lambda: _assemble_constraint_arrays_from_data_blocks(
            [("x", x_data), ("y", y_data), ("corner", corner_data)]
        ),
    )

    def _finalize_mpc():
        mpc = dolfinx_mpc.MultiPointConstraint(V)
        mpc.add_constraint(
            V,
            np.asarray(slave_dofs, dtype=np.int32),
            np.asarray(master_dofs, dtype=np.int64),
            np.asarray(coefficients, dtype=np.complex128),
            np.asarray(master_owners, dtype=np.int32),
            np.asarray(offsets, dtype=np.int32),
        )
        mpc.finalize()
        return mpc

    mpc = _timed_step(
        "floquet_mpc_finalize",
        "finalizing 3D double-Floquet MPC",
        _finalize_mpc,
    )
    timings["floquet_total"] = float(comm.allreduce(time.perf_counter() - total_start, op=MPI.MAX))

    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)
    phase_corner = phase_x * phase_y
    orientation_values = np.concatenate(
        [
            np.asarray(x_data["orientation_values"], dtype=np.complex128),
            np.asarray(y_data["orientation_values"], dtype=np.complex128),
            np.asarray(corner_data["orientation_values"], dtype=np.complex128),
        ]
    )
    orientation_stats = _orientation_stats(orientation_values)
    orientation_stats.update(
        {
            "mapping_kind": "topological_trace_p2_edge_and_face_blocks",
            "uses_basix_interval_transform": True,
            "uses_basix_quadrilateral_transform_hook": True,
            "face_transform_limit": "tensor-product quadrilateral D4 rotations/reflections from Basix local blocks",
            "basix_interval_transform_shape": list(np.asarray(_context()["basix_interval_transform"]).shape),
            "basix_quadrilateral_transform_shape": list(
                np.asarray(_context()["basix_quadrilateral_transforms"]).shape
            ),
        }
    )

    max_edge_pair_error = max(
        float(x_data["pair_error"]),
        float(y_data["pair_error"]),
        float(corner_data["pair_error"]),
    )
    max_face_pair_error = max(float(x_data["face_pair_error"]), float(y_data["face_pair_error"]))

    num_slave_edges = int(x_data["num_slave_edges"] + y_data["num_slave_edges"] + corner_data["num_slave_edges"])
    num_matched_master_edges = int(
        x_data["num_matched_master_edges"]
        + y_data["num_matched_master_edges"]
        + corner_data["num_matched_master_edges"]
    )
    num_slave_faces = int(x_data["num_slave_faces"] + y_data["num_slave_faces"])
    num_matched_master_faces = int(x_data["num_matched_master_faces"] + y_data["num_matched_master_faces"])
    num_edge_constraints = int(
        x_data["num_edge_constraints"] + y_data["num_edge_constraints"] + corner_data["num_edge_constraints"]
    )
    num_face_constraints = int(x_data["num_face_constraints"] + y_data["num_face_constraints"])
    num_constraints = int(num_edge_constraints + num_face_constraints)
    num_x_constraints = int(x_data["num_constraints"])
    num_y_constraints = int(y_data["num_constraints"])
    num_corner_constraints = int(corner_data["num_constraints"])
    num_local_slave_records_seen = int(
        x_data["num_local_slave_records_seen"]
        + y_data["num_local_slave_records_seen"]
        + corner_data["num_local_slave_records_seen"]
    )
    num_local_ghost_slave_constraints = int(
        x_data["num_local_ghost_slave_records_for_owned_cells"]
        + y_data["num_local_ghost_slave_records_for_owned_cells"]
        + corner_data["num_local_ghost_slave_records_for_owned_cells"]
    )
    num_global_ghost_slave_constraints = int(
        x_data["num_global_ghost_slave_records_for_owned_cells"]
        + y_data["num_global_ghost_slave_records_for_owned_cells"]
        + corner_data["num_global_ghost_slave_records_for_owned_cells"]
    )
    num_local_ghost_slave_records_skipped = int(
        x_data["num_local_ghost_slave_records_skipped"]
        + y_data["num_local_ghost_slave_records_skipped"]
        + corner_data["num_local_ghost_slave_records_skipped"]
    )
    num_global_ghost_slave_records_skipped = int(
        x_data["num_global_ghost_slave_records_skipped"]
        + y_data["num_global_ghost_slave_records_skipped"]
        + corner_data["num_global_ghost_slave_records_skipped"]
    )
    local_slave_dofs = np.asarray(slave_dofs, dtype=np.int32)

    if log is not None:
        log(f"3D Floquet phase x = {phase_x.real:.12g} + {phase_x.imag:.12g}j")
        log(f"3D Floquet phase y = {phase_y.real:.12g} + {phase_y.imag:.12g}j")
        log(f"3D Floquet phase corner = {phase_corner.real:.12g} + {phase_corner.imag:.12g}j")
        log(f"3D Floquet number of slave edges = {num_slave_edges}")
        log(f"3D Floquet number of matched master edges = {num_matched_master_edges}")
        log(f"3D Floquet number of slave faces = {num_slave_faces}")
        log(f"3D Floquet number of matched master faces = {num_matched_master_faces}")
        log(f"3D Floquet number of constraints = {num_constraints}")
        log(f"3D Floquet number of edge constraints = {num_edge_constraints}")
        log(f"3D Floquet number of face constraints = {num_face_constraints}")
        log(f"3D Floquet max edge midpoint pairing error = {max_edge_pair_error:.3e} nm")
        log(f"3D Floquet max face midpoint pairing error = {max_face_pair_error:.3e} nm")
        log(f"3D Floquet number of x constraints = {num_x_constraints}")
        log(f"3D Floquet number of y constraints = {num_y_constraints}")
        log(f"3D Floquet number of corner constraints = {num_corner_constraints}")
        log(f"3D Floquet local slave dofs = {len(local_slave_dofs)}")
        log(f"3D Floquet local slave records seen = {num_local_slave_records_seen}")
        log(
            "3D Floquet local ghost slave records on owned cells "
            f"(not added to MPC) = {num_local_ghost_slave_constraints}"
        )
        log(
            "3D Floquet global ghost slave records on owned cells "
            f"(not added to MPC) = {num_global_ghost_slave_constraints}"
        )
        log(f"3D Floquet local ghost slave records skipped = {num_local_ghost_slave_records_skipped}")
        log(f"3D Floquet global ghost slave records skipped = {num_global_ghost_slave_records_skipped}")
        log(f"3D Floquet raw map nnz = {raw_map_nnz}")
        log(f"3D Floquet max masters per slave = {max_masters_per_slave}")
        log(f"3D Floquet estimated constraint memory MB = {estimated_constraint_memory_mb:.3f}")
        log(f"3D Floquet total constraint setup seconds = {timings['floquet_total']:.3f}")

    return DoubleFloquet3DData(
        mpc=mpc,
        local_slave_dofs=local_slave_dofs,
        num_local_slaves=len(local_slave_dofs),
        num_local_slave_records_seen=num_local_slave_records_seen,
        num_local_ghost_slave_constraints=num_local_ghost_slave_constraints,
        num_global_ghost_slave_constraints=num_global_ghost_slave_constraints,
        num_local_ghost_slave_records_skipped=num_local_ghost_slave_records_skipped,
        num_global_ghost_slave_records_skipped=num_global_ghost_slave_records_skipped,
        constraint_mode_resolved=constraint_mode_resolved,
        phase_x=phase_x,
        phase_y=phase_y,
        phase_corner=phase_corner,
        max_face_pairing_coordinate_error=max(max_edge_pair_error, max_face_pair_error),
        edge_corner_phase_mismatch=0.0,
        orientation_factor_stats=orientation_stats,
        timings_seconds=timings,
        raw_map_nnz=raw_map_nnz,
        max_masters_per_slave=max_masters_per_slave,
        estimated_constraint_memory_mb=estimated_constraint_memory_mb,
        num_slave_edges=num_slave_edges,
        num_matched_master_edges=num_matched_master_edges,
        num_constraints=num_constraints,
        max_edge_midpoint_pairing_error=max_edge_pair_error,
        num_x_constraints=num_x_constraints,
        num_y_constraints=num_y_constraints,
        num_corner_constraints=num_corner_constraints,
        num_slave_faces=num_slave_faces,
        num_matched_master_faces=num_matched_master_faces,
        num_edge_constraints=num_edge_constraints,
        num_face_constraints=num_face_constraints,
        max_face_midpoint_pairing_error=max_face_pair_error,
    )


def build_double_floquet_mpc(V, mesh_data, cfg: SimulationConfig3D, log=None) -> DoubleFloquet3DData:
    """Create double-periodic x/y Floquet constraints for 3D Nedelec trace dofs."""

    try:
        import dolfinx_mpc
    except ModuleNotFoundError as exc:
        raise RuntimeError("The 3D Floquet path requires dolfinx_mpc, but it is not installed.") from exc

    comm = V.mesh.comm
    timings: dict[str, float] = {}
    comm.barrier()
    total_start = time.perf_counter()
    constraint_mode_resolved = _resolve_constraint_mode(V, cfg)
    if log is not None:
        log(f"3D Floquet constraint mode requested = {cfg.floquet_constraint_mode_requested}")
        log(f"3D Floquet constraint mode resolved = {constraint_mode_resolved}")
    if constraint_mode_resolved == "topological_trace_p2":
        if log is not None:
            log(
                "3D Floquet formal mapping = explicit p=2 N1curl edge + face-interior trace topology; "
                "probe/pinv is disabled."
            )
        return _build_double_floquet_mpc_p2_trace(V, mesh_data, cfg, dolfinx_mpc, log)
    if log is not None:
        log("3D Floquet formal mapping = explicit degree-1 N1curl edge topology; probe/pinv is disabled.")

    context_cache: dict[str, object] = {}

    def _context() -> dict[str, object]:
        if "value" not in context_cache:
            context_cache["value"] = _build_topological_edge_context(V, mesh_data, cfg)
        return context_cache["value"]

    def _timed_step(key: str, message: str, callback):
        """Time one MPI collective Floquet step and report the slowest rank."""

        if log is not None:
            log(message)
        comm.barrier()
        step_start = time.perf_counter()
        result = callback()
        elapsed = float(comm.allreduce(time.perf_counter() - step_start, op=MPI.MAX))
        timings[key] = elapsed
        if log is not None:
            log(f"{message} seconds = {elapsed:.3f}")
        return result

    _timed_step(
        "floquet_build_topological_edge_context",
        "building 3D Floquet topological edge context",
        _context,
    )
    x_data = _timed_step(
        "floquet_build_x_constraints",
        "building 3D Floquet x-direction low-level constraints",
        lambda: _build_constraints_for_kind(_context(), cfg, "x", comm),
    )
    y_data = _timed_step(
        "floquet_build_y_constraints",
        "building 3D Floquet y-direction low-level constraints",
        lambda: _build_constraints_for_kind(_context(), cfg, "y", comm),
    )
    corner_data = _timed_step(
        "floquet_resolve_corner_master_chains",
        "resolving 3D double-Floquet corner/master chain",
        lambda: _build_constraints_for_kind(_context(), cfg, "corner", comm),
    )

    def _assemble_constraint_arrays():
        return _assemble_constraint_arrays_from_data_blocks(
            [("x", x_data), ("y", y_data), ("corner", corner_data)]
        )

    (
        slave_dofs,
        master_dofs,
        master_owners,
        coefficients,
        offsets,
        raw_map_nnz,
        max_masters_per_slave,
        estimated_constraint_memory_mb,
    ) = _timed_step(
        "floquet_build_mpc_arrays",
        "assembling 3D topological Floquet MPC arrays",
        _assemble_constraint_arrays,
    )

    def _finalize_mpc():
        mpc = dolfinx_mpc.MultiPointConstraint(V)
        mpc.add_constraint(
            V,
            np.asarray(slave_dofs, dtype=np.int32),
            np.asarray(master_dofs, dtype=np.int64),
            np.asarray(coefficients, dtype=np.complex128),
            np.asarray(master_owners, dtype=np.int32),
            np.asarray(offsets, dtype=np.int32),
        )
        mpc.finalize()
        return mpc

    mpc = _timed_step(
        "floquet_mpc_finalize",
        "finalizing 3D double-Floquet MPC",
        _finalize_mpc,
    )
    timings["floquet_total"] = float(comm.allreduce(time.perf_counter() - total_start, op=MPI.MAX))

    local_slave_dofs = np.asarray(slave_dofs, dtype=np.int32)
    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)
    phase_corner = phase_x * phase_y
    orientation_values = np.concatenate(
        [
            np.asarray(x_data["orientation_values"], dtype=np.complex128),
            np.asarray(y_data["orientation_values"], dtype=np.complex128),
            np.asarray(corner_data["orientation_values"], dtype=np.complex128),
        ]
    )
    orientation_stats = _orientation_stats(orientation_values)
    max_edge_pair_error = max(
        float(x_data["pair_error"]),
        float(y_data["pair_error"]),
        float(corner_data["pair_error"]),
    )

    num_slave_edges = int(x_data["num_slave_edges"] + y_data["num_slave_edges"] + corner_data["num_slave_edges"])
    num_matched_master_edges = int(
        x_data["num_matched_master_edges"]
        + y_data["num_matched_master_edges"]
        + corner_data["num_matched_master_edges"]
    )
    num_constraints = int(x_data["num_constraints"] + y_data["num_constraints"] + corner_data["num_constraints"])
    num_x_constraints = int(x_data["num_constraints"])
    num_y_constraints = int(y_data["num_constraints"])
    num_corner_constraints = int(corner_data["num_constraints"])
    num_local_slave_records_seen = int(
        x_data["num_local_slave_records_seen"]
        + y_data["num_local_slave_records_seen"]
        + corner_data["num_local_slave_records_seen"]
    )
    num_local_ghost_slave_constraints = int(
        x_data["num_local_ghost_slave_records_for_owned_cells"]
        + y_data["num_local_ghost_slave_records_for_owned_cells"]
        + corner_data["num_local_ghost_slave_records_for_owned_cells"]
    )
    num_global_ghost_slave_constraints = int(
        x_data["num_global_ghost_slave_records_for_owned_cells"]
        + y_data["num_global_ghost_slave_records_for_owned_cells"]
        + corner_data["num_global_ghost_slave_records_for_owned_cells"]
    )
    num_local_ghost_slave_records_skipped = int(
        x_data["num_local_ghost_slave_records_skipped"]
        + y_data["num_local_ghost_slave_records_skipped"]
        + corner_data["num_local_ghost_slave_records_skipped"]
    )
    num_global_ghost_slave_records_skipped = int(
        x_data["num_global_ghost_slave_records_skipped"]
        + y_data["num_global_ghost_slave_records_skipped"]
        + corner_data["num_global_ghost_slave_records_skipped"]
    )

    if log is not None:
        log(f"3D Floquet phase x = {phase_x.real:.12g} + {phase_x.imag:.12g}j")
        log(f"3D Floquet phase y = {phase_y.real:.12g} + {phase_y.imag:.12g}j")
        log(f"3D Floquet phase corner = {phase_corner.real:.12g} + {phase_corner.imag:.12g}j")
        log(f"3D Floquet number of slave edges = {num_slave_edges}")
        log(f"3D Floquet number of matched master edges = {num_matched_master_edges}")
        log(f"3D Floquet number of constraints = {num_constraints}")
        log(f"3D Floquet max edge midpoint pairing error = {max_edge_pair_error:.3e} nm")
        log(f"3D Floquet number of x constraints = {num_x_constraints}")
        log(f"3D Floquet number of y constraints = {num_y_constraints}")
        log(f"3D Floquet number of corner constraints = {num_corner_constraints}")
        log(f"3D Floquet local slave dofs = {len(local_slave_dofs)}")
        log(f"3D Floquet local slave records seen = {num_local_slave_records_seen}")
        log(f"3D Floquet local ghost slave constraints = {num_local_ghost_slave_constraints}")
        log(f"3D Floquet global ghost slave constraints = {num_global_ghost_slave_constraints}")
        log(f"3D Floquet local ghost slave records skipped = {num_local_ghost_slave_records_skipped}")
        log(f"3D Floquet global ghost slave records skipped = {num_global_ghost_slave_records_skipped}")
        log(f"3D Floquet raw map nnz = {raw_map_nnz}")
        log(f"3D Floquet max masters per slave = {max_masters_per_slave}")
        log(f"3D Floquet estimated constraint memory MB = {estimated_constraint_memory_mb:.3f}")
        log(f"3D Floquet total constraint setup seconds = {timings['floquet_total']:.3f}")

    return DoubleFloquet3DData(
        mpc=mpc,
        local_slave_dofs=local_slave_dofs,
        num_local_slaves=len(local_slave_dofs),
        num_local_slave_records_seen=num_local_slave_records_seen,
        num_local_ghost_slave_constraints=num_local_ghost_slave_constraints,
        num_global_ghost_slave_constraints=num_global_ghost_slave_constraints,
        num_local_ghost_slave_records_skipped=num_local_ghost_slave_records_skipped,
        num_global_ghost_slave_records_skipped=num_global_ghost_slave_records_skipped,
        constraint_mode_resolved=constraint_mode_resolved,
        phase_x=phase_x,
        phase_y=phase_y,
        phase_corner=phase_corner,
        max_face_pairing_coordinate_error=max_edge_pair_error,
        edge_corner_phase_mismatch=0.0,
        orientation_factor_stats=orientation_stats,
        timings_seconds=timings,
        raw_map_nnz=raw_map_nnz,
        max_masters_per_slave=max_masters_per_slave,
        estimated_constraint_memory_mb=estimated_constraint_memory_mb,
        num_slave_edges=num_slave_edges,
        num_matched_master_edges=num_matched_master_edges,
        num_constraints=num_constraints,
        max_edge_midpoint_pairing_error=max_edge_pair_error,
        num_x_constraints=num_x_constraints,
        num_y_constraints=num_y_constraints,
        num_corner_constraints=num_corner_constraints,
    )
