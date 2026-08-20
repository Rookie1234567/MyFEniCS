"""Owner-local Full3D slab topology and first-order interface action.

This module contains the small T4 topology lane.  The slab map is geometric
bookkeeping around the existing DOLFINx mesh and finalized Floquet MPC; it is
not a second constraint system.  The Robin candidate is a facet action, not a
diagonal operation on trace coefficients.  In particular, its local weak
term is

    integral_(Gamma) q u_t dot v_t,

where ``u_t`` and ``v_t`` are the tangential H(curl) traces on the horizontal
interface.  No interface matrix is retained or assembled.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

import numpy as np
import ufl
from mpi4py import MPI

from dolfinx import cpp, mesh

from ..common.config_3d import SimulationConfig3D
from ..constraints.floquet_3d_high_order import _local_dof_global_info
from ..geometry.tetra_mesh_audit import canonical_entity_key, mesh_coordinate_tolerance
from .fullspace_mpc_action import build_fullspace_mpc_form_action


FULLSPACE_SCALABLE_PROFILE = "full3d_scalable_v1"
FULLSPACE_T4_SLAB_COUNT = 2
FULLSPACE_T4_TRANSMISSION = "first_order_impedance_robin_v1"
FULLSPACE_T4_TRACE_WEIGHT = 1.0


@dataclass(frozen=True)
class MaterialSignature:
    """Physical material data used by the interface action."""

    tag: int
    epsilon_r: complex
    mu_r: complex

    @property
    def refractive_index(self) -> complex:
        index = complex(np.sqrt(self.epsilon_r * self.mu_r))
        if index.real < 0.0:
            index = -index
        return index


@dataclass(frozen=True)
class InterfaceFacet:
    """One owned horizontal interior facet and its active H(curl) trace rows."""

    local_index: int
    key: tuple[tuple[int, int, int], ...]
    lower_cell_global: int
    upper_cell_global: int
    lower_cell_owner: int
    upper_cell_owner: int
    lower_participant_ranks: tuple[int, ...]
    upper_participant_ranks: tuple[int, ...]
    lower_material: MaterialSignature
    upper_material: MaterialSignature
    classification: str
    interface_tag: int
    trace_local_rows: tuple[int, ...]
    trace_global_rows: tuple[int, ...]
    trace_owners: tuple[int, ...]


@dataclass(frozen=True)
class NeighborPlan:
    """Facet/row owner-consumer routes for the current partition."""

    forward_send_peers: tuple[int, ...]
    forward_recv_peers: tuple[int, ...]
    backward_send_peers: tuple[int, ...]
    backward_recv_peers: tuple[int, ...]
    lower_participant_ranks: tuple[int, ...]
    upper_participant_ranks: tuple[int, ...]


@dataclass(frozen=True)
class InterfaceTopology:
    """Partition-local topology plus partition-independent physical identity."""

    mesh: Any
    function_space: Any
    floquet_data: Any
    cfg: SimulationConfig3D
    profile: str
    interface_z: float
    tolerance: float
    facets: tuple[InterfaceFacet, ...]
    global_material_pairs: tuple[tuple[int, MaterialSignature, MaterialSignature], ...]
    interface_facet_indices: np.ndarray
    interface_facet_tag_values: np.ndarray
    interface_facet_tags: Any
    owned_trace_global_rows: np.ndarray
    owned_trace_local_rows: np.ndarray
    ghost_trace_global_rows: np.ndarray
    ghost_trace_local_rows: np.ndarray
    ghost_trace_owners: np.ndarray
    excluded_slave_local_rows: np.ndarray
    owned_slab_ids: np.ndarray
    neighbor_plan: NeighborPlan
    volume_owned_size: int
    canonical_manifest: tuple[dict[str, object], ...]
    local_canonical_manifest: tuple[dict[str, object], ...]
    canonical_sha256: str
    local_canonical_sha256: str
    canonical_global_count: int
    audit: Mapping[str, object]

    @property
    def owned_trace_count(self) -> int:
        return int(self.owned_trace_global_rows.size)

    @property
    def ghost_trace_count(self) -> int:
        return int(self.ghost_trace_global_rows.size)

    def restrict_volume_to_trace(self, volume_values: np.ndarray) -> np.ndarray:
        """Select active owned rows; this is data movement, not transmission."""

        values = np.asarray(volume_values, dtype=np.complex128)
        if values.size < self.volume_owned_size:
            raise ValueError("volume values do not contain owned rows")
        return values[self.owned_trace_local_rows].copy()

    def prolong_trace_to_volume(self, trace_values: np.ndarray) -> np.ndarray:
        """Inject active owned rows with the unit trace weight."""

        values = np.asarray(trace_values, dtype=np.complex128)
        if values.size != self.owned_trace_count:
            raise ValueError("trace values do not match owned trace rows")
        result = np.zeros(self.volume_owned_size, dtype=np.complex128)
        result[self.owned_trace_local_rows] = (
            FULLSPACE_T4_TRACE_WEIGHT * values
        )
        return result


def _complex_key(value: complex) -> tuple[float, float]:
    return (float(complex(value).real), float(complex(value).imag))


def _material_key(material: MaterialSignature) -> tuple[object, ...]:
    return (
        int(material.tag),
        *_complex_key(material.epsilon_r),
        *_complex_key(material.mu_r),
    )


def _material_from_tag(cfg: SimulationConfig3D, tag: int) -> MaterialSignature:
    if int(tag) == int(cfg.tags.air):
        epsilon = cfg.eps_air
    elif int(tag) == int(cfg.tags.substrate):
        epsilon = cfg.eps_substrate
    elif int(tag) == int(cfg.tags.grating):
        epsilon = cfg.eps_grating
    else:
        raise ValueError(
            "T4 interface topology supports physical air/substrate/grating "
            f"cells only; encountered cell tag {int(tag)}."
        )
    return MaterialSignature(int(tag), complex(epsilon), complex(cfg.mu_r))


def _entity_geometry(msh: mesh.Mesh, dim: int, entities: np.ndarray) -> list[np.ndarray]:
    geometry = cpp.mesh.entities_to_geometry(
        msh._cpp_object,
        int(dim),
        np.asarray(entities, dtype=np.int32),
        True,
    )
    return [
        np.asarray(msh.geometry.x[np.asarray(indices, dtype=np.int64)], dtype=np.float64)
        for indices in geometry
    ]


def _cell_global_index(index_map: Any, local_index: int) -> int:
    local_index = int(local_index)
    if local_index < int(index_map.size_local):
        return int(index_map.local_to_global(np.asarray([local_index], dtype=np.int32))[0])
    return int(np.asarray(index_map.ghosts, dtype=np.int64)[local_index - int(index_map.size_local)])


def _cell_materials(
    msh: mesh.Mesh,
    mesh_data: Any,
    cfg: SimulationConfig3D,
) -> tuple[list[MaterialSignature], str, int]:
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    owned_count = int(cell_map.size_local)
    ghost_count = int(cell_map.num_ghosts)
    total_count = owned_count + ghost_count
    indices = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
    values = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    local_error = ""
    if indices.size != values.size or np.unique(indices).size != indices.size:
        local_error = "cell tags do not provide one value per tagged cell"
    elif np.any(indices < 0) or np.any(indices >= total_count):
        local_error = "cell tag index exceeds local cell storage"
    failed = msh.comm.allreduce(bool(local_error), op=MPI.LOR)
    if failed:
        errors = msh.comm.allgather(local_error)
        message = next(error for error in errors if error)
        message = msh.comm.bcast(message if msh.comm.rank == 0 else None, root=0)
        raise RuntimeError(f"cell tag preflight failed: {message}")

    tags = np.full(total_count, -1, dtype=np.int32)
    local_scope = "owned_local_sparse_ghost_owner_exchange"
    request_count = 0
    if indices.size == total_count and np.array_equal(
        np.sort(indices), np.arange(total_count, dtype=np.int32)
    ):
        tags[indices] = values
        local_scope = "local_owned_plus_ghost"
    else:
        local_error = ""
        if np.any(indices >= owned_count):
            local_error = "partial cell tags must use owned local cell indices"
        tags[indices] = values
        if np.any(tags[:owned_count] < 0):
            local_error = "cell tags do not cover all owned cells"
        failed = msh.comm.allreduce(bool(local_error), op=MPI.LOR)
        if failed:
            errors = msh.comm.allgather(local_error)
            message = next(error for error in errors if error)
            message = msh.comm.bcast(message if msh.comm.rank == 0 else None, root=0)
            raise RuntimeError(f"cell tag preflight failed: {message}")

        owned_tags_by_global = {
            _cell_global_index(cell_map, int(index)): int(value)
            for index, value in zip(indices, values, strict=True)
        }
        requests: list[list[tuple[int, int]]] = [
            [] for _rank in range(msh.comm.size)
        ]
        owner_array = np.asarray(cell_map.owners, dtype=np.int32)
        ghost_array = np.asarray(cell_map.ghosts, dtype=np.int64)
        local_error = ""
        for local_cell in range(owned_count, total_count):
            ghost_index = local_cell - owned_count
            owner = int(owner_array[ghost_index])
            global_cell = int(ghost_array[ghost_index])
            if owner < 0 or owner >= msh.comm.size:
                local_error = "ghost cell has an invalid owner rank"
                break
            requests[owner].append((global_cell, local_cell))
        failed = msh.comm.allreduce(bool(local_error), op=MPI.LOR)
        if failed:
            errors = msh.comm.allgather(local_error)
            message = next(error for error in errors if error)
            message = msh.comm.bcast(message if msh.comm.rank == 0 else None, root=0)
            raise RuntimeError(f"ghost cell request preflight failed: {message}")
        request_count = sum(len(packet) for packet in requests)
        incoming_requests = msh.comm.alltoall(requests)
        responses: list[list[tuple[int, int]]] = [
            [] for _rank in range(msh.comm.size)
        ]
        response_error = ""
        for requester, packet in enumerate(incoming_requests):
            for global_cell, _local_cell in packet:
                if int(global_cell) not in owned_tags_by_global:
                    response_error = (
                        "owner rank received a ghost tag request for an unknown "
                        f"owned cell {int(global_cell)}"
                    )
                    break
                responses[requester].append(
                    (int(global_cell), owned_tags_by_global[int(global_cell)])
                )
            if response_error:
                break
        failed = msh.comm.allreduce(bool(response_error), op=MPI.LOR)
        if failed:
            errors = msh.comm.allgather(response_error)
            message = next(error for error in errors if error)
            message = msh.comm.bcast(message if msh.comm.rank == 0 else None, root=0)
            raise RuntimeError(f"ghost cell tag exchange failed: {message}")
        received = msh.comm.alltoall(responses)
        global_to_local = {
            int(np.asarray(cell_map.ghosts, dtype=np.int64)[local - owned_count]): local
            for local in range(owned_count, total_count)
        }
        for packet in received:
            for global_cell, tag in packet:
                tags[global_to_local[int(global_cell)]] = int(tag)
        if np.any(tags[owned_count:] < 0):
            local_error = "ghost cell tag exchange did not close local cells"

    valid_tags = {
        int(cfg.tags.air),
        int(cfg.tags.substrate),
        int(cfg.tags.grating),
    }
    invalid_tags = sorted({int(tag) for tag in tags if int(tag) not in valid_tags})
    if invalid_tags:
        local_error = f"unsupported physical cell tags {invalid_tags}"
    else:
        local_error = ""
    failed = msh.comm.allreduce(bool(local_error), op=MPI.LOR)
    if failed:
        errors = msh.comm.allgather(local_error)
        message = next(error for error in errors if error)
        message = msh.comm.bcast(message if msh.comm.rank == 0 else None, root=0)
        raise RuntimeError(f"cell material preflight failed: {message}")

    materials: list[MaterialSignature] = []
    for tag in tags:
        materials.append(_material_from_tag(cfg, int(tag)))
    return materials, local_scope, request_count


def _trace_rows_for_facet(
    V: Any,
    cell_to_facet: Any,
    cell_to_edge: Any,
    facet_to_edge: Any,
    facet: int,
    cells: tuple[int, int],
    slave_rows: set[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Collect all edge and face H(curl) rows on both cells of one facet."""

    facet_edges = np.asarray(facet_to_edge.links(int(facet)), dtype=np.int32)
    local_records: dict[int, tuple[int, int, bool]] = {}
    excluded: set[int] = set()
    for cell in cells:
        cell_facets = np.asarray(cell_to_facet.links(int(cell)), dtype=np.int32)
        local_faces = np.flatnonzero(cell_facets == int(facet))
        if local_faces.size != 1:
            raise RuntimeError("interface facet does not have one local cell-face index")
        local_face = int(local_faces[0])
        cell_edges = np.asarray(cell_to_edge.links(int(cell)), dtype=np.int32)
        local_edge_ids: list[int] = []
        for edge in facet_edges:
            matches = np.flatnonzero(cell_edges == int(edge))
            if matches.size != 1:
                raise RuntimeError("interface facet edge is not closed in its cell")
            local_edge_ids.append(int(matches[0]))

        positions: list[int] = []
        for local_edge in local_edge_ids:
            positions.extend(
                int(value)
                for value in V.dofmap.dof_layout.entity_dofs(1, local_edge)
            )
        positions.extend(
            int(value)
            for value in V.dofmap.dof_layout.entity_dofs(2, local_face)
        )
        cell_dofs = np.asarray(V.dofmap.cell_dofs(int(cell)), dtype=np.int32)
        local_dofs = cell_dofs[np.asarray(positions, dtype=np.int32)]
        global_dofs, owners, _owned = _local_dof_global_info(V, local_dofs)
        for local_dof, global_dof, owner in zip(
            local_dofs, global_dofs, owners, strict=True
        ):
            local_int = int(local_dof)
            if local_int in slave_rows:
                excluded.add(local_int)
                continue
            global_int = int(global_dof)
            record = (local_int, int(owner), local_int < int(V.dofmap.index_map.size_local))
            previous = local_records.get(global_int)
            if previous is not None and previous != record:
                if previous[1] != record[1]:
                    raise RuntimeError("one interface row has conflicting owners")
                if previous[2] and not record[2]:
                    continue
            local_records[global_int] = record

    ordered = sorted(local_records.items())
    return (
        np.asarray([item[1][0] for item in ordered], dtype=np.int32),
        np.asarray([item[0] for item in ordered], dtype=np.int64),
        np.asarray([item[1][1] for item in ordered], dtype=np.int32),
        np.asarray(sorted(excluded), dtype=np.int32),
    )


