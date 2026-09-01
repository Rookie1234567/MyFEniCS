"""Owner-local same-mesh H(curl) transfer for the C1.1 structural oracle.

The local Basix map is supplied by :mod:`fullspace_same_mesh_hcurl_pmg`.
This adapter applies one bounded local map on each cell, routes only global
row ids and coefficients to their deterministic PETSc owners, and keeps no
global transfer matrix.  Floquet constraints are finalized by the existing
MPC exactly once on each side of an action.
"""

from __future__ import annotations

from hashlib import sha256
from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_same_mesh_hcurl_pmg import (
    SameMeshHcurlTransfer,
    build_same_mesh_hcurl_transfer,
)


ROW_CONSISTENCY_LIMIT = 1.0e-11
OWNER_RUNTIME_SCHEMA = "task038.same_mesh_hcurl_owner_transfer.v1"
SAME_MESH_OWNER_TRANSFER_PAIRS = ((3, 1), (6, 3))


def _owner_ranges(index_map: Any, comm: Any) -> tuple[tuple[int, int], ...]:
    local = (int(index_map.local_range[0]), int(index_map.local_range[1]))
    ranges = tuple(
        tuple(int(value) for value in item) for item in comm.allgather(local)
    )
    if len(ranges) != int(comm.size) or not ranges:
        raise ValueError("owner range inventory is not closed")
    if ranges[0][0] != 0 or ranges[-1][1] != int(index_map.size_global):
        raise ValueError("owner ranges do not cover the global vector")
    for left, right in zip(ranges, ranges[1:]):
        if left[1] != right[0] or left[0] >= left[1]:
            raise ValueError("owner ranges overlap or have a gap")
    if ranges[-1][0] >= ranges[-1][1]:
        raise ValueError("last owner range is empty")
    return ranges


def _owner_ranks(ids: np.ndarray, ranges: tuple[tuple[int, int], ...]) -> np.ndarray:
    values = np.asarray(ids, dtype=np.int64)
    if values.ndim != 1 or np.any(values < 0):
        raise ValueError("global ids must be a one-dimensional nonnegative array")
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ids = np.ascontiguousarray(ids, dtype=np.uint64)
    values = np.ascontiguousarray(values, dtype=np.complex128)
    if ids.ndim != 1 or values.ndim != 1 or ids.size != values.size:
        raise ValueError("candidate packet shape is not closed")
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
    recv_counts = np.empty(int(comm.size), dtype=np.int32)
    comm.Alltoall(send_counts, recv_counts)
    recv_displacements = np.zeros(int(comm.size), dtype=np.int32)
    if int(comm.size) > 1:
        recv_displacements[1:] = np.cumsum(recv_counts[:-1], dtype=np.int32)
    recv_size = int(np.sum(recv_counts, dtype=np.int64))
    recv_ids = np.empty(recv_size, dtype=np.uint64)
    recv_values = np.empty(recv_size, dtype=np.complex128)
    comm.Alltoallv(
        [send_ids, (send_counts, send_displacements), MPI.UNSIGNED_LONG_LONG],
        [recv_ids, (recv_counts, recv_displacements), MPI.UNSIGNED_LONG_LONG],
    )
    comm.Alltoallv(
        [
            send_values,
            (send_counts, send_displacements),
            MPI.C_DOUBLE_COMPLEX,
        ],
        [
            recv_values,
            (recv_counts, recv_displacements),
            MPI.C_DOUBLE_COMPLEX,
        ],
    )
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
    return recv_ids[order], recv_values[order], source_ranks[order]


