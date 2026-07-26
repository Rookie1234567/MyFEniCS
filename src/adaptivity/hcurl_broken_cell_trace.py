"""Bind physical local-h trace constraints to DOLFINx entity ordering.

The physical constraint graph in :mod:`hcurl_broken_trace_graph` deliberately
does not depend on DOLFINx global entity numbers.  Compiled cell tensors,
however, are oriented into the DOLFINx-owned edge and face coefficient order
before insertion.  This module is the explicit bridge between those two
authorities:

* every DOLFINx edge/face is matched to one quantized physical entity;
* canonical physical coefficients are transformed into the DOLFINx entity
  ordering exactly once;
* hanging and Floquet slaves are substituted to partition-independent root
  rows; and
* each owned cell receives one dense local expansion suitable for
  ``C_K^H S_K C_K`` insertion.

No full p6 trace matrix and no hanging/Floquet slave row is introduced by this
binding.  The module remains opt-in and does not change the ordinary assembly
default.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from dolfinx import mesh as dmesh
from mpi4py import MPI
import numpy as np
from scipy import sparse

from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)

from .dyadic_hexa_broken_mesh import BrokenDyadicHexCarrier
from .dyadic_hexa_refinement import BalancedDyadicHexForest
from .hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
)
from .exact_sequence_variable_p import build_variable_p_reference_space
from .variable_p_entity_map import VariablePGlobalEntityMap


@dataclass(frozen=True)
class BrokenHexTraceEntityBlock:
    """One DOLFINx trace entity expressed by physical independent roots."""

    dimension: int
    global_entity: int
    dolfinx_owner_rank: int
    active_vector_work_owner_rank: int
    physical_entity: PhysicalTraceEntity
    full_rows: np.ndarray
    independent_rows: np.ndarray
    full_from_independent: np.ndarray
    physical_from_independent: np.ndarray
    canonical_to_dolfinx: np.ndarray


@dataclass(frozen=True)
class BrokenHexCellTraceMap:
    """One owned cell's oriented trace expansion."""

    local_cell: int
    global_cell: int
    canonical_leaf: int
    independent_rows: np.ndarray
    full_trace_from_independent: np.ndarray


@dataclass(frozen=True)
class BrokenHexCellTraceConstraintMap:
    """Actual cell/PETSc binding for physical hanging and Floquet constraints."""

    entity_map: VariablePGlobalEntityMap
    authority: BrokenHexTraceConstraintAuthority
    entity_blocks: Mapping[tuple[int, int], BrokenHexTraceEntityBlock]
    work_owned_entity_blocks: tuple[BrokenHexTraceEntityBlock, ...]
    owned_cells: tuple[BrokenHexCellTraceMap, ...]
    independent_trace_rows: int
    component_gram: np.ndarray | sparse.csr_matrix
    audit: Mapping[str, Any]


def _matrix_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).view(np.uint8)
    ).hexdigest()


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    array = np.asarray(values)
    return {
        "shape": list(array.shape),
        "dtype": np.dtype(array.dtype).str,
        "bytes_sha256": _matrix_sha256(array),
    }


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _balanced_ownership_ranges(
    total: int,
    size: int,
) -> tuple[tuple[int, int], ...]:
    quotient, remainder = divmod(int(total), int(size))
    counts = tuple(
        quotient + (1 if rank < remainder else 0)
        for rank in range(int(size))
    )
    ranges: list[tuple[int, int]] = []
    start = 0
    for count in counts:
        stop = start + count
        ranges.append((start, stop))
        start = stop
    if start != int(total):
        raise RuntimeError("balanced ownership ranges do not close")
    return tuple(ranges)


def _owner_of_row(
    row: int,
    ranges: tuple[tuple[int, int], ...],
) -> int:
    row = int(row)
    for rank, (start, stop) in enumerate(ranges):
        if start <= row < stop:
            return rank
    raise RuntimeError(f"row {row} is outside the ownership ranges")


