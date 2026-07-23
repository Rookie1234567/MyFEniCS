from __future__ import annotations

from dataclasses import dataclass
import time

import basix
import dolfinx
import numpy as np
from mpi4py import MPI

from dolfinx import cpp, mesh

from ..common.config_3d import SimulationConfig3D
from .high_order_floquet_trace import (
    FloquetTopologyCache,
    FloquetTopologyKey,
    FloquetTraceTopology,
    PhaseIndependentConstraintBlock,
    distributed_match_periodic_records,
    edge_coefficient_transform,
    face_coefficient_transform,
    high_order_trace_layout,
    tetrahedral_trace_layout,
    triangle_face_coefficient_transform,
)


_TOPOLOGY_CACHE = FloquetTopologyCache(max_entries=8)
_KIND_CODE = {"x": 1, "y": 2, "corner": 3}


def clear_floquet_topology_cache() -> None:
    """Release every cached phase-independent topology on the current rank."""

    _TOPOLOGY_CACHE.clear()


def floquet_topology_cache_size() -> int:
    """Return the number of live-owner topology entries on the current rank."""

    return len(_TOPOLOGY_CACHE)


@dataclass(frozen=True)
class HighOrderFloquetConstraintData:
    topology: FloquetTraceTopology
    topology_cache_hit: bool
    slave_local_dofs: np.ndarray
    slave_global_dofs: np.ndarray
    master_global_dofs: np.ndarray
    master_owners: np.ndarray
    coefficients: np.ndarray
    offsets: np.ndarray
    global_constraint_rows: int
    global_constraint_nnz: int
    max_masters_per_slave: int
    estimated_constraint_memory_mb: float
    num_local_slave_records_seen: int
    num_local_ghost_slave_constraints: int
    num_global_ghost_slave_constraints: int
    num_local_ghost_slave_records_skipped: int
    num_global_ghost_slave_records_skipped: int
    num_slave_edges: int
    num_matched_master_edges: int
    num_slave_faces: int
    num_matched_master_faces: int
    num_edge_constraints: int
    num_face_constraints: int
    num_x_constraints: int
    num_y_constraints: int
    num_corner_constraints: int
    max_edge_pairing_error: float
    max_face_pairing_error: float
    orientation_values: np.ndarray
    topology_build_seconds_current: float
    phase_update_seconds: float
    communication_bytes_sent_current: int
    communication_bytes_received_current: int


def _geometry_tolerance(cfg: SimulationConfig3D) -> float:
    span = max(
        abs(cfg.x_max - cfg.x_min),
        abs(cfg.y_max - cfg.y_min),
        abs(cfg.domain_z_max - cfg.domain_z_min),
        1.0,
    )
    return max(1.0e-8, 1.0e-10 * span)


