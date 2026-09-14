"""Recompute V19 residual and physical gates from saved evidence only."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from benchmarks.check_p4_blr_v16 import _hash, _json, _jsonl
from benchmarks.check_p4_blr_tradeoff_v17 import _control_value
from benchmarks.check_p4_cell_condensed_v18 import (
    fullspace_residual_facts, fullspace_balance_facts, matrix_identity_facts, resource_facts,
)


def load_arrays(packet, section, root):
    archive = Path(packet["arrays"]["path"])
    if not archive.is_absolute():
        archive = root / archive
    if _hash(archive) != packet["arrays"]["sha256"]:
        raise ValueError(f"array archive hash changed: {archive}")
    result = {}
    with np.load(archive, allow_pickle=False) as data:
        for name, descriptor in packet[section].items():
            if not isinstance(descriptor, dict) or "array_key" not in descriptor:
                continue
            array = data[descriptor["array_key"]].copy()
            if list(array.shape) != descriptor["shape"] or str(array.dtype) != descriptor["dtype"]:
                raise ValueError(f"array shape or dtype changed: {name}")
            if not np.isfinite(array).all():
                raise ValueError(f"nonfinite array: {name}")
            result[name] = array
    return result


def residual_facts(raw, facts, *, terminal=False):
    specifications = (
        ("original_A6_relative", "native_residual", "native_rhs_norm", 1e-6),
        ("port_closure_relative", "augmented_port_residual", "port_operation_scale", 1e-8),
        ("internal_residual_relative", "internal_residual", "internal_operation_scale", 1e-10),
        ("native_identity_relative", "native_identity_difference", "native_identity_operation_scale", 1e-10),
        ("schur_port_identity_relative", "schur_port_identity_difference", "schur_port_identity_operation_scale", 1e-10),
    )
    measured, checks = {}, {}
    for name, array, scale, limit in specifications:
        numerator = float(np.linalg.norm(raw[array]))
        denominator = float(facts[scale])
        if not math.isfinite(denominator) or denominator < 0:
            raise ValueError(f"invalid recorded operation scale: {scale}")
        ratio = (numerator / denominator if denominator > np.finfo(float).tiny
                 else 0.0 if numerator <= 1e-12 else math.inf)
        measured[name] = ratio
        checks[f"{name}.finite"] = math.isfinite(ratio) and ratio >= 0
        checks[f"{name}.reported"] = math.isclose(ratio, facts[name], rel_tol=1e-10, abs_tol=1e-16)
        if terminal or name not in {"original_A6_relative", "port_closure_relative"}:
            checks[f"{name}.gate"] = math.isfinite(ratio) and 0 <= ratio <= limit
    return {"measured": measured, "checks": checks, "passed": all(checks.values())}


def check_run(directory, root):
    from src.runners.physical_macro_v12 import _compare_saved_output
    from src.runners.physical_p4_schur_v14 import _v14_physical_checks

    path = directory / "physical_dual_cell_condensed_v19_summary.json"
    summary = _json(path)
    result = {"schema": "task039extra.v19.independent.v1", "source_sha": summary["source_sha"],
              "directory": str(directory), "summary_sha256": _hash(path),
              "worker_status": summary["status"], "passed": False}
    try:
        result["resources"] = resource_facts(directory, fullspace=True, prefix="v19")
    except (KeyError, ValueError, OSError) as exc:
        result["resources"] = {"passed": False, "error": str(exc)}
    if "final_residual" not in summary:
        return {**result, "reason": "no_completed_post_KSP_residual", "error": summary.get("error")}
    solver, stack = summary["solver"], summary["interface_stack"]
    retained = solver["retained_outer"]
    residual = fullspace_residual_facts(summary["final_residual"], root)
    balance = fullspace_balance_facts(summary["pc"]["boundary_records"])
    matrix = matrix_identity_facts(stack["matrix_identity_before_factor"], stack["matrix_identity_after_factor"])
    manifest, resolved = _json(directory / "run_manifest.json"), _json(directory / "resolved_config.json")
    identity = summary["operator_identity"]
    checks = {
        "terminal_state": solver["status"] == "TRUE_RESIDUAL_PASS"
                          and summary["stage_pass"] is True and summary["official_result"] is True,
        "original_A6": residual["passed"], "resources": result["resources"]["passed"],
        "unchanged_BAL_H": balance["passed"], "p4_content_identity": matrix["passed"],
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
        "cache_unchanged": retained["cache"]["array_content_sha256"] == solver["p6_cache_after"]["array_content_sha256"]
                           and retained["cache"]["unique_numpy_bytes"] == solver["p6_cache_after"]["unique_numpy_bytes"],
        "source": summary["source_sha"] == manifest["source_sha"] == manifest["source_after"]["source_sha"],
        "physical_identity": identity["physical_model_sha256"] == manifest["physical_model_sha256"]
                             == resolved["provenance"]["physical_model_sha256"],
        "input_identity": identity["input_sha256"] == manifest["input_sha256"] == resolved["provenance"]["input_sha256"],
        "no_notch": resolved.get("geometry", {}).get("cell_notch") in (None, ""),
    }
    rows = []
    for row in _jsonl(directory / "monitor_residuals.jsonl"):
        packet = row["packet"]
        recomputed = residual_facts(load_arrays(packet, "raw", root), packet["facts"])
        rows.append({"iteration": row["iteration"], "facts": row, "recomputed": recomputed})
    checks["every_eight"] = set(range(0, solver["iterations"] + 1, 8)) <= {r["iteration"] for r in rows}
    checks["saved_residuals"] = bool(rows) and all(r["recomputed"]["passed"] for r in rows)
    final_packet = _json(directory / "x2_retained_final.json")
    final = residual_facts(load_arrays(final_packet, "residuals", root), final_packet["facts"], terminal=True)
    checks["final_ports_and_recovery"] = final["passed"]
    checks["every_32_saved_y"] = set(range(0, solver["iterations"] + 1, 32)) <= {
        int(key) for key in retained["retained_checkpoints"]}
    physical, comparison = {}, None
    if residual["passed"] and "output" in summary:
        binding = summary["reference_binding"]
        for index, descriptor in enumerate(list(binding["binding_files"].values()) + [binding["residual_binding"]]):
            checks[f"reference_binding_{index}"] = _hash(Path(descriptor["path"])) == descriptor["sha256"]
        for name, digest in binding["reference_output_file_hashes"].items():
            checks[f"reference_output_{name}"] = _hash(Path(binding["reference_output_dir"]) / name) == digest
        comparison = _compare_saved_output(summary["output"]["output"], binding["reference_output"],
                                           current_dir=directory / "numerical_output",
                                           reference_dir=Path(binding["reference_output_dir"]))
        physical = _v14_physical_checks(solver, summary["field"], comparison, time_policy="observe_only")
        events = _jsonl(directory / "v19_events.jsonl")
        evaluated = [e["timestamp_ns"] for e in events if e["event"].endswith("_physical_output_comparison_complete")]
        for label in ("v18_exact_condensed_global", "v19_p6_local_caches"):
            released = [e["timestamp_ns"] for e in events if e["event"] == "v14_inventory_released"
                        and e["facts"]["label"] == label]
            checks[f"retained.{label}"] = bool(evaluated and len(released) == 1 and released[0] > max(evaluated))
    checks["physical_outputs"] = bool(physical) and all(physical.values())
    return {**result, "residual": residual, "retained_final": final, "trace": rows,
            "balance": balance, "matrix": matrix, "physical_checks": physical,
            "comparison": comparison, "field": summary.get("field"), "checks": checks,
            "passed": all(checks.values())}


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
