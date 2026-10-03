"""Run V5 saved-field comparison/checker under the existing subreaper watchdog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
    _qualified_environment,
    _read_json,
    _write_json,
)
from benchmarks.subreaper_watchdog import (
    PHYSICAL_MEMORY_PRESSURE_POLICY,
    supervise,
)
from src.runners.task038_launcher import (
    _reserve_task40_v5_postprocess_budget,
    _settle_task40_v5_postprocess_budget,
)
from src.runners.workflow_timebase import clock_sample


ROOT = Path(__file__).resolve().parents[1]


def _git_facts() -> tuple[str, str]:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    if branch != "task40extra_0p7nm_engineering" or status:
        raise RuntimeError("V5 postprocessing requires the clean committed Task40 source")
    return branch, source_sha


def _last_sample(path: Path) -> dict[str, Any]:
    last = None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            last = line
    return {} if last is None else json.loads(last)


def _watchdog_checks(summary: dict[str, Any], last: dict[str, Any]) -> dict[str, bool]:
    return {
        "completed": summary.get("classification") == "COMPLETED",
        "worker_exit_zero": summary.get("leader_exit_code") == 0,
        "enforced_conservative_clock": (
            summary.get("time_policy") == "enforce"
            and summary.get("timebase_policy") == "conservative_realtime"
        ),
        "physical_memory_pressure_policy": (
            summary.get("memory_policy") == PHYSICAL_MEMORY_PRESSURE_POLICY
        ),
        "process_tree_swap_gate_enforced": (
            summary.get("process_tree_swap_gate_enforced") is True
        ),
        "process_tree_swap_zero": (
            summary.get("sampled_process_tree_swap_peak_bytes") == 0
        ),
        "samples_present": (
            isinstance(summary.get("process_tree_samples"), int)
            and summary.get("process_tree_samples", 0) > 0
        ),
        "last_sample_readable_and_identified": (
            last.get("all_status_readable") is True
            and last.get("identity_complete") is True
        ),
        "whole_tree_readable_and_identified": (
            summary.get("process_tree_all_status_readable") is True
            and summary.get("process_tree_all_identity_complete") is True
            and summary.get("process_tree_identity_coverage") == "complete"
        ),
        "descendants_cleared": (
            summary.get("descendants_cleared") is True
            and not summary.get("remaining_child_pids", [])
        ),
        "pss_disabled_by_profile": (
            summary.get("pss_sampling_policy") == "disabled_by_profile"
            and summary.get("sampled_process_tree_pss_peak_bytes") is None
        ),
    }


def _run(case_root: Path, implementation_bug_evidence: Path | None) -> dict[str, Any]:
    workflow_start = clock_sample()
    env = _qualified_environment()
    if env.get("mpi_size") != 1:
        raise RuntimeError("V5 postprocessing is frozen to MPI size one")
    branch, source_sha = _git_facts()
    case_root = case_root.resolve()
    manifest = _read_json(case_root / "run_manifest.json")
    if manifest.get("run_id") != "task40extra_0p7nm_nonseparable_gx784_review_v5_v1":
        raise ValueError("postprocessing run root is not the authorized Gx784 case")
    run_ledger_path = (
        ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering"
        / "task40_nonseparable_0p7nm"
        / manifest["run_id"]
        / "shared_workflow_ledger.json"
    )
    old_ledger = _read_json(run_ledger_path)
    previous = old_ledger.get("stages", {}).get("V5_POSTPROCESS", {})
    previous_attempts = previous.get("attempts", []) if isinstance(previous, dict) else []
    attempt_number = len(previous_attempts) + 1
    if attempt_number > 2:
        raise RuntimeError("V5 comparison/checker is limited to one implementation-bug replay")
    post_root = case_root / "postprocess_v5" / f"attempt{attempt_number}"
    if post_root.exists():
        raise FileExistsError(f"V5 postprocessing attempt output already exists: {post_root}")
    post_root.mkdir(parents=True)
    lease = _reserve_task40_v5_postprocess_budget(
        ROOT,
        source_sha=source_sha,
        run_directory=post_root,
        workflow_clock_start=workflow_start,
        implementation_bug_replay=(
            _read_json(implementation_bug_evidence)
            if implementation_bug_evidence is not None
            else None
        ),
    )
    watchdog_dir = post_root / "watchdog"
    comparison_path = post_root / "gx784_pair_comparisons.json"
    command = [
        sys.executable,
        "-u",
        "-m",
        "benchmarks.postprocess_task40_review_v5_gx784",
        "--gx784-root",
        str(case_root),
        "--output",
        str(comparison_path),
    ]
    worker_status = "POSTPROCESS_PARENT_FAILED"
    summary = None
    error: str | None = None
    try:
        summary = supervise(
            command,
            watchdog_dir,
            wall_seconds=float(lease["reserved_seconds"]),
            solve_seconds=float(lease["reserved_seconds"]),
            interval=0.25,
            grace_seconds=30.0,
            source_state={
                "branch": branch,
                "source_sha": source_sha,
                "purpose": "Task40 Review V5 Gx784 paired saved-field comparison and independent checker",
                "run_id": manifest["run_id"],
                "shared_ledger_path": lease["path"],
                "shared_ledger_attempt": lease["attempt_index"] + 1,
                "reserved_seconds": lease["reserved_seconds"],
            },
            hard_stop_immediate=True,
            timebase_guard=True,
            timebase_policy="conservative_realtime",
            stop_on_global_swap=False,
            allow_swap_observation=False,
            time_policy="enforce",
            memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
            pss_sampling_policy="disabled_by_profile",
        )
        worker_status = (
            "POSTPROCESS_WORKER_COMPLETED"
            if summary.get("classification") == "COMPLETED"
            and summary.get("leader_exit_code") == 0
            else "POSTPROCESS_WORKER_FAILED_OR_CONTROLLED_STOP"
        )
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        watchdog_summary = watchdog_dir / "summary.json"
        last = _last_sample(watchdog_dir / "resources.jsonl") if (
            watchdog_dir / "resources.jsonl"
        ).is_file() else {}
        checks = {} if summary is None else _watchdog_checks(summary, last)
        watcher_passed = bool(checks) and all(checks.values())
        worker_tail = []
        worker_log = watchdog_dir / "worker.log"
        if worker_log.is_file():
            worker_tail = worker_log.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()[-30:]
        record = {
            "schema": "task40extra.review-v5.gx784-postprocess-supervision.v1",
            "status": worker_status,
            "branch": branch,
            "source_sha": source_sha,
            "source_clean_before_worker": True,
            "case_root": str(case_root),
            "postprocess_root": str(post_root),
            "shared_ledger_path": lease["path"],
            "shared_ledger_attempt_index": lease["attempt_index"],
            "reserved_remaining_seconds": lease["reserved_seconds"],
            "time_policy": "enforce",
            "watchdog_summary": summary,
            "watchdog_summary_sha256": (
                hashlib.sha256(watchdog_summary.read_bytes()).hexdigest()
                if watchdog_summary.is_file()
                else None
            ),
            "watchdog_resources_sha256": (
                hashlib.sha256((watchdog_dir / "resources.jsonl").read_bytes()).hexdigest()
                if (watchdog_dir / "resources.jsonl").is_file()
                else None
            ),
            "watchdog_checks": checks,
            "watchdog_gate_passed": watcher_passed,
            "comparison_path": str(comparison_path),
            "comparison_sha256": (
                hashlib.sha256(comparison_path.read_bytes()).hexdigest()
                if comparison_path.is_file()
                else None
            ),
            "worker_log_tail": worker_tail,
            "error": error,
        }
        _write_json(post_root / "supervisor_result.json", record)
        settled = _settle_task40_v5_postprocess_budget(
            lease,
            status=(
                "POSTPROCESS_WATCHDOG_PASS" if watcher_passed else worker_status
            ),
            watchdog_summary_path=watchdog_summary,
            parent_clock_end=clock_sample(),
        )
        record["settlement"] = settled
        record["actual_run_time_seconds"] = settled["settled_seconds"]
        record["effective_budget_after_settlement"] = settled[
            "effective_budget_after_settlement"
        ]
        _write_json(post_root / "supervisor_result.json", record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--implementation-bug-evidence", type=Path)
    args = parser.parse_args()
    record = _run(args.case_root, args.implementation_bug_evidence)
    print(
        json.dumps(
            {
                "status": record["status"],
                "watchdog_gate_passed": record["watchdog_gate_passed"],
                "actual_run_time_seconds": record.get("actual_run_time_seconds"),
                "effective_budget_after_settlement": record.get(
                    "effective_budget_after_settlement"
                ),
                "postprocess_root": record["postprocess_root"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if record["watchdog_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