def _local_dof_global_info(
    V, dofs: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index_map = V.dofmap.index_map
    block_size = V.dofmap.index_map_bs
    comm = V.mesh.comm
    dofs = np.asarray(dofs, dtype=np.int64)
    blocks = dofs // block_size
    components = dofs % block_size
    global_blocks = index_map.local_to_global(blocks.astype(np.int32)).astype(np.int64)
    global_dofs = global_blocks * block_size + components
    owned = blocks < index_map.size_local
    owners = np.empty(len(dofs), dtype=np.int32)
    owners[owned] = comm.rank
    if np.any(~owned):
        ghost_owners = np.asarray(index_map.owners, dtype=np.int32)
        owners[~owned] = ghost_owners[blocks[~owned] - index_map.size_local]
    return global_dofs.astype(np.int64), owners, owned


def _build_entity_dof_map(
    V, entity_dim: int, expected_entity_dofs: int
) -> dict[int, dict[str, object]]:
    msh = V.mesh
    tdim = msh.topology.dim
    msh.topology.create_entity_permutations()
    msh.topology.create_connectivity(tdim, entity_dim)
    msh.topology.create_connectivity(entity_dim, tdim)
    cell_to_entity = msh.topology.connectivity(tdim, entity_dim)
    cell_map = msh.topology.index_map(tdim)
    num_cells = cell_map.size_local + cell_map.num_ghosts
    entity_dofs = [
        V.dofmap.dof_layout.entity_dofs(entity_dim, local_entity)
        for local_entity in range(
            len(V.element.basix_element.entity_dofs[int(entity_dim)])
        )
    ]
    local_entity_count = len(entity_dofs)

    records: dict[int, dict[str, object]] = {}
    for cell in range(num_cells):
        cell_entities = cell_to_entity.links(cell)
        cell_dofs = V.dofmap.cell_dofs(cell)
        if len(cell_entities) != local_entity_count:
            raise RuntimeError(
                "Basix and DOLFINx disagree on the local trace entity count: "
                f"Basix={local_entity_count}, DOLFINx={len(cell_entities)}."
            )
        for local_entity, entity in enumerate(cell_entities):
            reference_dofs = np.asarray(entity_dofs[local_entity], dtype=np.int32)
            if len(reference_dofs) != int(expected_entity_dofs):
                raise RuntimeError(
                    "Basix/DOLFINx entity layout disagrees with the qualified "
                    f"Task033 layout for dim={entity_dim}: expected "
                    f"{expected_entity_dofs}, found {len(reference_dofs)}."
                )
            local_dofs = np.asarray(
                [int(cell_dofs[int(index)]) for index in reference_dofs],
                dtype=np.int32,
            )
            global_dofs, owners, owned = _local_dof_global_info(V, local_dofs)
            record = {
                "entity": int(entity),
                "local_dofs": local_dofs,
                "global_dofs": global_dofs,
                "owners": owners,
                "owned": owned,
                "touches_owned_cell": bool(cell < cell_map.size_local),
            }
            current = records.get(int(entity))
            if current is not None and not np.array_equal(
                current["global_dofs"], record["global_dofs"]
            ):
                raise RuntimeError(
                    "DOLFINx returned inconsistent global coefficient ordering "
                    f"for shared entity dim={entity_dim}, id={int(entity)}."
                )
            if current is None:
                records[int(entity)] = record
                continue
            current["touches_owned_cell"] = bool(
                current.get("touches_owned_cell", False)
            ) or bool(record["touches_owned_cell"])
            if bool(np.any(record["owned"])) and not bool(np.any(current["owned"])):
                record["touches_owned_cell"] = bool(
                    record["touches_owned_cell"]
                ) or bool(current["touches_owned_cell"])
                records[int(entity)] = record
    return records


def _periodic_boundary_entities(
    mesh_data, cfg: SimulationConfig3D, entity_dim: int
) -> np.ndarray:
    msh = mesh_data.mesh
    tagged_facets: list[int] = []
    for tag in (cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max):
        tagged_facets.extend(
            int(value)
            for value in np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
        )
    tagged_entities: list[int] = []
    if int(entity_dim) == msh.topology.dim - 1:
        tagged_entities.extend(tagged_facets)
    elif tagged_facets:
        msh.topology.create_connectivity(msh.topology.dim - 1, entity_dim)
        facet_to_entity = msh.topology.connectivity(msh.topology.dim - 1, entity_dim)
        tagged_entities.extend(
            int(entity)
            for facet in tagged_facets
            for entity in facet_to_entity.links(int(facet))
        )

    msh.topology.create_entities(entity_dim)
    msh.topology.create_connectivity(entity_dim, msh.topology.dim)
    msh.topology.create_entity_permutations()
    entity_map = msh.topology.index_map(entity_dim)
    local_entities = np.arange(
        entity_map.size_local + entity_map.num_ghosts, dtype=np.int32
    )
    geometry = cpp.mesh.entities_to_geometry(
        msh._cpp_object, entity_dim, local_entities, True
    )
    tolerance = _geometry_tolerance(cfg)
    geometric_entities = []
    for entity, geometry_dofs in zip(local_entities, geometry, strict=True):
        coordinates = np.asarray(
            msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64)],
            dtype=np.float64,
        )
        if any(
            np.all(np.abs(coordinates[:, axis] - boundary) <= tolerance)
            for axis, boundary in (
                (0, cfg.x_min),
                (0, cfg.x_max),
                (1, cfg.y_min),
                (1, cfg.y_max),
            )
        ):
            geometric_entities.append(int(entity))
    return np.unique(
        np.asarray((*tagged_entities, *geometric_entities), dtype=np.int32)
    )


