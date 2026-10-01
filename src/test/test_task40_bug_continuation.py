"""Task40 continuation keeps failure evidence and all numerical stop semantics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.geometry.task40_nonseparable_plan import (
    TASK40_COMPARISON_GROUP,
    TASK40_F1_REFERENCE_METRIC_RUN_ID,
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
