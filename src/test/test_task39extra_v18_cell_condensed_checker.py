"""V18 branching boundaries, independent of PETSc and worker PASS labels."""

import pytest
import numpy as np

from benchmarks import check_p4_cell_condensed_v18 as checker

from benchmarks.check_p4_cell_condensed_v18 import (
    STEMS, choose_backend, exact_fallback_allowed, matrix_identity_facts, quality_facts,
)


def test_exact_admission_survives_missing_or_worse_memory_comparison():
    for comparison, peak, live in [(False, None, None), (True, 1.3, 1.4)]:
        result = choose_backend(exact_quality=True, common_correct=True, exact_safe=True,
                                comparison_valid=comparison, peak_ratio=peak, live_ratio=live)
        assert result["admit_u4"]
        assert result["selected_backend"] == "exact"
        assert not result["exact_admission_has_memory_saving_threshold"]


@pytest.mark.parametrize("peak,live,expected", [
    (0.9, 0.99, "blr"), (0.900001, 0.800001, "exact"),
    (1.05, 0.8, "blr"), (1.050001, 0.8, "exact"),
])
def test_blr_memory_boundaries(peak, live, expected):
    result = choose_backend(exact_quality=True, common_correct=True, exact_safe=True,
                            blr_quality=True, blr_safe=True, compression_present=True,
                            comparison_valid=True, peak_ratio=peak, live_ratio=live)
    assert result["selected_backend"] == expected


@pytest.mark.parametrize("failed", ["blr_quality", "blr_safe", "compression_present", "comparison_valid"])
def test_blr_failure_preserves_safe_exact(failed):
    facts = dict(exact_quality=True, common_correct=True, exact_safe=True,
                 blr_quality=True, blr_safe=True, compression_present=True,
                 comparison_valid=True, peak_ratio=.8, live_ratio=.7)
    facts[failed] = False
    assert choose_backend(**facts)["selected_backend"] == "exact"


@pytest.mark.parametrize("failed", ["exact_quality", "common_correct", "exact_safe"])
def test_common_or_exact_failure_cannot_be_masked_by_blr(failed):
    facts = dict(exact_quality=True, common_correct=True, exact_safe=True,
                 blr_quality=True, blr_safe=True, compression_present=True,
                 comparison_valid=True, peak_ratio=.8, live_ratio=.7)
    facts[failed] = False
    result = choose_backend(**facts)
    assert result["selected_backend"] is None
    assert not result["admit_u4"]


def test_exact_quality_rejects_missing_rhs_nonfinite_and_tiny_slave_values():
    rows = [dict(stem=stem, rho=1e-10, field_l2_relative=1e-8,
                 scaled_curl_relative=1e-8, native_identity_relative=1e-10,
                 slave_nonzero_count=0, factor_solve_call_delta=1,
                 evidence_checks={"raw": True}, status="PASS") for stem in STEMS]
    assert quality_facts(rows, backend="exact")["quality_pass"]
    assert not quality_facts(rows[:2], backend="exact")["quality_pass"]
    for key, value in [("rho", float("nan")), ("rho", -1),
                       ("rho", 1.000001e-10), ("slave_nonzero_count", 1),
                       ("factor_solve_call_delta", 2), ("evidence_checks", {})]:
        altered = [dict(row) for row in rows]
        altered[0][key] = value
        assert not quality_facts(altered, backend="exact")["quality_pass"]


def test_only_one_explicit_exact_original_fallback():
    facts = dict(selected_backend="blr", original_pass=False, exact_core_safe=True,
                 common_error=False, prior_fallback_count=0)
    assert exact_fallback_allowed(**facts)
    for key, value in [("selected_backend", "exact"), ("original_pass", True),
                       ("exact_core_safe", False), ("common_error", True),
                       ("prior_fallback_count", 1)]:
        assert not exact_fallback_allowed(**{**facts, key: value})


def test_same_dimensions_cannot_mask_changed_matrix_contents():
    before = dict(shape=[21_824, 21_824], dtype="complex128", nnz=1,
                  mapping_sha256="a" * 64, values_sha256="b" * 64, csr_sha256="c" * 64)
    assert matrix_identity_facts(before, dict(before))["passed"]
    changed = {**before, "values_sha256": "d" * 64, "csr_sha256": "e" * 64}
    assert not matrix_identity_facts(before, changed)["passed"]
    assert not matrix_identity_facts(changed, changed, exact_matrix=before)["passed"]
    assert not matrix_identity_facts({}, {})["passed"]


