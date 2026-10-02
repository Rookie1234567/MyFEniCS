"""Thin stage-gated Q3--Q5 quotient CLI using the Q0--Q2 supervisor contract.

Default invocation prints a plan and never imports numerical project modules.
The prefactor stage restores audited coefficients and rebuilds/compares all four
q blocks; factors and solver dispatch are forbidden. Solve is a separate opt-in
command requiring its own authorization after the integrated source is frozen.
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
PASSES = {"prefactor": "QUOTIENT_PREFACTOR_COMPARE_PASS",
          "solve": "QUOTIENT_FULL3D_INVERSE_PROBE_PASS"}
FACTOR_ALLOWANCE_BYTES = 512 * 1024**2
AUDIT_RUN = "y_orbit_two_cell_p4_phi5_audit_attempt1"
SCHEMA = "task40extra.y-orbit-two-cell-quotient-probe.v1"


def plain_metadata(value):
    """Detach immutable authority metadata for canonical JSON serialization."""
    from collections.abc import Mapping
    if isinstance(value, Mapping):
        return {key: plain_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_metadata(item) for item in value]
    return value


def plan_metadata(stage, *, shared_transforms=False):
    if stage not in PASSES:
        raise ValueError("unknown quotient stage")
    return {"schema": SCHEMA, "status": "NOT_RUN_STAGED_PLAN_ONLY", "stage": stage,
            "degree": 4, "physical_mode_count": 532, "factor_count": 0,
            "PDE_solved": False, "official_results": False,
            "scope": "restore and compare four fresh q blocks" if stage == "prefactor"
                     else "separately authorized quotient factors and full3D original solves",
            "tree_cap_bytes": TREE_CAP_BYTES, "wall_seconds": WALL_SECONDS,
            "mpi": 1, "math_threads": 1, "swap_bytes": 0,
            "evidence_reserve_bytes": RESERVE_BYTES,
            "factor_workspace_allowance_bytes": 0 if stage == "prefactor" else FACTOR_ALLOWANCE_BYTES,
            "shared_transforms": shared_transforms, "shared_profile": "same80_p4_only" if shared_transforms else None}


def allocation_request(stage, facts):
    """Additional bytes only; current RSS already includes both local caches."""
    if stage not in PASSES:
        raise ValueError("unknown quotient allocation stage")
    fields = ("factor_count", "retained_factor_count", "resident_factor_count",
              "factor_workspace_allowance_bytes", "declared_factor_workspace_allowance_bytes")
    for name in fields:
        if name in facts and (type(facts[name]) is not int or facts[name] < 0):
            raise ValueError("factor declarations require nonnegative literal integers")
    if stage == "prefactor" and any(facts.get(name, 0) != 0 for name in fields):
        raise ValueError("prefactor prohibits factors, solves and factor workspace allowance")
    allowance = facts.get("factor_workspace_allowance_bytes", 0)
    if "declared_factor_workspace_allowance_bytes" in facts:
        if facts["declared_factor_workspace_allowance_bytes"] != allowance:
            raise ValueError("factor allowance declarations differ")
    if allowance:
        retained = facts.get("retained_factor_count", facts.get("resident_factor_count"))
        if type(retained) is not int or retained not in range(4):
            raise ValueError("factor admission requires actual retained count before the next factor")
        expected = FACTOR_ALLOWANCE_BYTES * (4 - retained) // 4
        if allowance != expected:
            raise ValueError("remaining factor allowance must follow actual retained count")
        if facts.get("LU_fill_and_workspace_unknown") is not True:
            raise ValueError("factor fill and temporary workspace must remain explicitly unknown")
    payload = int(facts.get("matrix_payload_bytes", facts.get("retained_numeric_bytes_upper", 0)))
    workspace = int(facts.get("workspace_bytes", 0))
    reserve = max(RESERVE_BYTES, int(facts.get("evidence_reserve_bytes", 0)))
    if min(payload, workspace, reserve) < 0:
        raise ValueError("negative allocation declaration")
    return payload, workspace, reserve, allowance


def validate_worker_result(report, stage):
    if (stage not in PASSES or report.get("schema") != SCHEMA
            or report.get("stage") != stage or report.get("status") != PASSES[stage]
            or report.get("degree") != 4 or report.get("physical_mode_count") != 532
            or report.get("official_results") is not False):
        raise ValueError("quotient API stage/schema/degree/all532 scope contract differs")
    count = 0 if stage == "prefactor" else 4
    if (report.get("factor_count") != count
            or report.get("PDE_solved") is not (stage == "solve")
            or report.get("prefactor_only") is not (stage == "prefactor")):
        raise ValueError("quotient API returned an unauthorized factor or solve stage")
    if stage == "prefactor" and any(report.get(key) for key in
            ("regular_sources", "notched_sources", "sampled_right_PC_defect")):
        raise ValueError("prefactor cannot contain solved-source or PC qualification")
    return True


def apply_supervisor_classification(report, classification):
    """Retain a numerical negative instead of relabeling it a resource stop."""
    if classification == "COMPLETED":
        return report
    report["supervisor_classification"] = classification
    report["worker_status_before_supervisor_classification"] = report.get("status")
    if report.get("status") == "QUOTIENT_INVERSE_PROBE_FAILED":
        return report
    if classification == "WORKER_FAILED":
        report["status"] = "QUOTIENT_INVERSE_PROBE_FAILED"
    elif classification and "CONTROLLED_STOP" in classification:
        report["status"] = "QUOTIENT_INVERSE_PROBE_CONTROLLED_STOP"
    else:
        report["status"] = "QUOTIENT_INVERSE_PROBE_SUPERVISION_FAILED"
    return report


def retained_factor_evidence(directory):
    """Preserve the last worker receipt after interruption; never infer pass."""
    phase = Path(directory) / "phase.json"
    if not phase.is_file():
        return {"count": None, "authority": "no_worker_phase_receipt"}
    value = json.loads(phase.read_text()).get("factor_count")
    if type(value) is not int or value not in range(5):
        raise ValueError("bounded last-factor phase receipt differs")
    return {"count": value, "authority": "last_worker_phase_receipt"}


def preserve_supervisor_failure(directory, *, stage, source, environment, command, exc):
    """Do not fabricate a completed watchdog receipt when launch itself fails."""
    from src.solvers.real_p4_probe import file_sha256, write_json
    directory.mkdir(parents=True, exist_ok=True)
    summary_relative = "summary.json" if stage != "checker" else "checker_supervision/summary.json"
    summary_path = directory / summary_relative
    failure = {"classification": "SUPERVISION_FAILED", "stage": stage,
               "source": source, "environment": environment, "command": command,
               "degree": 4, "factor_count": 0, "error_type": type(exc).__name__, "error": str(exc),
               "supervisor_receipt": {"path": summary_relative, "sha256": file_sha256(summary_path)}
               if summary_path.is_file() else None, "completed_supervision_claimed": False}
    write_json(directory / (stage + "_supervision_failure.json"), failure)
    (directory / (stage + "_supervision_traceback.txt")).write_text(traceback.format_exc())
    report_path = directory / "probe_report.json"
    if stage != "checker":
        report = json.loads(report_path.read_text()) if report_path.is_file() else {
            "schema": SCHEMA, "degree": 4, "factor_count": 0, "source": source,
            "environment": environment, "PDE_solved": False, "official_results": False, "stage": stage, "prefactor_only": stage == "prefactor"}
        report["last_factor_count_evidence"] = retained_factor_evidence(directory)
        observed = report["last_factor_count_evidence"]["count"]
        if observed is not None:
            report["factor_count"] = max(report.get("factor_count", 0), observed)
        report["worker_status_before_supervisor_failure"] = report.get("status")
        report["status"] = "QUOTIENT_INVERSE_PROBE_SUPERVISION_FAILED"
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
    from src.solvers.y_orbit_qualified_snapshot import SavedQuotientSnapshotAuthority
    from benchmarks.y_orbit_two_cell_authority import SavedFullP4Authority, AUTHORITY_RUN
    from src.solvers.real_p4_probe import file_sha256, write_json
    from src.solvers.fullspace_dtn_action import _jsonable

    started = time.monotonic()
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    source = None
    environment = None
    descriptors = {}
    authority = full_period_authority = None
    runtime_state = {"factor_count": 0, "shared_equivalence_complete": False}
    report = {"schema": SCHEMA, "status": "STARTED", "degree": 4, "factor_count": 0,
              "stage": args.stage, "prefactor_only": args.stage == "prefactor", "PDE_solved": False, "official_results": False}

    def event(name, facts):
        facts = _jsonable(facts)
        if args.stage == "prefactor" and name in ("all_branch_factor_test", "all_branch_factor_retained",
                                                  "original_augmented_manufactured_control"):
            raise ValueError("prefactor callback detected unauthorized factor/solve dispatch")
        if name == "all_branch_factor_test":
            runtime_state["factor_count"] = max(runtime_state["factor_count"], int(facts["q"]) + 1)
        if args.stage == "prefactor" and any(int(facts.get(k, 0)) != 0 for k in
                ("factor_count", "retained_factor_count", "resident_factor_count")):
            raise ValueError("prefactor callback detected unauthorized factor dispatch")
        if "factor_count" in facts:
            runtime_state["factor_count"] = max(runtime_state["factor_count"], int(facts["factor_count"]))
        if "retained_factor_count" in facts:
            runtime_state["factor_count"] = max(runtime_state["factor_count"], int(facts["retained_factor_count"]))
        if name == "shared_complete_equivalence_before_any_factor":
            if (not args.shared_transforms or facts.get("complete_before_any_factor") is not True
                    or [item.get("role") for item in facts.get("roles",[])] != ["full","twist_0","twist_1"]):
                raise ValueError("complete actual shared-equivalence event required before factor")
            runtime_state["shared_equivalence_complete"] = True
        payload = {"event": name, "worker_elapsed_seconds": time.monotonic() - started, **facts}
        append_jsonl(args.run_directory / "probe_events.jsonl", payload)
        write_json(args.run_directory / "phase.json", {"phase": name, "factor_count": runtime_state["factor_count"],
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
        if name.startswith("quotient_factor_q_") and args.shared_transforms and not runtime_state["shared_equivalence_complete"]:
            raise ValueError("shared factor admission requires complete actual equivalence first")
        if name.startswith("quotient_factor_q_") and (args.stage != "solve"
                or not facts.get("factor_workspace_allowance_bytes")):
            raise ValueError("q factor allocation requires the solve stage and remaining factor allowance")
        payload, workspace, reserve, allowance = allocation_request(args.stage, facts)
        if time.monotonic() - started >= WALL_SECONDS:
            raise TimeoutError("quotient worker-plus-checker budget expired before allocation")
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if (sample.get("all_status_readable") is not True or sample.get("identity_complete") is not True
                or sample.get("swap_bytes") != 0 or global_swap() != swap_baseline):
            raise RuntimeError("per-allocation readable whole-tree identity and zero global/tree swap required")
        projected = int(sample["rss_bytes"]) + payload + workspace + allowance + reserve
        envelope = memory_envelope()
        effective_cap = runtime_tree_cap(cap, int(sample["rss_bytes"]), envelope,
                                         explicit_tree_cap_bytes=TREE_CAP_BYTES)
        event("allocation_admission", {"boundary": name, "current_tree_rss_bytes": sample["rss_bytes"],
              "additional_payload_bytes": payload, "declared_workspace_bytes": workspace, "remaining_factor_allowance_bytes": allowance,
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
        resource = {"stage": args.stage, "tree_cap_bytes": cap, "wall_seconds": WALL_SECONDS, "swap_bytes": 0,
                    "mpi": 1, "math_threads": 1, "evidence_reserve_bytes": RESERVE_BYTES,
                    "factor_workspace_allowance_bytes": 0 if args.stage == "prefactor" else FACTOR_ALLOWANCE_BYTES,
                    "factor_fill_and_temporary_workspace_unknown": True,
                    "factor_L_U_statistics_copies_permitted": False,
                    "performance_or_target_capacity_claim": False}
        provenance = {"source": source, "environment": environment, "command": sys.argv,
                      "input_sha256": INPUT_SHA, "resource_contract": resource,
                      "schema": SCHEMA, "stage": args.stage, "prefactor_only": args.stage == "prefactor", "degree": 4}
        write_json(args.run_directory / "provenance.json", provenance)
        shutil.copyfile(environment["qualification_manifest"], args.run_directory / "abi_manifest.json")
        write_json(args.run_directory / "probe_report.json", {**report, "source": source,
                                                              "environment": environment})
        allocation_gate("authority_metadata_validation", {"matrix_payload_bytes": 4 << 20,
                                                          "workspace_bytes": 4 << 20})
        storage_source_bridge = None
        if args.shared_transforms:
            from benchmarks.y_orbit_shared_storage_bridge import load_storage_source_bridge
            storage_source_bridge = load_storage_source_bridge(ARTIFACT_ROOT,new_source=source,
                new_environment=environment,allocation_gate=allocation_gate)
            provenance["shared_transforms"] = True
            provenance["same80_storage_source_bridge"] = storage_source_bridge["receipt"]
        authority = SavedQuotientSnapshotAuthority(ARTIFACT_ROOT / AUDIT_RUN, new_source=source,
                                        new_environment=environment, allocation_gate=allocation_gate, storage_source_bridge=storage_source_bridge)
        full_period_authority = SavedFullP4Authority(ARTIFACT_ROOT / AUTHORITY_RUN,
            new_source=source, new_environment=environment, allocation_gate=allocation_gate, storage_source_bridge=storage_source_bridge)
        provenance["saved_quotient_snapshot_authority"] = plain_metadata(authority.receipt)
        provenance["saved_full_p4_authority"] = full_period_authority.receipt
        write_json(args.run_directory / "provenance.json", provenance)
        from src.solvers.y_orbit_two_cell_inverse_probe import run_quotient_inverse_probe
        report = _jsonable(run_quotient_inverse_probe(INPUT, authority=authority,
            full_period_authority=full_period_authority, event=event,
            save_array=save_array, allocation_gate=allocation_gate,
            run_directory=args.run_directory, stage=args.stage, shared_transforms=args.shared_transforms))
        validate_worker_result(report, args.stage)
        if args.shared_transforms:
            if report.get("shared_transforms") is not True or report.get("shared_transform_equivalence",{}).get("complete_before_any_factor") is not True:
                raise ValueError("shared-transform command requires complete actual storage equivalence")
            report["same80_storage_source_bridge"] = storage_source_bridge["receipt"]
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source changed during quotient probe")
        report.update(schema=SCHEMA, source=source, environment=environment, source_clean_unchanged=True,
                      artifacts=descriptors, authority=plain_metadata(authority.receipt), stage=args.stage,
                      prefactor_only=args.stage == "prefactor",
                      worker_elapsed_seconds=time.monotonic() - started)
        report["saved_full_p4_authority"] = full_period_authority.receipt
        report["provenance_receipt"] = {"path": "provenance.json",
            "sha256": file_sha256(args.run_directory / "provenance.json")}
        report["artifact_manifest_receipt"] = {"path": "artifact_manifest.json",
            "sha256": file_sha256(args.run_directory / "artifact_manifest.json")}
        write_json(args.run_directory / "probe_report.json", report)
        event("probe_complete", {"status": report["status"], "factor_count": report["factor_count"]})
        return 0
    except Exception as exc:
        report.update(schema=SCHEMA, status="QUOTIENT_INVERSE_PROBE_FAILED", degree=4,
                      source=source, environment=environment, artifacts=descriptors,
                      source_clean_unchanged=None,
                      factor_count=max(report.get("factor_count", 0), runtime_state["factor_count"]),
                      error_type=type(exc).__name__, error=str(exc), stage=args.stage,
                      prefactor_only=args.stage == "prefactor",
                      PDE_solved=report.get("PDE_solved", False),
                      official_results=report.get("official_results", False),
                      worker_elapsed_seconds=time.monotonic() - started)
        if authority is not None:
            report["authority"] = plain_metadata(authority.receipt)
        write_json(args.run_directory / "probe_report.json", report)
        (args.run_directory / "probe_traceback.txt").write_text(traceback.format_exc())
        event("probe_failure", {"error_type": type(exc).__name__, "error": str(exc)})
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--stage", choices=("prefactor", "solve"), default="prefactor")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head")
    parser.add_argument("--run-directory", type=Path)
    parser.add_argument("--shared-transforms", action="store_true", help="same80 p4 storage-only bank; all original gates retained")
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(plan_metadata(args.stage, shared_transforms=args.shared_transforms), indent=2))
        return 0
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_head or "") or not args.run_directory:
        parser.error("quotient probe requires exact clean integrated HEAD and a fresh ignored run directory")
    args.run_directory = args.run_directory.resolve()
    if not args.run_directory.is_relative_to(ARTIFACT_ROOT.resolve()):
        parser.error("quotient probe evidence must remain within the own ignored artifact subtree")
    if not (ROOT / "AGENTS.md").is_file() or not (ROOT / "src/solvers/y_orbit_two_cell_inverse_probe.py").is_file():
        parser.error("external staging cannot run; integrate and freeze the quotient source first")
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
            raise RuntimeError("quotient evidence requires at least 2GiB free disk")
    except Exception as exc:
        args.run_directory.mkdir(parents=True, exist_ok=False)
        write_json(args.run_directory / "prelaunch_failure.json", {
            "classification": "PRELAUNCH_REJECTED", "source": source, "environment": environment,
            "command": sys.argv, "expected_head": args.expected_head, "worker_started": False,
            "supervisor_receipt": None, "degree": 4, "stage": args.stage, "factor_count": 0,
            "error_type": type(exc).__name__, "error": str(exc)})
        (args.run_directory / "prelaunch_traceback.txt").write_text(traceback.format_exc())
        return 2
    command = [sys.executable, "-m", "benchmarks.run_y_orbit_quotient_probe", "--run", "--worker", "--stage", args.stage,
               "--expected-head", args.expected_head, "--run-directory", str(args.run_directory)]
    if args.shared_transforms:command.append("--shared-transforms")
    try:
        summary = supervise(command, args.run_directory, wall_seconds=WALL_SECONDS - (time.monotonic() - started),
                            interval=.25, grace_seconds=2, source_state=source,
                            phase_path=args.run_directory / "phase.json", tree_cap_bytes=TREE_CAP_BYTES,
                            hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                            pss_sampling_policy="disabled_by_profile")
    except Exception as exc:
        preserve_supervisor_failure(args.run_directory, stage=args.stage, source=source,
                                    environment=environment, command=command, exc=exc)
        return 2
    report_path = args.run_directory / "probe_report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else {
        "schema": SCHEMA, "status": "QUOTIENT_INVERSE_PROBE_CONTROLLED_STOP",
        "degree": 4, "factor_count": 0, "stage": args.stage, "prefactor_only": args.stage == "prefactor", "PDE_solved": False,
        "official_results": False, "source": source, "environment": environment,
        "artifacts": json.loads((args.run_directory / "artifact_manifest.json").read_text())
        if (args.run_directory / "artifact_manifest.json").is_file() else {}}
    report["last_factor_count_evidence"] = retained_factor_evidence(args.run_directory)
    observed = report["last_factor_count_evidence"]["count"]
    if observed is not None:
        report["factor_count"] = max(report.get("factor_count", 0), observed)
    report["supervisor_receipt"] = {"path": "summary.json",
                                     "sha256": file_sha256(args.run_directory / "summary.json")}
    if (args.run_directory / "artifact_manifest.json").is_file():
        report["artifacts"] = json.loads((args.run_directory / "artifact_manifest.json").read_text())
    apply_supervisor_classification(report, summary.get("classification"))
    write_json(report_path, report)
    if summary.get("classification") != "COMPLETED" or report.get("status") != PASSES[args.stage]:
        return 2
    remaining = WALL_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        report.update(status="QUOTIENT_INVERSE_PROBE_CHECKER_NOT_RUN", checker_blocker="600s total budget exhausted")
        write_json(report_path, report)
        return 2
    checker_command = [sys.executable, "-m", "benchmarks.check_y_orbit_quotient_probe", "--worker", "--stage", args.stage,
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
