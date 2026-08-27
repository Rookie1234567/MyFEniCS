from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from benchmarks import run_task038_full3d_lor_hx_foundation as runner
from benchmarks import task038_full3d_lor_hx_foundation_checker as checker


SOURCE_SHA = "a" * 40


def _descriptor(path: Path, values: np.ndarray) -> dict[str, object]:
    np.save(path, values, allow_pickle=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _role(raw: Path, name: str, semantic: str, keys: list[str], values: list[complex]) -> dict[str, object]:
    key_values = np.asarray(keys, dtype="<U32")
    numeric_values = np.asarray(values, dtype=np.complex128)
    return {
        "role": semantic,
        "keys": _descriptor(raw / f"{name}_keys.npy", key_values),
        "values": _descriptor(raw / f"{name}_values.npy", numeric_values),
    }


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    raw = tmp_path / "raw"
    raw.mkdir()
    record_path = tmp_path / "record.json"
    source_keys = ["p0", "p1"]
    dual_keys = ["d0", "d1"]
    artifacts = {
        "source_before": _role(raw, "source_before", "primal", source_keys, [1, 2]),
        "source_after": _role(raw, "source_after", "primal", source_keys, [1, 2]),
        "high_rhs": _role(raw, "high_rhs", "dual", dual_keys, [1, 2]),
        "high_rhs_repeat": _role(raw, "high_rhs_repeat", "dual", dual_keys, [1, 2]),
        "e_input_before": _role(raw, "e_input_before", "dual", dual_keys, [1, 2]),
        "e_input_after": _role(raw, "e_input_after", "dual", dual_keys, [1, 2]),
        "e_output": _role(raw, "e_output", "primal", source_keys, [1, 2]),
        "e_repeat": _role(raw, "e_repeat", "primal", source_keys, [1, 2]),
        "e_final_solution": _role(raw, "e_final_solution", "primal", source_keys, [0.1, 0.1]),
        "e_final_action": _role(raw, "e_final_action", "dual", dual_keys, [0.999999997763932, 2.0]),
        "e_final_true_residual": _role(raw, "e_final_true_residual", "dual", dual_keys, [2.23606797749979e-9, 0.0]),
        "e_output_constraint": _role(raw, "e_output_constraint", "constraint", ["high-slave:0"], [0]),
        "e_repeat_constraint": _role(raw, "e_repeat_constraint", "constraint", ["high-slave:0"], [0]),
        "e_final_constraint": _role(raw, "e_final_constraint", "constraint", ["high-slave:0"], [0]),
    }
    owner_artifacts = {
        "e_low_input_owner": _role(raw, "e_low_input_owner", "dual", ["owner:2", "owner:10"], [1, 2]),
        "e_low_solution_owner": _role(raw, "e_low_solution_owner", "primal", ["owner:10", "owner:2"], [1, 2]),
    }
    indptr = np.asarray([0, 1, 2], dtype=np.int32)
    indices = np.asarray([0, 1], dtype=np.int32)
    values = np.asarray([1, 1], dtype=np.complex128)
    row_keys = np.asarray(["lor-edge:0", "lor-edge:1"], dtype="<U32")
    matrix = {
        "rows": 2,
        "cols": 2,
        "type": "aij",
        "nnz": 2,
        "numeric_bytes": values.nbytes,
        "index_bytes": indptr.nbytes + indices.nbytes,
        "indptr": _descriptor(raw / "edge_indptr.npy", indptr),
        "indices": _descriptor(raw / "edge_indices.npy", indices),
        "values": _descriptor(raw / "edge_values.npy", values),
        "row_keys": _descriptor(raw / "edge_row_keys.npy", row_keys),
    }
    matrix_input = _role(raw, "e_low_input_matrix", "dual", ["lor-edge:0", "lor-edge:1"], [1, 2])
    matrix_solution = _role(raw, "e_low_solution_matrix", "primal", ["lor-edge:0", "lor-edge:1"], [1, 2])

    checkpoint = raw / "checkpoint-500"
    checkpoint.mkdir()
    solution = np.asarray([0, 0], dtype=np.complex128)
    solution_descriptor = _descriptor(checkpoint / "solution_rank0.npy", solution)
    manifest = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 500,
        "explicit_true_residual": 1e-9,
        "input_identity_sha256": "1" * 64,
        "operator_identity_sha256": "2" * 64,
        "physical_model_sha256": "3" * 64,
        "source_sha": SOURCE_SHA,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "ranks": [{
            "rank": 0,
            "ownership": {"rank": 0, "ownership_range": [0, 2], "local_size": 2, "global_size": 2},
            "solution": solution_descriptor,
        }],
    }
    manifest_path = checkpoint / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    checkpoint_fact = {
        "iteration": 500,
        "explicit_true_residual": 1e-9,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }

    cycles = [
        {
            "cycle_index": index,
            "start_iteration": index * 20,
            "end_iteration": (index + 1) * 20,
            "iterations": 20,
            "reason": -3,
            "explicit_true_residual": 1e-9,
            "reported_final_residual": 1e-9,
            "ksp_destroyed": True,
            "matvec_count": 21,
            "pc_apply_count": 20,
            "wall_seconds": 0.01,
            "resource": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}, "job_cgroup": {"dedicated_job_cgroup": False}},
        }
        for index in range(25)
    ]
    record = {
        "schema": runner.SCHEMA,
        "stage": "foundation-e",
        "case": runner.CASE,
        "degree": 3,
        "h_nm": 50.0,
        "source_name": "random",
        "variant": "sequential-v1",
        "mpi_size": 1,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": [
            "/qualified/bin/python", "-m", "benchmarks.run_task038_full3d_lor_hx_foundation", "--stage", "foundation-e",
            "--case", "p3-mpi1", "--raw-dir", str(raw.resolve()), "--record", str(record_path.resolve()),
            "--expected-source-sha", SOURCE_SHA, "--expected-mpi-size", "1",
        ],
        "source": {
            "expected_sha": SOURCE_SHA,
            "branch": runner.BRANCH,
            "clean_start": True,
            "clean_end": True,
            "commit_sha_start": SOURCE_SHA,
            "commit_sha_end": SOURCE_SHA,
        },
        "runtime": {
            "qualified_activation": "1",
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "threads": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
        },
        "provenance": {"input_identity_sha256": "1" * 64, "operator_identity_sha256": "2" * 64, "physical_model_sha256": "3" * 64},
        "settings": {
            "ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned", "restart": 20,
            "max_it": 10000, "residual_replacement": True, "zero_initial_guess": True, "residual_limit": 1e-8,
            "checkpoint_interval": 500, "first_checkpoint_iteration": None, "direct_backend": "petsc-preonly-lu-mumps",
        },
        "fixture_audit": {"global_transfer_matrix": False, "global_numeric_allgather": False, "high_order_global_aij": False, "hx_audit": {"global_transfer_matrix": False, "high_order_aij": False}, "phase_application": "finalized_floquet_mpc_once", "slave_master_complete": True, "lor_full_edge_rows": 2, "lor_edge_slave_rows": 0},
        "production_forbidden": {"high_order_global_aij": False, "global_dense_transfer": False, "global_direct_coarse": False, "global_numeric_allgather": False},
        "route_audit": {"owner_inventory_equal": True, "owner_count": 2, "high_to_lor_owner_route": True, "lor_to_high_owner_route": True, "orientation_consistent": True, "phase_application": "finalized_floquet_mpc_once", "slave_master_complete": True},
        "canonical_artifacts": artifacts,
        "owner_artifacts": owner_artifacts,
        "matrix_artifacts": {
            "edge": matrix,
            "e_low_input_matrix": matrix_input,
            "e_low_solution_matrix": matrix_solution,
        },
        "component_hashes": {},
        "checkpoint_facts": [checkpoint_fact],
        "cycles": cycles,
        "boundary_facts": [{"iteration": 500, "explicit_true_residual": 1e-9, "matvec_count": 525, "pc_apply_count": 500, "cumulative_explicit_true_residual_action_count": 26, "cumulative_high_action_count": 551, "wall_seconds": 0.25, "wall_semantics": "cumulative_cycle_wall_seconds_excludes_setup", "resource": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}, "job_cgroup": {"dedicated_job_cgroup": False}}}],
        "outer": {"iterations": 500, "final_true_residual": 1e-9, "matvec_count": 525, "pc_apply_count": 500, "explicit_action_count": 26, "total_high_action_count": 551, "ksp_destroy_count": 25, "reason": -3, "elapsed_seconds": 1.0},
        "single_apply": {"direct_residual_relative": 0.0, "direct_finite": True, "repeat_relative": 0.0, "input_unchanged_relative": 0.0, "primal_constraint_relative": 0.0},
        "pc_legality": {"apply_count": 500, "max_input_unchanged_relative": 0.0, "max_primal_constraint_relative": 0.0, "finite": True, "direct_factor_solve_count_total": 502, "reference_repeat_relative": 0.0, "reference_input_unchanged_relative": 0.0, "reference_primal_constraint_relative": 0.0},
        "rank_facts": [{"rank": 0, "runtime": {"qualified_activation": "1", "mpi_size": 1, "petsc_scalar_type": "complex128", "petsc_int_type": "int32", "threads": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}}, "pc_legality": {"apply_count": 500, "max_input_unchanged_relative": 0.0, "max_primal_constraint_relative": 0.0, "finite": True}, "direct_factor_solve_count": 502, "outer_iterations": 500, "outer_matvec_count": 525, "outer_pc_apply_count": 500}],
        "prior_q0_reference": checker.PRIOR_Q0,
    }
    record["component_hashes"] = {
        name: hashlib.sha256(
            (json.dumps({"keys_sha256": descriptor["keys"]["sha256"], "values_sha256": descriptor["values"]["sha256"]}, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        for name, descriptor in {**artifacts, **owner_artifacts}.items()
    }
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    (raw / "stage-rank0.jsonl").write_text(
        "".join(json.dumps({"stage": stage, "rank": 0, "time": 0.0}) + "\n" for stage in (
            "setup", "source_identity_closed", "runtime_identity", "single_apply_legality",
            "outer_start", "checkpoint-500", "final", "record_closeout", "record_written",
        )),
        encoding="utf-8",
    )
    watchdog_raw = tmp_path / "watchdog.jsonl"
    watchdog_sample = {"authority": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}, "job_cgroup": {"dedicated_job_cgroup": False}}}
    watchdog_raw.write_text(json.dumps(watchdog_sample) + "\n", encoding="utf-8")
    watchdog = tmp_path / "watchdog.json"
    watchdog.write_text(json.dumps({
        "schema": checker.WATCHDOG_SCHEMA,
        "source_sha": SOURCE_SHA,
        "worker_record": str(record_path.resolve()),
        "worker_raw_dir": str(raw.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
        "stop_reason": "natural_exit",
        "sample_count": 1,
        "all_status_readable": True,
        "watchdog_poll_seconds": 0.25,
        "watchdog_rss_limit_bytes": 500000000,
        "worker_command": record["command"],
        "peak_process_tree_rss_bytes": 100,
        "max_process_tree_swap_bytes": 0,
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
    }, sort_keys=True) + "\n", encoding="utf-8")
    return record_path, watchdog, record


def test_foundation_is_e_only_and_settings_are_frozen() -> None:
    text = Path(runner.__file__).read_text(encoding="utf-8")
    checker_text = Path(checker.__file__).read_text(encoding="utf-8")
    assert "replay_multiplicative_components" not in text
    assert "WATCHDOG_TIMEOUT" not in text
    assert "watchdog_timeout" not in text
    assert "WATCHDOG_TIMEOUT" not in checker_text
    assert "watchdog_timeout" not in checker_text
    assert runner.MAX_IT == 10_000
    assert runner.RESTART == 20
    assert runner.CHECKPOINT_INTERVAL == 500
    assert runner.SOURCE_NAME == "random"
    assert runner.WATCHDOG_RSS_LIMIT == 500_000_000


def test_exact_apply_uses_the_current_residual() -> None:
    seen: list[np.ndarray] = []

    def restrict(value: np.ndarray) -> tuple[np.ndarray, None]:
        seen.append(value.copy())
        return value.copy(), None

    def solve(value: np.ndarray) -> tuple[np.ndarray, dict[str, object]]:
        return 2.0 * value, {}

    result_one = runner._apply_current_residual(np.asarray([1.0 + 0j]), restrict, solve, lambda value: value)
    result_two = runner._apply_current_residual(np.asarray([3.0 + 0j]), restrict, solve, lambda value: value)
    assert np.array_equal(seen[0], [1.0 + 0j])
    assert np.array_equal(seen[1], [3.0 + 0j])
    assert np.array_equal(result_one, [2.0 + 0j])
    assert np.array_equal(result_two, [6.0 + 0j])


def test_checkpoint_and_watchdog_contract_helpers() -> None:
    assert runner._checkpoint_due(500)
    assert not runner._checkpoint_due(520)
    assert runner._expected_checkpoint_files() == {"manifest.json", "solution_rank0.npy"}
    authority = {"process_tree": {"rss_bytes": 499_999_999, "swap_bytes": 0, "all_status_readable": True}, "job_cgroup": {"dedicated_job_cgroup": False}}
    assert runner._watchdog_stop_reason(authority) is None
    authority["process_tree"]["rss_bytes"] = 500_000_000
    assert runner._watchdog_stop_reason(authority) == "process_tree_rss_limit"
    assert runner._watchdog_stop_reason(authority, 2_000_000_000) is None
    authority["process_tree"]["rss_bytes"] = 1
    authority["process_tree"]["swap_bytes"] = 1
    assert runner._watchdog_stop_reason(authority) == "process_tree_swap_nonzero"
    unreadable = {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": False}}
    assert runner._watchdog_stop_reason(unreadable) == "authority_unreadable"

    class FakeProcess:
        def __init__(self, result: int | None) -> None:
            self.result = result

        def poll(self) -> int | None:
            return self.result

    assert runner._watchdog_terminal_exit_race(FakeProcess(0), "authority_unreadable")
    assert not runner._watchdog_terminal_exit_race(FakeProcess(None), "authority_unreadable")
    assert not runner._watchdog_terminal_exit_race(FakeProcess(0), "process_tree_swap_nonzero")
    assert "args.worker_raw_dir.mkdir" not in Path(runner.__file__).read_text(encoding="utf-8")


def test_watchdog_retries_one_transient_unreadable_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    unreadable = {
        "process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": False, "pids": [7]}
    }
    readable = {
        "process_tree": {"rss_bytes": 200, "swap_bytes": 0, "all_status_readable": True, "pids": [7]}
    }
    calls: list[int] = []
    sleeps: list[float] = []

    def sample(pid: int) -> dict[str, object]:
        calls.append(pid)
        return unreadable if len(calls) == 1 else readable

    class LiveProcess:
        pid = 123

        def poll(self) -> None:
            return None

    monkeypatch.setattr(runner, "resource_authority_sample", sample)
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    authority, retry_count, initial = runner._watchdog_authority_with_retry(LiveProcess())
    assert calls == [123, 123]
    assert sleeps == [0.01]
    assert authority is readable
    assert retry_count == 1
    assert initial == unreadable["process_tree"]


def test_watchdog_keeps_second_unreadable_authority_as_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    unreadable = {
        "process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": False, "pids": [7]}
    }
    calls: list[int] = []

    def sample(pid: int) -> dict[str, object]:
        calls.append(pid)
        return unreadable

    class LiveProcess:
        pid = 456

        def poll(self) -> None:
            return None

    monkeypatch.setattr(runner, "resource_authority_sample", sample)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    authority, retry_count, initial = runner._watchdog_authority_with_retry(LiveProcess())
    assert calls == [456, 456]
    assert retry_count == 1
    assert initial == unreadable["process_tree"]
    assert runner._watchdog_stop_reason(authority) == "authority_unreadable"


def test_owner_identity_and_boundary_facts_are_order_independent_and_cumulative() -> None:
    assert runner._owner_key_identity(
        np.asarray(["owner:10", "owner:2"]), np.asarray(["owner:2", "owner:10"])
    )
    cycles = [
        {
            "end_iteration": (index + 1) * 20,
            "matvec_count": 21,
            "pc_apply_count": 20,
            "wall_seconds": 0.01,
            "explicit_true_residual": 1.0e-9,
            "resource": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}, "job_cgroup": {"dedicated_job_cgroup": False}},
        }
        for index in range(25)
    ]
    facts = runner._boundary_facts(cycles)
    assert facts[0]["iteration"] == 500
    assert facts[0]["explicit_true_residual"] == 1.0e-9
    assert facts[0]["matvec_count"] == 525
    assert facts[0]["pc_apply_count"] == 500
    assert facts[0]["cumulative_explicit_true_residual_action_count"] == 26
    assert facts[0]["cumulative_high_action_count"] == 551
    assert np.isclose(facts[0]["wall_seconds"], 0.25)
    assert facts[0]["wall_semantics"] == "cumulative_cycle_wall_seconds_excludes_setup"