def test_raw_rhs_norms_and_strict_storage_override_pass_labels(monkeypatch, tmp_path):
    g = np.array([3., 4., 0.], complex)
    zero = np.zeros(3, complex)
    packet = dict(g=g, x_storage=g / 2, native_A4_residual=zero,
                  native_action=g, augmented_top_residual=zero,
                  native_identity_reconstructed=zero)
    identity = {k: "fixture" for k in ("input_json", "input_npz", "reference_json",
                "reference_npz", "input_sha256", "input_npz_sha256",
                "reference_json_sha256", "reference_npz_sha256")}
    identity.update(g_sha256=checker._array_sha256(g), stem=STEMS[0])
    packet["identity"] = identity
    monkeypatch.setattr(checker, "_array", lambda p, k, _root: p[k])
    monkeypatch.setattr(checker, "_json", lambda _path: {"g": g})
    monkeypatch.setattr(checker, "_hash", lambda _path: "fixture")
    record = dict(field_metrics={"field_l2_relative": 0., "scaled_curl_relative": 0.,
                  "fields": {k: {"absolute_error_norm": 0., "reference_norm": 2.}
                             for k in ("L2", "scaled_curl")}},
                  controls_after_solve={"icntl": {"10": 0, "35": 0}},
                  rhs_input_unchanged=True, hidden_refinement=False,
                  native_residual_identity={"absolute_difference": 0., "operation_scale": 10.},
                  factor_solve_calls_before=0, factor_solve_calls_after=1, status="PASS")
    def check():
        return checker.rhs_facts(packet, record, root=tmp_path,
                                  baseline_identity=identity, slave_rows=np.array([2]), backend="exact")
    assert all(check()["evidence_checks"].values())
    packet["x_storage"][2] = 1e-300
    assert check()["slave_nonzero_count"] == 1
    packet["native_A4_residual"] = g.copy()
    assert check()["rho"] == 1.
    assert not check()["evidence_checks"]["native_action"]


def test_main_memory_window_excludes_extra_calls_but_safety_does_not(monkeypatch, tmp_path):
    samples = [dict(timestamp_ns=t, rss_bytes=r, pss_bytes=r, swap_bytes=0,
                    all_status_readable=True, pss_all_readable=True,
                    memory_envelope=dict(effective_available_bytes=8 << 30, reserve_bytes=4 << 30),
                    global_swap_pages=dict(pswpin_pages=0, pswpout_pages=0),
                    time_policy="observe_only", time_gate_evaluated=False)
               for t, r in ((1, 100), (3, 200), (5, 800))]
    events = [dict(event="schur_factor_numeric_complete", timestamp_ns=2),
              dict(event="u2_main_rhs_window_complete", timestamp_ns=4)]
    run = dict(time_policy="observe_only", time_gate_evaluated=False,
               full_workflow_monotonic_seconds=5., resource_authority=dict(
                   launch_envelope=dict(launch_cap_bytes=8 << 30),
                   global_swap_activity=dict(baseline=dict(pswpin_pages=0, pswpout_pages=0),
                                             end=dict(pswpin_pages=0, pswpout_pages=0)),
                   descendants_cleared=True, remaining_child_pids=[]))
    worker = [dict(inventory_peak_bytes=1000, workspace_peak_bytes=1000)]
    monkeypatch.setattr(checker, "_jsonl", lambda p: samples if p.name == "resources.jsonl"
                        else events if p.name == "v18_events.jsonl" else worker)
    monkeypatch.setattr(checker, "_json", lambda p: run if p.name == "run_summary.json" else
                        {"source_after": {"tracked_and_nonignored_untracked_clean": True}})
    monkeypatch.setattr(checker, "_hash", lambda p: "fixture")
    facts = checker.resource_facts(tmp_path)
    assert facts["passed"]
    assert facts["main_full_rss_peak_bytes"] == facts["main_live_rss_peak_bytes"] == 200
    assert facts["whole_run_rss_peak_bytes"] == 800
    samples[-1]["swap_bytes"] = 1
    assert not checker.resource_facts(tmp_path)["passed"]
