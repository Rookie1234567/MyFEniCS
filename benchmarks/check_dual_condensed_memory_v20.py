"""Independently evaluate V20 raw physics and the opt-in release lifecycle."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.check_dual_cell_condensed_v19 import load_arrays, residual_facts
from benchmarks.check_p4_blr_v16 import _hash, _json, _jsonl
from benchmarks.check_p4_blr_tradeoff_v17 import _control_value
from benchmarks.check_p4_cell_condensed_v18 import (
    _array, _array_sha256, fullspace_balance_facts, fullspace_residual_facts,
    matrix_identity_facts, resource_facts,
)


PHYSICAL_SHA = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_SHA = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
RHS_SHA = "e8ece14d273d8bcdec672f2e29ac8c62971bb0d0fe4af7cc63e741df21934686"
P4_CSR_SHA = "19b9fbf759e6dc586d1316b53c69099647bd3a23e43378535b718c1db2c218d8"
V19_P6_ARRAY_SHA = "c79e781afb4b866db0e38bcaafd92d80f8148c847e1de6bec594ebc4994db62e"
TARGET_MODULE = "libffcx_forms_9c081a2454e80304289733853e6aa2b2d94badd9"
PROFILE = "physical_p6_trace_p4_condensed_lowmem_v20"


def exact_p4_call_facts(boundaries):
    """Recompute the online A4 gate for both coarse calls of every PC."""
    rows = []
    for number, boundary in enumerate(boundaries, 1):
        for index, call in enumerate(boundary["pc"]["inexact_balance"]["calls"], 1):
            rhs, defect = float(call["rhs_norm"]), float(call["eps_norm"])
            rho = defect / max(rhs, np.finfo(float).tiny)
            inner = call["inner"]
            passed = (np.isfinite(rhs) and rhs >= 0 and np.isfinite(defect) and defect >= 0
                      and np.isfinite(rho) and rho <= 1e-10
                      and np.isclose(defect, inner["native_A4_residual_norm"], rtol=1e-12, atol=1e-30)
                      and np.isclose(rhs, inner["rhs_norm"], rtol=1e-12, atol=1e-30))
            rows.append({"pc": number, "call": index, "rho": rho, "passed": bool(passed)})
    return {"passed": bool(rows) and all(r["passed"] for r in rows), "rows": rows,
            "max_relative_residual": max((r["rho"] for r in rows), default=None)}


def cache_description_facts(packet):
    """Rehash saved cache descriptors, separating semantics and sharing."""
    cache = packet["cache"]
    identity = cache["identity_cache"]
    semantic, representation = identity["semantic"], identity["representation"]

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    checks = {
        "saved_descriptor_digest": digest(cache["arrays"]) == cache["array_content_sha256"],
        "semantic_digest": digest(semantic) == identity["semantic_sha256"]
                           == cache["identity_cache_semantic_sha256"],
        "representation_digest": digest(representation) == identity["representation_sha256"]
                                 == cache["identity_cache_representation_sha256"],
        "identity_semantics": semantic["operator"] == "identity" and semantic["shape"] == [450, 450]
                              and semantic["dtype"] == "float64" and semantic["logical_class_count"] == 12,
        "one_shared_identity": representation["mode"] == "shared_read_only_per_interior_shape"
                               and representation["read_only"] is True
                               and representation["unique_storage_count"] == 1
                               and representation["unique_storage_bytes"] == 450 * 450 * 8,
        "payload_components": sum(cache["components"].values()) == cache["unique_numpy_bytes"],
    }
    return {"checks": checks, "passed": all(checks.values()), "semantic": semantic,
            "representation": representation, "unique_numpy_bytes": cache["unique_numpy_bytes"],
            "array_content_sha256": cache["array_content_sha256"]}


def jit_preparation_facts(events, samples):
    """Separate successful preparation from evidence of a real cold reorder."""
    begin = [e for e in events if e["event"] == "v20_form_preparation_started"]
    end = [e for e in events if e["event"] == "v20_form_preparation_complete"]
    factor = [e for e in events if e["event"] == "schur_factor_symbolic_started"]
    checks = {"one_preparation_window": len(begin) == len(end) == len(factor) == 1}
    if not checks["one_preparation_window"]:
        return {"checks": checks, "passed": False, "cold_reorder_demonstrated": False}
    facts = end[0]["facts"]
    start_ns, end_ns = begin[0]["timestamp_ns"], end[0]["timestamp_ns"]
    checks["before_factor"] = start_ns < end_ns < factor[0]["timestamp_ns"]
    checks["both_complete_forms"] = all(
        facts["roles"][name]["dtype"] == "complex128" and facts["roles"][name]["rank"] == 2
        and facts["roles"][name]["module_file"]
        for name in ("p6_condensation", "p4_condensation"))
    cache = facts["cache"]
    cache_root = Path(cache["formal_cache_dir"]).resolve()
    checks["independent_cache"] = cache_root != Path(cache["source_cache_dir"]).resolve()
    checks["source_cache_untouched"] = cache["source_cache_untouched"] is True
    checks["same_options"] = facts["jit_options"]["cffi_extra_compile_args"] == ["-O2", "-g0"]
    checks["same_debug"] = facts["jit_options"]["cffi_debug"] is False
    checks["prepared_objects_reused"] = (facts["p6_module_reused_by_adapter"] is True
                                          and facts["p4_module_reused_by_stack"] is True)
    official = {r["role"] for r in facts["official_evaluation_roles"]}
    expected = {f"postprocess_component_l2_{i}" for i in range(3)} | {
        f"rta_region_{quantity}_{region}" for quantity in ("volume", "absorption")
        for region in ("grating", "substrate")} | {
        "postprocess_E_to_H_expression", "diffraction_E_to_H_expression"}
    checks["official_kernels_prepared"] = expected <= official
    target = [r for r in facts["compiler_events"]
              if any(TARGET_MODULE in Path(p).name for p in r["module_files"])]
    compiling = [s for s in samples if start_ns <= s["timestamp_ns"] <= end_ns
                 and any(m["comm"] in ("cc1", "cc1plus") for m in s["members"])]
    cold_checks = {
        "excluded_exact_old_family": cache["excluded_module_family"] == TARGET_MODULE,
        "one_actual_target_miss": len(target) == 1 and target[0]["cache_hit"] is False
                                  and target[0]["code"] != [None, None],
        "compiler_observed_in_preparation": bool(compiling),
        "target_in_formal_cache": bool(target) and all(
            Path(p).resolve().is_relative_to(cache_root) for r in target for p in r["module_files"]),
    }
    return {"checks": checks, "passed": all(checks.values()), "cache": cache,
            "cold_comparison_checks": cold_checks, "cold_reorder_demonstrated": all(cold_checks.values()),
            "compiler_observation_count": len(compiling), "target_events": target,
            "note": "A merely warm run cannot establish cold JIT ordering gains, even when numerical gates pass."}


def phase_resource_facts(samples, events):
    """Four non-additive measured windows; compiler samples remain included."""
    boundaries = {}
    for name in ("schur_factor_symbolic_started", "v20_outer_ksp_started",
                 "y3_independent_final_residual_complete"):
        rows = [e["timestamp_ns"] for e in events if e["event"] == name]
        if len(rows) != 1:
            return {"status": "EVIDENCE_INCOMPLETE", "missing_or_duplicate_boundary": name}
        boundaries[name] = rows[0]
    factor, solve, final = boundaries.values()
    if not factor < solve < final:
        return {"status": "EVIDENCE_INCOMPLETE", "reason": "unordered_phase_boundaries"}

    def compiler_count(row):
        return sum(m["comm"] in ("cc1", "cc1plus") for m in row["members"])

    def peak(rows):
        if not rows:
            return {"status": "NO_SAMPLES", "rss_bytes": None}
        row = max(rows, key=lambda r: r["rss_bytes"])
        return {"classification": "measured_sampled_simultaneous_process_tree",
                "sample_count": len(rows), "timestamp_ns": row["timestamp_ns"],
                "elapsed_seconds": row["elapsed_seconds"], "rss_bytes": row["rss_bytes"],
                "pss_bytes": row["pss_bytes"], "compiler_descendant_count": compiler_count(row),
                "members": [{k: member[k] for k in ("pid", "ppid", "comm", "rss_bytes", "pss_bytes", "swap_bytes")}
                            for member in row["members"]]}

    buckets = {
        "pre_factor_preparation": [s for s in samples if s["timestamp_ns"] < factor],
        "factor_H6_p6_cache_setup": [s for s in samples if factor <= s["timestamp_ns"] < solve],
        "iteration_final_residual": [s for s in samples if solve <= s["timestamp_ns"] < final],
        "release_recovery_postprocess": [s for s in samples if s["timestamp_ns"] >= final],
    }
    return {"status": "MEASURED", "boundaries_ns": boundaries,
            "scope_note": "Continuous watchdog tree, compiler included. Preparation includes p4 assembly up to symbolic. Windows mapped by event timestamps; phases and compiler subset are non-additive.",
            "phases": {name: peak(rows) for name, rows in buckets.items()},
            "full": peak(samples),
            "compiler_subset": peak([s for s in samples if compiler_count(s)]),
            "iteration_without_compiler_subset": peak([s for s in buckets["iteration_final_residual"] if not compiler_count(s)])}


def release_timeline_facts(events):
    """An inventory debit must follow the final packet and native A6 gate."""
    names = (
        "v20_complete_field_packet_saved", "y3_independent_final_residual_complete",
        "v20_release_gate_checked", "v20_preconditioner_release_started",
        "v20_preconditioner_release_complete", "v20_p6_release_started",
        "v20_p6_release_complete", "v20_p4_release_started", "v20_p4_release_complete",
        "v20_post_release_final_residual_complete", "y3_physical_output_comparison_complete",
    )
    by_name = {name: [e for e in events if e["event"] == name] for name in names}
    checks = {f"one.{name}": len(rows) == 1 for name, rows in by_name.items()}
    times = {name: rows[0]["timestamp_ns"] for name, rows in by_name.items() if len(rows) == 1}
    if all(checks.values()):
        gate = by_name["v20_release_gate_checked"][0]["facts"]
        checks["release_gate"] = (gate["field_packet_saved"] is True
                                  and gate["pre_release_A6_passed"] is True
                                  and gate["pre_release_identity_passed"] is True
                                  and 0 <= gate["pre_release_A6_relative"] <= 1e-6)
        checks["packet_before_A6"] = times[names[0]] < times[names[1]] < times[names[2]]
        post = times["v20_post_release_final_residual_complete"]
        for family in ("preconditioner", "p6", "p4"):
            checks[f"release_order.{family}"] = (
                times["v20_release_gate_checked"] < times[f"v20_{family}_release_started"]
                < times[f"v20_{family}_release_complete"] < post)
        official = times["y3_physical_output_comparison_complete"]
        checks["post_release_before_official"] = post < official
        # The before-output resource sample is also checked by the run checker;
        # completion alone cannot establish when official processing began.
        checks["p6_owner_refs"] = by_name["v20_p6_release_complete"][0]["facts"].get("owner_refs_cleared") is True
        p4 = by_name["v20_p4_release_complete"][0]["facts"]
        checks["borrowed_matrix_retained"] = (
            p4["matrix_lifecycle_policy"] == "MATRIX_RETAINED_BACKEND_DEPENDENCY"
            and p4["factor_destroy_before_matrix"] is True)
        for label, family in (
            ("v14_h6", "preconditioner"), ("v20_p6_local_caches", "p6"),
            ("v18_exact_condensed_global", "p4"), ("v18_exact_condensed_matrix", "p4"),
            ("v18_exact_port_recovery", "p4"),
        ):
            rows = [e for e in events if e["event"] == "v14_inventory_released"
                    and e["facts"]["label"] == label]
            checks[f"debit.{label}"] = (len(rows) == 1
                and times[f"v20_{family}_release_started"] <= rows[0]["timestamp_ns"]
                <= times[f"v20_{family}_release_complete"])
    return {"checks": checks, "timestamps_ns": times, "passed": all(checks.values())}


def saved_field_facts(full, original_rhs, y, alpha, slave_rows, pre_x, pre_b, post_x, post_b):
    """Check the actual saved full field survives solver destruction unchanged."""
    slaves = np.asarray(slave_rows)
    valid_slaves = (slaves.ndim == 1 and np.issubdtype(slaves.dtype, np.integer)
                    and len(slaves) > 0 and len(np.unique(slaves)) == len(slaves)
                    and np.all(slaves >= 0) and np.all(slaves < full.size))
    checks = {
        "full_storage_size": full.shape == (173802,),
        "retained_size": y.shape == (51272,) and alpha.shape == (80,),
        "same_full_solution": np.array_equal(full, pre_x) and np.array_equal(full, post_x),
        "same_physical_rhs": np.array_equal(original_rhs, pre_b) and np.array_equal(original_rhs, post_b),
        "frozen_rhs": _array_sha256(original_rhs) == RHS_SHA,
        "finite_full_solution": bool(np.isfinite(full).all()),
        "retained_ports_saved": np.array_equal(y[-80:], alpha),
        "owned_slave_rows": bool(valid_slaves),
        "strict_slave_zero": bool(valid_slaves and np.all(full[slaves] == 0)),
    }
    return {"checks": checks, "solution_sha256": _array_sha256(full),
            "rhs_sha256": _array_sha256(original_rhs), "passed": all(checks.values())}


def check_run(directory, root):
    from src.runners.physical_macro_v12 import _compare_saved_output
    from src.runners.physical_p4_schur_v14 import _v14_physical_checks

    directory, root = Path(directory), Path(root)
    path = directory / "physical_dual_condensed_memory_v20_summary.json"
    summary = _json(path)
    result = {"schema": "task039extra.v20.independent.v1", "source_sha": summary["source_sha"],
              "directory": str(directory), "summary_sha256": _hash(path),
              "worker_status": summary["status"], "passed": False}
    try:
        result["resources"] = resource_facts(directory, fullspace=True, prefix="v20")
    except (KeyError, ValueError, OSError) as exc:
        result["resources"] = {"passed": False, "error": str(exc)}
    if not summary.get("post_release_final_residual"):
        return {**result, "reason": "no_completed_post_release_native_A6", "error": summary.get("error")}

    solver, stack = summary["solver"], summary["interface_stack"]
    retained, identity = solver["retained_outer"], summary["operator_identity"]
    pre = fullspace_residual_facts(summary["final_residual"], root)
    post = fullspace_residual_facts(summary["post_release_final_residual"], root)
    balance = fullspace_balance_facts(summary["pc"]["boundary_records"])
    p4_quality = exact_p4_call_facts(summary["pc"]["boundary_records"])
    matrix = matrix_identity_facts(stack["matrix_identity_before_factor"], stack["matrix_identity_after_factor"])
    manifest, resolved = _json(directory / "run_manifest.json"), _json(directory / "resolved_config.json")
    events = _jsonl(directory / "v20_events.jsonl")
    lifecycle = release_timeline_facts(events)
    samples = _jsonl(directory / "watchdog/resources.jsonl")
    phases = phase_resource_facts(samples, events)
    jit = jit_preparation_facts(events, samples)
    cache_description = cache_description_facts(_json(directory / "v20_x1_p6_cache_identity.json"))
    checks = {
        "terminal_state": solver["status"] == "TRUE_RESIDUAL_PASS"
                          and summary["stage_pass"] is True and summary["official_result"] is True,
        "new_profile": resolved["solver"]["preconditioner"] == PROFILE
                       and resolved["solver"]["stage"] == "Y3_ORIGINAL",
        "original_A6_before_release": pre["passed"], "original_A6_after_release": post["passed"],
        "resources": result["resources"]["passed"], "lifecycle": lifecycle["passed"],
        "phase_evidence": phases["status"] == "MEASURED",
        "prefactor_form_preparation": jit["passed"],
        "cache_descriptor_evidence": cache_description["passed"]
                                     and cache_description["array_content_sha256"] == retained["cache"]["array_content_sha256"],
        "unchanged_BAL_H": balance["passed"], "online_native_A4": p4_quality["passed"],
        "p4_content_identity": matrix["passed"],
        "frozen_p4_CSR": stack["matrix_identity_before_factor"]["csr_sha256"] == P4_CSR_SHA,
        "p4_CSR_before_release": stack["matrix_identity_before_release"] == stack["matrix_identity_after_factor"],
        "exact_p4": stack["backend"] == "exact"
                    and _control_value(stack["factor"]["controls_before_symbolic"], "icntl", 35) == 0
                    and _control_value(stack["factor"]["controls_before_symbolic"], "icntl", 10) == 0,
        "p6_action_only": identity["retained_p6"]["p6_build_audit"]["matrix_materialized"] is False,
        "new_space": solver["retained_global_size"] == 51272,
        "one_KSP": solver["ksp_create_count"] == solver["ksp_solve_count"] == solver["ksp_destroy_count"] == 1,
        "frozen_KSP": solver["restart"] == 32 and solver["max_it"] == 2048
                      and 0 <= solver["iterations"] <= 2048 and solver["screen_enabled"] is False,
        "setup_count": retained["setup_checks"]["setup_pc_counts"] == {"bal_h": 1, "p4_mat_solve": 2, "h6": 1},
        "total_pc_count": balance["pc_count"] == solver["pc_apply_count"] + 1,
        "complete_PC_counts": solver["actual_pc_counts_including_one_setup_call"] == {
            "bal_h": balance["pc_count"], "h6": balance["pc_count"],
            "p4_mat_solve": balance["global_mat_solve_count"]}
            and summary["pc"]["h6_apply_count"] == balance["pc_count"]
            and summary["pc"]["native_A4_action_count"] == 2 * balance["pc_count"],
        "cache_unchanged": retained["cache"]["array_content_sha256"] == solver["p6_cache_after"]["array_content_sha256"]
                           and retained["cache"]["unique_numpy_bytes"] == solver["p6_cache_after"]["unique_numpy_bytes"],
        "V19_numeric_cache": retained["cache"]["array_content_sha256"] == V19_P6_ARRAY_SHA,
        "shared_identity": identity["retained_p6"]["identity_cache_mode"] == "shared_read_only_per_interior_shape"
                           and identity["retained_p6"]["p6_build_audit"]["identity_cache_readonly"] is True,
        "prepared_p6_form": identity["retained_p6"]["compiled_form_reused"] is True,
        "source": summary["source_sha"] == manifest["source_sha"] == manifest["source_after"]["source_sha"],
        "physical_identity": identity["physical_model_sha256"] == manifest["physical_model_sha256"]
                             == resolved["provenance"]["physical_model_sha256"] == PHYSICAL_SHA,
        "mode_identity": identity["ordered_mode_sha256"] == MODE_SHA,
        "input_identity": identity["input_sha256"] == manifest["input_sha256"] == resolved["provenance"]["input_sha256"],
        "no_notch": resolved.get("geometry", {}).get("cell_notch") in (None, ""),
    }
    rows = []
    for row in _jsonl(directory / "monitor_residuals.jsonl"):
        packet = row["packet"]
        recomputed = residual_facts(load_arrays(packet, "raw", root), packet["facts"])
        rows.append({"iteration": row["iteration"], "recomputed": recomputed})
    checks["every_eight"] = set(range(0, solver["iterations"] + 1, 8)) <= {r["iteration"] for r in rows}
    checks["saved_residuals"] = bool(rows) and all(r["recomputed"]["passed"] for r in rows)
    packet = _json(directory / "x2_retained_final.json")
    final = residual_facts(load_arrays(packet, "residuals", root), packet["facts"], terminal=True)
    checks["final_ports_and_recovery"] = final["passed"]
    saved = saved_field_facts(
        *[_array(packet, name, root) for name in ("full_solution", "original_rhs", "retained_y")],
        load_arrays(packet, "residuals", root)["retained_alpha"], _array(packet, "owned_slave_rows", root),
        *[_array(summary[key], name, root) for key in ("final_residual", "post_release_final_residual")
          for name in ("solution", "rhs")],
    )
    checks["complete_saved_field"] = saved["passed"]
    checks["every_32_saved_y"] = set(range(0, solver["iterations"] + 1, 32)) <= {
        int(key) for key in retained["retained_checkpoints"]}
    workers = _jsonl(directory / "v20_worker_resources.jsonl")
    before_output = [w["timestamp_ns"] for w in workers if w["label"] == "y3_before_output_recovery"]
    post_times = lifecycle["timestamps_ns"].get("v20_post_release_final_residual_complete")
    checks["release_before_official_start"] = (len(before_output) == 1 and post_times is not None
                                               and post_times < before_output[0])
    physical, comparison = {}, None
    if pre["passed"] and post["passed"] and "output" in summary:
        binding = summary["reference_binding"]
        for index, descriptor in enumerate(list(binding["binding_files"].values()) + [binding["residual_binding"]]):
            checks[f"reference_binding_{index}"] = _hash(Path(descriptor["path"])) == descriptor["sha256"]
        for name, digest in binding["reference_output_file_hashes"].items():
            checks[f"reference_output_{name}"] = _hash(Path(binding["reference_output_dir"]) / name) == digest
        comparison = _compare_saved_output(summary["output"]["output"], binding["reference_output"],
                                           current_dir=directory / "numerical_output",
                                           reference_dir=Path(binding["reference_output_dir"]))
        physical = _v14_physical_checks(solver, summary["field"], comparison, time_policy="observe_only")
    checks["physical_outputs"] = bool(physical) and all(physical.values())
    return {**result, "residual_before": pre, "residual_after": post, "retained_final": final,
            "saved_field": saved, "lifecycle": lifecycle, "phase_resources": phases,
            "jit_preparation": jit, "cold_reorder_comparison_qualified": jit["cold_reorder_demonstrated"],
            "cache_description": cache_description,
            "trace": rows, "balance": balance, "online_p4_quality": p4_quality,
            "matrix": matrix, "physical_checks": physical, "comparison": comparison,
            "field": summary.get("field"), "checks": checks, "passed": all(checks.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check_run(args.directory.resolve(), args.root.resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