def _interface_material_tag(lower: MaterialSignature, upper: MaterialSignature) -> int:
    return 100 + 10 * int(lower.tag) + int(upper.tag)


def _classify_material_pair(
    lower: MaterialSignature,
    upper: MaterialSignature,
) -> str:
    return (
        "homogeneous"
        if np.isclose(lower.epsilon_r, upper.epsilon_r, rtol=0.0, atol=1.0e-13)
        and np.isclose(lower.mu_r, upper.mu_r, rtol=0.0, atol=1.0e-13)
        else "nonhomogeneous"
    )


def _global_material_pairs(
    comm: MPI.Comm,
    facets: tuple[InterfaceFacet, ...],
) -> tuple[tuple[int, MaterialSignature, MaterialSignature], ...]:
    """Return one deterministic material inventory for every MPI rank."""

    local_error = ""
    local_pairs: tuple[tuple[int, MaterialSignature, MaterialSignature], ...] = ()
    try:
        by_tag: dict[int, tuple[MaterialSignature, MaterialSignature]] = {}
        for facet in facets:
            pair = (facet.lower_material, facet.upper_material)
            previous = by_tag.setdefault(int(facet.interface_tag), pair)
            if tuple(map(_material_key, previous)) != tuple(map(_material_key, pair)):
                raise RuntimeError("one interface tag has inconsistent material sides")
        local_pairs = tuple(
            (tag, pair[0], pair[1]) for tag, pair in sorted(by_tag.items())
        )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"

    failed = comm.allreduce(bool(local_error), op=MPI.LOR)
    if failed:
        errors = comm.allgather(local_error)
        message = next(error for error in errors if error)
        message = comm.bcast(message if comm.rank == 0 else None, root=0)
        raise RuntimeError(f"T4 material inventory preflight failed: {message}")

    reports = comm.allgather(local_pairs)
    by_tag: dict[int, tuple[MaterialSignature, MaterialSignature]] = {}
    for report in reports:
        for tag, lower, upper in report:
            pair = (lower, upper)
            previous = by_tag.setdefault(int(tag), pair)
            if tuple(map(_material_key, previous)) != tuple(map(_material_key, pair)):
                raise RuntimeError("global material inventory has conflicting sides")
    return tuple(
        (tag, pair[0], pair[1]) for tag, pair in sorted(by_tag.items())
    )


