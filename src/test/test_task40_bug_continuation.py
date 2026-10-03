"""Task40 continuation keeps failure evidence and all numerical stop semantics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.geometry.task40_nonseparable_plan import (
    TASK40_COMPARISON_GROUP,
    TASK40_F1_REFERENCE_METRIC_RUN_ID,
    TASK40_GX560_RUN_ID,
    TASK40_GZ528_RUN_ID,
)
from src.io import InputError
from src.runners import task038_launcher as launcher

RUN_ID = "task40extra_0p7nm_nonseparable_g0_iterative_v1"
SUMMARY = "task40extra_nonseparable_0p7nm_p6q4_summary.json"
RECORD = "docs/task40extra_0p7nm_engineering/outcomes/records/g0_user_authorized_continuation_v1.json"
INPUT = "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat"
CLOCK = {"monotonic_seconds": 0.0, "boottime_seconds": 0.0, "utc_seconds": 0.0}


def reserve(root, name, source, run_id=RUN_ID):
    return launcher._reserve_task40_0p7nm_budget(
        root, root / name, run_id=run_id,
        comparison_group=TASK40_COMPARISON_GROUP,
        source_sha=source, stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start=CLOCK, time_policy="observe_only",
        service_cgroup_path=Path("/sys/fs/cgroup/app.slice/myfenics-case-fixture.service"),
    )


def fail(lease, next_source):
    ledger = json.loads(Path(lease["path"]).read_bytes())
    attempt = ledger["stages"]["Q4_ORIGINAL"]["attempts"][lease["attempt_index"]]
    directory = Path(attempt["run_directory"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SUMMARY).write_text(json.dumps({
        "status": "FAILED", "result_classification": "WORKER_FAILED",
        "source_sha": attempt["source_sha"], "error": {"type": "AttributeError"},
    }))
    (directory / "implementation_bug_replay.json").write_text(json.dumps({
        "classification": "IMPLEMENTATION_BUG", "stage": "Q4_ORIGINAL",
        "failed_source_sha": attempt["source_sha"], "fixed_source_sha": next_source,
        "bug_and_fix": "fixture: preserve missing geometry audit metadata",
    }))
    launcher._settle_v14_shared_budget(
        lease, status="WORKER_FAILED", authority=None,
        parent_interval={"budget_seconds": 45.0}, parent_clock_end=CLOCK,
    )


@pytest.mark.parametrize("invalid", [None, "ledger", "numerical"])
def test_task40_explicit_bug_continuation_preserves_history(tmp_path, invalid):
    first = reserve(tmp_path, "first", "a" * 40)
    fail(first, "b" * 40)
    second = reserve(tmp_path, "second", "b" * 40)
    fail(second, "c" * 40)
    ledger_path = Path(second["path"])
    before_bytes = ledger_path.read_bytes()
    before = json.loads(before_bytes)
    input_path = tmp_path / INPUT
    input_path.parent.mkdir(parents=True)
    input_path.write_text("fixture frozen input")
    record = {
        "classification": "USER_AUTHORIZED_IMPLEMENTATION_BUG_CONTINUATION",
        "authorization_id": "fixture-user-authorization",
        "user_instruction": "Repair implementation bugs and continue; keep numerical gates.",
        "run_id": RUN_ID, "stage": "Q4_ORIGINAL",
        "comparison_group": "task40extra_0p7nm_nonseparable_n0_n6",
        "prior_ledger_sha256": hashlib.sha256(before_bytes).hexdigest(),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "previous_bug_replay_count": 1, "additional_bug_replays": 1,
    }
    if invalid == "ledger":
        record["prior_ledger_sha256"] = "0" * 64
    if invalid == "numerical":
        summary_path = tmp_path / "second" / SUMMARY
        summary = json.loads(summary_path.read_bytes())
        summary["result_classification"] = "NUMERICAL_CONTROLLED_STOP"
        summary_path.write_text(json.dumps(summary))
    record_path = tmp_path / RECORD
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps(record))
    if invalid:
        with pytest.raises(InputError):
            reserve(tmp_path, "third", "c" * 40)
        assert ledger_path.read_bytes() == before_bytes
        return
    third = reserve(tmp_path, "third", "c" * 40)
    after_bytes = ledger_path.read_bytes()
    after = json.loads(after_bytes)
    assert third["replay"] is True
    assert third["prerequisite"]["user_bug_continuation"]["authorization"] == record
    assert after["stages"]["Q4_ORIGINAL"]["attempts"][:2] == before["stages"]["Q4_ORIGINAL"]["attempts"]
    assert after["elapsed_seconds"] == before["elapsed_seconds"] == 90.0
    assert after["fresh_worker_count"] == 3
    assert after["unique_bug_replay_count"] == 2
    fail(third, "d" * 40)
    settled_bytes = ledger_path.read_bytes()
    with pytest.raises(InputError, match="already consumed"):
        reserve(tmp_path, "fourth", "d" * 40)
    assert ledger_path.read_bytes() == settled_bytes
    g1 = reserve(tmp_path, "g1", "c" * 40, RUN_ID.replace("g0_", "g1_"))
    assert g1["replay"] is False
    assert "user_bug_continuation" not in g1["prerequisite"]



def test_task40_review_v2_f1_allows_next_hash_bound_bug_repair_after_one_use(
    tmp_path,
):
    review_v1_run_id = "task40extra_0p7nm_nonseparable_g0_iterative_review_v1"
    old_path = (
        tmp_path
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        / "task40_nonseparable_0p7nm"
        / review_v1_run_id
        / "shared_workflow_ledger.json"
    )
    old_path.parent.mkdir(parents=True)
    old_path.write_text(
        json.dumps(
            {
                "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
                "batch_identity": review_v1_run_id,
                "unique_bug_replay_count": 1,
                "elapsed_seconds": 900.0,
                "conservative_allowance_seconds": 120.0,
                "fresh_worker_count": 2,
            }
        ),
        encoding="utf-8",
    )
    old_bytes = old_path.read_bytes()

    first = reserve(
        tmp_path,
        "review-v2-f1-first",
        "a" * 40,
        run_id=TASK40_F1_REFERENCE_METRIC_RUN_ID,
    )
    fail(first, "b" * 40)
    second = reserve(
        tmp_path,
        "review-v2-f1-first-repair",
        "b" * 40,
        run_id=TASK40_F1_REFERENCE_METRIC_RUN_ID,
    )
    assert second["replay"] is True
    fail(second, "c" * 40)

    ledger_after_one_replay = json.loads(Path(second["path"]).read_bytes())
    assert ledger_after_one_replay["unique_bug_replay_count"] == 1
    third = reserve(
        tmp_path,
        "review-v2-f1-second-repair",
        "c" * 40,
        run_id=TASK40_F1_REFERENCE_METRIC_RUN_ID,
    )
    assert third["replay"] is True
    assert third["replay_evidence"]["classification"] == "IMPLEMENTATION_BUG"
    assert third["replay_evidence"]["failed_source_sha"] == "b" * 40
    assert third["replay_evidence"]["fixed_source_sha"] == "c" * 40
    assert json.loads(Path(third["path"]).read_bytes())[
        "unique_bug_replay_count"
    ] == 2
    assert old_path.read_bytes() == old_bytes



def test_task40_f1_outer_timebase_recovery_is_one_hash_bound_repeat(tmp_path):
    import hashlib

    from src.runners.task038_launcher import (
        _task40_f1_outer_timebase_recovery_repeat,
    )

    run_id = TASK40_F1_REFERENCE_METRIC_RUN_ID
    input_path = (
        tmp_path / "input/task40extra_0p7nm_engineering/"
        "nonseparable_g1_p6_q4_reference_metric_f1.dat"
    )
    input_path.parent.mkdir(parents=True)
    input_path.write_text("frozen F1 input fixture", encoding="utf-8")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    prior_dir = tmp_path / "results/f1-attempt1"
    prior_dir.mkdir(parents=True)
    worker_manifest = {
        "status": "launching", "result_classification": "not_run", "exit_status": None
    }
    worker_summary = dict(worker_manifest)
    (prior_dir / "run_manifest.json").write_text(json.dumps(worker_manifest))
    (prior_dir / "run_summary.json").write_text(json.dumps(worker_summary))

    recovery_root = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "f1_reference_metric_g1/attempt4/recovery"
    )
    recovery_root.mkdir(parents=True)
    outer_path = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "f1_reference_metric_g1/attempt4/watchdog/summary.json"
    )
    outer_path.parent.mkdir(parents=True)
    outer = {
        "classification": "TIMEBASE_INCONSISTENCY",
        "stop_event": {"reason": "TIMEBASE_INCONSISTENCY"},
        "timebase_policy": "strict",
        "time_policy": "observe_only",
        "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        "pss_sampling_policy": "disabled_by_profile",
        "elapsed_seconds": 62.372320763999596,
        "descendants_cleared": True,
        "process_tree_identity_coverage": "complete",
        "sampled_process_tree_swap_peak_bytes": 0,
    }
    outer_bytes = json.dumps(outer, sort_keys=True).encode()
    outer_path.write_bytes(outer_bytes)
    outer_sha = hashlib.sha256(outer_bytes).hexdigest()
    source_before, source_after = "d" * 40, "e" * 40
    parent_interval = {
        "budget_seconds": outer["elapsed_seconds"],
        "outer_watchdog_summary_sha256": outer_sha,
    }
    ledger_path = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "task40_nonseparable_0p7nm" / run_id / "shared_workflow_ledger.json"
    )
    ledger_path.parent.mkdir(parents=True)
    ledger = {
        "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
        "batch_identity": run_id,
        "total_budget_seconds": 43200.0,
        "elapsed_seconds": outer["elapsed_seconds"],
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [],
        "fresh_worker_count": 1,
        "source_attempts": [],
        "unique_bug_replay_count": 0,
        "allowed_stages": ["Q4_ORIGINAL"],
        "cross_case_recycling": False,
        "authorized_performance_repeats": [],
        "stages": {
            "Q4_ORIGINAL": {
                "active_attempt": None,
                "attempts": [{
                    "source_sha": source_before,
                    "status": "OUTER_WATCHDOG_TIMEBASE_INCONSISTENCY",
                    "watchdog_classification": "TIMEBASE_INCONSISTENCY",
                    "hard_kill_included": True,
                    "replay": False,
                    "settled_seconds": outer["elapsed_seconds"],
                    "parent_workflow_clock_interval": parent_interval,
                    "run_directory": str(prior_dir),
                }],
            }
        },
    }
    ledger_bytes = json.dumps(ledger, sort_keys=True).encode()
    ledger_path.write_bytes(ledger_bytes)
    manifest_bytes = (prior_dir / "run_manifest.json").read_bytes()
    worker_summary_bytes = (prior_dir / "run_summary.json").read_bytes()
    record = {
        "schema": "task40extra.f1.outer-timebase-recovery.v1",
        "authorization_id": "task40extra_f1_outer_timebase_stop_recovery_20261001",
        "classification": "CONTROLLED_RECOVERY_AFTER_OUTER_TIMEBASE_STOP",
        "kind": "STARTUP_INFRASTRUCTURE_REPAIR",
        "scope": "single_f1_startup_repair_after_outer_timebase_stop",
        "allowed_repeat_count": 1,
        "worker_final_status_claimed": False,
        "run_id": run_id,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "input_sha256": input_sha,
        "source_sha_before": source_before,
        "source_sha_after": source_after,
        "settled_ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "outer_watchdog_summary_path": str(outer_path),
        "outer_watchdog_summary_sha256": outer_sha,
        "prior_run_directory": str(prior_dir),
        "worker_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "worker_run_summary_sha256": hashlib.sha256(worker_summary_bytes).hexdigest(),
        "prior_worker_result": worker_summary,
    }
    record_path = recovery_root / "f1_recovery_authorization.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(InputError, match="evidence or identity changed"):
        _task40_f1_outer_timebase_recovery_repeat(
            tmp_path,
            run_id=run_id,
            comparison_group=TASK40_COMPARISON_GROUP,
            source_sha="f" * 40,
        )
    result = launcher._reserve_task40_0p7nm_budget(
        tmp_path,
        tmp_path / "f1-attempt2",
        source_sha=source_after,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start=CLOCK,
        time_policy="observe_only",
        run_id=run_id,
        comparison_group=TASK40_COMPARISON_GROUP,
        service_cgroup_path=Path(
            "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
            "app.slice/myfenics-case-task40-recovery.service"
        ),
    )
    repeat = result["authorized_performance_repeat"]
    assert result["replay"] is False
    assert repeat["authorization_id"] == record["authorization_id"]
    assert repeat["kind"] == "STARTUP_INFRASTRUCTURE_REPAIR"
    assert repeat["scope"] == "single_f1_startup_repair_after_outer_timebase_stop"
    assert repeat["outer_watchdog_summary_sha256"] == outer_sha
    assert result["reserved_seconds"] == 43200.0
    assert json.loads(ledger_path.read_text())["infrastructure_recovery_count"] == 1
    assert json.loads(ledger_path.read_text())["unique_bug_replay_count"] == 0
    accounting = json.loads(
        Path(result["task40_batch_replay_accounting_path"]).read_text()
    )
    assert accounting["selected_batch"] == "review_v2_f1"
    assert accounting["one_off_infrastructure_recovery"][
        "settled_ledger_sha256"
    ] == record["settled_ledger_sha256"]

    # Once the one infrastructure repair is consumed, it is excluded from the
    # bug-attempt length gate while a genuine hash-bound implementation repair
    # still follows the normal replay checks and increments only the bug count.
    consumed_ledger = json.loads(ledger_path.read_bytes())
    recovery_run = Path(result["task40_batch_replay_accounting_path"]).parent
    failed_summary = {
        "status": "FAILED",
        "result_classification": "WORKER_FAILED",
        "source_sha": source_after,
        "error": {"type": "AttributeError", "message": "fixture bug"},
    }
    (recovery_run / SUMMARY).write_text(json.dumps(failed_summary), encoding="utf-8")
    (recovery_run / "implementation_bug_replay.json").write_text(
        json.dumps({
            "classification": "IMPLEMENTATION_BUG",
            "stage": "Q4_ORIGINAL",
            "failed_source_sha": source_after,
            "fixed_source_sha": "f" * 40,
            "bug_and_fix": "fixture: correct Task40 worker setup",
        }),
        encoding="utf-8",
    )
    attempt_index = result["attempt_index"]
    consumed_attempt = consumed_ledger["stages"]["Q4_ORIGINAL"]["attempts"][attempt_index]
    consumed_attempt.update({
        "status": "WORKER_FAILED",
        "watchdog_classification": "WORKER_FAILED",
        "replay": False,
    })
    launcher._settle_v14_shared_budget(
        result,
        status="WORKER_FAILED",
        authority=None,
        parent_interval={"budget_seconds": 45.0},
        parent_clock_end=CLOCK,
    )
    consumed_ledger = json.loads(ledger_path.read_bytes())
    assert consumed_ledger["infrastructure_recovery_count"] == 1
    assert consumed_ledger["unique_bug_replay_count"] == 0
    assert _task40_f1_outer_timebase_recovery_repeat(
        tmp_path,
        run_id=run_id,
        comparison_group=TASK40_COMPARISON_GROUP,
        source_sha="f" * 40,
    ) is None
    next_attempt = reserve(
        tmp_path,
        "review-v2-f1-after-infrastructure-recovery",
        "f" * 40,
        run_id=run_id,
    )
    assert next_attempt["replay"] is True
    assert next_attempt["replay_evidence"]["classification"] == "IMPLEMENTATION_BUG"
    final_ledger = json.loads(Path(next_attempt["path"]).read_bytes())
    assert final_ledger["unique_bug_replay_count"] == 1
    assert final_ledger["infrastructure_recovery_count"] == 1
    assert len(final_ledger["authorized_performance_repeats"]) == 1
    assert len(final_ledger["stages"]["Q4_ORIGINAL"]["attempts"]) == 3


@pytest.mark.parametrize("reverse", [False, True])
def test_task40_review_v4_cases_have_independent_one_replay_limits(tmp_path, reverse):
    old_lease = reserve(tmp_path, "legacy-first", "a" * 40)
    fail(old_lease, "b" * 40)
    old_repair = reserve(tmp_path, "legacy-repair", "b" * 40)
    fail(old_repair, "c" * 40)
    old_path = Path(old_lease["path"])
    old_bytes = old_path.read_bytes()
    cases = [
        (TASK40_GX560_RUN_ID, "review_v4_gx560"),
        (TASK40_GZ528_RUN_ID, "review_v4_gz528"),
    ]
    if reverse:
        cases.reverse()
    for run_id, batch in cases:
        first = reserve(tmp_path, batch + "-first", "d" * 40, run_id)
        assert first["replay"] is False
        accounting = first["task40_batch_replay_accounting"]
        assert accounting["selected_batch"] == batch
        assert accounting["selected_bug_replay_limit"] == 1
        assert accounting[batch]["run_ids"] == [run_id]
        assert accounting["legacy"]["unique_bug_replay_count"] == 1
        assert accounting["legacy"]["elapsed_seconds"] == 90.0
        fail(first, "e" * 40)
        second = reserve(tmp_path, batch + "-repair", "e" * 40, run_id)
        assert second["replay"] is True
        assert second["task40_batch_replay_accounting"]["selected_bug_replay_limit"] == 1
        assert second["replay_evidence"]["fixed_source_sha"] == "e" * 40
        fail(second, "f" * 40)
        path = Path(second["path"])
        settled_bytes = path.read_bytes()
        settled = json.loads(settled_bytes)
        assert settled["batch_identity"] == run_id
        assert settled["fresh_worker_count"] == 2
        assert settled["unique_bug_replay_count"] == 1
        assert settled["elapsed_seconds"] == 90.0
        with pytest.raises(InputError):
            reserve(tmp_path, batch + "-second-repair", "f" * 40, run_id)
        assert path.read_bytes() == settled_bytes
        assert old_path.read_bytes() == old_bytes


def test_task40_review_v4_unknown_run_is_rejected_without_ledger_mutation(tmp_path):
    first = reserve(tmp_path, "gx-first", "a" * 40, TASK40_GX560_RUN_ID)
    fail(first, "b" * 40)
    ledger_path = Path(first["path"])
    before = ledger_path.read_bytes()
    unknown_directory = tmp_path / "unknown"
    with pytest.raises(InputError, match="run authorized by its review batch"):
        reserve(tmp_path, "unknown", "b" * 40, TASK40_GX560_RUN_ID + "_unknown")
    assert ledger_path.read_bytes() == before
    assert not unknown_directory.exists()


@pytest.mark.parametrize("tamper", [None, "ledger", "log", "worker_started", "clearance", "reproduction", "numerical", "resource"])
def test_task40_v4_parent_import_bug_uses_the_same_single_repair(tmp_path, tamper):
    first = reserve(tmp_path, "gx-parent-failure", "a" * 40, TASK40_GX560_RUN_ID)
    launcher._settle_v14_shared_budget(
        first, status="PARENT_PREFLIGHT_OR_MONITORING_FAILURE", authority=None,
        parent_interval={"budget_seconds": 0.024}, parent_clock_end=CLOCK,
    )
    path = Path(first["path"])
    before = path.read_bytes()
    directory = tmp_path / "gx-parent-failure"
    message = "watchdog must be a dedicated parent with no existing children"
    log = ("RuntimeError: " + message + "\n").encode()
    (directory / "parent_service_failure.log").write_bytes(log)
    reproduction = b'{"child": "MPI singleton orted", "pde_started": false}'
    (directory / "parent_import_reproduction.json").write_bytes(reproduction)
    summary = {
        "status": "FAILED",
        "result_classification": "PARENT_PREFLIGHT_OR_MONITORING_FAILURE",
        "source_sha": "a" * 40,
        "worker_started": tamper == "worker_started",
        "descendants_cleared": tamper != "clearance",
        "reproduction_sha256": hashlib.sha256(reproduction).hexdigest(),
        "error": {"type": "RuntimeError", "message": message},
        "service_log_sha256": hashlib.sha256(log).hexdigest(),
    }
    if tamper in {"numerical", "resource"}:
        summary["result_classification"] = tamper.upper() + "_CONTROLLED_STOP"
    if tamper == "reproduction":
        (directory / "parent_import_reproduction.json").write_text("changed")
    (directory / "parent_startup_failure.json").write_text(json.dumps(summary))
    evidence = {
        "classification": "IMPLEMENTATION_BUG", "stage": "Q4_ORIGINAL",
        "failed_source_sha": "a" * 40, "fixed_source_sha": "b" * 40,
        "bug_and_fix": "Delay dolfinx import until FE sampling in the worker",
        "prior_ledger_sha256": hashlib.sha256(before).hexdigest(),
    }
    if tamper == "ledger":
        evidence["prior_ledger_sha256"] = "0" * 64
    if tamper == "log":
        (directory / "parent_service_failure.log").write_text("different error")
    (directory / "implementation_bug_replay.json").write_text(json.dumps(evidence))
    if tamper:
        with pytest.raises(InputError, match="repair"):
            reserve(tmp_path, "gx-parent-repair", "b" * 40, TASK40_GX560_RUN_ID)
        assert path.read_bytes() == before
        return
    repair = reserve(tmp_path, "gx-parent-repair", "b" * 40, TASK40_GX560_RUN_ID)
    assert repair["replay"] is True
    assert "parent_startup_summary_path" in repair["replay_evidence"]
    after = json.loads(path.read_bytes())
    assert after["stages"]["Q4_ORIGINAL"]["attempts"][0] == json.loads(before)["stages"]["Q4_ORIGINAL"]["attempts"][0]
    assert after["elapsed_seconds"] == 0.024
    assert after["unique_bug_replay_count"] == 1
    fail(repair, "c" * 40)
    settled = path.read_bytes()
    with pytest.raises(InputError, match="exhausted"):
        reserve(tmp_path, "gx-second-repair", "c" * 40, TASK40_GX560_RUN_ID)
    assert path.read_bytes() == settled
