"""Independent supervised saved-array pilot replay; never calls the FE runner."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
import hashlib
import importlib.util

_WORKER_PATH = Path(__file__).resolve().with_name("launch_boundary_support_pilot.py")
_WORKER_EXPECTED = "b46b8671663e52549899666bd94e7399463737340aa019ac94f4a8796ac2b03d"
if hashlib.sha256(_WORKER_PATH.read_bytes()).hexdigest() != _WORKER_EXPECTED:
    raise ValueError("producer orchestration changed before import")
_SPEC = importlib.util.spec_from_file_location("pinned_boundary_worker_orchestration", _WORKER_PATH)
worker = importlib.util.module_from_spec(_SPEC); sys.modules[_SPEC.name] = worker; _SPEC.loader.exec_module(worker)

WORKER_LAUNCHER_SHA = "b46b8671663e52549899666bd94e7399463737340aa019ac94f4a8796ac2b03d"
CHECKER_SHA = "9cdf0722301a196c79a04d4bdad69ecd3998d042196e6069ce41f6fb9ddcef5c"
REPORT_SHA = "cb2e240edfc8c583a7050ea5f9497f5ed7a9281527be9086c2bf5d4367e7200e"
SUMMARY_SHA = "3e897087dddfe99896df287e4b12fe99adf90809859c19423094147ae3ffab17"
LIBRARY_SHA = "40eee408e370075fa25fa205ba41b046f7492baf8118846d09067356b5c66dd8"
ARCHIVE_SHA = "f5b9ce1b2c000b12df1557d4429dbfefdcc82b2d0984560b3837e6c216af9ca0"
MANIFEST_SHA = "73ab422a6f478ffda53e2f633d959d89e1a2aeed3792e361ed2cff1091f0bf05"
WORKER = Path('/workspace/scratch/9c465670b46b/task40extra_cloud/repo/benchmarks/artifacts/task40extra_dot_parallel_cloud/target_AUTO_boundary_support_pilot_attempt1')
CHECKER = worker.STAGE/"check_saved_boundary_pilot.py"
LIBRARY = worker.STAGE/"terminal_packet/library_full_roundtrip_receipt.json"
WALL = 600
SCHEMA = "task40extra.saved-boundary-support-checker-launcher.v1"


def code(base):
    base.require(base.file_sha256(worker.__file__) == WORKER_LAUNCHER_SHA and
                 base.file_sha256(CHECKER) == CHECKER_SHA, "saved-checker or producer orchestration source changed")
    return {"producer_code": worker.code_identity(base), "saved_checker_sha256": CHECKER_SHA,
            "saved_checker_launcher_sha256": base.file_sha256(__file__), "wall_seconds": WALL}


def authority(base, args, source, environment):
    # Scalar JSON objects are bounded before parsing; full raw operands are
    # admitted separately by the saved checker before any mmap.
    base.require(LIBRARY.stat().st_size < 16384 and base.file_sha256(LIBRARY) == LIBRARY_SHA, "actual complete Library receipt differs")
    receipt = base.read_json(LIBRARY)
    base.require(receipt.get("status") == "PASS" and receipt.get("qualification") == "WORKER_ONLY_CHECKER_PENDING" and
                 receipt.get("source_head") == base.HEAD and receipt.get("archive_sha256") == ARCHIVE_SHA and
                 receipt.get("archive_bytes") == 87590500 and receipt.get("members_verified") == 390 and
                 receipt.get("member_manifest_sha256") == MANIFEST_SHA and receipt.get("npy_count") == 355 and
                 receipt.get("full_uncompressed_bytes") == 759987904 and len(receipt.get("parts", [])) == 3,
                 "complete immutable worker Library readback authority missing")
    archive = Path(receipt["fresh_readback_path"])
    base.require(archive.is_relative_to(worker.STAGE/"terminal_packet/fresh_library_readback") and
                 archive.stat().st_size == 87590500 and base.file_sha256(archive) == ARCHIVE_SHA,
                 "fresh Library archive bytes no longer match")
    base.require(base.file_sha256(WORKER/"summary.json") == SUMMARY_SHA and
                 base.file_sha256(WORKER/"pilot/pilot_record.json") == REPORT_SHA, "immutable worker report/watchdog differs")
    summary = base.read_json(WORKER/"summary.json"); base.require_summary(summary, source, WALL)
    result = base.read_json(WORKER/"launcher_child_result.json")
    base.require(result.get("passed") is True and result.get("status") == "PILOT_WORKER_PASS_PENDING_CHECKER_AND_DURABILITY" and
                 result.get("source") == source and result.get("environment") == environment and
                 result.get("code") == worker.code_identity(base) and result.get("pilot_record", {}).get("sha256") == REPORT_SHA,
                 "producer source/ABI/worker status equality failed")
    terminal = base.read_json(WORKER/"launcher_terminal_result.json")
    base.require(terminal.get("passed") is True and terminal.get("status") == "PILOT_WORKER_PASS_PENDING_CHECKER_AND_DURABILITY" and
                 terminal.get("pilot_record", {}).get("sha256") == REPORT_SHA and
                 terminal.get("watchdog_receipt") == {"path": "summary.json", "sha256": SUMMARY_SHA} and
                 terminal.get("child_result_sha256") == base.file_sha256(WORKER/"launcher_child_result.json"),
                 "producer terminal/child/report/watchdog linkage differs")
    seal, packet, metadata = base.verify_metadata(args, source, environment)
    record = base.read_json(WORKER/"pilot/pilot_record.json")
    worker.verify_record(base, record, packet, result["code"])
    return record, seal, packet, {"worker_report_sha256": REPORT_SHA, "worker_summary_sha256": SUMMARY_SHA,
        "worker_library_receipt_sha256": LIBRARY_SHA, "worker_archive_sha256": ARCHIVE_SHA, "metadata": metadata}


def preflight(base, args):
    candidate = args.run_directory.resolve()
    base.require(not candidate.is_relative_to(WORKER) and not WORKER.is_relative_to(candidate),
                 "fresh checker directory must be disjoint from immutable worker")
    receipt, _ = base.runtime_preflight(args)
    record, seal, packet, inputs = authority(base, args, receipt["source"], receipt["environment"])
    receipt.update(schema=SCHEMA, code=code(base), checker_inputs=inputs,
                   scope="saved selected12 affine-boundary finite-array replay only", numeric_checker_started=False)
    receipt["policy"]["wall_seconds"] = WALL
    base.require(base.source_and_environment() == (receipt["source"], receipt["environment"]) and
                 code(base) == receipt["code"], "post-preflight source/ABI changed")
    return receipt


def child(base, args):
    run = args.run_directory.resolve()
    result = {"schema": SCHEMA, "passed": False, "status": "SAVED_CHECKER_FAILED_OR_PARTIAL"}
    try:
        parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
        base.require(parent == os.getppid() and parent > 0 and Path.cwd().resolve() == base.ROOT and
                     int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0")) == base.CAP,
                     "exact saved-only watchdog/cwd/cap required")
        source, environment = base.source_and_environment(); identities = code(base)
        path = Path(os.environ["SAVED_BOUNDARY_PREFLIGHT_PATH"])
        base.require(base.file_sha256(path) == os.environ["SAVED_BOUNDARY_PREFLIGHT_SHA256"], "saved preflight hash differs")
        shutil.copyfile(path, run/"launch_preflight.json"); admitted = base.read_json(run/"launch_preflight.json")
        base.require((source, environment, identities) == (admitted["source"], admitted["environment"], admitted["code"]),
                     "complete saved-checker parent/child source/ABI equality failed")
        record, seal, packet, inputs = authority(base, args, source, environment)
        base.require(inputs == admitted["checker_inputs"], "worker/Library inputs changed between parent and child")
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        retained_selected_metadata = 0
        def gate(label, facts):
            additional = base.allocation_bytes(facts)+retained_selected_metadata
            if label.startswith("saved_pilot/") and "complete_mapping" in label:
                base.require(additional < 128 << 20, "complete numerical replay plus retained selected metadata exceeds128MiB")
            sample = process_tree_snapshot(parent, label, None, pss_sampling_policy="disabled_by_profile")
            base.require(sample["all_status_readable"] and sample["identity_complete"] and sample["swap_bytes"] == 0,
                         "saved-checker tree identity/readability/zeroSwap failed")
            total = sample["rss_bytes"]+additional+base.RESERVE
            with (run/"saved_allocation_events.jsonl").open("a") as stream:
                stream.write(json.dumps({"label": label, "current_RSS_bytes": sample["rss_bytes"],
                    "predicted_additional_bytes": additional, "reserve_bytes": base.RESERVE, "cap_bytes": base.CAP,
                    "admission_total_bytes": total, "passed": total < base.CAP}, sort_keys=True)+"\n")
            if total >= base.CAP: raise MemoryError("saved-checker actual RSS+allocation+128MiB reaches3GiB")
            return True
        manifest_path = base.METADATA_RUN/"metadata/original_physical_manifest.json"
        manifest_buffers = {"immutable_input_JSON_bytes": manifest_path.stat().st_size,
            "complete_row_objects_from_core12288bytes_each": 32060*12288, "decoder_container_workspace": 16 << 20}
        gate("sealed_original_manifest_parse_before_load", {"predicted_total_bytes": sum(manifest_buffers.values()),
             "predicted_buffer_bytes": manifest_buffers})
        manifest = base.read_json(base.METADATA_RUN/"metadata/original_physical_manifest.json")
        base.require(manifest.get("mode_count") == 32060 and len(manifest.get("modes", [])) == 32060,
                     "full sealed physical manifest count differs")
        # Keep the exact twelve queried operands and the full count/index
        # domain. Other rows are explicitly unmaterialized, never represented
        # as verified numerical outputs. The complete immutable bytes remain
        # hash-bound by the original metadata Library seal above.
        selected_manifest = [None]*32060
        for index in record["selected_original_mode_indices"]:
            selected_manifest[index] = manifest["modes"][index]
        del manifest
        retained_selected_metadata = 4 << 20
        helper = worker.load("target_boundary_support_pilot", worker.STAGE/worker.PINS["helper"][0])
        checker = worker.load("frozen_saved_boundary_support_checker", CHECKER)
        utility_path = worker.STAGE.parent/"chunked_native/run_chunked_surface_cost_mass_v2.py"
        utilities = worker.load("pinned_saved_boundary_utilities", utility_path)
        from src.solvers import target_auto_surface_cost as core
        base.save_json(run/"phase.json", {"phase": "saved_finite_array_replay", "application_worker": {"pid": os.getpid()}})
        measured = checker.check_saved(record=record, root=WORKER/"pilot", gate=gate, base=utilities,
            helper=helper, core=core, sealed_manifest=selected_manifest)
        base.require(measured.get("passed") is True and measured.get("status") == "SAVED_SELECTED_PILOT_REPLAY_PASS",
                     "saved algebra/functionals replay failed")
        base.require(base.source_and_environment() == (source, environment) and code(base) == identities and
                     base.file_sha256(WORKER/"pilot/pilot_record.json") == REPORT_SHA and
                     base.file_sha256(WORKER/"summary.json") == SUMMARY_SHA, "post-check source/ABI/worker authority changed")
        result.update(passed=True, status="SAVED_SELECTED_BOUNDARY_PILOT_CHECKER_PASS", source=source, environment=environment,
            code=identities, checker_inputs=inputs, measured=measured, all24_component_certificates_full882_fallback=True)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc()); traceback.print_exc()
    base.save_json(run/"checker_report.json", result)
    return 0 if result["passed"] else 2


def main(argv=None):
    base = worker.inherited(); args = base.parser().parse_args(argv)
    if args.child: return child(base, args)
    stamp=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+"_"+str(os.getpid())
    diagnostic = worker.STAGE/("saved_checker_preflight_"+stamp+".json")
    try:
        admitted=preflight(base,args);base.save_json(diagnostic,admitted)
        if args.stage == "preflight":
            print(json.dumps({"status": admitted["status"], "path": str(diagnostic), "sha256": base.file_sha256(diagnostic)}));return 0
        from benchmarks.subreaper_watchdog import supervise
        run=args.run_directory.resolve()
        command=[base.PYTHON,str(Path(__file__).resolve()),"--stage","run","--child",
            "--metadata-library-receipt",str(args.metadata_library_receipt.resolve()),"--metadata-library-receipt-sha256",args.metadata_library_receipt_sha256,
            "--metadata-seal",str(args.metadata_seal.resolve()),"--metadata-seal-sha256",args.metadata_seal_sha256,"--run-directory",str(run)]
        summary=supervise(command,run,wall_seconds=WALL,interval=.25,grace_seconds=2,source_state=admitted["source"],
            phase_path=run/"phase.json",tree_cap_bytes=base.CAP,hard_stop_immediate=True,timebase_guard=True,stop_on_global_swap=True,
            pss_sampling_policy="disabled_by_profile",worker_environment={"SAVED_BOUNDARY_PREFLIGHT_PATH":str(diagnostic),
            "SAVED_BOUNDARY_PREFLIGHT_SHA256":base.file_sha256(diagnostic)})
        terminal={"schema":SCHEMA,"passed":False,"status":"SAVED_CHECKER_FAILED_OR_PARTIAL",
            "watchdog_receipt":{"path":"summary.json","sha256":base.file_sha256(run/"summary.json")}}
        try:
            base.require_summary(summary,admitted["source"],WALL)
            base.require(base.source_and_environment()==(admitted["source"],admitted["environment"]) and code(base)==admitted["code"],
                "saved-checker post-supervision source/ABI differs")
            report=base.read_json(run/"checker_report.json")
            base.require(report.get("passed") is True and report.get("source")==admitted["source"] and
                report.get("environment")==admitted["environment"] and report.get("code")==admitted["code"] and
                report.get("checker_inputs")==admitted["checker_inputs"],"saved checker report/identity differs")
            terminal.update(passed=True,status="SAVED_SELECTED_BOUNDARY_PILOT_CHECKER_PASS",
                checker_report_sha256=base.file_sha256(run/"checker_report.json"),checker_inputs=report["checker_inputs"])
        except BaseException as error: terminal.update(error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        base.save_json(run/"checker_terminal.json",terminal)
        print(json.dumps({"status":terminal["status"],"passed":terminal["passed"],"seconds":summary.get("elapsed_seconds"),
            "RSS_peak_bytes":summary.get("sampled_process_tree_rss_peak_bytes")}));return 0 if terminal["passed"] else 2
    except BaseException as error:
        base.save_json(worker.STAGE/("saved_checker_launch_failure_"+stamp+".json"),{"passed":False,"error_type":type(error).__name__,
            "error":str(error),"traceback":traceback.format_exc()});traceback.print_exc();return 2


if __name__ == "__main__": raise SystemExit(main())
