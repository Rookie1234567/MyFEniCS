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


def _mesh_is_hexahedron(msh) -> bool:
    return "hexahedron" in str(msh.basix_cell()).lower()


def _resolve_constraint_mode(V, cfg: SimulationConfig3D) -> str:
    requested = cfg.floquet_constraint_mode_requested
    if requested in {"auto", "topological_edges", "sparse_facet"}:
        return "topological_edges"
    raise RuntimeError(
        "3D Floquet dense probe/pseudo-inverse constraint construction is disabled. "
        "Use floquet_constraint_mode='auto' or 'topological_edges'."
    )


def _require_supported_topological_edges(V, cfg: SimulationConfig3D) -> None:
    if int(cfg.nedelec_degree) != 1:
        raise NotImplementedError(
            "3D explicit Floquet edge topology constraints currently support only degree=1 N1curl. "
            f"Requested degree={cfg.nedelec_degree}."
        )
    if not _mesh_is_hexahedron(V.mesh):
        raise NotImplementedError(
            "3D explicit Floquet edge topology constraints require a hexahedron mesh. "
            "Use mesh_cell_type='auto' or 'hexahedron' for Stage 2 Floquet cases."
        )
    edge_entity_dofs = V.element.basix_element.entity_dofs[1]
    if not edge_entity_dofs or any(len(dofs) != 1 for dofs in edge_entity_dofs):
        raise NotImplementedError(
            "3D explicit Floquet constraints assume exactly one N1curl dof on each mesh edge. "
            "This is true for degree=1 N1curl on hexahedra; higher-order elements are not implemented."
        )


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
            }
            current = edge_dof_map.get(int(edge))
            if current is not None and int(current["global_dof"]) != int(record["global_dof"]):
                raise RuntimeError(
                    "Inconsistent N1curl dof assignment for mesh edge "
                    f"{int(edge)}: {current['global_dof']} vs {record['global_dof']}."
                )
            if current is None or (bool(record["owned"]) and not bool(current["owned"])):
                edge_dof_map[int(edge)] = record
    return edge_dof_map


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
    edge_geometry = cpp.mesh.entities_to_geometry(msh._cpp_object, 1, periodic_edges, False)

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
        local_slave_globals.append(slave_global)
        local_matched_master_globals.append(master_global)
        pair_errors.append(pair_error)
        orientation_values.append(orientation_sign + 0.0j)

        terms = (
            np.asarray([master_global], dtype=np.int64),
            np.asarray([int(master["owner"])], dtype=np.int32),
            np.asarray([phase * orientation_sign], dtype=np.complex128),
        )
        slave_local = int(record["local_dof"])
        if slave_local in local_maps:
            raise RuntimeError(
                f"Local 3D Floquet slave dof {slave_local} would be constrained twice in kind={kind}."
            )
        local_maps[slave_local] = (slave_global, *terms)

        if bool(record["owned"]):
            if slave_global in owned_raw_maps:
                raise RuntimeError(
                    f"3D Floquet slave dof {slave_global} would be constrained twice in kind={kind}."
                )
            owned_raw_maps[slave_global] = terms

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


def build_double_floquet_mpc(V, mesh_data, cfg: SimulationConfig3D, log=None) -> DoubleFloquet3DData:
    """Create double-periodic x/y Floquet constraints for degree-1 3D Nedelec dofs."""

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
        maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray]] = {}
        for label, data in (("x", x_data), ("y", y_data), ("corner", corner_data)):
            for slave_global, terms in data["global_raw_maps"].items():
                if int(slave_global) in maps:
                    raise RuntimeError(
                        f"3D Floquet slave dof {int(slave_global)} would be constrained twice after {label} merge."
                    )
                maps[int(slave_global)] = terms
            for slave_local, local_terms in data["local_maps"].items():
                if int(slave_local) in local_maps:
                    raise RuntimeError(
                        f"Local 3D Floquet slave dof {int(slave_local)} would be constrained twice."
                    )
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
                raise RuntimeError(
                    f"Local/global 3D Floquet terms disagree for slave global dof {int(slave_global)}."
                )
            if len(masters) != 1:
                raise RuntimeError(
                    f"3D explicit Floquet constraint expected one master for slave {slave_global}, "
                    f"got {len(masters)}."
                )
            slave_dofs.append(int(slave_local))
            master_dofs.append(int(masters[0]))
            master_owners.append(int(owners[0]))
            coefficients.append(complex(coeffs[0]))
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
        log(f"3D Floquet raw map nnz = {raw_map_nnz}")
        log(f"3D Floquet max masters per slave = {max_masters_per_slave}")
        log(f"3D Floquet estimated constraint memory MB = {estimated_constraint_memory_mb:.3f}")
        log(f"3D Floquet total constraint setup seconds = {timings['floquet_total']:.3f}")

    return DoubleFloquet3DData(
        mpc=mpc,
        local_slave_dofs=local_slave_dofs,
        num_local_slaves=len(local_slave_dofs),
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