def _quantize_point(
    point: np.ndarray,
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


def _geometry_key(
    dimension: int,
    points: tuple[tuple[int, int, int], ...],
) -> tuple[int, ...]:
    if int(dimension) == 1:
        if len(points) != 2:
            raise RuntimeError("edge geometry must contain two vertices")
        return tuple(value for point in sorted(points) for value in point)
    if int(dimension) != 2 or len(points) != 4:
        raise RuntimeError("face geometry must contain four vertices")
    values = np.asarray(points, dtype=np.int64)
    fixed = [
        axis
        for axis in range(3)
        if int(np.ptp(values[:, axis])) == 0
    ]
    if len(fixed) != 1:
        raise RuntimeError("physical trace face is not axis aligned")
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


def _canonical_to_dolfinx_transform(
    entity: PhysicalTraceEntity,
    ordered_points: tuple[tuple[int, int, int], ...],
    *,
    degree: int,
) -> tuple[np.ndarray, tuple[int, ...]]:
    try:
        permutation = tuple(
            entity.canonical_points.index(point) for point in ordered_points
        )
    except ValueError as exc:
        raise RuntimeError(
            "DOLFINx entity vertices differ from the physical trace entity"
        ) from exc
    if entity.dimension == 1:
        if permutation not in {(0, 1), (1, 0)}:
            raise RuntimeError("DOLFINx edge orientation is invalid")
        transform = edge_coefficient_transform(
            degree,
            reversed_orientation=permutation == (1, 0),
        )
    elif entity.dimension == 2:
        transform = face_coefficient_transform(degree, permutation)
    else:  # pragma: no cover - guarded by PhysicalTraceEntity
        raise RuntimeError("H(curl) trace entity must be an edge or face")
    return np.ascontiguousarray(transform), permutation


def _selected_graph_rows(
    authority: BrokenHexTraceConstraintAuthority,
    physical_rows: tuple[Any, ...],
) -> tuple[np.ndarray, np.ndarray]:
    row_index = {
        row: index for index, row in enumerate(authority.graph.raw_rows)
    }
    try:
        indices = np.asarray(
            [row_index[row] for row in physical_rows],
            dtype=np.int64,
        )
    except KeyError as exc:
        raise RuntimeError(
            "physical entity row is absent from the flattened trace graph"
        ) from exc
    graph = authority.graph.raw_from_independent
    if sparse.issparse(graph):
        selected = sparse.csr_matrix(graph)[indices].tocsr()
        independent = np.unique(selected.indices).astype(np.int64)
        values = np.asarray(
            selected[:, independent].toarray(),
            dtype=np.complex128,
        )
    else:
        selected = np.asarray(graph[indices], dtype=np.complex128)
        independent = np.flatnonzero(
            np.max(np.abs(selected), axis=0) > 0.0
        ).astype(np.int64)
        values = np.ascontiguousarray(selected[:, independent])
    if not len(independent):
        raise RuntimeError("one physical trace entity has no independent root")
    return independent, values


def _entity_block_sha256(block: BrokenHexTraceEntityBlock) -> str:
    return _json_sha256(
        {
            "dimension": int(block.dimension),
            "global_entity": int(block.global_entity),
            "dolfinx_owner_rank": int(block.dolfinx_owner_rank),
            "active_vector_work_owner_rank": int(
                block.active_vector_work_owner_rank
            ),
            "physical_geometry_key": list(
                block.physical_entity.geometry_key
            ),
            "full_rows": _array_identity(block.full_rows),
            "independent_rows": _array_identity(
                block.independent_rows
            ),
            "full_from_independent": _array_identity(
                block.full_from_independent
            ),
            "physical_from_independent": _array_identity(
                block.physical_from_independent
            ),
            "canonical_to_dolfinx": _array_identity(
                block.canonical_to_dolfinx
            ),
        }
    )


def _entity_block_native_array_bytes(
    block: BrokenHexTraceEntityBlock,
) -> int:
    return int(
        block.full_rows.nbytes
        + block.independent_rows.nbytes
        + block.full_from_independent.nbytes
        + block.physical_from_independent.nbytes
        + block.canonical_to_dolfinx.nbytes
    )


def _build_local_entity_records(
    entity_map: VariablePGlobalEntityMap,
    authority: BrokenHexTraceConstraintAuthority,
    *,
    by_physical: Mapping[
        tuple[int, tuple[int, ...]],
        PhysicalTraceEntity,
    ],
    origin: np.ndarray,
    tolerance: float,
    active_trace_ranges: tuple[tuple[int, int], ...],
) -> tuple[
    dict[tuple[int, tuple[int, ...]], BrokenHexTraceEntityBlock],
    dict[tuple[int, int], dict[str, Any]],
    list[dict[str, Any]],
    dict[str, int],
    dict[str, int],
    float,
]:
    """Build rank-local owned blocks before the first MPI exchange."""

    msh = entity_map.mesh
    comm = msh.comm
    topology = msh.topology
    owned_by_physical: dict[
        tuple[int, tuple[int, ...]],
        BrokenHexTraceEntityBlock,
    ] = {}
    local_crosswalk: dict[tuple[int, int], dict[str, Any]] = {}
    local_declarations: list[dict[str, Any]] = []
    local_owned_counts_by_dimension: dict[str, int] = {}
    local_ghost_counts_by_dimension: dict[str, int] = {}
    maximum_orthogonality_error = 0.0
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, 3)
        index_map = topology.index_map(dimension)
        owned = int(index_map.size_local)
        local_count = owned + int(index_map.num_ghosts)
        local_owned_counts_by_dimension[str(dimension)] = owned
        local_ghost_counts_by_dimension[str(dimension)] = int(
            index_map.num_ghosts
        )
        local_entities = np.arange(local_count, dtype=np.int32)
        global_entities = np.asarray(
            index_map.local_to_global(local_entities),
            dtype=np.int64,
        )
        geometry = dmesh.entities_to_geometry(
            msh,
            dimension,
            local_entities,
            permute=True,
        )
        for local_entity, global_entity, dofs in zip(
            local_entities,
            global_entities,
            geometry,
            strict=True,
        ):
            ordered_points = tuple(
                _quantize_point(
                    point,
                    origin=origin,
                    tolerance=tolerance,
                )
                for point in msh.geometry.x[np.asarray(dofs), :3]
            )
            geometry_key = _geometry_key(dimension, ordered_points)
            physical = by_physical.get((dimension, geometry_key))
            if physical is None:
                raise RuntimeError(
                    "DOLFINx trace entity has no physical graph identity"
                )
            try:
                permutation = tuple(
                    physical.canonical_points.index(point)
                    for point in ordered_points
                )
            except ValueError as exc:
                raise RuntimeError(
                    "local trace entity vertices differ from physical identity"
                ) from exc
            local_identity = (int(dimension), int(global_entity))
            if local_identity in local_crosswalk:
                raise RuntimeError("local trace crosswalk contains a duplicate")
            local_crosswalk[local_identity] = {
                "physical_identity": (
                    int(dimension),
                    tuple(physical.geometry_key),
                ),
                "ordered_points": ordered_points,
                "permutation": permutation,
            }
            if int(local_entity) >= owned:
                continue
            transform, permutation = _canonical_to_dolfinx_transform(
                physical,
                ordered_points,
                degree=authority.degree,
            )
            independent, physical_expansion = _selected_graph_rows(
                authority,
                physical.rows,
            )
            expansion = np.ascontiguousarray(
                transform @ physical_expansion
            )
            full_rows = np.asarray(
                entity_map.global_entity_rows[dimension][int(global_entity)],
                dtype=np.int64,
            )
            if len(full_rows) != expansion.shape[0]:
                raise RuntimeError(
                    "DOLFINx entity rows and physical mode count disagree"
                )
            orthogonality_error = float(
                np.max(
                    np.abs(
                        transform.conj().T @ transform
                        - np.eye(transform.shape[0])
                    ),
                    initial=0.0,
                )
            )
            maximum_orthogonality_error = max(
                maximum_orthogonality_error,
                orthogonality_error,
            )
            full_rows = np.ascontiguousarray(full_rows)
            independent = np.ascontiguousarray(independent)
            expansion = np.ascontiguousarray(expansion)
            physical_expansion = np.ascontiguousarray(
                physical_expansion
            )
            transform = np.ascontiguousarray(transform)
            for values in (
                full_rows,
                independent,
                expansion,
                physical_expansion,
                transform,
            ):
                values.setflags(write=False)
            physical_identity = (
                int(dimension),
                tuple(physical.geometry_key),
            )
            if physical_identity in owned_by_physical:
                raise RuntimeError(
                    "one rank owns duplicate physical trace entities"
                )
            block = BrokenHexTraceEntityBlock(
                dimension=int(dimension),
                global_entity=int(global_entity),
                dolfinx_owner_rank=int(comm.rank),
                active_vector_work_owner_rank=_owner_of_row(
                    int(full_rows[0]),
                    active_trace_ranges,
                ),
                physical_entity=physical,
                full_rows=full_rows,
                independent_rows=independent,
                full_from_independent=expansion,
                physical_from_independent=physical_expansion,
                canonical_to_dolfinx=transform,
            )
            owned_by_physical[physical_identity] = block
            local_declarations.append(
                {
                    "dimension": int(dimension),
                    "global_entity": int(global_entity),
                    "geometry_key": list(physical.geometry_key),
                    "ordered_points": [
                        list(point) for point in ordered_points
                    ],
                    "permutation": list(permutation),
                    "dolfinx_owner_rank": int(comm.rank),
                    "active_vector_work_owner_rank": int(
                        block.active_vector_work_owner_rank
                    ),
                    "full_rows_sha256": _matrix_sha256(full_rows),
                    "independent_rows_sha256": _matrix_sha256(independent),
                    "physical_expansion_sha256": _matrix_sha256(
                        physical_expansion
                    ),
                    "dolfinx_expansion_sha256": _matrix_sha256(expansion),
                    "canonical_to_dolfinx_sha256": _matrix_sha256(transform),
                    "block_sha256": _entity_block_sha256(block),
                }
            )
    return (
        owned_by_physical,
        local_crosswalk,
        local_declarations,
        local_owned_counts_by_dimension,
        local_ghost_counts_by_dimension,
        maximum_orthogonality_error,
    )


