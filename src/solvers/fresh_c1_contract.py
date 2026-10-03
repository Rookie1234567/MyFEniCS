"""Explicit fresh-C1 admission; historical bridges remain separate.

These scalar/receipt contracts create no FE objects and perform no solve.
They never grant source, runtime, resource or remote-storage qualification.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

P6_WORKER_STATUS = "FRESH_C1_P6_COMPONENT_WORKER_PASS"
P6_CHECKER_STATUS = "FRESH_C1_P6_COMPONENT_CHECKER_PASS"
P6_CORE_STATUS = "worker_component_controls_passed_independent_checker_pending"
FRESH_LIMITS = {"action_recovery": 1e-11, "original_residual": 1e-10,
                "pure_algebra": 1e-12}
TREE_CAP_BYTES = 3 * 1024**3
WALL_SECONDS = 4500
RESERVE_BYTES = 128 * 1024**2
RAW_EXPORT_BYTES = 512 * 1024**2
NEAR_ZERO_OUTPUT = {
    "reference_normalized_magnitude_upper": 1e-8,
    "absolute_normalized_error_upper": 1e-12,
    "amplitude_and_E_units": "relative to frozen nonzero incident E0",
    "magnetic_units": "native k_cross_E/(k0*mu_r), relative to incident E0; scaled H, not amperes/m",
    "power_units": "native plane scaled-flux divided by period_area_nm2*abs(E0)^2; not SI watts",
    "existing_operation_scaled_limits_changed": False,
    "exact_zero_arithmetic_scale_requires_exact_zero_error": True,
}


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def validate_profile(stage, *, degree, auxiliary_gauge, dtn_phase_gauge,
                     live_component_oracle, historical_authority_requested=False):
    if stage not in ("p6-component", "p4-chain"):
        raise ValueError("unknown fresh-C1 stage")
    expected = 6 if stage == "p6-component" else 4
    if (degree != expected or auxiliary_gauge != "positive-h"
            or dtn_phase_gauge != "boundary_plane" or live_component_oracle is not True
            or historical_authority_requested):
        raise ValueError("fresh-C1 requires its exact degree, centered gauge and same-live oracle; no historical authority")
    return {"stage": stage, "degree": expected, "scope": (
        "actual p6 compact component only" if degree == 6 else
        "actual p4 dense-reference all-q regular/notch chain; compact quotient not qualified"),
        "tree_cap_bytes": TREE_CAP_BYTES, "wall_seconds": WALL_SECONDS,
        "reserve_bytes": RESERVE_BYTES, "uncompressed_raw_export_budget_bytes": RAW_EXPORT_BYTES,
        "unknown_cold_JIT_and_fill": True, "limits": dict(FRESH_LIMITS),
        "near_zero_output": dict(NEAR_ZERO_OUTPUT)}


def validate_component_packets(report, checker, *, expected_source, expected_environment,
                               report_sha256, provenance_sha256, artifact_manifest_sha256):
    """Bind a new p6 component to its independent current saved-data checker."""
    core = report.get("component", {})
    if (report.get("status") != P6_WORKER_STATUS
            or report.get("fresh_fixture_c1") != "p6-component"
            or report.get("source_clean_unchanged") is not True
            or report.get("source") != expected_source
            or report.get("environment") != expected_environment
            or core.get("status") != P6_CORE_STATUS
            or core.get("same_system_and_carrier") is not True
            or core.get("global_p6_matrix_created") is not False
            or core.get("global_p6_factor_created") is not False
            or core.get("quotient_constructed") is not False):
        raise ValueError("fresh p6 component/source/representation inventory is incomplete")
    actual = core.get("actual_inventory", {})
    expected_counts = {"degree": 6, "cell_count": 80, "local_dimension": 882,
        "local_interiors": 450, "local_traces": 432, "storage_rows": 55950,
        "independent_rows": 52992, "interior_rows": 36000,
        "active_trace_rows": 16992, "port_rows": 532}
    if any(actual.get(k) != v for k, v in expected_counts.items()):
        raise ValueError("fresh p6 actual full3D inventory differs")
    if any(core.get("limits", {}).get(k) != v for k, v in FRESH_LIMITS.items()):
        raise ValueError("fresh p6 mathematical limits differ")
    if (checker.get("status") != P6_CHECKER_STATUS
            or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
            or checker.get("source") != expected_source
            or checker.get("environment") != expected_environment
            or checker.get("report_sha256") != report_sha256
            or checker.get("provenance_sha256") != provenance_sha256
            or checker.get("artifact_manifest_sha256") != artifact_manifest_sha256):
        raise ValueError("fresh p6 checker is stale, swapped or unbound")
    if (not checker.get("checks") or any(x.get("passed") is not True for x in checker["checks"])
            or checker.get("cells_checked")!=list(range(80))
            or checker.get("q_alias_counts_recomputed")!=[76,152,152,152]
            or checker.get("all_saved_members_hash_checked") is not True
            or checker.get("unique_saved_members_checked")!=len(core["snapshot"]["members"])
            or set(checker.get("negative_controls",{}))!={"omitted_correction","wrong_sign","wrong_conjugation",
                                                         "Hhat_substituted_for_original_H"}
            or any(x.get("separated") is not True for x in checker["negative_controls"].values())):
        raise ValueError("fresh p6 checker full inventory/negative gates are absent or failed")
    return {"component_report_sha256": report_sha256,
            "component_provenance_sha256": provenance_sha256,
            "component_artifact_manifest_sha256": artifact_manifest_sha256,
            "component_checker_bound": True,
            "p6_scope": "component only; no p6 full-chain qualification"}


def validate_shared_fixture(report, receipt):
    """Degree may differ; physical data, mesh and frozen input must agree."""
    fields = (("input_sha256", "fixture_input_sha256"), ("axes_nm", "axes_nm"),
              ("mode_manifest_sha256", "physical_generator_manifest_sha256"),
              ("shared_fixture_configuration", "shared_fixture_configuration"))
    if any(report.get(left) is None or report[left] != receipt.get(right)
           for left, right in fields):
        raise ValueError("fresh p6 component and p4 chain do not share the exact fixture")
    return True


def validate_resource_receipt(summary, resource, source):
    """Readable whole-tree success is mandatory for both supervised stages."""
    if (summary.get("classification") != "COMPLETED" or summary.get("source_state") != source
            or summary.get("sampled_process_tree_swap_peak_bytes") != 0
            or summary.get("descendants_cleared") is not True
            or summary.get("process_tree_all_status_readable") is not True
            or summary.get("process_tree_all_identity_complete") is not True
            or resource.get("wall_seconds") != WALL_SECONDS
            or not 0 < resource.get("tree_cap_bytes", 0) <= TREE_CAP_BYTES
            or not 0 < summary.get("sampled_process_tree_rss_peak_bytes", 0) < resource["tree_cap_bytes"]
            or not 0 <= summary.get("elapsed_seconds", math.inf) <= WALL_SECONDS):
        raise ValueError("fresh worker/checker whole-tree resource evidence is incomplete")
    return True


def near_zero_output_check(actual, expected, *, normalization, name):
    """Supplement, never replace, existing per-mode operation-scaled controls."""
    import numpy as np
    if not math.isfinite(float(normalization)) or float(normalization) <= 0:
        raise ValueError("fixed output normalization must be finite and positive")
    a, e = np.asarray(actual), np.asarray(expected)
    if a.shape != e.shape or len(a) != 532 or not np.isfinite(a).all() or not np.isfinite(e).all():
        raise ValueError("complete finite532 output inventory required")
    magnitude = np.abs(e) if e.ndim == 1 else np.linalg.norm(e, axis=1)
    error = np.abs(a-e) if a.ndim == 1 else np.linalg.norm(a-e, axis=1)
    selected = magnitude / normalization <= NEAR_ZERO_OUTPUT["reference_normalized_magnitude_upper"]
    absolute = error / normalization
    max_error = float(np.max(absolute[selected])) if np.any(selected) else 0.0
    return {"name": name, "compared_modes": 532, "near_zero_modes": int(np.count_nonzero(selected)),
            "reference_normalized_magnitude_upper": NEAR_ZERO_OUTPUT["reference_normalized_magnitude_upper"],
            "absolute_normalized_error_max": max_error,
            "absolute_normalized_error_upper": NEAR_ZERO_OUTPUT["absolute_normalized_error_upper"],
            "passed": bool(max_error <= NEAR_ZERO_OUTPUT["absolute_normalized_error_upper"]),
            "supplement_to_unchanged_operation_scale_gate": True}
