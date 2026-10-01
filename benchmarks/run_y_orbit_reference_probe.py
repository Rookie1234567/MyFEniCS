"""Thin whole-tree supervised entrypoint for the full-3D y-orbit pilot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback

from benchmarks.run_real_p4_probe import source_facts, environment_facts
from src.solvers.real_p4_probe import file_sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
EXPECTED_INPUT_SHA256 = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
TREE_CAP_BYTES = 3 * 1024**3 // 2
WALL_SECONDS = 600


def _worker(args):
    import numpy as np
    from time import perf_counter
    from src.solvers.task40extra_y_orbit_reference import run_full3d_pilot

    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    if parent <= 0 or parent != os.getppid():
        raise RuntimeError("worker must be a direct child of the dedicated existing watchdog")
    if not 0 < int(os.environ["PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES"]) <= TREE_CAP_BYTES:
        raise RuntimeError("worker tree cap differs from the coordinated bound")
    source = source_facts(args.expected_head)
    environment = environment_facts()
    component_reuse = None
    if args.dtn_phase_gauge == "boundary_plane":
        from src.solvers.y_orbit_centered_evidence import verify_component_sources
        component_reuse = verify_component_sources(ROOT)
    if file_sha256(INPUT) != EXPECTED_INPUT_SHA256:
        raise RuntimeError("reduced-geometry inherited input hash differs")
    events = args.run_directory / "pilot_events.jsonl"
    artifact_directory = args.run_directory / "arrays"
    artifact_directory.mkdir()
    descriptors = {}
    started = perf_counter()

    def event(name, facts):
        payload = {"event": name, "worker_elapsed_seconds": perf_counter() - started, **facts}
        with events.open("a") as stream:
            stream.write(json.dumps(payload, allow_nan=False) + "\n")
        print(json.dumps(payload, allow_nan=False), flush=True)

    def save_array(name, values):
        array = np.asarray(values)
        if array.dtype.hasobject or (array.dtype.kind in "fc" and not np.isfinite(array).all()):
            raise ValueError("invalid nonfinite/object diagnostic artifact")
        path = artifact_directory / (name + ".npy")
        np.save(path, array, allow_pickle=False)
        descriptors[name] = {"path": str(path.relative_to(args.run_directory)), "shape": list(array.shape),
                             "dtype": str(array.dtype), "payload_bytes": int(array.nbytes),
                             "file_sha256": file_sha256(path)}

    def allocation_gate(name, facts):
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        payload, workspace = int(facts.get("matrix_payload_bytes", 0)), int(facts.get("workspace_bytes", 0))
        cap = int(os.environ["PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES"])
        projected = int(sample["rss_bytes"])+payload+workspace+(128 << 20)
        event("allocation_admission", {"boundary": name, "current_tree_rss_bytes": sample["rss_bytes"],
              "additional_payload_bytes": payload, "declared_workspace_bytes": workspace,
              "reserve_bytes": 128 << 20, "projected_tree_bytes": projected, "tree_cap_bytes": cap,
              "facts": facts, "admitted": projected < cap})
        if (min(payload, workspace) < 0 or sample.get("all_status_readable") is not True
                or sample.get("identity_complete") is not True or sample.get("swap_bytes") != 0 or projected >= cap):
            raise MemoryError("dense actual tree/additional allocation policy fails")

    provenance = {"source": source, "environment": environment, "command": sys.argv,
                  "input_path": str(INPUT.relative_to(ROOT)), "input_sha256": EXPECTED_INPUT_SHA256,
                  "dtn_phase_gauge": args.dtn_phase_gauge, "component_reuse": component_reuse,
                  "resource_contract": {"tree_cap_bytes": TREE_CAP_BYTES, "wall_seconds": WALL_SECONDS,
                                        "swap": 0, "mpi": 1, "math_threads": 1,
                                        "budget_is_performance_claim": False}}
    write_json(args.run_directory / "provenance.json", provenance)
    report = {"schema": "task40extra.y-orbit-full3d-reference.v1", "status": "STARTED"}
    try:
        if args.dtn_phase_gauge == "boundary_plane":
            from src.solvers.y_orbit_centered_probe import run_centered_dense_probe
            from benchmarks.run_y_orbit_sparse_probe import SavedDenseP2Authority
            report = run_centered_dense_probe(INPUT, event=event, save_array=save_array,
                         allocation_gate=allocation_gate, old_oracle=SavedDenseP2Authority(environment))
            report.update(source=source, environment=environment, component_reuse=component_reuse)
        else:
            report = run_full3d_pilot(INPUT, event=event, save_array=save_array, azimuth_deg=args.azimuth)
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source identity changed during the numerical pilot")
        report["source_clean_unchanged"] = True
        report["worker_elapsed_seconds"] = perf_counter() - started
        report["artifacts"] = descriptors
        write_json(args.run_directory / "pilot_report.json", report)
        event("pilot_complete", {"status": report["status"], "design_signal": report.get("design_signal")})
        return 0
    except Exception as exc:
        report.update(status="FAILED", error_type=type(exc).__name__, error=str(exc),
                      worker_elapsed_seconds=perf_counter() - started, artifacts=descriptors)
        write_json(args.run_directory / "pilot_report.json", report)
        (args.run_directory / "pilot_traceback.txt").write_text(traceback.format_exc())
        event("pilot_failure", {"error_type": type(exc).__name__, "error": str(exc)})
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head")
    parser.add_argument("--run-directory", type=Path)
    parser.add_argument("--azimuth", type=float, default=0.0)
    parser.add_argument("--dtn-phase-gauge", choices=("global_z", "boundary_plane"), default="global_z")
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({"status": "not_run", "scope": "80 full3D p2 cells; all y blocks; actual manual DtN aliases",
                          "required_before_run": ["parent exact command approval", "integrated clean committed own branch", "qualified complex cloud activation"],
                          "wall_seconds": WALL_SECONDS, "tree_cap_bytes": TREE_CAP_BYTES}, indent=2))
        return 0
    if not args.expected_head or not args.run_directory:
        parser.error("run needs exact committed HEAD and a new ignored artifact directory")
    args.run_directory = args.run_directory.resolve()
    if not args.run_directory.is_relative_to(ARTIFACT_ROOT):
        parser.error("artifacts must remain in the own ignored subtree")
    if args.azimuth not in (0.0, 5.0):
        parser.error("only separately coordinated real-ky phi=0 or phi=5 pilots are supported")
    if args.dtn_phase_gauge == "boundary_plane" and args.azimuth != 5.0:
        parser.error("fresh centered authority is fixed to the qualified phi5 fixture")
    if args.worker:
        return _worker(args)
    source = source_facts(args.expected_head)
    environment_facts()
    if file_sha256(INPUT) != EXPECTED_INPUT_SHA256:
        raise RuntimeError("inherited input SHA mismatch")
    from benchmarks.subreaper_watchdog import supervise
    command = [sys.executable, "-m", "benchmarks.run_y_orbit_reference_probe", "--run", "--worker",
               "--expected-head", args.expected_head, "--run-directory", str(args.run_directory), "--azimuth", str(args.azimuth),
               "--dtn-phase-gauge", args.dtn_phase_gauge]
    summary = supervise(command, args.run_directory, wall_seconds=WALL_SECONDS, interval=0.25, grace_seconds=2,
                        source_state=source, phase_path=args.run_directory / "phase.json", tree_cap_bytes=TREE_CAP_BYTES,
                        hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                        pss_sampling_policy="disabled_by_profile")
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    path = args.run_directory / "pilot_report.json"
    passed = (summary.get("classification") == "COMPLETED" and path.is_file()
              and json.loads(path.read_text()).get("status") == ("CENTERED_DENSE_AUTHORITY_PASS"
                  if args.dtn_phase_gauge == "boundary_plane" else "ARCHITECTURE_IDENTITY_AND_NOTCH_PASS"))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
