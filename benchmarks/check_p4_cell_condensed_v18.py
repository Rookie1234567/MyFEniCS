"""Read-only V18 admission from saved arrays, norms and resource samples.

Exact condensation is admitted by equivalence and safety.  Memory benefit
selects the optional BLR backend only; it never vetoes qualified exact U4.
No assembly, factorization or reference generation occurs in this checker.
"""

from __future__ import annotations

import math
import re
import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.check_p4_blr_v16 import GIB, STEMS, _array, _hash, _json, _jsonl, resource_scope
from benchmarks.check_p4_blr_tradeoff_v17 import (
    _array_sha256,
    _control_value,
    _field_facts,
    _raw_compression_facts,
    _stdout_coverage_facts,
    memory_facts,
)


def _finite_nonnegative(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) >= 0.0
    except (TypeError, ValueError):
        return False


def quality_facts(rows: Sequence[Mapping[str, Any]], *, backend: str) -> dict:
    """Use independently reconstructed norms, never worker PASS labels."""
    if backend not in {"exact", "blr"}:
        raise ValueError("V18 permits only exact and the single tau=1e-5 BLR")
    limits = {"rho": 1e-10 if backend == "exact" else 0.5,
              "field_l2_relative": 1e-8 if backend == "exact" else 0.25,
              "scaled_curl_relative": 1e-8 if backend == "exact" else 0.25,
              "native_identity_relative": 1e-10}
    checks = {"three_frozen_rhs": tuple(r.get("stem") for r in rows) == STEMS}
    for row in rows:
        stem = str(row.get("stem"))
        for key, limit in limits.items():
            value = row.get(key)
            checks[f"{stem}.{key}"] = _finite_nonnegative(value) and float(value) <= limit
        checks[f"{stem}.strict_slave_zero"] = row.get("slave_nonzero_count") == 0
        checks[f"{stem}.one_solve"] = row.get("factor_solve_call_delta") == 1
        checks[f"{stem}.evidence"] = bool(row.get("evidence_checks")) and all(
            value is True for value in row.get("evidence_checks", {}).values()
        )
    return {"backend": backend, "limits": limits, "checks": checks,
            "quality_pass": all(checks.values()),
            "failures": [key for key, passed in checks.items() if not passed]}


def choose_backend(*, exact_quality: bool, common_correct: bool,
                   exact_safe: bool, blr_quality: bool = False,
                   blr_safe: bool = False, compression_present: bool = False,
                   comparison_valid: bool = False,
                   peak_ratio: Any = None, live_ratio: Any = None) -> dict:
    """Apply the fixed U3 rule while preserving qualified exact fallback."""
    memory = memory_facts(peak_ratio=peak_ratio, live_ratio=live_ratio)
    eligible = bool(exact_quality and common_correct and exact_safe)
    use_blr = bool(eligible and blr_quality and blr_safe and compression_present
                   and comparison_valid and memory["memory_pass"])
    return {"selected_backend": ("blr" if use_blr else "exact") if eligible else None,
            "admit_u4": eligible, "memory": memory,
            "exact_admission_has_memory_saving_threshold": False,
            "status": "SELECT_BLR" if use_blr else "SELECT_EXACT" if eligible
            else "COMMON_CORE_OR_EXACT_NOT_QUALIFIED",
            "time_policy": "observe_only"}


def exact_fallback_allowed(*, selected_backend: str, original_pass: bool,
                           exact_core_safe: bool, common_error: bool,
                           prior_fallback_count: int) -> bool:
    return bool(selected_backend == "blr" and not original_pass and exact_core_safe
                and not common_error and prior_fallback_count == 0)