def test_watchdog_artifacts_are_siblings_and_last_sample_is_not_post_exit() -> None:
    raw_dir = Path("/tmp") / "foundation-worker-raw-test"
    assert "final_live_observation" not in Path(runner.__file__).read_text(encoding="utf-8")
    assert "last_live_observation" in Path(runner.__file__).read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        runner._validate_watchdog_paths(raw_dir, (raw_dir,))
    with pytest.raises(ValueError):
        runner._validate_watchdog_paths(raw_dir, (raw_dir / "watchdog.json",))
    runner._validate_watchdog_paths(raw_dir, (raw_dir.parent / "watchdog.json",))


def test_watchdog_dispatch_preserves_worker_remainder() -> None:
    worker_command = [
        "/abs/python",
        "-m",
        "benchmarks.run_task038_full3d_lor_hx_foundation",
        "--stage",
        "foundation-e",
        "--case",
        "p3-mpi1",
        "--raw-dir",
        "/tmp/worker_raw",
    ]
    watchdog_args = [
        "--watchdog-raw",
        "/tmp/watchdog.raw.jsonl",
        "--watchdog-compact",
        "/tmp/watchdog.json",
        "--watchdog-log",
        "/tmp/worker.log",
        "--worker-raw-dir",
        "/tmp/worker_raw",
        "--worker-record",
        "/tmp/record.json",
        "--source-sha",
        SOURCE_SHA,
        "--watchdog-rss-limit-bytes",
        "2000000000",
        "--worker-command",
        "--",
        *worker_command,
    ]
    assert runner._watchdog_argv_without_separator(watchdog_args)[-len(worker_command) :] == worker_command


