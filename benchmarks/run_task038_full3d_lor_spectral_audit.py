"""Thin p3/h50 MPI1 owner-space LOR spectral audit worker.

The worker records raw owner-space algebra and a sparse low-order matrix.  It
does not change the production HX implementation and it never builds a
high-order global AIJ or a dense transfer matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_lor_hx import (
    _append_stage_marker,
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from benchmarks.run_task038_full3d_lor_hx_krylov import _closeout_record
from src.solvers.fullspace_lor_hx_root_cause import low_input_from_high_dual
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture
from src.solvers.fullspace_lor_spectral_audit import (
    DEGREE,
    EIGEN_RESIDUAL_LIMIT,
    EPS_MAX_IT,
    EPS_FACTOR_SOLVER,
    EPS_KSP_TYPE,
    EPS_NCV,
    EPS_NEV,
    EPS_PC_TYPE,
    EPS_SHIFT,
    EPS_ST_TYPE,
    EPS_TOL,
    FULL_EDGE_ROWS,
    H_NM,
    INDEPENDENT_EDGE_ROWS,
    LINEARITY_ALPHA,
    LINEARITY_BETA,
    LINEARITY_LIMIT,
    REPEAT_LIMIT,
    SLAVE_EDGE_ROWS,
    SPECTRAL_CONDITION_LIMIT,
    WORK_LIMIT,
    build_independent_layout,
    build_pulled_high_shell,
    create_independent_submatrix,
    extract_owner_values,
    high_dual_to_owner,
    owner_to_high,
    raw_slave_global_rows,
    solve_extreme_generalized_pairs,
    work_identity_relative,
    apply_with_input_snapshot,
)


SCHEMA = "task038.lor-native-complex-hx.global-spectral-audit.v1"
STAGE = "global-spectral-audit"
CASE = "p3-mpi1"
SOURCE_NAME = "random"
VARIANT = "sequential-v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_sha(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _write_array(raw_dir: Path, name: str, values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values)
    path = raw_dir / f"audit_{name}.npy"
    np.save(path, values, allow_pickle=False)
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _vector_artifact(
    raw_dir: Path, name: str, values: np.ndarray, coordinate: str
) -> dict[str, Any]:
    return {"coordinate": coordinate, "values": _write_array(raw_dir, name, values)}


def _split_raw_edge_canonical_map(
    raw_map: dict[int, tuple[int, int]]
) -> tuple[dict[int, int], dict[int, int]]:
    """Separate canonical edge identity from its finalized phase code."""

    canonical: dict[int, int] = {}
    phases: dict[int, int] = {}
    for raw_row, value in raw_map.items():
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError(f"raw edge row {raw_row} has no (canonical, phase) pair")
        canonical_id, phase_code = value
        canonical[int(raw_row)] = int(canonical_id)
        phases[int(raw_row)] = int(phase_code)
    return canonical, phases


def _require_global_size(name: str, values: np.ndarray, expected: int) -> None:
    if int(np.asarray(values).size) != int(expected):
        raise RuntimeError(
            f"{name} has {np.asarray(values).size} entries; expected {expected}"
        )


def _matrix_artifact(
    raw_dir: Path, matrix: Any, row_keys: np.ndarray
) -> dict[str, Any]:
    indptr, indices, values = matrix.getValuesCSR()
    indptr = np.asarray(indptr)
    indices = np.asarray(indices)
    values = np.asarray(values, dtype=np.complex128)
    rows, cols = (int(value) for value in matrix.getSize())
    if rows != int(row_keys.size) or np.any(indices < 0) or np.any(indices >= cols):
        raise RuntimeError("independent CSR layout is not closed")
    return {
        "rows": rows,
        "cols": cols,
        "type": str(matrix.getType()),
        "nnz": int(values.size),
        "numeric_bytes": int(values.nbytes),
        "index_bytes": int(indptr.nbytes + indices.nbytes),
        "indptr": _write_array(raw_dir, "B_L_ind_indptr", indptr),
        "indices": _write_array(raw_dir, "B_L_ind_indices", indices),
        "values": _write_array(raw_dir, "B_L_ind_values", values),
        "row_keys": _write_array(raw_dir, "B_L_ind_row_keys", np.asarray(row_keys, dtype=np.int64)),
    }


def _deterministic_vector(size: int, salt: int) -> np.ndarray:
    index = np.arange(int(size), dtype=np.float64)
    return (
        0.31 * np.sin((index + 1.0) * (0.17 + 0.013 * salt))
        + 0.21 * np.cos((index + 1.0) * (0.29 + 0.017 * salt))
        + 1j * (0.19 * np.sin((index + 1.0) * (0.23 + 0.011 * salt)) + 0.07)
    ).astype(np.complex128)


def _high_probe(size: int, salt: int) -> np.ndarray:
    index = np.arange(int(size), dtype=np.float64)
    return (
        0.27 * np.cos((index + 1.0) * (0.11 + 0.019 * salt))
        + 1j * 0.23 * np.sin((index + 1.0) * (0.37 + 0.007 * salt))
    ).astype(np.complex128)


def _apply_owner(matrix: Any, values: np.ndarray) -> np.ndarray:
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    try:
        source.array[:] = np.asarray(values, dtype=np.complex128)
        matrix.mult(source, target)
        return np.asarray(target.array, dtype=np.complex128).copy()
    finally:
        target.destroy()
        source.destroy()


def _route_ids(fixture: Any, layout: dict[str, Any], owner_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    low = fixture.edge_matrix.createVecRight()
    try:
        low.set(0.0 + 0.0j)
        active = np.asarray(layout["active_raw_rows"], dtype=np.int64)
        low.array[active] = np.asarray(owner_values, dtype=np.complex128)
        return fixture._route_low_owner_packet(low)
    finally:
        low.destroy()


def _build_record(
    raw_dir: Path,
    record_path: Path,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    artifacts: dict[str, Any],
    matrix_artifact: dict[str, Any],
    layout: dict[str, Any],
    phase_codes: np.ndarray,
    high_layout: dict[str, Any],
    fixture_audit: dict[str, Any],
    provenance: dict[str, str],
    route_audit: dict[str, Any],
    spectral: dict[str, Any],
    scalar_facts: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "stage": STAGE,
        "case": CASE,
        "degree": DEGREE,
        "h_nm": H_NM,
        "source_name": SOURCE_NAME,
        "variant": VARIANT,
        "mpi_size": 1,
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": source,
        "runtime": runtime,
        "provenance": provenance,
        "settings": {
            "owner_coordinate": "increasing_raw_active_edge_row",
            "full_edge_rows": FULL_EDGE_ROWS,
            "slave_edge_rows": SLAVE_EDGE_ROWS,
            "independent_edge_rows": INDEPENDENT_EDGE_ROWS,
            "linearity_alpha": [float(LINEARITY_ALPHA.real), float(LINEARITY_ALPHA.imag)],
            "linearity_beta": [float(LINEARITY_BETA.real), float(LINEARITY_BETA.imag)],
            "slepc_problem_type": "GHEP",
            "slepc_type": "KRYLOVSCHUR",
            "slepc_nev": EPS_NEV,
            "slepc_ncv": EPS_NCV,
            "slepc_tol": EPS_TOL,
            "slepc_max_it": EPS_MAX_IT,
            "slepc_st_type": EPS_ST_TYPE,
            "slepc_shift": EPS_SHIFT,
            "slepc_ksp_type": EPS_KSP_TYPE,
            "slepc_pc_type": EPS_PC_TYPE,
            "slepc_factor_solver": EPS_FACTOR_SOLVER,
            "spectral_condition_limit": SPECTRAL_CONDITION_LIMIT,
            "work_limit": WORK_LIMIT,
            "linearity_limit": LINEARITY_LIMIT,
            "repeat_limit": REPEAT_LIMIT,
            "eigen_residual_limit": EIGEN_RESIDUAL_LIMIT,
        },
        "layout": {
            "full_rows": int(layout["full_rows"]),
            "slave_rows": int(np.asarray(layout["slave_rows"]).size),
            "owner_count": int(layout["owner_count"]),
            "bijection": bool(layout["bijection"]),
            "active_raw_rows": _write_array(raw_dir, "active_raw_rows", layout["active_raw_rows"]),
            "slave_raw_rows": _write_array(raw_dir, "slave_raw_rows", layout["slave_rows"]),
            "canonical_ids": _write_array(raw_dir, "canonical_ids_for_active_rows", layout["canonical_ids"]),
            "owner_ids": _write_array(raw_dir, "canonical_owner_ids", layout["owner_ids"]),
            "phase_codes": _write_array(raw_dir, "phase_codes_for_active_rows", phase_codes),
        },
        "high_layout": {
            "full_rows": int(high_layout["full_rows"]),
            "slave_rows": int(np.asarray(high_layout["slave_rows"]).size),
            "independent_rows": int(high_layout["independent_rows"]),
            "slave_raw_rows": _write_array(
                raw_dir, "high_slave_raw_rows", high_layout["slave_rows"]
            ),
        },
        "fixture_audit": fixture_audit,
        "route_audit": route_audit,
        "production": {
            "high_order_global_aij": bool(
                fixture_audit.get("high_order_global_aij", False)
                or fixture_audit.get("hx_audit", {}).get("high_order_aij", False)
            ),
            "global_dense_transfer": bool(
                fixture_audit.get("global_transfer_matrix", False)
                or fixture_audit.get("hx_audit", {}).get("global_transfer_matrix", False)
            ),
            "numeric_allgather": bool(fixture_audit.get("global_numeric_allgather", False)),
            "resource_gate": "external_foundation_watchdog_required",
        },
        "matrix_artifacts": {"B_L_ind": matrix_artifact},
        "artifacts": artifacts,
        "spectral": spectral,
        "facts": scalar_facts,
        "rank_facts": rank_facts,
        "resource": {
            "scope": "worker_local_diagnostic_not_external_process_tree_gate",
            "external_watchdog_schema": "task038.lor-native-complex-hx.foundation-e-watchdog.v1",
        },
    }


def run_worker(
    raw_dir: Path, record_path: Path, expected_source_sha: str, expected_mpi_size: int
) -> None:
    comm = MPI.COMM_WORLD
    if int(expected_mpi_size) != 1 or comm.size != 1:
        raise ValueError("global spectral audit is frozen to p3-mpi1")
    root = Path(__file__).resolve().parents[1]
    _prepare_paths(raw_dir.resolve(), record_path.resolve(), comm, stage=STAGE)
    _append_stage_marker(raw_dir, "setup", comm.rank)
    source = _source_identity(root, expected_source_sha)
    runtime = _runtime_identity(root, 1)
    _append_stage_marker(raw_dir, "source_runtime_closed", comm.rank)

    fixture = None
    submatrix = None
    operator = None
    source_vec = None
    source_action = None
    source_repeat = None
    try:
        fixture = RealL2PositiveHXFixture(DEGREE, comm, variant=VARIANT)
        fixture_audit = _jsonable(fixture.audit)
        raw_map = fixture._raw_edge_canonical_map()
        raw_to_canonical, raw_phase = _split_raw_edge_canonical_map(raw_map)
        slave_rows = raw_slave_global_rows(
            fixture.lor_edge_space, fixture.lor_edge_floquet.mpc
        )
        owner_ids = np.asarray(fixture.lor_topology.owned_edge_ids, dtype=np.int64)
        full_rows = int(fixture.edge_matrix.getSize()[0])
        layout = build_independent_layout(
            full_rows, slave_rows, raw_to_canonical, owner_ids
        )
        phase_codes = np.asarray(
            [raw_phase[int(row)] for row in layout["active_raw_rows"]], dtype=np.int8
        )
        if phase_codes.size != INDEPENDENT_EDGE_ROWS or np.any(phase_codes != 0):
            raise RuntimeError("active raw edge phase codes are not all zero")
        high_full_rows = int(fixture.high_space.dofmap.index_map.size_global)
        high_matrix_rows = int(fixture.high_action.matrix.getSize()[0])
        high_slave_rows = raw_slave_global_rows(
            fixture.high_space, fixture.high_floquet.mpc
        )
        high_layout = {
            "full_rows": high_full_rows,
            "slave_rows": high_slave_rows,
            "independent_rows": high_full_rows - int(high_slave_rows.size),
        }
        if (full_rows, int(slave_rows.size), int(layout["owner_count"])) != (
            FULL_EDGE_ROWS,
            SLAVE_EDGE_ROWS,
            INDEPENDENT_EDGE_ROWS,
        ):
            raise RuntimeError("p3/h50 owner/slave dimensions do not match the frozen audit")
        if (
            high_full_rows,
            int(high_slave_rows.size),
            int(high_layout["independent_rows"]),
            high_matrix_rows,
        ) != (FULL_EDGE_ROWS, SLAVE_EDGE_ROWS, INDEPENDENT_EDGE_ROWS, FULL_EDGE_ROWS):
            raise RuntimeError("p3/h50 high-space owner/slave dimensions do not match the frozen audit")
        _append_stage_marker(raw_dir, "layout_closed", comm.rank)

        submatrix = create_independent_submatrix(
            fixture.edge_matrix, np.asarray(layout["active_raw_rows"], dtype=np.int64)
        )
        operator, operator_context = build_pulled_high_shell(fixture, layout)
        _append_stage_marker(raw_dir, "operators_built", comm.rank)

        source_vec, source_facts = fixture.build_l2_source(SOURCE_NAME)
        source_before = np.asarray(source_vec.array, dtype=np.complex128).copy()
        source_action = fixture.apply_high_action_copy(source_vec)
        source_repeat = fixture.apply_high_action_copy(source_vec)
        source_after = np.asarray(source_vec.array, dtype=np.complex128).copy()
        for name, values in (
            ("source_before", source_before),
            ("source_after", source_after),
            ("source_action", source_action.array),
            ("source_action_repeat", source_repeat.array),
        ):
            _require_global_size(name, values, high_full_rows)
        _append_stage_marker(raw_dir, "high_action_legality", comm.rank)

        owner_size = int(layout["owner_count"])
        q1 = _deterministic_vector(owner_size, 1)
        q2 = _deterministic_vector(owner_size, 2)
        q_combined = LINEARITY_ALPHA * q1 + LINEARITY_BETA * q2
        aq1, q1_before, q1_after = apply_with_input_snapshot(operator, q1)
        aq1_repeat = _apply_owner(operator, q1)
        aq2, q2_before, q2_after = apply_with_input_snapshot(operator, q2)
        aq_combined, qcombined_before, qcombined_after = apply_with_input_snapshot(operator, q_combined)
        q1 = q1_before
        q2 = q2_before
        q_combined = qcombined_before
        bq1 = _apply_owner(submatrix, q1)
        bq2 = _apply_owner(submatrix, q2)
        bq_combined = _apply_owner(submatrix, q_combined)
        h1_vec = fixture.high_action.matrix.createVecRight()
        h2_vec = fixture.high_action.matrix.createVecRight()
        h1_values = _high_probe(h1_vec.getSize(), 1)
        h2_values = _high_probe(h2_vec.getSize(), 2)
        _require_global_size("work_h1", h1_values, high_full_rows)
        _require_global_size("work_h2", h2_values, high_full_rows)
        h1_vec.array[:] = h1_values
        h2_vec.array[:] = h2_values
        lq1_vec = None
        lq2_vec = None
        try:
            lq1_vec = owner_to_high(fixture, layout, q1)
            lq2_vec = owner_to_high(fixture, layout, q2)
            lq1_values = np.asarray(lq1_vec.array, dtype=np.complex128).copy()
            lq2_values = np.asarray(lq2_vec.array, dtype=np.complex128).copy()
            _require_global_size("work_lq1", lq1_values, high_full_rows)
            _require_global_size("work_lq2", lq2_values, high_full_rows)
            lstar_h1 = high_dual_to_owner(fixture, layout, h1_vec)
            lstar_h2 = high_dual_to_owner(fixture, layout, h2_vec)
            work_q1 = work_identity_relative(lq1_vec.array, h1_vec.array, q1, lstar_h1)
            work_q2 = work_identity_relative(lq2_vec.array, h2_vec.array, q2, lstar_h2)
            route_low_ids, _ = _route_ids(fixture, layout, q1)
            _low_for_route, high_route_packet = low_input_from_high_dual(fixture, h1_vec)
            try:
                route_high_ids = np.asarray(high_route_packet[0], dtype=np.int64)
            finally:
                _low_for_route.destroy()
        finally:
            if lq2_vec is not None:
                lq2_vec.destroy()
            if lq1_vec is not None:
                lq1_vec.destroy()
            h2_vec.destroy()
            h1_vec.destroy()
        initial = operator.createVecRight()
        initial.array[:] = q1 / max(np.linalg.norm(q1), np.finfo(float).tiny)
        try:
            eigenpairs = solve_extreme_generalized_pairs(operator, submatrix, initial)
        finally:
            initial.destroy()
        _append_stage_marker(raw_dir, "spectral_pairs_solved", comm.rank)

        vectors: dict[str, Any] = {
            "source_before": _vector_artifact(raw_dir, "high_source_before", source_before, "high_raw_owned"),
            "source_after": _vector_artifact(raw_dir, "high_source_after", source_after, "high_raw_owned"),
            "source_action": _vector_artifact(raw_dir, "high_source_action", source_action.array, "high_raw_owned"),
            "source_action_repeat": _vector_artifact(raw_dir, "high_source_action_repeat", source_repeat.array, "high_raw_owned"),
            "q1": _vector_artifact(raw_dir, "owner_q1", q1, "independent_raw_active_row"),
            "q1_after": _vector_artifact(raw_dir, "owner_q1_after", q1_after, "independent_raw_active_row"),
            "q2": _vector_artifact(raw_dir, "owner_q2", q2, "independent_raw_active_row"),
            "q2_after": _vector_artifact(raw_dir, "owner_q2_after", q2_after, "independent_raw_active_row"),
            "q_combined": _vector_artifact(raw_dir, "owner_q_combined", q_combined, "independent_raw_active_row"),
            "q_combined_after": _vector_artifact(raw_dir, "owner_q_combined_after", qcombined_after, "independent_raw_active_row"),
            "A_q1": _vector_artifact(raw_dir, "A_pull_q1", aq1, "independent_raw_active_row"),
            "A_q1_repeat": _vector_artifact(raw_dir, "A_pull_q1_repeat", aq1_repeat, "independent_raw_active_row"),
            "A_q2": _vector_artifact(raw_dir, "A_pull_q2", aq2, "independent_raw_active_row"),
            "A_q_combined": _vector_artifact(raw_dir, "A_pull_q_combined", aq_combined, "independent_raw_active_row"),
            "B_q1": _vector_artifact(raw_dir, "B_L_ind_q1", bq1, "independent_raw_active_row"),
            "B_q2": _vector_artifact(raw_dir, "B_L_ind_q2", bq2, "independent_raw_active_row"),
            "B_q_combined": _vector_artifact(raw_dir, "B_L_ind_q_combined", bq_combined, "independent_raw_active_row"),
            "work_h1": _vector_artifact(raw_dir, "work_h1_high", h1_values, "high_raw_owned"),
            "work_h2": _vector_artifact(raw_dir, "work_h2_high", h2_values, "high_raw_owned"),
            "work_lq1": _vector_artifact(raw_dir, "work_lq1_high", lq1_values, "high_raw_owned"),
            "work_lq2": _vector_artifact(raw_dir, "work_lq2_high", lq2_values, "high_raw_owned"),
            "work_lstar_h1": _vector_artifact(raw_dir, "work_lstar_h1_owner", lstar_h1, "independent_raw_active_row"),
            "work_lstar_h2": _vector_artifact(raw_dir, "work_lstar_h2_owner", lstar_h2, "independent_raw_active_row"),
            "route_low_ids": _vector_artifact(raw_dir, "route_low_owner_ids", route_low_ids, "independent_raw_active_row"),
            "route_high_ids": _vector_artifact(raw_dir, "route_high_owner_ids", route_high_ids, "independent_raw_active_row"),
        }
        spectral_facts: dict[str, Any] = {}
        for name, pair in eigenpairs.items():
            spectral_facts[name] = {
                key: value
                for key, value in pair.items()
                if key not in {"vector", "action", "mass_action"}
            }
            vectors[f"eigen_{name}_q"] = _vector_artifact(raw_dir, f"eigen_{name}_q", pair["vector"], "independent_raw_active_row")
            vectors[f"eigen_{name}_Aq"] = _vector_artifact(raw_dir, f"eigen_{name}_Aq", pair["action"], "independent_raw_active_row")
            vectors[f"eigen_{name}_Bq"] = _vector_artifact(raw_dir, f"eigen_{name}_Bq", pair["mass_action"], "independent_raw_active_row")
        spectral_facts["tested_dimension"] = INDEPENDENT_EDGE_ROWS
        matrix_artifact = _matrix_artifact(raw_dir, submatrix, layout["active_raw_rows"])
        route_audit = {
            "owner_inventory_equal": bool(np.array_equal(np.sort(route_low_ids), np.sort(layout["owner_ids"]))),
            "high_to_lor_owner_route": bool(np.array_equal(np.sort(route_high_ids), np.sort(layout["owner_ids"]))),
            "lor_to_high_owner_route": bool(np.array_equal(np.sort(route_low_ids), np.sort(layout["owner_ids"]))),
            "owner_count": owner_size,
            "owner_ids_unique": bool(np.unique(layout["owner_ids"]).size == owner_size),
            "canonical_owner_bijection": bool(layout["bijection"]),
            "orientation_consistent": bool(fixture_audit.get("raw_edge_orientation_consistent", False)),
            "phase_application": fixture_audit.get("phase_application"),
            "slave_master_complete": bool(fixture_audit.get("slave_master_complete", False)),
        }
        scalar_facts = {
            "source_formula": source_facts.get("formula"),
            "source_unchanged_relative": float(np.linalg.norm(source_after - source_before) / max(np.linalg.norm(source_before), np.finfo(float).tiny)),
            "high_action_repeat_relative": float(np.linalg.norm(source_action.array - source_repeat.array) / max(np.linalg.norm(source_action.array), np.finfo(float).tiny)),
            "A_linearity_relative": float(
                np.linalg.norm(
                    aq_combined
                    - LINEARITY_ALPHA * aq1
                    - LINEARITY_BETA * aq2
                )
                / max(
                    np.linalg.norm(
                        LINEARITY_ALPHA * aq1 + LINEARITY_BETA * aq2
                    ),
                    np.finfo(float).tiny,
                )
            ),
            "A_repeat_relative": float(np.linalg.norm(aq1 - aq1_repeat) / max(np.linalg.norm(aq1), np.finfo(float).tiny)),
            "A_input_unchanged": bool(np.array_equal(q1, q1_after) and np.array_equal(q2, q2_after) and np.array_equal(q_combined, qcombined_after)),
            "work_q1_relative": float(work_q1),
            "work_q2_relative": float(work_q2),
            "A_hermitian_probe_relative": float(abs(np.vdot(q1, aq2) - np.vdot(aq1, q2)) / max(abs(np.vdot(q1, aq2)), abs(np.vdot(aq1, q2)), np.finfo(float).tiny)),
            "B_hermitian_probe_relative": float(abs(np.vdot(q1, bq2) - np.vdot(bq1, q2)) / max(abs(np.vdot(q1, bq2)), abs(np.vdot(bq1, q2)), np.finfo(float).tiny)),
            "operator_apply_count": int(operator_context.apply_count),
            "high_action_finite": bool(np.all(np.isfinite(source_action.array)) and np.all(np.isfinite(source_repeat.array))),
            "local_spectral_condition_reference": 10.740847884857926,
        }
        provenance = {
            "input_identity_sha256": _identity_sha({"degree": DEGREE, "h_nm": H_NM, "source": SOURCE_NAME, "formula": source_facts.get("formula")}),
            "operator_identity_sha256": _identity_sha({"operator": "positive_B_H_and_B_L_ind", "degree": DEGREE, "h_nm": H_NM, "variant": VARIANT}),
            "physical_model_sha256": _identity_sha({"model": "positive_piecewise_auxiliary", "degree": DEGREE, "h_nm": H_NM, "tags": "air_substrate_grating"}),
        }
        rank_fact = {
            "rank": 0,
            "runtime": runtime,
            "owner_count": owner_size,
            "full_rows": full_rows,
            "slave_rows": int(slave_rows.size),
            "matrix_rows": int(submatrix.getSize()[0]),
            "operator_apply_count": int(operator_context.apply_count),
        }
        command = [
            str(Path(sys.executable).absolute()), "-m", "benchmarks.run_task038_full3d_lor_spectral_audit",
            "--stage", STAGE, "--case", CASE, "--raw-dir", str(raw_dir.resolve()),
            "--record", str(record_path.resolve()), "--expected-source-sha", expected_source_sha,
            "--expected-mpi-size", "1",
        ]
        def build_record(rank_facts: list[dict[str, Any]]) -> dict[str, Any]:
            return _build_record(
                raw_dir, record_path, source, runtime, rank_facts, vectors, matrix_artifact,
                layout, phase_codes, high_layout, fixture_audit, provenance, route_audit,
                spectral_facts, scalar_facts, command,
            )
        _append_stage_marker(raw_dir, "raw_artifacts_written", comm.rank)
        _closeout_record(comm, raw_dir, record_path, rank_fact, build_record)
        if comm.rank == 0:
            print(json.dumps({"record": str(record_path.resolve()), "schema": SCHEMA}, sort_keys=True), flush=True)
    finally:
        if source_repeat is not None:
            source_repeat.destroy()
        if source_action is not None:
            source_action.destroy()
        if source_vec is not None:
            source_vec.destroy()
        if operator is not None:
            operator.destroy()
        if submatrix is not None:
            submatrix.destroy()
        if fixture is not None:
            fixture.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    run_worker(args.raw_dir, args.record, args.expected_source_sha, args.expected_mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