def _cell_owner_rank(index_map: Any, local_cell: int, rank: int) -> int:
    if int(local_cell) < int(index_map.size_local):
        return int(rank)
    return int(np.asarray(index_map.owners, dtype=np.int32)[int(local_cell) - int(index_map.size_local)])


def _local_interface_routes(
    msh: mesh.Mesh,
    facet_to_cell: Any,
    facet_geometry: list[np.ndarray],
    cell_midpoints: np.ndarray,
    cell_map: Any,
    tolerance: float,
    interface_z: float,
) -> tuple[tuple[int, int, int], ...]:
    """Return owner/side-owner routes from owned and ghost facet copies."""

    facet_map = msh.topology.index_map(msh.topology.dim - 1)
    routes: list[tuple[int, int, int]] = []
    for facet, coordinates in enumerate(facet_geometry):
        if not np.allclose(coordinates[:, 2], interface_z, rtol=0.0, atol=tolerance):
            continue
        adjacent = tuple(int(value) for value in facet_to_cell.links(facet))
        if len(adjacent) != 2:
            continue
        lower, upper = sorted(adjacent, key=lambda cell: float(cell_midpoints[cell, 2]))
        facet_owner = (
            msh.comm.rank
            if facet < int(facet_map.size_local)
            else int(np.asarray(facet_map.owners, dtype=np.int32)[facet - int(facet_map.size_local)])
        )
        routes.append(
            (
                facet_owner,
                _cell_owner_rank(cell_map, lower, msh.comm.rank),
                _cell_owner_rank(cell_map, upper, msh.comm.rank),
            )
        )
    return tuple(routes)