def test_watchdog_main_subprocess_natural_closeout_and_fail_closed_reuse(tmp_path: Path) -> None:
    repo = Path(runner.__file__).resolve().parents[1]
    worker_raw = tmp_path / "worker_raw"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    watchdog_compact = tmp_path / "watchdog.json"
    watchdog_log = tmp_path / "worker.log"
    worker_record = tmp_path / "record.json"
    worker_command = [sys.executable, "-c", "import time; time.sleep(0.35)"]
    command = [
        sys.executable,
        "-m",
        "benchmarks.run_task038_full3d_lor_hx_foundation",
        "--watchdog",
        "--watchdog-raw",
        str(watchdog_raw),
        "--watchdog-compact",
        str(watchdog_compact),
        "--watchdog-log",
        str(watchdog_log),
        "--worker-raw-dir",
        str(worker_raw),
        "--worker-record",
        str(worker_record),
        "--source-sha",
        SOURCE_SHA,
        "--watchdog-rss-limit-bytes",
        "2000000000",
        "--worker-command",
        "--",
        *worker_command,
    ]
    first = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    compact = json.loads(watchdog_compact.read_text(encoding="utf-8"))
    assert compact["worker_command"] == worker_command
    assert compact["natural_exit"] is True
    assert compact["no_orphan"] is True
    assert compact["returncode"] == 0
    assert compact["watchdog_rss_limit_bytes"] == 2_000_000_000
    assert compact["authority_readability_retry_count"] == 0
    assert compact["authority_readability_recovered_count"] == 0
    assert compact["terminal_exit_race_discard_count"] == 0
    assert not worker_raw.exists()
    second = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert not worker_raw.exists()