def resource_facts(directory: Path) -> dict:
    """Separate the three-input main window from U2's extra calls."""
    samples = _jsonl(directory / "watchdog/resources.jsonl")
    events = _jsonl(directory / "v18_events.jsonl")
    worker = _jsonl(directory / "v18_worker_resources.jsonl")
    run = _json(directory / "run_summary.json")
    manifest = _json(directory / "run_manifest.json")
    numeric = [r for r in events if r["event"] == "schur_factor_numeric_complete"]
    ends = [r for r in events if r["event"] == "u2_main_rhs_window_complete"]
    if len(numeric) != 1 or len(ends) != 1:
        raise ValueError("one numeric and one explicit main-window end are required")
    start, end = numeric[0]["timestamp_ns"], ends[0]["timestamp_ns"]
    main = [s for s in samples if s["timestamp_ns"] <= end]
    live = [s for s in main if s["timestamp_ns"] >= start]
    if not main or not live or not worker:
        raise ValueError("main/live/worker samples are missing")
    authority = run["resource_authority"]
    cap = int(authority["launch_envelope"]["launch_cap_bytes"])
    swap = authority["global_swap_activity"]
    gates = {
        "readable": all(s["all_status_readable"] and s["pss_all_readable"] for s in samples),
        "tree_cap": 0 < max(s["rss_bytes"] for s in samples) <= cap <= 8 * GIB,
        "inventory_cap": max(s["inventory_peak_bytes"] for s in worker) <= 6 * GIB,
        "workspace_cap": max(s["workspace_peak_bytes"] for s in worker) <= GIB,
        "reserve": all(s["memory_envelope"]["effective_available_bytes"] >=
                       s["memory_envelope"]["reserve_bytes"] for s in samples),
        "zero_swap": all(s["swap_bytes"] == 0 for s in samples) and all(
            swap["end"][key] == swap["baseline"][key]
            and all(s["global_swap_pages"][key] == swap["baseline"][key] for s in samples)
            for key in ("pswpin_pages", "pswpout_pages")),
        "cleaned": authority["descendants_cleared"] is True
                   and authority["remaining_child_pids"] == [],
        "clean_source": manifest["source_after"]["tracked_and_nonignored_untracked_clean"] is True,
        "observe_only": run["time_policy"] == "observe_only" and run["time_gate_evaluated"] is False
                        and all(s["time_policy"] == "observe_only"
                                and not s["time_gate_evaluated"] for s in samples),
    }
    return {"scope": "continuous_parent_process_tree", "gates": gates,
            "passed": all(gates.values()), "main_window_end_ns": end,
            "main_full_rss_peak_bytes": max(s["rss_bytes"] for s in main),
            "main_live_rss_peak_bytes": max(s["rss_bytes"] for s in live),
            "main_full_pss_peak_bytes": max(s["pss_bytes"] for s in main),
            "main_live_pss_peak_bytes": max(s["pss_bytes"] for s in live),
            "whole_run_rss_peak_bytes": max(s["rss_bytes"] for s in samples),
            "inventory_peak_bytes": max(s["inventory_peak_bytes"] for s in worker),
            "workspace_peak_bytes": max(s["workspace_peak_bytes"] for s in worker),
            "full_workflow_monotonic_seconds": run["full_workflow_monotonic_seconds"],
            "hashes": {name: _hash(directory / name) for name in (
                "watchdog/resources.jsonl", "v18_events.jsonl", "v18_worker_resources.jsonl",
                "run_summary.json", "run_manifest.json")}}


