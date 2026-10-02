"""Thin Q0--Q2 two-cell p4 audit CLI; no factor or solver option exists.

The existing sparse runner couples operator audit with global q factors and
solve/recovery. This entrypoint calls only the separate src audit API and
retains the same source/ABI/supervision and artifact mechanisms.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
TREE_CAP_BYTES = 3 * 1024**3 // 2
RESERVE_BYTES = 128 * 1024**2
WALL_SECONDS = 600
PASS = "QUOTIENT_OPERATOR_AUDIT_PASS"
SCHEMA = "task40extra.y-orbit-two-cell-operator-audit.v1"


def apply_supervisor_classification(report, classification):
    """Retain a numerical negative instead of relabeling it a resource stop."""
    if classification == "COMPLETED":
        return report
    report["supervisor_classification"] = classification
    report["worker_status_before_supervisor_classification"] = report.get("status")
    if report.get("status") == "QUOTIENT_OPERATOR_AUDIT_FAILED":
        return report
    if classification == "WORKER_FAILED":
        report["status"] = "QUOTIENT_OPERATOR_AUDIT_FAILED"
    elif classification and "CONTROLLED_STOP" in classification:
        report["status"] = "QUOTIENT_OPERATOR_AUDIT_CONTROLLED_STOP"
    else:
        report["status"] = "QUOTIENT_OPERATOR_AUDIT_SUPERVISION_FAILED"
    return report


def preserve_supervisor_failure(directory, *, stage, source, environment, command, exc):
    """Do not fabricate a completed watchdog receipt when launch itself fails."""
    from src.solvers.real_p4_probe import file_sha256, write_json
    directory.mkdir(parents=True, exist_ok=True)
    summary_relative = "summary.json" if stage == "audit" else "checker_supervision/summary.json"
    summary_path = directory / summary_relative
    failure = {"classification": "SUPERVISION_FAILED", "stage": stage,
               "source": source, "environment": environment, "command": command,
               "degree": 4, "factor_count": 0, "error_type": type(exc).__name__, "error": str(exc),
               "supervisor_receipt": {"path": summary_relative, "sha256": file_sha256(summary_path)}
               if summary_path.is_file() else None, "completed_supervision_claimed": False}
    write_json(directory / (stage + "_supervision_failure.json"), failure)
    (directory / (stage + "_supervision_traceback.txt")).write_text(traceback.format_exc())
    report_path = directory / "audit_report.json"
    if stage == "audit":
        report = json.loads(report_path.read_text()) if report_path.is_file() else {
            "schema": SCHEMA, "degree": 4, "factor_count": 0, "source": source,
            "environment": environment, "PDE_solved": False, "official_results": False, "audit_only": True}
        report["worker_status_before_supervisor_failure"] = report.get("status")
        report["status"] = "QUOTIENT_OPERATOR_AUDIT_SUPERVISION_FAILED"
        report["supervisor_receipt"] = failure["supervisor_receipt"]
        manifest = directory / "artifact_manifest.json"
        report["artifacts"] = json.loads(manifest.read_text()) if manifest.is_file() else report.get("artifacts", {})
        write_json(report_path, report)
    else:
        write_json(directory / "checker_incomplete.json", {"gate_pass": False, "evidence_valid": False,
            "classification": "SUPERVISION_FAILED", "supervisor_receipt": failure["supervisor_receipt"],
            "no_solver_qualification": True})


def _worker(args):
    from benchmarks.run_real_p4_probe import source_facts, environment_facts
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot, append_jsonl
    from benchmarks.subreaper_watchdog import memory_envelope, runtime_tree_cap
    from benchmarks.y_orbit_two_cell_authority import SavedFullP4Authority, AUTHORITY_RUN
    from src.solvers.real_p4_probe import file_sha256, write_json

    started = time.monotonic()
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    source = None
    environment = None
    descriptors = {}
    authority = None
    report = {"schema": SCHEMA, "status": "STARTED", "degree": 4, "factor_count": 0,
              "audit_only": True, "PDE_solved": False, "official_results": False}

    def event(name, facts):
        payload = {"event": name, "worker_elapsed_seconds": time.monotonic() - started, **facts}
        append_jsonl(args.run_directory / "audit_events.jsonl", payload)
        write_json(args.run_directory / "phase.json", {"phase": name, "factor_count": 0,
                                                       "worker_elapsed_seconds": payload["worker_elapsed_seconds"]})
        print(json.dumps(payload, allow_nan=False), flush=True)

    def global_swap():
        values = {}
        for line in Path("/proc/vmstat").read_text().splitlines():
            key, value = line.split()
            if key in ("pswpin", "pswpout"):
                values[key] = int(value)
        if set(values) != {"pswpin", "pswpout"}:
            raise RuntimeError("readable global swap counters are required")
        return values

    swap_baseline = global_swap()

    def allocation_gate(name, facts):
        if any(int(facts.get(field, 0)) != 0 for field in
               ("factor_count", "factor_workspace_allowance_bytes", "declared_factor_workspace_allowance_bytes")):
            raise ValueError("Q0-Q2 prohibits q factors and the future 512MiB factor allowance")
        if time.monotonic() - started >= WALL_SECONDS:
            raise TimeoutError("Q0-Q2 workflow budget expired before allocation")
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if (sample.get("all_status_readable") is not True or sample.get("identity_complete") is not True
                or sample.get("swap_bytes") != 0 or global_swap() != swap_baseline):
            raise RuntimeError("per-allocation readable whole-tree identity and zero global/tree swap required")
        payload = int(facts.get("matrix_payload_bytes", facts.get("retained_numeric_bytes_upper", 0)))
        workspace = int(facts.get("workspace_bytes", 0))
        reserve = max(RESERVE_BYTES, int(facts.get("evidence_reserve_bytes", 0)))
        if min(payload, workspace, reserve) < 0:
            raise ValueError("negative allocation declaration")
        projected = int(sample["rss_bytes"]) + payload + workspace + reserve
        envelope = memory_envelope()
        effective_cap = runtime_tree_cap(cap, int(sample["rss_bytes"]), envelope,
                                         explicit_tree_cap_bytes=TREE_CAP_BYTES)
        event("allocation_admission", {"boundary": name, "current_tree_rss_bytes": sample["rss_bytes"],
              "additional_payload_bytes": payload, "declared_workspace_bytes": workspace,
              "evidence_reserve_bytes": reserve, "projected_tree_bytes": projected,
              "launch_cap_bytes": cap, "effective_tree_cap_bytes": effective_cap,
              "fresh_memory_envelope": envelope, "admitted": projected < effective_cap,
              "global_swap_counters": swap_baseline, "facts": facts})
        if projected >= effective_cap:
            raise MemoryError("fresh measured whole-tree allocation plus evidence reserve exceeds cap")

    def save_array(name, values):
        import numpy as np
        if not re.fullmatch(r"[A-Za-z0-9_]+", name) or name in descriptors:
            raise ValueError("artifact names must be unique safe identifiers")
        if isinstance(values, np.ndarray):
            workspace = (1 << 20) + (0 if values.flags.c_contiguous or values.flags.f_contiguous else int(values.nbytes))
            allocation_gate("save_array_" + name, {"matrix_payload_bytes": 0, "workspace_bytes": workspace})
        elif isinstance(values, (np.number, bool, int, float, complex)):
            allocation_gate("save_scalar_array_" + name, {"matrix_payload_bytes": 64, "workspace_bytes": 1 << 20})
        else:
            raise TypeError("artifact writer requires an existing ndarray or bounded scalar; admit list conversion in numerical code first")
        values = np.asarray(values)
        if values.dtype.hasobject:
            raise ValueError("object artifact forbidden")
        path = args.run_directory / "arrays" / (name + ".npy")
        temporary = path.with_suffix(".npy.tmp")
        with temporary.open("xb") as stream:
            np.save(stream, values, allow_pickle=False)
        temporary.replace(path)
        finite_entries = values.size
        if values.dtype.kind in "fc":
            flat = values.ravel(order="K")
            finite_entries = sum(int(np.count_nonzero(np.isfinite(flat[start:start + 65536])))
                                 for start in range(0, flat.size, 65536))
        descriptors[name] = {"path": str(path.relative_to(args.run_directory)),
                             "shape": list(values.shape), "dtype": str(values.dtype),
                             "payload_bytes": int(values.nbytes), "file_sha256": file_sha256(path),
                             "finite_entries": int(finite_entries),
                             "nonfinite_entries": int(values.size - finite_entries),
                             "raw_failure_diagnostic_only": finite_entries != values.size}
        write_json(args.run_directory / "artifact_manifest.json", descriptors)
        return dict(descriptors[name])

    try:
        if parent <= 0 or parent != os.getppid() or not 0 < cap <= TREE_CAP_BYTES:
            raise RuntimeError("worker requires its direct 1.5GiB whole-tree subreaper watchdog")
        if os.environ.get("PHYSICAL_TIMEBASE_GUARD") != "1":
            raise RuntimeError("strict supervised workflow timebase is required")
        source = source_facts(args.expected_head)
        environment = environment_facts()
        if file_sha256(INPUT) != INPUT_SHA:
            raise ValueError("frozen input hash differs")
        args.run_directory.joinpath("arrays").mkdir()
        resource = {"tree_cap_bytes": cap, "wall_seconds": WALL_SECONDS, "swap_bytes": 0,
                    "mpi": 1, "math_threads": 1, "evidence_reserve_bytes": RESERVE_BYTES,
                    "factor_count": 0, "factor_workspace_allowance_bytes": 0,
                    "future_factor_allowance_not_authorized_bytes": 512 * 1024**2,
                    "performance_or_target_capacity_claim": False}
        provenance = {"source": source, "environment": environment, "command": sys.argv,
                      "input_sha256": INPUT_SHA, "resource_contract": resource,
                      "schema": SCHEMA, "audit_only": True, "degree": 4}
        write_json(args.run_directory / "provenance.json", provenance)
        shutil.copyfile(environment["qualification_manifest"], args.run_directory / "abi_manifest.json")
        write_json(args.run_directory / "audit_report.json", {**report, "source": source,
                                                              "environment": environment})
        allocation_gate("authority_metadata_validation", {"matrix_payload_bytes": 4 << 20,
                                                          "workspace_bytes": 4 << 20})
        authority = SavedFullP4Authority(ARTIFACT_ROOT / AUTHORITY_RUN, new_source=source,
                                        new_environment=environment, allocation_gate=allocation_gate)
        provenance["saved_full_p4_authority"] = authority.receipt
        write_json(args.run_directory / "provenance.json", provenance)
        # Only this audit API is imported. No q-factor or later solver dispatch.
        from src.solvers.y_orbit_two_cell_audit import run_two_cell_operator_audit
        report = run_two_cell_operator_audit(INPUT, authority=authority, event=event,
                                             save_array=save_array, allocation_gate=allocation_gate,
                                             run_directory=args.run_directory)
        if (report.get("status") != PASS or report.get("factor_count") != 0
                or report.get("degree") != 4 or report.get("PDE_solved") is not False
                or report.get("official_results") is not False):
            raise ValueError("audit API did not return the bounded no-factor/no-PDE contract")
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source changed during quotient audit")
        report.update(schema=SCHEMA, source=source, environment=environment, source_clean_unchanged=True,
                      artifacts=descriptors, authority=authority.receipt, audit_only=True,
                      worker_elapsed_seconds=time.monotonic() - started)
        write_json(args.run_directory / "audit_report.json", report)
        event("audit_complete", {"status": report["status"], "factor_count": 0})
        return 0
    except Exception as exc:
        report.update(schema=SCHEMA, status="QUOTIENT_OPERATOR_AUDIT_FAILED", degree=4,
                      source=source, environment=environment, artifacts=descriptors,
                      source_clean_unchanged=None,
                      factor_count=report.get("factor_count", 0),
                      error_type=type(exc).__name__, error=str(exc), audit_only=True,
                      PDE_solved=report.get("PDE_solved", False),
                      official_results=report.get("official_results", False),
                      worker_elapsed_seconds=time.monotonic() - started)
        if authority is not None:
            report["authority"] = authority.receipt
        write_json(args.run_directory / "audit_report.json", report)
        (args.run_directory / "audit_traceback.txt").write_text(traceback.format_exc())
        event("audit_failure", {"error_type": type(exc).__name__, "error": str(exc)})
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head")
    parser.add_argument("--run-directory", type=Path)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps({"status": "NOT_RUN_STAGED_PLAN_ONLY", "degree": 4,
                          "scope": "Q0-Q2 two-cell all-four-q operator audit only",
                          "factor_count": 0, "PDE_solved": False, "official_results": False,
                          "tree_cap_bytes": TREE_CAP_BYTES, "wall_seconds": WALL_SECONDS,
                          "mpi": 1, "math_threads": 1, "swap_bytes": 0,
                          "evidence_reserve_bytes": RESERVE_BYTES}, indent=2))
        return 0
    if not args.expected_head or not args.run_directory:
        parser.error("audit requires exact clean integrated HEAD and a fresh ignored run directory")
    args.run_directory = args.run_directory.resolve()
    if not args.run_directory.is_relative_to(ARTIFACT_ROOT.resolve()):
        parser.error("audit evidence must remain within the own ignored artifact subtree")
    if not (ROOT / "AGENTS.md").is_file() or not (ROOT / "src/solvers/y_orbit_two_cell_audit.py").is_file():
        parser.error("external staging cannot run; integrate and freeze the audit source first")
    if args.worker:
        return _worker(args)
    from benchmarks.run_real_p4_probe import source_facts, environment_facts
    from benchmarks.subreaper_watchdog import supervise
    from src.solvers.real_p4_probe import file_sha256, write_json
    started = time.monotonic()
    if args.run_directory.exists():
        raise ValueError("requires a new evidence directory; prior failures remain immutable")
    source = environment = None
    try:
        source = source_facts(args.expected_head)
        environment = environment_facts()
        if file_sha256(INPUT) != INPUT_SHA:
            raise ValueError("frozen input hash differs")
        if shutil.disk_usage(ROOT).free < 2 * 1024**3:
            raise RuntimeError("audit evidence requires at least 2GiB free disk")
    except Exception as exc:
        args.run_directory.mkdir(parents=True, exist_ok=False)
        write_json(args.run_directory / "prelaunch_failure.json", {
            "classification": "PRELAUNCH_REJECTED", "source": source, "environment": environment,
            "command": sys.argv, "expected_head": args.expected_head, "worker_started": False,
            "supervisor_receipt": None, "degree": 4, "factor_count": 0,
            "error_type": type(exc).__name__, "error": str(exc)})
        (args.run_directory / "prelaunch_traceback.txt").write_text(traceback.format_exc())
        return 2
    command = [sys.executable, "-m", "benchmarks.run_y_orbit_two_cell_audit", "--run", "--worker",
               "--expected-head", args.expected_head, "--run-directory", str(args.run_directory)]
    try:
        summary = supervise(command, args.run_directory, wall_seconds=WALL_SECONDS - (time.monotonic() - started),
                            interval=.25, grace_seconds=2, source_state=source,
                            phase_path=args.run_directory / "phase.json", tree_cap_bytes=TREE_CAP_BYTES,
                            hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                            pss_sampling_policy="disabled_by_profile")
    except Exception as exc:
        preserve_supervisor_failure(args.run_directory, stage="audit", source=source,
                                    environment=environment, command=command, exc=exc)
        return 2
    report_path = args.run_directory / "audit_report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else {
        "schema": SCHEMA, "status": "QUOTIENT_OPERATOR_AUDIT_CONTROLLED_STOP",
        "degree": 4, "factor_count": 0, "audit_only": True, "PDE_solved": False,
        "official_results": False, "source": source, "environment": environment,
        "artifacts": json.loads((args.run_directory / "artifact_manifest.json").read_text())
        if (args.run_directory / "artifact_manifest.json").is_file() else {}}
    report["supervisor_receipt"] = {"path": "summary.json",
                                     "sha256": file_sha256(args.run_directory / "summary.json")}
    if (args.run_directory / "artifact_manifest.json").is_file():
        report["artifacts"] = json.loads((args.run_directory / "artifact_manifest.json").read_text())
    apply_supervisor_classification(report, summary.get("classification"))
    write_json(report_path, report)
    if summary.get("classification") != "COMPLETED" or report.get("status") != PASS:
        return 2
    remaining = WALL_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        report.update(status="QUOTIENT_OPERATOR_AUDIT_CHECKER_NOT_RUN", checker_blocker="600s total budget exhausted")
        write_json(report_path, report)
        return 2
    checker_command = [sys.executable, "-m", "benchmarks.check_y_orbit_two_cell_audit", "--worker",
                       "--expected-head", args.expected_head, "--run-directory", str(args.run_directory)]
    try:
        checked = supervise(checker_command, args.run_directory / "checker_supervision", wall_seconds=remaining,
                            interval=.25, grace_seconds=2, source_state=source,
                            phase_path=args.run_directory / "checker_phase.json", tree_cap_bytes=TREE_CAP_BYTES,
                            hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                            pss_sampling_policy="disabled_by_profile")
    except Exception as exc:
        preserve_supervisor_failure(args.run_directory, stage="checker", source=source,
                                    environment=environment, command=checker_command, exc=exc)
        return 2
    checker_path = args.run_directory / "independent_checker.json"
    if checker_path.is_file():
        result = json.loads(checker_path.read_text())
        result["checker_watchdog_receipt"] = {"path": "checker_supervision/summary.json",
            "sha256": file_sha256(args.run_directory / "checker_supervision/summary.json")}
        write_json(checker_path, result)
        return 0 if checked.get("classification") == "COMPLETED" and result.get("gate_pass") is True else 2
    write_json(args.run_directory / "checker_incomplete.json", {
        "gate_pass": False, "classification": checked.get("classification"),
        "checker_not_completed": True, "no_solver_qualification": True})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