def test_checker_recomputes_synthetic_raw_and_rejects_checkpoint_extra(tmp_path: Path) -> None:
    record_path, watchdog, _record = _synthetic_record(tmp_path)
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert result["passed"], result
    (tmp_path / "raw" / "checkpoint-500" / "action.npy").write_bytes(b"forbidden")
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert not result["passed"]
    assert any("undeclared" in item for item in result["contract_errors"])


def test_checker_binds_boundary_resource_rho_and_each_primal_constraint_norm(tmp_path: Path) -> None:
    resource_root = tmp_path / "resource"
    resource_root.mkdir()
    record_path, watchdog, _record = _synthetic_record(resource_root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["boundary_facts"][0]["resource"]["process_tree"]["rss_bytes"] = 500_000_000
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert any("boundary 500 process-tree resource failed" in item for item in result["gate_failures"])

    rho_root = tmp_path / "rho"
    rho_root.mkdir()
    record_path, watchdog, _record = _synthetic_record(rho_root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["outer"]["final_true_residual"] = 2.0e-9
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert any("raw final rho does not match outer" in item for item in result["contract_errors"])

    constraint_root = tmp_path / "constraint"
    constraint_root.mkdir()
    record_path, watchdog, _record = _synthetic_record(constraint_root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    descriptor = record["canonical_artifacts"]["e_final_constraint"]["values"]
    values_path = constraint_root / "raw" / descriptor["relative_path"]
    np.save(values_path, np.asarray([1.0e-12], dtype=np.complex128), allow_pickle=False)
    descriptor["bytes"] = values_path.stat().st_size
    descriptor["sha256"] = hashlib.sha256(values_path.read_bytes()).hexdigest()
    record["component_hashes"]["e_final_constraint"] = checker._identity_sha(
        {
            "keys_sha256": record["canonical_artifacts"]["e_final_constraint"]["keys"]["sha256"],
            "values_sha256": descriptor["sha256"],
        }
    )
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert any("e_final_constraint relative" in item for item in result["gate_failures"])


def test_checker_fail_closed_for_missing_watchdog_and_tampered_residual(tmp_path: Path) -> None:
    record_path, watchdog, _record = _synthetic_record(tmp_path)
    result = checker.check_record(record_path, tmp_path / "missing-watchdog.json", SOURCE_SHA)
    assert not result["passed"]
    assert "missing external watchdog compact" in result["contract_errors"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    residual_path = tmp_path / "raw" / record["canonical_artifacts"]["e_final_true_residual"]["values"]["relative_path"]
    np.save(residual_path, np.asarray([2.0e-9, 2.0e-9], dtype=np.complex128), allow_pickle=False)
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert not result["passed"]
    assert any("SHA256 mismatch" in item for item in result["contract_errors"])


def test_checker_requires_absolute_worker_executable(tmp_path: Path) -> None:
    record_path, watchdog, _record = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["command"][0] = "python"
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog, SOURCE_SHA)
    assert any("fixed ordered invocation" in item for item in result["contract_errors"])