def rhs_facts(packet: Mapping, record: Mapping, *, root: Path,
              baseline_identity: Mapping, slave_rows: np.ndarray, backend: str) -> dict:
    """Recompute native quality and strict storage checks from saved vectors."""
    identity = packet["identity"]
    rhs = _array(packet, "g", root)
    residual = _array(packet, "native_A4_residual", root)
    solution = _array(packet, "x_storage", root)
    action = _array(packet, "native_action", root)
    input_path = Path(identity["input_json"])
    if not input_path.is_absolute():
        input_path = root / input_path
    original = _array(_json(input_path), "g", root)
    field_l2, curl, _ = _field_facts(record)
    top = _array(packet, "augmented_top_residual", root)
    reconstructed = _array(packet, "native_identity_reconstructed", root)
    scale = max(float(np.linalg.norm(rhs)) + float(np.linalg.norm(action)),
                float(np.linalg.norm(top)) + float(np.linalg.norm(top - reconstructed)),
                np.finfo(float).tiny)
    difference = float(np.linalg.norm(residual - reconstructed))
    controls = record["controls_after_solve"]
    expected35 = 0 if backend == "exact" else 2
    identity_keys = ("input_sha256", "input_npz_sha256", "g_sha256",
                     "reference_json_sha256", "reference_npz_sha256", "stem")
    checks = {
        "same_input_and_reference": all(identity[k] == baseline_identity[k] for k in identity_keys),
        "input_file": _hash(input_path) == identity["input_sha256"],
        "same_g": np.array_equal(rhs, original),
        "g_hash": _array_sha256(rhs) == identity["g_sha256"],
        "native_action": np.array_equal(action, rhs - residual),
        "matching_storage": solution.shape == rhs.shape == residual.shape,
        "input_unchanged": record.get("rhs_input_unchanged") is True,
        "no_refinement": record.get("hidden_refinement") is False,
        "icntl10": _control_value(controls, "icntl", 10) == 0,
        "icntl35": _control_value(controls, "icntl", 35) == expected35,
        "positive_identity_scale": math.isfinite(scale) and scale > 0,
        "identity_difference_norm": math.isclose(
            difference, float(record["native_residual_identity"]["absolute_difference"]),
            rel_tol=1e-12, abs_tol=1e-30),
        "identity_operation_scale": math.isclose(
            scale, float(record["native_residual_identity"]["operation_scale"]), rel_tol=1e-12),
    }
    if backend == "blr":
        checks["cntl7"] = _control_value(controls, "cntl", 7) == 1e-5
    for name, digest in (("input_npz", "input_npz_sha256"),
                         ("reference_json", "reference_json_sha256"),
                         ("reference_npz", "reference_npz_sha256")):
        path = Path(identity[name])
        checks[name] = _hash(path if path.is_absolute() else root / path) == identity[digest]
    norm = float(np.linalg.norm(rhs))
    return {"stem": identity["stem"], "rho": float(np.linalg.norm(residual)) / norm if norm else math.inf,
            "field_l2_relative": field_l2, "scaled_curl_relative": curl,
            "native_identity_relative": difference / scale if scale > 0 else math.inf,
            "slave_nonzero_count": int(np.count_nonzero(solution[slave_rows])),
            "factor_solve_call_delta": record["factor_solve_calls_after"] - record["factor_solve_calls_before"],
            "evidence_checks": {key: bool(value) for key, value in checks.items()}}


def compression_facts(summary: Mapping) -> dict:
    """Use this condensed matrix's native INFOG counters as denominator."""
    return _raw_compression_facts(summary)


def matrix_identity_facts(before: Mapping, after: Mapping,
                          *, exact_matrix: Mapping | None = None) -> dict:
    """Validate recorded CSR content identity, not just row and NNZ counts."""
    required = ("shape", "dtype", "nnz", "mapping_sha256", "values_sha256", "csr_sha256")
    checks = {"required_fields": all(key in before and key in after for key in required),
              "complex128": before.get("dtype") == "complex128",
              "nonempty_sparse": type(before.get("nnz")) is int and before["nnz"] > 0,
              "unchanged_through_factor": bool(before) and before == after}
    for key in ("mapping_sha256", "values_sha256", "csr_sha256"):
        checks[key] = bool(re.fullmatch(r"[0-9a-f]{64}", str(before.get(key, ""))))
    if exact_matrix is not None:
        checks["same_exact_and_blr_matrix"] = all(before.get(k) == exact_matrix.get(k)
                                                     for k in required)
    return {"checks": checks, "passed": all(checks.values()),
            "matrix": dict(before),
            "scope": "streamed matrix bytes at worker assembly and factor boundaries"}


