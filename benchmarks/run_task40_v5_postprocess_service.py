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

from src.runners.workflow_timebase import clock_sample


ROOT = Path(__file__).resolve().parents[1]
GX784_RUN_ID = "task40extra_0p7nm_nonseparable_gx784_review_v5_v1"
WORKER_SUMMARY_NAME = "task40extra_nonseparable_0p7nm_p6q4_summary.json"
PHYSICAL_MEMORY_PRESSURE_POLICY = "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _preflight_case(case_root: Path) -> dict[str, Any]:
    """Check only the Gx784 solver gate and its retained-vector archive."""

    from benchmarks import check_task40_review_v5_gx784 as checker

    case_root = case_root.resolve()
    manifest_path = case_root / "run_manifest.json"
    run_summary_path = case_root / "run_summary.json"
    worker_summary_path = case_root / WORKER_SUMMARY_NAME
    for path in (manifest_path, run_summary_path, worker_summary_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Gx784 preflight evidence is missing: {path}")
    manifest = _read_json(manifest_path)
    run_summary = _read_json(run_summary_path)
    worker_summary = _read_json(worker_summary_path)
    if manifest.get("run_id") != GX784_RUN_ID:
        raise ValueError("postprocessing root is not the frozen Gx784 run")
    if run_summary.get("run_id") != manifest.get("run_id"):
        raise ValueError("Gx784 run manifest and run summary identities differ")
    if (
        run_summary.get("status") != manifest.get("status")
        or run_summary.get("result_classification")
        != manifest.get("result_classification")
        or run_summary.get("exit_status") != manifest.get("exit_status")
    ):
        raise ValueError("Gx784 run manifest and run summary outcomes differ")
    if worker_summary.get("source_sha") != manifest.get("source_sha"):
        raise ValueError("Gx784 worker summary source SHA differs from its run manifest")
    if worker_summary.get("profile") != "task40extra_0p7nm_p6trace_p4_reference_metric_v2":
        raise ValueError("Gx784 worker summary profile differs from the frozen reference profile")
    if worker_summary.get("result_classification") != manifest.get(
        "result_classification"
    ):
        raise ValueError("Gx784 worker summary classification differs from its run manifest")
    solver_gate = checker._recompute_solver_gate(worker_summary)
    field_artifact: dict[str, Any] = {
        "checked": False,
        "complete": False,
        "archive_path": None,
        "expected_sha256": None,
        "actual_sha256": None,
        "failure_reason": None,
    }
    if solver_gate["pass"]:
        packet_path = case_root / "x2_retained_final.json"
        if not packet_path.is_file() or packet_path.stat().st_size == 0:
            field_artifact["failure_reason"] = "Gx784 retained-field packet is missing"
        else:
            try:
                packet = _read_json(packet_path)
                arrays = packet.get("arrays", {})
                archive_value = arrays.get("path")
                expected_sha = arrays.get("sha256")
                archive_path = Path(str(archive_value)) if archive_value else Path()
                if not archive_path.is_absolute():
                    archive_path = (case_root / archive_path).resolve()
                field_artifact.update(
                    {
                        "checked": True,
                        "packet_sha256": _sha256(packet_path),
                        "archive_path": str(archive_path),
                        "expected_sha256": expected_sha,
                    }
                )
                if (
                    not isinstance(expected_sha, str)
                    or len(expected_sha) != 64
                    or not archive_path.is_file()
                    or archive_path.stat().st_size == 0
                ):
                    field_artifact["failure_reason"] = (
                        "Gx784 retained vector archive or its saved SHA is missing"
                    )
                else:
                    actual_sha = _sha256(archive_path)
                    field_artifact["actual_sha256"] = actual_sha
                    packet_identity = packet.get("identity", {})
                    identity_matches = (
                        packet_identity.get("source_sha") == manifest.get("source_sha")
                        and packet_identity.get("physical_model_sha256")
                        == manifest.get("physical_model_sha256")
                    )
                    field_artifact["packet_identity_matches_manifest"] = identity_matches
                    field_artifact["complete"] = (
                        actual_sha == expected_sha and identity_matches
                    )
                    if actual_sha != expected_sha:
                        field_artifact["failure_reason"] = (
                            "Gx784 retained vector archive SHA differs from its saved packet SHA"
                        )
                    elif not identity_matches:
                        field_artifact["failure_reason"] = (
                            "Gx784 retained-field packet identity differs from its manifest"
                        )
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                field_artifact["failure_reason"] = (
                    f"Gx784 retained-field packet is unreadable: {exc}"
                )
    return {
        "case_root": str(case_root),
        "run_id": GX784_RUN_ID,
        "run_manifest_path": str(manifest_path),
        "run_manifest_sha256": _sha256(manifest_path),
        "run_summary_path": str(run_summary_path),
        "run_summary_sha256": _sha256(run_summary_path),
        "worker_summary_path": str(worker_summary_path),
        "worker_summary_sha256": _sha256(worker_summary_path),
        "source_sha": manifest["source_sha"],
        "solver_gate": solver_gate,
        "field_artifact_preflight": field_artifact,
        "ready_for_supervised_field_work": bool(
            solver_gate["pass"] and field_artifact["complete"]
        ),
    }


def _write_held_comparison(
    preflight: dict[str, Any], *, source_sha: str, branch: str
) -> dict[str, Any]:
    """Write a compact held result without reserving time or starting a worker."""

    from benchmarks import check_task40_review_v5_gx784 as checker

    case_root = Path(preflight["case_root"])
    post_root = case_root / "postprocess_v5" / "preflight_held_v1"
    post_root.mkdir(parents=True, exist_ok=True)
    comparison_path = post_root / "gx784_pair_comparisons.json"
    checker_path = post_root / "gx784_independent_check.json"
    if comparison_path.exists() or checker_path.exists():
        raise FileExistsError(f"refusing to overwrite V5 held preflight output: {post_root}")
    gate = preflight["solver_gate"]
    payload = {
        "schema": "task40extra.review-v5.gx784-paired-comparison.v1",
        "status": "completed",
        "classification": (
            "solver_or_recovery_gate_not_passed_comparison_held"
            if not gate["pass"]
            else "saved_field_archive_missing_or_hash_mismatch_comparison_held"
        ),
        "analysis_source": {
            "branch": branch,
            "source_sha": source_sha,
            "worker_started": False,
        },
        "solver_evidence": {
            "path": preflight["worker_summary_path"],
            "sha256": preflight["worker_summary_sha256"],
            "run_id": preflight["run_id"],
            "run_manifest_path": preflight["run_manifest_path"],
            "run_manifest_sha256": preflight["run_manifest_sha256"],
            "source_sha": preflight["source_sha"],
        },
        "solver_preflight_diagnostics": gate,
        "field_artifact_preflight": preflight["field_artifact_preflight"],
        "comparison_status": "held_before_FE_import_field_restoration_and_power_comparison",
    }
    _write_json(comparison_path, payload)
    checked = checker.check_payload(payload)
    checked["source_result_path"] = str(comparison_path)
    checked["source_result_sha256"] = _sha256(comparison_path)
    _write_json(checker_path, checked)
    return {
        "status": "POSTPROCESS_HELD_BEFORE_WORKER",
        "branch": branch,
        "source_sha": source_sha,
        "case_root": str(case_root),
        "postprocess_root": str(post_root),
        "worker_started": False,
        "budget_reserved": False,
        "watchdog_summary": None,
        "watchdog_gate_passed": False,
        "comparison_path": str(comparison_path),
        "comparison_sha256": _sha256(comparison_path),
        "checker_path": str(checker_path),
        "checker_sha256": _sha256(checker_path),
        "checker_record": checked,
        "preflight": preflight,
    }


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
    preflight_start = time.monotonic()
    workflow_start = clock_sample()
    branch, source_sha = _git_facts()
    case_root = case_root.resolve()
    manifest = _read_json(case_root / "run_manifest.json")
    preflight = _preflight_case(case_root)
    preflight["elapsed_monotonic_seconds"] = time.monotonic() - preflight_start
    if not preflight["ready_for_supervised_field_work"]:
        return _write_held_comparison(
            preflight,
            source_sha=source_sha,
            branch=branch,
        )

    # This legacy API imports NumPy but no FE/MPI stack.  Defer it until the
    # stdlib-only solver and saved-file gates have established that work exists.
    from src.runners.task038_launcher import (
        _reserve_task40_v5_postprocess_budget,
        _settle_task40_v5_postprocess_budget,
    )

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
        from benchmarks.subreaper_watchdog import (
            PHYSICAL_MEMORY_PRESSURE_POLICY,
            supervise,
        )

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