def _build_periodic_entity_records(
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    entity_dim: int,
    entity_dofs: int,
) -> list[dict[str, object]]:
    msh = mesh_data.mesh
    entities = _periodic_boundary_entities(mesh_data, cfg, entity_dim)
    if len(entities) == 0:
        raise RuntimeError(
            f"No periodic boundary entities of dim={entity_dim} were found."
        )
    dof_map = _build_entity_dof_map(V, entity_dim, entity_dofs)
    msh.topology.create_entity_permutations()
    midpoints = mesh.compute_midpoints(msh, entity_dim, entities)
    geometry = cpp.mesh.entities_to_geometry(
        msh._cpp_object, entity_dim, entities, True
    )
    records: list[dict[str, object]] = []
    for entity, midpoint, geometry_dofs in zip(
        entities, midpoints, geometry, strict=True
    ):
        dof_record = dof_map.get(int(entity))
        if dof_record is None:
            raise RuntimeError(
                f"No N1curl dofs were found for periodic entity {int(entity)}."
            )
        coords = np.asarray(
            msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64)],
            dtype=np.float64,
        )
        record = {
            **dof_record,
            "cell_type": str(msh.basix_cell()).lower(),
            "midpoint": np.asarray(midpoint, dtype=np.float64),
            "geometry_coords": coords,
        }
        if int(entity_dim) == 1:
            if coords.shape[0] < 2:
                raise RuntimeError("A periodic edge exposes fewer than two vertices.")
            tangent = np.asarray(coords[1] - coords[0], dtype=np.float64)
            if float(np.linalg.norm(tangent)) <= 1.0e-30:
                raise RuntimeError("A periodic edge has a near-zero tangent.")
            record["tangent"] = tangent
        else:
            if coords.shape[0] not in {3, 4}:
                raise RuntimeError(
                    "Periodic faces require linear triangle or quadrilateral geometry."
                )
            normal = np.cross(coords[1] - coords[0], coords[2] - coords[0])
            record["normal_axis"] = int(np.argmax(np.abs(normal)))
        records.append(record)
    return records


def _boundary_flags(
    point: np.ndarray, cfg: SimulationConfig3D, tol: float
) -> dict[str, bool]:
    return {
        "x_min": abs(float(point[0]) - cfg.x_min) <= tol,
        "x_max": abs(float(point[0]) - cfg.x_max) <= tol,
        "y_min": abs(float(point[1]) - cfg.y_min) <= tol,
        "y_max": abs(float(point[1]) - cfg.y_max) <= tol,
    }


def _entity_role(
    record: dict[str, object],
    cfg: SimulationConfig3D,
    tol: float,
    *,
    entity_kind: str,
    kind: str,
) -> str | None:
    flags = _boundary_flags(np.asarray(record["midpoint"], dtype=np.float64), cfg, tol)
    if entity_kind == "face":
        if kind == "x":
            return "slave" if flags["x_max"] else "master" if flags["x_min"] else None
        if kind == "y":
            return "slave" if flags["y_max"] else "master" if flags["y_min"] else None
        raise ValueError("Periodic faces support only x/y relations.")
    if kind == "corner":
        if flags["x_max"] and flags["y_max"]:
            return "slave"
        if flags["x_min"] and flags["y_min"]:
            return "master"
        return None
    if kind == "x":
        if flags["x_max"] and not flags["y_max"]:
            return "slave"
        if flags["x_min"] and not flags["y_max"]:
            return "master"
        return None
    if kind == "y":
        if flags["y_max"] and not flags["x_max"]:
            return "slave"
        if flags["y_min"] and not flags["x_max"]:
            return "master"
        return None
    raise ValueError(f"Unsupported Floquet relation kind {kind!r}.")


def _periodic_shift(cfg: SimulationConfig3D, kind: str) -> np.ndarray:
    shift = np.zeros(3, dtype=np.float64)
    if kind in {"x", "corner"}:
        shift[0] = cfg.x_max - cfg.x_min
    if kind in {"y", "corner"}:
        shift[1] = cfg.y_max - cfg.y_min
    return shift


