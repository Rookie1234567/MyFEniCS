"""Packed owner-local topology for the structured H(curl) LOR path.

The setup phase derives canonical refined-edge ids and fixed typed MPI schedules.
The apply phase consumes one bounded cell chunk at a time and retains only the
local unique-edge vector; it never materializes a cell-by-edge value matrix or
sorts the full edge inventory.  Coordinate lists exchanged during setup are
metadata, not numerical field payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from mpi4py import MPI

from .hcurl_canonical_vector_dolfinx import _entity_coordinates
from .fullspace_lor_transfer import LOR_BATCH_CELL_CAP, _edge_endpoints

PACKED_COORDINATE_BITS = 10
PACKED_COORDINATE_LIMIT = 1 << PACKED_COORDINATE_BITS
P6_H10_REFERENCE_CELL_EDGE_COUNT = 882
P6_H10_REFERENCE_CELL_COUNT = 54_432
P6_H10_REFERENCE_UNIQUE_EDGE_COUNT = 173_802
# Review V7's canonical source/action identity Gate; this is the route's
# shared-edge consistency check, not a result-dependent solver tolerance.
LOR_ROUTE_TOL = 1.0e-12


def _readonly(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array)
    array.setflags(write=False)
    return array


def _displacements(counts: np.ndarray) -> np.ndarray:
    counts = np.asarray(counts, dtype=np.int32)
    result = np.zeros(counts.size, dtype=np.int32)
    if counts.size > 1:
        result[1:] = np.cumsum(counts[:-1], dtype=np.int64).astype(np.int32)
    return result


def _alltoallv(
    comm: MPI.Comm,
    values: np.ndarray,
    send_counts: np.ndarray,
    mpi_type: MPI.Datatype,
    *,
    recv_counts: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Exchange a typed flat buffer with precomputed counts when supplied."""

    send_counts = np.asarray(send_counts, dtype=np.int32)
    if recv_counts is None:
        recv_counts = np.empty(comm.size, dtype=np.int32)
        comm.Alltoall([send_counts, MPI.INT], [recv_counts, MPI.INT])
    else:
        recv_counts = np.asarray(recv_counts, dtype=np.int32)
    send_displacements = _displacements(send_counts)
    recv_displacements = _displacements(recv_counts)
    values = np.ascontiguousarray(values)
    received = np.empty(int(np.sum(recv_counts, dtype=np.int64)), dtype=values.dtype)
    comm.Alltoallv(
        [values, send_counts, send_displacements, mpi_type],
        [received, recv_counts, recv_displacements, mpi_type],
    )
    return received, recv_counts


