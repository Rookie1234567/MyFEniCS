"""Focused pure checks for the V11 S0/S1 audit harness."""

from __future__ import annotations

import ast
import hashlib
import json
import inspect
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks import task038_full3d_lor_spectral_audit_v2_checker as checker
from benchmarks import run_task038_full3d_lor_spectral_audit_v2 as runner
from benchmarks.run_task038_full3d_lor_spectral_audit_v2 import (
    BATCH_SCHEMA,
    _prepare_paths,
)
from src.solvers.fullspace_lor_global_audit import (
    EIGEN_DRIVER,
    EIGEN_LIBRARY,
    EIGEN_METHOD,
    EIGEN_SELECTION,
    H_NM,
    _high_matrix_free_action,
    _independent_csr,
    _route_pull_action,
    build_sparse_transfer,
    build_owner_layout,
    csr_matvec,
    csr_adjoint_left_product,
    csr_right_product,
    csr_to_dense,
    generalized_endpoints,
    global_slave_rows,
    petsc_csr,
)


def _descriptor(path: Path, values: np.ndarray) -> dict[str, object]:
    values = np.asarray(values)
    np.save(path, values, allow_pickle=False)
    return {
        "relative_path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _csr(raw: Path, name: str, matrix: np.ndarray) -> dict[str, object]:
    matrix = np.asarray(matrix, dtype=np.complex128)
    rows, cols = matrix.shape
    indptr = [0]
    indices: list[int] = []
    values: list[complex] = []
    for row in matrix:
        for col, value in enumerate(row):
            if value != 0:
                indices.append(col)
                values.append(complex(value))
        indptr.append(len(values))
    indptr_array = np.asarray(indptr, dtype=np.int64)
    indices_array = np.asarray(indices, dtype=np.int64)
    values_array = np.asarray(values, dtype=np.complex128)
    return {
        "rows": rows,
        "cols": cols,
        "nnz": len(values),
        "index_bytes": indptr_array.nbytes + indices_array.nbytes,
        "numeric_bytes": values_array.nbytes,
        "indptr": _descriptor(raw / f"{name}_indptr.npy", indptr_array),
        "indices": _descriptor(raw / f"{name}_indices.npy", indices_array),
        "values": _descriptor(raw / f"{name}_values.npy", values_array),
    }


def _vectors(raw: Path, prefix: str, values: np.ndarray) -> list[dict[str, object]]:
    return [_descriptor(raw / f"{prefix}_{i}.npy", row) for i, row in enumerate(values)]


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path, str, Path]:
    campaign = tmp_path / "benchmarks" / "artifacts" / "campaign" / "p2-mpi1"
    raw = campaign / "raw"
    raw.mkdir(parents=True)
    record_path = tmp_path / "docs" / "record.json"
    record_path.parent.mkdir(parents=True)
    source_sha = "a" * 40
    bh_full = np.diag([4.0, 9.0, 1.0]).astype(np.complex128)
    bl_full = np.diag([2.0, 3.0, 1.0]).astype(np.complex128)
    bh_ind = bh_full[:2, :2]
    bl_ind = bl_full[:2, :2]
    transfer = np.eye(2, dtype=np.complex128)
    spectral = generalized_endpoints(bh_ind, bl_ind)
    high_probes = np.asarray(
        [[1.0 + 0.3j, -0.5 + 0.1j, 0.0j], [0.2 - 0.4j, 0.7 + 0.2j, 0.0j]],
        dtype=np.complex128,
    )
    high_expected = high_probes @ bh_full.T
    low_probes = np.asarray(
        [[1.0 + 0.3j, -0.5 + 0.1j], [0.2 - 0.4j, 0.7 + 0.2j]],
        dtype=np.complex128,
    )
    pull_expected = low_probes @ bh_ind.T
    work_payload = {
        "work_0_high_primal": np.asarray([1.0 + 0.3j, -0.5 + 0.1j, 0.0j]),
        "work_0_high_dual": np.asarray([0.2 - 0.4j, 0.7 + 0.2j, 0.0j]),
        "work_0_owner_primal": low_probes[0],
        "work_0_owner_dual": np.asarray([0.2 - 0.4j, 0.7 + 0.2j]),
    }
    artifacts: dict[str, object] = {
        "singular_values": _descriptor(raw / "singular_values.npy", np.ones(2, dtype=np.float64)),
        "low_probes": _vectors(raw, "low_probe", low_probes),
        "high_probes": _vectors(raw, "high_probe", high_probes),
        "high_action_expected": _vectors(raw, "high_expected", high_expected),
        "high_action_observed": _vectors(raw, "high_observed", high_expected),
        "pull_expected": _vectors(raw, "pull_expected", pull_expected),
        "pull_observed": _vectors(raw, "pull_observed", pull_expected),
    }
    for name, values in work_payload.items():
        artifacts[name] = _descriptor(raw / f"{name}.npy", values)
    layout_low = np.asarray([0, 1], dtype=np.int64)
    layout_high = np.asarray([0, 1], dtype=np.int64)
    layout = {
        "low": {
            "low_active_raw_rows": _descriptor(raw / "low_active.npy", layout_low),
            "low_slave_raw_rows": _descriptor(raw / "low_slave.npy", np.asarray([2], dtype=np.int64)),
            "low_canonical_owner_ids": _descriptor(raw / "low_canonical.npy", np.asarray([2, 10], dtype=np.int64)),
            "low_topology_owner_ids": _descriptor(raw / "low_topology_owner.npy", np.asarray([2, 10], dtype=np.int64)),
            "low_phase_codes": _descriptor(raw / "low_phase.npy", np.zeros(2, dtype=np.int8)),
        },
        "high": {
            "high_active_raw_rows": _descriptor(raw / "high_active.npy", layout_high),
            "high_slave_raw_rows": _descriptor(raw / "high_slave.npy", np.asarray([2], dtype=np.int64)),
            "high_topology_owner_ids": _descriptor(raw / "high_topology_owner.npy", np.asarray([100, 200], dtype=np.int64)),
        },
        "tested_dimension": 2,
        "numerical_rank": 2,
        "rank_tau": 2 * np.finfo(float).eps,
        "low_owner_authority": "lor_raw_topology.owned_edge_ids",
        "high_owner_authority": "lor_topology.owned_edge_ids",
        "low_bijection": True,
        "high_active_slave_partition": True,
        "independent_dimension_closed": True,
    }
    command = [
        "/usr/bin/python3",
        "-m",
        "benchmarks.run_task038_full3d_lor_spectral_audit_v2",
        "--stage",
        "s1",
        "--case",
        "p2-mpi1",
        "--source-name",
        "random",
        "--raw-dir",
        str(raw.resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        source_sha,
        "--expected-mpi-size",
        "1",
    ]
    record = {
        "schema": checker.SCHEMA,
        "stage": checker.STAGE,
        "case": "p2-mpi1",
        "degree": 2,
        "h_nm": H_NM,
        "source_name": "random",
        "mpi_size": 1,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": {"expected_sha": source_sha, "commit_sha_start": source_sha, "commit_sha_end": source_sha, "branch": checker.BRANCH, "clean_start": True, "clean_end": True},
        "runtime": {"qualified_activation": "1", "mpi_size": 1, "petsc_scalar_type": "complex128", "petsc_int_type": "int32", "threads": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}},
        "settings": {"rank_tolerance": checker.RANK_TOLERANCE, "eigen_method": EIGEN_METHOD, "eigen_library": EIGEN_LIBRARY, "eigen_driver": EIGEN_DRIVER, "eigen_selection": EIGEN_SELECTION, "rank_method": checker.RANK_METHOD, "condition_policy": "report_only_no_cap", "eigen_residual_limit": checker.EIGEN_RESIDUAL_LIMIT},
        "layout": layout,
        "matrix_artifacts": {"B_L_full": _csr(raw, "bl_full", bl_full), "B_H_full": _csr(raw, "bh_full", bh_full), "B_L_ind": _csr(raw, "bl_ind", bl_ind), "B_H_ind": _csr(raw, "bh_ind", bh_ind), "L": _csr(raw, "transfer", transfer)},
        "artifacts": artifacts,
        "spectral": {name: {key: value for key, value in item.items() if key not in {"vector", "Aq", "Bq"}} | {key: _descriptor(raw / f"eigen_{name}_{key}.npy", item[key]) for key in ("vector", "Aq", "Bq")} for name, item in spectral.items() if name in {"smallest", "largest"}},
        "fixture_audit": {"fixture_build_hx": False, "fixture_hx_constructed": False, "high_order_global_aij": False, "global_transfer_matrix": False, "global_numeric_allgather": False, "phase_application": "finalized_floquet_mpc_once", "slave_master_complete": True, "raw_edge_orientation_consistent": True, "raw_edge_orientation_owned_rows_closed": True, "raw_edge_orientation_factor_count": 4, "raw_edge_orientation_plus_count": 4, "raw_edge_orientation_minus_count": 0},
        "fixture_hx_audit": {"constructed": False},
        "audit_assembly": {"high_order_global_aij": True, "sparse_independent_transfer": True, "temporary_dense_transfer_for_rank_svd": True, "production_global_dense_transfer": False, "numeric_allgather": False},
        "forbidden": {"production_high_order_global_aij": False, "production_global_transfer_matrix": False, "production_numeric_allgather": False, "scalar_node_matrix_constructed": False, "native_hx_constructed": False},
        "markers": {},
    }
    record["facts"] = {
        "spd": {"B_L": {"positive_definite": True}, "A_pull": {"positive_definite": True}},
        "spectral_status": "solved",
    }
    marker_path = raw / "stage-rank0.jsonl"
    marker_path.write_text(
        "\n".join(json.dumps({"stage": name}) for name in ("paths_ready", "source_runtime_closed", "fixture_built", "layout_closed", "matrices_built", "actions_checked", "rank_spd_checked", "endpoints_solved", "record_written")) + "\n",
        encoding="utf-8",
    )
    record["markers"] = {
        "relative_path": marker_path.name,
        "sha256": hashlib.sha256(marker_path.read_bytes()).hexdigest(),
        "bytes": marker_path.stat().st_size,
        "lines": 9,
    }
    record_path.write_text(json.dumps(record, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    watchdog_dir = tmp_path / "watchdog"
    watchdog_dir.mkdir()
    watchdog_raw = watchdog_dir / "watchdog.raw.jsonl"
    watchdog_sample = {"authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 1234, "swap_bytes": 0}, "job_cgroup": {"dedicated_job_cgroup": False}}}
    watchdog_raw.write_text(json.dumps(watchdog_sample) + "\n", encoding="utf-8")
    watchdog = watchdog_dir / "watchdog.json"
    watchdog.write_text(json.dumps({
        "schema": checker.WATCHDOG_SCHEMA,
        "source_sha": source_sha,
        "worker_command": command,
        "worker_raw_dir": str(raw.resolve()),
        "worker_record": str(record_path.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
        "stop_reason": "natural_exit",
        "sample_count": 1,
        "all_status_readable": True,
        "peak_process_tree_rss_bytes": 1234,
        "max_process_tree_swap_bytes": 0,
        "watchdog_poll_seconds": 0.25,
        "watchdog_rss_limit_bytes": 2_000_000_000,
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
    }, sort_keys=True) + "\n", encoding="utf-8")
    return record_path, raw, source_sha, watchdog


def test_owner_bijection_accepts_noncontiguous_ids_and_phase_is_explicit() -> None:
    layout = build_owner_layout(4, np.asarray([1]), {0: (100, 0), 2: (2, 0), 3: (10, 0)}, np.asarray([2, 10, 100]))
    np.testing.assert_array_equal(layout["active_raw_rows"], [0, 2, 3])
    np.testing.assert_array_equal(layout["canonical_ids"], [100, 2, 10])
    np.testing.assert_array_equal(layout["phase_codes"], [0, 0, 0])


def test_fixed_complex_lapack_generalized_endpoints() -> None:
    result = generalized_endpoints(np.diag([4.0, 9.0]), np.diag([2.0, 3.0]))
    assert EIGEN_DRIVER == "gvx"
    assert np.isclose(result["lambda_min"], 2.0)
    assert np.isclose(result["lambda_max"], 3.0)
    assert result["smallest"]["residual_relative"] <= checker.EIGEN_RESIDUAL_LIMIT
    assert result["largest"]["residual_relative"] <= checker.EIGEN_RESIDUAL_LIMIT


def test_explicit_csr_action_and_no_old_slepc_or_condition_cap() -> None:
    result = csr_matvec(np.asarray([0, 2, 3]), np.asarray([0, 1, 1]), np.asarray([2.0, 1.0, 4.0j]), np.asarray([1.0, 2.0j]))
    np.testing.assert_allclose(result, [2.0 + 2.0j, -8.0])
    core_text = Path("src/solvers/fullspace_lor_global_audit.py").read_text(encoding="utf-8")
    runner_text = Path("benchmarks/run_task038_full3d_lor_spectral_audit_v2.py").read_text(encoding="utf-8")
    assert "SPECTRAL_CONDITION_LIMIT" not in core_text + runner_text
    assert "slepc4py" not in core_text + runner_text
    assert "svdvals" in core_text
    assert "csr_gram" not in core_text
    assert "NativeComplexLORHX" not in runner_text
    assert "build_hx=False" in runner_text


def test_new_python_files_have_no_duplicate_literal_dict_keys() -> None:
    paths = (
        Path("src/solvers/fullspace_lor_global_audit.py"),
        Path("benchmarks/run_task038_full3d_lor_spectral_audit_v2.py"),
        Path("benchmarks/task038_full3d_lor_spectral_audit_v2_checker.py"),
        Path(__file__),
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [
                item.value
                for item in node.keys
                if isinstance(item, ast.Constant)
            ]
            assert len(keys) == len(set(keys)), f"duplicate literal key in {path}"


def test_audit_only_runner_does_not_construct_hx() -> None:
    from benchmarks import run_task038_full3d_lor_spectral_audit_v2 as runner

    assert "build_hx=False" in inspect.getsource(runner.run_worker)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="audit-only fixture smoke is MPI1")
def test_audit_only_fixture_skips_scalar_node_and_hx_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.solvers.fullspace_lor_native_hx as production_hx
    from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture

    def forbidden_constructor(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("NativeComplexLORHX must not be constructed by audit-only setup")

    monkeypatch.setattr(production_hx, "NativeComplexLORHX", forbidden_constructor)
    fixture = RealL2PositiveHXFixture(2, MPI.COMM_WORLD, build_hx=False)
    try:
        assert fixture.hx is None
        assert fixture.node_matrix is None
        assert fixture.audit["hx_audit"]["constructed"] is False
    finally:
        fixture.destroy()


def test_fresh_raw_path_is_not_overwritten(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    record = tmp_path / "record.json"
    _prepare_paths(raw, record)
    try:
        _prepare_paths(raw, record)
    except FileExistsError:
        pass
    else:
        raise AssertionError("fresh path helper accepted an existing raw directory")


def test_checker_recomputes_positive_structure_and_rejects_mutated_artifact(tmp_path: Path) -> None:
    record_path, raw, source_sha, watchdog = _synthetic_record(tmp_path)
    result = checker.check_record(record_path, watchdog, source_sha)
    assert result["passed"], result
    assert result["metrics"]["numerical_rank"] == 2
    resource = result["resource"]
    compact = json.loads(watchdog.read_text(encoding="utf-8"))
    assert resource["watchdog_compact_path"] == str(watchdog.resolve())
    assert resource["watchdog_compact_sha256"] == hashlib.sha256(watchdog.read_bytes()).hexdigest()
    assert resource["watchdog_raw_path"] == str(Path(compact["watchdog_raw"]).resolve())
    assert resource["watchdog_raw_sha256"] == compact["raw_sha256"]
    assert resource["watchdog_rss_limit_bytes"] == checker.WATCHDOG_RSS_LIMIT
    assert resource["worker_command"] == compact["worker_command"]
    path = raw / "transfer_values.npy"
    values = np.load(path, allow_pickle=False)
    values[0] += 0.25
    np.save(path, values, allow_pickle=False)
    mutated = checker.check_record(record_path, watchdog, source_sha)
    assert not mutated["passed"]
    assert mutated["contract_errors"]


def test_checker_missing_required_role_fails_closed(tmp_path: Path) -> None:
    record_path, _raw, source_sha, watchdog = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["artifacts"]["high_action_observed"]
    record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, source_sha)
    assert not result["passed"]
    assert any("artifacts.high_action_observed" in item for item in result["contract_errors"])


def test_checker_does_not_use_old_v10_condition_cap() -> None:
    checker_text = Path("benchmarks/task038_full3d_lor_spectral_audit_v2_checker.py").read_text(encoding="utf-8")
    assert "SPECTRAL_CONDITION_LIMIT" not in checker_text
    assert "condition_policy" in checker_text
    assert "petsc4py" not in checker_text
    assert "mpi4py" not in checker_text
    assert "from benchmarks.run_task038" not in checker_text
    assert "fullspace_lor_global_audit" not in checker_text


def test_batch_entrypoint_is_explicit_and_uses_no_old_slepc_settings() -> None:
    from benchmarks import run_task038_full3d_lor_spectral_audit_v2 as runner

    args = runner._parser().parse_args(
        [
            "--stage",
            "s1",
            "--case",
            "batch",
            "--raw-dir",
            "/tmp/campaign",
            "--record",
            "/tmp/record.json",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ]
    )
    assert args.case == "batch"
    assert runner.BATCH_SCHEMA.endswith(".batch")


def test_worker_command_preserves_qualified_executable_and_module() -> None:
    argv = ["--stage", "s1", "--case", "p2-mpi1", "--raw-dir", "/tmp/raw"]
    command = runner._worker_command(argv)
    assert command[0] == os.path.abspath(sys.executable)
    assert command[0] == str(Path(sys.executable).absolute())
    assert command[0] != str(Path(sys.executable).resolve())
    assert command[1:3] == ["-m", runner.WORKER_MODULE]
    assert command[3:] == argv


def test_batch_gate_uses_real_threshold_and_limits() -> None:
    facts = {
        "numerical_rank": 3,
        "tested_dimension": 3,
        "high_action_relatives": [0.0],
        "work_relatives": [0.0],
        "pull_relatives": [0.0],
        "hermitian_defects": {"A_pull": 0.0},
        "spd": {"B_L": {"positive_definite": True}, "A_pull": {"positive_definite": True}},
        "spectral": {
            "status": "solved",
            "smallest": {"eigenvalue": 1.0, "residual_relative": 0.0},
            "largest": {"eigenvalue": 4.0, "residual_relative": 0.0},
        },
        "condition": 4.0,
    }
    assert runner._batch_case_is_closed(facts)
    facts["spectral"]["smallest"]["eigenvalue"] = 0.0
    assert not runner._batch_case_is_closed(facts)


def test_batch_checker_preserves_fixed_case_order_and_condition_growth(tmp_path: Path) -> None:
    first_path, first_raw, source_sha, _first_watchdog = _synthetic_record(tmp_path / "first")
    second_path, second_raw, _source_sha, _second_watchdog = _synthetic_record(tmp_path / "second")
    batch_root = tmp_path / "campaign"
    batch_root.mkdir()
    first_case_raw = batch_root / "p2-mpi1"
    second_case_raw = batch_root / "p3-mpi1"
    shutil.copytree(first_raw, first_case_raw)
    shutil.copytree(second_raw, second_case_raw)
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    for item, case, degree, raw in (
        (first, "p2-mpi1", 2, first_case_raw),
        (second, "p3-mpi1", 3, second_case_raw),
    ):
        item["case"] = case
        item["degree"] = degree
        item["raw_dir"] = str(raw.resolve())
    record_path = tmp_path / "docs" / "batch.json"
    record_path.parent.mkdir()
    first["record_path"] = str(record_path.resolve())
    second["record_path"] = str(record_path.resolve())
    command = [
        "/usr/bin/python3",
        "-m",
        "benchmarks.run_task038_full3d_lor_spectral_audit_v2",
        "--stage",
        "s1",
        "--case",
        "batch",
        "--source-name",
        "random",
        "--raw-dir",
        str(batch_root.resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        source_sha,
        "--expected-mpi-size",
        "1",
    ]
    first["command"] = command
    second["command"] = command
    marker_path = batch_root / "stage-rank0.jsonl"
    marker_path.write_text(json.dumps({"stage": "batch_record_written"}) + "\n", encoding="utf-8")
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    watchdog_sample = {"authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 1234, "swap_bytes": 0}}}
    watchdog_raw.write_text(json.dumps(watchdog_sample) + "\n", encoding="utf-8")
    watchdog = tmp_path / "watchdog.json"
    watchdog.write_text(json.dumps({
        "schema": checker.WATCHDOG_SCHEMA,
        "source_sha": source_sha,
        "worker_command": command,
        "worker_raw_dir": str(batch_root.resolve()),
        "worker_record": str(record_path.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
        "stop_reason": "natural_exit",
        "sample_count": 1,
        "all_status_readable": True,
        "peak_process_tree_rss_bytes": 1234,
        "max_process_tree_swap_bytes": 0,
        "watchdog_poll_seconds": 0.25,
        "watchdog_rss_limit_bytes": 2_000_000_000,
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
    }) + "\n", encoding="utf-8")
    batch = {
        "schema": BATCH_SCHEMA,
        "stage": "s1",
        "case": "batch",
        "source_name": "random",
        "mpi_size": 1,
        "raw_dir": str(batch_root.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": first["source"],
        "runtime": first["runtime"],
        "cases": [first, second],
        "completed_cases": ["p2-mpi1", "p3-mpi1"],
        "not_run_cases": [],
        "stop_reason": None,
        "markers": {
            "relative_path": "stage-rank0.jsonl",
            "sha256": hashlib.sha256(marker_path.read_bytes()).hexdigest(),
            "bytes": marker_path.stat().st_size,
            "lines": 1,
        },
    }
    record_path.write_text(json.dumps(batch, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_batch(record_path, watchdog, source_sha)
    assert result["passed"], result
    assert result["condition_growth"] is not None


def test_watchdog_and_marker_mutations_fail_closed(tmp_path: Path) -> None:
    record_path, _raw, source_sha, watchdog = _synthetic_record(tmp_path)
    compact = json.loads(watchdog.read_text(encoding="utf-8"))
    compact["no_orphan"] = False
    watchdog.write_text(json.dumps(compact) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, source_sha)
    assert not result["passed"]
    assert any("no_orphan" in item for item in result["contract_errors"])


def test_batch_releases_case_before_next_constructor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[tuple[str, object]] = []
    released = {"ready": False}
    source_sha = "0ee727d65e72032c211108a324c0fbebb37be4e3"

    class FakeFixture:
        def __init__(self, degree: int, *_args: object, **_kwargs: object) -> None:
            if degree == 3:
                assert released["ready"]
            events.append(("construct", degree))

        def destroy(self) -> None:
            events.append(("destroy", None))

    def fake_audit(_fixture: FakeFixture) -> dict[str, object]:
        return {
            "low_layout": {"owner_count": 1},
            "high_layout": {"owner_count": 1},
            "low_matrix_full": {"rows": 1},
            "high_matrix_full": {"rows": 1},
            "high_action_relatives": [0.0],
            "work_relatives": [0.0],
            "pull_relatives": [0.0],
            "hermitian_defects": {"A_pull": 0.0},
            "numerical_rank": 1,
            "tested_dimension": 1,
            "spd": {"B_L": {"positive_definite": True}, "A_pull": {"positive_definite": True}},
            "spectral": {"status": "solved", "smallest": {"eigenvalue": 1.0, "residual_relative": 0.0}, "largest": {"eigenvalue": 1.0, "residual_relative": 0.0}},
            "condition": 1.0,
        }

    def fake_build(_raw: Path, _record: Path, _source: dict[str, object], _runtime: dict[str, object], facts: dict[str, object], _command: list[str]) -> dict[str, object]:
        return {"case": facts["case"]}

    original_release = runner._release_batch_case

    def fake_release(fixture: object | None, facts: dict[str, object] | None) -> tuple[object | None, None]:
        result = original_release(fixture, facts)
        released["ready"] = result == (None, None)
        return result

    identity = {"expected": True, "expected_sha": source_sha, "commit_sha_start": source_sha, "commit_sha_end": source_sha, "branch": checker.BRANCH, "clean_start": True, "clean_end": True, "tracked_status_start": [], "tracked_status_end": []}
    monkeypatch.setattr(runner, "RealL2PositiveHXFixture", FakeFixture)
    monkeypatch.setattr(runner, "audit_fixture", fake_audit)
    monkeypatch.setattr(runner, "_build_record", fake_build)
    monkeypatch.setattr(runner, "_batch_case_is_closed", lambda _facts: True)
    monkeypatch.setattr(runner, "_source_identity", lambda _repo, _sha: dict(identity))
    monkeypatch.setattr(runner, "_source_probe", lambda _repo, _sha: {"commit_sha": source_sha, "clean": True, "tracked_status": [], "expected": True})
    monkeypatch.setattr(runner, "_runtime_facts", lambda _comm: {"mpi_size": 1})
    monkeypatch.setattr(runner, "_release_batch_case", fake_release)
    args = type("Args", (), {"expected_source_sha": source_sha})()
    runner.run_batch(args, tmp_path, tmp_path / "campaign", tmp_path / "docs" / "batch.json", ["/usr/bin/python3", "-m", "worker"])
    assert events == [("construct", 2), ("destroy", None), ("construct", 3), ("destroy", None)]


def test_spd_negative_is_recorded_without_fabricating_endpoints(tmp_path: Path) -> None:
    record_path, raw, source_sha, watchdog = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for matrix_name in ("B_L_full", "B_L_ind"):
        value_descriptor = record["matrix_artifacts"][matrix_name]["values"]
        value_path = raw / value_descriptor["relative_path"]
        values = np.load(value_path, allow_pickle=False)
        values[0] = -abs(values[0])
        np.save(value_path, values, allow_pickle=False)
        value_descriptor["sha256"] = hashlib.sha256(value_path.read_bytes()).hexdigest()
        value_descriptor["bytes"] = value_path.stat().st_size
    record["facts"]["spd"]["B_L"]["positive_definite"] = False
    record["facts"]["spectral_status"] = "not_run_spd_failure"
    record["spectral"] = {}
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, source_sha)
    assert not result["passed"]
    assert result["metrics"]["numerical_rank"] == 2
    assert any("spd" in item.lower() or "spectrum" in item.lower() for item in result["contract_errors"] + result["gate_failures"])


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="audit-only fixture smoke is MPI1")
def test_real_p2_matrix_free_and_sparse_pull_micro_smoke() -> None:
    from src.solvers.fullspace_lor_native_hx_fixture import _assemble_sparse, RealL2PositiveHXFixture

    fixture = RealL2PositiveHXFixture(2, MPI.COMM_WORLD, build_hx=False)
    high_matrix_object = _assemble_sparse(fixture.high_form, mpc=fixture.high_floquet.mpc)
    try:
        high_full = petsc_csr(high_matrix_object)
    finally:
        high_matrix_object.destroy()
    low_full = petsc_csr(fixture.edge_matrix)
    low_slave = global_slave_rows(fixture.lor_edge_space, fixture.lor_edge_floquet.mpc)
    high_slave = global_slave_rows(fixture.high_space, fixture.high_floquet.mpc)
    low_raw_map = fixture._raw_edge_canonical_map()
    low_active = np.asarray([row for row in range(low_full["rows"]) if row not in set(low_slave.tolist())], dtype=np.int64)
    high_active = np.asarray([row for row in range(high_full["rows"]) if row not in set(high_slave.tolist())], dtype=np.int64)
    low_layout = build_owner_layout(
        low_full["rows"],
        low_slave,
        low_raw_map,
        np.asarray(fixture.lor_raw_topology.owned_edge_ids, dtype=np.int64),
        owner_authority="lor_raw_topology.owned_edge_ids",
    )
    high_layout = {
        "full_rows": high_full["rows"],
        "slave_rows": high_slave,
        "active_raw_rows": high_active,
        "owner_ids": np.asarray(fixture.lor_topology.owned_edge_ids, dtype=np.int64),
        "owner_authority": "lor_topology.owned_edge_ids",
        "owner_count": high_active.size,
    }
    try:
        probe = np.asarray(
            np.sin(np.arange(high_full["rows"]) * 0.013)
            + 1j * np.cos(np.arange(high_full["rows"]) * 0.017),
            dtype=np.complex128,
        )
        probe[high_slave] = 0.0
        observed = _high_matrix_free_action(fixture, probe)
        expected = csr_matvec(high_full["indptr"], high_full["indices"], high_full["values"], probe)
        np.testing.assert_allclose(observed, expected, rtol=0.0, atol=1.0e-11)
        transfer = build_sparse_transfer(fixture, low_layout, high_layout)
        high_ind = _independent_csr(high_full, high_active)
        probe_low = np.ones(low_layout["owner_count"], dtype=np.complex128) + 0.2j
        csr_pull = csr_adjoint_left_product(
            transfer,
            csr_right_product(
                csr_to_dense(high_ind["rows"], high_ind["cols"], high_ind["indptr"], high_ind["indices"], high_ind["values"]),
                transfer,
            ),
        ) @ probe_low
        routed = _route_pull_action(fixture, low_layout, probe_low)
        np.testing.assert_allclose(routed, csr_pull, rtol=0.0, atol=1.0e-10)
    finally:
        fixture.destroy()
