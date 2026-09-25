"""Distributed p4 cell-condensation and complete inverse recovery.

The assembly-time module owns the FE geometry, MPC map, local cell Schur
data, and PETSc matrix.  This module supplies the p4 port blocks and the
single inverse operation around that already-built object.  In particular,
the input is the MPC-assembled storage dual: this adapter never applies a
second ``C^H``.

``assemble_condensed_ports`` is the unchanged donor carrier bridge and keeps
its explicit MPI1 qualification.  ``assemble_port_condensed_terms`` and
``P4CellCondensedInverse`` are the distributed path: the former accepts the
already-owned local ``B_i/D_i/B_t/D_t/H`` terms and the latter exchanges only
the active trace entries needed by locally owned cells.  It never gathers a
full FE vector or a full trace field.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.linalg import lu_solve

from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
)


def _matrix(value: Any, name: str) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite two-dimensional complex128 array")
    return array


def _canonical_csr(matrix: Any) -> sparse.csr_matrix:
    csr = sparse.csr_matrix(matrix, dtype=np.complex128, copy=True)
    csr.sum_duplicates()
    csr.sort_indices()
    return csr


def csr_content_identity(matrix: Any) -> dict[str, Any]:
    """Hash canonical CSR structure and values without a dense gather."""

    csr = _canonical_csr(matrix)
    indptr = np.asarray(csr.indptr, dtype="<i8")
    indices = np.asarray(csr.indices, dtype="<i8")
    data = np.asarray(csr.data, dtype="<c16")
    mapping = hashlib.sha256(indptr.tobytes() + indices.tobytes()).hexdigest()
    values = hashlib.sha256(data.tobytes()).hexdigest()
    digest = hashlib.sha256(
        np.asarray(csr.shape, dtype="<i8").tobytes()
        + indptr.tobytes()
        + indices.tobytes()
        + data.tobytes()
    ).hexdigest()
    return {
        "schema_version": "task041.p4-cell-condensed-inverse.v1",
        "shape": [int(value) for value in csr.shape],
        "dtype": "complex128",
        "index_dtype": "int64-little-endian-canonical",
        "nnz": int(csr.nnz),
        "hash_algorithm": "sha256(shape||indptr||indices||data)",
        "mapping_sha256": mapping,
        "values_sha256": values,
        "csr_sha256": digest,
        "dense_gather": False,
    }


def petsc_csr_content_identity(matrix: PETSc.Mat) -> dict[str, Any]:
    """Stream owned PETSc rows and gather only small rank digests."""

    comm = matrix.getComm().tompi4py()
    local_mapping = hashlib.sha256()
    local_values = hashlib.sha256()
    header = (
        "task041.p4-petsc-csr-stream.v1\0"
        f"shape={tuple(map(int, matrix.getSize()))}\0dtype=<c16\0"
    ).encode()
    local_mapping.update(header)
    local_values.update(header)
    local_nnz = 0
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns, values = matrix.getRow(row)
        columns = np.asarray(columns, dtype="<i8")
        values = np.asarray(values, dtype="<c16")
        if len(columns):
            order = np.argsort(columns, kind="mergesort")
            columns = columns[order]
            values = values[order]
        row_header = np.asarray([row, len(columns)], dtype="<i8").tobytes()
        local_mapping.update(row_header + columns.tobytes())
        local_values.update(row_header + values.tobytes())
        local_nnz += len(columns)
    packet = ((start, end), local_mapping.hexdigest(), local_values.hexdigest(), local_nnz)
    packets = comm.allgather(packet)
    mapping = hashlib.sha256()
    values = hashlib.sha256()
    digest = hashlib.sha256()
    for rank, packet in enumerate(packets):
        ownership, mapping_sha, values_sha, nnz = packet
        prefix = repr((rank, tuple(map(int, ownership)), int(nnz))).encode()
        mapping.update(prefix + bytes.fromhex(mapping_sha))
        values.update(prefix + bytes.fromhex(values_sha))
        digest.update(prefix + bytes.fromhex(mapping_sha) + bytes.fromhex(values_sha))
    return {
        "schema_version": "task041.p4-petsc-csr-stream.v1",
        "shape": [int(value) for value in matrix.getSize()],
        "dtype": "complex128",
        "index_dtype": "int64-little-endian-canonical",
        "nnz": int(sum(packet[3] for packet in packets)),
        "hash_algorithm": "sha256(header||rank||ownership||row-stream-digests)",
        "mapping_sha256": mapping.hexdigest(),
        "values_sha256": values.hexdigest(),
        "csr_sha256": digest.hexdigest(),
        "dense_gather": False,
    }


@dataclass(frozen=True)
class CellPortTerms:
    """Non-Hermitian local port blocks for one locally owned cell."""

    Bi: np.ndarray
    Di: np.ndarray
    port_indices: np.ndarray
    Bt: np.ndarray | None = None
    Dt: np.ndarray | None = None
    H: np.ndarray | None = None


def _validate_term(term: CellPortTerms, cell: Any, appended_rows: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bi = _matrix(term.Bi, "CellPortTerms.Bi")
    di = _matrix(term.Di, "CellPortTerms.Di")
    ports = np.asarray(term.port_indices, dtype=PETSc.IntType)
    ni = len(cell.interior_original_dofs)
    if (
        bi.shape[0] != ni
        or di.shape[1] != ni
        or bi.shape[1] != di.shape[0]
        or ports.ndim != 1
        or len(ports) != bi.shape[1]
        or len(np.unique(ports)) != len(ports)
        or np.any(ports < 0)
        or np.any(ports >= appended_rows)
    ):
        raise ValueError("local B_i/D_i/port dimensions do not match the cell")
    return bi, di, ports


def _port_condensed_blocks(
    *,
    trace_from_interior: np.ndarray,
    interior_from_trace: np.ndarray,
    interior_from_port: np.ndarray,
    term: CellPortTerms,
    cell: Any,
    appended_rows: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Form exact non-Hermitian port blocks for one owned cell.

    interior_from_trace is R = -A_ii^{-1} A_it.  With the repository
    block convention [A, B; -D, H], the lower-left contribution is
    Dhat = Dt + Di @ R and the matrix insertion is -Dhat.
    """

    bi, di, ports = _validate_term(term, cell, appended_rows)
    trace_from_interior = _matrix(
        trace_from_interior,
        "trace_from_interior",
    )
    interior_from_trace = _matrix(
        interior_from_trace,
        "interior_from_trace",
    )
    interior_from_port = _matrix(
        interior_from_port,
        "interior_from_port",
    )
    expected_interior = len(cell.interior_original_dofs)
    expected_trace = len(cell.trace_original_dofs)
    if trace_from_interior.shape != (expected_trace, expected_interior):
        raise ValueError("trace_from_interior has the wrong shape")
    if interior_from_trace.shape != (expected_interior, expected_trace):
        raise ValueError("interior_from_trace has the wrong shape")
    if interior_from_port.shape != (expected_interior, len(ports)):
        raise ValueError("interior_from_port has the wrong shape")

    b_hat = trace_from_interior @ bi
    if term.Bt is not None:
        bt = _matrix(term.Bt, "CellPortTerms.Bt")
        if bt.shape != (expected_trace, len(ports)):
            raise ValueError("CellPortTerms.Bt has the wrong shape")
        b_hat = bt + b_hat

    d_hat = di @ interior_from_trace
    if term.Dt is not None:
        dt = _matrix(term.Dt, "CellPortTerms.Dt")
        if dt.shape != (len(ports), expected_trace):
            raise ValueError("CellPortTerms.Dt has the wrong shape")
        d_hat = dt + d_hat

    h_hat = di @ interior_from_port
    if term.H is not None:
        h_local = _matrix(term.H, "CellPortTerms.H")
        if h_local.shape != (len(ports), len(ports)):
            raise ValueError("CellPortTerms.H has the wrong shape")
        h_hat = h_local + h_hat
    return (
        np.ascontiguousarray(b_hat),
        np.ascontiguousarray(d_hat),
        np.ascontiguousarray(h_hat),
    )