def _group_by_owner(
    ids: np.ndarray, size: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ids = np.asarray(ids, dtype=np.uint32)
    owners = (ids.astype(np.uint64) % int(size)).astype(np.int32)
    order = np.argsort(owners, kind="stable").astype(np.int32)
    counts = np.bincount(owners, minlength=int(size)).astype(np.int32)
    return order, counts, _displacements(counts), ids[order]


def _merge_coordinates(parts: Iterable[Iterable[float]]) -> np.ndarray:
    values = np.asarray(
        [float(value) for part in parts for value in part], dtype=np.float64
    )
    if values.size == 0:
        raise ValueError("LOR topology received no coordinate metadata")
    values.sort()
    merged = [float(values[0])]
    for value in values[1:]:
        previous = merged[-1]
        if abs(float(value) - previous) > 1.0e-11 * max(
            1.0, abs(previous), abs(float(value))
        ):
            merged.append(float(value))
    result = np.asarray(merged, dtype=np.float64)
    if result.size >= PACKED_COORDINATE_LIMIT:
        raise ValueError("canonical LOR coordinate inventory exceeds packed id width")
    return result


def _coordinate_indices(values: np.ndarray, coordinates: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    right = np.searchsorted(coordinates, values, side="left")
    right = np.clip(right, 0, coordinates.size - 1)
    left = np.maximum(right - 1, 0)
    choose_left = np.abs(coordinates[left] - values) <= np.abs(
        coordinates[right] - values
    )
    indices = np.where(choose_left, left, right).astype(np.int32)
    error = np.abs(coordinates[indices] - values)
    if np.any(error > 1.0e-10 * np.maximum(1.0, np.abs(values))):
        raise ValueError("cell coordinate is absent from canonical LOR lattice")
    return indices


def _phase_code(
    start_upper: tuple[bool, bool], end_upper: tuple[bool, bool]
) -> int:
    """Return a phase code only when an entire edge is on a slave plane."""

    code = 0
    if bool(start_upper[0] and end_upper[0]):
        code |= 1
    if bool(start_upper[1] and end_upper[1]):
        code |= 2
    return code


def _phase_codes(start: np.ndarray, end: np.ndarray, upper: np.ndarray) -> np.ndarray:
    both_x = (start[:, 0] == upper[0]) & (end[:, 0] == upper[0])
    both_y = (start[:, 1] == upper[1]) & (end[:, 1] == upper[1])
    return (both_x.astype(np.uint8) + 2 * both_y.astype(np.uint8)).astype(np.uint8)


def _packed_edge_ids(start: np.ndarray, end: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    delta = end.astype(np.int32) - start.astype(np.int32)
    axis = np.argmax(np.abs(delta), axis=1).astype(np.uint32)
    if np.any(np.sum(delta != 0, axis=1) != 1):
        raise ValueError("LOR subedge is not axis aligned")
    lower = np.minimum(start, end).astype(np.uint32)
    if np.any(lower >= PACKED_COORDINATE_LIMIT):
        raise ValueError("LOR coordinate cannot be packed in ten bits")
    ids = (
        (axis << 30)
        | (lower[:, 0] << 20)
        | (lower[:, 1] << 10)
        | lower[:, 2]
    ).astype(np.uint32)
    orientation = np.where(
        np.take_along_axis(delta, axis[:, None], axis=1)[:, 0] >= 0,
        1,
        -1,
    ).astype(np.int8)
    return ids, orientation


def _pack_canonical_edges(
    start: np.ndarray, end: np.ndarray, upper: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Map complete slave-plane edges to their lower/master packed edge."""

    phase_codes = _phase_codes(start, end, upper)
    canonical_start = np.asarray(start, dtype=np.int32).copy()
    canonical_end = np.asarray(end, dtype=np.int32).copy()
    x_slave = (phase_codes & 1) != 0
    y_slave = (phase_codes & 2) != 0
    canonical_start[x_slave, 0] = 0
    canonical_end[x_slave, 0] = 0
    canonical_start[y_slave, 1] = 0
    canonical_end[y_slave, 1] = 0
    ids, orientation = _packed_edge_ids(canonical_start, canonical_end)
    return ids, orientation, phase_codes


def _schedule(ids: np.ndarray, comm: MPI.Comm) -> dict[str, np.ndarray]:
    order, counts, displacements, send_ids = _group_by_owner(ids, comm.size)
    received_ids, receive_counts = _alltoallv(
        comm, send_ids, counts, MPI.UNSIGNED
    )
    return {
        "send_order": _readonly(order),
        "send_counts": _readonly(counts),
        "send_displacements": _readonly(displacements),
        "send_ids": _readonly(send_ids),
        "receive_ids": _readonly(received_ids),
        "receive_counts": _readonly(receive_counts),
        "receive_displacements": _readonly(_displacements(receive_counts)),
    }


def _schedule_bytes(schedule: dict[str, np.ndarray]) -> int:
    return int(sum(value.nbytes for value in schedule.values()))


@dataclass(frozen=True)
class CanonicalLORSubedgeTopology:
    """Packed setup data and fixed owner/request schedules for one mesh."""

    degree: int
    edge_count: int
    cell_edge_ids: np.ndarray
    cell_orientation: np.ndarray
    cell_phase_codes: np.ndarray
    phase_values: np.ndarray
    unique_edge_ids: np.ndarray
    owned_edge_ids: np.ndarray
    owner_schedule: dict[str, np.ndarray]
    owner_received_sort_order: np.ndarray
    owner_received_sorted_ids: np.ndarray
    owner_received_group_starts: np.ndarray
    pull_schedule: dict[str, np.ndarray]
    pull_received_positions: np.ndarray
    pull_send_positions: np.ndarray
    comm: MPI.Comm
    audit: dict[str, Any]

    def route_owner_cell_chunks(
        self, chunks: Iterable[tuple[int, np.ndarray]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Canonicalize bounded cell chunks and route only unique-edge values."""

        local_unique_values = np.zeros(
            self.unique_edge_ids.size, dtype=np.complex128
        )
        seen = np.zeros(self.unique_edge_ids.size, dtype=np.bool_)
        expected_cell = 0
        for cell_start, values in chunks:
            cell_start = int(cell_start)
            values = np.asarray(values, dtype=np.complex128)
            if cell_start != expected_cell:
                raise ValueError("cell chunks must be contiguous and canonical ordered")
            if values.ndim != 2 or values.shape[1] != self.edge_count:
                raise ValueError("cell chunk has an unexpected edge dimension")
            cell_count = int(values.shape[0])
            if cell_count < 1 or cell_count > int(self.audit["apply_chunk_cell_cap"]):
                raise ValueError("cell chunk exceeds the fixed streaming cap")
            cell_end = cell_start + cell_count
            if cell_end > self.cell_edge_ids.shape[0]:
                raise ValueError("cell chunk exceeds the local cell inventory")
            phase = self.phase_values[self.cell_phase_codes[cell_start:cell_end]]
            canonical = (
                values
                * self.cell_orientation[cell_start:cell_end]
                / phase
            )
            flat_ids = self.cell_edge_ids[cell_start:cell_end].reshape(-1)
            flat_values = canonical.reshape(-1)
            positions = np.searchsorted(self.unique_edge_ids, flat_ids)
            if np.any(
                positions >= self.unique_edge_ids.size
            ) or not np.array_equal(
                self.unique_edge_ids[np.minimum(positions, self.unique_edge_ids.size - 1)],
                flat_ids,
            ):
                raise ValueError("cell chunk contains an unknown packed edge id")
            positions_by_cell = positions.reshape((cell_count, self.edge_count))
            values_by_cell = flat_values.reshape((cell_count, self.edge_count))
            for cell_offset in range(cell_count):
                cell_positions = positions_by_cell[cell_offset]
                cell_values = values_by_cell[cell_offset]
                repeated = seen[cell_positions]
                if np.any(repeated):
                    difference = np.abs(
                        cell_values[repeated]
                        - local_unique_values[cell_positions[repeated]]
                    )
                    scale = np.maximum(
                        1.0,
                        np.maximum(
                            np.abs(cell_values[repeated]),
                            np.abs(local_unique_values[cell_positions[repeated]]),
                        ),
                    )
                    if np.any(difference > LOR_ROUTE_TOL * scale):
                        raise ValueError("shared local edge values disagree")
                new_positions = cell_positions[~repeated]
                local_unique_values[new_positions] = cell_values[~repeated]
                seen[new_positions] = True
                seen[cell_positions] = True
            expected_cell = cell_end
        if expected_cell != self.cell_edge_ids.shape[0] or not np.all(seen):
            raise ValueError("streaming chunks did not cover every local cell edge")

        send_values = local_unique_values[self.owner_schedule["send_order"]]
        received_values, _ = _alltoallv(
            self.comm,
            send_values,
            self.owner_schedule["send_counts"],
            MPI.DOUBLE_COMPLEX,
            recv_counts=self.owner_schedule["receive_counts"],
        )
        sort_order = self.owner_received_sort_order
        sorted_ids = self.owner_received_sorted_ids
        sorted_values = received_values[sort_order]
        if sorted_values.size > 1:
            same_id = sorted_ids[1:] == sorted_ids[:-1]
            if np.any(same_id):
                difference = np.abs(sorted_values[1:] - sorted_values[:-1])
                scale = np.maximum(
                    1.0,
                    np.maximum(
                        np.abs(sorted_values[1:]), np.abs(sorted_values[:-1])
                    ),
                )
                if np.any(difference[same_id] > LOR_ROUTE_TOL * scale[same_id]):
                    raise ValueError("owner ranks received inconsistent edge values")
        owned_values = sorted_values[self.owner_received_group_starts].copy()
        owned_values.setflags(write=False)
        return self.owned_edge_ids, owned_values

    def route_owner_cell_chunks_additive(
        self, chunks: Iterable[tuple[int, np.ndarray]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Route cell contributions whose shared edges must be summed.

        This is the dual counterpart of :meth:`route_owner_cell_chunks`.
        Cell contributions are accumulated in the local unique-edge buffer and
        then reduced once at the deterministic edge owners.  It deliberately
        does not apply the primal shared-value consistency test.
        """

        local_unique_values = np.zeros(
            self.unique_edge_ids.size, dtype=np.complex128
        )
        seen = np.zeros(self.unique_edge_ids.size, dtype=np.bool_)
        expected_cell = 0
        for cell_start, values in chunks:
            cell_start = int(cell_start)
            values = np.asarray(values, dtype=np.complex128)
            if cell_start != expected_cell:
                raise ValueError("cell chunks must be contiguous and canonical ordered")
            if values.ndim != 2 or values.shape[1] != self.edge_count:
                raise ValueError("cell chunk has an unexpected edge dimension")
            cell_count = int(values.shape[0])
            if cell_count < 1 or cell_count > int(self.audit["apply_chunk_cell_cap"]):
                raise ValueError("cell chunk exceeds the fixed streaming cap")
            cell_end = cell_start + cell_count
            if cell_end > self.cell_edge_ids.shape[0]:
                raise ValueError("cell chunk exceeds the local cell inventory")
            phase = self.phase_values[self.cell_phase_codes[cell_start:cell_end]]
            canonical = (
                values
                * self.cell_orientation[cell_start:cell_end]
                / phase
            )
            flat_ids = self.cell_edge_ids[cell_start:cell_end].reshape(-1)
            positions = np.searchsorted(self.unique_edge_ids, flat_ids)
            if np.any(positions >= self.unique_edge_ids.size) or not np.array_equal(
                self.unique_edge_ids[
                    np.minimum(positions, self.unique_edge_ids.size - 1)
                ],
                flat_ids,
            ):
                raise ValueError("cell chunk contains an unknown packed edge id")
            positions_by_cell = positions.reshape((cell_count, self.edge_count))
            values_by_cell = canonical.reshape((cell_count, self.edge_count))
            for cell_offset in range(cell_count):
                cell_positions = positions_by_cell[cell_offset]
                np.add.at(local_unique_values, cell_positions, values_by_cell[cell_offset])
                seen[cell_positions] = True
            expected_cell = cell_end
        if expected_cell != self.cell_edge_ids.shape[0] or not np.all(seen):
            raise ValueError("streaming chunks did not cover every local cell edge")

        send_values = local_unique_values[self.owner_schedule["send_order"]]
        received_values, _ = _alltoallv(
            self.comm,
            send_values,
            self.owner_schedule["send_counts"],
            MPI.DOUBLE_COMPLEX,
            recv_counts=self.owner_schedule["receive_counts"],
        )
        sort_order = self.owner_received_sort_order
        sorted_ids = self.owner_received_sorted_ids
        sorted_values = received_values[sort_order]
        if sorted_values.size:
            owned_values = np.add.reduceat(
                sorted_values, self.owner_received_group_starts
            ).astype(np.complex128, copy=False)
        else:
            owned_values = np.empty(0, dtype=np.complex128)
        owned_values.setflags(write=False)
        return self.owned_edge_ids, owned_values

    def pull_owner_unique_values(
        self, owned_ids: np.ndarray, owned_values: np.ndarray
    ) -> np.ndarray:
        """Return a unique-edge vector in this rank's setup order."""

        owned_ids = np.asarray(owned_ids, dtype=np.uint32)
        owned_values = np.asarray(owned_values, dtype=np.complex128)
        if not np.array_equal(owned_ids, self.owned_edge_ids):
            raise ValueError("owner packet ids do not match the setup schedule")
        if owned_values.shape != owned_ids.shape:
            raise ValueError("owner packet values do not match packet ids")
        replies = owned_values[self.pull_received_positions]
        received, _ = _alltoallv(
            self.comm,
            replies,
            self.pull_schedule["receive_counts"],
            MPI.DOUBLE_COMPLEX,
            recv_counts=self.pull_schedule["send_counts"],
        )
        unique_values = np.empty(self.unique_edge_ids.size, dtype=np.complex128)
        unique_values[self.pull_send_positions] = received
        unique_values.setflags(write=False)
        return unique_values

    def cell_values_from_unique(
        self, unique_values: np.ndarray, cell_start: int, cell_end: int
    ) -> np.ndarray:
        """Expand only a bounded cell chunk back to local edge order."""

        cell_start, cell_end = int(cell_start), int(cell_end)
        if cell_end <= cell_start or cell_end - cell_start > int(
            self.audit["apply_chunk_cell_cap"]
        ):
            raise ValueError("cell expansion exceeds the fixed streaming cap")
        unique_values = np.asarray(unique_values, dtype=np.complex128)
        if unique_values.shape != self.unique_edge_ids.shape:
            raise ValueError("unique-edge vector has an unexpected shape")
        ids = self.cell_edge_ids[cell_start:cell_end]
        positions = np.searchsorted(self.unique_edge_ids, ids)
        if np.any(positions >= self.unique_edge_ids.size) or not np.array_equal(
            self.unique_edge_ids[np.minimum(positions, self.unique_edge_ids.size - 1)], ids
        ):
            raise ValueError("cell expansion contains an unknown packed edge id")
        phase = self.phase_values[self.cell_phase_codes[cell_start:cell_end]]
        return unique_values[positions] * self.cell_orientation[cell_start:cell_end] * phase


def global_lor_edge_roundtrip(
    function_space: Any,
    floquet_data: Any,
    source_field: Any,
    transfer: Any,
) -> tuple[Any, tuple[np.ndarray, np.ndarray], float, CanonicalLORSubedgeTopology]:
    """Apply the production batched H-to-LOR-to-H owner route.

    Cell orientation transforms, fixed-size batched transfer, typed owner
    routing, and finalized MPC backsubstitution are kept in this reusable
    path so tests and benchmark runners do not carry a second numerical
    implementation.  Only owner-local LOR values cross MPI; canonical packet
    gathering, when requested by a caller, remains evidence-only.
    """

    from dolfinx import fem
    from petsc4py import PETSc

    comm = function_space.mesh.comm
    work_space = floquet_data.mpc.function_space
    topology = build_canonical_lor_subedge_topology(
        function_space, floquet_data, transfer
    )
    cell_info = np.asarray(
        function_space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    local_max_error = 0.0
    batch_sizes: list[int] = []

    def cell_chunks():
        nonlocal local_max_error
        batch_start = 0
        canonical_batch: list[np.ndarray] = []
        for cell in range(topology.cell_edge_ids.shape[0]):
            local_dofs = np.asarray(
                work_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            raw = np.asarray(
                source_field.x.array[local_dofs], dtype=np.complex128
            ).copy()
            canonical = raw.copy()
            work_space.element.Tt_apply(
                canonical, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            canonical_batch.append(canonical)
            if (
                len(canonical_batch) == LOR_BATCH_CELL_CAP
                or cell + 1 == topology.cell_edge_ids.shape[0]
            ):
                batch = np.asarray(canonical_batch, dtype=np.complex128)
                lor_batch = transfer.high_to_lor_many(batch)
                restored_batch = transfer.lor_to_high_many(lor_batch)
                errors = np.linalg.norm(restored_batch - batch, axis=1) / np.maximum(
                    np.linalg.norm(batch, axis=1), np.finfo(float).tiny
                )
                local_max_error = max(local_max_error, float(np.max(errors)))
                batch_sizes.append(len(canonical_batch))
                yield batch_start, lor_batch
                batch_start = cell + 1
                canonical_batch = []

    owner_ids, owner_values = topology.route_owner_cell_chunks(cell_chunks())
    unique_values = topology.pull_owner_unique_values(owner_ids, owner_values)
    roundtrip = fem.Function(work_space)
    multiplicity = fem.Function(work_space)
    roundtrip.x.array[:] = 0.0
    multiplicity.x.array[:] = 0.0
    for cell_start in range(0, topology.cell_edge_ids.shape[0], LOR_BATCH_CELL_CAP):
        cell_end = min(
            cell_start + LOR_BATCH_CELL_CAP, topology.cell_edge_ids.shape[0]
        )
        pulled_lor = topology.cell_values_from_unique(
            unique_values, cell_start, cell_end
        )
        canonical_batch = transfer.lor_to_high_many(pulled_lor)
        for offset, cell in enumerate(range(cell_start, cell_end)):
            local_dofs = np.asarray(
                work_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            stored = canonical_batch[offset].copy()
            work_space.element.T_apply(
                stored, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            roundtrip.x.array[local_dofs] += stored
            multiplicity.x.array[local_dofs] += 1.0
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    multiplicity.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    owned = int(work_space.dofmap.index_map.size_local)
    if np.any(np.real(multiplicity.x.array[:owned]) <= 0.0):
        raise AssertionError("real-cell transfer did not cover owned rows")
    roundtrip.x.array[:owned] /= multiplicity.x.array[:owned]
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
    )
    floquet_data.mpc.homogenize(roundtrip)
    floquet_data.mpc.backsubstitution(roundtrip)
    roundtrip.x.scatter_forward()
    local_max_error = comm.allreduce(local_max_error, op=MPI.MAX)
    if topology.cell_edge_ids.shape[0] >= 2:
        assert max(batch_sizes) >= 2
    del multiplicity
    return roundtrip, (owner_ids, owner_values), float(local_max_error), topology


def build_canonical_lor_subedge_topology(
    function_space: Any, floquet_data: Any, transfer: Any
) -> CanonicalLORSubedgeTopology:
    """Build packed shared-edge metadata and typed owner/request schedules."""

    comm = function_space.mesh.comm
    degree = int(transfer.degree)
    edge_count = int(transfer.edge_count)
    starts, ends = _edge_endpoints(degree)
    if edge_count != starts.shape[0]:
        raise ValueError("transfer and edge endpoint inventories disagree")
    cell_count = int(function_space.mesh.topology.index_map(3).size_local)
    bounds = np.empty((cell_count, 2, 3), dtype=np.float64)
    local_axis_values = [[], [], []]
    for cell in range(cell_count):
        coordinates = _entity_coordinates(function_space, 3, cell)
        bounds[cell, 0] = np.min(coordinates, axis=0)
        bounds[cell, 1] = np.max(coordinates, axis=0)
        for axis in range(3):
            values = bounds[cell, 0, axis] + (
                bounds[cell, 1, axis] - bounds[cell, 0, axis]
            ) * np.asarray(transfer.nodes, dtype=np.float64)
            local_axis_values[axis].extend(values.tolist())
    coordinates = tuple(
        _merge_coordinates(comm.allgather(np.unique(values).tolist()))
        for values in local_axis_values
    )
    upper = np.asarray([values.size - 1 for values in coordinates], dtype=np.int32)
    cell_edge_ids = np.empty((cell_count, edge_count), dtype=np.uint32)
    cell_orientation = np.empty((cell_count, edge_count), dtype=np.int8)
    cell_phase_codes = np.empty((cell_count, edge_count), dtype=np.uint8)
    single_endpoint_local = 0
    for cell in range(cell_count):
        local_indices = tuple(
            _coordinate_indices(
                bounds[cell, 0, axis]
                + (bounds[cell, 1, axis] - bounds[cell, 0, axis])
                * np.asarray(transfer.nodes, dtype=np.float64),
                coordinates[axis],
            )
            for axis in range(3)
        )
        start_indices = np.column_stack(
            [local_indices[axis][starts[:, axis]] for axis in range(3)]
        )
        end_indices = np.column_stack(
            [local_indices[axis][ends[:, axis]] for axis in range(3)]
        )
        ids, orientations, phase_codes = _pack_canonical_edges(
            start_indices, end_indices, upper
        )
        cell_edge_ids[cell] = ids
        cell_orientation[cell] = orientations
        cell_phase_codes[cell] = phase_codes
        any_upper = np.any(
            (start_indices[:, :2] == upper[:2])
            | (end_indices[:, :2] == upper[:2]),
            axis=1,
        )
        single_endpoint_local += int(np.count_nonzero(any_upper & (phase_codes == 0)))
        if np.unique(cell_edge_ids[cell]).size != edge_count:
            raise ValueError("one cell contains duplicate packed LOR edges")
    cell_edge_ids.setflags(write=False)
    cell_orientation.setflags(write=False)
    cell_phase_codes.setflags(write=False)
    unique_edge_ids = _readonly(np.unique(cell_edge_ids.reshape(-1)).astype(np.uint32))
    owner_schedule = _schedule(unique_edge_ids, comm)
    owner_received_ids = owner_schedule["receive_ids"]
    owner_received_sort_order = np.argsort(owner_received_ids, kind="stable").astype(np.int32)
    owner_received_sorted_ids = owner_received_ids[owner_received_sort_order]
    if owner_received_sorted_ids.size:
        owner_received_group_starts = np.flatnonzero(
            np.r_[True, owner_received_sorted_ids[1:] != owner_received_sorted_ids[:-1]]
        ).astype(np.int32)
    else:
        owner_received_group_starts = np.empty(0, dtype=np.int32)
    owned_edge_ids = _readonly(owner_received_sorted_ids[owner_received_group_starts])
    # The request ids are exactly the local unique ids grouped by the same
    # deterministic owner.  Reuse this one typed setup schedule for both the
    # owner registration and the later value pull; no second id table or
    # per-apply ordering is needed.
    pull_schedule = owner_schedule
    pull_received_ids = pull_schedule["receive_ids"]
    pull_received_positions = np.searchsorted(owned_edge_ids, pull_received_ids).astype(np.int32)
    if np.any(
        pull_received_positions >= owned_edge_ids.size
    ) or not np.array_equal(
        owned_edge_ids[np.minimum(pull_received_positions, owned_edge_ids.size - 1)],
        pull_received_ids,
    ):
        raise ValueError("owner/request schedule contains an unowned edge")
    pull_send_positions = _readonly(
        np.asarray(pull_schedule["send_order"], dtype=np.int32)
    )
    phase_x = complex(getattr(floquet_data, "phase_x"))
    phase_y = complex(getattr(floquet_data, "phase_y"))
    phase_corner = complex(getattr(floquet_data, "phase_corner"))
    phase_values = _readonly(np.asarray([1.0 + 0.0j, phase_x, phase_y, phase_corner]))
    phase_counts_local = np.bincount(cell_phase_codes.reshape(-1), minlength=4).astype(np.int64)
    phase_counts = np.asarray(comm.allreduce(phase_counts_local, op=MPI.SUM), dtype=np.int64)
    single_endpoint_count = int(comm.allreduce(single_endpoint_local, op=MPI.SUM))
    local_map_bytes = int(
        cell_edge_ids.nbytes + cell_orientation.nbytes + cell_phase_codes.nbytes
    )
    global_map_bytes = int(comm.allreduce(local_map_bytes, op=MPI.SUM))
    max_map_bytes = int(comm.allreduce(local_map_bytes, op=MPI.MAX))
    owner_bytes = _schedule_bytes(owner_schedule)
    pull_position_bytes = int(
        pull_received_positions.nbytes + pull_send_positions.nbytes
    )
    global_unique_edges = int(comm.allreduce(owned_edge_ids.size, op=MPI.SUM))
    edge_value_bytes = int(unique_edge_ids.size * np.dtype(np.complex128).itemsize)
    chunk_edge_bytes = int(
        LOR_BATCH_CELL_CAP * edge_count * np.dtype(np.complex128).itemsize
    )
    chunk_edge_index_bytes = int(
        LOR_BATCH_CELL_CAP * edge_count * np.dtype(np.int32).itemsize
    )
    chunk_edge_bool_bytes = int(
        LOR_BATCH_CELL_CAP * edge_count * np.dtype(np.bool_).itemsize
    )
    send_value_bytes = int(unique_edge_ids.size * np.dtype(np.complex128).itemsize)
    received_value_bytes = int(owner_received_ids.size * np.dtype(np.complex128).itemsize)
    sorted_value_bytes = received_value_bytes
    owned_value_bytes = int(owned_edge_ids.size * np.dtype(np.complex128).itemsize)
    transfer_batch_value_bytes = int(
        LOR_BATCH_CELL_CAP * edge_count * np.dtype(np.complex128).itemsize
    )
    transfer_axis_temporary_bytes = int(
        LOR_BATCH_CELL_CAP
        * (edge_count // 3)
        * np.dtype(np.complex128).itemsize
    )
    transfer_batch_scratch_bytes = int(
        2 * transfer_batch_value_bytes + transfer_axis_temporary_bytes
    )
    route_scratch_bytes = int(
        chunk_edge_bytes
        + chunk_edge_index_bytes
        + chunk_edge_bool_bytes
        + edge_value_bytes
        + unique_edge_ids.size * np.dtype(np.bool_).itemsize
        + send_value_bytes
        + received_value_bytes
        + sorted_value_bytes
        + owned_value_bytes
    )
    pull_reply_bytes = int(pull_received_ids.size * np.dtype(np.complex128).itemsize)
    pull_received_value_bytes = int(unique_edge_ids.size * np.dtype(np.complex128).itemsize)
    pull_output_bytes = pull_received_value_bytes
    scratch_bytes = max(
        route_scratch_bytes,
        int(pull_reply_bytes + pull_received_value_bytes + pull_output_bytes),
        transfer_batch_scratch_bytes,
    )
    projected_map_bytes = int(
        P6_H10_REFERENCE_CELL_COUNT * P6_H10_REFERENCE_CELL_EDGE_COUNT * 6
    )
    projected_route_scratch_bytes = int(
        LOR_BATCH_CELL_CAP * P6_H10_REFERENCE_CELL_EDGE_COUNT * 16
        + LOR_BATCH_CELL_CAP * P6_H10_REFERENCE_CELL_EDGE_COUNT * 4
        + LOR_BATCH_CELL_CAP * P6_H10_REFERENCE_CELL_EDGE_COUNT
        + P6_H10_REFERENCE_UNIQUE_EDGE_COUNT * 16
        + P6_H10_REFERENCE_UNIQUE_EDGE_COUNT * 16
        + P6_H10_REFERENCE_UNIQUE_EDGE_COUNT * 16 * 2
        + P6_H10_REFERENCE_UNIQUE_EDGE_COUNT * 16
    )
    projected_pull_scratch_bytes = int(
        P6_H10_REFERENCE_UNIQUE_EDGE_COUNT * 16 * 3
    )
    projected_transfer_batch_value_bytes = int(
        LOR_BATCH_CELL_CAP
        * P6_H10_REFERENCE_CELL_EDGE_COUNT
        * np.dtype(np.complex128).itemsize
    )
    projected_transfer_axis_temporary_bytes = int(
        LOR_BATCH_CELL_CAP
        * (P6_H10_REFERENCE_CELL_EDGE_COUNT // 3)
        * np.dtype(np.complex128).itemsize
    )
    projected_transfer_batch_scratch_bytes = int(
        2 * projected_transfer_batch_value_bytes
        + projected_transfer_axis_temporary_bytes
    )
    projected_scratch_bytes = max(
        projected_route_scratch_bytes,
        projected_pull_scratch_bytes,
        projected_transfer_batch_scratch_bytes,
    )
    audit = {
        "schema": "task038.lor-packed-owner-topology.v1",
        "owner_local_maps": True,
        "numeric_allgather": False,
        "metadata_allgather": True,
        "numeric_owner_route": "typed_uint32_complex128_alltoallv",
        "global_transfer_matrix": False,
        "retained_python_edge_objects": 0,
        "production_apply_streaming": True,
        "per_apply_full_cell_value_array": False,
        "per_apply_global_sort": False,
        "degree": degree,
        "local_cell_count": cell_count,
        "global_cell_count": int(comm.allreduce(cell_count, op=MPI.SUM)),
        "edge_count": edge_count,
        "local_unique_edge_count": int(unique_edge_ids.size),
        "owned_unique_edge_count": int(owned_edge_ids.size),
        "global_unique_edge_count": global_unique_edges,
        "local_map_bytes": local_map_bytes,
        "global_map_bytes": global_map_bytes,
        "max_rank_map_bytes": max_map_bytes,
        "owner_schedule_retained_bytes": owner_bytes,
        "pull_schedule_bytes": pull_position_bytes,
        "pull_incremental_positions_bytes": pull_position_bytes,
        "shared_schedule": True,
        "phase_code_counts": [int(value) for value in phase_counts],
        "single_endpoint_normal_edge_count": single_endpoint_count,
        "periodic_phase_rule": "both_endpoints_on_upper_slave_plane",
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "mpc_slave_master": "finalized_mpc_homogenize_backsubstitution",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True,
        "packed_coordinate_bits": PACKED_COORDINATE_BITS,
        "apply_chunk_cell_cap": LOR_BATCH_CELL_CAP,
        "unique_edge_value_bytes": edge_value_bytes,
        "apply_scratch_upper_bound_bytes": scratch_bytes,
        "apply_send_value_bytes": send_value_bytes,
        "apply_received_value_bytes": received_value_bytes,
        "apply_sorted_value_bytes": sorted_value_bytes,
        "apply_owned_value_bytes": owned_value_bytes,
        "apply_pull_reply_bytes": pull_reply_bytes,
        "apply_pull_received_value_bytes": pull_received_value_bytes,
        "apply_pull_output_bytes": pull_output_bytes,
        "transfer_batch_cell_cap": LOR_BATCH_CELL_CAP,
        "transfer_batch_input_bytes": transfer_batch_value_bytes,
        "transfer_batch_output_bytes": transfer_batch_value_bytes,
        "transfer_axis_temporary_bytes": transfer_axis_temporary_bytes,
        "transfer_batch_scratch_bytes": transfer_batch_scratch_bytes,
        "apply_scratch_provenance": "derived_chunk_plus_unique_send_receive_sorted_owned_pull_and_transfer_batch_vectors",
        "projected_p6_h10_packed_map_bytes": projected_map_bytes,
        "projected_p6_h10_unique_edge_count": P6_H10_REFERENCE_UNIQUE_EDGE_COUNT,
        "projected_p6_h10_apply_scratch_bytes": projected_scratch_bytes,
        "projected_p6_h10_transfer_batch_input_bytes": projected_transfer_batch_value_bytes,
        "projected_p6_h10_transfer_batch_output_bytes": projected_transfer_batch_value_bytes,
        "projected_p6_h10_transfer_axis_temporary_bytes": projected_transfer_axis_temporary_bytes,
        "projected_p6_h10_transfer_batch_scratch_bytes": projected_transfer_batch_scratch_bytes,
        "projected_p6_h10_map_provenance": "derived_54432_times_882_times_6_uint32_int8_uint8",
    }
    return CanonicalLORSubedgeTopology(
        degree=degree,
        edge_count=edge_count,
        cell_edge_ids=cell_edge_ids,
        cell_orientation=cell_orientation,
        cell_phase_codes=cell_phase_codes,
        phase_values=phase_values,
        unique_edge_ids=unique_edge_ids,
        owned_edge_ids=owned_edge_ids,
        owner_schedule=owner_schedule,
        owner_received_sort_order=_readonly(owner_received_sort_order),
        owner_received_sorted_ids=_readonly(owner_received_sorted_ids),
        owner_received_group_starts=_readonly(owner_received_group_starts),
        pull_schedule=pull_schedule,
        pull_received_positions=_readonly(pull_received_positions),
        pull_send_positions=pull_send_positions,
        comm=comm,
        audit=audit,
    )