def _canonical_record(facet: InterfaceFacet) -> dict[str, object]:
    return {
        "facet_key": [list(point) for point in facet.key],
        "classification": facet.classification,
        "lower_material": list(_material_key(facet.lower_material)),
        "upper_material": list(_material_key(facet.upper_material)),
        "trace_row_count": len(facet.trace_global_rows),
    }


def _canonical_identity(
    comm: MPI.Comm,
    facets: tuple[InterfaceFacet, ...],
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    str,
    str,
    int,
]:
    local_records = tuple(
        sorted(
            (_canonical_record(facet) for facet in facets),
            key=lambda record: json.dumps(record, sort_keys=True),
        )
    )
    local_payload = json.dumps(local_records, sort_keys=True, separators=(",", ":")).encode()
    gathered = comm.gather(local_records, root=0)
    result: tuple[str, str, int] | None = None
    if comm.rank == 0:
        error = ""
        try:
            by_facet: dict[str, dict[str, object]] = {}
            for report in gathered:
                for record in report:
                    key = json.dumps(record["facet_key"], separators=(",", ":"))
                    previous = by_facet.setdefault(key, record)
                    if previous != record:
                        raise RuntimeError(
                            "partition copies disagree on interface metadata"
                        )
            global_records = tuple(
                sorted(
                    by_facet.values(),
                    key=lambda record: json.dumps(record, sort_keys=True),
                )
            )
            payload = json.dumps(
                global_records, sort_keys=True, separators=(",", ":")
            ).encode()
            result = ("", hashlib.sha256(payload).hexdigest(), len(global_records))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            result = (error, "", -1)
    error, canonical_sha, global_count = comm.bcast(result, root=0)
    if error:
        raise RuntimeError(f"canonical interface identity failed: {error}")
    return (
        local_records,
        local_records,
        canonical_sha,
        hashlib.sha256(local_payload).hexdigest(),
        global_count,
    )


