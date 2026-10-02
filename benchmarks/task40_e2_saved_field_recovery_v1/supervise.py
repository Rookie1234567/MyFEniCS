#!/usr/bin/env python3
"""Run and finalize the one-off E2 recovery under the existing subreaper."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path("/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering")
RUN_ROOT = ROOT / (
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_e2_manual_m2_growth_v1__full3d_iterative__mpi1__Mna/"
    "20261002T023827.030745Z"
)
REPAIR_ROOT = RUN_ROOT / "postprocess_repair_v1"
WATCHDOG_DIR = REPAIR_ROOT / "watchdog"
RECORD = REPAIR_ROOT / "repair_record.json"
ENTRY = ROOT / "benchmarks/task40_e2_saved_field_recovery_v1"


def watchdog_gate_checks(summary: Mapping[str, Any], last_sample: Mapping[str, Any]) -> dict[str, bool]:
    """Check the established watchdog's run, identity, swap, PSS, and cleanup evidence."""
    remaining = summary.get("remaining_child_pids", [])
    rss_peak = summary.get("sampled_process_tree_rss_peak_bytes")
    return {
        "classification_completed": summary.get("classification") == "COMPLETED",
        "worker_exit_zero": summary.get("leader_exit_code") == 0,
        "observe_only_conservative_clock": (
            summary.get("time_policy") == "observe_only"
            and summary.get("timebase_policy") == "conservative_realtime"
        ),
        "physical_memory_policy": summary.get("memory_policy") == "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        "process_tree_swap_gate_enforced": summary.get("process_tree_swap_gate_enforced") is True,
        "sample_present": bool(summary.get("process_tree_samples")),
        "last_sample_identity_complete": last_sample.get("identity_complete") is True,
        "last_sample_status_readable": last_sample.get("all_status_readable") is True,
        "process_tree_status_readable": summary.get("process_tree_all_status_readable") is True,
        "process_tree_identity_complete": summary.get("process_tree_all_identity_complete") is True,
        "identity_coverage_complete": summary.get("process_tree_identity_coverage") == "complete",
        "rss_peak_measured": isinstance(rss_peak, int) and rss_peak > 0,
        "process_tree_swap_zero": summary.get("sampled_process_tree_swap_peak_bytes") == 0,
        "descendants_cleared": summary.get("descendants_cleared") is True and not remaining,
        "pss_disabled_and_null": (
            summary.get("pss_sampling_policy") == "disabled_by_profile"
            and summary.get("sampled_process_tree_pss_peak_bytes") is None
            and last_sample.get("pss_sampling_policy") == "disabled_by_profile"
            and last_sample.get("pss_status") == "DISABLED_BY_PROFILE"
            and last_sample.get("pss_bytes") is None
        ),
    }


def recovery_failure_record(
    summary: Mapping[str, Any],
    worker_tail: list[str],
    *,
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "task40extra.e2.saved-field-postprocess-repair.v1",
        "status": "OFFLINE_RECOVERY_WORKER_FAILED_ORIGINAL_RUN_FAILED",
        "classification": "RECOVERY_WORKER_FAILED; ORIGINAL_E2_WORKER_FAILED_PRESERVED",
        "failure": {
            "worker_exit_code": summary.get("leader_exit_code"),
            "watchdog_classification": summary.get("classification"),
            "worker_log_tail": worker_tail,
        },
        "repair_identity": dict(source_identity),
        "original_worker_result_mutated": False,
    }


def _last_resource_sample(path: Path) -> dict[str, Any]:
    last_line = None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            last_line = line
    return {} if last_line is None else json.loads(last_line)


