"""Worker-only bounded support pilot; inherits exact source/ABI/Library gates.

Saved independent checking and packet durability are separate prerequisites
for qualification. Importing/preflight creates no mesh, form, JIT or vector.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

STAGE = Path(__file__).resolve().parent
BASE_PATH = STAGE.parent/"launch_target_chunked_surface_mass_v2.py"
BASE_SHA = "0a1f103a307ae5e95151424a645d6fca5cdeb772049951f1143d817aae8885d0"
PINS = {
    "helper": ("target_boundary_support_pilot.py", "85d00a1f7059a41664b10f8441ce8aff13965d9455a016c748a810399aa2a271"),
    "reference": ("target_boundary_support_reference.py", "b0cee0d3ba36c9d8b1b23dc00a7ac32590de4c7540a08db2811c6ba1c5f02c64"),
    "runner": ("run_boundary_support_pilot.py", "1d32f31d8160fb4b886cbaade3928b39844aa1702764789205be179d44844668"),
}
SCHEMA = "task40extra.boundary-support-worker-launcher.v1"
WALL = 600


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inherited():
    import hashlib
    if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError("immutable inherited orchestration bytes changed")
    return load("immutable_mass_v2_orchestration", BASE_PATH)


def code_identity(base):
    expected = {name: {"path": str((STAGE/path).resolve()), "sha256": sha}
                for name, (path, sha) in PINS.items()}
    expected["helper"]["function"] = "assemble_boundary_support_pilot"
    expected["reference"]["function"] = "run_reference"
    for name, item in expected.items():
        base.require(base.file_sha256(item["path"]) == item["sha256"], "unfrozen pilot source: " + name)
    return {"inherited_source_identity": base.code_identity(), "pilot_sources": expected,
            "pilot_launcher_sha256": base.file_sha256(__file__), "wall_seconds": WALL}


def verify_record(base, record, packet, code):
    base.require(record.get("status") == "BOUNDARY_SUPPORT_PILOT_COMPLETE" and record.get("pilot_passed") is True,
                 "pilot numerical worker incomplete")
    base.require(record.get("selected_only") is True and record.get("allmode_qualification") is False and
                 record.get("full_C_D_allmode_qualification") is False and record.get("carrier_volume_factor_PDE_calls") == 0,
                 "selected affine pilot scope differs")
    for field, saved in (("physical_manifest_sha256", "original_physical_manifest_sha256"),
                        ("ordered_keys_sha256", "ordered_keys_sha256"), ("config_sha256", "config_sha256")):
        base.require(record.get(field) == packet[saved], "full original metadata differs: " + field)
    base.require(record.get("actual_sources") == code["pilot_sources"], "numerical source identities differ")
    base.require(record.get("mechanism_forms") == 4 and record.get("actual_native_rows") == 13224 and
                 len(record.get("mechanism_comparisons", [])) == 24 and record.get("mechanism_gate_passed") is True,
                 "mechanism coverage/gate differs")
    base.require(all(item.get("passed") is True for item in record["mechanism_comparisons"]),
                 "complete FFCx vector gate failed")
    selected = record.get("selected_original_mode_indices", [])
    base.require(len(selected) == 12 and len(set(selected)) == 12 and
                 {(item.get("index"), item.get("axis")) for item in record["mechanism_comparisons"]} ==
                 {(index, axis) for index in selected for axis in (0, 1)}, "unique complete mechanism mode/axis coverage missing")
    base.require("compiled_mechanism" in record, "actual compiled mechanism identity missing")
    if "compiled_mechanism" in record:
        base.require(len(record["compiled_mechanism"]) == 4 and
                     {(item["side"], item["axis"]) for item in record["compiled_mechanism"]} ==
                     {(side, axis) for side in ("top", "bottom") for axis in (0, 1)}, "four exact component forms missing")
        for item in record["compiled_mechanism"]:
            identity = item["identity"]; kernel = identity.get("loaded_kernel", {})
            base.require(kernel.get("restoration_exact") is True and kernel.get("num_constants") == 3 and
                         [x.get("role") for x in kernel.get("constant_roles", [])] == ["alpha", "gamma", "kz"] and
                         kernel.get("numerical_assembly_during_probe") is False, "actual mechanism Constant-pack/restoration differs")
            base.require(identity.get("rules") and all(rule.get("degree") == 27 and
                         rule.get("points", {}).get("shape") == [196, 2] and rule.get("weights", {}).get("shape") == [196] and
                         rule.get("compiled_weight_tables_verified", 0) > 0 for rule in identity["rules"]),
                         "actual degree27 compiled Gauss coverage missing")
            base.require(item.get("rule_match", {}).get("passed") is True, "actual mechanism rule bytes differ")
    base.require(set(record.get("reference_checks", {})) == {"component", "Cdual", "Dfunctional",
                 "component_convergence", "Cdual_convergence", "Dfunctional_convergence"} and
                 all(item.get("passed") is True for item in record["reference_checks"].values()),
                 "higher quadrature component/C/D action gate missing")
    reference = record.get("reference_record", {})
    base.require(reference.get("reference_convergence_pass") is True and reference.get("operation_rtol") == 1e-10 and
                 reference.get("primary_degree") == 160 and reference.get("actual_facet_count") == 12 and
                 reference.get("distinct_side_phase_groups") == 6 and reference.get("FE_JIT_PDE_creation_calls") == 0 and
                 reference.get("no_numerical_denominator_floor") is True and reference.get("selected_indices") == record["selected_original_mode_indices"],
                 "independent reference role/coverage differs")
    rules = reference.get("rules", [])
    base.require(len(rules) == 2 and [rule.get("degree") for rule in rules] == [168, 176] and
                 [rule.get("actual_nodes_per_facet") for rule in rules] == [7225, 7921] and
                 all(rule.get("actual_geometric_points") == 12*rule["actual_nodes_per_facet"] and
                     rule.get("state_side_component_nonzero") == [[[True]*3]*2]*2 for rule in rules),
                 "reference facet/node/side/component/state coverage missing")
    state = reference.get("state_identity", {})
    base.require(state.get("slave_slots_zero") is True and state.get("constraint_equations_checked", 0) > 0 and
                 all(state.get(field) for field in ("master_state_sha256", "global_numbering_sha256", "cell_dof_order_sha256")),
                 "reference native/slave state identity missing")


def check_artifact_bytes(base, record, root):
    groups = ("mechanism_artifacts", "primary_artifacts", "state_artifacts", "action_artifacts", "reference_artifacts")
    base.require(all(isinstance(record.get(name), dict) and record[name] for name in groups), "complete pilot artifact groups missing")
    base.require(len(record.get("compiled_mechanism", [])) == 4 and
                 all(item.get("artifacts", {}).get("C") and item["artifacts"].get("binary")
                     for item in record["compiled_mechanism"]), "four compiled mechanism files missing")
    checked = {}
    for descriptor in base.descriptor_items(record):
        path = Path(descriptor["path"]).resolve()
        base.require(path.is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(), "foreign/missing pilot artifact")
        base.require(path.stat().st_size == descriptor["bytes"] and base.file_sha256(path) == descriptor["sha256"],
                     "pilot artifact bytes/hash differ")
        checked[str(path)] = descriptor["sha256"]
    base.require(checked, "empty pilot artifact inventory")
    return {"artifact_hash_entries": len(checked), "all_contained_lengths_hashes_verified": True}


def preflight(base, args):
    receipt, packet = base.runtime_preflight(args)
    code = code_identity(base)
    receipt.update(schema=SCHEMA, code=code, pilot_scope="selected12 modes/both sides/xy/full882 anchors",
                   numerical_worker_started=False, qualification=False)
    receipt["policy"]["wall_seconds"] = WALL
    base.require(base.source_and_environment() == (receipt["source"], receipt["environment"]) and
                 code_identity(base) == code, "post-preflight source/ABI/code changed")
    return receipt, packet


def child(base, args):
    run = args.run_directory.resolve()
    result = {"schema": SCHEMA, "passed": False, "status": "PILOT_WORKER_FAILED_OR_PARTIAL",
              "independent_checker_passed": False, "durability_passed": False}
    try:
        parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
        base.require(Path.cwd().resolve() == base.ROOT and parent == os.getppid() and parent > 0 and
                     int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0")) == base.CAP,
                     "exact whole-tree supervisor/cwd required")
        source, environment = base.source_and_environment(); code = code_identity(base)
        path = Path(os.environ["BOUNDARY_PILOT_PREFLIGHT_PATH"])
        base.require(base.file_sha256(path) == os.environ["BOUNDARY_PILOT_PREFLIGHT_SHA256"], "preflight changed")
        shutil.copyfile(path, run/"launch_preflight.json")
        admitted = base.read_json(run/"launch_preflight.json")
        base.require((source, environment, code) == (admitted["source"], admitted["environment"], admitted["code"]),
                     "full parent/child/source/environment equality failed")
        seal, packet, metadata = base.verify_metadata(args, source, environment)
        base.require((seal, metadata) == (admitted["metadata_seal"], admitted["metadata"]), "Library authority changed")
        from src.solvers.target_auto_surface_cost import jsonable
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        def event(value):
            converted = jsonable(value)
            with (run/"pilot_events.jsonl").open("a") as stream:
                stream.write(json.dumps({"monotonic": time.monotonic(), "record": converted}, sort_keys=True, allow_nan=False)+"\n")
            base.save_json(run/"phase.json", {"phase": converted.get("stage", converted.get("kind", "pilot")),
                "application_worker": {"pid": os.getpid()}, "last_event_monotonic": time.monotonic()})
        def gate(label, facts):
            additional = base.allocation_bytes(facts)
            sample = process_tree_snapshot(parent, label, None, pss_sampling_policy="disabled_by_profile")
            base.require(sample["all_status_readable"] and sample["identity_complete"] and sample["swap_bytes"] == 0,
                         "allocation identity/readability/zeroSwap failed")
            total = sample["rss_bytes"]+additional+base.RESERVE
            event({"stage": "pilot_whole_tree_allocation", "label": label, "additional_bytes": additional,
                "current_RSS_bytes": sample["rss_bytes"], "reserve_bytes": base.RESERVE,
                "cap_bytes": base.CAP, "total_bytes": total, "passed": total < base.CAP})
            if total >= base.CAP:
                raise MemoryError("actual current RSS+allocation+128MiB reaches3GiB")
            return True
        modules = {}
        for name in ("helper", "reference", "runner"):
            item = code["pilot_sources"][name]
            import_name = "target_boundary_support_pilot" if name == "helper" else "frozen_boundary_pilot_"+name
            modules[name] = load(import_name, item["path"])
        base.require(base.source_and_environment() == (source, environment) and code_identity(base) == code,
                     "source/ABI changed before mesh")
        produced = modules["runner"].run_pilot(repo_root=base.ROOT, metadata_dir=base.METADATA_RUN/"metadata",
            metadata_seal=seal, output_dir=run/"pilot", cache_dir=run/"mechanism_jit_cache", allocation_gate=gate,
            event=event, helper=modules["helper"].assemble_boundary_support_pilot,
            reference_helper=modules["reference"].run_reference)
        verify_record(base, produced["record"], packet, code)
        base.require(base.file_sha256(run/"pilot/pilot_record.json") == produced["pilot_record"]["sha256"], "record hash changed")
        members = check_artifact_bytes(base, produced["record"], run/"pilot")
        raw_bytes = sum(path.stat().st_size for path in (run/"pilot").rglob("*.npy"))
        packet_bytes = sum(path.stat().st_size for path in run.rglob("*") if path.is_file())
        base.require(raw_bytes <= 512 << 20 and packet_bytes <= 1 << 30, "raw512MiB/fullpacket1GiB policy exceeded")
        base.require(base.source_and_environment() == (source, environment) and code_identity(base) == code,
                     "post-worker source/ABI changed")
        result.update(passed=True, status="PILOT_WORKER_PASS_PENDING_CHECKER_AND_DURABILITY", source=source,
            environment=environment, code=code, pilot_record=produced["pilot_record"], saved_artifact_hashes=members,
            raw_NPY_bytes=raw_bytes, fullpacket_snapshot_bytes=packet_bytes)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    base.save_json(run/"launcher_child_result.json", result)
    return 0 if result["passed"] else 2


def main(argv=None):
    base = inherited(); args = base.parser().parse_args(argv)
    if args.child:
        base.require(args.stage == "run", "child accepts only admittedrun")
        return child(base, args)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+"_"+str(os.getpid())
    diagnostic = STAGE/("pilot_preflight_"+stamp+".json")
    try:
        admitted, packet = preflight(base, args)
        base.save_json(diagnostic, admitted)
        if args.stage == "preflight":
            print(json.dumps({"status": admitted["status"], "path": str(diagnostic), "sha256": base.file_sha256(diagnostic)})); return 0
        from benchmarks.subreaper_watchdog import supervise
        run = args.run_directory.resolve()
        command = [base.PYTHON, str(Path(__file__).resolve()), "--stage", "run", "--child",
            "--metadata-library-receipt", str(args.metadata_library_receipt.resolve()),
            "--metadata-library-receipt-sha256", args.metadata_library_receipt_sha256,
            "--metadata-seal", str(args.metadata_seal.resolve()), "--metadata-seal-sha256", args.metadata_seal_sha256,
            "--run-directory", str(run)]
        summary = supervise(command, run, wall_seconds=WALL, interval=.25, grace_seconds=2,
            source_state=admitted["source"], phase_path=run/"phase.json", tree_cap_bytes=base.CAP,
            hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
            pss_sampling_policy="disabled_by_profile", worker_environment={"BOUNDARY_PILOT_PREFLIGHT_PATH": str(diagnostic),
            "BOUNDARY_PILOT_PREFLIGHT_SHA256": base.file_sha256(diagnostic)})
        terminal = {"schema": SCHEMA, "passed": False, "status": "PILOT_WORKER_FAILED_OR_PARTIAL",
            "independent_checker_passed": False, "durability_passed": False,
            "watchdog_receipt": {"path": "summary.json", "sha256": base.file_sha256(run/"summary.json")}}
        try:
            base.require_summary(summary, admitted["source"], WALL)
            base.require(base.source_and_environment() == (admitted["source"], admitted["environment"]) and
                         code_identity(base) == admitted["code"], "post-supervision source/ABI changed")
            result = base.read_json(run/"launcher_child_result.json")
            base.require(result.get("passed") is True and result.get("source") == admitted["source"] and
                         result.get("environment") == admitted["environment"] and result.get("code") == admitted["code"],
                         "worker result/fullidentity gate failed")
            record = base.read_json(run/"pilot/pilot_record.json"); verify_record(base, record, packet, admitted["code"])
            base.require(base.file_sha256(run/"pilot/pilot_record.json") == result["pilot_record"]["sha256"], "post-watchdog record changed")
            terminal.update(passed=True, status="PILOT_WORKER_PASS_PENDING_CHECKER_AND_DURABILITY",
                pilot_record=result["pilot_record"], child_result_sha256=base.file_sha256(run/"launcher_child_result.json"))
        except BaseException as error:
            terminal.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        base.save_json(run/"launcher_terminal_result.json", terminal)
        print(json.dumps({"status": terminal["status"], "passed": terminal["passed"], "seconds": summary.get("elapsed_seconds"),
            "RSS_peak_bytes": summary.get("sampled_process_tree_rss_peak_bytes")}))
        return 0 if terminal["passed"] else 2
    except BaseException as error:
        base.save_json(STAGE/("pilot_launch_failure_"+stamp+".json"), {"passed": False, "stage": args.stage,
            "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()})
        traceback.print_exc(); return 2


if __name__ == "__main__":
    raise SystemExit(main())
