"""V20 release claims must agree with chronology and durable full vectors."""

from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from benchmarks import check_dual_condensed_memory_v20 as checker


def _timeline():
    sequence = [
        ("v20_complete_field_packet_saved", {}),
        ("y3_independent_final_residual_complete", {}),
        ("v20_release_gate_checked", {"field_packet_saved": True, "pre_release_A6_passed": True,
                                      "pre_release_identity_passed": True, "pre_release_A6_relative": 1e-7}),
        ("v20_preconditioner_release_started", {}),
        ("v14_inventory_released", {"label": "v14_h6"}),
        ("v20_preconditioner_release_complete", {}),
        ("v20_p6_release_started", {}),
        ("v14_inventory_released", {"label": "v20_p6_local_caches"}),
        ("v20_p6_release_complete", {"owner_refs_cleared": True}),
        ("v20_p4_release_started", {}),
        ("v14_inventory_released", {"label": "v18_exact_condensed_global"}),
        ("v14_inventory_released", {"label": "v18_exact_condensed_matrix"}),
        ("v14_inventory_released", {"label": "v18_exact_port_recovery"}),
        ("v20_p4_release_complete", {"matrix_lifecycle_policy": "MATRIX_RETAINED_BACKEND_DEPENDENCY",
                                     "factor_destroy_before_matrix": True}),
        ("v20_post_release_final_residual_complete", {}),
        ("y3_physical_output_comparison_complete", {}),
    ]
    return [{"event": name, "facts": facts, "timestamp_ns": index + 1}
            for index, (name, facts) in enumerate(sequence)]


def test_new_timeline_accepts_release_before_official_not_old_retention():
    events = _timeline()
    assert checker.release_timeline_facts(events)["passed"]
    for row in events:
        if row["event"] == "v20_p4_release_complete":
            row["timestamp_ns"] = 100
    assert not checker.release_timeline_facts(events)["passed"]


@pytest.mark.parametrize("event", [
    "v20_complete_field_packet_saved", "y3_independent_final_residual_complete",
    "v20_post_release_final_residual_complete", "v20_p6_release_complete",
])
def test_missing_or_duplicate_completion_is_not_a_pass(event):
    events = _timeline()
    assert not checker.release_timeline_facts([e for e in events if e["event"] != event])["passed"]
    events.append(deepcopy(next(e for e in events if e["event"] == event)))
    assert not checker.release_timeline_facts(events)["passed"]


def test_ledger_debit_before_real_release_is_rejected():
    events = _timeline()
    next(e for e in events if e["facts"].get("label") == "v20_p6_local_caches")["timestamp_ns"] = 1
    assert not checker.release_timeline_facts(events)["passed"]


@pytest.mark.parametrize("key,value", [
    ("pre_release_A6_relative", 2e-6), ("pre_release_A6_relative", float("nan")),
    ("pre_release_identity_passed", False), ("field_packet_saved", False),
])
def test_a_positive_release_label_does_not_override_its_gate(key, value):
    events = _timeline()
    next(e for e in events if e["event"] == "v20_release_gate_checked")["facts"][key] = value
    assert not checker.release_timeline_facts(events)["passed"]


@pytest.fixture
def field_packet(monkeypatch):
    full = np.zeros(173802, dtype=np.complex128)
    full[0], full[-1] = 1 + 2j, 3 - 4j
    rhs = full * (0.2 + 0.1j)
    y = np.zeros(51272, dtype=np.complex128)
    y[-1] = 0.7j
    monkeypatch.setattr(checker, "RHS_SHA", checker._array_sha256(rhs))
    return [full, rhs, y, y[-80:].copy(), np.array([1, 3, 7], dtype=np.int32),
            full.copy(), rhs.copy(), full.copy(), rhs.copy()]


def test_saved_full_field_and_rhs_are_identical_after_release(field_packet):
    assert checker.saved_field_facts(*field_packet)["passed"]
    field_packet[7][0] += 1e-14j
    assert not checker.saved_field_facts(*field_packet)["passed"]


def test_actual_slave_entry_cannot_be_hidden_by_unchanged_packet_hashes(field_packet):
    for index in (0, 5, 7):
        field_packet[index][3] = 1e-30j
    facts = checker.saved_field_facts(*field_packet)
    assert facts["checks"]["same_full_solution"]
    assert not facts["checks"]["strict_slave_zero"]


def test_trace_only_save_cannot_pass_as_full_field(field_packet):
    for index in (0, 5, 7):
        field_packet[index] = field_packet[index][:51272]
    assert not checker.saved_field_facts(*field_packet)["passed"]


def test_port_state_cannot_change_across_saved_recovery(field_packet):
    field_packet[3][-1] += 1e-14
    assert not checker.saved_field_facts(*field_packet)["passed"]