def _pair_key(
    record: dict[str, object],
    canonical_midpoint: np.ndarray,
    tol: float,
    *,
    entity_dim: int,
    kind: str,
) -> tuple[int, ...]:
    if int(entity_dim) == 1:
        direction_axis = int(
            np.argmax(np.abs(np.asarray(record["tangent"], dtype=np.float64)))
        )
    else:
        direction_axis = int(record["normal_axis"])
    return (
        int(entity_dim),
        int(_KIND_CODE[kind]),
        int(round(float(canonical_midpoint[0]) / tol)),
        int(round(float(canonical_midpoint[1]) / tol)),
        int(round(float(canonical_midpoint[2]) / tol)),
        direction_axis,
    )


def _json_packet(
    record: dict[str, object],
    role: str,
    cfg: SimulationConfig3D,
    tol: float,
    *,
    entity_dim: int,
    kind: str,
    rank: int,
    token: str,
) -> dict:
    midpoint = np.asarray(record["midpoint"], dtype=np.float64)
    canonical = midpoint - _periodic_shift(cfg, kind) if role == "slave" else midpoint
    packet = {
        "pair_key": list(
            _pair_key(
                record,
                canonical,
                tol,
                entity_dim=entity_dim,
                kind=kind,
            )
        ),
        "role": role,
        "global_dofs": [
            int(value) for value in np.asarray(record["global_dofs"], dtype=np.int64)
        ],
        "owners": [
            int(value) for value in np.asarray(record["owners"], dtype=np.int32)
        ],
        "owns_any": bool(np.any(record["owned"])),
        "reply_rank": int(rank),
        "token": token,
        "midpoint": [float(value) for value in midpoint],
        "entity_dim": int(entity_dim),
        "entity_kind": "edge" if int(entity_dim) == 1 else "face",
    }
    if int(entity_dim) == 1:
        packet["tangent"] = [
            float(value) for value in np.asarray(record["tangent"], dtype=np.float64)
        ]
    else:
        packet["geometry_coords"] = np.asarray(
            record["geometry_coords"], dtype=np.float64
        ).tolist()
        packet["normal_axis"] = int(record["normal_axis"])
    return packet


def _face_vertex_permutation(
    shifted_slave_coords: np.ndarray,
    master_coords: np.ndarray,
    tol: float,
) -> tuple[int, ...]:
    if (
        shifted_slave_coords.ndim != 2
        or shifted_slave_coords.shape != master_coords.shape
        or shifted_slave_coords.shape[0] not in {3, 4}
        or shifted_slave_coords.shape[1] != 3
    ):
        raise RuntimeError(
            "A high-order face pairing needs matching triangle or quadrilateral vertices."
        )
    permutation: list[int] = []
    used: set[int] = set()
    for slave_point in shifted_slave_coords:
        distances = np.linalg.norm(master_coords - slave_point, axis=1)
        master_index = int(np.argmin(distances))
        if float(distances[master_index]) > 10.0 * tol or master_index in used:
            raise RuntimeError(
                "Could not build a one-to-one periodic face vertex permutation."
            )
        used.add(master_index)
        permutation.append(master_index)
    return tuple(permutation)


