"""Owner-routed same-mesh p4-to-p6 H(curl) transfer for BAL_H.

The local map is the donor V5 Basix N1E map with the cell orientation
transforms on both sides.  The distributed adapter applies that map on local
cells, routes only global row ids and coefficients to their PETSc owners, and
uses the existing Floquet MPC once on each primal/dual side.  It does not
materialise a global transfer matrix or use a numerical allgather.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import pairwise
from time import perf_counter
from types import MappingProxyType
from typing import Any

import basix
import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

SAME_MESH_TRANSFER_PAIRS = ((6, 4),)
ROW_CONSISTENCY_LIMIT = 1.0e-11
_TASK041_SCHUR_SPEED_V2_PROFILE = "task041_schur_speed_v2"
_TRANSFER_VARIANTS = {"legacy": 0, "optimized": 1}
SUPPORT_POLICY_LEGACY = "legacy"
SUPPORT_POLICY_ENTITY_CLOSURE = "entity_closure"
_SUPPORT_POLICIES = {SUPPORT_POLICY_LEGACY, SUPPORT_POLICY_ENTITY_CLOSURE}
_OWNER_RESOLUTION_CHUNK_ROWS = 4096
_TRANSFER_DIAGNOSTIC_MAX_LOCAL_ROWS = 8
_TRANSFER_DIAGNOSTIC_MAX_GLOBAL_ROWS = 64
_TRANSFER_TIMING_NAMES = (
    "local_candidate_generation_seconds",
    "route_sort_index_seconds",
    "mpi_exchange_seconds",
    "duplicate_row_check_seconds",
    "ghost_mpc_prepare_seconds",
    "cell_adjoint_seconds",
    "dual_reduce_seconds",
    "ghost_mpc_check_seconds",
)


def _add_timing(
    timing: MutableMapping[str, float] | None,
    name: str,
    elapsed: float,
) -> None:
    if timing is not None:
        timing[name] = float(timing.get(name, 0.0)) + max(0.0, float(elapsed))


def _n1e(degree: int) -> Any:
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.legendre,
    )


def _normalize_support_policy(support_policy: str | None) -> str:
    policy = SUPPORT_POLICY_LEGACY if support_policy is None else str(support_policy)
    if policy not in _SUPPORT_POLICIES:
        raise ValueError(
            "support_policy must be 'legacy' or 'entity_closure'"
        )
    return policy


def _entity_block_labels(element: Any) -> tuple[tuple[int, int], ...]:
    labels: list[tuple[int, int] | None] = [None] * int(element.dim)
    for topological_dim, entities in enumerate(element.entity_dofs):
        for entity, dofs in enumerate(entities):
            for dof in dofs:
                index = int(dof)
                label = (int(topological_dim), int(entity))
                if labels[index] is not None and labels[index] != label:
                    raise ValueError("Basix entity DOF belongs to multiple blocks")
                labels[index] = label
    if any(label is None for label in labels):
        raise ValueError("Basix entity metadata does not cover all DOFs")
    return tuple(label for label in labels if label is not None)


def _verify_entity_block_transform(
    transform: np.ndarray,
    element: Any,
) -> None:
    labels = _entity_block_labels(element)
    for row, label in enumerate(labels):
        nonzero_columns = np.flatnonzero(transform[row, :] != 0.0)
        if any(labels[int(column)] != label for column in nonzero_columns):
            raise ValueError(
                "Basix orientation transform crosses entity support blocks"
            )


def _apply_entity_closure_support(
    matrix: np.ndarray,
    fine_element: Any,
    coarse_element: Any,
) -> None:
    """Zero only coarse columns outside the fine row's entity closure."""
    all_columns = np.arange(int(coarse_element.dim), dtype=np.intp)
    coarse_closures = coarse_element.entity_closure_dofs
    for topological_dim, entities in enumerate(fine_element.entity_dofs):
        if topological_dim >= 3:
            continue
        if topological_dim >= len(coarse_closures):
            raise ValueError("coarse entity closure metadata is incomplete")
        for entity, fine_rows in enumerate(entities):
            if len(fine_rows) == 0:
                continue
            if entity >= len(coarse_closures[topological_dim]):
                raise ValueError("coarse entity closure metadata is incomplete")
            allowed = np.asarray(
                coarse_closures[topological_dim][entity],
                dtype=np.intp,
            )
            if allowed.size == 0 or np.any(allowed < 0) or np.any(
                allowed >= int(coarse_element.dim)
            ):
                raise ValueError("coarse entity closure indices are invalid")
            disallowed = np.setdiff1d(
                all_columns,
                allowed,
                assume_unique=False,
            )
            for row in fine_rows:
                matrix[int(row), disallowed] = 0.0


def _reference_entity_trace_v1(
    reference: np.ndarray,
    fine_element: Any,
    coarse_element: Any,
) -> tuple[tuple[int, ...], ...]:
    """Replace N1E boundary rows with shared edge/face trace maps."""
    quad_coarse = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.quadrilateral,
        4,
        basix.LagrangeVariant.legendre,
    )
    quad_fine = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.quadrilateral,
        6,
        basix.LagrangeVariant.legendre,
    )
    quad_reference = np.asarray(
        basix.compute_interpolation_operator(quad_coarse, quad_fine),
        dtype=np.complex128,
    )
    quad_edges = tuple(
        tuple(int(vertex) for vertex in edge)
        for edge in basix.cell.topology(basix.CellType.quadrilateral)[1]
    )
    hex_topology = basix.cell.topology(basix.CellType.hexahedron)
    hex_edges = tuple(
        tuple(int(vertex) for vertex in edge)
        for edge in hex_topology[1]
    )
    hex_faces = tuple(
        tuple(int(vertex) for vertex in face)
        for face in hex_topology[2]
    )
    edge_by_ordered_vertices = {
        edge: index for index, edge in enumerate(hex_edges)
    }
    face_edge_map: list[tuple[int, ...]] = []
    for face_index, face_vertices in enumerate(hex_faces):
        mapped_edges: list[int] = []
        for quad_edge in quad_edges:
            ordered_edge = (
                face_vertices[quad_edge[0]],
                face_vertices[quad_edge[1]],
            )
            if ordered_edge not in edge_by_ordered_vertices:
                raise ValueError(
                    "hex face/quad edge orientation is not an ordered match "
                    f"for face {face_index}: {ordered_edge}"
                )
            mapped_edges.append(edge_by_ordered_vertices[ordered_edge])
        face_edge_map.append(tuple(mapped_edges))

    fine_edges = fine_element.entity_dofs[1]
    coarse_edges = coarse_element.entity_dofs[1]
    if any(len(rows) != 6 for rows in fine_edges) or any(
        len(columns) != 4 for columns in coarse_edges
    ):
        raise ValueError("unexpected hexahedron N1E edge dimensions")
    edge_block = np.zeros((6, 4), dtype=np.complex128)
    edge_block[:4, :] = np.eye(4, dtype=np.complex128)
    for fine_rows, coarse_columns in zip(
        fine_edges, coarse_edges, strict=True
    ):
        reference[np.asarray(fine_rows, dtype=np.intp), :] = 0.0
        reference[np.ix_(fine_rows, coarse_columns)] = edge_block

    quad_coarse_edges = quad_coarse.entity_dofs[1]
    quad_fine_face_rows = np.asarray(
        quad_fine.entity_dofs[2][0],
        dtype=np.intp,
    )
    quad_coarse_face_columns = np.asarray(
        np.concatenate(
            [
                np.asarray(rows, dtype=np.intp)
                for rows in quad_coarse_edges
            ]
            + [
                np.asarray(quad_coarse.entity_dofs[2][0], dtype=np.intp)
            ]
        ),
        dtype=np.intp,
    )
    for face_index, mapped_edges in enumerate(face_edge_map):
        fine_rows = np.asarray(
            fine_element.entity_dofs[2][face_index],
            dtype=np.intp,
        )
        coarse_columns = np.asarray(
            np.concatenate(
                [
                    np.asarray(coarse_edges[edge], dtype=np.intp)
                    for edge in mapped_edges
                ]
                + [
                    np.asarray(
                        coarse_element.entity_dofs[2][face_index],
                        dtype=np.intp,
                    )
                ]
            ),
            dtype=np.intp,
        )
        quad_block = quad_reference[
            np.ix_(quad_fine_face_rows, quad_coarse_face_columns)
        ]
        reference[fine_rows, :] = 0.0
        reference[np.ix_(fine_rows, coarse_columns)] = quad_block
    return tuple(face_edge_map)