def main() -> int:
    assert os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
    assert Path(sys.executable).resolve().is_relative_to((ROOT / ".venv").resolve())
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert branch == "task40extra_0p7nm_engineering"
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    assert REPAIR_ROOT.is_dir() and not WATCHDOG_DIR.exists()

    from benchmarks.subreaper_watchdog import PHYSICAL_MEMORY_PRESSURE_POLICY, supervise

    summary = supervise(
        [sys.executable, "-u", "-m", "benchmarks.task40_e2_saved_field_recovery_v1.recover"],
        WATCHDOG_DIR,
        wall_seconds=43200.0,
        interval=0.25,
        grace_seconds=30.0,
        source_state={
            "branch": branch,
            "source_sha": head,
            "purpose": "E2 saved-field postprocessing recovery",
        },
        hard_stop_immediate=True,
        timebase_guard=True,
        timebase_policy="conservative_realtime",
        stop_on_global_swap=False,
        allow_swap_observation=False,
        time_policy="observe_only",
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
    )
    last_sample = _last_resource_sample(WATCHDOG_DIR / "resources.jsonl")
    checks = watchdog_gate_checks(summary, last_sample)
    watchdog_passed = all(checks.values())
    worker_log = WATCHDOG_DIR / "worker.log"
    worker_tail = [
        line[:2000]
        for line in worker_log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
    ]
    source_identity = {
        "recovery_source_branch": branch,
        "recovery_source_sha": head,
        "recovery_source_clean": True,
        "recovery_driver_sha256": hashlib.sha256((ENTRY / "recover.py").read_bytes()).hexdigest(),
        "recovery_launcher_sha256": hashlib.sha256((ENTRY / "launch.sh").read_bytes()).hexdigest(),
        "recovery_supervisor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "supervisor_command": "python -u -m benchmarks.task40_e2_saved_field_recovery_v1.supervise",
        "worker_command": "python -u -m benchmarks.task40_e2_saved_field_recovery_v1.recover",
    }
    if RECORD.exists():
        record = json.loads(RECORD.read_text(encoding="utf-8"))
    else:
        record = recovery_failure_record(summary, worker_tail, source_identity=source_identity)
    record.setdefault("additional_cost", {})
    record.setdefault("repair_identity", {}).update(source_identity)
    record["additional_cost"]["process_tree_watchdog"] = {
        "timebase_policy": summary.get("timebase_policy"),
        "time_policy": summary.get("time_policy"),
        "memory_policy": summary.get("memory_policy"),
        "memory_scope": summary.get("memory_scope"),
        "swap_scope": summary.get("swap_scope"),
        "process_tree_rss_peak_bytes": summary.get("sampled_process_tree_rss_peak_bytes"),
        "process_tree_swap_peak_bytes": summary.get("sampled_process_tree_swap_peak_bytes"),
        "pss_sampling_policy": summary.get("pss_sampling_policy"),
        "pss_status": summary.get("pss_status"),
        "sampled_process_tree_pss_peak_bytes": summary.get("sampled_process_tree_pss_peak_bytes"),
        "process_tree_sample_count": len(summary.get("process_tree_samples", [])),
        "process_tree_all_status_readable": summary.get("process_tree_all_status_readable"),
        "process_tree_all_identity_complete": summary.get("process_tree_all_identity_complete"),
        "process_tree_identity_coverage": summary.get("process_tree_identity_coverage"),
        "descendants_cleared": summary.get("descendants_cleared"),
        "remaining_child_pids": summary.get("remaining_child_pids", []),
        "watchdog_classification": summary.get("classification"),
        "watchdog_checks": checks,
        "watchdog_gate_passed": watchdog_passed,
        "watchdog_summary_sha256": hashlib.sha256((WATCHDOG_DIR / "summary.json").read_bytes()).hexdigest(),
        "watchdog_resources_sha256": hashlib.sha256((WATCHDOG_DIR / "resources.jsonl").read_bytes()).hexdigest(),
        "worker_log_sha256": hashlib.sha256(worker_log.read_bytes()).hexdigest(),
    }
    if not watchdog_passed and record.get("status") == "POSTPROCESS_REPAIR_COMPLETE_ORIGINAL_RUN_FAILED":
        record["status"] = "POSTPROCESS_OUTPUTS_RECOVERED_WATCHDOG_GATE_FAIL_ORIGINAL_RUN_FAILED"
    record["original_worker_result_mutated"] = False
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(RECORD.read_bytes()).hexdigest()
    RECORD.with_name("repair_record.sha256").write_text(f"{digest}  repair_record.json\n")
    print(json.dumps({
        "watchdog_gate_passed": watchdog_passed,
        "watchdog_checks": checks,
        "classification": summary.get("classification"),
        "process_tree_rss_peak_bytes": summary.get("sampled_process_tree_rss_peak_bytes"),
        "process_tree_swap_peak_bytes": summary.get("sampled_process_tree_swap_peak_bytes"),
        "descendants_cleared": summary.get("descendants_cleared"),
        "record_sha256": digest,
    }, sort_keys=True), flush=True)
    return 0 if watchdog_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