def _resolve_owner_candidates(
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
    comm: Any,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    if ids.size == 0:
        raise ValueError("owner received no candidate rows")
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
        group_defect = float(np.max(np.abs(values[cursor:end] - reference_value)))
        local_defect = max(local_defect, group_defect)
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


def _space_degree(space: Any) -> int:
    return int(space.element.basix_element.degree)


def _space_mesh(space: Any) -> Any:
    return space.mesh


def _cell_global_dofs(space: Any, cell: int) -> tuple[np.ndarray, np.ndarray]:
    local = np.asarray(space.dofmap.cell_dofs(int(cell)), dtype=np.int32)
    global_ids = np.asarray(
        space.dofmap.index_map.local_to_global(local), dtype=np.int64
    )
    if global_ids.shape != local.shape or np.any(global_ids < 0):
        raise ValueError("cell dof map contains an invalid global id")
    return local, global_ids


def _finite_global(array: np.ndarray, comm: Any) -> bool:
    local = int(np.all(np.isfinite(np.asarray(array))))
    return bool(comm.allreduce(local, op=MPI.MIN))


def _mpc_constraint_residual(field: Any, floquet: Any) -> float:
    mpc = floquet.mpc
    values = np.asarray(field.x.array, dtype=np.complex128)
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    local_max = 0.0
    for slave in np.asarray(mpc.slaves, dtype=np.int64):
        slave = int(slave)
        start = int(offsets[slave])
        stop = int(offsets[slave + 1])
        masters = np.asarray(mpc.masters.links(slave), dtype=np.int64)
        if stop - start != masters.size or slave >= values.size:
            raise ValueError("MPC local constraint storage is not closed")
        expected = np.dot(coefficients[start:stop], values[masters])
        local_max = max(local_max, float(abs(values[slave] - expected)))
    return float(field.function_space.mesh.comm.allreduce(local_max, op=MPI.MAX))


def _slave_storage_max(field: Any, floquet: Any) -> float:
    values = np.asarray(field.x.array, dtype=np.complex128)
    slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
    local = float(np.max(np.abs(values[slaves]))) if slaves.size else 0.0
    return float(field.function_space.mesh.comm.allreduce(local, op=MPI.MAX))


def explicit_owner_adjoint_audit_only(owner: Any, fine_source: Any) -> Any:
    """Return an independent local ``Pᴴ`` plus direct coarse ``Cᴴ`` audit.

    This audit path intentionally bypasses the production owner-adjoint
    method.  It accumulates the bounded local maps directly and applies the
    finalized coarse MPC metadata once as a dual reducer.
    """

    fine_field = fem.Function(owner.fine_floquet.mpc.function_space)
    fine_source.copy(fine_field.x.petsc_vec)
    fine_field.x.scatter_forward()
    owner.fine_floquet.mpc.homogenize(fine_field)
    fine_field.x.scatter_forward()
    coarse_field = fem.Function(owner.coarse_floquet.mpc.function_space)
    coarse_field.x.array[:] = 0.0
    for record in owner._records:
        values = np.asarray(
            fine_field.x.array[record["fine_local"]], dtype=np.complex128
        )
        contribution = record["matrix"].conj().T @ (
            values * record["authority"]
        )
        np.add.at(coarse_field.x.array, record["coarse_local"], contribution)
    mpc = owner.coarse_floquet.mpc
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    raw = coarse_field.x.array.copy()
    for slave in np.asarray(mpc.slaves, dtype=np.int64):
        start = int(offsets[int(slave)])
        stop = int(offsets[int(slave) + 1])
        masters = np.asarray(mpc.masters.links(int(slave)), dtype=np.int64)
        coarse_field.x.array[masters] += (
            np.conjugate(coefficients[start:stop]) * raw[int(slave)]
        )
        coarse_field.x.array[int(slave)] = 0.0
    coarse_field.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    coarse_field.x.scatter_forward()
    target = create_vector(
        [
            (
                owner.coarse_space.dofmap.index_map,
                int(owner.coarse_space.dofmap.index_map_bs),
            )
        ]
    )
    coarse_field.x.petsc_vec.copy(target)
    del fine_field, coarse_field
    return target


def _dual_reduction_metadata(
    mpc: Any, local_storage: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Prepare the bounded ``C^H`` slave-to-master packet for one MPC."""

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
        flat_coefficients.extend(
            complex(np.conjugate(value)) for value in row_coefficients
        )
    return (
        slaves,
        np.asarray(flat_slaves, dtype=np.int32),
        np.asarray(flat_masters, dtype=np.int32),
        np.asarray(flat_coefficients, dtype=np.complex128),
    )


def _phase_facts(floquet: Any) -> dict[str, object]:
    values: list[tuple[str, str]] = []
    for name in ("phase_x", "phase_y", "phase_xy", "phase_xz", "phase_yz"):
        if hasattr(floquet, name):
            value = complex(getattr(floquet, name))
            values.append((name, float(value.real).hex() + ":" + float(value.imag).hex()))
    return {
        "phase_values": values,
        "phase_application": "finalized_floquet_mpc_once",
    }


class SameMeshHcurlOwnerTransfer:
    """Distributed owner-packet adapter for one same-mesh N1E pair."""

    def __init__(
        self,
        fine_space: Any,
        fine_floquet: Any,
        coarse_space: Any,
        coarse_floquet: Any,
        local_transfer: SameMeshHcurlTransfer,
    ) -> None:
        pair = (_space_degree(fine_space), _space_degree(coarse_space))
        if pair not in SAME_MESH_OWNER_TRANSFER_PAIRS:
            raise ValueError("unsupported same-mesh owner transfer pair")
        if _space_mesh(fine_space) is not _space_mesh(coarse_space):
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
        self.fine_space = fine_space
        self.coarse_space = coarse_space
        self.fine_floquet = fine_floquet
        self.coarse_floquet = coarse_floquet
        self.mesh = _space_mesh(fine_space)
        self.comm = self.mesh.comm
        self.local_transfer = local_transfer
        self._destroyed = False
        self._last_apply_facts: dict[str, object] = {}

        if getattr(fine_floquet, "mpc", None) is None or getattr(
            coarse_floquet, "mpc", None
        ) is None:
            raise ValueError("same-mesh owner transfer requires both Floquet MPCs")
        if _space_mesh(fine_floquet.mpc.function_space) is not self.mesh:
            raise ValueError("fine Floquet MPC is attached to another mesh")
        if _space_mesh(coarse_floquet.mpc.function_space) is not self.mesh:
            raise ValueError("coarse Floquet MPC is attached to another mesh")

        self.fine_ranges = _owner_ranges(fine_space.dofmap.index_map, self.comm)
        self.coarse_ranges = _owner_ranges(coarse_space.dofmap.index_map, self.comm)
        self._fine_owned_start = int(fine_space.dofmap.index_map.local_range[0])
        self._coarse_owned_start = int(coarse_space.dofmap.index_map.local_range[0])
        self._fine_owned_size = int(fine_space.dofmap.index_map.size_local)
        self._coarse_owned_size = int(coarse_space.dofmap.index_map.size_local)

        fine_topology = self.mesh.topology
        fine_topology.create_entity_permutations()
        permutation_info = np.asarray(
            fine_topology.get_cell_permutation_info(), dtype=np.uint32
        )
        cell_map = fine_topology.index_map(fine_topology.dim)
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
        nontrivial = 0
        for cell in range(cell_count):
            fine_info = int(permutation_info[cell])
            coarse_info = fine_info
            if fine_info != 0 and cell < owned_cell_count:
                nontrivial += 1
            key = (fine_info, coarse_info)
            if key not in cache:
                cache[key] = build_same_mesh_hcurl_transfer(
                    pair[0], pair[1],
                    coarse_cell_info=coarse_info,
                    fine_cell_info=fine_info,
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
                    "cell_info": key,
                }
            )
        fine_expected = set(
            range(
                int(self.fine_ranges[self.comm.rank][0]),
                int(self.fine_ranges[self.comm.rank][1]),
            )
        )
        coarse_expected = set(
            range(
                int(self.coarse_ranges[self.comm.rank][0]),
                int(self.coarse_ranges[self.comm.rank][1]),
            )
        )
        if set(authority) != fine_expected:
            raise ValueError("fine owner rows do not have a local canonical authority")
        if coarse_seen != coarse_expected:
            raise ValueError("coarse owner columns do not have local cell coverage")
        self._records = tuple(records)
        self._map_cache = tuple(cache.items())
        self._authority = authority
        self._coarse_work = fem.Function(coarse_floquet.mpc.function_space)
        self._fine_work = fem.Function(fine_floquet.mpc.function_space)
        (
            self._coarse_slaves,
            self._dual_flat_slaves,
            self._dual_flat_masters,
            self._dual_conjugated_coefficients,
        ) = _dual_reduction_metadata(
            coarse_floquet.mpc, self._coarse_work.x.array.size
        )
        self._dual_reduction_work = np.empty(
            self._dual_flat_slaves.size, dtype=np.complex128
        )

        local_min = np.min(np.asarray(self.mesh.geometry.x), axis=0)
        local_max = np.max(np.asarray(self.mesh.geometry.x), axis=0)
        global_min = np.empty_like(local_min)
        global_max = np.empty_like(local_max)
        self.comm.Allreduce(local_min, global_min, op=MPI.MIN)
        self.comm.Allreduce(local_max, global_max, op=MPI.MAX)
        global_cells = int(self.comm.allreduce(owned_cell_count, op=MPI.SUM))
        fine_phase = _phase_facts(fine_floquet)
        coarse_phase = _phase_facts(coarse_floquet)
        digest_payload = (
            pair,
            int(fine_space.dofmap.index_map.size_global),
            int(coarse_space.dofmap.index_map.size_global),
            global_cells,
            tuple(float(value).hex() for value in global_min),
            tuple(float(value).hex() for value in global_max),
            tuple(fine_phase["phase_values"]),
            tuple(coarse_phase["phase_values"]),
        )
        canonical_digest = sha256(repr(digest_payload).encode("ascii")).hexdigest()
        nontrivial_present = bool(
            self.comm.allreduce(int(nontrivial > 0), op=MPI.LOR)
        )
        fine_mpc_index_map = fine_floquet.mpc.function_space.dofmap.index_map
        fine_owned_scalar_size = int(fine_mpc_index_map.size_local) * int(
            fine_floquet.mpc.function_space.dofmap.index_map_bs
        )
        fine_mpc_slaves = np.asarray(fine_floquet.mpc.slaves, dtype=np.int64)
        fine_owned_mpc_count = int(
            np.count_nonzero(
                (fine_mpc_slaves >= 0) & (fine_mpc_slaves < fine_owned_scalar_size)
            )
        )
        coarse_mpc_index_map = coarse_floquet.mpc.function_space.dofmap.index_map
        coarse_owned_scalar_size = int(coarse_mpc_index_map.size_local) * int(
            coarse_floquet.mpc.function_space.dofmap.index_map_bs
        )
        coarse_mpc_slaves = np.asarray(
            coarse_floquet.mpc.slaves, dtype=np.int64
        )
        coarse_owned_mpc_count = int(
            np.count_nonzero(
                (coarse_mpc_slaves >= 0)
                & (coarse_mpc_slaves < coarse_owned_scalar_size)
            )
        )
        self._audit = MappingProxyType(
            {
                "schema": OWNER_RUNTIME_SCHEMA,
                "pair_fine_to_coarse": [int(pair[0]), int(pair[1])],
                "fine_degree": int(pair[0]),
                "coarse_degree": int(pair[1]),
                "fine_lagrange_variant": fine_variant,
                "coarse_lagrange_variant": coarse_variant,
                "fine_global_rows": int(fine_space.dofmap.index_map.size_global),
                "coarse_global_rows": int(coarse_space.dofmap.index_map.size_global),
                "fine_local_owned_rows": self._fine_owned_size,
                "coarse_local_owned_rows": self._coarse_owned_size,
                "fine_owner_ranges": [list(item) for item in self.fine_ranges],
                "coarse_owner_ranges": [list(item) for item in self.coarse_ranges],
                "cell_count_local": cell_count,
                "cell_count_global": global_cells,
                "cell_map_cache_count": len(cache),
                "local_cache_array_bytes": int(
                    sum(int(transfer.matrix.nbytes) for transfer in cache.values())
                ),
                "nontrivial_cell_permutation_count_local": nontrivial,
                "nontrivial_cell_permutation_present_global": nontrivial_present,
                "canonical_global_digest": canonical_digest,
                "canonical_digest_scope": "mesh-bounds/layout/phase metadata only",
                "zero_owned_fine_rows": 0,
                "zero_owned_coarse_columns": 0,
                "owner_local": True,
                "owner_ghost_identity": True,
                "owner_row_authority": "fine_owner_rank_then_local_cell_order",
                "orientation_application": "Basix_T_apply_exact_cell_permutation",
                **fine_phase,
                "coarse_phase_values": coarse_phase["phase_values"],
                "coarse_phase_application": coarse_phase["phase_application"],
                "coarse_dual_reduction": "C^H_once",
                "fine_mpc_slave_count_global": int(
                    self.comm.allreduce(fine_owned_mpc_count, op=MPI.SUM)
                ),
                "coarse_mpc_slave_count_global": int(
                    self.comm.allreduce(coarse_owned_mpc_count, op=MPI.SUM)
                ),
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "static_condensation": False,
                "physical": False,
                "pde": False,
                "ksp_created": False,
                "vcycle_created": False,
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
        ids: list[np.ndarray] = []
        values: list[np.ndarray] = []
        for record in self._records:
            local_values = np.asarray(
                self._coarse_work.x.array[record["coarse_local"]],
                dtype=np.complex128,
            )
            ids.append(record["fine_global"])
            values.append(record["matrix"] @ local_values)
        return np.concatenate(ids), np.concatenate(values)

    def apply_primal_into(self, source: Any, target: Any) -> None:
        self._require_live()
        self._require_vector(target, self.fine_space.dofmap.index_map)
        self._prepare_primal(source, self._coarse_work, self.coarse_floquet)
        candidate_ids, candidate_values = self._candidate_packet()
        if not np.all(np.isfinite(candidate_values)):
            raise RuntimeError("same-mesh primal candidates are non-finite")
        received_ids, received_values, source_ranks = _alltoallv_candidates(
            candidate_ids, candidate_values, self.fine_ranges, self.comm
        )
        owned_ids, owned_values, defect, packet_size = _resolve_owner_candidates(
            received_ids, received_values, source_ranks, self.comm.rank, self.comm
        )
        self._fine_work.x.array[:] = 0.0
        local_ids = owned_ids.astype(np.int64) - self._fine_owned_start
        if np.any(local_ids < 0) or np.any(local_ids >= self._fine_owned_size):
            raise ValueError("resolved owner ids are not locally owned")
        self._fine_work.x.array[local_ids] = owned_values
        self._fine_work.x.scatter_forward()
        self._finalize_primal(self._fine_work, self.fine_floquet)
        constraint = _mpc_constraint_residual(self._fine_work, self.fine_floquet)
        finite = _finite_global(self._fine_work.x.array, self.comm)
        if not finite or not np.isfinite(constraint):
            raise RuntimeError("same-mesh primal output is non-finite")
        self._fine_work.x.petsc_vec.copy(target)
        self._last_apply_facts = {
            "operation": "primal",
            "finite": finite,
            "input_unchanged": True,
            "owner_packet_rows": packet_size,
            "shared_row_max_defect": defect,
            "fine_mpc_constraint_residual": constraint,
            "phase_application": "finalized_floquet_mpc_once",
        }

    def apply_primal(self, source: Any) -> Any:
        self._require_live()
        target = create_vector(
            [
                (
                    self.fine_space.dofmap.index_map,
                    int(self.fine_space.dofmap.index_map_bs),
                )
            ]
        )
        self.apply_primal_into(source, target)
        return target

    def apply_adjoint_into(self, source: Any, target: Any) -> None:
        self._require_live()
        self._require_vector(source, self.fine_space.dofmap.index_map)
        self._require_vector(target, self.coarse_space.dofmap.index_map)
        source.copy(self._fine_work.x.petsc_vec)
        self._fine_work.x.scatter_forward()
        self.fine_floquet.mpc.homogenize(self._fine_work)
        self._fine_work.x.scatter_forward()
        self._coarse_work.x.array[:] = 0.0
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
        if self._dual_flat_slaves.size:
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
            self._coarse_work.x.array[self._coarse_slaves] = 0.0
        self._coarse_work.x.petsc_vec.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self._coarse_work.x.scatter_forward()
        finite = _finite_global(self._coarse_work.x.array, self.comm)
        slave_max = _slave_storage_max(self._coarse_work, self.coarse_floquet)
        if not finite or not np.isfinite(slave_max):
            raise RuntimeError("same-mesh adjoint output is non-finite")
        self._coarse_work.x.petsc_vec.copy(target)
        self._last_apply_facts = {
            "operation": "adjoint",
            "finite": finite,
            "input_unchanged": True,
            "coarse_slave_storage_max": slave_max,
            "coarse_dual_reduction": "C^H_once",
            "phase_application": "fine_dual_homogenize_then_coarse_C^H_once",
        }

    def apply_adjoint(self, source: Any) -> Any:
        self._require_live()
        target = create_vector(
            [
                (
                    self.coarse_space.dofmap.index_map,
                    int(self.coarse_space.dofmap.index_map_bs),
                )
            ]
        )
        self.apply_adjoint_into(source, target)
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        coarse_work = self._coarse_work
        fine_work = self._fine_work
        self._coarse_work = None
        self._fine_work = None
        self._records = ()
        self._map_cache = ()
        self._authority = {}
        self._coarse_slaves = np.empty(0, dtype=np.int32)
        self._dual_flat_slaves = np.empty(0, dtype=np.int32)
        self._dual_flat_masters = np.empty(0, dtype=np.int32)
        self._dual_conjugated_coefficients = np.empty(0, dtype=np.complex128)
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
    """Build one owner-local same-mesh adapter without a global transfer."""

    pair = (_space_degree(fine_space), _space_degree(coarse_space))
    if pair not in SAME_MESH_OWNER_TRANSFER_PAIRS:
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
    "OWNER_RUNTIME_SCHEMA",
    "ROW_CONSISTENCY_LIMIT",
    "SAME_MESH_OWNER_TRANSFER_PAIRS",
    "SameMeshHcurlOwnerTransfer",
    "build_same_mesh_hcurl_owner_transfer",
    "explicit_owner_adjoint_audit_only",
]