def _pair_entity_blocks(
    comm,
    records: list[dict[str, object]],
    cfg: SimulationConfig3D,
    tol: float,
    *,
    degree: int,
    entity_dim: int,
    kind: str,
) -> tuple[list[PhaseIndependentConstraintBlock], object]:
    packets: list[dict] = []
    slaves_by_token: dict[str, dict[str, object]] = {}
    for record in records:
        entity_kind = "edge" if int(entity_dim) == 1 else "face"
        role = _entity_role(
            record,
            cfg,
            tol,
            entity_kind=entity_kind,
            kind=kind,
        )
        if role is None:
            continue
        token = f"{entity_dim}:{kind}:{int(record['entity'])}"
        if role == "slave":
            if token in slaves_by_token:
                raise RuntimeError(f"Duplicate local periodic slave token {token}.")
            slaves_by_token[token] = record
        packets.append(
            _json_packet(
                record,
                role,
                cfg,
                tol,
                entity_dim=entity_dim,
                kind=kind,
                rank=int(comm.rank),
                token=token,
            )
        )

    replies, metrics = distributed_match_periodic_records(comm, packets)
    replies_by_token = {str(reply["token"]): reply for reply in replies}
    if set(replies_by_token) != set(slaves_by_token):
        missing = sorted(set(slaves_by_token) - set(replies_by_token))
        unexpected = sorted(set(replies_by_token) - set(slaves_by_token))
        raise RuntimeError(
            "Distributed periodic pairing replies disagree with local slaves: "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}."
        )

    blocks: list[PhaseIndependentConstraintBlock] = []
    shift = _periodic_shift(cfg, kind)
    for token, record in slaves_by_token.items():
        master = replies_by_token[token]["master"]
        target = np.asarray(record["midpoint"], dtype=np.float64) - shift
        master_midpoint = np.asarray(master["midpoint"], dtype=np.float64)
        pair_error = float(np.linalg.norm(target - master_midpoint))
        if pair_error > 10.0 * tol:
            raise RuntimeError(
                "Periodic entity pairing coordinate error exceeds tolerance: "
                f"kind={kind}, token={token}, error={pair_error:.3e}."
            )
        if int(entity_dim) == 1:
            tangent = np.asarray(record["tangent"], dtype=np.float64)
            master_tangent = np.asarray(master["tangent"], dtype=np.float64)
            tangent_dot = float(np.dot(tangent, master_tangent))
            tangent_norm = float(
                np.linalg.norm(tangent) * np.linalg.norm(master_tangent)
            )
            if tangent_norm <= 1.0e-30 or abs(tangent_dot) / tangent_norm < 0.99:
                raise RuntimeError("Periodic edge tangents are not collinear.")
            transform = edge_coefficient_transform(
                degree,
                reversed_orientation=tangent_dot < 0.0,
                cell_type=(
                    "tetrahedron"
                    if "tetrahedron" in str(record.get("cell_type", ""))
                    else "hexahedron"
                ),
            )
            entity_kind = "edge"
        else:
            shifted_coords = (
                np.asarray(record["geometry_coords"], dtype=np.float64) - shift
            )
            master_coords = np.asarray(master["geometry_coords"], dtype=np.float64)
            permutation = _face_vertex_permutation(shifted_coords, master_coords, tol)
            transform = (
                triangle_face_coefficient_transform(degree, permutation)
                if len(permutation) == 3
                else face_coefficient_transform(degree, permutation)
            )
            entity_kind = "face"
        blocks.append(
            PhaseIndependentConstraintBlock(
                kind=kind,  # type: ignore[arg-type]
                slave_global_dofs=tuple(
                    int(value)
                    for value in np.asarray(record["global_dofs"], dtype=np.int64)
                ),
                master_global_dofs=tuple(int(value) for value in master["global_dofs"]),
                coefficient_transform=transform,
                slave_local_dofs=tuple(
                    int(value)
                    for value in np.asarray(record["local_dofs"], dtype=np.int32)
                ),
                master_owners=tuple(int(value) for value in master["owners"]),
                slave_owned=tuple(
                    bool(value) for value in np.asarray(record["owned"], dtype=bool)
                ),
                touches_owned_cell=bool(record["touches_owned_cell"]),
                entity_kind=entity_kind,  # type: ignore[arg-type]
                pair_error=pair_error,
            )
        )
    return blocks, metrics


def _topology_key(
    V, mesh_data, cfg: SimulationConfig3D, degree: int
) -> FloquetTopologyKey:
    msh = V.mesh
    geometry_degree = int(getattr(msh.geometry.cmap, "degree", 1))
    mesh_token = (
        id(msh._cpp_object),
        id(V),
        int(V.dofmap.index_map.size_global),
        int(msh.comm.size),
        str(msh.basix_cell()),
        geometry_degree,
        float(cfg.x_min),
        float(cfg.x_max),
        float(cfg.y_min),
        float(cfg.y_max),
        int(cfg.tags.x_min),
        int(cfg.tags.x_max),
        int(cfg.tags.y_min),
        int(cfg.tags.y_max),
        float(_geometry_tolerance(cfg)),
        str(dolfinx.__version__),
        str(basix.__version__),
    )
    cell_kind = "tetra-s3" if "tetrahedron" in str(msh.basix_cell()) else "hexa-d4"
    return FloquetTopologyKey(
        mesh_token=mesh_token,
        element_family=str(V.element.basix_element.family),
        degree=int(degree),
        orientation_schema=f"basix-0.10-{cell_kind}-dolfinx-global-v1",
    )