def _communication_plan(
    comm: MPI.Comm,
    routes: tuple[tuple[int, int, int], ...],
) -> NeighborPlan:
    forward_send: set[int] = set()
    forward_recv: set[int] = set()
    backward_send: set[int] = set()
    backward_recv: set[int] = set()
    lower_participants: set[int] = set()
    upper_participants: set[int] = set()
    for facet_owner, lower, upper in routes:
        facet_owner = int(facet_owner)
        lower = int(lower)
        upper = int(upper)
        lower_participants.update((facet_owner, lower))
        upper_participants.update((facet_owner, upper))
        if lower == comm.rank and facet_owner != comm.rank:
            forward_send.add(facet_owner)
            backward_recv.add(facet_owner)
        if facet_owner == comm.rank and lower != comm.rank:
            forward_recv.add(lower)
            backward_send.add(lower)
        if facet_owner == comm.rank and upper != comm.rank:
            forward_send.add(upper)
            backward_recv.add(upper)
        if upper == comm.rank and facet_owner != comm.rank:
            forward_recv.add(facet_owner)
            backward_send.add(facet_owner)
    return NeighborPlan(
        forward_send_peers=tuple(sorted(forward_send)),
        forward_recv_peers=tuple(sorted(forward_recv)),
        backward_send_peers=tuple(sorted(backward_send)),
        backward_recv_peers=tuple(sorted(backward_recv)),
        lower_participant_ranks=tuple(sorted(lower_participants)),
        upper_participant_ranks=tuple(sorted(upper_participants)),
    )


