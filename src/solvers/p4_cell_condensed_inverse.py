"""The narrow Review V18 p4 inverse adapter.

The FE assembly and its local LU/cache ownership remain in
``hcurl_assembly_time_condensation``.  This module only supplies the general
port-block formulas, the native CSR identity, and the one-solve adapter that
turns an already MPC-applied p4 storage RHS into a recovered storage vector.
Small dense algebra oracles belong to the U0 tests, not to the production
adapter module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any, Mapping

import numpy as np
from scipy import sparse
from scipy.linalg import lu_solve

from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
)


def _matrix(value: Any, name: str) -> np.ndarray:
    value = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    if value.ndim != 2 or not np.isfinite(value).all():
        raise ValueError(f"{name} must be a finite two-dimensional complex128 array")
    return value

def _canonical_csr(matrix: Any) -> sparse.csr_matrix:
    csr = sparse.csr_matrix(matrix, dtype=np.complex128, copy=True)
    csr.sum_duplicates()
    csr.sort_indices()
    return csr


def csr_content_identity(matrix: Any) -> dict[str, Any]:
    """Hash canonical CSR structure and values, never by dense gathering."""

    csr = _canonical_csr(matrix)
    indptr = np.asarray(csr.indptr, dtype="<i8")
    indices = np.asarray(csr.indices, dtype="<i8")
    data = np.asarray(csr.data, dtype="<c16")
    mapping = hashlib.sha256(indptr.tobytes() + indices.tobytes()).hexdigest()
    values = hashlib.sha256(data.tobytes()).hexdigest()
    digest = hashlib.sha256(np.asarray(csr.shape, dtype="<i8").tobytes() + indptr.tobytes() + indices.tobytes() + data.tobytes()).hexdigest()
    return {
        "schema_version": "task039extra.v18.csr-content-identity.v1",
        "shape": [int(value) for value in csr.shape], "dtype": "complex128",
        "value_endianness": "little", "index_dtype": "int64-little-endian-canonical",
        "nnz": int(csr.nnz), "nnz_semantics": "sum_duplicates_then_sorted_csr_stored_entries",
        "hash_algorithm": "sha256(shape_le_i8||indptr_le_i8||indices_le_i8||data_le_c16)",
        "mapping_sha256": mapping, "values_sha256": values, "csr_sha256": digest,
        "dense_gather": False,
    }


def petsc_csr_content_identity(matrix: PETSc.Mat) -> dict[str, Any]:
    """Stream owned rows through ``getRow`` without a dense or CSR copy."""

    comm = matrix.getComm().tompi4py()
    local_mapping = hashlib.sha256()
    local_values = hashlib.sha256()
    header = (
        "task039extra.v18.petsc-csr-stream.v1\0"
        f"shape={tuple(map(int, matrix.getSize()))}\0dtype=<c16\0indices=<i8\0"
    ).encode()
    local_mapping.update(header)
    local_values.update(header)
    local_nnz = 0
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns, row_values = matrix.getRow(row)
        columns = np.asarray(columns, dtype="<i8")
        row_values = np.asarray(row_values, dtype="<c16")
        if len(columns):
            order = np.argsort(columns, kind="mergesort")
            columns = columns[order]
            row_values = row_values[order]
        row_header = np.asarray([row, len(columns)], dtype="<i8").tobytes()
        local_mapping.update(row_header + columns.tobytes())
        local_values.update(row_header + row_values.tobytes())
        local_nnz += len(columns)
        # petsc4py's getRow returns borrowed NumPy views and this version has
        # no restoreRow method.  Do not call a non-existent compatibility API.
    local = (matrix.getOwnershipRange(), local_mapping.hexdigest(), local_values.hexdigest(), local_nnz)
    packets = comm.allgather(local)
    digest = hashlib.sha256(); mapping = hashlib.sha256(); values = hashlib.sha256()
    for rank, packet in enumerate(packets):
        payload = repr((rank, tuple(map(int, packet[0])), packet[3])).encode()
        mapping.update(payload + bytes.fromhex(packet[1])); values.update(payload + bytes.fromhex(packet[2]))
        digest.update(payload + bytes.fromhex(packet[1]) + bytes.fromhex(packet[2]))
    return {
        "schema_version": "task039extra.v18.petsc-csr-content-identity.v1",
        "shape": [int(value) for value in matrix.getSize()], "dtype": "complex128",
        "value_endianness": "little", "index_dtype": "int64-little-endian-canonical",
        "nnz": int(sum(packet[3] for packet in packets)), "nnz_semantics": "owned-row-getRow-stored-entries",
        "hash_algorithm": "sha256(header||rank||ownership||owned-row-stream-digests)",
        "mapping_sha256": mapping.hexdigest(), "values_sha256": values.hexdigest(),
        "csr_sha256": digest.hexdigest(), "dense_gather": False,
    }


@dataclass(frozen=True)
class CellPortTerms:
    """Optional nonzero local port coupling for one owned cell."""

    Bi: np.ndarray
    Di: np.ndarray
    port_indices: np.ndarray
    Bt: np.ndarray | None = None
    Dt: np.ndarray | None = None
    H: np.ndarray | None = None


def assemble_port_condensed_terms(
    condensed: AssemblyTimeCondensedSystem,
    port_terms: Mapping[int, CellPortTerms],
) -> dict[str, Any]:
    """Insert ``Bhat/Dhat/Hhat`` into the already trace-condensed AIJ matrix.

    The caller invokes this once, before creating the global factor.  The
    base assembly has already inserted ``S_V`` and preallocated appended-port
    support.  This function is the production bridge for nonzero local
    ``B_i``/``D_i``; it does not build a full p4 matrix or a dense Schur.
    """

    if condensed.matrix is None:
        raise ValueError("condensed matrix is not materialized")
    if condensed.appended_rows == 0:
        raise ValueError("port condensation requires appended port rows")
    inserted = 0
    nonzero_bi = nonzero_di = False
    for index, cell in enumerate(condensed.cell_recovery_maps):
        term = port_terms.get(index)
        if term is None:
            continue
        bi = _matrix(term.Bi, "CellPortTerms.Bi")
        di = _matrix(term.Di, "CellPortTerms.Di")
        ni = len(cell.interior_original_dofs)
        nt = len(cell.trace_original_dofs)
        ports = np.asarray(term.port_indices, dtype=PETSc.IntType)
        if (
            bi.shape[0] != ni
            or di.shape[1] != ni
            or bi.shape[1] != di.shape[0]
            or ports.ndim != 1
            or len(ports) != bi.shape[1]
            or len(np.unique(ports)) != len(ports)
        ):
            raise ValueError("local B_i/D_i dimensions do not match the cell")
        if np.any(ports < 0) or np.any(ports >= condensed.appended_rows):
            raise ValueError("local port index is outside the appended rows")
        ids, expansion, _identity = _cell_trace_expansion(
            np.asarray(cell.trace_original_dofs, dtype=PETSc.IntType),
            condensed.trace_constraints,
        )
        lu = condensed.interior_lu_by_class[cell.class_key]
        xit = -condensed.interior_from_trace_by_class[cell.class_key]
        xib = lu_solve(lu, bi)
        # The cached RHS projection already contains one V_ii^{-1}:
        #   T_g = -V_ti V_ii^{-1}.
        # Therefore Bhat = Bt + T_g Bi; multiplying T_g by XiB would
        # incorrectly apply a second inverse.
        trace_from_interior = condensed.trace_from_interior_rhs_by_class[
            cell.class_key
        ]
        b_hat = trace_from_interior @ bi
        if term.Bt is not None:
            bt = _matrix(term.Bt, "CellPortTerms.Bt")
            if bt.shape != (nt, len(ports)):
                raise ValueError("CellPortTerms.Bt has the wrong shape")
            b_hat = bt + b_hat
        d_hat = -di @ xit
        if term.Dt is not None:
            dt = _matrix(term.Dt, "CellPortTerms.Dt")
            if dt.shape != (len(ports), nt):
                raise ValueError("CellPortTerms.Dt has the wrong shape")
            d_hat = dt - di @ xit
        # The local elimination also contributes Hhat = H + Di XiB.  The
        # carrier's normalization H is inserted independently by
        # assemble_condensed_ports, so this is normally just Di XiB.
        h_hat = np.ascontiguousarray(di @ xib)
        if term.H is not None:
            h_local = _matrix(term.H, "CellPortTerms.H")
            if h_local.shape != (len(ports), len(ports)):
                raise ValueError("CellPortTerms.H has the wrong shape")
            h_hat = h_local + h_hat
        # PETSc's dense setValues path consumes row-major buffers.  In
        # particular, sparse CSR multiplication can return a non-C-contiguous
        # view for the lower-left block; passing that view can silently place
        # Dhat entries in the wrong rows while leaving the other blocks valid.
        b_active = np.ascontiguousarray(expansion.conj().T @ b_hat)
        d_active = np.ascontiguousarray(d_hat @ expansion)
        h_hat = np.ascontiguousarray(h_hat)
        global_ports = condensed.active_rows + ports
        condensed.matrix.setValues(ids, global_ports, b_active, addv=PETSc.InsertMode.ADD_VALUES)
        condensed.matrix.setValues(global_ports, ids, -d_active, addv=PETSc.InsertMode.ADD_VALUES)
        condensed.matrix.setValues(global_ports, global_ports, h_hat, addv=PETSc.InsertMode.ADD_VALUES)
        inserted += 1
        nonzero_bi = nonzero_bi or bool(np.any(bi))
        nonzero_di = nonzero_di or bool(np.any(di))
    condensed.matrix.assemble()
    return {
        "schema_version": "task039extra.v18.port-condensed-terms.v1",
        "cells_with_port_terms": inserted,
        "nonzero_Bi": nonzero_bi,
        "nonzero_Di": nonzero_di,
        "global_full_p4_matrix_allocated": False,
        "matrix_identity": petsc_csr_content_identity(condensed.matrix),
    }


def assemble_condensed_ports(
    condensed: AssemblyTimeCondensedSystem,
    carrier: Any,
) -> dict[int, CellPortTerms]:
    """Translate an MPC-processed carrier and assemble its local terms.

    Carrier rows are already dual/independent p4 storage rows.  A slave row is
    therefore rejected instead of being passed through another ``C^H``.  A
    shared trace row is assigned to one owner cell for the carrier value; the
    local Schur correction is still projected by the existing trace map.
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
            "Review V18 U0 carrier assembly is qualified for MPI1 only"
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
                raise RuntimeError(
                    f"interior original DoF {original} belongs to multiple cells"
                )
            interior_locations[original] = (cell_index, local)

    # Keep only nonzero interior terms per cell/port.  Independent trace
    # carrier rows are inserted directly into the final matrix below; dense
    # Bt/Dt/H copies on every incident cell would duplicate those values.
    bi_by_cell: dict[int, dict[int, dict[int, complex]]] = {}
    di_by_cell: dict[int, dict[int, dict[int, complex]]] = {}
    direct_b_entries = 0
    direct_d_entries = 0
    direct_h_entries = 0
    terms: dict[int, CellPortTerms] = {}
    for port, entry in enumerate(entries):
        coupling_rows = np.asarray(
            getattr(entry, "coupling_rows"), dtype=np.int64
        )
        coupling_values = np.asarray(
            getattr(entry, "coupling_values"), dtype=np.complex128
        )
        projection_rows = np.asarray(
            getattr(entry, "projection_rows"), dtype=np.int64
        )
        projection_values = np.asarray(
            getattr(entry, "projection_values"), dtype=np.complex128
        )
        if (
            coupling_rows.ndim != 1
            or projection_rows.ndim != 1
            or coupling_rows.shape != coupling_values.shape
            or projection_rows.shape != projection_values.shape
            or not np.isfinite(coupling_values).all()
            or not np.isfinite(projection_values).all()
        ):
            raise ValueError("carrier row/value arrays have different shapes")
        normalization_h = complex(getattr(entry, "normalization_h"))
        if not np.isfinite(normalization_h):
            raise ValueError("carrier normalization_h must be finite")
        condensed.matrix.setValue(
            condensed.active_rows + port,
            condensed.active_rows + port,
            PETSc.ScalarType(normalization_h),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        direct_h_entries += 1
        for rows, values, side in (
            (coupling_rows, coupling_values, "B"),
            (projection_rows, projection_values, "D"),
        ):
            for row, value in zip(rows, values, strict=True):
                row = int(row)
                value = complex(value)
                location = interior_locations.get(row)
                if location is not None:
                    target_cell, local = location
                    target = bi_by_cell if side == "B" else di_by_cell
                    per_port = target.setdefault(target_cell, {}).setdefault(port, {})
                    per_port[local] = per_port.get(local, 0.0) + value
                    continue
                active = active_map.get(row)
                if active is None:
                    raise ValueError(
                        "carrier includes an MPC slave row; duplicate C^H is forbidden"
                    )
                if side == "B":
                    condensed.matrix.setValue(
                        active,
                        condensed.active_rows + port,
                        PETSc.ScalarType(value),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
                    direct_b_entries += 1
                else:
                    condensed.matrix.setValue(
                        condensed.active_rows + port,
                        active,
                        PETSc.ScalarType(-value),
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
                    direct_d_entries += 1

    for cell_index in sorted(set(bi_by_cell) | set(di_by_cell)):
        cell = condensed.cell_recovery_maps[cell_index]
        ni = len(cell.interior_original_dofs)
        bi_ports = set(bi_by_cell.get(cell_index, {}))
        di_ports = set(di_by_cell.get(cell_index, {}))
        ports = np.asarray(sorted(bi_ports | di_ports), dtype=PETSc.IntType)
        bi = np.zeros((ni, len(ports)), dtype=np.complex128)
        di = np.zeros((len(ports), ni), dtype=np.complex128)
        for local_port, port in enumerate(ports):
            for local, value in bi_by_cell.get(cell_index, {}).get(
                int(port), {}
            ).items():
                bi[local, local_port] = value
            for local, value in di_by_cell.get(cell_index, {}).get(
                int(port), {}
            ).items():
                di[local_port, local] = value
        terms[cell_index] = CellPortTerms(
            Bi=bi,
            Di=di,
            port_indices=ports,
        )
    audit = assemble_port_condensed_terms(condensed, terms)
    for term in terms.values():
        term.Bi.setflags(write=False)
        term.Di.setflags(write=False)
    stored_term_bytes = int(
        sum(
            term.Bi.nbytes + term.Di.nbytes + term.port_indices.nbytes
            for term in terms.values()
        )
    )
    audit["carrier_rows_are_mpc_processed"] = True
    audit["carrier_cell_count"] = len(condensed.cell_recovery_maps)
    audit["interior_port_cell_count"] = len(terms)
    audit["stored_interior_term_bytes"] = stored_term_bytes
    audit["direct_trace_B_entries"] = direct_b_entries
    audit["direct_trace_D_entries"] = direct_d_entries
    audit["direct_normalization_H_entries"] = direct_h_entries
    audit["dense_trace_carrier_copies_retained"] = False
    # Keep the build audit serializable and compact.  The numerical terms are
    # owned by the adapter passed to the factor, not duplicated in metadata.
    condensed.build_audit["port_condensed_terms"] = {
        key: value for key, value in audit.items() if key != "matrix_identity"
    }
    condensed.build_audit["port_condensed_matrix_identity"] = dict(
        audit["matrix_identity"]
    )
    return terms


class P4CellCondensedInverse:
    """One global condensed factor with complete local recovery.

    The U0 adapter is explicitly MPI1-qualified.  It copies active trace
    coordinates from the already MPC-applied dual RHS, reduces interior RHS
    locally, performs one global factor solve, and returns exact slave zeros.
    """

    def __init__(self, condensed: AssemblyTimeCondensedSystem, factor: Any, *, port_terms: Mapping[int, CellPortTerms] | None = None, owns_condensed: bool = False, owns_factor: bool = False, retain_through_postprocess_v18: bool = True) -> None:
        if condensed.matrix is None:
            raise ValueError("p4 inverse requires a materialized condensed matrix")
        if condensed.comm.Get_size() != 1:
            raise NotImplementedError("Review V18 U0 adapter is qualified for MPI1 only")
        self.condensed = condensed; self.factor = factor; self.port_terms = dict(port_terms or {})
        self.owns_condensed = bool(owns_condensed); self.owns_factor = bool(owns_factor)
        self.retain_through_postprocess_v18 = bool(retain_through_postprocess_v18)
        self.solve_count = 0; self.destroyed = False; self.last_port_solution = np.empty(0, dtype=np.complex128); self.last_audit = {}
        self.timing_cumulative = {
            "reduce_seconds": 0.0,
            "solve_seconds": 0.0,
            "recover_seconds": 0.0,
            "elapsed_seconds": 0.0,
        }
        self.matrix_identity = petsc_csr_content_identity(condensed.matrix)
        active = {int(value) for value in condensed.trace_constraints.owned_active_original_dofs}
        self._slave_original = np.asarray([int(value) for value in condensed.owned_trace_original_dofs if int(value) not in active], dtype=PETSc.IntType)
        self._xiB_by_cell: dict[int, np.ndarray] = {}
        # Freeze every local B_i recovery operator during setup.  A later RHS
        # call must only perform vector work and the one global solve.
        for index, cell in enumerate(condensed.cell_recovery_maps):
            self._port_data(index, cell)

    def _port_data(self, index: int, cell: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        term = self.port_terms.get(int(index))
        if term is None:
            ni = len(cell.interior_original_dofs)
            return np.zeros((ni, 0), complex), np.zeros((0, ni), complex), np.empty(0, dtype=PETSc.IntType)
        Bi, Di = _matrix(term.Bi, "CellPortTerms.Bi"), _matrix(term.Di, "CellPortTerms.Di")
        ni = len(cell.interior_original_dofs)
        if Bi.shape[0] != ni or Di.shape[1] != ni or Bi.shape[1] != Di.shape[0]:
            raise ValueError("local port coupling dimensions do not match the cell")
        ports = np.asarray(term.port_indices, dtype=PETSc.IntType)
        if (
            ports.ndim != 1
            or len(ports) != Bi.shape[1]
            or np.any(ports < 0)
            or np.any(ports >= self.condensed.appended_rows)
            or len(np.unique(ports)) != len(ports)
        ):
            raise ValueError("local port index is outside the appended system")
        if index not in self._xiB_by_cell:
            self._xiB_by_cell[index] = np.ascontiguousarray(lu_solve(self.condensed.interior_lu_by_class[cell.class_key], Bi))
        return Bi, Di, ports

    def _reduce_storage_rhs(self, rhs: PETSc.Vec) -> PETSc.Vec:
        system = self.condensed; active_original = system.trace_constraints.owned_active_original_dofs
        reduced = system.create_augmented_vector()
        try:
            if len(active_original):
                reduced.getArray()[:len(active_original)] = np.asarray(rhs.getValues(active_original), dtype=PETSc.ScalarType)
            if len(self._slave_original) and np.any(rhs.getValues(self._slave_original) != 0.0):
                raise ValueError("native p4 RHS violates exact MPC slave-zero storage")
            for index, cell in enumerate(system.cell_recovery_maps):
                rows = np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType); gi = np.asarray(rhs.getValues(rows), dtype=np.complex128)
                if not np.any(gi):
                    continue
                xig = lu_solve(system.interior_lu_by_class[cell.class_key], gi)
                correction = system.trace_from_interior_rhs_by_class[cell.class_key] @ gi
                for original, value in zip(cell.trace_original_dofs, correction, strict=True):
                    if value == 0.0:
                        continue
                    ids, coefficients = system.trace_constraints.expansion_by_original[int(original)]
                    reduced.setValues(ids, np.asarray(np.conj(coefficients) * value, dtype=PETSc.ScalarType), addv=PETSc.InsertMode.ADD_VALUES)
                _Bi, Di, ports = self._port_data(index, cell)
                if len(ports):
                    reduced.setValues(system.active_rows + ports, np.asarray(Di @ xig, dtype=PETSc.ScalarType), addv=PETSc.InsertMode.ADD_VALUES)
            reduced.assemble(); return reduced
        except BaseException:
            reduced.destroy()
            raise

    def _solve_once(self, rhs: PETSc.Vec) -> PETSc.Vec:
        solution = rhs.duplicate(); solution.set(PETSc.ScalarType(0.0)); solve = getattr(self.factor, "solve_repeated", None)
        if not callable(solve):
            solve = getattr(self.factor, "solve", None)
        if not callable(solve):
            solution.destroy(); raise TypeError("factor has no solve_repeated/solve API")
        try:
            solve(rhs, solution)
        except BaseException:
            solution.destroy()
            raise
        self.solve_count += 1; return solution

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        started = perf_counter()
        audit: dict[str, Any] = {
            "schema_version": "task039extra.v18.p4-cell-condensed-inverse.v1",
            "input_is_mpc_dual_storage": True,
            "duplicate_C_H_applied": False,
            "factor_solve_call_delta": 0,
            "reduce_seconds": 0.0,
            "solve_seconds": 0.0,
            "recover_seconds": 0.0,
            "input_finite": None,
            "solution_finite": None,
            "output_finite": None,
        }
        reduced_rhs = None
        solution = None
        result = None
        try:
            if self.destroyed:
                raise RuntimeError("p4 cell-condensed inverse has been destroyed")
            if rhs.getSize() != self.condensed.full_rows:
                raise ValueError("native p4 RHS has the wrong storage size")
            rhs_values = np.asarray(rhs.getArray(readonly=True))
            input_finite = bool(np.isfinite(rhs_values).all())
            audit["input_finite"] = input_finite
            if not input_finite:
                raise ValueError("native p4 RHS contains non-finite values")
            if rhs.norm() == 0.0:
                result = rhs.duplicate()
                result.set(PETSc.ScalarType(0.0))
                self.last_port_solution = np.zeros(
                    self.condensed.appended_rows, dtype=np.complex128
                )
                audit.update(
                    {
                        "status": "ZERO_RHS_DIRECT_ZERO",
                        "slave_zero": True,
                        "solution_finite": True,
                        "output_finite": True,
                        "factor_solve_count": int(self.solve_count),
                    }
                )
                return result
            reduce_started = perf_counter()
            reduced_rhs = self._reduce_storage_rhs(rhs)
            audit["reduce_seconds"] = float(perf_counter() - reduce_started)
            reduced_values = np.asarray(reduced_rhs.getArray(readonly=True))
            if not np.isfinite(reduced_values).all():
                raise FloatingPointError(
                    "reduced native p4 RHS contains non-finite values"
                )
            # Nonzero native g always takes exactly one global MatSolve.
            solve_started = perf_counter()
            solution = self._solve_once(reduced_rhs)
            audit["solve_seconds"] = float(perf_counter() - solve_started)
            solution_values = np.asarray(solution.getArray(readonly=True))
            solution_finite = bool(np.isfinite(solution_values).all())
            audit["solution_finite"] = solution_finite
            if not solution_finite:
                raise FloatingPointError(
                    "condensed factor returned non-finite solution values"
                )
            local_active = int(self.condensed.owned_active_rows)
            active_solution = np.asarray(
                solution_values[:local_active], dtype=np.complex128
            ).copy()
            active_original = self.condensed.trace_constraints.owned_active_original_dofs
            result = rhs.duplicate()
            result.set(PETSc.ScalarType(0.0))
            if len(active_original):
                result.setValues(active_original, active_solution, addv=PETSc.InsertMode.INSERT_VALUES)
            self.last_port_solution = np.asarray(
                solution_values[
                    local_active : local_active + self.condensed.appended_rows
                ],
                dtype=np.complex128,
            ).copy()
            recovered_rows = 0
            recover_started = perf_counter()
            for index, cell in enumerate(self.condensed.cell_recovery_maps):
                local_trace = np.empty(len(cell.trace_original_dofs), dtype=np.complex128)
                for row, original in enumerate(cell.trace_original_dofs):
                    ids, coefficients = self.condensed.trace_constraints.expansion_by_original[int(original)]
                    local_trace[row] = np.dot(coefficients, active_solution[ids])
                rows = np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType); gi = np.asarray(rhs.getValues(rows), dtype=np.complex128)
                xig = lu_solve(self.condensed.interior_lu_by_class[cell.class_key], gi)
                values = self.condensed.interior_from_trace_by_class[cell.class_key] @ local_trace + xig
                _Bi, _Di, ports = self._port_data(index, cell)
                if len(ports):
                    values = values - self._xiB_by_cell[index] @ self.last_port_solution[ports]
                if not np.isfinite(values).all():
                    raise FloatingPointError(
                        "local p4 interior recovery returned non-finite values"
                    )
                result.setValues(rows, np.asarray(values, dtype=PETSc.ScalarType), addv=PETSc.InsertMode.INSERT_VALUES); recovered_rows += len(rows)
            result.assemble()
            audit["recover_seconds"] = float(perf_counter() - recover_started)
            output_values = np.asarray(result.getArray(readonly=True))
            output_finite = bool(np.isfinite(output_values).all())
            audit["output_finite"] = output_finite
            if not output_finite:
                raise FloatingPointError(
                    "p4 interior recovery produced non-finite output values"
                )
            audit.update(
                {
                    "status": "SOLVE_COMPLETED",
                    "factor_solve_call_delta": 1,
                    "factor_solve_count": int(self.solve_count),
                    "recovered_interior_rows": int(recovered_rows),
                    "slave_zero_policy": "zero_initialize_and_no_backsubstitution",
                    "retain_through_postprocess_v18": self.retain_through_postprocess_v18,
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
            audit["elapsed_seconds"] = float(perf_counter() - started)
            for key in self.timing_cumulative:
                self.timing_cumulative[key] += float(audit[key])
            audit["timing_cumulative"] = dict(self.timing_cumulative)
            self.last_audit = dict(audit)
            if solution is not None:
                solution.destroy()
            if reduced_rhs is not None:
                reduced_rhs.destroy()

    def destroy(self) -> None:
        if self.destroyed:
            return
        factor = self.factor
        self.factor = None
        condensed = self.condensed
        cleanup_error: BaseException | None = None
        try:
            if self.owns_factor and factor is not None:
                destroy = getattr(factor, "destroy", None)
                if callable(destroy):
                    destroy()
        except BaseException as exc:
            cleanup_error = exc
        finally:
            self._xiB_by_cell.clear()
            if self.owns_condensed and condensed is not None:
                # The historical helper predates this owning adapter and only
                # destroys its PETSc matrix.  Release the adapter-owned
                # numeric payload explicitly before/after invoking it.
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
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
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
