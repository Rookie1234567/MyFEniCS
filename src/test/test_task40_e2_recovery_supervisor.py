from benchmarks.task40_e2_saved_field_recovery_v1.supervise import (
    qualified_python_environment,
    recovery_failure_record,
    watchdog_gate_checks,
)


def _passing_summary():
    return {
        "classification": "COMPLETED",
        "leader_exit_code": 0,
        "time_policy": "observe_only",
        "timebase_policy": "conservative_realtime",
        "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        "process_tree_swap_gate_enforced": True,
        "process_tree_samples": [{"rss_bytes": 100}],
        "process_tree_all_status_readable": True,
        "process_tree_all_identity_complete": True,
        "process_tree_identity_coverage": "complete",
        "sampled_process_tree_rss_peak_bytes": 100,
        "sampled_process_tree_swap_peak_bytes": 0,
        "descendants_cleared": True,
        "remaining_child_pids": [],
        "pss_sampling_policy": "disabled_by_profile",
        "sampled_process_tree_pss_peak_bytes": None,
    }


def _passing_last_sample():
    return {
        "identity_complete": True,
        "all_status_readable": True,
        "pss_sampling_policy": "disabled_by_profile",
        "pss_status": "DISABLED_BY_PROFILE",
        "pss_bytes": None,
    }


def test_watchdog_accepts_complete_zero_swap_sample_and_cleanup():
    assert all(watchdog_gate_checks(_passing_summary(), _passing_last_sample()).values())


def test_watchdog_rejects_empty_sample_and_incomplete_identity():
    summary = _passing_summary()
    summary["process_tree_samples"] = []
    summary["process_tree_all_identity_complete"] = False
    summary["process_tree_identity_coverage"] = "incomplete"
    sample = _passing_last_sample()
    sample["identity_complete"] = False
    checks = watchdog_gate_checks(summary, sample)
    assert not checks["sample_present"]
    assert not checks["process_tree_identity_complete"]
    assert not checks["last_sample_identity_complete"]


def test_worker_failure_record_preserves_failure_and_original_result():
    record = recovery_failure_record(
        {"leader_exit_code": 3, "classification": "WORKER_FAILED"},
        ["postprocess gate failed"],
        source_identity={"recovery_source_sha": "abc"},
    )
    assert record["status"] == "OFFLINE_RECOVERY_WORKER_FAILED_ORIGINAL_RUN_FAILED"
    assert record["failure"]["worker_exit_code"] == 3
    assert record["failure"]["worker_log_tail"] == ["postprocess gate failed"]
    assert record["original_worker_result_mutated"] is False


def test_qualified_venv_entry_accepts_system_python_symlink(tmp_path):
    venv = tmp_path / "repo" / ".venv"
    executable = venv / "bin" / "python"
    target = tmp_path / "system" / "python3"
    executable.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("system interpreter target")
    executable.symlink_to(target)
    assert executable.resolve() != executable
    assert qualified_python_environment("1", executable, venv, venv)


def test_qualified_python_rejects_unactivated_or_external_entry(tmp_path):
    venv = tmp_path / "repo" / ".venv"
    local = venv / "bin" / "python"
    external = tmp_path / "system" / "python3"
    local.parent.mkdir(parents=True)
    external.parent.mkdir(parents=True)
    local.write_text("qualified entry")
    external.write_text("system interpreter")
    assert not qualified_python_environment("0", local, venv, venv)
    assert not qualified_python_environment("1", external, venv, venv)
