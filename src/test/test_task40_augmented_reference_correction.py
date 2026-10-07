from __future__ import annotations

import numpy as np
import pytest

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.task40_v10_worker import _regular_inverse_sample_label
from src.solvers.augmented_reference_correction import (
    BOUNDED_INEXACT_LIMITS,
    BOUNDED_INEXACT_REFERENCE_PC,
    FACTOR_CALL_COUNTER_SOURCE,
    REFERENCE_PC_REJECTED,
    STRICT_REFERENCE_LIMITS,
    STRICT_REFERENCE_PASS,
    apply_one_augmented_residual_correction,
    augmented_port_state_offset,
    augmented_rhs_sha256,
    evaluate_complete_augmented_residual,
    q_solve_limit,
    recheck_reference_pc_final_admission,
    select_reference_pc_candidate,
)


def _q_rows():
    return [
        {"q": q, "true_residual_relative": 1e-12}
        for q in range(4)
    ]


def _metrics(*, full=2e-10, augmented_full=3e-10, local0=1e-10, local1=8e-11, combined=1e-10, alpha=1e-11, q=3e-11):
    return {
        "full_equation": full,
        "complete_augmented_fe_equation": augmented_full,
        "local_sector_0": local0,
        "local_sector_1": local1,
        "local_combined": combined,
        "alpha_closure": alpha,
        "q_solve": q,
    }


def _candidate(metrics, *, frozen=None, state="candidate", structural=None):
    return {
        "metrics": dict(metrics),
        "frozen_scale_metrics": dict(metrics if frozen is None else frozen),
        "structural_gates": {"map": True, "recovery": True} if structural is None else structural,
        "state": state,
    }


def test_one_correction_updates_complex_fe_and_port_before_allocating_buffers():
    # D is intentionally not B.conj().T; the raw inverse must honor the full
    # augmented block, including independent primal and dual port couplings.
    V = np.array(
        [[2.0 + 0.3j, 0.1 - 0.2j], [0.4j, 1.7 - 0.2j]], dtype=np.complex128
    )
    B = np.array([[0.2 + 0.1j], [-0.3j]], dtype=np.complex128)
    D = np.array([[0.15 - 0.2j, 0.5 + 0.1j]], dtype=np.complex128)
    Hp = np.array([[1.2 - 0.3j]], dtype=np.complex128)
    A_aug = np.block([[V, B], [-D, Hp]])
    exact = np.array([0.4 + 0.2j, -0.1 + 0.7j, 0.3 - 0.4j])
    rhs = A_aug @ exact
    initial = exact + np.array([1e-6j, -2e-6, 3e-6j])
    residual = rhs - A_aug @ initial
    events = []
    allocation_records = []

    class TrackedArray(np.ndarray):
        def copy(self, order="C"):
            events.append("copy")
            return super().copy(order=order)

    def track(vector):
        return vector.view(TrackedArray)

    def allocation_gate(label, facts):
        events.append("gate")
        allocation_records.append((label, facts))

    def raw_inverse(fe_rhs, port_rhs):
        events.append("raw")
        delta = np.linalg.solve(A_aug, np.concatenate((fe_rhs, port_rhs)))
        return delta[:2], delta[2:], {
            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
            "factor_calls_before": 7,
            "factor_calls_after": 11,
            "q_true_residuals": _q_rows(),
        }

    corrected = apply_one_augmented_residual_correction(
        track(initial[:2]),
        track(initial[2:]),
        track(residual[:2]),
        track(residual[2:]),
        raw_inverse=raw_inverse,
        allocation_gate=allocation_gate,
        require_verified_solve_counter=True,
    )

    np.testing.assert_allclose(
        np.concatenate((corrected.finite_element, corrected.port_amplitudes)),
        exact,
        rtol=2e-13,
        atol=2e-13,
    )
    assert events[0] == "gate"
    assert events[1:5] == ["copy"] * 4
    assert events[-1] == "raw"
    assert corrected.audit["extra_mat_solve_count"] == 4
    assert corrected.audit["extra_mat_solve_count_status"] == "verified_from_factors_calls_delta"
    assert corrected.audit["q_phase_coverage"] == [0, 1, 2, 3]
    assert corrected.audit["all_four_q_phases_covered"] is True
    assert corrected.audit["nonrecursive_raw_inverse"] is True
    assert corrected.audit["full_fe_and_port_updated_together"] is True
    assert len(allocation_records) == 1
    gate_facts = allocation_records[0][1]
    assert gate_facts["covers_explicit_copies_delta_and_updated_state"] is True
    assert gate_facts["additional_payload_bytes"] == 2 * gate_facts["input_array_bytes"]
    assert gate_facts["simultaneous_live_array_bytes"] == 3 * gate_facts["input_array_bytes"]