def build_fullspace_slab_interface(
    V: Any,
    mesh_data: Any,
    floquet_data: Any,
    cfg: SimulationConfig3D,
) -> InterfaceTopology:
    """Build the real owner-local two-slab interface topology."""

    msh = V.mesh
    comm = msh.comm
    cell_name = str(msh.basix_cell()).lower()
    if "hexahedron" not in cell_name and "tetrahedron" not in cell_name:
        raise NotImplementedError("T4 topology requires a hexahedron or tetrahedron mesh")
    if int(V.dofmap.index_map_bs) != 1:
        raise NotImplementedError("T4 topology requires scalar-blocked H(curl) DoFs")
    if FULLSPACE_T4_SLAB_COUNT != 2:
        raise RuntimeError("full3d_scalable_v1 T4 lane must retain two slabs")

    tdim = msh.topology.dim
    fdim = tdim - 1
    msh.topology.create_connectivity(tdim, fdim)
    msh.topology.create_connectivity(fdim, tdim)
    msh.topology.create_connectivity(tdim, 1)
    msh.topology.create_connectivity(fdim, 1)
    cell_to_facet = msh.topology.connectivity(tdim, fdim)
    facet_to_cell = msh.topology.connectivity(fdim, tdim)
    cell_to_edge = msh.topology.connectivity(tdim, 1)
    facet_to_edge = msh.topology.connectivity(fdim, 1)
    facet_map = msh.topology.index_map(fdim)
    cell_map = msh.topology.index_map(tdim)
    tolerance = mesh_coordinate_tolerance(msh)
    num_cells = int(cell_map.size_local + cell_map.num_ghosts)
    cell_indices = np.arange(num_cells, dtype=np.int32)
    cell_geometry = _entity_geometry(msh, tdim, cell_indices)
    cell_midpoints = np.asarray(
        [np.mean(coordinates, axis=0) for coordinates in cell_geometry],
        dtype=np.float64,
    )
    materials, cell_tag_scope, cell_tag_request_count = _cell_materials(
        msh, mesh_data, cfg
    )

    slab_ids = np.empty(int(cell_map.size_local), dtype=np.int8)
    for cell in range(num_cells):
        z_min = float(np.min(cell_geometry[cell][:, 2]))
        z_max = float(np.max(cell_geometry[cell][:, 2]))
        if z_min < cfg.interface_z - tolerance and z_max > cfg.interface_z + tolerance:
            raise ValueError("a T4 cell crosses cfg.interface_z")
        midpoint_z = float(cell_midpoints[cell, 2])
        if abs(midpoint_z - cfg.interface_z) <= tolerance:
            raise ValueError("a T4 cell midpoint lies on cfg.interface_z")
        if cell < int(cell_map.size_local):
            slab_ids[cell] = 0 if midpoint_z < cfg.interface_z else 1

    slave_rows = {int(value) for value in np.asarray(floquet_data.local_slave_dofs)}
    excluded_slave_rows: set[int] = set()
    facets: list[InterfaceFacet] = []
    owned_facet_indices: list[int] = []
    facet_tag_values: list[int] = []
    all_facet_geometry = _entity_geometry(
        msh,
        fdim,
        np.arange(int(facet_map.size_local + facet_map.num_ghosts), dtype=np.int32),
    )
    local_routes = _local_interface_routes(
        msh,
        facet_to_cell,
        all_facet_geometry,
        cell_midpoints,
        cell_map,
        tolerance,
        float(cfg.interface_z),
    )
    facet_geometry = all_facet_geometry[: int(facet_map.size_local)]
    for facet, coordinates in enumerate(facet_geometry):
        if not np.allclose(
            coordinates[:, 2],
            float(cfg.interface_z),
            rtol=0.0,
            atol=tolerance,
        ):
            continue
        adjacent = tuple(int(value) for value in facet_to_cell.links(facet))
        if len(adjacent) != 2:
            raise RuntimeError("T4 interface facet must have two adjacent cells")
        lower, upper = sorted(adjacent, key=lambda cell: float(cell_midpoints[cell, 2]))
        if not (
            cell_midpoints[lower, 2] < cfg.interface_z - tolerance
            and cell_midpoints[upper, 2] > cfg.interface_z + tolerance
        ):
            raise RuntimeError("T4 interface facet does not close lower/upper slabs")
        trace_local, trace_global, owners, excluded = _trace_rows_for_facet(
            V,
            cell_to_facet,
            cell_to_edge,
            facet_to_edge,
            facet,
            (lower, upper),
            slave_rows,
        )
        excluded_slave_rows.update(int(value) for value in excluded)
        if trace_global.size == 0:
            raise RuntimeError("T4 interface facet has no active H(curl) trace rows")
        lower_material = materials[lower]
        upper_material = materials[upper]
        classification = _classify_material_pair(lower_material, upper_material)
        interface_tag = _interface_material_tag(lower_material, upper_material)
        key = canonical_entity_key(coordinates, tolerance)
        lower_owner = _cell_owner_rank(cell_map, lower, comm.rank)
        upper_owner = _cell_owner_rank(cell_map, upper, comm.rank)
        lower_participants = tuple(sorted({comm.rank, lower_owner}))
        upper_participants = tuple(sorted({comm.rank, upper_owner}))
        record = InterfaceFacet(
            local_index=int(facet),
            key=key,
            lower_cell_global=_cell_global_index(cell_map, lower),
            upper_cell_global=_cell_global_index(cell_map, upper),
            lower_cell_owner=lower_owner,
            upper_cell_owner=upper_owner,
            lower_participant_ranks=lower_participants,
            upper_participant_ranks=upper_participants,
            lower_material=lower_material,
            upper_material=upper_material,
            classification=classification,
            interface_tag=interface_tag,
            trace_local_rows=tuple(int(value) for value in trace_local),
            trace_global_rows=tuple(int(value) for value in trace_global),
            trace_owners=tuple(int(value) for value in owners),
        )
        facets.append(record)
        owned_facet_indices.append(int(facet))
        facet_tag_values.append(interface_tag)

    local_owned_globals: dict[int, int] = {}
    local_ghost_globals: dict[int, tuple[int, int]] = {}
    for facet in facets:
        for local, global_row, owner in zip(
            facet.trace_local_rows,
            facet.trace_global_rows,
            facet.trace_owners,
            strict=True,
        ):
            if int(owner) == comm.rank:
                local_owned_globals[int(global_row)] = int(local)
            else:
                local_ghost_globals[int(global_row)] = (int(local), int(owner))
    owned_order = sorted(local_owned_globals.items())
    ghost_order = sorted(local_ghost_globals.items())
    owned_global_rows = np.asarray([row for row, _local in owned_order], dtype=np.int64)
    owned_local_rows = np.asarray([local for _row, local in owned_order], dtype=np.int32)
    ghost_global_rows = np.asarray([row for row, _record in ghost_order], dtype=np.int64)
    ghost_local_rows = np.asarray(
        [record[0] for _row, record in ghost_order], dtype=np.int32
    )
    ghost_owners = np.asarray(
        [record[1] for _row, record in ghost_order], dtype=np.int32
    )
    global_material_pairs = _global_material_pairs(comm, tuple(facets))
    plan = _communication_plan(comm, local_routes)
    (
        canonical_manifest,
        local_canonical_manifest,
        canonical_sha,
        local_canonical_sha,
        canonical_global_count,
    ) = _canonical_identity(comm, tuple(facets))
    if canonical_global_count == 0:
        raise RuntimeError("no cfg.interface_z interior facets were found")
    interface_tags = mesh.meshtags(
        msh,
        fdim,
        np.asarray(owned_facet_indices, dtype=np.int32),
        np.asarray(facet_tag_values, dtype=np.int32),
    )
    audit = {
        "profile": FULLSPACE_SCALABLE_PROFILE,
        "slab_count": FULLSPACE_T4_SLAB_COUNT,
        "transmission": FULLSPACE_T4_TRANSMISSION,
        "trace_weight": FULLSPACE_T4_TRACE_WEIGHT,
        "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
        "phase_application": "finalized_floquet_mpc_once",
        "bounded_material_class_collective": True,
        "material_class_collective": "bounded_inventory_allgather_with_error_allreduce",
        "cell_tag_scope": cell_tag_scope,
        "cell_tag_request_count": cell_tag_request_count,
        "communication_plan_collective": "none_owner_local_owned_ghost_routes",
        "canonical_identity_collective": "root_only_digest_count_gather_bcast",
        "numeric_allgather": False,
        "global_aij_materialized": False,
        "dense_interface_mass_materialized": False,
        "dense_interface_schur_materialized": False,
        "slab_factor_materialized": False,
        "slave_rows_excluded": True,
        "excluded_slave_count": len(excluded_slave_rows),
        "canonical_identity_kind": "root_only_owned_facet_digest_count",
        "global_material_pair_inventory": [
            {
                "interface_tag": int(tag),
                "lower_material": list(_material_key(lower)),
                "upper_material": list(_material_key(upper)),
            }
            for tag, lower, upper in global_material_pairs
        ],
        "canonical_global_facet_count": canonical_global_count,
        "canonical_local_facet_count": len(local_canonical_manifest),
        "canonical_manifest_scope": "rank_owned_facets_only",
        "interface_classifications": sorted(
            {
                _classify_material_pair(lower, upper)
                for _tag, lower, upper in global_material_pairs
            }
        ),
        "lower_upper_trace_maps": True,
        "forward_send_peers": list(plan.forward_send_peers),
        "forward_recv_peers": list(plan.forward_recv_peers),
        "backward_send_peers": list(plan.backward_send_peers),
        "backward_recv_peers": list(plan.backward_recv_peers),
        "lower_participant_ranks": list(plan.lower_participant_ranks),
        "upper_participant_ranks": list(plan.upper_participant_ranks),
    }
    topology = InterfaceTopology(
        mesh=msh,
        function_space=V,
        floquet_data=floquet_data,
        cfg=cfg,
        profile=FULLSPACE_SCALABLE_PROFILE,
        interface_z=float(cfg.interface_z),
        tolerance=float(tolerance),
        facets=tuple(facets),
        global_material_pairs=global_material_pairs,
        interface_facet_indices=np.asarray(owned_facet_indices, dtype=np.int32),
        interface_facet_tag_values=np.asarray(facet_tag_values, dtype=np.int32),
        interface_facet_tags=interface_tags,
        owned_trace_global_rows=owned_global_rows,
        owned_trace_local_rows=owned_local_rows,
        ghost_trace_global_rows=ghost_global_rows,
        ghost_trace_local_rows=ghost_local_rows,
        ghost_trace_owners=ghost_owners,
        excluded_slave_local_rows=np.asarray(sorted(excluded_slave_rows), dtype=np.int32),
        owned_slab_ids=slab_ids,
        neighbor_plan=plan,
        volume_owned_size=int(V.dofmap.index_map.size_local),
        canonical_manifest=canonical_manifest,
        local_canonical_manifest=local_canonical_manifest,
        canonical_sha256=canonical_sha,
        local_canonical_sha256=local_canonical_sha,
        canonical_global_count=canonical_global_count,
        audit=audit,
    )
    return topology


