"""Read-only Review V16 admission from saved vectors and process-tree samples.

No FE assembly, factorization, reference creation, or worker invocation occurs
here. Worker PASS labels do not determine this checker's decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


STEMS = ("A2R160_BAL_H_p4_01", "A2R160_BAL_H_p4_02", "LIGHT448_BAL_H_p4_09")
GIB = 1024**3


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _finite(*values: float) -> bool:
    return bool(np.all(np.isfinite(values)))


def _array(packet: dict, key: str, root: Path) -> np.ndarray:
    archive = Path(packet["arrays"]["path"])
    if not archive.is_absolute():
        archive = root / archive
    if _hash(archive) != packet["arrays"]["sha256"]:
        raise ValueError(f"NPZ hash mismatch: {archive}")
    descriptor = packet[key]
    with np.load(archive, allow_pickle=False) as arrays:
        value = arrays[descriptor["array_key"]].copy()
    if list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]:
        raise ValueError(f"Array shape/dtype mismatch: {archive}:{key}")
    if not np.isfinite(value).all():
        raise ValueError(f"Non-finite saved array: {archive}:{key}")
    return value


def resource_scope(directory: Path, prefix: str) -> dict[str, Any]:
    """Use the same continuous parent sampling scope for both factors."""
    samples = _jsonl(directory / "watchdog/resources.jsonl")
    events = _jsonl(directory / f"{prefix}_events.jsonl")
    worker = _jsonl(directory / f"{prefix}_worker_resources.jsonl")
    run = _json(directory / "run_summary.json")
    manifest = _json(directory / "run_manifest.json")
    numeric = [e for e in events if e["event"] == "schur_factor_numeric_complete"]
    metrics = [e for e in events if e["event"] == "v14_field_metrics_complete"]
    if len(numeric) != 1 or len(metrics) != (1 if prefix == "v14" else 3):
        raise ValueError("Factor-live interval lacks exactly one numeric and all three evaluations")
    start = numeric[0]["timestamp_ns"]
    end = metrics[-1]["timestamp_ns"]
    live = [s for s in samples if start <= s["timestamp_ns"] <= end]
    if not samples or not live or not worker:
        raise ValueError("Full or factor-live resource samples missing")
    authority = run["resource_authority"]
    cap = int(authority["launch_envelope"]["launch_cap_bytes"])
    swap = authority["global_swap_activity"]
    global_zero = all(
        swap["end"][key] == swap["baseline"][key]
        and all(s["global_swap_pages"][key] == swap["baseline"][key] for s in samples)
        for key in ("pswpin_pages", "pswpout_pages")
    )
    readable = all(s["all_status_readable"] and s["pss_all_readable"] for s in samples)
    peak = max(s["rss_bytes"] for s in samples)
    inventory_peak = max(s["inventory_peak_bytes"] for s in worker)
    temp_peak = max(s["workspace_peak_bytes"] for s in worker)
    reserve_ok = all(
        s["memory_envelope"]["effective_available_bytes"]
        >= s["memory_envelope"]["reserve_bytes"] for s in samples
    )
    zero_swap = global_zero and all(s["swap_bytes"] == 0 for s in samples)
    gates = {
        "all_rss_pss_readable": readable,
        "tree_cap": 0 < peak <= cap <= 8 * GIB,
        "resident_inventory_cap": inventory_peak <= 6 * GIB,
        "shared_workspace_cap": temp_peak <= GIB,
        "host_reserve": reserve_ok,
        "zero_swap": zero_swap,
        "descendants_cleared": authority["descendants_cleared"] is True
        and authority["remaining_child_pids"] == [],
        "clean_source_after": manifest["source_after"]["tracked_and_nonignored_untracked_clean"] is True,
        "observe_only": run["time_policy"] == "observe_only"
        and run["time_gate_evaluated"] is False
        and all(s["time_policy"] == "observe_only" and not s["time_gate_evaluated"] for s in samples),
    }
    return {
        "scope": "continuous_parent_process_tree",
        "full_sample_count": len(samples), "live_sample_count": len(live),
        "live_start_ns": start, "live_end_ns": end,
        "full_rss_peak_bytes": peak,
        "live_rss_peak_bytes": max(s["rss_bytes"] for s in live),
        "full_pss_peak_bytes": max(s["pss_bytes"] for s in samples),
        "live_pss_peak_bytes": max(s["pss_bytes"] for s in live),
        "inventory_peak_bytes": inventory_peak, "workspace_peak_bytes": temp_peak,
        "gates": gates, "passed": all(gates.values()),
        "full_workflow_monotonic_seconds": run["full_workflow_monotonic_seconds"],
        "workflow_clock_interval": run["workflow_clock_interval"],
        "hashes": {name: _hash(directory / name) for name in (
            "watchdog/resources.jsonl", f"{prefix}_events.jsonl",
            f"{prefix}_worker_resources.jsonl", "run_manifest.json", "run_summary.json")},
    }


def decide_s2(*, quality: bool, comparison_valid: bool, statistics_available: bool,
              compression_effect: bool, r_peak: float, r_live: float) -> dict:
    """The frozen two memory benefit alternatives; time is not a veto."""
    finite_ratios = _finite(r_peak, r_live) and r_peak > 0 and r_live > 0
    if not comparison_valid or not finite_ratios:
        status = "COMPARISON_INCONCLUSIVE"
    elif not statistics_available:
        status = "COMPRESSION_STATS_UNAVAILABLE"
    elif not compression_effect:
        status = "BLR_UNAVAILABLE_OR_NO_EFFECT"
    elif not quality:
        status = "BLR_ACTION_UNQUALIFIED"
    elif r_peak <= 0.90:
        status = "ADMIT_S3_PEAK_MEMORY_GAIN"
    elif r_live <= 0.80 and r_peak <= 1.05:
        status = "ADMIT_S3_RESIDENT_MEMORY_GAIN_ONLY"
    else:
        status = "STRONG_BUT_INSUFFICIENT_MEMORY_GAIN"
    return {"status": status, "admit_s3": status.startswith("ADMIT_S3_"),
            "R_peak": r_peak, "R_live": r_live, "quality_pass": bool(quality),
            "time_policy": "observe_only"}


def check_run(directory: Path, baseline: Path, root: Path) -> dict:
    summary = _json(directory / "physical_p4_blr_v16_summary.json")
    exact = _json(baseline / "physical_p4_schur_v14_summary.json")
    current_scope = resource_scope(directory, "v16")
    exact_scope = resource_scope(baseline, "v14")
    rows = []
    exact_by_stem = {r["stem"]: r for r in exact["solve_records"]}
    records = summary["solve_records"]
    if tuple(r["stem"] for r in records) != STEMS:
        raise ValueError("Frozen RHS order changed")
    for record in records:
        stem = record["stem"]
        packet_path = directory / "s2_rhs_packets" / f"{stem}.json"
        packet = _json(packet_path)
        identity = packet["identity"]
        input_path = Path(identity["input_json"])
        if _hash(input_path) != identity["input_sha256"]:
            raise ValueError(f"Input identity changed: {stem}")
        rhs = _array(_json(input_path), "g", root)
        residual = _array(packet, "native_A4_residual", root)
        x = _array(packet, "x_augmented", root)
        rho = float(np.linalg.norm(residual) / np.linalg.norm(rhs))
        field = record["field_metrics"]["fields"]
        l2 = float(field["L2"]["absolute_error_norm"] / field["L2"]["reference_norm"])
        curl = float(field["scaled_curl"]["absolute_error_norm"] / field["scaled_curl"]["reference_norm"])
        residual_identity = record["native_residual_identity"]
        closure = float(residual_identity["absolute_difference"] / residual_identity["operation_scale"])
        old = exact_by_stem[stem]
        old_identity = old["packet"]["identity"]
        exact_field = old["field_metrics"]
        controls = record["controls_after_solve"]
        gates = {
            "same_input_and_reference": all(identity[k] == old_identity[k] for k in (
                "input_sha256", "input_npz_sha256", "g_sha256", "reference_json_sha256", "reference_npz_sha256")),
            "solution_hash": hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest() == record["solution_sha256"],
            "one_solve": record["factor_solve_calls_after"] - record["factor_solve_calls_before"] == 1,
            "no_refinement": controls["icntl"]["10"]["value"] == 0,
            "controls_retained": controls["icntl"]["35"]["value"] == 2
            and controls["cntl"]["7"]["value"] == 1e-5,
            "original_A4_rho_agrees": bool(np.isclose(rho, record["native_A4_relative_residual"], rtol=1e-11, atol=1e-14)),
            "identity": _finite(closure) and closure <= 1e-10,
            "exact_A4_qualified": old["native_A4_relative_residual"] <= 1e-10
            and exact_field["field_l2_relative"] <= 1e-8 and exact_field["scaled_curl_relative"] <= 1e-8,
        }
        quality = _finite(rho, l2, curl) and rho <= 0.5 and l2 <= 0.25 and curl <= 0.25
        rows.append({"stem": stem, "rho": rho, "field_l2_relative": l2,
                     "scaled_curl_relative": curl, "native_identity_relative": closure,
                     "quality_pass": quality, "gates": gates, "packet_sha256": _hash(packet_path)})
    factor = summary["factor"]
    raw = factor["numeric_raw"]
    entries = {key: float(v if v >= 0 else -v * 1_000_000)
               for key in ("9", "29", "35") if isinstance((v := raw["infog"].get(key)), int)}
    flops = {key: raw["rinfog"].get(key) for key in ("3", "14")}
    stats_available = len(entries) == 3 and all(v > 0 for v in entries.values())
    stats_available = stats_available and all(isinstance(v, (float, int)) and np.isfinite(v) and v > 0 for v in flops.values())
    effect = stats_available and entries["9"] < entries["29"] and entries["35"] < entries["29"]
    matrix_keys = ("fe_rows", "port_rows", "augmented_rows", "allocated_nnz", "preallocated_nnz")
    controls = factor["backend_control_facts"]
    source = _json(directory / "run_manifest.json")
    old_source = _json(baseline / "run_manifest.json")
    control_gates = {
        "set_before_symbolic": controls["configured_before_symbolic"] is True,
        "before_symbolic_icntl35": controls["effective_after"]["35"]["value"] == 2,
        "before_symbolic_cntl7": controls["cntl_after"]["7"]["value"] == 1e-5,
        "post_symbolic_icntl35": controls["effective_after_symbolic"]["35"]["value"] == 2,
        "post_symbolic_cntl7": controls["cntl_after_symbolic"]["7"]["value"] == 1e-5,
        "post_numeric_fixed_icntl": all(
            controls["effective_after_numeric"]["icntl"][str(index)]["value"] == value
            for index, value in ((10, 0), (22, 0), (31, 0), (32, 0), (35, 2), (37, 0))),
        "one_factor_no_setup_solves": factor["factor_solve_calls_at_factorization"] == 0,
    }
    comparison_gates = {
        "BLR_resources": current_scope["passed"], "exact_resources": exact_scope["passed"],
        "all_rhs_evidence": all(all(r["gates"].values()) for r in rows),
        "matrix_identity": all(summary["matrix"][k] == exact["matrix"][k] for k in matrix_keys),
        "physical_identity": source["physical_model_sha256"] == old_source["physical_model_sha256"],
        "source_identity": source["source_sha"] == summary["source_sha"] == source["source_after"]["source_sha"],
        "controls": all(control_gates.values()),
    }
    comparison = all(comparison_gates.values())
    decision = decide_s2(quality=all(r["quality_pass"] for r in rows), comparison_valid=comparison,
                         statistics_available=stats_available, compression_effect=effect,
                         r_peak=current_scope["full_rss_peak_bytes"] / exact_scope["full_rss_peak_bytes"],
                         r_live=current_scope["live_rss_peak_bytes"] / exact_scope["live_rss_peak_bytes"])
    return {"schema": "task039extra.v16.independent-checker.v1", "source_sha": summary["source_sha"],
            "baseline_source_sha": exact["source_sha"], "directory": str(directory), "baseline": str(baseline),
            "decision": decision, "comparison_gates": comparison_gates, "control_gates": control_gates,
            "rhs": rows, "BLR_resources": current_scope, "exact_resources": exact_scope,
            "native_entries": entries, "native_flops": flops, "factor_memory": factor["mumps_memory_observation"],
            "exact_factor_memory": exact["factor"]["mumps_memory_observation"],
            "actual_storage_ratio_to_theoretical": entries["9"] / entries["29"] if stats_available else None,
            "phase_times": {"BLR_symbolic_seconds": factor["symbolic_seconds"],
                            "BLR_numeric_seconds": factor["numeric_seconds"],
                            "exact_symbolic_seconds": exact["factor"]["symbolic_seconds"],
                            "exact_numeric_seconds": exact["factor"]["numeric_seconds"],
                            "BLR_rhs": [{k: v for k, v in r.items() if k == "stem" or k.endswith("seconds")} for r in records]},
            "input_result_hashes": {str(directory / "physical_p4_blr_v16_summary.json"): _hash(directory / "physical_p4_blr_v16_summary.json"),
                                    str(baseline / "physical_p4_schur_v14_summary.json"): _hash(baseline / "physical_p4_schur_v14_summary.json")}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("baseline_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(check_run(args.run_directory.resolve(), args.baseline_directory.resolve(),
                               Path(__file__).resolve().parents[1]), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