def _entity_records(
    entity_map: VariablePGlobalEntityMap,
    authority: BrokenHexTraceConstraintAuthority,
    *,
    origin: np.ndarray,
    tolerance: float,
) -> tuple[
    dict[tuple[int, int], BrokenHexTraceEntityBlock],
    tuple[BrokenHexTraceEntityBlock, ...],
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    dict[str, Any],
]:
    msh = entity_map.mesh
    comm = msh.comm
    topology = msh.topology
    by_physical = {
        (entity.dimension, entity.geometry_key): entity
        for entity in authority.entities
    }
    active_trace_ranges = _balanced_ownership_ranges(
        entity_map.active_trace_rows,
        comm.size,
    )
    local_declaration_error: str | None = None
    try:
        (
            owned_by_physical,
            local_crosswalk,
            local_declarations,
            local_owned_counts_by_dimension,
            local_ghost_counts_by_dimension,
            maximum_orthogonality_error,
        ) = _build_local_entity_records(
            entity_map,
            authority,
            by_physical=by_physical,
            origin=origin,
            tolerance=tolerance,
            active_trace_ranges=active_trace_ranges,
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        np.linalg.LinAlgError,
    ) as exc:
        owned_by_physical = {}
        local_crosswalk = {}
        local_declarations = []
        local_owned_counts_by_dimension = {}
        local_ghost_counts_by_dimension = {}
        maximum_orthogonality_error = 0.0
        local_declaration_error = f"{type(exc).__name__}: {exc}"
    declaration_packets = comm.allgather(
        (tuple(local_declarations), local_declaration_error)
    )
    declaration_errors = [
        f"rank {rank}: {error}"
        for rank, (_records, error) in enumerate(declaration_packets)
        if error is not None
    ]
    if declaration_errors:
        raise RuntimeError(
            "trace entity declaration failed collectively: "
            + "; ".join(declaration_errors[:4])
        )
    declarations = [
        record
        for packet, _error in declaration_packets
        for record in packet
    ]
    expected = sum(
        int(entity_map.mesh.topology.index_map(dimension).size_global)
        for dimension in (1, 2)
    )
    declaration_by_physical: dict[
        tuple[int, tuple[int, ...]],
        dict[str, Any],
    ] = {}
    declaration_by_global: dict[tuple[int, int], dict[str, Any]] = {}
    for declaration in declarations:
        physical_identity = (
            int(declaration["dimension"]),
            tuple(map(int, declaration["geometry_key"])),
        )
        global_identity = (
            int(declaration["dimension"]),
            int(declaration["global_entity"]),
        )
        if (
            physical_identity in declaration_by_physical
            or global_identity in declaration_by_global
        ):
            raise RuntimeError(
                "trace entity declarations contain duplicate owners"
            )
        declaration_by_physical[physical_identity] = declaration
        declaration_by_global[global_identity] = declaration
    if len(declarations) != expected:
        raise RuntimeError("DOLFINx trace entity declarations are incomplete")
    if len(declarations) != len(authority.entities):
        raise RuntimeError("physical and DOLFINx trace catalogs differ")

    local_errors: list[str] = []
    for global_identity, local in local_crosswalk.items():
        declaration = declaration_by_global.get(global_identity)
        if declaration is None:
            local_errors.append(
                f"missing declaration for global entity {global_identity}"
            )
            continue
        declared_physical = (
            int(declaration["dimension"]),
            tuple(map(int, declaration["geometry_key"])),
        )
        if declared_physical != local["physical_identity"]:
            local_errors.append(
                f"physical-key mismatch for global entity {global_identity}"
            )
        if (
            tuple(
                tuple(map(int, point))
                for point in declaration["ordered_points"]
            )
            != local["ordered_points"]
            or tuple(map(int, declaration["permutation"]))
            != local["permutation"]
        ):
            local_errors.append(
                f"orientation mismatch for global entity {global_identity}"
            )
    crosswalk_error_packets = comm.allgather(tuple(local_errors))
    crosswalk_errors = [
        f"rank {rank}: {error}"
        for rank, packet in enumerate(crosswalk_error_packets)
        for error in packet
    ]
    if crosswalk_errors:
        raise RuntimeError(
            "collective trace declaration crosswalk failed: "
            + "; ".join(crosswalk_errors[:4])
        )

    cell_needed_physical: set[tuple[int, tuple[int, ...]]] = set()
    needed_physical: set[tuple[int, tuple[int, ...]]] = set()
    outbound_requests: list[list[dict[str, Any]]] = [
        [] for _ in range(int(comm.size))
    ]
    expected_requests: dict[str, dict[str, Any]] = {}
    local_request_prep_error: str | None = None
    try:
        for cell in entity_map.owned_cells:
            for dimension in (1, 2):
                index_map = topology.index_map(dimension)
                global_entities = np.asarray(
                    index_map.local_to_global(
                        np.asarray(
                            cell.entity_ids[dimension],
                            dtype=np.int32,
                        )
                    ),
                    dtype=np.int64,
                )
                for global_entity in global_entities:
                    cell_needed_physical.add(
                        local_crosswalk[
                            (dimension, int(global_entity))
                        ]["physical_identity"]
                    )
        needed_physical.update(cell_needed_physical)
        needed_physical.update(
            physical_identity
            for physical_identity, declaration in (
                declaration_by_physical.items()
            )
            if int(declaration["active_vector_work_owner_rank"])
            == int(comm.rank)
        )
        for physical_identity in sorted(needed_physical):
            declaration = declaration_by_physical[physical_identity]
            owner_rank = int(declaration["dolfinx_owner_rank"])
            if owner_rank == int(comm.rank):
                continue
            request = {
                "requester_rank": int(comm.rank),
                "dimension": physical_identity[0],
                "geometry_key": list(physical_identity[1]),
                "expected_owner_rank": owner_rank,
                "expected_block_sha256": str(
                    declaration["block_sha256"]
                ),
            }
            request["token"] = _json_sha256(request)
            outbound_requests[owner_rank].append(request)
            expected_requests[str(request["token"])] = request
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        local_request_prep_error = f"{type(exc).__name__}: {exc}"
    request_prep_packets = comm.allgather(local_request_prep_error)
    request_prep_errors = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(request_prep_packets)
        if error is not None
    ]
    if request_prep_errors:
        raise RuntimeError(
            "trace entity request preparation failed collectively: "
            + "; ".join(request_prep_errors[:4])
        )
    inbound_requests = comm.alltoall(outbound_requests)

    outbound_replies: list[list[dict[str, Any]]] = [
        [] for _ in range(int(comm.size))
    ]
    local_routing_errors: list[str] = []
    local_reply_array_bytes = 0
    request_keys = {
        "requester_rank",
        "dimension",
        "geometry_key",
        "expected_owner_rank",
        "expected_block_sha256",
        "token",
    }
    for requester_rank, packet in enumerate(inbound_requests):
        seen_tokens: set[str] = set()
        for request in packet:
            token = ""
            error: str | None = None
            block: BrokenHexTraceEntityBlock | None = None
            try:
                if not isinstance(request, Mapping):
                    raise TypeError("request is not a mapping")
                token = str(request.get("token", ""))
                if set(request) != request_keys:
                    raise ValueError("request keys differ from the protocol")
                unsigned_request = {
                    key: request[key] for key in request if key != "token"
                }
                if token != _json_sha256(unsigned_request):
                    raise ValueError("request token integrity mismatch")
                if token in seen_tokens:
                    raise ValueError("duplicate request token")
                seen_tokens.add(token)
                physical_identity = (
                    int(request["dimension"]),
                    tuple(map(int, request["geometry_key"])),
                )
                block = owned_by_physical.get(physical_identity)
                if int(request["requester_rank"]) != requester_rank:
                    raise ValueError("requester rank mismatch")
                if int(request["expected_owner_rank"]) != int(comm.rank):
                    raise ValueError("wrong declared owner")
                if block is None:
                    raise ValueError("requested entity is not owned")
                if str(request["expected_block_sha256"]) != (
                    _entity_block_sha256(block)
                ):
                    raise ValueError("stale block identity")
            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
            ) as exc:
                error = f"{type(exc).__name__}: {exc}"
            if error is not None:
                local_routing_errors.append(
                    f"rank {requester_rank} token {token}: {error}"
                )
                outbound_replies[requester_rank].append(
                    {"token": token, "error": error}
                )
                continue
            try:
                if block is None:
                    raise RuntimeError("validated request has no owned block")
                reply = {
                    "token": token,
                    "error": None,
                    "dimension": int(block.dimension),
                    "global_entity": int(block.global_entity),
                    "geometry_key": list(
                        block.physical_entity.geometry_key
                    ),
                    "dolfinx_owner_rank": int(block.dolfinx_owner_rank),
                    "active_vector_work_owner_rank": int(
                        block.active_vector_work_owner_rank
                    ),
                    "full_rows": np.asarray(block.full_rows),
                    "independent_rows": np.asarray(block.independent_rows),
                    "full_from_independent": np.asarray(
                        block.full_from_independent
                    ),
                    "physical_from_independent": np.asarray(
                        block.physical_from_independent
                    ),
                    "canonical_to_dolfinx": np.asarray(
                        block.canonical_to_dolfinx
                    ),
                    "block_sha256": _entity_block_sha256(block),
                }
                local_reply_array_bytes += sum(
                    int(np.asarray(reply[name]).nbytes)
                    for name in (
                        "full_rows",
                        "independent_rows",
                        "full_from_independent",
                        "physical_from_independent",
                        "canonical_to_dolfinx",
                    )
                )
                outbound_replies[requester_rank].append(reply)
            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
            ) as exc:
                error = f"{type(exc).__name__}: {exc}"
                local_routing_errors.append(
                    f"rank {requester_rank} token {token}: {error}"
                )
                outbound_replies[requester_rank].append(
                    {"token": token, "error": error}
                )
    inbound_replies = comm.alltoall(outbound_replies)

    received_by_token: dict[str, dict[str, Any]] = {}
    local_received_reply_array_bytes = 0
    success_reply_keys = {
        "token",
        "error",
        "dimension",
        "global_entity",
        "geometry_key",
        "dolfinx_owner_rank",
        "active_vector_work_owner_rank",
        "full_rows",
        "independent_rows",
        "full_from_independent",
        "physical_from_independent",
        "canonical_to_dolfinx",
        "block_sha256",
    }
    error_reply_keys = {"token", "error"}
    for owner_rank, packet in enumerate(inbound_replies):
        for reply in packet:
            token = ""
            try:
                if not isinstance(reply, Mapping):
                    raise TypeError("reply is not a mapping")
                token = str(reply.get("token", ""))
                if token in received_by_token:
                    raise ValueError("duplicate reply token")
                expected_request = expected_requests.get(token)
                if expected_request is None:
                    raise ValueError("unrequested reply token")
                if owner_rank != int(
                    expected_request["expected_owner_rank"]
                ):
                    raise ValueError("wrong reply owner")
                if reply.get("error") is not None:
                    if set(reply) != error_reply_keys:
                        raise ValueError(
                            "error reply keys differ from the protocol"
                        )
                    raise ValueError(
                        f"owner rejected request: {reply['error']}"
                    )
                if set(reply) != success_reply_keys:
                    raise ValueError(
                        "success reply keys differ from the protocol"
                    )
                local_received_reply_array_bytes += sum(
                    int(np.asarray(reply[name]).nbytes)
                    for name in (
                        "full_rows",
                        "independent_rows",
                        "full_from_independent",
                        "physical_from_independent",
                        "canonical_to_dolfinx",
                    )
                )
            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
            ) as exc:
                local_routing_errors.append(
                    f"rank {owner_rank} token {token}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            received_by_token[token] = reply
    missing_tokens = set(expected_requests) - set(received_by_token)
    if missing_tokens:
        local_routing_errors.append(
            f"missing reply tokens: {sorted(missing_tokens)[:3]}"
        )
    routing_error_packets = comm.allgather(tuple(local_routing_errors))
    routing_errors = [
        f"rank {rank}: {error}"
        for rank, packet in enumerate(routing_error_packets)
        for error in packet
    ]
    if routing_errors:
        raise RuntimeError(
            "owner-routed trace lookup failed collectively: "
            + "; ".join(routing_errors[:4])
        )

    cache_by_physical: dict[
        tuple[int, tuple[int, ...]],
        BrokenHexTraceEntityBlock,
    ] = {
        identity: owned_by_physical[identity]
        for identity in needed_physical
        if identity in owned_by_physical
    }
    local_rebuild_errors: list[str] = []
    for token, request in expected_requests.items():
        try:
            reply = received_by_token[token]
            physical_identity = (
                int(reply["dimension"]),
                tuple(map(int, reply["geometry_key"])),
            )
            declaration = declaration_by_physical[physical_identity]
            if (
                physical_identity
                != (
                    int(request["dimension"]),
                    tuple(map(int, request["geometry_key"])),
                )
                or int(reply["global_entity"])
                != int(declaration["global_entity"])
                or int(reply["dolfinx_owner_rank"])
                != int(declaration["dolfinx_owner_rank"])
            ):
                raise RuntimeError("remote trace reply identity mismatch")
            arrays = {
                "full_rows": np.ascontiguousarray(
                    reply["full_rows"],
                    dtype=np.int64,
                ),
                "independent_rows": np.ascontiguousarray(
                    reply["independent_rows"],
                    dtype=np.int64,
                ),
                "full_from_independent": np.ascontiguousarray(
                    reply["full_from_independent"],
                    dtype=np.complex128,
                ),
                "physical_from_independent": np.ascontiguousarray(
                    reply["physical_from_independent"],
                    dtype=np.complex128,
                ),
                "canonical_to_dolfinx": np.ascontiguousarray(
                    reply["canonical_to_dolfinx"],
                    dtype=np.complex128,
                ),
            }
            for values in arrays.values():
                values.setflags(write=False)
            block = BrokenHexTraceEntityBlock(
                dimension=physical_identity[0],
                global_entity=int(reply["global_entity"]),
                dolfinx_owner_rank=int(reply["dolfinx_owner_rank"]),
                active_vector_work_owner_rank=int(
                    reply["active_vector_work_owner_rank"]
                ),
                physical_entity=by_physical[physical_identity],
                full_rows=arrays["full_rows"],
                independent_rows=arrays["independent_rows"],
                full_from_independent=arrays["full_from_independent"],
                physical_from_independent=arrays[
                    "physical_from_independent"
                ],
                canonical_to_dolfinx=arrays["canonical_to_dolfinx"],
            )
            block_sha256 = _entity_block_sha256(block)
            if (
                block_sha256 != str(request["expected_block_sha256"])
                or block_sha256 != str(reply["block_sha256"])
            ):
                raise RuntimeError(
                    "remote trace block content hash mismatch"
                )
            cache_by_physical[physical_identity] = block
        except (
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            local_rebuild_errors.append(
                f"token {token}: {type(exc).__name__}: {exc}"
            )
    if set(cache_by_physical) != needed_physical:
        local_rebuild_errors.append(
            "owner-routed trace cache is incomplete"
        )
    rebuild_error_packets = comm.allgather(tuple(local_rebuild_errors))
    rebuild_errors = [
        f"rank {rank}: {error}"
        for rank, packet in enumerate(rebuild_error_packets)
        for error in packet
    ]
    if rebuild_errors:
        raise RuntimeError(
            "owner-routed trace reply reconstruction failed collectively: "
            + "; ".join(rebuild_errors[:4])
        )

    blocks = {
        (block.dimension, block.global_entity): block
        for block in cache_by_physical.values()
    }
    work_blocks = tuple(
        sorted(
            (
                block
                for block in cache_by_physical.values()
                if block.active_vector_work_owner_rank == int(comm.rank)
            ),
            key=lambda block: (
                block.dimension,
                block.physical_entity.geometry_key,
            ),
        )
    )
    canonical_records = [
        {
            "dimension": int(declaration["dimension"]),
            "geometry_key": list(declaration["geometry_key"]),
            "independent_rows_sha256": str(
                declaration["independent_rows_sha256"]
            ),
            "physical_expansion_sha256": str(
                declaration["physical_expansion_sha256"]
            ),
        }
        for declaration in sorted(
            declarations,
            key=lambda record: (
                int(record["dimension"]),
                tuple(map(int, record["geometry_key"])),
            ),
        )
    ]
    local_cache_bytes = sum(
        _entity_block_native_array_bytes(block)
        for block in blocks.values()
    )
    local_unique_owner_bytes = sum(
        _entity_block_native_array_bytes(block)
        for block in owned_by_physical.values()
    )
    local_work_bytes = sum(
        _entity_block_native_array_bytes(block)
        for block in work_blocks
    )
    local_straddling_work_blocks = sum(
        any(
            _owner_of_row(int(row), active_trace_ranges)
            != int(block.active_vector_work_owner_rank)
            for row in block.full_rows
        )
        for block in work_blocks
    )
    local_cache_counts_by_dimension = {
        str(dimension): sum(
            block.dimension == dimension for block in blocks.values()
        )
        for dimension in (1, 2)
    }
    local_work_counts_by_dimension = {
        str(dimension): sum(
            block.dimension == dimension for block in work_blocks
        )
        for dimension in (1, 2)
    }
    request_counts = comm.allgather(len(expected_requests))
    received_request_counts = comm.allgather(
        sum(len(packet) for packet in inbound_requests)
    )
    reply_counts = comm.allgather(
        sum(len(packet) for packet in outbound_replies)
    )
    received_reply_counts = comm.allgather(len(received_by_token))
    if not (
        sum(request_counts)
        == sum(received_request_counts)
        == sum(reply_counts)
        == sum(received_reply_counts)
    ):
        raise RuntimeError("owner-routed trace request/reply counts do not close")
    local_cache_bytes_by_rank = comm.allgather(local_cache_bytes)
    unique_owner_bytes_by_rank = comm.allgather(local_unique_owner_bytes)
    work_bytes_by_rank = comm.allgather(local_work_bytes)
    unique_owner_bytes_global = sum(unique_owner_bytes_by_rank)
    retained_cache_bytes_global = sum(local_cache_bytes_by_rank)
    cache_duplication_factor = (
        float(retained_cache_bytes_global / unique_owner_bytes_global)
        if unique_owner_bytes_global
        else 0.0
    )
    routing_audit = {
        "schema_version": "task035d.owner-routed-trace-cache.v1",
        "owner_policy": "dolfinx_unique_entity_owner",
        "request_key": "canonical_physical_dimension_and_geometry",
        "reply_validation": (
            "token_key_owner_global_entity_orientation_and_block_sha256"
        ),
        "dense_global_entity_catalog_replicated": False,
        "declaration_catalog_is_metadata_only": True,
        "declaration_count": len(declarations),
        "canonical_content_sha256": _json_sha256(canonical_records),
        "owner_assignment_sha256": _json_sha256(
            [
                {
                    "dimension": int(record["dimension"]),
                    "geometry_key": list(record["geometry_key"]),
                    "global_entity": int(record["global_entity"]),
                    "dolfinx_owner_rank": int(
                        record["dolfinx_owner_rank"]
                    ),
                    "active_vector_work_owner_rank": int(
                        record["active_vector_work_owner_rank"]
                    ),
                    "block_sha256": str(record["block_sha256"]),
                }
                for record in sorted(
                    declarations,
                    key=lambda record: (
                        int(record["dimension"]),
                        tuple(map(int, record["geometry_key"])),
                    ),
                )
            ]
        ),
        "request_counts_by_rank": request_counts,
        "received_request_counts_by_rank": received_request_counts,
        "reply_counts_by_rank": reply_counts,
        "received_reply_counts_by_rank": received_reply_counts,
        "request_reply_count_closes": True,
        "reply_native_array_bytes_by_rank": comm.allgather(
            local_reply_array_bytes
        ),
        "received_reply_native_array_bytes_by_rank": comm.allgather(
            local_received_reply_array_bytes
        ),
        "temporary_reply_bytes_are_logical_not_peak_rss": True,
        "dolfinx_owned_entity_counts_by_dimension_by_rank": {
            dimension: comm.allgather(count)
            for dimension, count in local_owned_counts_by_dimension.items()
        },
        "dolfinx_ghost_entity_counts_by_dimension_by_rank": {
            dimension: comm.allgather(count)
            for dimension, count in local_ghost_counts_by_dimension.items()
        },
        "local_cache_block_counts_by_dimension_by_rank": {
            dimension: comm.allgather(count)
            for dimension, count in local_cache_counts_by_dimension.items()
        },
        "work_owned_block_counts_by_dimension_by_rank": {
            dimension: comm.allgather(count)
            for dimension, count in local_work_counts_by_dimension.items()
        },
        "cell_needed_block_counts_by_rank": comm.allgather(
            len(cell_needed_physical)
        ),
        "local_cache_block_counts_by_rank": comm.allgather(len(blocks)),
        "work_owned_block_counts_by_rank": comm.allgather(
            len(work_blocks)
        ),
        "active_trace_work_ownership_ranges": [
            list(row) for row in active_trace_ranges
        ],
        "work_owner_straddling_block_counts_by_rank": comm.allgather(
            local_straddling_work_blocks
        ),
        "work_owner_straddling_block_count": int(
            comm.allreduce(local_straddling_work_blocks, op=MPI.SUM)
        ),
        "unique_dolfinx_owner_native_array_bytes_by_rank": (
            unique_owner_bytes_by_rank
        ),
        "unique_dolfinx_owner_native_array_bytes_global_sum": (
            unique_owner_bytes_global
        ),
        "work_owned_native_array_bytes_by_rank": work_bytes_by_rank,
        "work_owned_native_array_bytes_max": max(work_bytes_by_rank),
        "work_owned_native_array_bytes_mean": float(
            sum(work_bytes_by_rank) / len(work_bytes_by_rank)
        ),
        "local_cache_native_array_bytes_by_rank": (
            local_cache_bytes_by_rank
        ),
        "retained_cache_native_array_bytes_global_sum": (
            retained_cache_bytes_global
        ),
        "retained_cache_native_array_bytes_max": max(
            local_cache_bytes_by_rank
        ),
        "retained_cache_duplication_factor": cache_duplication_factor,
        "native_array_bytes_are_logical_not_rss_pss_peak": True,
        "missing_reply_count": 0,
        "duplicate_reply_count": 0,
        "unrequested_reply_count": 0,
        "wrong_owner_reply_count": 0,
        "stale_or_corrupt_reply_count": 0,
        "collective_fail_closed": True,
        "pass": True,
    }
    return (
        blocks,
        work_blocks,
        canonical_records,
        declarations,
        maximum_orthogonality_error,
        routing_audit,
    )


def _cell_entity_blocks(
    entity_blocks: Mapping[tuple[int, int], BrokenHexTraceEntityBlock],
    entity_map: VariablePGlobalEntityMap,
    *,
    local_cell: int,
) -> tuple[BrokenHexTraceEntityBlock, ...]:
    cell = entity_map.owned_cells[local_cell]
    selected: list[BrokenHexTraceEntityBlock] = []
    for dimension in (1, 2):
        index_map = entity_map.mesh.topology.index_map(dimension)
        local_entities = np.asarray(
            cell.entity_ids[dimension],
            dtype=np.int32,
        )
        global_entities = np.asarray(
            index_map.local_to_global(local_entities),
            dtype=np.int64,
        )
        selected.extend(
            entity_blocks[(dimension, int(global_entity))]
            for global_entity in global_entities
        )
    return tuple(selected)


def _cell_expansion(
    entity_blocks: Mapping[tuple[int, int], BrokenHexTraceEntityBlock],
    entity_map: VariablePGlobalEntityMap,
    *,
    local_cell: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cell = entity_map.owned_cells[local_cell]
    selected = _cell_entity_blocks(
        entity_blocks,
        entity_map,
        local_cell=local_cell,
    )
    full_rows = np.concatenate([block.full_rows for block in selected])
    if not np.array_equal(full_rows, cell.trace_rows):
        raise RuntimeError(
            "cell trace entity sequence differs from active reference ordering"
        )
    independent = np.unique(
        np.concatenate([block.independent_rows for block in selected])
    ).astype(np.int64)
    local_column = {
        int(global_row): local_row
        for local_row, global_row in enumerate(independent)
    }
    expansion = np.zeros(
        (len(full_rows), len(independent)),
        dtype=np.complex128,
    )
    canonical_expansion = np.zeros_like(expansion)
    row_start = 0
    for block in selected:
        row_stop = row_start + len(block.full_rows)
        columns = np.asarray(
            [local_column[int(row)] for row in block.independent_rows],
            dtype=np.int64,
        )
        expansion[np.ix_(np.arange(row_start, row_stop), columns)] = (
            block.full_from_independent
        )
        canonical_expansion[
            np.ix_(np.arange(row_start, row_stop), columns)
        ] = block.physical_from_independent
        row_start = row_stop
    if np.any(
        np.max(np.abs(expansion), axis=1)
        <= np.finfo(np.float64).tiny
    ):
        raise RuntimeError("cell trace expansion contains an empty physical row")
    return (
        independent,
        np.ascontiguousarray(expansion),
        np.ascontiguousarray(canonical_expansion),
    )


def _canonical_cell_chart_error(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    *,
    local_cell: int,
) -> float:
    leaf = forest.leaves[
        int(carrier.canonical_leaf_by_local_cell[local_cell])
    ]
    box = leaf.box
    expected = np.asarray(
        [
            (
                box[3] if dx else box[0],
                box[4] if dy else box[1],
                box[5] if dz else box[2],
            )
            for dz in (0, 1)
            for dy in (0, 1)
            for dx in (0, 1)
        ],
        dtype=np.float64,
    )
    geometry_dofs = dmesh.entities_to_geometry(
        carrier.mesh,
        3,
        np.asarray([local_cell], dtype=np.int32),
        permute=False,
    )[0]
    observed = np.asarray(
        carrier.mesh.geometry.x[np.asarray(geometry_dofs), :3],
        dtype=np.float64,
    )
    return float(
        np.max(np.abs(observed - expected), initial=0.0)
    )


def build_broken_hexa_cell_trace_constraint_map(
    forest: BalancedDyadicHexForest,
    carrier: BrokenDyadicHexCarrier,
    entity_map: VariablePGlobalEntityMap,
    authority: BrokenHexTraceConstraintAuthority,
) -> BrokenHexCellTraceConstraintMap:
    """Bind the flattened physical graph to actual owned cell trace rows."""

    if carrier.mesh is not entity_map.mesh:
        raise ValueError("carrier and entity map use different DOLFINx meshes")
    if authority.audit["pass"] is not True:
        raise ValueError("physical trace authority must pass before binding")
    if str(carrier.audit["leaf_catalog_sha256"]) != str(
        forest.audit["leaf_catalog_sha256"]
    ):
        raise ValueError("forest and carrier identities differ")
    if str(authority.audit["physical_authority_sha256"]) == "":
        raise ValueError("physical trace authority identity is missing")
    degree = int(authority.degree)
    for dimension in (1, 2):
        if np.any(entity_map.global_degrees[dimension] != degree):
            raise ValueError(
                "broken local-h binding currently requires one trace degree"
            )

    bounds = forest.domain_bounds
    origin = np.asarray(bounds[:3], dtype=np.float64)
    extent = np.asarray(
        [bounds[axis + 3] - bounds[axis] for axis in range(3)],
        dtype=np.float64,
    )
    tolerance = max(float(np.max(extent)), 1.0) * 1.0e-11
    (
        blocks,
        work_blocks,
        canonical_records,
        declarations,
        orthogonality_error,
        routing_audit,
    ) = _entity_records(
        entity_map,
        authority,
        origin=origin,
        tolerance=tolerance,
    )
    comm = carrier.mesh.comm
    physical_row_owner: dict[Any, int] = {}
    block_owner_payload: list[dict[str, Any]] = []
    declaration_by_physical = {
        (
            int(declaration["dimension"]),
            tuple(map(int, declaration["geometry_key"])),
        ): declaration
        for declaration in declarations
    }
    if len(declaration_by_physical) != len(declarations):
        raise RuntimeError("physical entity owner declarations are not unique")
    entity_by_physical = {
        (entity.dimension, entity.geometry_key): entity
        for entity in authority.entities
    }
    for physical_identity, declaration in declaration_by_physical.items():
        physical = entity_by_physical.get(physical_identity)
        if physical is None:
            raise RuntimeError(
                "one owner declaration has no physical trace entity"
            )
        owner_rank = int(declaration["dolfinx_owner_rank"])
        for row in physical.rows:
            if row in physical_row_owner:
                raise RuntimeError(
                    "one physical trace row has multiple DOLFINx owners"
                )
            physical_row_owner[row] = owner_rank
        block_owner_payload.append(
            {
                "dimension": physical_identity[0],
                "geometry_key": list(physical_identity[1]),
                "dolfinx_owner_rank": owner_rank,
                "active_vector_work_owner_rank": int(
                    declaration["active_vector_work_owner_rank"]
                ),
            }
        )
    if set(physical_row_owner) != set(authority.graph.raw_rows):
        raise RuntimeError(
            "physical trace row ownership does not cover the raw graph once"
        )
    physical_entity_owner_sha256 = _json_sha256(
        sorted(
            block_owner_payload,
            key=lambda row: (
                int(row["dimension"]),
                tuple(row["geometry_key"]),
            ),
        )
    )

    relations = (
        *authority.hanging_relations,
        *authority.periodic_relations,
    )
    relation_owner_payload: list[dict[str, Any]] = []
    relation_owner_counts = [0] * int(comm.size)
    cross_rank_relation_counts: dict[str, int] = {}
    cross_rank_hanging_participant_entities: set[
        tuple[int, tuple[int, ...]]
    ] = set()
    for relation_index, relation in enumerate(relations):
        participant_rows = (*relation.slave_rows, *relation.master_rows)
        try:
            participant_owners = sorted(
                {physical_row_owner[row] for row in participant_rows}
            )
            canonical_owner_row = min(relation.slave_rows)
            owner_rank = int(physical_row_owner[canonical_owner_row])
        except KeyError as exc:
            raise RuntimeError(
                "one constraint relation references an unowned physical row"
            ) from exc
        if owner_rank not in participant_owners:
            raise RuntimeError(
                "constraint relation owner is not a participating entity owner"
            )
        relation_owner_counts[owner_rank] += 1
        crosses_rank = len(participant_owners) > 1
        if crosses_rank:
            cross_rank_relation_counts[relation.kind] = (
                cross_rank_relation_counts.get(relation.kind, 0) + 1
            )
            if relation.kind.startswith("hanging"):
                cross_rank_hanging_participant_entities.update(
                    (
                        int(row.entity_dimension),
                        tuple(row.entity_geometry_key),
                    )
                    for row in participant_rows
                )
        relation_owner_payload.append(
            {
                "relation_index": relation_index,
                "kind": relation.kind,
                "primary": bool(relation.primary),
                "canonical_owner_row": canonical_owner_row.to_tuple(),
                "owner_rank": owner_rank,
                "participant_owner_ranks": participant_owners,
                "crosses_rank": crosses_rank,
                "matrix_sha256": _matrix_sha256(
                    relation.slave_from_master
                ),
            }
        )
    relation_owner_sha256 = _json_sha256(relation_owner_payload)
    if len(set(comm.allgather(relation_owner_sha256))) != 1:
        raise RuntimeError("MPI ranks disagree on constraint relation ownership")
    missing_hanging_participants = (
        cross_rank_hanging_participant_entities
        - set(declaration_by_physical)
    )
    if missing_hanging_participants:
        raise RuntimeError(
            "cross-rank hanging relation has an unbound physical participant"
        )
    cross_rank_hanging_participant_sha256 = _json_sha256(
        [
            [dimension, list(geometry_key)]
            for dimension, geometry_key in sorted(
                cross_rank_hanging_participant_entities
            )
        ]
    )

    root_owner_ranges = _balanced_ownership_ranges(
        len(authority.graph.root_rows),
        comm.size,
    )
    active_trace_work_owner_ranges = _balanced_ownership_ranges(
        entity_map.active_trace_rows,
        comm.size,
    )
    block_owner_counts = [0] * int(comm.size)
    block_work_owner_counts = [0] * int(comm.size)
    for declaration in declarations:
        owner_rank = int(declaration["dolfinx_owner_rank"])
        work_owner_rank = int(
            declaration["active_vector_work_owner_rank"]
        )
        block_owner_counts[owner_rank] += 1
        expected_work_owner = _owner_of_row(
            int(
                entity_map.global_entity_rows[
                    int(declaration["dimension"])
                ][int(declaration["global_entity"])][0]
            ),
            active_trace_work_owner_ranges,
        )
        if work_owner_rank != expected_work_owner:
            raise RuntimeError(
                "entity block work owner differs from active-vector ownership"
            )
        block_work_owner_counts[work_owner_rank] += 1

    owned_cells: list[BrokenHexCellTraceMap] = []
    local_cell_records: list[dict[str, Any]] = []
    local_remote_entity_lookup_count = 0
    local_cross_rank_hanging_remote_lookup_count = 0
    local_cross_rank_hanging_remote_participants: set[
        tuple[int, tuple[int, ...]]
    ] = set()
    local_off_process_root_reference_count = 0
    remote_entity_lookup_hasher = hashlib.sha256()
    off_process_root_reference_hasher = hashlib.sha256()
    maximum_local_condition = 0.0
    maximum_cell_transform_error = 0.0
    maximum_canonical_chart_error = 0.0
    maximum_trace_interior_mixing_error = 0.0
    local_rank_failures = 0
    local_cell_expansion_bytes = 0
    local_cell_binding_error: str | None = None
    try:
        for local_cell, cell in enumerate(entity_map.owned_cells):
            independent, expansion, canonical_expansion = _cell_expansion(
                blocks,
                entity_map,
                local_cell=local_cell,
            )
            space = build_variable_p_reference_space(cell.degree_map)
            reference_values = np.zeros(
                (space.hcurl_dimension, len(independent)),
                dtype=np.complex128,
            )
            reference_values[
                np.asarray(space.trace_dofs, dtype=np.int32)
            ] = canonical_expansion
            transformed = space.apply_hcurl_dof_transform(
                reference_values,
                cell_info=cell.cell_info,
            )
            expected_expansion = transformed[
                np.asarray(space.trace_dofs, dtype=np.int32)
            ]
            trace_interior_mixing_error = float(
                np.max(
                    np.abs(
                        transformed[
                            np.asarray(
                                space.interior_dofs,
                                dtype=np.int32,
                            )
                        ]
                    ),
                    initial=0.0,
                )
            )
            maximum_trace_interior_mixing_error = max(
                maximum_trace_interior_mixing_error,
                trace_interior_mixing_error,
            )
            transform_error = float(
                np.max(
                    np.abs(expected_expansion - expansion),
                    initial=0.0,
                )
            )
            maximum_cell_transform_error = max(
                maximum_cell_transform_error,
                transform_error,
            )
            # DOLFINx cell_info is the orientation authority.  The
            # independently geometry-bound entity expansion above is retained
            # as a mandatory cross-check, while the cell map itself uses the
            # direct T_K G_K path.
            expansion = np.ascontiguousarray(expected_expansion)
            chart_error = _canonical_cell_chart_error(
                forest,
                carrier,
                local_cell=cell.local_cell,
            )
            maximum_canonical_chart_error = max(
                maximum_canonical_chart_error,
                chart_error,
            )
            singular_values = np.linalg.svd(
                expansion,
                compute_uv=False,
            )
            positive = singular_values[
                singular_values
                > max(expansion.shape)
                * np.finfo(np.float64).eps
                * singular_values[0]
            ]
            if len(positive) != len(independent):
                local_rank_failures += 1
                condition = float("inf")
            else:
                condition = float(positive[0] / positive[-1])
            maximum_local_condition = max(
                maximum_local_condition,
                condition,
            )
            local_cell_expansion_bytes += int(
                expansion.nbytes + independent.nbytes
            )
            expansion.setflags(write=False)
            independent.setflags(write=False)
            canonical_leaf = int(
                carrier.canonical_leaf_by_local_cell[cell.local_cell]
            )
            for block in _cell_entity_blocks(
                blocks,
                entity_map,
                local_cell=local_cell,
            ):
                if block.dolfinx_owner_rank == int(comm.rank):
                    continue
                physical_identity = (
                    int(block.dimension),
                    tuple(block.physical_entity.geometry_key),
                )
                remote_record = {
                    "canonical_leaf": canonical_leaf,
                    "dimension": physical_identity[0],
                    "geometry_key": list(physical_identity[1]),
                    "dolfinx_owner_rank": int(block.dolfinx_owner_rank),
                }
                remote_entity_lookup_hasher.update(
                    json.dumps(
                        remote_record,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("ascii")
                )
                remote_entity_lookup_hasher.update(b"\n")
                local_remote_entity_lookup_count += 1
                if (
                    physical_identity
                    in cross_rank_hanging_participant_entities
                ):
                    local_cross_rank_hanging_remote_lookup_count += 1
                    local_cross_rank_hanging_remote_participants.add(
                        physical_identity
                    )
            for root_row in independent:
                root_owner = _owner_of_row(
                    int(root_row),
                    root_owner_ranges,
                )
                if root_owner == int(comm.rank):
                    continue
                root_record = {
                    "canonical_leaf": canonical_leaf,
                    "root_row": int(root_row),
                    "petsc_owner_rank": root_owner,
                }
                off_process_root_reference_hasher.update(
                    json.dumps(
                        root_record,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("ascii")
                )
                off_process_root_reference_hasher.update(b"\n")
                local_off_process_root_reference_count += 1
            owned_cells.append(
                BrokenHexCellTraceMap(
                    local_cell=cell.local_cell,
                    global_cell=cell.global_cell,
                    canonical_leaf=canonical_leaf,
                    independent_rows=independent,
                    full_trace_from_independent=expansion,
                )
            )
            local_cell_records.append(
                {
                    "canonical_leaf": canonical_leaf,
                    "independent_rows": list(map(int, independent)),
                    "canonical_expansion_sha256": _matrix_sha256(
                        canonical_expansion
                    ),
                    "dolfinx_expansion_sha256": _matrix_sha256(
                        expansion
                    ),
                    "condition": condition,
                    "cell_transform_error": transform_error,
                    "trace_interior_mixing_error": (
                        trace_interior_mixing_error
                    ),
                    "canonical_chart_error": chart_error,
                }
            )
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        np.linalg.LinAlgError,
    ) as exc:
        local_cell_binding_error = f"{type(exc).__name__}: {exc}"
    cell_binding_error_packets = comm.allgather(local_cell_binding_error)
    cell_binding_errors = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(cell_binding_error_packets)
        if error is not None
    ]
    if cell_binding_errors:
        raise RuntimeError(
            "broken cell trace expansion failed collectively: "
            + "; ".join(cell_binding_errors[:4])
        )

    gathered_cells = [
        row
        for packet in carrier.mesh.comm.allgather(tuple(local_cell_records))
        for row in packet
    ]
    if sorted(record["canonical_leaf"] for record in gathered_cells) != list(
        range(len(forest.leaves))
    ):
        raise RuntimeError("cell trace binding does not cover each forest leaf")
    independent_rows = len(authority.graph.root_rows)
    used_roots = np.unique(
        np.concatenate(
            [cell.independent_rows for cell in owned_cells]
            or [np.empty(0, dtype=np.int64)]
        )
    )
    all_used_roots = np.unique(
        np.concatenate(carrier.mesh.comm.allgather(used_roots))
    )
    if not np.array_equal(
        all_used_roots,
        np.arange(independent_rows, dtype=np.int64),
    ):
        raise RuntimeError("one independent physical trace root is unused")
    maximum_condition = float(
        carrier.mesh.comm.allreduce(maximum_local_condition, op=MPI.MAX)
    )
    rank_failures = int(
        carrier.mesh.comm.allreduce(local_rank_failures, op=MPI.SUM)
    )
    if rank_failures:
        raise RuntimeError(
            "one broken-hexa cell trace expansion is rank deficient"
        )
    maximum_orthogonality = float(
        carrier.mesh.comm.allreduce(orthogonality_error, op=MPI.MAX)
    )
    maximum_transform_error = float(
        carrier.mesh.comm.allreduce(
            maximum_cell_transform_error,
            op=MPI.MAX,
        )
    )
    maximum_chart_error = float(
        carrier.mesh.comm.allreduce(
            maximum_canonical_chart_error,
            op=MPI.MAX,
        )
    )
    maximum_mixing_error = float(
        carrier.mesh.comm.allreduce(
            maximum_trace_interior_mixing_error,
            op=MPI.MAX,
        )
    )
    canonical_cell_graph_payload = [
        {
            "canonical_leaf": int(record["canonical_leaf"]),
            "independent_rows": record["independent_rows"],
            "canonical_expansion_sha256": record[
                "canonical_expansion_sha256"
            ],
        }
        for record in sorted(
            gathered_cells,
            key=lambda value: int(value["canonical_leaf"]),
        )
    ]
    canonical_cell_graph_sha256 = _json_sha256(
        canonical_cell_graph_payload
    )
    graph_hashes = carrier.mesh.comm.allgather(
        canonical_cell_graph_sha256
    )
    entity_block_bytes = sum(
        _entity_block_native_array_bytes(block)
        for block in blocks.values()
    )
    component_gram = authority.graph.component_gram
    if sparse.issparse(component_gram):
        component_gram_bytes = int(
            component_gram.data.nbytes
            + component_gram.indices.nbytes
            + component_gram.indptr.nbytes
        )
    else:
        component_gram_bytes = int(component_gram.nbytes)
    cell_expansion_bytes_by_rank = carrier.mesh.comm.allgather(
        local_cell_expansion_bytes
    )
    remote_entity_lookup_counts = comm.allgather(
        local_remote_entity_lookup_count
    )
    off_process_root_reference_counts = comm.allgather(
        local_off_process_root_reference_count
    )
    remote_entity_lookup_digests = comm.allgather(
        remote_entity_lookup_hasher.hexdigest()
    )
    cross_rank_hanging_remote_lookup_counts = comm.allgather(
        local_cross_rank_hanging_remote_lookup_count
    )
    cross_rank_hanging_remote_participant_packets = comm.allgather(
        tuple(sorted(local_cross_rank_hanging_remote_participants))
    )
    cross_rank_hanging_remote_participants = sorted(
        {
            physical_identity
            for packet in cross_rank_hanging_remote_participant_packets
            for physical_identity in packet
        }
    )
    if not set(cross_rank_hanging_remote_participants).issubset(
        cross_rank_hanging_participant_entities
    ):
        raise RuntimeError(
            "remote hanging participant is absent from the cross-rank "
            "hanging relation catalog"
        )
    cross_rank_hanging_participant_payload = [
        [dimension, list(geometry_key)]
        for dimension, geometry_key in sorted(
            cross_rank_hanging_participant_entities
        )
    ]
    cross_rank_hanging_remote_participant_payload = [
        [dimension, list(geometry_key)]
        for dimension, geometry_key in (
            cross_rank_hanging_remote_participants
        )
    ]
    cross_rank_hanging_remote_participant_sha256 = _json_sha256(
        cross_rank_hanging_remote_participant_payload
    )
    off_process_root_reference_digests = comm.allgather(
        off_process_root_reference_hasher.hexdigest()
    )
    remote_resolution_payload = {
        "remote_entity_lookup_counts_by_rank": remote_entity_lookup_counts,
        "remote_entity_lookup_local_digests_by_rank": (
            remote_entity_lookup_digests
        ),
        "off_process_root_reference_counts_by_rank": (
            off_process_root_reference_counts
        ),
        "off_process_root_reference_local_digests_by_rank": (
            off_process_root_reference_digests
        ),
    }
    remote_resolution_sha256 = _json_sha256(remote_resolution_payload)
    if len(set(comm.allgather(remote_resolution_sha256))) != 1:
        raise RuntimeError("MPI ranks disagree on remote constraint resolution")
    cross_rank_hanging_relations = sum(
        count
        for kind, count in cross_rank_relation_counts.items()
        if kind.startswith("hanging")
    )
    cross_rank_hanging_patches = int(
        carrier.audit["cross_rank_hanging_patch_count"]
    )
    checks = {
        "forest_carrier_identity": True,
        "all_physical_entities_bound_once": (
            len(canonical_records) == len(authority.entities)
        ),
        "entity_transform_orthogonality": (
            maximum_orthogonality <= 5.0e-11
        ),
        "cell_transform_matches_dolfinx_cell_info": (
            maximum_transform_error <= 5.0e-11
        ),
        "unpermuted_cell_chart_matches_forest": (
            maximum_chart_error <= 5.0e-11
        ),
        "trace_transform_does_not_mix_cell_interior": (
            maximum_mixing_error <= 5.0e-11
        ),
        "canonical_cell_graph_mpi_identity": (
            len(set(graph_hashes)) == 1
        ),
        "all_owned_cells_bound": (
            len(owned_cells) == len(entity_map.owned_cells)
        ),
        "cell_expansions_full_column_rank": rank_failures == 0,
        "all_independent_roots_reached": (
            len(all_used_roots) == independent_rows
        ),
        "no_slave_rows_numbered": (
            independent_rows < int(authority.audit["raw_trace_rows"])
        ),
        "physical_rows_have_one_dolfinx_owner": (
            len(physical_row_owner) == len(authority.graph.raw_rows)
        ),
        "constraint_relations_have_one_canonical_owner": (
            sum(relation_owner_counts) == len(relations)
            and all(
                record["owner_rank"]
                in record["participant_owner_ranks"]
                for record in relation_owner_payload
            )
        ),
        "active_vector_block_work_ownership_closes": (
            sum(block_work_owner_counts) == len(declarations)
            and active_trace_work_owner_ranges[0][0] == 0
            and active_trace_work_owner_ranges[-1][1]
            == entity_map.active_trace_rows
        ),
        "petsc_root_row_ownership_closes": (
            root_owner_ranges[0][0] == 0
            and root_owner_ranges[-1][1] == independent_rows
            and sum(stop - start for start, stop in root_owner_ranges)
            == independent_rows
        ),
        "cross_rank_hanging_graph_and_cell_expansions_close": (
            cross_rank_hanging_patches == 0
            or (
                cross_rank_hanging_relations > 0
                and bool(cross_rank_hanging_participant_entities)
                and not missing_hanging_participants
                and len(owned_cells) == len(entity_map.owned_cells)
            )
        ),
        "off_process_root_insertion_path_exercised": (
            comm.size == 1
            or sum(off_process_root_reference_counts) > 0
        ),
        "owner_routed_remote_cache_pass": (
            routing_audit["pass"] is True
            and routing_audit[
                "dense_global_entity_catalog_replicated"
            ]
            is False
            and (
                (
                    comm.size == 1
                    and not cross_rank_hanging_remote_participants
                    and sum(cross_rank_hanging_remote_lookup_counts) == 0
                )
                or (
                    comm.size > 1
                    and sum(routing_audit["request_counts_by_rank"]) > 0
                    and sum(remote_entity_lookup_counts) > 0
                    and sum(cross_rank_hanging_remote_lookup_counts) > 0
                    and bool(cross_rank_hanging_remote_participants)
                )
            )
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(
            f"broken cell trace binding failed: {failures}"
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035d.broken-hexa-cell-trace-map.v2",
            "status": "broken_hexa_cell_trace_binding_pass",
            "pass": True,
            "mpi_size": int(carrier.mesh.comm.size),
            "degree": degree,
            "constraint_kinds": [
                kind
                for kind, present in (
                    ("hanging", bool(authority.hanging_relations)),
                    ("floquet", bool(authority.periodic_relations)),
                )
                if present
            ],
            "contains_hanging_constraints": bool(
                authority.hanging_relations
            ),
            "contains_floquet_constraints": bool(
                authority.periodic_relations
            ),
            "global_cell_count": len(gathered_cells),
            "raw_trace_rows": int(authority.audit["raw_trace_rows"]),
            "independent_trace_rows": independent_rows,
            "eliminated_hanging_or_floquet_rows": int(
                authority.audit["raw_trace_rows"] - independent_rows
            ),
            "hanging_slave_rows": sum(
                len(relation.slave_rows)
                for relation in authority.hanging_relations
                if relation.primary
            ),
            "periodic_slave_rows": sum(
                len(relation.slave_rows)
                for relation in authority.periodic_relations
                if relation.primary
            ),
            "maximum_entity_transform_orthogonality_error": (
                maximum_orthogonality
            ),
            "maximum_cell_expansion_condition": maximum_condition,
            "maximum_cell_transform_error": maximum_transform_error,
            "maximum_unpermuted_cell_chart_error": maximum_chart_error,
            "maximum_trace_interior_mixing_error": maximum_mixing_error,
            "physical_authority_sha256": str(
                authority.audit["physical_authority_sha256"]
            ),
            "flattened_graph_sha256": str(
                authority.audit["flattened_graph_sha256"]
            ),
            "canonical_cell_graph_sha256": canonical_cell_graph_sha256,
            "ownership_policy": {
                "physical_entity_owner": "dolfinx_unique_entity_owner",
                "relation_owner": (
                    "owner_of_lexicographically_first_physical_slave_row"
                ),
                "reduced_petsc_row_owner": "balanced_contiguous_root_rows",
                "active_vector_block_work_owner": (
                    "owner_of_first_active_trace_entity_row"
                ),
                "remote_entity_resolution": (
                    "owner_routed_canonical_key_query_reply"
                ),
            },
            "dolfinx_entity_owner_counts_by_rank": block_owner_counts,
            "physical_entity_owner_sha256": (
                physical_entity_owner_sha256
            ),
            "active_vector_block_work_owner_counts_by_rank": (
                block_work_owner_counts
            ),
            "constraint_relation_owner_counts_by_rank": (
                relation_owner_counts
            ),
            "constraint_relation_owner_sha256": relation_owner_sha256,
            "cross_rank_relation_counts_by_kind": (
                cross_rank_relation_counts
            ),
            "cross_rank_hanging_patch_count": (
                cross_rank_hanging_patches
            ),
            "cross_rank_hanging_relation_count": (
                cross_rank_hanging_relations
            ),
            "cross_rank_hanging_participant_entity_count": len(
                cross_rank_hanging_participant_entities
            ),
            "cross_rank_hanging_participant_entity_sha256": (
                cross_rank_hanging_participant_sha256
            ),
            "cross_rank_hanging_participant_entities": (
                cross_rank_hanging_participant_payload
            ),
            "cross_rank_hanging_remote_lookup_counts_by_rank": (
                cross_rank_hanging_remote_lookup_counts
            ),
            "cross_rank_hanging_remote_participant_entity_count": len(
                cross_rank_hanging_remote_participants
            ),
            "cross_rank_hanging_remote_participant_entity_sha256": (
                cross_rank_hanging_remote_participant_sha256
            ),
            "cross_rank_hanging_remote_participant_entities": (
                cross_rank_hanging_remote_participant_payload
            ),
            "cross_rank_hanging_remote_participant_semantics": (
                "unique canonical physical entities that participate in a "
                "cross-rank hanging relation and are consumed by an owned "
                "cell through an owner-routed remote block"
            ),
            "cross_rank_hanging_resolution_semantics": (
                "replicated_physical_graph_plus_owner_routed_entity_blocks_"
                "plus_all_owned_cell_expansions"
            ),
            "reduced_petsc_root_ownership_ranges": [
                list(row) for row in root_owner_ranges
            ],
            "active_trace_work_ownership_ranges": [
                list(row) for row in active_trace_work_owner_ranges
            ],
            "remote_entity_lookup_counts_by_rank": (
                remote_entity_lookup_counts
            ),
            "remote_entity_lookup_local_digests_by_rank": (
                remote_entity_lookup_digests
            ),
            "off_process_root_reference_counts_by_rank": (
                off_process_root_reference_counts
            ),
            "off_process_root_reference_local_digests_by_rank": (
                off_process_root_reference_digests
            ),
            "remote_resolution_audit_is_count_and_digest_only": True,
            "remote_resolution_sha256": remote_resolution_sha256,
            "hanging_cell_ghost_counts_by_rank": list(
                carrier.audit["ghost_cell_counts_by_rank"]
            ),
            "owner_routed_trace_cache_audit": routing_audit,
            "replicated_entity_block_bytes_per_rank": 0,
            "replicated_entity_block_bytes_semantics": (
                "no_complete_dense_global_entity_catalog_is_retained_per_rank"
            ),
            "full_dense_entity_catalog_replicated": False,
            "local_entity_block_cache_bytes_by_rank": comm.allgather(
                entity_block_bytes
            ),
            "local_entity_block_cache_bytes_global_sum": int(
                comm.allreduce(entity_block_bytes, op=MPI.SUM)
            ),
            "entity_block_bytes_are_logical_native_arrays_not_peak_rss": True,
            "replicated_component_gram_bytes_per_rank": (
                component_gram_bytes
            ),
            "owned_cell_expansion_bytes_by_rank": (
                cell_expansion_bytes_by_rank
            ),
            "owned_cell_expansion_bytes_global_sum": int(
                sum(cell_expansion_bytes_by_rank)
            ),
            "checks": checks,
            "failures": failures,
            "canonical_root_numbering_partition_independent": True,
            "dolfinx_entity_order_bound_exactly_once": True,
            "compiled_cell_tensor_binding_complete": False,
            "petsc_constraint_row_ownership_qualified": True,
            "mpi_ghost_expansion_qualified": True,
            "pde_launch_ownership_gate": True,
            "entity_catalog_distribution": (
                "owner_routed_requested_dense_cache"
            ),
            "global_entity_declarations_distribution": (
                "allgather_metadata_only"
            ),
            "dense_cell_expansion_retained": True,
            "cell_expansion_svd_used_for_rank_audit": True,
            "cell_expansion_inverse_used": False,
            "distributed_scalability_qualified": False,
            "full_p6_trace_matrix_constructed": False,
            "hanging_or_floquet_slave_rows_globally_numbered": False,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    return BrokenHexCellTraceConstraintMap(
        entity_map=entity_map,
        authority=authority,
        entity_blocks=MappingProxyType(blocks),
        work_owned_entity_blocks=work_blocks,
        owned_cells=tuple(owned_cells),
        independent_trace_rows=independent_rows,
        component_gram=authority.graph.component_gram,
        audit=audit,
    )


__all__ = [
    "BrokenHexCellTraceConstraintMap",
    "BrokenHexCellTraceMap",
    "BrokenHexTraceEntityBlock",
    "build_broken_hexa_cell_trace_constraint_map",
]