def _build_trace_topology(
    V, mesh_data, cfg: SimulationConfig3D, key: FloquetTopologyKey
) -> FloquetTraceTopology:
    comm = V.mesh.comm
    comm.barrier()
    started = time.perf_counter()
    degree = int(cfg.nedelec_degree)
    cell_name = str(V.mesh.basix_cell()).lower()
    layout = (
        tetrahedral_trace_layout(degree)
        if "tetrahedron" in cell_name
        else high_order_trace_layout(degree)
    )
    edge_records = _build_periodic_entity_records(
        V,
        mesh_data,
        cfg,
        entity_dim=1,
        entity_dofs=layout.edge_dofs,
    )
    face_records = (
        _build_periodic_entity_records(
            V,
            mesh_data,
            cfg,
            entity_dim=2,
            entity_dofs=layout.face_interior_dofs,
        )
        if layout.face_interior_dofs
        else []
    )

    blocks: list[PhaseIndependentConstraintBlock] = []
    pair_counts: list[tuple[str, str, int]] = []
    local_bytes_sent = 0
    local_bytes_received = 0
    for entity_kind, entity_dim, records, kinds in (
        ("edge", 1, edge_records, ("x", "y", "corner")),
        ("face", 2, face_records, ("x", "y")),
    ):
        if not records:
            for kind in kinds:
                pair_counts.append((entity_kind, kind, 0))
            continue
        for kind in kinds:
            relation_blocks, metrics = _pair_entity_blocks(
                comm,
                records,
                cfg,
                _geometry_tolerance(cfg),
                degree=degree,
                entity_dim=entity_dim,
                kind=kind,
            )
            blocks.extend(relation_blocks)
            pair_counts.append((entity_kind, kind, int(metrics.pair_count)))
            local_bytes_sent += int(metrics.bytes_sent)
            local_bytes_received += int(metrics.bytes_received)

    bytes_sent = int(comm.allreduce(local_bytes_sent, op=MPI.SUM))
    bytes_received = int(comm.allreduce(local_bytes_received, op=MPI.SUM))
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    return FloquetTraceTopology(
        key=key,
        blocks=tuple(blocks),
        topology_build_seconds=elapsed,
        bytes_sent=bytes_sent,
        bytes_received=bytes_received,
        used_full_boundary_gather=False,
        created_dense_boundary_square=False,
        pair_counts=tuple(pair_counts),  # type: ignore[arg-type]
    )


def _get_or_build_topology(
    V, mesh_data, cfg: SimulationConfig3D
) -> tuple[FloquetTraceTopology, bool]:
    key = _topology_key(V, mesh_data, cfg, int(cfg.nedelec_degree))
    cached = _TOPOLOGY_CACHE.get(key, mesh=mesh_data.mesh, space=V)
    hit_count = int(V.mesh.comm.allreduce(cached is not None, op=MPI.SUM))
    if hit_count == int(V.mesh.comm.size):
        assert cached is not None
        return cached, True
    if hit_count:
        # A partial rank hit must not leave divergent cache state.
        _TOPOLOGY_CACHE.clear()
    topology = _build_trace_topology(V, mesh_data, cfg, key)
    _TOPOLOGY_CACHE.put(topology, mesh=mesh_data.mesh, space=V)
    return topology, False