def test_complete_augmented_residual_uses_independent_native_fe_and_original_h_rows():
    physical = np.array(
        [7.0 - 2.0j, 1.0 + 0.5j, -0.3 + 1.2j], dtype=np.complex128
    )
    dual = np.array(
        [0.4 + 0.2j, -0.1 + 0.7j, 0.6 - 0.8j], dtype=np.complex128
    )
    rows = np.array([1, 2], dtype=np.int64)
    fe_rhs = np.array([0.2 - 0.3j, 1.1 + 0.4j], dtype=np.complex128)
    alpha = np.array([0.8 + 0.3j, -0.2 + 0.9j], dtype=np.complex128)
    recovered = np.array([0.1 - 0.2j, 0.4 + 0.1j], dtype=np.complex128)
    h = np.array([2.0, 0.5], dtype=np.float64)
    offset = augmented_port_state_offset(alpha, recovered)
    port_rhs = h * offset

    result = evaluate_complete_augmented_residual(
        physical_action_storage=physical,
        dual_coupling_storage=dual,
        finite_element_rhs=fe_rhs,
        port_amplitudes=alpha,
        recovered_port_amplitudes=recovered,
        port_state_offset=offset,
        port_rhs=port_rhs,
        h=h,
        original_fe_equation_scale=3.0,
        independent_rows=rows,
    )

    expected_fe = fe_rhs - (physical[rows] + dual[rows])
    expected_port = port_rhs - h * (alpha - recovered)
    np.testing.assert_array_equal(result["finite_element_residual"], expected_fe)
    np.testing.assert_array_equal(result["port_residual"], expected_port)
    assert np.linalg.norm(result["finite_element_residual"]) > 0.0
    assert result["fe_row_formula"] == (
        "physical_action(u) + B * (alpha - recover_auxiliary(u))"
    )
    assert "original h" in result["port_row_formula"]
    assert result["complete_augmented_fe_equation_relative"] == pytest.approx(
        np.linalg.norm(expected_fe) / 3.0
    )
    np.testing.assert_allclose(
        result["augmented_residual_norm"],
        np.hypot(np.linalg.norm(expected_fe), np.linalg.norm(expected_port)),
    )


def test_complete_augmented_residual_keeps_tiny_nonzero_defect_and_denominator():
    tiny = 1.0e-200
    physical = np.array([-tiny + 0.0j], dtype=np.complex128)
    zero_fe = np.zeros(1, dtype=np.complex128)
    zero_port = np.zeros(1, dtype=np.complex128)
    result = evaluate_complete_augmented_residual(
        physical_action_storage=physical,
        dual_coupling_storage=zero_fe,
        finite_element_rhs=np.array([tiny + 0.0j], dtype=np.complex128),
        port_amplitudes=zero_port,
        recovered_port_amplitudes=zero_port,
        port_state_offset=zero_port,
        port_rhs=zero_port,
        h=np.ones(1, dtype=np.float64),
        original_fe_equation_scale=2.0 * tiny,
        independent_rows=np.array([0], dtype=np.int64),
    )

    assert result["finite_element_residual_norm"] == pytest.approx(2.0 * tiny)
    assert result["augmented_rhs_norm"] == pytest.approx(tiny)
    assert result["original_fe_equation_scale"] == pytest.approx(2.0 * tiny)
    assert result["complete_augmented_fe_equation_relative"] == pytest.approx(1.0)


def test_exact_zero_augmented_residual_does_not_call_raw_inverse():
    calls = []
    zero = np.zeros(2, dtype=np.complex128)

    result = apply_one_augmented_residual_correction(
        zero,
        np.zeros(1, dtype=np.complex128),
        zero,
        np.zeros(1, dtype=np.complex128),
        raw_inverse=lambda *_args: calls.append(True),
    )

    assert calls == []
    assert result.audit["attempted"] is False
    assert result.audit["extra_mat_solve_count"] == 0
    assert np.count_nonzero(result.finite_element) == 0
    assert np.count_nonzero(result.port_amplitudes) == 0
    assert augmented_rhs_sha256(zero, np.zeros(1, dtype=np.complex128)) == (
        result.audit["input_rhs_sha256"]
    )