def check_run(directory: Path, baseline: Path, root: Path, *, exact_control: Path | None = None) -> dict:
    """Check one completed control without launching any numerical work."""
    summary_path = directory / "physical_p4_cell_condensed_v18_summary.json"
    summary = _json(summary_path)
    backend = summary["backend"]
    records = summary["solve_records"]
    baseline_summary = _json(baseline / "physical_p4_schur_v14_summary.json")
    baseline_rows = {row["stem"]: row for row in baseline_summary["solve_records"]}
    mapping = _json(directory / "v18_mapping_identity.json")
    slaves = _array(mapping, "slave_rows", root)
    rows, solutions, inputs = [], [], []
    if tuple(row["stem"] for row in records) != STEMS:
        raise ValueError("three frozen RHS records are required")
    for record in records:
        packet = _json(directory / "rhs_packets" / f"{record['stem']}.json")
        facts = rhs_facts(packet, record, root=root,
                          baseline_identity=baseline_rows[record["stem"]]["packet"]["identity"],
                          slave_rows=slaves, backend=backend)
        facts["evidence_checks"].update(
            one_symbolic=record["symbolic_calls"] == 1,
            one_numeric=record["numeric_calls"] == 1,
            local_lu_reused=record["local_lu_identity_unchanged"] is True,
            saved_solution_hash=_array_sha256(_array(packet, "x_storage", root)) == record["solution_sha256"],
            timings=all(_finite_nonnegative(record.get(key)) for key in (
                "apply_seconds", "native_evaluation_seconds", "field_metric_seconds", "packet_save_seconds", "elapsed_seconds")),
        )
        rows.append(facts)
        solutions.append(_array(packet, "x_storage", root))
        inputs.append(_array(packet, "g", root))
    quality = quality_facts(rows, backend=backend)
    extra_rows = []
    if backend == "exact":
        expected = (
            ("extra_01_repeat", inputs[0], solutions[0]),
            ("extra_01_plus_i02", inputs[0] + 1j * inputs[1], solutions[0] + 1j * solutions[1]),
            ("extra_09_minus_01", inputs[2] - inputs[0], solutions[2] - solutions[0]),
        )
        actual_rows = summary["additional_solve_records"]
        if tuple(r["stem"] for r in actual_rows) != tuple(r[0] for r in expected):
            raise ValueError("exact U2 requires precisely its three extra calls")
        for record, (stem, g_expected, c_expected) in zip(actual_rows, expected, strict=True):
            packet = _json(directory / "additional_rhs" / f"{stem}.json")
            g, c, residual = (_array(packet, key, root) for key in ("g", "x_storage", "native_A4_residual"))
            rho = float(np.linalg.norm(residual) / np.linalg.norm(g))
            scale = sum(float(np.linalg.norm(x)) for x in solutions)
            linearity = float(np.linalg.norm(c - c_expected) / scale)
            checks = {"expected_input": bool(np.array_equal(g, g_expected)), "rho": rho <= 1e-10,
                      "linearity": linearity <= 1e-10, "slave_zero": not np.any(c[slaves]),
                      "one_solve": record["factor_solve_calls_after"] - record["factor_solve_calls_before"] == 1,
                      "one_factor": record["symbolic_calls"] == record["numeric_calls"] == 1,
                      "local_lu_reused": record["local_lu_identity_unchanged"] is True}
            extra_rows.append({"stem": stem, "rho": rho, "linearity_relative": linearity,
                               "checks": checks, "passed": all(checks.values())})
    elif summary["additional_solve_records"]:
        raise ValueError("U3 must not add extra solves")
    exact_matrix = None
    if exact_control is not None:
        exact_matrix = _json(exact_control / "physical_p4_cell_condensed_v18_summary.json")["matrix_identity_before_factor"]
    matrix = matrix_identity_facts(summary["matrix_identity_before_factor"],
                                   summary["matrix_identity_after_factor"], exact_matrix=exact_matrix)
    matrix["checks"]["unchanged_through_calls"] = summary["matrix_identity_after_calls"] == summary["matrix_identity_before_factor"]
    matrix["passed"] = all(matrix["checks"].values())
    resources = resource_facts(directory)
    baseline_resources = resource_scope(baseline, "v14")
    controls = summary["factor"]["controls_before_symbolic"]
    expected35 = 0 if backend == "exact" else 2
    count = summary["factor_call_counts"]
    construction = summary["stack"]["condensation"]
    structural = {
        "matrix": matrix["passed"], "resources": resources["passed"],
        "one_symbolic_numeric": count["symbolic"] == count["numeric"] == 1,
        "solve_budget": count["solve"] == (6 if backend == "exact" else 3),
        "sum_before_schur": construction["sum_duplicate_cell_integrals"] is True,
        "strict_local_checks": construction["strict_local_checks"] is True,
        "no_full_p4_matrix": construction["full_global_matrix_allocated"] is False,
        "no_full_trace_matrix": construction["full_trace_matrix_allocated"] is False,
        "no_macro_mumps": summary["stack"]["internal_factor_count"] == 0,
        "retained_through_postprocess": summary["stack"]["retain_through_postprocess_v18"] is True,
        "icntl10_before_symbolic": _control_value(controls, "icntl", 10) == 0,
        "icntl35_before_symbolic": _control_value(controls, "icntl", 35) == expected35,
        "additional_calls": all(r["passed"] for r in extra_rows),
    }
    if backend == "blr":
        structural["tau_before_symbolic"] = _control_value(controls, "cntl", 7) == 1e-5
    # Common action/metric construction is the same qualified _build_common;
    # new algorithm storage is the subject of comparison, not a scope mismatch.
    baseline_abi = baseline_summary["abi"]
    comparable = summary["abi"] == baseline_abi and baseline_resources["passed"]
    coverage = (_stdout_coverage_facts(directory, _json(directory / "run_summary.json"))
                if backend == "blr" else {"status": "not_applicable_exact", "passed": True})
    if backend == "blr":
        structural["coverage_statistics"] = coverage["passed"]
        for index, expected in ((36, 0), (37, 0), (38, 600)):
            structural[f"icntl{index}_before_symbolic"] = _control_value(controls, "icntl", index) == expected
    denominator = resource_facts(exact_control) if exact_control is not None else baseline_resources
    denominator_full = denominator.get("main_full_rss_peak_bytes", denominator.get("full_rss_peak_bytes"))
    denominator_live = denominator.get("main_live_rss_peak_bytes", denominator.get("live_rss_peak_bytes"))
    memory = memory_facts(peak_ratio=resources["main_full_rss_peak_bytes"] / denominator_full,
                          live_ratio=resources["main_live_rss_peak_bytes"] / denominator_live)
    return {"schema": "task039extra.v18.independent-checker.v1", "source_sha": summary["source_sha"],
            "backend": backend, "stage": summary["stage"], "directory": str(directory),
            "summary_sha256": _hash(summary_path), "quality": quality, "rows": rows,
            "additional_rows": extra_rows, "structural_checks": structural,
            "control_qualified": bool(quality["quality_pass"] and all(structural.values())),
            "matrix_identity": matrix, "resources": resources,
            "baseline_resources": baseline_resources, "comparison_valid": bool(comparable),
            "memory": memory, "compression": compression_facts(summary), "coverage": coverage,
            "memory_denominator": str(exact_control or baseline),
            "time_policy": "observe_only", "official_p6_pass": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--exact-control", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    facts = check_run(args.directory, args.baseline, args.root, exact_control=args.exact_control)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(facts, indent=2, allow_nan=False) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"control_qualified": facts["control_qualified"],
                      "quality": facts["quality"]["quality_pass"],
                      "resources": facts["resources"]["passed"]}))


if __name__ == "__main__":
    main()
