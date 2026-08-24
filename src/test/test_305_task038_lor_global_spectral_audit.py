"""Focused tests for the owner-space global LOR spectral audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import task038_full3d_lor_spectral_audit_checker as checker
from src.solvers.fullspace_lor_spectral_audit import (
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
    INDEPENDENT_EDGE_ROWS,
    LINEARITY_ALPHA,
    LINEARITY_BETA,
    SLAVE_EDGE_ROWS,
    SPECTRAL_CONDITION_LIMIT,
    build_independent_layout,
    csr_matvec,
    solve_extreme_generalized_pairs,
    work_identity_relative,
)
from benchmarks.run_task038_full3d_lor_spectral_audit import _split_raw_edge_canonical_map


def _descriptor(path: Path, values: np.ndarray) -> dict[str, object]:
    values = np.asarray(values)
    np.save(path, values, allow_pickle=False)
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _vector(raw: Path, name: str, values: np.ndarray, coordinate: str) -> dict[str, object]:
    return {"coordinate": coordinate, "values": _descriptor(raw / f"{name}.npy", values)}


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path, str, Path]:
    outer = tmp_path / "outer"
    raw = outer / "raw"
    raw.mkdir(parents=True)
    record_path = outer / "record.json"
    source_sha = "a" * 40
    n = INDEPENDENT_EDGE_ROWS
    active = np.arange(n, dtype=np.int64)
    slave = np.arange(n, FULL_EDGE_ROWS, dtype=np.int64)
    owners = np.asarray([1000 + 3 * index for index in range(n)], dtype=np.int64)
    q1 = np.linspace(1.0, 2.0, n).astype(np.complex128) + 0.2j
    q2 = np.linspace(-1.0, 0.5, n).astype(np.complex128) + 0.4j
    high = np.linspace(0.2, 1.1, FULL_EDGE_ROWS).astype(np.complex128) + 0.3j
    work1 = np.concatenate((q1, np.zeros(SLAVE_EDGE_ROWS, dtype=np.complex128)))
    work2 = np.concatenate((q2, np.zeros(SLAVE_EDGE_ROWS, dtype=np.complex128)))
    qc = LINEARITY_ALPHA * q1 + LINEARITY_BETA * q2
    a1, a2, ac = 2 * q1, 2 * q2, 2 * qc
    indptr = np.arange(n + 1, dtype=np.int64)
    indices = np.arange(n, dtype=np.int64)
    values = np.ones(n, dtype=np.complex128)
    artifacts = {
        "source_before": _vector(raw, "source_before", high, "high_raw_owned"),
        "source_after": _vector(raw, "source_after", high, "high_raw_owned"),
        "source_action": _vector(raw, "source_action", 2 * high, "high_raw_owned"),
        "source_action_repeat": _vector(raw, "source_action_repeat", 2 * high, "high_raw_owned"),
        "q1": _vector(raw, "q1", q1, "independent_raw_active_row"),
        "q1_after": _vector(raw, "q1_after", q1, "independent_raw_active_row"),
        "q2": _vector(raw, "q2", q2, "independent_raw_active_row"),
        "q2_after": _vector(raw, "q2_after", q2, "independent_raw_active_row"),
        "q_combined": _vector(raw, "q_combined", qc, "independent_raw_active_row"),
        "q_combined_after": _vector(raw, "q_combined_after", qc, "independent_raw_active_row"),
        "A_q1": _vector(raw, "A_q1", a1, "independent_raw_active_row"),
        "A_q1_repeat": _vector(raw, "A_q1_repeat", a1, "independent_raw_active_row"),
        "A_q2": _vector(raw, "A_q2", a2, "independent_raw_active_row"),
        "A_q_combined": _vector(raw, "A_q_combined", ac, "independent_raw_active_row"),
        "B_q1": _vector(raw, "B_q1", q1, "independent_raw_active_row"),
        "B_q2": _vector(raw, "B_q2", q2, "independent_raw_active_row"),
        "B_q_combined": _vector(raw, "B_q_combined", qc, "independent_raw_active_row"),
        "work_h1": _vector(raw, "work_h1", work1, "high_raw_owned"),
        "work_h2": _vector(raw, "work_h2", work2, "high_raw_owned"),
        "work_lq1": _vector(raw, "work_lq1", work1, "high_raw_owned"),
        "work_lq2": _vector(raw, "work_lq2", work2, "high_raw_owned"),
        "work_lstar_h1": _vector(raw, "work_lstar_h1", q1, "independent_raw_active_row"),
        "work_lstar_h2": _vector(raw, "work_lstar_h2", q2, "independent_raw_active_row"),
        "route_low_ids": _vector(raw, "route_low_ids", owners, "canonical_owner_id"),
        "route_high_ids": _vector(raw, "route_high_ids", owners, "canonical_owner_id"),
    }
    for name in ("smallest", "largest"):
        artifacts[f"eigen_{name}_q"] = _vector(raw, f"eigen_{name}_q", q1, "independent_raw_active_row")
        artifacts[f"eigen_{name}_Aq"] = _vector(raw, f"eigen_{name}_Aq", 2 * q1, "independent_raw_active_row")
        artifacts[f"eigen_{name}_Bq"] = _vector(raw, f"eigen_{name}_Bq", q1, "independent_raw_active_row")
    matrix = {
        "rows": n,
        "cols": n,
        "type": "aij",
        "nnz": n,
        "numeric_bytes": values.nbytes,
        "index_bytes": indptr.nbytes + indices.nbytes,
        "indptr": _descriptor(raw / "indptr.npy", indptr),
        "indices": _descriptor(raw / "indices.npy", indices),
        "values": _descriptor(raw / "values.npy", values),
        "row_keys": _descriptor(raw / "row_keys.npy", active),
    }
    fixture_audit = {
        "lor_full_edge_rows": FULL_EDGE_ROWS,
        "lor_edge_slave_rows": SLAVE_EDGE_ROWS,
        "high_space_global_rows": FULL_EDGE_ROWS,
        "high_order_global_aij": False,
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "slave_master_complete": True,
        "phase_application": "finalized_floquet_mpc_once",
        "hx_audit": {"high_order_aij": False, "global_transfer_matrix": False},
    }
    record = {
        "schema": checker.SCHEMA,
        "stage": checker.STAGE,
        "case": checker.CASE,
        "degree": 3,
        "h_nm": 50.0,
        "source_name": "random",
        "variant": "sequential-v1",
        "mpi_size": 1,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": [
            "/usr/bin/python3", "-m", "benchmarks.run_task038_full3d_lor_spectral_audit",
            "--stage", checker.STAGE, "--case", checker.CASE, "--raw-dir", str(raw.resolve()),
            "--record", str(record_path.resolve()), "--expected-source-sha", source_sha,
            "--expected-mpi-size", "1",
        ],
        "source": {"expected_sha": source_sha, "branch": checker.BRANCH, "clean_start": True, "clean_end": True},
        "runtime": {"qualified_activation": "1", "mpi_size": 1, "petsc_scalar_type": "complex128", "petsc_int_type": "int32", "threads": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}},
        "provenance": {"input_identity_sha256": "1" * 64, "operator_identity_sha256": "2" * 64, "physical_model_sha256": "3" * 64},
        "settings": {"owner_coordinate": "increasing_raw_active_edge_row", "full_edge_rows": FULL_EDGE_ROWS, "slave_edge_rows": SLAVE_EDGE_ROWS, "independent_edge_rows": INDEPENDENT_EDGE_ROWS, "linearity_alpha": [float(LINEARITY_ALPHA.real), float(LINEARITY_ALPHA.imag)], "linearity_beta": [float(LINEARITY_BETA.real), float(LINEARITY_BETA.imag)], "slepc_problem_type": "GHEP", "slepc_type": "KRYLOVSCHUR", "slepc_nev": EPS_NEV, "slepc_ncv": EPS_NCV, "slepc_tol": EPS_TOL, "slepc_max_it": EPS_MAX_IT, "slepc_st_type": EPS_ST_TYPE, "slepc_shift": EPS_SHIFT, "slepc_ksp_type": EPS_KSP_TYPE, "slepc_pc_type": EPS_PC_TYPE, "slepc_factor_solver": EPS_FACTOR_SOLVER, "spectral_condition_limit": SPECTRAL_CONDITION_LIMIT, "work_limit": 1e-12, "linearity_limit": 1e-12, "repeat_limit": 1e-13, "eigen_residual_limit": 1e-10},
        "layout": {"full_rows": FULL_EDGE_ROWS, "slave_rows": SLAVE_EDGE_ROWS, "owner_count": n, "bijection": True, "active_raw_rows": _descriptor(raw / "active.npy", active), "slave_raw_rows": _descriptor(raw / "slave.npy", slave), "canonical_ids": _descriptor(raw / "canonical.npy", owners), "owner_ids": _descriptor(raw / "owners.npy", owners), "phase_codes": _descriptor(raw / "phase.npy", np.zeros(n, dtype=np.int8))},
        "high_layout": {"full_rows": FULL_EDGE_ROWS, "slave_rows": SLAVE_EDGE_ROWS, "independent_rows": INDEPENDENT_EDGE_ROWS, "slave_raw_rows": _descriptor(raw / "high_slave.npy", slave)},
        "fixture_audit": fixture_audit,
        "route_audit": {"owner_inventory_equal": True, "high_to_lor_owner_route": True, "lor_to_high_owner_route": True, "owner_count": n, "owner_ids_unique": True, "canonical_owner_bijection": True, "orientation_consistent": True, "phase_application": "finalized_floquet_mpc_once", "slave_master_complete": True},
        "production": {"high_order_global_aij": False, "global_dense_transfer": False, "numeric_allgather": False, "resource_gate": "external_foundation_watchdog_required"},
        "matrix_artifacts": {"B_L_ind": matrix},
        "artifacts": artifacts,
        "spectral": {"tested_dimension": INDEPENDENT_EDGE_ROWS, "smallest": {"eigenvalue": 2.0, "imaginary_part": 0.0, "residual_relative": 0.0, "reason": 1, "iterations": 2}, "largest": {"eigenvalue": 2.0, "imaginary_part": 0.0, "residual_relative": 0.0, "reason": 1, "iterations": 2}},
        "facts": {},
        "rank_facts": [{"rank": 0, "owner_count": n, "full_rows": FULL_EDGE_ROWS, "slave_rows": SLAVE_EDGE_ROWS}],
        "resource": {"scope": "synthetic"},
    }
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    watchdog_raw = outer / "watchdog.raw.jsonl"
    sample = {
        "authority": {
            "process_tree": {"all_status_readable": True, "rss_bytes": 1000, "swap_bytes": 0},
            "job_cgroup": {"dedicated_job_cgroup": False},
        }
    }
    watchdog_raw.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    watchdog = outer / "watchdog.json"
    watchdog.write_text(
        json.dumps(
            {
                "schema": checker.WATCHDOG_SCHEMA,
                "source_sha": source_sha,
                "worker_command": record["command"],
                "worker_raw_dir": str(raw.resolve()),
                "worker_record": str(record_path.resolve()),
                "watchdog_raw": str(watchdog_raw.resolve()),
                "returncode": 0,
                "natural_exit": True,
                "no_orphan": True,
                "stop_reason": "natural_exit",
                "sample_count": 1,
                "all_status_readable": True,
                "peak_process_tree_rss_bytes": 1000,
                "max_process_tree_swap_bytes": 0,
                "watchdog_poll_seconds": checker.WATCHDOG_POLL_SECONDS,
                "watchdog_rss_limit_bytes": checker.WATCHDOG_RSS_LIMIT,
                "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return record_path, raw, source_sha, watchdog


def test_owner_layout_does_not_assume_contiguous_canonical_ids() -> None:
    layout = build_independent_layout(4, np.asarray([1]), {0: 100, 2: 2, 3: 10}, np.asarray([2, 10, 100]))
    assert layout["owner_count"] == 3
    np.testing.assert_array_equal(layout["active_raw_rows"], [0, 2, 3])
    np.testing.assert_array_equal(layout["canonical_ids"], [100, 2, 10])


def test_raw_canonical_map_splits_tuple_identity_and_phase() -> None:
    from benchmarks.run_task038_full3d_lor_spectral_audit import _split_raw_edge_canonical_map

    canonical, phase = _split_raw_edge_canonical_map({2: (101, 0), 10: (202, 0)})
    assert canonical == {2: 101, 10: 202}
    assert phase == {2: 0, 10: 0}


def test_work_identity_uses_nonzero_complex_probes() -> None:
    q = np.asarray([1.0 + 2.0j, -0.5 + 0.25j])
    h = np.asarray([0.7 - 0.2j, 1.2 + 0.3j])
    assert work_identity_relative(q, h, q, h) == 0.0
    assert work_identity_relative(q, h, q, h * 1.0001) > 1.0e-5


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="fixed two-by-two local SLEPc ownership test")
def test_slepc_ghep_krylovschur_shell_a_sparse_b() -> None:
    class Shell:
        def __init__(self) -> None:
            self.array = np.asarray([[4.0, 1.0], [1.0, 3.0]], dtype=np.complex128)
            self.matrix = PETSc.Mat().createPython(((2, 2), (2, 2)), context=self, comm=MPI.COMM_WORLD)
            self.matrix.setUp()

        def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
            target.array[:] = self.array @ source.array

    shell = Shell()
    mass = PETSc.Mat().createAIJ(((2, 2), (2, 2)), comm=MPI.COMM_WORLD)
    mass.setUp()
    mass.setValues([0, 1], [0, 1], [[2.0, 0.0], [0.0, 1.0]])
    mass.assemble()
    initial = shell.matrix.createVecRight()
    initial.array[:] = [1.0 + 0.25j, -0.5 + 0.1j]
    try:
        pairs = solve_extreme_generalized_pairs(shell.matrix, mass, initial)
        assert pairs["smallest"]["eigenvalue"] > 0.0
        assert pairs["largest"]["eigenvalue"] >= pairs["smallest"]["eigenvalue"]
        assert pairs["smallest"]["residual_relative"] <= 1.0e-10
        assert pairs["largest"]["residual_relative"] <= 1.0e-10
    finally:
        initial.destroy()
        mass.destroy()
        shell.matrix.destroy()


def test_checker_accepts_owner_space_record_and_rejects_tampering(tmp_path: Path) -> None:
    record_path, raw, source_sha, watchdog = _synthetic_record(tmp_path)
    result = checker.check_record(record_path, watchdog, source_sha)
    assert result["passed"] is True, result
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "A_q_expected" not in record["artifacts"]
    assert result["metrics"]["numerical_rank"] == INDEPENDENT_EDGE_ROWS
    assert result["resource_metrics"]["sample_count"] == 1
    q1_path = raw / "q1.npy"
    q1 = np.load(q1_path, allow_pickle=False)
    q1[0] += 1.0
    np.save(q1_path, q1, allow_pickle=False)
    mutated = checker.check_record(record_path, watchdog, source_sha)
    assert mutated["passed"] is False
    assert mutated["contract_errors"]
    assert mutated["metrics"]["numerical_rank"] is None


def test_checker_does_not_derive_rank_after_eigen_gate_failure(tmp_path: Path) -> None:
    record_path, raw, source_sha, watchdog = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    bad_aq_path = raw / "eigen_smallest_Aq.npy"
    np.save(bad_aq_path, np.zeros(INDEPENDENT_EDGE_ROWS, dtype=np.complex128), allow_pickle=False)
    descriptor = record["artifacts"]["eigen_smallest_Aq"]["values"]
    descriptor["bytes"] = bad_aq_path.stat().st_size
    descriptor["sha256"] = hashlib.sha256(bad_aq_path.read_bytes()).hexdigest()
    record["spectral"]["smallest"]["residual_relative"] = 1.0
    bad_path = record_path.with_name("bad_spectral.json")
    bad_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(bad_path, watchdog, source_sha)
    assert result["passed"] is False
    assert result["metrics"]["numerical_rank"] is None
    assert any("eigen_smallest residual" in item for item in result["gate_failures"])


def test_checker_missing_role_fails_closed(tmp_path: Path) -> None:
    record_path, _raw, source_sha, watchdog = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["artifacts"]["work_h1"]
    record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, source_sha)
    assert result["passed"] is False
    assert any("artifact role set mismatch" in item for item in result["contract_errors"])


def test_fixed_settings_and_no_reference_n_in_source() -> None:
    from benchmarks import run_task038_full3d_lor_spectral_audit as runner

    assert runner.DEGREE == 3
    assert runner.CASE == "p3-mpi1"
    assert "reference_n" not in runner.__dict__
    assert "createAIJ" not in Path(runner.__file__).read_text(encoding="utf-8")


def test_checker_csr_matvec_is_independent() -> None:
    result = csr_matvec(np.asarray([0, 2, 3]), np.asarray([0, 1, 1]), np.asarray([2, 1, 4j]), np.asarray([1, 2j]))
    np.testing.assert_allclose(result, [2 + 2j, -8])