def test_near_zero_nonzero_residual_is_not_suppressed_by_norm_underflow():
    tiny = np.nextafter(np.float64(0.0), np.float64(1.0))
    residual = np.array([complex(tiny, 0.0)], dtype=np.complex128)
    calls = []

    result = apply_one_augmented_residual_correction(
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        residual,
        np.zeros(1, dtype=np.complex128),
        raw_inverse=lambda fe, port: (calls.append((fe.copy(), port.copy())) or (
            np.zeros(1, dtype=np.complex128), np.zeros(1, dtype=np.complex128)
        )),
    )

    assert np.count_nonzero(residual) == 1
    assert len(calls) == 1
    assert result.audit["attempted"] is True
    assert result.audit["input_fe_residual_norm"] == tiny


def test_audit_rows_do_not_masquerade_as_a_real_factor_call_counter():
    result = apply_one_augmented_residual_correction(
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        np.ones(1, dtype=np.complex128),
        np.ones(1, dtype=np.complex128),
        raw_inverse=lambda *_args: (
            np.zeros(1, dtype=np.complex128),
            np.zeros(1, dtype=np.complex128),
            {"q_true_residuals": _q_rows()},
        ),
    )

    assert result.audit["q_phase_coverage"] == [0, 1, 2, 3]
    assert result.audit["extra_mat_solve_count"] is None
    assert result.audit["extra_mat_solve_count_status"] == "unknown_no_factor_counter"