def _dof_transform(element: Any, cell_info: int) -> np.ndarray:
    dimension = int(element.dim)
    data = np.eye(dimension, dtype=np.float64).reshape(-1).copy()
    element.T_apply(data, dimension, int(cell_info))
    transform = np.ascontiguousarray(data.reshape(dimension, dimension))
    if not np.all(np.isfinite(transform)):
        raise ValueError("Basix cell transform is non-finite")
    if abs(np.linalg.det(transform)) <= np.finfo(np.float64).tiny:
        raise ValueError("Basix cell transform is singular")
    return transform


@dataclass(frozen=True)
class SameMeshHcurlTransfer:
    """Bounded single-cell p4-to-p6 N1E map and its conjugate transpose."""

    fine_degree: int
    coarse_degree: int
    matrix: np.ndarray
    coarse_cell_info: int
    fine_cell_info: int
    audit: MappingProxyType

    def apply(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[1],):
            raise ValueError("coarse N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix @ vector)

    def apply_adjoint(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[0],):
            raise ValueError("fine N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix.conj().T @ vector)

    apply_primal = apply


def build_same_mesh_hcurl_transfer(
    fine_degree: int,
    coarse_degree: int,
    *,
    coarse_cell_info: int = 0,
    fine_cell_info: int = 0,
    support_policy: str = SUPPORT_POLICY_LEGACY,
) -> SameMeshHcurlTransfer:
    """Build the oriented reference-cell N1E embedding used by ``P``."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in SAME_MESH_TRANSFER_PAIRS:
        raise ValueError(
            "same-mesh transfer supports only "
            f"{SAME_MESH_TRANSFER_PAIRS}"
        )
    support_policy = _normalize_support_policy(support_policy)
    coarse_element = _n1e(coarse_degree)
    fine_element = _n1e(fine_degree)
    coarse_transform = _dof_transform(coarse_element, coarse_cell_info)
    fine_transform = _dof_transform(fine_element, fine_cell_info)
    orientation_blocks_verified = False
    if support_policy == SUPPORT_POLICY_ENTITY_CLOSURE:
        _verify_entity_block_transform(coarse_transform, coarse_element)
        _verify_entity_block_transform(fine_transform, fine_element)
        orientation_blocks_verified = True
    reference = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    shape = (int(fine_element.dim), int(coarse_element.dim))
    if reference.shape != shape:
        raise RuntimeError(
            f"Basix N1E interpolation shape {reference.shape} != {shape}"
        )
    reference_entity_trace_v1 = False
    reference_face_edge_map: tuple[tuple[int, ...], ...] = ()
    if support_policy == SUPPORT_POLICY_ENTITY_CLOSURE:
        reference_face_edge_map = _reference_entity_trace_v1(
            reference,
            fine_element,
            coarse_element,
        )
        reference_entity_trace_v1 = True
    matrix = np.ascontiguousarray(
        fine_transform
        @ reference
        @ np.linalg.inv(coarse_transform),
        dtype=np.complex128,
    )
    if support_policy == SUPPORT_POLICY_ENTITY_CLOSURE:
        _apply_entity_closure_support(matrix, fine_element, coarse_element)
    return SameMeshHcurlTransfer(
        fine_degree=int(fine_degree),
        coarse_degree=int(coarse_degree),
        matrix=matrix,
        coarse_cell_info=int(coarse_cell_info),
        fine_cell_info=int(fine_cell_info),
        audit=MappingProxyType(
            {
                "schema": "task041.bal_h.same_mesh_hcurl_transfer.v1",
                "pair_fine_to_coarse": [int(fine_degree), int(coarse_degree)],
                "shape": [int(value) for value in matrix.shape],
                "fine_lagrange_variant": "legendre",
                "coarse_lagrange_variant": "legendre",
                "support_policy": support_policy,
                "reference_entity_trace_v1": reference_entity_trace_v1,
                "reference_edge_block": (
                    "legendre_identity_zero"
                    if reference_entity_trace_v1
                    else None
                ),
                "reference_face_block": (
                    "quadrilateral_n1e_interpolation"
                    if reference_entity_trace_v1
                    else None
                ),
                "reference_face_edge_map": [
                    list(edges) for edges in reference_face_edge_map
                ],
                "orientation_entity_blocks_verified": (
                    orientation_blocks_verified
                ),
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "physical": False,
                "pde": False,
            }
        ),
    )


def _owner_ranges(index_map: Any, comm: Any) -> tuple[tuple[int, int], ...]:
    local = (int(index_map.local_range[0]), int(index_map.local_range[1]))
    ranges = tuple(
        tuple(int(value) for value in item) for item in comm.allgather(local)
    )
    if len(ranges) != int(comm.size) or not ranges:
        raise ValueError("owner range inventory is not closed")
    if ranges[0][0] != 0 or ranges[-1][1] != int(index_map.size_global):
        raise ValueError("owner ranges do not cover the global vector")
    for left, right in pairwise(ranges):
        if left[1] != right[0] or left[0] > left[1]:
            raise ValueError("owner ranges overlap or have a gap")
    return ranges


def _owner_ranks(
    ids: np.ndarray,
    ranges: tuple[tuple[int, int], ...],
) -> np.ndarray:
    values = np.asarray(ids, dtype=np.int64)
    if values.ndim != 1 or np.any(values < 0):
        raise ValueError("global ids must be one-dimensional and nonnegative")
    stops = np.asarray([item[1] for item in ranges], dtype=np.int64)
    owners = np.searchsorted(stops, values, side="right").astype(np.int32)
    if np.any(owners >= len(ranges)) or np.any(values >= stops[-1]):
        raise ValueError("global ids fall outside owner ranges")
    return owners


def _alltoallv_candidates(
    ids: np.ndarray,
    values: np.ndarray,
    ranges: tuple[tuple[int, int], ...],
    comm: Any,
    *,
    timing: MutableMapping[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ids = np.ascontiguousarray(ids, dtype=np.uint64)
    values = np.ascontiguousarray(values, dtype=np.complex128)
    if ids.ndim != 1 or values.ndim != 1 or ids.size != values.size:
        raise ValueError("owner candidate packet shape is not closed")
    route_started = perf_counter()
    destinations = _owner_ranks(ids, ranges)
    order = np.argsort(destinations, kind="stable")
    send_ids = np.ascontiguousarray(ids[order], dtype=np.uint64)
    send_values = np.ascontiguousarray(values[order], dtype=np.complex128)
    send_counts = np.bincount(
        destinations, minlength=int(comm.size)
    ).astype(np.int32)
    send_displacements = np.zeros(int(comm.size), dtype=np.int32)
    if int(comm.size) > 1:
        send_displacements[1:] = np.cumsum(send_counts[:-1], dtype=np.int32)
    _add_timing(
        timing,
        "route_sort_index_seconds",
        perf_counter() - route_started,
    )
    recv_counts = np.empty(int(comm.size), dtype=np.int32)
    exchange_started = perf_counter()
    try:
        comm.Alltoall(send_counts, recv_counts)
    finally:
        _add_timing(
            timing,
            "mpi_exchange_seconds",
            perf_counter() - exchange_started,
        )
    route_started = perf_counter()
    recv_displacements = np.zeros(int(comm.size), dtype=np.int32)
    if int(comm.size) > 1:
        recv_displacements[1:] = np.cumsum(recv_counts[:-1], dtype=np.int32)
    recv_size = int(np.sum(recv_counts, dtype=np.int64))
    recv_ids = np.empty(recv_size, dtype=np.uint64)
    recv_values = np.empty(recv_size, dtype=np.complex128)
    _add_timing(
        timing,
        "route_sort_index_seconds",
        perf_counter() - route_started,
    )
    exchange_started = perf_counter()
    try:
        comm.Alltoallv(
            [send_ids, (send_counts, send_displacements), MPI.UNSIGNED_LONG_LONG],
            [recv_ids, (recv_counts, recv_displacements), MPI.UNSIGNED_LONG_LONG],
        )
        comm.Alltoallv(
            [send_values, (send_counts, send_displacements), MPI.C_DOUBLE_COMPLEX],
            [recv_values, (recv_counts, recv_displacements), MPI.C_DOUBLE_COMPLEX],
        )
    finally:
        _add_timing(
            timing,
            "mpi_exchange_seconds",
            perf_counter() - exchange_started,
        )
    route_started = perf_counter()
    source_ranks = np.repeat(
        np.arange(int(comm.size), dtype=np.int32), recv_counts.astype(np.int64)
    )
    order = np.lexsort(
        (
            np.arange(recv_size, dtype=np.int64),
            source_ranks,
            recv_ids,
        )
    )
    _add_timing(
        timing,
        "route_sort_index_seconds",
        perf_counter() - route_started,
    )
    return recv_ids[order], recv_values[order], source_ranks[order]


def _resolve_owner_candidates(
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
    comm: Any,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    output_ids: list[int] = []
    output_values: list[complex] = []
    local_defect = 0.0
    cursor = 0
    while cursor < ids.size:
        end = cursor + 1
        while end < ids.size and ids[end] == ids[cursor]:
            end += 1
        group_sources = source_ranks[cursor:end]
        preferred = np.flatnonzero(group_sources == int(owner_rank))
        if preferred.size == 0:
            raise ValueError("fine owner rank has no canonical row candidate")
        reference = cursor + int(preferred[0])
        reference_value = complex(values[reference])
        local_defect = max(
            local_defect,
            float(np.max(np.abs(values[cursor:end] - reference_value))),
        )
        output_ids.append(int(ids[cursor]))
        output_values.append(reference_value)
        cursor = end
    global_defect = float(comm.allreduce(local_defect, op=MPI.MAX))
    if not np.isfinite(global_defect) or global_defect > ROW_CONSISTENCY_LIMIT:
        raise RuntimeError(
            "same-mesh owner row candidates disagree: "
            f"{global_defect} > {ROW_CONSISTENCY_LIMIT}"
        )
    return (
        np.asarray(output_ids, dtype=np.uint64),
        np.asarray(output_values, dtype=np.complex128),
        global_defect,
        int(ids.size),
    )


def _resolve_owner_candidates_batched(
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
    comm: Any,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    """Resolve contiguous owner groups with bounded NumPy scratch arrays.

    ``_alltoallv_candidates`` already orders rows by fine id, source rank, and
    packet order.  The first row from ``owner_rank`` in each contiguous id
    group is therefore the same canonical row selected by the legacy resolver.
    Group discovery and defect evaluation use a fixed-size chunk; only group
    starts/references and the returned owned packet scale with the number of
    distinct ids.  No route cache is retained.
    """

    ids = np.asarray(ids, dtype=np.uint64)
    values = np.asarray(values, dtype=np.complex128)
    source_ranks = np.asarray(source_ranks, dtype=np.int32)
    if (
        ids.ndim != 1
        or values.ndim != 1
        or source_ranks.ndim != 1
        or ids.size != values.size
        or ids.size != source_ranks.size
    ):
        raise ValueError("owner candidate packet shape is not closed")
    packet_size = int(ids.size)
    if packet_size == 0:
        global_defect = float(comm.allreduce(0.0, op=MPI.MAX))
        if (
            not np.isfinite(global_defect)
            or global_defect > ROW_CONSISTENCY_LIMIT
        ):
            raise RuntimeError(
                "same-mesh owner row candidates disagree: "
                f"{global_defect} > {ROW_CONSISTENCY_LIMIT}"
            )
        return ids.copy(), values.copy(), global_defect, packet_size

    group_starts_list = [0]
    chunk_rows = min(_OWNER_RESOLUTION_CHUNK_ROWS, packet_size)
    for chunk_start in range(0, packet_size, chunk_rows):
        chunk_stop = min(chunk_start + chunk_rows, packet_size)
        if chunk_start and ids[chunk_start] != ids[chunk_start - 1]:
            group_starts_list.append(chunk_start)
        if chunk_stop - chunk_start > 1:
            boundaries = np.flatnonzero(
                ids[chunk_start + 1 : chunk_stop]
                != ids[chunk_start : chunk_stop - 1]
            )
            group_starts_list.extend(
                (boundaries + chunk_start + 1).tolist()
            )
    group_starts = np.asarray(group_starts_list, dtype=np.intp)
    del group_starts_list
    group_count = int(group_starts.size)

    # packet_size is a valid upper-bound sentinel and cannot be an input row.
    reference_positions = np.full(
        group_count, packet_size, dtype=np.intp
    )
    for chunk_start in range(0, packet_size, chunk_rows):
        chunk_stop = min(chunk_start + chunk_rows, packet_size)
        owner_positions = np.flatnonzero(
            source_ranks[chunk_start:chunk_stop] == int(owner_rank)
        )
        if owner_positions.size:
            owner_positions += chunk_start
            owner_groups = np.searchsorted(
                group_starts, owner_positions, side="right"
            ) - 1
            np.minimum.at(reference_positions, owner_groups, owner_positions)
    if np.any(reference_positions == packet_size):
        raise ValueError("fine owner rank has no canonical row candidate")

    reference_values = values[reference_positions]
    expected_values = np.empty(chunk_rows, dtype=np.complex128)
    absolute_defect = np.empty(chunk_rows, dtype=np.float64)
    local_defect = 0.0
    for chunk_start in range(0, packet_size, chunk_rows):
        chunk_stop = min(chunk_start + chunk_rows, packet_size)
        count = chunk_stop - chunk_start
        positions = np.arange(chunk_start, chunk_stop, dtype=np.intp)
        group_index = np.searchsorted(
            group_starts, positions, side="right"
        ) - 1
        np.take(reference_values, group_index, out=expected_values[:count])
        np.subtract(
            values[chunk_start:chunk_stop],
            expected_values[:count],
            out=expected_values[:count],
        )
        np.abs(
            expected_values[:count], out=absolute_defect[:count]
        )
        chunk_defect = float(np.max(absolute_defect[:count]))
        if not np.isfinite(chunk_defect):
            # NaN reduction semantics for MPI.MAX are implementation
            # dependent.  Normalize every non-finite local defect to +inf;
            # later finite chunks cannot overwrite this Gate failure.
            local_defect = float("inf")
        elif np.isfinite(local_defect):
            local_defect = max(local_defect, chunk_defect)
    del expected_values, absolute_defect, positions, group_index
    global_defect = float(comm.allreduce(local_defect, op=MPI.MAX))
    if not np.isfinite(global_defect) or global_defect > ROW_CONSISTENCY_LIMIT:
        raise RuntimeError(
            "same-mesh owner row candidates disagree: "
            f"{global_defect} > {ROW_CONSISTENCY_LIMIT}"
        )
    resolved_ids = ids[group_starts]
    del group_starts, reference_positions
    return resolved_ids, reference_values, global_defect, packet_size


def _diagnostic_packet_precheck(
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
    comm: Any,
) -> None:
    ids = np.asarray(ids)
    values = np.asarray(values)
    source_ranks = np.asarray(source_ranks)
    shape_ok = bool(
        ids.ndim == 1
        and values.ndim == 1
        and source_ranks.ndim == 1
        and ids.size == values.size
        and ids.size == source_ranks.size
        and np.issubdtype(source_ranks.dtype, np.integer)
    )
    sorted_ok = False
    owner_ok = False
    source_ok = False
    if shape_ok:
        source_ok = bool(
            np.all(source_ranks >= 0)
            and np.all(source_ranks < int(comm.size))
        )
        sorted_ok = True
        owner_ok = True
        if ids.size:
            group_has_owner = bool(source_ranks[0] == int(owner_rank))
            for index in range(1, int(ids.size)):
                if ids[index] < ids[index - 1]:
                    sorted_ok = False
                if ids[index] == ids[index - 1]:
                    if source_ranks[index] < source_ranks[index - 1]:
                        sorted_ok = False
                    group_has_owner = group_has_owner or bool(
                        source_ranks[index] == int(owner_rank)
                    )
                else:
                    owner_ok = owner_ok and group_has_owner
                    group_has_owner = bool(
                        source_ranks[index] == int(owner_rank)
                    )
            owner_ok = owner_ok and group_has_owner
    local_ok = shape_ok and sorted_ok and source_ok and owner_ok
    if not bool(comm.allreduce(bool(local_ok), op=MPI.LAND)):
        raise ValueError(
            'diagnostic candidate packet shape/order/owner precheck failed'
        )


def _apply_conjugate_transpose_vector(
    matrix: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    """Apply a complex matrix adjoint without materialising ``matrix.conj()``."""

    return np.conjugate(matrix.T @ np.conjugate(values))


def _cell_global_dofs(space: Any, cell: int) -> tuple[np.ndarray, np.ndarray]:
    local = np.asarray(space.dofmap.cell_dofs(int(cell)), dtype=np.int32)
    global_ids = np.asarray(
        space.dofmap.index_map.local_to_global(local), dtype=np.int64
    )
    if global_ids.shape != local.shape or np.any(global_ids < 0):
        raise ValueError("cell dof map contains an invalid global id")
    return local, global_ids


def _finite_global(array: np.ndarray, comm: Any) -> bool:
    return bool(comm.allreduce(int(np.all(np.isfinite(array))), op=MPI.MIN))


def _mpc_constraint_residual(field: Any, floquet: Any) -> float:
    mpc = floquet.mpc
    values = np.asarray(field.x.array, dtype=np.complex128)
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    local_max = 0.0
    for slave in np.asarray(mpc.slaves, dtype=np.int64):
        row = int(slave)
        start = int(offsets[row])
        stop = int(offsets[row + 1])
        masters = np.asarray(mpc.masters.links(row), dtype=np.int64)
        if stop - start != masters.size or row >= values.size:
            raise ValueError("MPC local constraint storage is not closed")
        local_max = max(
            local_max,
            float(abs(values[row] - np.dot(coefficients[start:stop], values[masters]))),
        )
    return float(field.function_space.mesh.comm.allreduce(local_max, op=MPI.MAX))


def _slave_storage_max(field: Any, floquet: Any) -> float:
    slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
    values = np.asarray(field.x.array, dtype=np.complex128)
    local = float(np.max(np.abs(values[slaves]))) if slaves.size else 0.0
    return float(field.function_space.mesh.comm.allreduce(local, op=MPI.MAX))


def _owned_slave_indices(space: Any, floquet: Any) -> np.ndarray:
    if int(space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("owner transfer requires scalar-blocked N1E spaces")
    slaves = np.asarray(floquet.mpc.slaves, dtype=np.int32)
    local_size = int(space.dofmap.index_map.size_local)
    return slaves[(slaves >= 0) & (slaves < local_size)].copy()


def _dual_reduction_metadata(
    mpc: Any,
    local_storage: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    slaves = np.ascontiguousarray(np.asarray(mpc.slaves, dtype=np.int32))
    if np.any(slaves < 0) or np.any(slaves >= int(local_storage)):
        raise ValueError("MPC slave metadata exceeds local storage")
    slave_mask = np.zeros(int(local_storage), dtype=bool)
    slave_mask[slaves] = True
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    flat_slaves: list[int] = []
    flat_masters: list[int] = []
    flat_coefficients: list[complex] = []
    for slave in slaves:
        row = int(slave)
        start = int(offsets[row])
        stop = int(offsets[row + 1])
        masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
        row_coefficients = np.ascontiguousarray(
            coefficients[start:stop], dtype=np.complex128
        )
        if masters.size != row_coefficients.size:
            raise ValueError("MPC master/coefficient metadata does not close")
        if masters.size and (
            np.any(masters < 0) or np.any(masters >= int(local_storage))
        ):
            raise ValueError("MPC master metadata exceeds local storage")
        if masters.size and np.any(slave_mask[masters]):
            raise NotImplementedError("chained MPC rows are unsupported")
        flat_slaves.extend([row] * int(masters.size))
        flat_masters.extend(int(master) for master in masters)
        flat_coefficients.extend(complex(np.conjugate(value)) for value in row_coefficients)
    return (
        slaves,
        np.asarray(flat_slaves, dtype=np.int32),
        np.asarray(flat_masters, dtype=np.int32),
        np.asarray(flat_coefficients, dtype=np.complex128),
    )


class SameMeshHcurlOwnerTransfer:
    """Distributed owner-packet adapter for one shared-mesh N1E pair."""

    def __init__(
        self,
        fine_space: Any,
        fine_floquet: Any,
        coarse_space: Any,
        coarse_floquet: Any,
        local_transfer: SameMeshHcurlTransfer,
        *,
        optimization_profile: str | None = None,
        support_policy: str = SUPPORT_POLICY_LEGACY,
    ) -> None:
        support_policy = _normalize_support_policy(support_policy)
        pair = (
            int(fine_space.element.basix_element.degree),
            int(coarse_space.element.basix_element.degree),
        )
        if pair not in SAME_MESH_TRANSFER_PAIRS:
            raise ValueError("unsupported same-mesh owner transfer pair")
        if fine_space.mesh is not coarse_space.mesh:
            raise ValueError("owner transfer requires one shared mesh object")
        if local_transfer.audit["pair_fine_to_coarse"] != list(pair):
            raise ValueError("local transfer pair does not match spaces")
        local_support_policy = local_transfer.audit.get(
            "support_policy",
            SUPPORT_POLICY_LEGACY,
        )
        if local_support_policy != support_policy:
            raise ValueError(
                "local transfer support policy does not match owner policy"
            )
        fine_variant = fine_space.element.basix_element.lagrange_variant.name
        coarse_variant = coarse_space.element.basix_element.lagrange_variant.name
        if (
            local_transfer.audit["fine_lagrange_variant"] != fine_variant
            or local_transfer.audit["coarse_lagrange_variant"] != coarse_variant
        ):
            raise ValueError(
                "local transfer Basix Lagrange variants do not match runtime spaces"
            )
        if int(fine_space.dofmap.index_map_bs) != 1 or int(
            coarse_space.dofmap.index_map_bs
        ) != 1:
            raise NotImplementedError("owner transfer requires scalar-blocked N1E spaces")
        if getattr(fine_floquet, "mpc", None) is None or getattr(
            coarse_floquet, "mpc", None
        ) is None:
            raise ValueError("same-mesh owner transfer requires both Floquet MPCs")
        mesh = fine_space.mesh
        if fine_floquet.mpc.function_space.mesh is not mesh:
            raise ValueError("fine Floquet MPC is attached to another mesh")
        if coarse_floquet.mpc.function_space.mesh is not mesh:
            raise ValueError("coarse Floquet MPC is attached to another mesh")

        self.fine_space = fine_space
        self.coarse_space = coarse_space
        self.fine_floquet = fine_floquet
        self.coarse_floquet = coarse_floquet
        self.mesh = mesh
        self.comm = mesh.comm
        self.local_transfer = local_transfer
        self._support_policy = support_policy
        if optimization_profile not in {None, _TASK041_SCHUR_SPEED_V2_PROFILE}:
            raise ValueError("unsupported same-mesh transfer optimization profile")
        self._optimization_profile = optimization_profile
        self._execution_variant = (
            "optimized"
            if optimization_profile == _TASK041_SCHUR_SPEED_V2_PROFILE
            else "legacy"
        )
        self._variant_context_active = False
        self._apply_in_progress = False
        self._destroyed = False
        self._last_apply_facts: dict[str, object] = {}
        self._diagnostic_context: dict[str, Any] | None = None
        self._last_diagnostic: dict[str, Any] = {}
        self._diagnostic_callback: Any | None = None
        self.fine_ranges = _owner_ranges(fine_space.dofmap.index_map, self.comm)
        self.coarse_ranges = _owner_ranges(coarse_space.dofmap.index_map, self.comm)
        self._fine_owned_start = int(fine_space.dofmap.index_map.local_range[0])
        self._coarse_owned_start = int(coarse_space.dofmap.index_map.local_range[0])
        self._fine_owned_size = int(fine_space.dofmap.index_map.size_local)
        self._coarse_owned_size = int(coarse_space.dofmap.index_map.size_local)
        self._fine_slaves = _owned_slave_indices(fine_space, fine_floquet)
        self._coarse_slaves = _owned_slave_indices(coarse_space, coarse_floquet)

        topology = self.mesh.topology
        topology.create_entity_permutations()
        permutation_info = np.asarray(
            topology.get_cell_permutation_info(), dtype=np.uint32
        )
        cell_map = topology.index_map(topology.dim)
        owned_cell_count = int(cell_map.size_local)
        cell_count = int(cell_map.size_local + cell_map.num_ghosts)
        if permutation_info.size < cell_count:
            raise ValueError("cell permutation inventory is incomplete")

        cache: dict[tuple[int, int], SameMeshHcurlTransfer] = {
            (
                int(local_transfer.fine_cell_info),
                int(local_transfer.coarse_cell_info),
            ): local_transfer
        }
        records: list[dict[str, Any]] = []
        authority: dict[int, tuple[int, int]] = {}
        coarse_seen: set[int] = set()
        for cell in range(cell_count):
            cell_info = int(permutation_info[cell])
            key = (cell_info, cell_info)
            if key not in cache:
                cache[key] = build_same_mesh_hcurl_transfer(
                    pair[0],
                    pair[1],
                    coarse_cell_info=cell_info,
                    fine_cell_info=cell_info,
                    support_policy=support_policy,
                )
            fine_local, fine_global = _cell_global_dofs(fine_space, cell)
            coarse_local, coarse_global = _cell_global_dofs(coarse_space, cell)
            if cache[key].matrix.shape != (fine_global.size, coarse_global.size):
                raise ValueError("local map and cell dof layout have different shapes")
            fine_owners = _owner_ranks(fine_global, self.fine_ranges)
            coarse_owners = _owner_ranks(coarse_global, self.coarse_ranges)
            for position, global_id in enumerate(fine_global):
                if int(fine_owners[position]) == int(self.comm.rank):
                    authority.setdefault(int(global_id), (cell, position))
            coarse_seen.update(
                int(global_id)
                for global_id, owner in zip(coarse_global, coarse_owners)
                if int(owner) == int(self.comm.rank)
            )
            records.append(
                {
                    "fine_local": fine_local,
                    "fine_global": fine_global.astype(np.uint64, copy=False),
                    "coarse_local": coarse_local,
                    "coarse_global": coarse_global.astype(np.uint64, copy=False),
                    "matrix": cache[key].matrix,
                    "authority": np.asarray(
                        [
                            authority.get(int(global_id)) == (cell, position)
                            and int(fine_owners[position]) == int(self.comm.rank)
                            for position, global_id in enumerate(fine_global)
                        ],
                        dtype=bool,
                    ),
                }
            )

        fine_first, fine_last = self.fine_ranges[self.comm.rank]
        coarse_first, coarse_last = self.coarse_ranges[self.comm.rank]
        if set(authority) != set(range(fine_first, fine_last)):
            raise ValueError("fine owner rows do not have a local canonical authority")
        if coarse_seen != set(range(coarse_first, coarse_last)):
            raise ValueError("coarse owner columns do not have local cell coverage")

        self._records = tuple(records)
        self._coarse_work = fem.Function(coarse_floquet.mpc.function_space)
        self._fine_work = fem.Function(fine_floquet.mpc.function_space)
        (
            self._coarse_mpc_slaves,
            self._dual_flat_slaves,
            self._dual_flat_masters,
            self._dual_conjugated_coefficients,
        ) = _dual_reduction_metadata(
            coarse_floquet.mpc, self._coarse_work.x.array.size
        )
        self._dual_reduction_work = np.empty(
            self._dual_flat_slaves.size, dtype=np.complex128
        )
        self._audit = MappingProxyType(
            {
                "schema": "task041.bal_h.same_mesh_owner_transfer.v1",
                "pair_fine_to_coarse": list(pair),
                "fine_global_rows": int(fine_space.dofmap.index_map.size_global),
                "coarse_global_rows": int(coarse_space.dofmap.index_map.size_global),
                "fine_local_owned_rows": self._fine_owned_size,
                "coarse_local_owned_rows": self._coarse_owned_size,
                "owner_local": True,
                "owner_ghost_identity": True,
                "owner_row_authority": "fine_owner_rank_then_local_cell_order",
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "static_condensation": False,
                "physical": False,
                "pde": False,
                "empty_owner_supported": True,
                "fine_owned_cells": owned_cell_count,
                "algebraic_slave_storage": "owned fine/coarse slaves zero",
                "optimization_profile": optimization_profile,
                "support_policy": support_policy,
                "default_execution_variant": self._execution_variant,
                "owner_resolution": (
                    "numpy_batched"
                    if self._execution_variant == "optimized"
                    else "legacy_python"
                ),
                "adjoint_cell_apply": (
                    "conjugate_transpose_identity"
                    if self._execution_variant == "optimized"
                    else "explicit_conjugate_transpose"
                ),
                "variant_bindings": {
                    "source_module": __name__,
                    "legacy": {
                        "owner_resolution": (
                            f"{__name__}._resolve_owner_candidates"
                        ),
                        "cell_adjoint": (
                            f"{__name__}.SameMeshHcurlOwnerTransfer."
                            "_apply_adjoint_into_impl"
                        ),
                        "adjoint_kernel": "explicit_matrix_conjugate_transpose",
                    },
                    "optimized": {
                        "owner_resolution": (
                            f"{__name__}._resolve_owner_candidates_batched"
                        ),
                        "cell_adjoint": (
                            f"{__name__}._apply_conjugate_transpose_vector"
                        ),
                        "adjoint_kernel": "conjugate_transpose_identity",
                    },
                },
            }
        )

    @property
    def audit(self) -> MappingProxyType:
        return self._audit

    @property
    def last_apply_facts(self) -> dict[str, object]:
        return dict(self._last_apply_facts)

    @property
    def last_diagnostic(self) -> dict[str, Any]:
        return dict(self._last_diagnostic)

    @property
    def execution_variant(self) -> str:
        return self._execution_variant

    @contextmanager
    def variant_context(self, variant: str):
        """Temporarily select one kernel variant on this live adapter.

        Every rank must enter this context with the same variant.  The one
        small ``Allreduce`` is used only for an explicit override; ordinary
        profile-selected applies remain on their existing path.  The context
        must cover the complete apply/KSP operation and restores the prior
        selection when the operation returns or raises.
        """

        self._require_live()
        if variant not in _TRANSFER_VARIANTS:
            raise ValueError("same-mesh transfer variant must be legacy or optimized")
        if self._apply_in_progress:
            raise RuntimeError("same-mesh transfer variant cannot change during apply")
        if self._variant_context_active:
            raise RuntimeError("same-mesh transfer variant cannot change while active")
        code = int(_TRANSFER_VARIANTS[variant])
        local_codes = np.asarray((code, -code), dtype=np.int32)
        global_codes = np.empty(2, dtype=np.int32)
        self.comm.Allreduce(local_codes, global_codes, op=MPI.MIN)
        if int(global_codes[0]) != -int(global_codes[1]):
            raise RuntimeError("same-mesh transfer variant differs across ranks")
        previous = self._execution_variant
        self._execution_variant = variant
        self._variant_context_active = True
        try:
            yield self
        finally:
            self._execution_variant = previous
            self._variant_context_active = False

    @contextmanager
    def diagnostic_context(self, callback: Any):
        """Enable one explicit test-only full-packet diagnostic operation."""

        self._require_live()
        if self._apply_in_progress:
            raise RuntimeError("same-mesh diagnostic cannot nest inside apply")
        if self._diagnostic_context is not None:
            raise RuntimeError("same-mesh diagnostic is already active")
        state: dict[str, Any] = {
            "schema": "task041.same_mesh_owner_transfer.diagnostic.v1",
            "max_local_rows": _TRANSFER_DIAGNOSTIC_MAX_LOCAL_ROWS,
            "max_global_rows": _TRANSFER_DIAGNOSTIC_MAX_GLOBAL_ROWS,
            "selected_variant": self._execution_variant,
        }
        self._diagnostic_context = state
        self._diagnostic_callback = callback
        try:
            yield state
        finally:
            self._last_diagnostic = state
            self._diagnostic_context = None
            self._diagnostic_callback = None

    def _require_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("same-mesh owner transfer has been destroyed")

    def _require_vector(self, vector: Any, index_map: Any) -> None:
        if int(vector.getSize()) != int(index_map.size_global):
            raise ValueError("PETSc vector global size does not match the space")
        if int(vector.getLocalSize()) != int(index_map.size_local):
            raise ValueError("PETSc vector local ownership does not match the space")

    def _require_algebraic(self, vector: Any, slaves: np.ndarray) -> None:
        values = np.asarray(vector.getArray(readonly=True))
        valid = bool(np.all(values[slaves] == 0.0))
        if not self.comm.allreduce(valid, op=MPI.LAND):
            raise ValueError("algebraic transfer input must have zero owned slave entries")

    def _finalize_primal(self, field: Any, floquet: Any) -> None:
        floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        floquet.mpc.backsubstitution(field)
        field.x.scatter_forward()

    def _prepare_primal(self, source: Any, field: Any, floquet: Any) -> None:
        self._require_vector(source, field.function_space.dofmap.index_map)
        source.copy(field.x.petsc_vec)
        field.x.scatter_forward()
        self._finalize_primal(field, floquet)

    def _candidate_packet(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._records:
            return np.empty(0, dtype=np.uint64), np.empty(0, dtype=np.complex128)
        ids = []
        values = []
        for record in self._records:
            local_values = np.asarray(
                self._coarse_work.x.array[record["coarse_local"]],
                dtype=np.complex128,
            )
            ids.append(record["fine_global"])
            values.append(record["matrix"] @ local_values)
        return (
            np.concatenate(ids).astype(np.uint64, copy=False),
            np.concatenate(values).astype(np.complex128, copy=False),
        )

    def _diagnostic_resolve_candidates(
        self,
        ids: np.ndarray,
        values: np.ndarray,
        source_ranks: np.ndarray,
        owner_rank: int,
        emitted_ids: np.ndarray,
        emitted_values: np.ndarray,
        source: Any,
    ) -> tuple[np.ndarray, np.ndarray, float, int]:
        attempts: dict[str, dict[str, Any]] = {}
        state = self._diagnostic_context
        if state is None or self._diagnostic_callback is None:
            raise RuntimeError("same-mesh diagnostic context is not active")
        try:
            _diagnostic_packet_precheck(
                ids, values, source_ranks, owner_rank, self.comm
            )
        except ValueError as exc:
            state["packet_precheck"] = {
                "status": "failed",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }
            state["collectives_complete"] = True
            self._last_apply_facts = {
                "operation": "primal",
                "finite": None,
                "input_unchanged": None,
                "transfer_diagnostic": dict(state),
            }
            raise
        state["packet_precheck"] = {"status": "passed"}
        for name, resolver in (
            ("legacy", _resolve_owner_candidates),
            ("batched", _resolve_owner_candidates_batched),
        ):
            try:
                result = resolver(
                    ids,
                    values,
                    source_ranks,
                    owner_rank,
                    self.comm,
                )
            except (RuntimeError, ValueError) as exc:
                attempts[name] = {
                    "exception": exc,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                }
            else:
                attempts[name] = {"result": result}
        callback_error = None
        try:
            callback_result = self._diagnostic_callback(
                ids=ids,
                values=values,
                source_ranks=source_ranks,
                owner_rank=int(owner_rank),
                owner_ranges=self.fine_ranges,
                coarse_owner_ranges=self.coarse_ranges,
                attempts=attempts,
                transfer=self,
                emitted_ids=emitted_ids,
                emitted_values=emitted_values,
                source=source,
            )
        except (AttributeError, KeyError, IndexError, RuntimeError, TypeError, ValueError) as exc:
            callback_result = None
            callback_error = f"{type(exc).__name__}: {exc}"
        if not bool(self.comm.allreduce(callback_error is None, op=MPI.LAND)):
            state["callback_error"] = callback_error or "peer callback failed"
            state["collectives_complete"] = True
            self._last_apply_facts = {
                "operation": "primal",
                "finite": None,
                "input_unchanged": None,
                "transfer_diagnostic": dict(state),
            }
            raise RuntimeError("same-mesh diagnostic callback failed")
        state["packet_rows"] = int(ids.size)
        for name in ("legacy", "batched"):
            attempt = attempts[name]
            result = attempt.get("result")
            if result is None:
                state[name] = {
                    "status": "exception",
                    "exception_type": str(attempt["exception_type"]),
                    "exception_message": str(attempt["exception_message"]),
                }
            else:
                state[name] = {
                    "status": "returned",
                    "resolved_rows": int(result[0].size),
                    "global_defect": float(result[2]),
                    "packet_rows": int(result[3]),
                }
        state["callback"] = callback_result
        state["collectives_complete"] = True
        selected_name = (
            "batched"
            if self._execution_variant == "optimized"
            else "legacy"
        )
        selected = attempts[selected_name]
        if "result" not in selected:
            self._last_apply_facts = {
                "operation": "primal",
                "finite": None,
                "input_unchanged": None,
                "transfer_diagnostic": dict(state),
            }
            raise selected["exception"] from None
        return selected["result"]

    def apply_primal_into(
        self,
        source: Any,
        target: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> None:
        self._require_live()
        if self._apply_in_progress:
            raise RuntimeError("same-mesh owner transfer apply is already in progress")
        self._apply_in_progress = True
        try:
            self._apply_primal_into_impl(source, target, timing=timing)
        finally:
            self._apply_in_progress = False

    def _apply_primal_into_impl(
        self,
        source: Any,
        target: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> None:
        self._require_live()
        self._require_algebraic(source, self._coarse_slaves)
        self._require_vector(target, self.fine_space.dofmap.index_map)
        started = perf_counter()
        try:
            self._prepare_primal(source, self._coarse_work, self.coarse_floquet)
        finally:
            _add_timing(timing, "ghost_mpc_prepare_seconds", perf_counter() - started)
        started = perf_counter()
        try:
            candidate_ids, candidate_values = self._candidate_packet()
        finally:
            _add_timing(
                timing,
                "local_candidate_generation_seconds",
                perf_counter() - started,
            )
        received_ids, received_values, source_ranks = _alltoallv_candidates(
            candidate_ids,
            candidate_values,
            self.fine_ranges,
            self.comm,
            timing=timing,
        )
        started = perf_counter()
        try:
            resolver = (
                _resolve_owner_candidates_batched
                if self._execution_variant == "optimized"
                else _resolve_owner_candidates
            )
            if self._diagnostic_context is not None:
                owned_ids, owned_values, defect, packet_size = (
                    self._diagnostic_resolve_candidates(
                        received_ids,
                        received_values,
                        source_ranks,
                        self.comm.rank,
                        candidate_ids,
                        candidate_values,
                        source,
                    )
                )
            else:
                owned_ids, owned_values, defect, packet_size = resolver(
                    received_ids,
                    received_values,
                    source_ranks,
                    self.comm.rank,
                    self.comm,
                )
        finally:
            _add_timing(
                timing,
                "duplicate_row_check_seconds",
                perf_counter() - started,
            )
        started = perf_counter()
        try:
            self._fine_work.x.array[:] = 0.0
            local_ids = owned_ids.astype(np.int64) - self._fine_owned_start
            if np.any(local_ids < 0) or np.any(local_ids >= self._fine_owned_size):
                raise ValueError("resolved owner ids are not locally owned")
            if local_ids.size:
                self._fine_work.x.array[local_ids] = owned_values
            self._fine_work.x.scatter_forward()
            self._finalize_primal(self._fine_work, self.fine_floquet)
            constraint = _mpc_constraint_residual(self._fine_work, self.fine_floquet)
            self._fine_work.x.array[self._fine_slaves] = 0.0
            self._fine_work.x.scatter_forward()
            finite = _finite_global(self._fine_work.x.array, self.comm)
            if not finite or not np.isfinite(constraint):
                raise RuntimeError("same-mesh primal output is non-finite")
            self._fine_work.x.petsc_vec.copy(target)
        finally:
            _add_timing(timing, "ghost_mpc_check_seconds", perf_counter() - started)
        self._last_apply_facts = {
            "operation": "primal",
            "finite": finite,
            "input_unchanged": True,
            "owner_packet_rows": packet_size,
            "shared_row_max_defect": defect,
            "fine_physical_mpc_constraint_residual": constraint,
            "fine_owned_slaves_zero": True,
            "phase_application": "finalized_floquet_mpc_once",
            "optimization_profile": self._optimization_profile,
            "execution_variant": self._execution_variant,
            "owner_resolution": (
                "numpy_batched"
                if self._execution_variant == "optimized"
                else "legacy_python"
            ),
            "execution_variant_source": (
                "explicit_context"
                if self._variant_context_active
                else "profile_default"
            ),
        }
        if timing is not None:
            self._last_apply_facts["timing"] = dict(timing)

    def apply_primal(
        self,
        source: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> Any:
        self._require_live()
        target = create_vector(
            [
                (
                    self.fine_space.dofmap.index_map,
                    int(self.fine_space.dofmap.index_map_bs),
                )
            ]
        )
        try:
            self.apply_primal_into(source, target, timing=timing)
            return target
        except BaseException:
            target.destroy()
            raise

    def apply_adjoint_into(
        self,
        source: Any,
        target: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> None:
        self._require_live()
        if self._apply_in_progress:
            raise RuntimeError("same-mesh owner transfer apply is already in progress")
        self._apply_in_progress = True
        try:
            self._apply_adjoint_into_impl(source, target, timing=timing)
        finally:
            self._apply_in_progress = False

    def _apply_adjoint_into_impl(
        self,
        source: Any,
        target: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> None:
        self._require_live()
        self._require_algebraic(source, self._fine_slaves)
        self._require_vector(source, self.fine_space.dofmap.index_map)
        self._require_vector(target, self.coarse_space.dofmap.index_map)
        started = perf_counter()
        try:
            source.copy(self._fine_work.x.petsc_vec)
            self._fine_work.x.scatter_forward()
            self.fine_floquet.mpc.homogenize(self._fine_work)
            self._fine_work.x.scatter_forward()
        finally:
            _add_timing(timing, "ghost_mpc_prepare_seconds", perf_counter() - started)
        self._coarse_work.x.array[:] = 0.0
        started = perf_counter()
        try:
            for record in self._records:
                values = np.asarray(
                    self._fine_work.x.array[record["fine_local"]],
                    dtype=np.complex128,
                )
                masked_values = values * record["authority"]
                if self._execution_variant == "optimized":
                    contribution = _apply_conjugate_transpose_vector(
                        record["matrix"], masked_values
                    )
                else:
                    contribution = record["matrix"].conj().T @ masked_values
                np.add.at(
                    self._coarse_work.x.array,
                    record["coarse_local"],
                    contribution,
                )
        finally:
            _add_timing(timing, "cell_adjoint_seconds", perf_counter() - started)
        if self._dual_flat_slaves.size:
            started = perf_counter()
            try:
                np.take(
                    self._coarse_work.x.array,
                    self._dual_flat_slaves,
                    out=self._dual_reduction_work,
                )
                np.multiply(
                    self._dual_reduction_work,
                    self._dual_conjugated_coefficients,
                    out=self._dual_reduction_work,
                )
                np.add.at(
                    self._coarse_work.x.array,
                    self._dual_flat_masters,
                    self._dual_reduction_work,
                )
                self._coarse_work.x.array[self._coarse_mpc_slaves] = 0.0
            finally:
                _add_timing(timing, "dual_reduce_seconds", perf_counter() - started)
        started = perf_counter()
        try:
            exchange_started = perf_counter()
            try:
                self._coarse_work.x.petsc_vec.ghostUpdate(
                    addv=PETSc.InsertMode.ADD_VALUES,
                    mode=PETSc.ScatterMode.REVERSE,
                )
            finally:
                _add_timing(
                    timing,
                    "mpi_exchange_seconds",
                    perf_counter() - exchange_started,
                )
            self._coarse_work.x.scatter_forward()
            finite = _finite_global(self._coarse_work.x.array, self.comm)
            slave_max = _slave_storage_max(self._coarse_work, self.coarse_floquet)
            if not finite or not np.isfinite(slave_max):
                raise RuntimeError("same-mesh adjoint output is non-finite")
            self._coarse_work.x.petsc_vec.copy(target)
        finally:
            _add_timing(timing, "ghost_mpc_check_seconds", perf_counter() - started)
        self._last_apply_facts = {
            "operation": "adjoint",
            "finite": finite,
            "input_unchanged": True,
            "coarse_slave_storage_max": slave_max,
            "coarse_dual_reduction": "C^H_once",
            "phase_application": "fine_dual_homogenize_then_coarse_C^H_once",
            "optimization_profile": self._optimization_profile,
            "execution_variant": self._execution_variant,
            "adjoint_cell_apply": (
                "conjugate_transpose_identity"
                if self._execution_variant == "optimized"
                else "explicit_conjugate_transpose"
            ),
            "execution_variant_source": (
                "explicit_context"
                if self._variant_context_active
                else "profile_default"
            ),
        }
        if timing is not None:
            self._last_apply_facts["timing"] = dict(timing)

    def apply_adjoint(
        self,
        source: Any,
        *,
        timing: MutableMapping[str, float] | None = None,
    ) -> Any:
        self._require_live()
        target = create_vector(
            [
                (
                    self.coarse_space.dofmap.index_map,
                    int(self.coarse_space.dofmap.index_map_bs),
                )
            ]
        )
        try:
            self.apply_adjoint_into(source, target, timing=timing)
            return target
        except BaseException:
            target.destroy()
            raise

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        coarse_work = self._coarse_work
        fine_work = self._fine_work
        self._coarse_work = None
        self._fine_work = None
        self._records = ()
        self._dual_reduction_work = np.empty(0, dtype=np.complex128)
        self.local_transfer = None
        self.coarse_floquet = None
        self.fine_floquet = None
        self.coarse_space = None
        self.fine_space = None
        del coarse_work, fine_work


def build_same_mesh_hcurl_owner_transfer(
    fine_space: Any,
    fine_floquet: Any,
    coarse_space: Any,
    coarse_floquet: Any,
    *,
    local_transfer: SameMeshHcurlTransfer | None = None,
    optimization_profile: str | None = None,
    support_policy: str = SUPPORT_POLICY_LEGACY,
) -> SameMeshHcurlOwnerTransfer:
    """Build one owner-local same-mesh adapter without a global matrix."""

    pair = (
        int(fine_space.element.basix_element.degree),
        int(coarse_space.element.basix_element.degree),
    )
    if pair not in SAME_MESH_TRANSFER_PAIRS:
        raise ValueError("unsupported same-mesh owner transfer pair")
    support_policy = _normalize_support_policy(support_policy)
    if optimization_profile not in {None, _TASK041_SCHUR_SPEED_V2_PROFILE}:
        raise ValueError("unsupported same-mesh transfer optimization profile")
    if local_transfer is None:
        local_transfer = build_same_mesh_hcurl_transfer(
            *pair,
            support_policy=support_policy,
        )
    return SameMeshHcurlOwnerTransfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
        local_transfer,
        optimization_profile=optimization_profile,
        support_policy=support_policy,
    )


__all__ = [
    "ROW_CONSISTENCY_LIMIT",
    "SAME_MESH_TRANSFER_PAIRS",
    "SUPPORT_POLICY_ENTITY_CLOSURE",
    "SUPPORT_POLICY_LEGACY",
    "SameMeshHcurlOwnerTransfer",
    "SameMeshHcurlTransfer",
    "build_same_mesh_hcurl_owner_transfer",
    "build_same_mesh_hcurl_transfer",
]