def _robin_coefficient(cfg: SimulationConfig3D, material: MaterialSignature) -> complex:
    """Return q=-i beta in nm^-1 under the current zero-order sign convention."""

    return complex(-1j * cfg.k0 * material.refractive_index)


def _facet_materials(topology: InterfaceTopology) -> tuple[tuple[int, MaterialSignature, MaterialSignature], ...]:
    return topology.global_material_pairs


def _tangential_robin_form(
    V: Any,
    topology: InterfaceTopology,
    direction: str,
) -> Any:
    """Candidate form builder: a real interior-facet tangential action."""

    if direction not in {"forward", "backward"}:
        raise ValueError("direction must be 'forward' or 'backward'")
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    u_plus = u("+")
    v_plus = v("+")
    u_t = ufl.as_vector((u_plus[0], u_plus[1], 0.0))
    v_t = ufl.as_vector((v_plus[0], v_plus[1], 0.0))
    dS = ufl.Measure(
        "dS",
        domain=topology.mesh,
        subdomain_data=topology.interface_facet_tags,
    )
    form = 0
    for tag, lower, upper in _facet_materials(topology):
        material = upper if direction == "forward" else lower
        form += _robin_coefficient(topology.cfg, material) * ufl.inner(u_t, v_t) * dS(tag)
    return form