def assemble_port_condensed_terms(
    condensed: AssemblyTimeCondensedSystem,
    port_terms: Mapping[int, CellPortTerms],
) -> dict[str, Any]:
    """Insert the complete non-Hermitian ``B/D/H`` Schur blocks.

    ``condensed`` already contains the trace Schur block and its exact local
    recovery factors.  The formulas retain both directions of the port
    coupling; no Hermitian assumption and no additional ``C^H`` is made.
    """

    if condensed.matrix is None:
        raise ValueError("p4 matrix is not materialized")
    if condensed.appended_rows <= 0:
        raise ValueError("p4 port terms require appended rows")
    comm = condensed.comm
    inserted = 0
    local_error = None
    try:
        for index, cell in enumerate(condensed.cell_recovery_maps):
            term = port_terms.get(index)
            if term is None:
                continue
            bi, _di, ports = _validate_term(term, cell, condensed.appended_rows)
            ids, expansion, _identity = _cell_trace_expansion(
                np.asarray(cell.trace_original_dofs, dtype=PETSc.IntType),
                condensed.trace_constraints,
            )
            lu = condensed.interior_lu_by_class[cell.class_key]
            # The cached recovery matrix is R=-A_ii^{-1}A_it.  Reconstructing
            # A_it is not needed; the pure helper owns the sign convention.
            trace_from_interior = condensed.trace_from_interior_rhs_by_class[
                cell.class_key
            ]
            xit = condensed.interior_from_trace_by_class[cell.class_key]
            xib = np.ascontiguousarray(lu_solve(lu, bi))
            b_hat, d_hat, h_hat = _port_condensed_blocks(
                trace_from_interior=trace_from_interior,
                interior_from_trace=xit,
                interior_from_port=xib,
                term=term,
                cell=cell,
                appended_rows=condensed.appended_rows,
            )
            global_ports = condensed.active_rows + ports
            condensed.matrix.setValues(
                ids,
                global_ports,
                np.ascontiguousarray(expansion.conj().T @ b_hat),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            condensed.matrix.setValues(
                global_ports,
                ids,
                np.ascontiguousarray(-d_hat @ expansion),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            condensed.matrix.setValues(
                global_ports,
                global_ports,
                np.ascontiguousarray(h_hat),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            inserted += 1
    except Exception as error:  # noqa: BLE001
        local_error = f"{type(error).__name__}: {error}"
    _collective_errors(comm, local_error, "p4 port-term assembly failed")
    condensed.matrix.assemble()
    return {
        "schema_version": "task041.p4-port-condensed-terms.v1",
        "cells_with_port_terms": inserted,
        "nonhermitian_blocks": ["Bi", "Di", "Bt", "Dt", "H"],
        "input_is_mpc_dual_storage": True,
        "global_full_p4_matrix_allocated": False,
        "matrix_identity": petsc_csr_content_identity(condensed.matrix),
    }


def assemble_condensed_ports(condensed: AssemblyTimeCondensedSystem, carrier: Any) -> dict[int, CellPortTerms]:
    """Use the donor carrier bridge, retaining its explicit MPI1 guard.

    A distributed caller must first create ``CellPortTerms`` through its
    owner-local carrier exchange and then call :func:`assemble_port_condensed_terms`.
    Removing this guard would falsely promote the donor's MPI1 carrier path.
    """

    entries = getattr(carrier, "entries", None)
    if entries is None and getattr(carrier, "carrier", None) is not None:
        entries = getattr(carrier.carrier, "entries", None)
    if entries is None:
        raise TypeError("carrier must expose an entries sequence")
    entries = tuple(entries)
    if len(entries) != condensed.appended_rows:
        raise ValueError("carrier entry count differs from appended port rows")
    if condensed.comm.Get_size() != 1:
        raise NotImplementedError(
            "donor carrier assembly is qualified for MPI1 only; use owner-local terms"
        )
    active_map = {
        int(original): int(active)
        for original, active in condensed.trace_constraints.original_to_active.items()
    }
    interior_locations: dict[int, tuple[int, int]] = {}
    for cell_index, cell in enumerate(condensed.cell_recovery_maps):
        for local, original in enumerate(cell.interior_original_dofs):
            original = int(original)
            if original in interior_locations:
                raise RuntimeError(f"interior DoF {original} belongs to multiple cells")
            interior_locations[original] = (cell_index, local)
    bi_by_cell: dict[int, dict[int, dict[int, complex]]] = {}
    di_by_cell: dict[int, dict[int, dict[int, complex]]] = {}
    terms: dict[int, CellPortTerms] = {}
    for port, entry in enumerate(entries):
        coupling_rows = np.asarray(entry.coupling_rows, dtype=np.int64)
        coupling_values = np.asarray(entry.coupling_values, dtype=np.complex128)
        projection_rows = np.asarray(entry.projection_rows, dtype=np.int64)
        projection_values = np.asarray(entry.projection_values, dtype=np.complex128)
        if (
            coupling_rows.ndim != 1
            or projection_rows.ndim != 1
            or coupling_rows.shape != coupling_values.shape
            or projection_rows.shape != projection_values.shape
            or not np.isfinite(coupling_values).all()
            or not np.isfinite(projection_values).all()
        ):
            raise ValueError("carrier row/value arrays have different shapes")
        normalization_h = complex(entry.normalization_h)
        if not np.isfinite(normalization_h):
            raise ValueError("carrier normalization_h must be finite")
        condensed.matrix.setValue(
            condensed.active_rows + port,
            condensed.active_rows + port,
            PETSc.ScalarType(normalization_h),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        for rows, values, side in (
            (coupling_rows, coupling_values, "B"),
            (projection_rows, projection_values, "D"),
        ):
            for row, value in zip(rows, values, strict=True):
                location = interior_locations.get(int(row))
                if location is not None:
                    cell_index, local = location
                    target = bi_by_cell if side == "B" else di_by_cell
                    target.setdefault(cell_index, {}).setdefault(port, {})[local] = (
                        target.get(cell_index, {}).get(port, {}).get(local, 0.0)
                        + complex(value)
                    )
                    continue
                active = active_map.get(int(row))
                if active is None:
                    raise ValueError("carrier includes an MPC slave row")
                if side == "B":
                    condensed.matrix.setValue(
                        active,
                        condensed.active_rows + port,
                        PETSc.ScalarType(value),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
                else:
                    condensed.matrix.setValue(
                        condensed.active_rows + port,
                        active,
                        PETSc.ScalarType(-value),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
    for cell_index in sorted(set(bi_by_cell) | set(di_by_cell)):
        cell = condensed.cell_recovery_maps[cell_index]
        bi_ports = set(bi_by_cell.get(cell_index, {}))
        di_ports = set(di_by_cell.get(cell_index, {}))
        ports = np.asarray(sorted(bi_ports | di_ports), dtype=PETSc.IntType)
        bi = np.zeros((len(cell.interior_original_dofs), len(ports)), dtype=np.complex128)
        di = np.zeros((len(ports), len(cell.interior_original_dofs)), dtype=np.complex128)
        for column, port in enumerate(ports):
            for local, value in bi_by_cell.get(cell_index, {}).get(int(port), {}).items():
                bi[local, column] = value
            for local, value in di_by_cell.get(cell_index, {}).get(int(port), {}).items():
                di[column, local] = value
        terms[cell_index] = CellPortTerms(bi, di, ports)
    assemble_port_condensed_terms(condensed, terms)
    for term in terms.values():
        term.Bi.setflags(write=False)
        term.Di.setflags(write=False)
        term.port_indices.setflags(write=False)
    return terms


def _local_rows(vector: PETSc.Vec, rows: np.ndarray, name: str) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.int64)
    start, end = map(int, vector.getOwnershipRange())
    if len(rows) and (int(rows.min()) < start or int(rows.max()) >= end):
        raise ValueError(f"{name} contains a non-owned storage row")
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    return np.array(local[rows - start], dtype=np.complex128, copy=True)


def _write_local_rows(vector: PETSc.Vec, rows: np.ndarray, values: np.ndarray, name: str) -> None:
    rows = np.asarray(rows, dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    start, end = map(int, vector.getOwnershipRange())
    if len(rows) and (int(rows.min()) < start or int(rows.max()) >= end):
        raise ValueError(f"{name} contains a non-owned storage row")
    local = vector.getArray()
    local[rows - start] = values


def _collective_errors(comm, local_error: str | None, context: str) -> None:
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise ValueError(
            f"{context}: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(errors)
                if error is not None
            )
        )


def _exchange_active_values(
    comm,
    owned_values: np.ndarray,
    active_offsets: np.ndarray,
    requested_rows_by_owner: tuple[np.ndarray, ...],
    requested_rows_from_rank: tuple[np.ndarray, ...],
) -> dict[int, complex]:
    """Exchange fresh values over the inverse's fixed owner/request plan."""

    local_start = int(active_offsets[comm.rank])
    local_end = int(active_offsets[comm.rank + 1])
    if len(owned_values) != local_end - local_start:
        local_error = "active solution local ownership does not match condensed metadata"
    else:
        local_error = None
    _collective_errors(comm, local_error, "active-trace request validation failed")
    send_values: list[list[tuple[int, complex]]] = [[] for _rank in range(comm.size)]
    for source, rows in enumerate(requested_rows_from_rank):
        send_values[source] = [
            (int(row), complex(owned_values[int(row) - local_start]))
            for row in rows
        ]
    received_values = comm.alltoall(send_values)
    result: dict[int, complex] = {}
    local_error = None
    for owner, packets in enumerate(received_values):
        expected_rows = requested_rows_by_owner[owner]
        if len(packets) != len(expected_rows):
            local_error = f"owner exchange returned an unexpected row count from rank {owner}"
            break
        for (row, value), expected in zip(packets, expected_rows, strict=True):
            if int(row) != int(expected):
                local_error = f"owner exchange returned an unexpected row from rank {owner}"
                break
            result[int(row)] = complex(value)
        if local_error is not None:
            break
    expected_count = sum(len(rows) for rows in requested_rows_by_owner)
    if local_error is None and len(result) != expected_count:
        local_error = f"owner exchange missed {expected_count - len(result)} requested active rows"
    _collective_errors(comm, local_error, "distributed active-trace exchange failed")
    return result


class P4CellCondensedInverse:
    """One exact p4 factor with distributed local-cell recovery.

    The factor is created by the caller from the assembled trace/port matrix.
    Every rank supplies its owned portion of an MPC-assembled full storage RHS;
    only active entries required by that rank's cells are exchanged after the
    factor solve.  The full FE vector and the full trace vector are never
    gathered.
    """

    def __init__(
        self,
        condensed: AssemblyTimeCondensedSystem,
        factor: Any,
        *,
        port_terms: Mapping[int, CellPortTerms] | None = None,
        owns_condensed: bool = False,
        owns_factor: bool = False,
        retain_through_postprocess_v18: bool = True,
    ) -> None:
        if condensed.matrix is None:
            raise ValueError("p4 inverse requires a materialized condensed matrix")
        self.condensed = condensed
        self.factor = factor
        self.port_terms = dict(port_terms or {})
        self.owns_condensed = bool(owns_condensed)
        self.owns_factor = bool(owns_factor)
        self.retain_through_postprocess_v18 = bool(retain_through_postprocess_v18)
        self.solve_count = 0
        self.destroyed = False
        self.last_port_solution = np.empty(0, dtype=np.complex128)
        self.last_audit: dict[str, Any] = {}
        self.last_timing: dict[str, float | None] = {}
        self.matrix_identity = petsc_csr_content_identity(condensed.matrix)
        self.active_counts = tuple(
            int(value) for value in condensed.comm.allgather(condensed.owned_active_rows)
        )
        self._active_offsets = np.concatenate(
            (
                np.asarray([0], dtype=np.int64),
                np.cumsum(np.asarray(self.active_counts, dtype=np.int64)),
            )
        )
        owned_active_original = {
            int(active)
            for active in condensed.trace_constraints.owned_active_original_dofs
        }
        self._slave_original = np.asarray(
            [
                int(value)
                for value in condensed.owned_trace_original_dofs
                if int(value) not in owned_active_original
            ],
            dtype=PETSc.IntType,
        )
        self._initialize_active_exchange_plan()
        self._xiB_by_cell: dict[int, np.ndarray] = {}
        for index, cell in enumerate(condensed.cell_recovery_maps):
            self._port_data(index, cell)

    def _initialize_active_exchange_plan(self) -> None:
        """Cache immutable owned indices and trace-row owner routes for this factor."""

        system = self.condensed
        comm = system.comm
        local_error = None
        owned_indices = np.empty(0, dtype=np.int64)
        requests_by_owner: tuple[np.ndarray, ...] = ()
        try:
            if len(self.active_counts) != comm.size:
                raise ValueError("active row counts do not match communicator size")
            active_original = np.asarray(
                system.trace_constraints.owned_active_original_dofs,
                dtype=PETSc.IntType,
            )
            local_start = int(self._active_offsets[comm.rank])
            local_end = int(self._active_offsets[comm.rank + 1])
            if len(active_original) != int(system.owned_active_rows):
                raise ValueError("owned active IDs do not match local condensed rows")
            if local_end - local_start != int(system.owned_active_rows):
                raise ValueError("active ownership counts do not match local condensed rows")
            active_ids = np.asarray(
                [
                    system.trace_constraints.original_to_active[int(original)]
                    for original in active_original
                ],
                dtype=np.int64,
            )
            owned_indices = active_ids - local_start
            if len(owned_indices) and (
                int(owned_indices.min()) < 0
                or int(owned_indices.max()) >= int(system.owned_active_rows)
            ):
                raise ValueError("owned active solution mapping is not local")

            requested = np.fromiter(
                (
                    int(active)
                    for cell in system.cell_recovery_maps
                    for original in cell.trace_original_dofs
                    for active in system.trace_constraints.expansion_by_original[
                        int(original)
                    ][0]
                ),
                dtype=np.int64,
            )
            requested = np.unique(requested)
            if len(requested) and (
                int(requested.min()) < 0
                or int(requested.max()) >= int(self._active_offsets[-1])
            ):
                raise ValueError("requested active trace row is out of range")
            owners = np.searchsorted(
                self._active_offsets[1:],
                requested,
                side="right",
            )
            requests_by_owner = tuple(
                np.asarray(requested[owners == owner], dtype=np.int64)
                for owner in range(comm.size)
            )
        except Exception as error:  # noqa: BLE001
            local_error = f"{type(error).__name__}: {error}"
        _collective_errors(
            comm,
            local_error,
            "active-trace communication plan construction failed",
        )

        received_requests = comm.alltoall(
            [rows.tolist() for rows in requests_by_owner]
        )
        local_start = int(self._active_offsets[comm.rank])
        local_end = int(self._active_offsets[comm.rank + 1])
        local_error = None
        requests_from_rank: tuple[np.ndarray, ...] = ()
        try:
            incoming = []
            for rows in received_requests:
                requested_rows = np.asarray(rows, dtype=np.int64)
                if len(requested_rows) and (
                    int(requested_rows.min()) < local_start
                    or int(requested_rows.max()) >= local_end
                ):
                    raise ValueError("owner request was routed outside local active rows")
                requested_rows.setflags(write=False)
                incoming.append(requested_rows)
            requests_from_rank = tuple(incoming)
        except Exception as error:  # noqa: BLE001
            local_error = f"{type(error).__name__}: {error}"
        _collective_errors(
            comm,
            local_error,
            "active-trace communication plan ownership failed",
        )

        self._active_offsets.setflags(write=False)
        owned_indices.setflags(write=False)
        for rows in requests_by_owner:
            rows.setflags(write=False)
        self._owned_active_local_indices = owned_indices
        self._active_request_rows_by_owner = requests_by_owner
        self._active_request_rows_from_rank = requests_from_rank
        # Exact NumPy integer-buffer bytes; Python tuple/object headers are excluded.
        self.active_exchange_plan_nbytes = sum(
            array.nbytes
            for array in (
                self._active_offsets,
                self._owned_active_local_indices,
                *self._active_request_rows_by_owner,
                *self._active_request_rows_from_rank,
            )
        )

    def _port_data(self, index: int, cell: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        term = self.port_terms.get(int(index))
        if term is None:
            ni = len(cell.interior_original_dofs)
            return (
                np.zeros((ni, 0), dtype=np.complex128),
                np.zeros((0, ni), dtype=np.complex128),
                np.empty(0, dtype=PETSc.IntType),
            )
        bi, di, ports = _validate_term(term, cell, self.condensed.appended_rows)
        if index not in self._xiB_by_cell:
            self._xiB_by_cell[index] = np.ascontiguousarray(
                lu_solve(self.condensed.interior_lu_by_class[cell.class_key], bi)
            )
        return bi, di, ports

    def _validate_rhs(self, rhs: PETSc.Vec) -> None:
        local_error = None
        try:
            if int(rhs.getSize()) != int(self.condensed.full_rows):
                raise ValueError("native p4 RHS has the wrong storage size")
            values = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            if not np.isfinite(values).all():
                raise ValueError("native p4 RHS contains non-finite values")
            _local_rows(rhs, self.condensed.trace_constraints.owned_active_original_dofs, "active RHS")
            _local_rows(rhs, self._slave_original, "slave RHS")
            for cell in self.condensed.cell_recovery_maps:
                _local_rows(rhs, np.asarray(cell.interior_original_dofs), "interior RHS")
        except Exception as error:  # noqa: BLE001
            local_error = f"{type(error).__name__}: {error}"
        _collective_errors(self.condensed.comm, local_error, "p4 RHS validation failed")

    def _prepare_port_rhs(self, port_rhs: np.ndarray | None) -> np.ndarray:
        appended = int(self.condensed.appended_rows)
        if port_rhs is None:
            values = np.zeros(appended, dtype=np.complex128)
        else:
            try:
                values = np.asarray(port_rhs, dtype=np.complex128)
            except Exception as error:  # noqa: BLE001
                values = np.zeros(appended, dtype=np.complex128)
                local_error = (
                    f"{type(error).__name__}: cannot convert port RHS"
                )
            else:
                local_error = None
        if port_rhs is None:
            local_error = None
        if values.shape != (appended,):
            local_error = (
                f"port RHS must have shape {(appended,)}, got {values.shape}"
            )
        elif not np.isfinite(values).all():
            local_error = "port RHS contains non-finite values"
        payloads = self.condensed.comm.allgather(values.tobytes())
        if any(payload != payloads[0] for payload in payloads[1:]):
            local_error = "replicated port RHS differs between ranks"
        _collective_errors(
            self.condensed.comm,
            local_error,
            "p4 port RHS validation failed",
        )
        return np.array(values, dtype=np.complex128, copy=True)

    def _reduce_storage_rhs(
        self,
        rhs: PETSc.Vec,
        port_rhs: np.ndarray,
    ) -> PETSc.Vec:
        system = self.condensed
        active_original = np.asarray(
            system.trace_constraints.owned_active_original_dofs,
            dtype=PETSc.IntType,
        )
        active_values = _local_rows(rhs, active_original, "active RHS")
        slave_values = _local_rows(rhs, self._slave_original, "slave RHS")
        local_error = None
        if len(slave_values) and np.any(slave_values != 0.0):
            local_error = "MPC-assembled p4 RHS has nonzero slave storage entries"
        _collective_errors(
            system.comm,
            local_error,
            "p4 slave RHS validation failed",
        )
        local_appended = int(system.owned_appended_rows)
        local_error = None
        if local_appended not in {0, len(port_rhs)}:
            local_error = (
                "owned appended-row count does not match the global port RHS"
            )
        _collective_errors(
            system.comm,
            local_error,
            "p4 port RHS ownership validation failed",
        )
        reduced = system.create_augmented_vector()
        if len(active_original):
            active_local = np.zeros(
                int(system.owned_active_rows),
                dtype=np.complex128,
            )
            active_local[self._owned_active_local_indices] = active_values
            reduced.getArray()[: int(system.owned_active_rows)] = active_local
        if local_appended:
            reduced.getArray()[
                int(system.owned_active_rows) :
                int(system.owned_active_rows) + local_appended
            ] = port_rhs
        local_error = None
        try:
            for index, cell in enumerate(system.cell_recovery_maps):
                rows = np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType)
                gi = _local_rows(rhs, rows, "interior RHS")
                if not np.any(gi):
                    continue
                xig = lu_solve(system.interior_lu_by_class[cell.class_key], gi)
                correction = system.trace_from_interior_rhs_by_class[cell.class_key] @ gi
                for original, value in zip(cell.trace_original_dofs, correction, strict=True):
                    ids, coefficients = system.trace_constraints.expansion_by_original[int(original)]
                    reduced.setValues(
                        ids,
                        np.asarray(np.conj(coefficients) * value, dtype=PETSc.ScalarType),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
                _bi, di, ports = self._port_data(index, cell)
                if len(ports):
                    reduced.setValues(
                        system.active_rows + ports,
                        np.asarray(di @ xig, dtype=PETSc.ScalarType),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
        except Exception as error:  # noqa: BLE001
            local_error = f"{type(error).__name__}: {error}"
        try:
            _collective_errors(system.comm, local_error, "p4 storage RHS reduction failed")
        except BaseException:
            reduced.destroy()
            raise
        reduced.assemble()
        return reduced

    def _solve_once(self, rhs: PETSc.Vec) -> PETSc.Vec:
        solution = rhs.duplicate()
        solution.set(PETSc.ScalarType(0.0))
        solve = getattr(self.factor, "solve_repeated", None)
        if not callable(solve):
            solve = getattr(self.factor, "solve", None)
        if not callable(solve):
            solution.destroy()
            raise TypeError("factor has no solve_repeated/solve API")
        try:
            started = perf_counter()
            try:
                solve(rhs, solution)
            finally:
                self.last_timing["factor_backsolve_seconds"] = float(
                    perf_counter() - started
                )
        except BaseException:
            solution.destroy()
            raise
        self.solve_count += 1
        return solution

    def _active_solution_map(self, solution: PETSc.Vec) -> dict[int, complex]:
        local_size = int(self.condensed.owned_active_rows)
        values = np.asarray(solution.getArray(readonly=True), dtype=np.complex128)
        if len(values) < local_size:
            raise ValueError("factor solution has fewer entries than owned active rows")
        return _exchange_active_values(
            self.condensed.comm,
            values[:local_size],
            self._active_offsets,
            self._active_request_rows_by_owner,
            self._active_request_rows_from_rank,
        )

    def _owned_active_solution(
        self,
        solution: PETSc.Vec,
    ) -> np.ndarray:
        """Read owned solution entries using the explicit original-to-active map."""

        local_size = int(self.condensed.owned_active_rows)
        values = np.asarray(solution.getArray(readonly=True), dtype=np.complex128)
        if len(values) < local_size:
            raise ValueError("factor solution has fewer entries than owned active rows")
        return np.array(
            values[self._owned_active_local_indices],
            dtype=np.complex128,
            copy=True,
        )

    def _port_solution(self, solution: PETSc.Vec) -> np.ndarray:
        appended = int(self.condensed.appended_rows)
        if appended == 0:
            return np.empty(0, dtype=np.complex128)
        local_error = None
        local_port = None
        try:
            values = np.asarray(solution.getArray(readonly=True), dtype=np.complex128)
        except Exception as error:  # noqa: BLE001
            local_error = f"{type(error).__name__}: cannot read port solution"
        else:
            if self.condensed.comm.rank == self.condensed.comm.size - 1:
                start = int(self.condensed.owned_active_rows)
                local_port = np.array(values[start : start + appended], copy=True)
                if len(local_port) != appended:
                    local_error = "last rank does not own all appended p4 rows"
        _collective_errors(
            self.condensed.comm,
            local_error,
            "port solution ownership validation failed",
        )
        if self.condensed.comm.rank == self.condensed.comm.size - 1:
            assert local_port is not None
        result = self.condensed.comm.bcast(local_port, root=self.condensed.comm.size - 1)
        return np.asarray(result, dtype=np.complex128)

    def apply(
        self,
        rhs: PETSc.Vec,
        *,
        port_rhs: np.ndarray | None = None,
    ) -> PETSc.Vec:
        """Apply the complete inverse to FE storage and an optional port RHS.

        port_rhs is the global appended-port RHS in condensed port order.
        The caller supplies the same small vector on each rank; it is written
        only into the rank that owns the appended rows.
        """

        started = perf_counter()
        self.last_timing = {
            "storage_rhs_reduction_seconds": None,
            "factor_backsolve_seconds": None,
            "solution_recovery_seconds": None,
            "inner_apply_seconds": None,
        }
        audit: dict[str, Any] = {
            "schema_version": "task041.p4-cell-condensed-inverse.v1",
            "input_is_mpc_dual_storage": True,
            "duplicate_C_H_applied": False,
            "distributed_recovery": bool(self.condensed.comm.size > 1),
            "factor_solve_call_delta": 0,
            "input_finite": None,
            "solution_finite": None,
            "output_finite": None,
        }
        reduced_rhs = None
        solution = None
        result = None
        recovery_started = None
        try:
            if self.destroyed:
                raise RuntimeError("p4 cell-condensed inverse has been destroyed")
            self._validate_rhs(rhs)
            port_rhs_values = self._prepare_port_rhs(port_rhs)
            audit["input_finite"] = True
            port_rhs_nonzero = bool(
                self.condensed.comm.allreduce(
                    bool(np.any(port_rhs_values != 0.0)),
                    op=MPI.LOR,
                )
            )
            if rhs.norm() == 0.0 and not port_rhs_nonzero:
                result = rhs.duplicate()
                result.set(PETSc.ScalarType(0.0))
                result.assemble()
                self.last_port_solution = np.zeros(self.condensed.appended_rows, dtype=np.complex128)
                self.last_timing["storage_rhs_reduction_seconds"] = 0.0
                self.last_timing["factor_backsolve_seconds"] = 0.0
                self.last_timing["solution_recovery_seconds"] = 0.0
                audit.update(
                    {
                        "status": "ZERO_RHS_DIRECT_ZERO",
                        "slave_zero": True,
                        "port_rhs_zero": True,
                        "solution_finite": True,
                        "output_finite": True,
                        "factor_solve_count": int(self.solve_count),
                    }
                )
                return result
            reduction_started = perf_counter()
            try:
                reduced_rhs = self._reduce_storage_rhs(rhs, port_rhs_values)
            finally:
                self.last_timing["storage_rhs_reduction_seconds"] = float(
                    perf_counter() - reduction_started
                )
            reduced_values = np.asarray(reduced_rhs.getArray(readonly=True), dtype=np.complex128)
            local_reduced_finite = bool(np.isfinite(reduced_values).all())
            reduced_finite = bool(
                self.condensed.comm.allreduce(local_reduced_finite, op=MPI.LAND)
            )
            if not reduced_finite:
                raise FloatingPointError("reduced p4 RHS contains non-finite values")
            solution = self._solve_once(reduced_rhs)
            local_solution = np.asarray(solution.getArray(readonly=True), dtype=np.complex128)
            solution_finite = bool(
                self.condensed.comm.allreduce(
                    bool(np.isfinite(local_solution).all()), op=MPI.LAND
                )
            )
            audit["solution_finite"] = solution_finite
            if not solution_finite:
                raise FloatingPointError("condensed factor returned non-finite values")
            recovery_started = perf_counter()
            active_values = self._active_solution_map(solution)
            port_values = self._port_solution(solution)
            self.last_port_solution = np.array(port_values, copy=True)
            result = rhs.duplicate()
            result.set(PETSc.ScalarType(0.0))
            active_original = np.asarray(
                self.condensed.trace_constraints.owned_active_original_dofs,
                dtype=PETSc.IntType,
            )
            recovered_rows = 0
            local_error = None
            try:
                if len(active_original):
                    _write_local_rows(
                        result,
                        active_original,
                        self._owned_active_solution(solution),
                        "active solution",
                    )
                for index, cell in enumerate(self.condensed.cell_recovery_maps):
                    local_trace = np.empty(len(cell.trace_original_dofs), dtype=np.complex128)
                    for row, original in enumerate(cell.trace_original_dofs):
                        ids, coefficients = self.condensed.trace_constraints.expansion_by_original[int(original)]
                        local_trace[row] = sum(
                            coefficient * active_values[int(active)]
                            for active, coefficient in zip(ids, coefficients, strict=True)
                        )
                    rows = np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType)
                    gi = _local_rows(rhs, rows, "interior RHS")
                    xig = lu_solve(
                        self.condensed.interior_lu_by_class[cell.class_key], gi
                    )
                    values = (
                        self.condensed.interior_from_trace_by_class[cell.class_key]
                        @ local_trace
                        + xig
                    )
                    _bi, _di, ports = self._port_data(index, cell)
                    if len(ports):
                        values = values - self._xiB_by_cell[index] @ port_values[ports]
                    if not np.isfinite(values).all():
                        raise FloatingPointError("local p4 interior recovery is non-finite")
                    _write_local_rows(result, rows, values, "interior solution")
                    recovered_rows += len(rows)
            except Exception as error:  # noqa: BLE001
                local_error = f"{type(error).__name__}: {error}"
            try:
                _collective_errors(
                    self.condensed.comm,
                    local_error,
                    "p4 local recovery failed",
                )
            except BaseException:
                result.destroy()
                result = None
                raise
            result.assemble()
            output_finite = bool(
                self.condensed.comm.allreduce(
                    bool(np.isfinite(np.asarray(result.getArray(readonly=True))).all()),
                    op=MPI.LAND,
                )
            )
            audit["output_finite"] = output_finite
            if not output_finite:
                raise FloatingPointError("p4 recovery produced non-finite output")
            audit.update(
                {
                    "status": "SOLVE_COMPLETED",
                    "factor_solve_call_delta": 1,
                    "factor_solve_count": int(self.solve_count),
                    "recovered_interior_rows": int(recovered_rows),
                    "slave_zero_policy": "zero_initialize_and_no_backsubstitution",
                    "matrix_identity": self.matrix_identity,
                }
            )
            return result
        except BaseException as exc:
            audit.update(
                {
                    "status": "SOLVE_FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "factor_solve_count": int(self.solve_count),
                }
            )
            if result is not None:
                result.destroy()
            raise
        finally:
            if recovery_started is not None:
                self.last_timing["solution_recovery_seconds"] = float(
                    perf_counter() - recovery_started
                )
            audit["elapsed_seconds"] = float(perf_counter() - started)
            self.last_audit = dict(audit)
            if solution is not None:
                solution.destroy()
            if reduced_rhs is not None:
                reduced_rhs.destroy()
            self.last_timing["inner_apply_seconds"] = float(
                perf_counter() - started
            )

    def destroy(self) -> None:
        if self.destroyed:
            return
        factor = self.factor
        condensed = self.condensed
        cleanup_error: BaseException | None = None
        self.factor = None
        try:
            if self.owns_factor and factor is not None:
                destroy = getattr(factor, "destroy", None)
                if callable(destroy):
                    destroy()
        except BaseException as error:  # noqa: BLE001 - preserve cleanup failure
            cleanup_error = error
        finally:
            self._xiB_by_cell.clear()
            self._active_offsets = np.empty(0, dtype=np.int64)
            self._owned_active_local_indices = np.empty(0, dtype=np.int64)
            self._active_request_rows_by_owner = ()
            self._active_request_rows_from_rank = ()
            self.active_exchange_plan_nbytes = 0
            if self.owns_condensed and condensed is not None:
                for cache in (
                    condensed.interior_from_trace_by_class,
                    condensed.interior_lu_by_class,
                    condensed.interior_rhs_projection_by_class,
                    condensed.interior_solution_embedding_by_class,
                    condensed.trace_from_interior_rhs_by_class,
                    condensed.interior_residual_projection_by_class,
                ):
                    cache.clear()
                condensed.cell_recovery_maps = ()
                condensed.retained_local_schur_by_class = None
                try:
                    condensed.destroy()
                except BaseException as error:  # noqa: BLE001 - preserve cleanup failure
                    if cleanup_error is None:
                        cleanup_error = error
                self.condensed = None
            self.port_terms.clear()
            self._slave_original = np.empty(0, dtype=PETSc.IntType)
            self.last_port_solution = np.empty(0, dtype=np.complex128)
            self.destroyed = True
        if cleanup_error is not None:
            raise cleanup_error


__all__ = [
    "CellPortTerms",
    "P4CellCondensedInverse",
    "assemble_condensed_ports",
    "assemble_port_condensed_terms",
    "csr_content_identity",
    "petsc_csr_content_identity",
]