def _nonzero_terms(
    globals_: tuple[int, ...],
    owners: tuple[int, ...],
    coefficients: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    mask = np.abs(coefficients) > 1.0e-14
    if not np.any(mask):
        raise RuntimeError("A high-order Floquet constraint row has no masters.")
    return (
        np.asarray(globals_, dtype=np.int64)[mask],
        np.asarray(owners, dtype=np.int32)[mask],
        coefficients[mask],
    )


def build_high_order_constraint_data(
    V, mesh_data, cfg: SimulationConfig3D
) -> HighOrderFloquetConstraintData:
    """Build phase-materialized qualified sparse local Floquet MPC arrays.

    The public 3D dispatcher uses this distributed exact-topology path for every
    qualified degree.  The topology is phase independent and can therefore be
    reused when only the incident angle (and hence the Floquet phase) changes.
    """

    degree = int(cfg.nedelec_degree)
    cell_name = str(V.mesh.basix_cell()).lower()
    if "tetrahedron" in cell_name:
        layout = tetrahedral_trace_layout(degree)
    elif "hexahedron" in cell_name:
        layout = high_order_trace_layout(degree)
    else:
        raise NotImplementedError(
            "High-order Floquet constraints support tetrahedra and hexahedra."
        )
    if int(V.element.basix_element.degree) != degree:
        raise RuntimeError("Config and function-space N1curl degrees disagree.")
    topology, cache_hit = _get_or_build_topology(V, mesh_data, cfg)

    comm = V.mesh.comm
    comm.barrier()
    started = time.perf_counter()
    phase_by_kind = {
        "x": complex(cfg.floquet_phase_x),
        "y": complex(cfg.floquet_phase_y),
        "corner": complex(cfg.floquet_phase_x) * complex(cfg.floquet_phase_y),
    }
    local_maps: dict[int, tuple[int, np.ndarray, np.ndarray, np.ndarray, bool]] = {}
    local_owned_rows = 0
    local_owned_nnz = 0
    local_max_masters = 0
    local_ghost_constraints = 0
    local_ghost_skipped = 0
    local_records_seen = 0
    orientation_values: list[complex] = []
    for block in topology.blocks:
        if not block.slave_local_dofs or not block.master_owners:
            raise RuntimeError("Cached Floquet topology block lacks local MPC data.")
        phase = phase_by_kind[block.kind]
        local_records_seen += len(block.slave_global_dofs)
        for row, (slave_local, slave_global, is_owned) in enumerate(
            zip(
                block.slave_local_dofs,
                block.slave_global_dofs,
                block.slave_owned,
                strict=True,
            )
        ):
            if not bool(is_owned) and not block.touches_owned_cell:
                local_ghost_skipped += 1
                continue
            masters, owners, coefficients = _nonzero_terms(
                block.master_global_dofs,
                block.master_owners,
                phase * block.coefficient_transform[row, :],
            )
            if int(slave_local) in local_maps:
                raise RuntimeError(
                    f"Local high-order Floquet slave {int(slave_local)} is duplicated."
                )
            local_maps[int(slave_local)] = (
                int(slave_global),
                masters,
                owners,
                coefficients,
                bool(is_owned),
            )
            orientation_values.extend(
                complex(value)
                for value in block.coefficient_transform[row, :]
                if abs(value) > 1.0e-14
            )
            if bool(is_owned):
                local_owned_rows += 1
                local_owned_nnz += len(masters)
                local_max_masters = max(local_max_masters, len(masters))
            else:
                local_ghost_constraints += 1

    pair_counts = {
        (entity_kind, kind): int(count)
        for entity_kind, kind, count in topology.pair_counts
    }
    expected_edge_rows = layout.edge_dofs * sum(
        pair_counts.get(("edge", kind), 0) for kind in ("x", "y", "corner")
    )
    expected_face_rows = layout.face_interior_dofs * sum(
        pair_counts.get(("face", kind), 0) for kind in ("x", "y")
    )
    expected_rows = int(expected_edge_rows + expected_face_rows)
    global_owned_rows = int(comm.allreduce(local_owned_rows, op=MPI.SUM))
    if global_owned_rows != expected_rows:
        raise RuntimeError(
            "Distributed high-order Floquet ownership coverage failed: "
            f"owned_rows={global_owned_rows}, expected_rows={expected_rows}."
        )
    global_nnz = int(comm.allreduce(local_owned_nnz, op=MPI.SUM))
    max_masters = int(comm.allreduce(local_max_masters, op=MPI.MAX))

    slave_local_dofs: list[int] = []
    slave_global_dofs: list[int] = []
    master_global_dofs: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets: list[int] = [0]
    for slave_local, (
        slave_global,
        masters,
        owners,
        row_coefficients,
        _is_owned,
    ) in sorted(local_maps.items()):
        slave_local_dofs.append(int(slave_local))
        slave_global_dofs.append(int(slave_global))
        master_global_dofs.extend(int(value) for value in masters)
        master_owners.extend(int(value) for value in owners)
        coefficients.extend(complex(value) for value in row_coefficients)
        offsets.append(len(master_global_dofs))

    phase_update_seconds = float(
        comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
    )
    global_ghost_constraints = int(comm.allreduce(local_ghost_constraints, op=MPI.SUM))
    global_ghost_skipped = int(comm.allreduce(local_ghost_skipped, op=MPI.SUM))
    estimated_bytes = global_owned_rows * 8 + global_nnz * (8 + 4 + 16)
    edge_pair_error = max(
        (
            float(block.pair_error)
            for block in topology.blocks
            if block.entity_kind == "edge"
        ),
        default=0.0,
    )
    face_pair_error = max(
        (
            float(block.pair_error)
            for block in topology.blocks
            if block.entity_kind == "face"
        ),
        default=0.0,
    )
    edge_pair_error = float(comm.allreduce(edge_pair_error, op=MPI.MAX))
    face_pair_error = float(comm.allreduce(face_pair_error, op=MPI.MAX))

    edge_pairs = sum(
        pair_counts.get(("edge", kind), 0) for kind in ("x", "y", "corner")
    )
    face_pairs = sum(pair_counts.get(("face", kind), 0) for kind in ("x", "y"))
    x_constraints = layout.edge_dofs * pair_counts.get(
        ("edge", "x"), 0
    ) + layout.face_interior_dofs * pair_counts.get(("face", "x"), 0)
    y_constraints = layout.edge_dofs * pair_counts.get(
        ("edge", "y"), 0
    ) + layout.face_interior_dofs * pair_counts.get(("face", "y"), 0)
    corner_constraints = layout.edge_dofs * pair_counts.get(("edge", "corner"), 0)
    return HighOrderFloquetConstraintData(
        topology=topology,
        topology_cache_hit=cache_hit,
        slave_local_dofs=np.asarray(slave_local_dofs, dtype=np.int32),
        slave_global_dofs=np.asarray(slave_global_dofs, dtype=np.int64),
        master_global_dofs=np.asarray(master_global_dofs, dtype=np.int64),
        master_owners=np.asarray(master_owners, dtype=np.int32),
        coefficients=np.asarray(coefficients, dtype=np.complex128),
        offsets=np.asarray(offsets, dtype=np.int32),
        global_constraint_rows=global_owned_rows,
        global_constraint_nnz=global_nnz,
        max_masters_per_slave=max_masters,
        estimated_constraint_memory_mb=float(estimated_bytes / (1024.0**2)),
        num_local_slave_records_seen=local_records_seen,
        num_local_ghost_slave_constraints=local_ghost_constraints,
        num_global_ghost_slave_constraints=global_ghost_constraints,
        num_local_ghost_slave_records_skipped=local_ghost_skipped,
        num_global_ghost_slave_records_skipped=global_ghost_skipped,
        num_slave_edges=int(edge_pairs),
        num_matched_master_edges=int(edge_pairs),
        num_slave_faces=int(face_pairs),
        num_matched_master_faces=int(face_pairs),
        num_edge_constraints=int(expected_edge_rows),
        num_face_constraints=int(expected_face_rows),
        num_x_constraints=int(x_constraints),
        num_y_constraints=int(y_constraints),
        num_corner_constraints=int(corner_constraints),
        max_edge_pairing_error=edge_pair_error,
        max_face_pairing_error=face_pair_error,
        orientation_values=np.asarray(orientation_values, dtype=np.complex128),
        topology_build_seconds_current=(
            0.0 if cache_hit else float(topology.topology_build_seconds)
        ),
        phase_update_seconds=phase_update_seconds,
        communication_bytes_sent_current=0 if cache_hit else topology.bytes_sent,
        communication_bytes_received_current=(
            0 if cache_hit else topology.bytes_received
        ),
    )