class FirstOrderImpedanceTransmission:
    """Matrix-free candidate A using owner-local facet assembly."""

    def __init__(
        self,
        V: Any,
        topology: InterfaceTopology,
        *,
        mpc: Any | None = None,
    ) -> None:
        self.topology = topology
        self.mpc = mpc
        self.function_space = mpc.function_space if mpc is not None else V

        self._actions = {
            direction: build_fullspace_mpc_form_action(
                _tangential_robin_form(self.function_space, topology, direction),
                self.function_space,
                mpc=mpc,
            )
            for direction in ("forward", "backward")
        }
        self._audit = {
            "candidate": "A",
            "action": "interior_facet_tangential_robin_weak_form",
            "transmission": FULLSPACE_T4_TRANSMISSION,
            "physical_q": "-i*k0*sqrt(epsilon_r*mu_r)",
            "units": "nm^-1",
            "phase_application": "finalized_floquet_mpc_once" if mpc is not None else "none",
            "backend": "build_fullspace_mpc_form_action_owner_local",
            "global_aij_materialized": False,
            "dense_interface_mass_materialized": False,
            "dense_interface_schur_materialized": False,
            "slab_factor_materialized": False,
            "numeric_allgather": False,
        }

    @property
    def audit(self) -> Mapping[str, object]:
        return dict(self._audit)

    def apply(self, source: Any, direction: str) -> Any:
        """Apply the facet weak form to a PETSc vector, without a matrix."""

        if direction not in self._actions:
            raise ValueError("direction must be 'forward' or 'backward'")
        return self._actions[direction].apply(source).copy()

    def destroy(self) -> None:
        for action in self._actions.values():
            action.destroy()


__all__ = [
    "FULLSPACE_SCALABLE_PROFILE",
    "FULLSPACE_T4_SLAB_COUNT",
    "FULLSPACE_T4_TRACE_WEIGHT",
    "FULLSPACE_T4_TRANSMISSION",
    "FirstOrderImpedanceTransmission",
    "InterfaceFacet",
    "InterfaceTopology",
    "MaterialSignature",
    "NeighborPlan",
    "build_fullspace_slab_interface",
]
