"""Small, audit-only owner-space LOR spectral calculations.

The routines in this module assemble bounded p2/p3 evidence for the positive
auxiliary operator.  They are deliberately separate from the HX fixture's
production path: an audit fixture may omit the scalar node matrix and HX
object, while the high matrix-free action, finalized MPC route, and low edge
matrix remain the same.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from petsc4py import PETSc
from scipy.linalg import eigh, svdvals

from .fullspace_lor_hx_root_cause import lift_low_primal, low_input_from_high_dual
from .fullspace_lor_native_hx_fixture import (
    _assemble_sparse,
)
from .fullspace_lor_transfer import build_local_lor_transfer


H_NM = 50.0
WORK_LIMIT = 1.0e-12
HIGH_ACTION_LIMIT = 1.0e-11
EIGEN_RESIDUAL_LIMIT = 1.0e-10
RANK_TOLERANCE = "max(m,n)*eps*sigma_max"
EIGEN_DRIVER = "gvx"
EIGEN_METHOD = "complex128_lapack_generalized_hermitian"
EIGEN_LIBRARY = "scipy.linalg.eigh"
EIGEN_SELECTION = "subset_endpoint"
RANK_METHOD = "scipy.linalg.svdvals"


def relative(left: np.ndarray, right: np.ndarray, denominator: np.ndarray | None = None) -> float:
    """Return a vector relative error with an explicit reference denominator."""

    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    base = right if denominator is None else np.asarray(denominator, dtype=np.complex128)
    return float(
        np.linalg.norm(left - right)
        / max(float(np.linalg.norm(base)), np.finfo(float).tiny)
    )


def scalar_relative(left: complex, right: complex) -> float:
    return float(abs(complex(left) - complex(right)) / max(abs(complex(right)), np.finfo(float).tiny))


def csr_matvec(
    indptr: np.ndarray, indices: np.ndarray, values: np.ndarray, vector: np.ndarray
) -> np.ndarray:
    """Apply a CSR matrix without importing a solver package."""

    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    vector = np.asarray(vector, dtype=np.complex128)
    result = np.zeros(indptr.size - 1, dtype=np.complex128)
    for row in range(result.size):
        start, stop = int(indptr[row]), int(indptr[row + 1])
        result[row] = np.dot(values[start:stop], vector[indices[start:stop]])
    return result


def csr_to_dense(
    rows: int, cols: int, indptr: np.ndarray, indices: np.ndarray, values: np.ndarray
) -> np.ndarray:
    dense = np.zeros((int(rows), int(cols)), dtype=np.complex128)
    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    for row in range(int(rows)):
        start, stop = int(indptr[row]), int(indptr[row + 1])
        dense[row, indices[start:stop]] = values[start:stop]
    return dense


def csr_right_product(dense_left: np.ndarray, matrix: Mapping[str, Any]) -> np.ndarray:
    """Multiply a dense left operand by a CSR right operand."""

    dense_left = np.asarray(dense_left, dtype=np.complex128)
    result = np.zeros((dense_left.shape[0], int(matrix["cols"])), dtype=np.complex128)
    for row in range(int(matrix["rows"])):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        for position in range(start, stop):
            result[:, int(matrix["indices"][position])] += (
                dense_left[:, row] * matrix["values"][position]
            )
    return result


def csr_adjoint_left_product(matrix: Mapping[str, Any], dense_right: np.ndarray) -> np.ndarray:
    """Multiply a CSR adjoint by a dense right operand."""

    dense_right = np.asarray(dense_right, dtype=np.complex128)
    result = np.zeros((int(matrix["cols"]), dense_right.shape[1]), dtype=np.complex128)
    for row in range(int(matrix["rows"])):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        for position in range(start, stop):
            column = int(matrix["indices"][position])
            result[column] += np.conj(matrix["values"][position]) * dense_right[row]
    return result


def petsc_csr(matrix: PETSc.Mat) -> dict[str, Any]:
    """Read one serial PETSc AIJ matrix into hashable CSR facts."""

    if matrix.comm.size != 1:
        raise ValueError("the bounded owner-space audit currently requires MPI1")
    rows, cols = (int(value) for value in matrix.getSize())
    indptr, indices, values = matrix.getValuesCSR()
    indptr = np.asarray(indptr, dtype=np.int64).copy()
    indices = np.asarray(indices, dtype=np.int64).copy()
    values = np.asarray(values, dtype=np.complex128).copy()
    if indptr.shape != (rows + 1,) or np.any(indices < 0) or np.any(indices >= cols):
        raise ValueError("PETSc CSR layout is inconsistent with matrix size")
    return {
        "rows": rows,
        "cols": cols,
        "nnz": int(values.size),
        "indptr": indptr,
        "indices": indices,
        "values": values,
        "index_bytes": int(indptr.nbytes + indices.nbytes),
        "numeric_bytes": int(values.nbytes),
    }


def global_slave_rows(space: Any, mpc: Any) -> np.ndarray:
    """Convert finalized local MPC slave indices to global raw row IDs."""

    index_map = space.dofmap.index_map
    storage = int(index_map.size_local + index_map.num_ghosts)
    global_ids = np.asarray(
        index_map.local_to_global(np.arange(storage, dtype=np.int32)), dtype=np.int64
    )
    local = np.asarray(mpc.slaves, dtype=np.int64)
    local = local[(local >= 0) & (local < storage)]
    return np.unique(global_ids[local]).astype(np.int64, copy=False)


def build_owner_layout(
    full_rows: int,
    slave_rows: np.ndarray,
    raw_to_canonical: Mapping[int, int | tuple[int, int]],
    owner_ids: np.ndarray,
    *,
    owner_authority: str = "independent_topology_authority",
) -> dict[str, Any]:
    """Build an explicit raw-row/owner-ID bijection without ordinal assumptions."""

    full_rows = int(full_rows)
    slave = np.asarray(slave_rows, dtype=np.int64)
    owners = np.asarray(owner_ids, dtype=np.int64)
    if slave.ndim != 1 or owners.ndim != 1:
        raise ValueError("row inventories must be one-dimensional")
    if np.any(slave < 0) or np.any(slave >= full_rows) or np.unique(slave).size != slave.size:
        raise ValueError("slave rows are not unique and in range")
    slave_set = set(int(value) for value in slave.tolist())
    active = np.asarray(
        [row for row in range(full_rows) if row not in slave_set], dtype=np.int64
    )
    canonical_values: list[int] = []
    phase_values: list[int] = []
    for raw in active.tolist():
        try:
            value = raw_to_canonical[int(raw)]
        except KeyError as exc:
            raise ValueError(f"missing canonical owner mapping for raw row {raw}") from exc
        if isinstance(value, tuple):
            canonical, phase = value
        else:
            canonical, phase = value, 0
        canonical_values.append(int(canonical))
        phase_values.append(int(phase))
    canonical = np.asarray(canonical_values, dtype=np.int64)
    phase = np.asarray(phase_values, dtype=np.int8)
    if np.unique(canonical).size != canonical.size:
        raise ValueError("active raw rows do not map uniquely to canonical IDs")
    if np.unique(owners).size != owners.size or not np.array_equal(
        np.sort(canonical), np.sort(owners)
    ):
        raise ValueError("active rows and canonical owner IDs are not a bijection")
    return {
        "full_rows": full_rows,
        "slave_rows": slave.copy(),
        "active_raw_rows": active,
        "canonical_ids": canonical,
        "owner_ids": owners.copy(),
        "owner_authority": owner_authority,
        "phase_codes": phase,
        "owner_count": int(active.size),
        "bijection": True,
    }


def deterministic_probes(size: int, count: int = 8, *, seed: int = 17) -> np.ndarray:
    """Return fixed nonzero complex probes without a rank-local RNG."""

    index = np.arange(int(size), dtype=np.float64)
    result = np.empty((int(count), int(size)), dtype=np.complex128)
    for probe in range(int(count)):
        result[probe] = (
            np.sin((0.013 + 0.001 * (probe + seed)) * (index + 1.0))
            + 1j * np.cos((0.017 + 0.0007 * (probe + seed)) * (index + 2.0))
        )
    return result


def generalized_endpoints(operator: np.ndarray, mass: np.ndarray) -> dict[str, Any]:
    """Compute fixed LAPACK generalized Hermitian endpoint evidence."""

    operator = np.asarray(operator, dtype=np.complex128)
    mass = np.asarray(mass, dtype=np.complex128)
    if operator.ndim != 2 or mass.shape != operator.shape:
        raise ValueError("generalized endpoint matrices must be square and conforming")
    values_small, vectors_small = eigh(
        operator,
        mass,
        subset_by_index=[0, 0],
        driver=EIGEN_DRIVER,
        check_finite=True,
    )
    values_large, vectors_large = eigh(
        operator,
        mass,
        subset_by_index=[operator.shape[0] - 1, operator.shape[0] - 1],
        driver=EIGEN_DRIVER,
        check_finite=True,
    )
    result: dict[str, Any] = {}
    for name, values, vectors in (
        ("smallest", values_small, vectors_small),
        ("largest", values_large, vectors_large),
    ):
        eigenvalue = float(values[0])
        vector = np.asarray(vectors[:, 0], dtype=np.complex128)
        aq = operator @ vector
        bq = mass @ vector
        denominator = max(
            float(np.linalg.norm(aq)),
            abs(eigenvalue) * float(np.linalg.norm(bq)),
            np.finfo(float).tiny,
        )
        result[name] = {
            "eigenvalue": eigenvalue,
            "vector": vector,
            "Aq": aq,
            "Bq": bq,
            "residual_relative": float(
                np.linalg.norm(aq - eigenvalue * bq) / denominator
            ),
            "imaginary_part": float(np.imag(eigenvalue)),
        }
    result["lambda_min"] = float(result["smallest"]["eigenvalue"])
    result["lambda_max"] = float(result["largest"]["eigenvalue"])
    if (
        np.isfinite(result["lambda_min"])
        and np.isfinite(result["lambda_max"])
        and result["lambda_min"] != 0.0
    ):
        result["condition"] = float(result["lambda_max"] / result["lambda_min"])
    else:
        result["condition"] = None
    return result


def _coo_to_csr(rows: int, cols: int, entries: Mapping[tuple[int, int], complex]) -> dict[str, Any]:
    ordered = sorted(
        ((int(row), int(col), complex(value)) for (row, col), value in entries.items() if value != 0),
        key=lambda item: (item[0], item[1]),
    )
    indptr = np.zeros(int(rows) + 1, dtype=np.int64)
    indices = np.empty(len(ordered), dtype=np.int64)
    values = np.empty(len(ordered), dtype=np.complex128)
    for position, (row, col, value) in enumerate(ordered):
        indptr[row + 1] += 1
        indices[position] = col
        values[position] = value
    np.cumsum(indptr, out=indptr)
    return {
        "rows": int(rows),
        "cols": int(cols),
        "nnz": int(values.size),
        "indptr": indptr,
        "indices": indices,
        "values": values,
        "index_bytes": int(indptr.nbytes + indices.nbytes),
        "numeric_bytes": int(values.nbytes),
    }


def build_sparse_transfer(fixture: Any, low_layout: Mapping[str, Any], high_layout: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble one sparse local-cell transfer, with orientation/phase once."""

    local_transfer = build_local_lor_transfer(int(fixture.degree))
    high_rows = int(high_layout["owner_count"])
    low_cols = int(low_layout["owner_count"])
    if local_transfer.lor_to_high_matrix.shape[1] != int(fixture.lor_topology.edge_count):
        raise ValueError("local transfer and packed topology edge counts differ")
    high_map = fixture.high_space.dofmap.index_map
    high_full = int(high_layout["full_rows"])
    multiplicity = np.zeros(high_full, dtype=np.int64)
    cell_count = int(fixture.high_mesh.topology.index_map(3).size_local)
    local_rows: list[np.ndarray] = []
    for cell in range(cell_count):
        local_dofs = np.asarray(fixture.high_space.dofmap.cell_dofs(cell), dtype=np.int32)
        global_rows = np.asarray(high_map.local_to_global(local_dofs), dtype=np.int64)
        if np.any(global_rows < 0) or np.any(global_rows >= high_full):
            raise ValueError("high cell row is outside the full raw layout")
        local_rows.append(global_rows)
        np.add.at(multiplicity, global_rows, 1)
    if np.any(multiplicity[np.asarray(high_layout["active_raw_rows"], dtype=np.int64)] <= 0):
        raise ValueError("high active rows are not covered by local transfer cells")
    active_row_positions = {
        int(raw): position
        for position, raw in enumerate(np.asarray(high_layout["active_raw_rows"], dtype=np.int64))
    }
    low_positions = {
        int(canonical): position
        for position, canonical in enumerate(np.asarray(low_layout["canonical_ids"], dtype=np.int64))
    }
    cell_info = np.asarray(fixture.high_mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    topology = fixture.lor_topology
    entries: dict[tuple[int, int], complex] = {}
    for cell, global_rows in enumerate(local_rows):
        local_matrix = np.asarray(local_transfer.lor_to_high_matrix, dtype=np.complex128)
        if local_matrix.shape[0] != global_rows.size:
            raise ValueError("local high transfer rows do not match high cell dofs")
        low_ids = np.asarray(topology.cell_edge_ids[cell], dtype=np.int64)
        positions = np.asarray([low_positions.get(int(value), -1) for value in low_ids], dtype=np.int64)
        if np.any(positions < 0):
            raise ValueError("high-cell transfer refers to an unknown low owner ID")
        factors = np.asarray(topology.cell_orientation[cell], dtype=np.complex128) * np.asarray(
            topology.phase_values[topology.cell_phase_codes[cell]], dtype=np.complex128
        )
        for local_column, low_position in enumerate(positions.tolist()):
            column = local_matrix[:, local_column] * factors[local_column]
            column = np.asarray(column, dtype=np.complex128).copy()
            fixture.high_space.element.T_apply(
                column, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            for local_row, raw_row in enumerate(global_rows.tolist()):
                row_position = active_row_positions.get(int(raw_row))
                if row_position is None:
                    continue
                key = (int(row_position), int(low_position))
                entries[key] = entries.get(key, 0.0 + 0.0j) + (
                    column[local_row] / float(multiplicity[int(raw_row)])
                )
    result = _coo_to_csr(high_rows, low_cols, entries)
    result["construction"] = "one_local_cell_transfer_per_coarse_cell_with_T_apply_and_owner_ids"
    result["orientation_phase_once"] = True
    return result


def _independent_csr(full: Mapping[str, Any], active_rows: np.ndarray) -> dict[str, Any]:
    active = np.asarray(active_rows, dtype=np.int64)
    if active.ndim != 1 or np.unique(active).size != active.size:
        raise ValueError("active CSR rows must be a unique one-dimensional inventory")
    if np.any(active < 0) or np.any(active >= int(full["rows"])):
        raise ValueError("active CSR rows are out of range")
    column_position = np.full(int(full["cols"]), -1, dtype=np.int64)
    column_position[active] = np.arange(active.size, dtype=np.int64)
    entries: dict[tuple[int, int], complex] = {}
    for new_row, raw_row in enumerate(active.tolist()):
        start, stop = int(full["indptr"][raw_row]), int(full["indptr"][raw_row + 1])
        for position in range(start, stop):
            new_column = int(column_position[int(full["indices"][position])])
            if new_column >= 0:
                entries[(new_row, new_column)] = complex(full["values"][position])
    return _coo_to_csr(active.size, active.size, entries)


def _vector_from_values(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    if vector.getSize() != int(np.asarray(values).size):
        vector.destroy()
        raise ValueError("vector values have an incompatible PETSc size")
    vector.array[:] = np.asarray(values, dtype=np.complex128)
    vector.assemble()
    return vector


def _high_matrix_free_action(fixture: Any, values: np.ndarray) -> np.ndarray:
    vector = _vector_from_values(fixture.high_action.matrix, values)
    result = fixture.apply_high_action_copy(vector)
    try:
        return np.asarray(result.array, dtype=np.complex128).copy()
    finally:
        result.destroy()
        vector.destroy()


def _route_pull_action(fixture: Any, low_layout: Mapping[str, Any], values: np.ndarray) -> np.ndarray:
    vector = _vector_from_values(fixture.edge_matrix, np.zeros(int(low_layout["full_rows"]), dtype=np.complex128))
    try:
        vector.array[np.asarray(low_layout["active_raw_rows"], dtype=np.int64)] = np.asarray(values, dtype=np.complex128)
        high = lift_low_primal(fixture, vector)
        action = fixture.apply_high_action_copy(high)
        try:
            low, _packet = low_input_from_high_dual(fixture, action)
            try:
                return np.asarray(low.array[np.asarray(low_layout["active_raw_rows"], dtype=np.int64)], dtype=np.complex128).copy()
            finally:
                low.destroy()
        finally:
            action.destroy()
            high.destroy()
    finally:
        vector.destroy()


def audit_fixture(fixture: Any, *, probe_count: int = 8) -> dict[str, Any]:
    """Build all bounded owner-space facts for one audit-only fixture."""

    if fixture.comm.size != 1:
        raise ValueError("owner-space audit currently supports MPI1 only")
    if getattr(fixture, "build_hx", True):
        raise ValueError("global spectral audit requires the audit-only fixture")
    low_matrix_full = petsc_csr(fixture.edge_matrix)
    high_matrix_object = _assemble_sparse(
        fixture.high_form, mpc=fixture.high_floquet.mpc
    )
    try:
        high_matrix_full = petsc_csr(high_matrix_object)
    finally:
        high_matrix_object.destroy()
    low_slave = global_slave_rows(fixture.lor_edge_space, fixture.lor_edge_floquet.mpc)
    high_slave = global_slave_rows(fixture.high_space, fixture.high_floquet.mpc)
    low_raw_map = fixture._raw_edge_canonical_map()
    low_active = np.asarray(
        [row for row in range(int(low_matrix_full["rows"])) if row not in set(low_slave.tolist())],
        dtype=np.int64,
    )
    low_owner_ids = np.asarray(
        fixture.lor_raw_topology.owned_edge_ids, dtype=np.int64
    )
    low_layout = build_owner_layout(
        int(low_matrix_full["rows"]),
        low_slave,
        low_raw_map,
        low_owner_ids,
        owner_authority="lor_raw_topology.owned_edge_ids",
    )
    high_active = np.asarray(
        [row for row in range(int(high_matrix_full["rows"])) if row not in set(high_slave.tolist())],
        dtype=np.int64,
    )
    high_route_ids = np.asarray(fixture.lor_topology.owned_edge_ids, dtype=np.int64)
    if high_route_ids.size != high_active.size or np.unique(high_route_ids).size != high_route_ids.size:
        raise ValueError("high route owner inventory does not close independent rows")
    high_layout = {
        "full_rows": int(high_matrix_full["rows"]),
        "slave_rows": high_slave,
        "active_raw_rows": high_active,
        "owner_ids": high_route_ids.copy(),
        "owner_authority": "lor_topology.owned_edge_ids",
        "owner_count": int(high_active.size),
        "active_slave_partition": True,
        "independent_dimension_closed": int(high_active.size) == int(low_active.size),
    }
    if low_layout["owner_count"] != high_layout["owner_count"]:
        raise ValueError("high and low independent dimensions differ")
    if np.any(np.asarray(low_layout["phase_codes"], dtype=np.int8) != 0):
        raise ValueError("active LOR owner rows contain a nonzero phase code")
    transfer = build_sparse_transfer(fixture, low_layout, high_layout)
    low_ind = _independent_csr(low_matrix_full, low_active)
    high_ind = _independent_csr(high_matrix_full, high_active)
    low_dense = csr_to_dense(low_ind["rows"], low_ind["cols"], low_ind["indptr"], low_ind["indices"], low_ind["values"])
    high_dense = csr_to_dense(high_ind["rows"], high_ind["cols"], high_ind["indptr"], high_ind["indices"], high_ind["values"])
    high_times_transfer = csr_right_product(high_dense, transfer)
    pulled_dense = csr_adjoint_left_product(transfer, high_times_transfer)
    probes = deterministic_probes(int(low_layout["owner_count"]), probe_count)
    high_probes = deterministic_probes(int(high_matrix_full["rows"]), probe_count, seed=41)
    for vector in high_probes:
        vector[high_slave] = 0.0 + 0.0j
    high_action_relatives: list[float] = []
    work_relatives: list[float] = []
    pull_relatives: list[float] = []
    high_action_expected: list[np.ndarray] = []
    high_action_observed: list[np.ndarray] = []
    work_payload: list[dict[str, np.ndarray]] = []
    pull_expected: list[np.ndarray] = []
    pull_observed: list[np.ndarray] = []
    for vector in high_probes:
        expected = csr_matvec(high_matrix_full["indptr"], high_matrix_full["indices"], high_matrix_full["values"], vector)
        observed = _high_matrix_free_action(fixture, vector)
        high_action_relatives.append(relative(observed, expected, denominator=expected))
        high_action_expected.append(expected)
        high_action_observed.append(observed)
    for probe in probes:
        low_raw = np.zeros(int(low_matrix_full["rows"]), dtype=np.complex128)
        low_raw[low_active] = probe
        low_vector = _vector_from_values(fixture.edge_matrix, low_raw)
        lifted = lift_low_primal(fixture, low_vector)
        try:
            high_values = np.asarray(lifted.array, dtype=np.complex128).copy()
            dual_raw = np.zeros(int(high_matrix_full["rows"]), dtype=np.complex128)
            dual_raw[high_active] = deterministic_probes(int(high_layout["owner_count"]), 1, seed=91 + len(work_relatives))[0]
            dual = _vector_from_values(fixture.high_action.matrix, dual_raw)
            try:
                low_dual, _packet = low_input_from_high_dual(fixture, dual)
                try:
                    owner_dual = np.asarray(low_dual.array[low_active], dtype=np.complex128).copy()
                    work_relatives.append(
                        scalar_relative(
                            np.vdot(high_values, dual_raw),
                            np.vdot(probe, owner_dual),
                        )
                    )
                    work_payload.append(
                        {
                            "high_primal": high_values.copy(),
                            "high_dual": dual_raw.copy(),
                            "owner_primal": probe.copy(),
                            "owner_dual": owner_dual,
                        }
                    )
                finally:
                    low_dual.destroy()
            finally:
                dual.destroy()
            route = _route_pull_action(fixture, low_layout, probe)
            expected_pull = pulled_dense @ probe
            pull_relatives.append(relative(route, expected_pull, denominator=expected_pull))
            pull_expected.append(expected_pull)
            pull_observed.append(route)
        finally:
            lifted.destroy()
            low_vector.destroy()
    transfer_dense = csr_to_dense(
        transfer["rows"], transfer["cols"], transfer["indptr"], transfer["indices"], transfer["values"]
    )
    singular_values = np.asarray(
        svdvals(transfer_dense, check_finite=True), dtype=np.float64
    )
    sigma_max = float(np.max(singular_values)) if singular_values.size else 0.0
    rank_tau = max(transfer["rows"], transfer["cols"]) * np.finfo(np.float64).eps * sigma_max
    numerical_rank = int(np.count_nonzero(singular_values > rank_tau))
    hermitian_high = relative(high_dense, high_dense.conj().T, denominator=high_dense)
    hermitian_low = relative(low_dense, low_dense.conj().T, denominator=low_dense)
    hermitian_pull = relative(pulled_dense, pulled_dense.conj().T, denominator=pulled_dense)
    spd: dict[str, Any] = {}
    for name, matrix in (("B_L", low_dense), ("A_pull", pulled_dense)):
        try:
            np.linalg.cholesky(matrix)
        except np.linalg.LinAlgError as exc:
            spd[name] = {"positive_definite": False, "error": str(exc)}
        else:
            spd[name] = {"positive_definite": True}
    if all(bool(item["positive_definite"]) for item in spd.values()):
        try:
            spectral = generalized_endpoints(pulled_dense, low_dense)
            spectral["status"] = "solved"
        except (ValueError, TypeError, RuntimeError, np.linalg.LinAlgError) as exc:
            spectral = {"status": "implementation_error", "error": str(exc)}
    else:
        spectral = {"status": "not_run_spd_failure"}
    condition = (
        float(spectral["condition"])
        if spectral.get("condition") is not None
        else None
    )
    fixture_audit = dict(fixture.audit)
    fixture_hx_audit = dict(fixture_audit.get("hx_audit", {}))
    audit = {
        "fixture_audit": fixture_audit,
        "fixture_hx_audit": fixture_hx_audit,
        "high_order_global_aij": bool(fixture_audit.get("high_order_global_aij", False)),
        "global_transfer_matrix": bool(fixture_audit.get("global_transfer_matrix", False)),
        "global_numeric_allgather": bool(fixture_audit.get("global_numeric_allgather", False)),
        "sparse_independent_transfer": True,
        "temporary_dense_transfer_for_rank_svd": True,
        "production_global_dense_transfer": False,
        "orientation_phase_once": fixture_audit.get("phase_application") == "finalized_floquet_mpc_once",
        "fixture_build_hx": bool(getattr(fixture, "build_hx", True)),
        "fixture_hx_constructed": bool(fixture.hx is not None),
        "low_owner_bijection": bool(low_layout["bijection"]),
        "high_owner_count_closed": int(high_layout["owner_count"])
        == int(high_layout["full_rows"] - high_layout["slave_rows"].size),
    }
    return {
        "settings": {
            "degree": int(fixture.degree),
            "h_nm": H_NM,
            "rank_tolerance": RANK_TOLERANCE,
            "work_limit": WORK_LIMIT,
            "high_action_limit": HIGH_ACTION_LIMIT,
            "eigen_residual_limit": EIGEN_RESIDUAL_LIMIT,
            "eigen_method": EIGEN_METHOD,
            "eigen_library": EIGEN_LIBRARY,
            "eigen_driver": EIGEN_DRIVER,
            "eigen_selection": EIGEN_SELECTION,
            "rank_method": RANK_METHOD,
            "condition_policy": "report_only_no_cap",
        },
        "low_layout": low_layout,
        "high_layout": high_layout,
        "low_matrix_full": low_matrix_full,
        "high_matrix_full": high_matrix_full,
        "low_matrix_ind": low_ind,
        "high_matrix_ind": high_ind,
        "transfer": transfer,
        "pulled_dense": pulled_dense,
        "probes": probes,
        "high_probes": high_probes,
        "high_action_relatives": high_action_relatives,
        "high_action_expected": np.asarray(high_action_expected, dtype=np.complex128),
        "high_action_observed": np.asarray(high_action_observed, dtype=np.complex128),
        "work_relatives": work_relatives,
        "work_payload": work_payload,
        "pull_relatives": pull_relatives,
        "pull_expected": np.asarray(pull_expected, dtype=np.complex128),
        "pull_observed": np.asarray(pull_observed, dtype=np.complex128),
        "hermitian_defects": {
            "B_H": float(hermitian_high),
            "B_L": float(hermitian_low),
            "A_pull": float(hermitian_pull),
        },
        "singular_values": singular_values,
        "rank_tau": float(rank_tau),
        "tested_dimension": int(low_layout["owner_count"]),
        "numerical_rank": numerical_rank,
        "spectral": spectral,
        "condition": condition,
        "spd": spd,
        "lambda_min_positive_threshold": (
            max(
                float(low_layout["owner_count"])
                * np.finfo(float).eps
                * float(spectral["largest"]["eigenvalue"]),
                0.0,
            )
            if spectral.get("status") == "solved"
            and np.isfinite(float(spectral["largest"]["eigenvalue"]))
            else None
        ),
        "audit": audit,
    }


__all__ = (
    "EIGEN_DRIVER",
    "EIGEN_LIBRARY",
    "EIGEN_METHOD",
    "EIGEN_RESIDUAL_LIMIT",
    "EIGEN_SELECTION",
    "RANK_METHOD",
    "H_NM",
    "HIGH_ACTION_LIMIT",
    "RANK_TOLERANCE",
    "WORK_LIMIT",
    "audit_fixture",
    "build_owner_layout",
    "build_sparse_transfer",
    "csr_matvec",
    "csr_adjoint_left_product",
    "csr_right_product",
    "csr_to_dense",
    "deterministic_probes",
    "generalized_endpoints",
    "global_slave_rows",
    "petsc_csr",
    "relative",
    "scalar_relative",
)
