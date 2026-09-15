"""Owner-routed same-mesh p4-to-p6 H(curl) transfer for BAL_H.

The local map is the donor V5 Basix N1E map with the cell orientation
transforms on both sides.  The distributed adapter applies that map on local
cells, routes only global row ids and coefficients to their PETSc owners, and
uses the existing Floquet MPC once on each primal/dual side.  It does not
materialise a global transfer matrix or use a numerical allgather.
"""

from __future__ import annotations

from collections.abc import MutableMapping
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
) -> SameMeshHcurlTransfer:
    """Build the oriented reference-cell N1E embedding used by ``P``."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in SAME_MESH_TRANSFER_PAIRS:
        raise ValueError(
            "same-mesh transfer supports only "
            f"{SAME_MESH_TRANSFER_PAIRS}"
        )
    coarse_element = _n1e(coarse_degree)
    fine_element = _n1e(fine_degree)
    coarse_transform = _dof_transform(coarse_element, coarse_cell_info)
    fine_transform = _dof_transform(fine_element, fine_cell_info)
    reference = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    shape = (int(fine_element.dim), int(coarse_element.dim))
    if reference.shape != shape:
        raise RuntimeError(
            f"Basix N1E interpolation shape {reference.shape} != {shape}"
        )
    matrix = np.ascontiguousarray(
        fine_transform
        @ reference
        @ np.linalg.inv(coarse_transform),
        dtype=np.complex128,
    )
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
    ) -> None:
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
        self._destroyed = False
        self._last_apply_facts: dict[str, object] = {}
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
            }
        )

    @property
    def audit(self) -> MappingProxyType:
        return self._audit

    @property
    def last_apply_facts(self) -> dict[str, object]:
        return dict(self._last_apply_facts)

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

    def apply_primal_into(
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
            owned_ids, owned_values, defect, packet_size = _resolve_owner_candidates(
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
                contribution = record["matrix"].conj().T @ (
                    values * record["authority"]
                )
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
) -> SameMeshHcurlOwnerTransfer:
    """Build one owner-local same-mesh adapter without a global matrix."""

    pair = (
        int(fine_space.element.basix_element.degree),
        int(coarse_space.element.basix_element.degree),
    )
    if pair not in SAME_MESH_TRANSFER_PAIRS:
        raise ValueError("unsupported same-mesh owner transfer pair")
    if local_transfer is None:
        local_transfer = build_same_mesh_hcurl_transfer(*pair)
    return SameMeshHcurlOwnerTransfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
        local_transfer,
    )


__all__ = [
    "ROW_CONSISTENCY_LIMIT",
    "SAME_MESH_TRANSFER_PAIRS",
    "SameMeshHcurlOwnerTransfer",
    "SameMeshHcurlTransfer",
    "build_same_mesh_hcurl_owner_transfer",
    "build_same_mesh_hcurl_transfer",
]