def test_production_counter_must_be_bounded_and_cover_all_q_phases():
    def raw_with_bad_delta(_fe, _port):
        return np.ones(1, dtype=np.complex128), np.ones(1, dtype=np.complex128), {
            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
            "factor_calls_before": 12,
            "factor_calls_after": 17,
            "q_true_residuals": _q_rows(),
        }

    with pytest.raises(ValueError, match="four-extra-MatSolve"):
        apply_one_augmented_residual_correction(
            np.zeros(1, dtype=np.complex128),
            np.zeros(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            raw_inverse=raw_with_bad_delta,
            require_verified_solve_counter=True,
        )


def test_production_counter_rejects_missing_before_after_counter():
    with pytest.raises(ValueError, match="verified four-call"):
        apply_one_augmented_residual_correction(
            np.zeros(1, dtype=np.complex128),
            np.zeros(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            raw_inverse=lambda *_args: (
                np.zeros(1, dtype=np.complex128),
                np.zeros(1, dtype=np.complex128),
                {"q_true_residuals": _q_rows()},
            ),
            require_verified_solve_counter=True,
        )


def test_candidate_selection_uses_one_whole_state_and_original_plus_frozen_scales():
    candidates = [
        _candidate(
            _metrics(full=4e-10, local0=8e-9, local1=2e-9, combined=3e-10, alpha=4e-10, q=4e-10),
            frozen=_metrics(full=2e-8),
            state="initial",
        ),
        _candidate(
            _metrics(full=2e-10, local0=1e-10, local1=8e-11, combined=1e-10, alpha=1e-11, q=3e-11),
            frozen=_metrics(full=8e-9),
            state="corrected",
        ),
    ]

    selected = select_reference_pc_candidate(candidates)

    assert selected["admission"] == BOUNDED_INEXACT_REFERENCE_PC
    assert selected["admitted"] is True
    assert selected["strict_passed"] is False
    assert selected["selected_candidate_index"] == 1
    assert selected["candidate_facts"][1]["bounded_inexact_passed"] is True
    assert selected["candidate_facts"][1]["strict_passed"] is False
    assert selected["candidate_facts"][1]["bounded_frozen_scale_max_normalized_exceedance"] < 1.0
    assert selected["selected_max_normalized_exceedance"] < 1.0


def test_frozen_scale_is_required_for_admission_even_when_original_metrics_pass():
    candidate = _candidate(
        _metrics(full=1e-9),
        frozen=_metrics(full=1.1e-8),
        state="same-complete-state",
    )

    selected = select_reference_pc_candidate([candidate])

    assert selected["admission"] == REFERENCE_PC_REJECTED
    assert selected["candidate_facts"][0]["bounded_original_scale_max_normalized_exceedance"] <= 1.0
    assert selected["candidate_facts"][0]["bounded_frozen_scale_max_normalized_exceedance"] > 1.0


def test_structural_failure_rejects_even_when_all_original_and_frozen_metrics_pass():
    candidate = _candidate(
        _metrics(full=1e-9),
        structural={"mapping": True, "native_recovery": False},
    )

    selected = select_reference_pc_candidate([candidate])

    assert selected["admission"] == REFERENCE_PC_REJECTED
    assert selected["admitted"] is False
    assert selected["candidate_facts"][0]["bounded_inexact_passed"] is False


def test_strict_gate_records_but_does_not_gate_tiny_scale_sector_metric():
    sector_one_ratio = 589.5067625934344
    candidate = _candidate(
        _metrics(
            full=1e-11,
            augmented_full=1e-11,
            local0=1e-11,
            local1=sector_one_ratio,
            combined=1e-11,
            alpha=1e-12,
            q=1e-11,
        ),
        state="initial",
    )

    selected = select_reference_pc_candidate([candidate])

    assert "local_sector_0" not in STRICT_REFERENCE_LIMITS
    assert "local_sector_1" not in STRICT_REFERENCE_LIMITS
    assert BOUNDED_INEXACT_LIMITS["local_sector_0"] == 1e-8
    assert BOUNDED_INEXACT_LIMITS["local_sector_1"] == 1e-8
    assert candidate["metrics"]["local_sector_1"] == sector_one_ratio
    assert selected["admission"] == STRICT_REFERENCE_PASS
    assert selected["selected_candidate_index"] == 0


def test_old_strict_failure_and_over_limit_sector_reject_bounded_admission():
    candidate = _candidate(
        _metrics(full=2e-10, local1=1.0001e-8),
        state="initial",
    )

    selected = select_reference_pc_candidate([candidate])

    assert selected["candidate_facts"][0]["strict_passed"] is False
    assert selected["candidate_facts"][0]["bounded_inexact_passed"] is False
    assert selected["admission"] == REFERENCE_PC_REJECTED


def test_regular_inverse_packets_keep_legacy_initial_name_and_separate_candidates(tmp_path):
    case = "physical_regular_incident_rhs"
    initial_name = _regular_inverse_sample_label(case, "initial")
    corrected_name = _regular_inverse_sample_label(case, "corrected_v13")

    assert initial_name == f"v10_regular_inverse_{case}"
    assert corrected_name == f"v13_regular_inverse_{case}_corrected_v13"
    assert corrected_name != initial_name

    save_packet(tmp_path, initial_name, {"witness": np.array([1.0 + 2.0j])})
    save_packet(tmp_path, corrected_name, {"witness": np.array([3.0 + 4.0j])})

    with np.load(tmp_path / f"{initial_name}.npz") as initial_packet:
        np.testing.assert_array_equal(initial_packet["array_0"], [1.0 + 2.0j])
    with np.load(tmp_path / f"{corrected_name}.npz") as corrected_packet:
        np.testing.assert_array_equal(corrected_packet["array_0"], [3.0 + 4.0j])
    assert (tmp_path / f"{initial_name}.json").is_file()
    assert (tmp_path / f"{corrected_name}.json").is_file()


def test_packet_npz_replacement_keeps_previous_packet_on_write_failure(tmp_path, monkeypatch):
    packet_name = "atomic_witness"
    npz_path = tmp_path / f"{packet_name}.npz"
    json_path = tmp_path / f"{packet_name}.json"
    save_packet(tmp_path, packet_name, {"witness": np.array([1.0 + 2.0j])})
    old_npz = npz_path.read_bytes()
    old_json = json_path.read_bytes()

    def fail_after_partial_write(stream, **_arrays):
        stream.write(b"partial replacement")
        raise OSError("simulated interrupted packet write")

    monkeypatch.setattr(np, "savez", fail_after_partial_write)
    with pytest.raises(OSError, match="simulated interrupted"):
        save_packet(tmp_path, packet_name, {"witness": np.array([9.0 + 8.0j])})

    assert npz_path.read_bytes() == old_npz
    assert json_path.read_bytes() == old_json
    with np.load(npz_path) as saved_packet:
        np.testing.assert_array_equal(saved_packet["array_0"], [1.0 + 2.0j])


def test_strategy_preserves_strict_default_and_only_v13_uses_bounded_q_limit():
    assert q_solve_limit("STRICT_ONLY") == 1e-10
    assert q_solve_limit("STRICT_THEN_BOUNDED_INEXACT_V13") == 1e-8
    assert STRICT_REFERENCE_PASS == "STRICT_REFERENCE_PASS"


def test_parent_final_gate_recomputes_v13_admission_and_bounded_pc_limits():
    metrics = {
        "complete_augmented_fe_equation": 5e-9,
        "alpha_closure": 8e-10,
        "q_solve": 5e-9,
    }
    candidate = {
        "metrics": dict(metrics),
        "frozen_scale_metrics": dict(metrics),
        "structural_gates": {"all_four_q_phases_covered": True},
    }
    selection = select_reference_pc_candidate(
        [candidate],
        strict_limits={
            "complete_augmented_fe_equation": 1e-10,
            "alpha_closure": 1e-11,
            "q_solve": 1e-10,
        },
        bounded_inexact_limits={
            "complete_augmented_fe_equation": 1e-8,
            "alpha_closure": 1e-9,
            "q_solve": 1e-8,
        },
    )
    last_facts = {
        "reference_pc_strategy": "STRICT_THEN_BOUNDED_INEXACT_V13",
        "port_identity_relative": metrics["alpha_closure"],
        "maximum_q_true_residual_relative": metrics["q_solve"],
        "all_four_q_used": True,
        "q_true_residuals_selected": _q_rows(),
        "candidate_metrics": [candidate],
        "candidate_selection": selection,
    }

    result = recheck_reference_pc_final_admission(
        last_facts, "STRICT_THEN_BOUNDED_INEXACT_V13"
    )

    assert result["passed"] is True
    assert result["admission"] == BOUNDED_INEXACT_REFERENCE_PC
    assert result["selection_recomputed_from_candidate_metrics"] is True
    assert result["port_identity_limit"] == 1e-9
    assert result["q_true_residual_limit"] == 1e-8


def test_parent_final_gate_rejects_mismatched_recorded_v13_selection():
    metrics = {
        "complete_augmented_fe_equation": 5e-9,
        "alpha_closure": 8e-10,
        "q_solve": 5e-9,
    }
    candidate = {
        "metrics": dict(metrics),
        "frozen_scale_metrics": dict(metrics),
        "structural_gates": {"all_four_q_phases_covered": True},
    }
    selection = select_reference_pc_candidate(
        [candidate],
        strict_limits={
            "complete_augmented_fe_equation": 1e-10,
            "alpha_closure": 1e-11,
            "q_solve": 1e-10,
        },
        bounded_inexact_limits={
            "complete_augmented_fe_equation": 1e-8,
            "alpha_closure": 1e-9,
            "q_solve": 1e-8,
        },
    )
    selection["admission"] = STRICT_REFERENCE_PASS
    result = recheck_reference_pc_final_admission(
        {
            "reference_pc_strategy": "STRICT_THEN_BOUNDED_INEXACT_V13",
            "port_identity_relative": metrics["alpha_closure"],
            "maximum_q_true_residual_relative": metrics["q_solve"],
            "all_four_q_used": True,
            "q_true_residuals_selected": _q_rows(),
            "candidate_metrics": [candidate],
            "candidate_selection": selection,
        },
        "STRICT_THEN_BOUNDED_INEXACT_V13",
    )

    assert result["passed"] is False
    assert result["failure_reason"] == "recorded_candidate_selection_mismatch"


def test_parent_final_gate_keeps_legacy_pc_thresholds_at_one_e_minus_ten():
    result = recheck_reference_pc_final_admission(
        {
            "reference_pc_strategy": "STRICT_ONLY",
            "port_identity_relative": 8e-11,
            "maximum_q_true_residual_relative": 9e-11,
        },
        "STRICT_ONLY",
    )
    assert result["passed"] is True
    assert result["port_identity_limit"] == 1e-10
    assert result["q_true_residual_limit"] == 1e-10