def test_compiler_peak_is_kept_in_full_and_preparation_scope():
    events = [{"event": name, "timestamp_ns": stamp} for name, stamp in (
        ("schur_factor_symbolic_started", 3), ("v20_outer_ksp_started", 5),
        ("y3_independent_final_residual_complete", 7))]
    samples = []
    for stamp, rss in ((2, 400), (4, 300), (6, 250), (8, 120)):
        samples.append({"timestamp_ns": stamp, "elapsed_seconds": stamp / 2,
                        "rss_bytes": rss, "pss_bytes": rss - 1,
                        "members": [{"pid": 1, "ppid": 0, "comm": "cc1" if stamp == 2 else "python",
                                     "rss_bytes": rss, "pss_bytes": rss - 1, "swap_bytes": 0}]})
    facts = checker.phase_resource_facts(samples, events)
    assert facts["full"]["rss_bytes"] == facts["compiler_subset"]["rss_bytes"] == 400
    assert facts["phases"]["pre_factor_preparation"]["rss_bytes"] == 400
    assert facts["iteration_without_compiler_subset"]["rss_bytes"] == 250
    assert checker.phase_resource_facts(samples, events[:-1])["status"] == "EVIDENCE_INCOMPLETE"


def test_warm_hit_cannot_claim_cold_reorder_benefit(tmp_path):
    target = str(tmp_path / "formal" / (checker.TARGET_MODULE + ".so"))
    role_names = [f"postprocess_component_l2_{i}" for i in range(3)] + [
        f"rta_region_{q}_{r}" for q in ("volume", "absorption") for r in ("grating", "substrate")
    ] + ["postprocess_E_to_H_expression", "diffraction_E_to_H_expression"]
    facts = {
        "roles": {k: {"dtype": "complex128", "rank": 2, "module_file": target}
                  for k in ("p6_condensation", "p4_condensation")},
        "cache": {"formal_cache_dir": str(tmp_path / "formal"), "source_cache_dir": str(tmp_path / "shared"),
                  "source_cache_untouched": True, "excluded_module_family": checker.TARGET_MODULE},
        "jit_options": {"cffi_extra_compile_args": ["-O2", "-g0"], "cffi_debug": False},
        "p6_module_reused_by_adapter": True, "p4_module_reused_by_stack": True,
        "official_evaluation_roles": [{"role": r} for r in role_names],
        "compiler_events": [{"module_files": [target], "cache_hit": False,
                             "code": ["<non_none>", "<non_none>"]}],
    }
    events = [{"event": name, "timestamp_ns": stamp, "facts": facts} for name, stamp in (
        ("v20_form_preparation_started", 1), ("v20_form_preparation_complete", 3),
        ("schur_factor_symbolic_started", 5))]
    samples = [{"timestamp_ns": 2, "members": [{"comm": "cc1"}]}]
    assert checker.jit_preparation_facts(events, samples)["cold_reorder_demonstrated"]
    facts["compiler_events"][0].update(cache_hit=True, code=[None, None])
    checked = checker.jit_preparation_facts(events, samples)
    assert checked["passed"]  # Kernel preparation remains numerically usable.
    assert not checked["cold_reorder_demonstrated"]
    facts["roles"]["p6_condensation"]["rank"] = 1
    assert not checker.jit_preparation_facts(events, samples)["passed"]


def test_cache_descriptor_and_representation_hashes_are_recomputed():
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    semantic = {"operator": "identity", "shape": [450, 450], "dtype": "float64", "logical_class_count": 12}
    representation = {"mode": "shared_read_only_per_interior_shape", "read_only": True,
                      "unique_storage_count": 1, "unique_storage_bytes": 1620000}
    arrays = {"fixture": {"sha256": "a" * 64, "shape": [1], "dtype": "complex128"}}
    cache = {"identity_cache": {"semantic": semantic, "representation": representation,
                                "semantic_sha256": digest(semantic), "representation_sha256": digest(representation)},
             "identity_cache_semantic_sha256": digest(semantic),
             "identity_cache_representation_sha256": digest(representation),
             "arrays": arrays, "array_content_sha256": digest(arrays),
             "components": {"fixture": 16}, "unique_numpy_bytes": 16}
    assert checker.cache_description_facts({"cache": cache})["passed"]
    arrays["fixture"]["sha256"] = "b" * 64
    assert not checker.cache_description_facts({"cache": cache})["passed"]
    cache["array_content_sha256"] = digest(arrays)
    representation["unique_storage_count"] = 12
    cache["identity_cache"]["representation_sha256"] = digest(representation)
    cache["identity_cache_representation_sha256"] = digest(representation)
    assert not checker.cache_description_facts({"cache": cache})["passed"]
def test_online_p4_quality_does_not_accept_only_balanced_defect_cancellation():
    from benchmarks.check_dual_condensed_memory_v20 import exact_p4_call_facts

    def boundary(defect):
        call = {"rhs_norm": 2.0, "eps_norm": defect,
                "inner": {"rhs_norm": 2.0, "native_A4_residual_norm": defect}}
        return [{"pc": {"inexact_balance": {"calls": [call, call]}}}]

    good = exact_p4_call_facts(boundary(1e-12))
    assert good["passed"]
    assert good["max_relative_residual"] == 5e-13
    assert not exact_p4_call_facts(boundary(1e-5))["passed"]
    assert not exact_p4_call_facts(boundary(float("nan")))["passed"]
    assert not exact_p4_call_facts(boundary(-1e-12))["passed"]

