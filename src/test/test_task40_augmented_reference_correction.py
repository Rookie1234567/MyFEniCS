from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.task40_v10_worker import _regular_inverse_sample_label
from src.solvers.augmented_reference_correction import (
    BOUNDED_INEXACT_LIMITS,
    BOUNDED_INEXACT_REFERENCE_PC,
    FACTOR_CALL_COUNTER_SOURCE,
    NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
    REFERENCE_PC_REJECTED,
    STRICT_REFERENCE_LIMITS,
    STRICT_REFERENCE_PASS,
    V15_REFERENCE_PC_PASS,
    apply_one_augmented_residual_correction,
    augmented_state_sha256,
    augmented_port_state_offset,
    augmented_rhs_sha256,
    evaluate_complete_augmented_residual,
    evaluate_v15_non_cancelling_budget,
    q_solve_limit,
    recompute_v15_candidate_facts,
    recheck_reference_pc_final_admission,
    select_reference_pc_candidate,
    select_v15_reference_pc_candidate,
    stable_euclidean_norm,
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


def _v15_candidate(
    metrics, *, frozen=None, state="candidate", structural=None,
    profile_identity="task40extra_v15_p6_y_orbit_b0_reference_v1",
):
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    frozen_metrics = dict(metrics if frozen is None else frozen)
    alpha = float(metrics["alpha_closure"])
    frozen_alpha = float(frozen_metrics["alpha_closure"])
    sectors = []
    next_mode = 0
    for twist, mode_count in enumerate(profile.sector_port_counts):
        sectors.append({
            "twist_index": twist,
            "mode_indices": list(range(next_mode, next_mode + mode_count)),
        })
        next_mode += mode_count
    raw = {
        "profile_identity": profile_identity,
        "effective_rhs_scale": 1.0,
        "eliminated_fe_residual_norm": float(metrics["eliminated_fe"]),
        "complete_augmented_fe_residual_norm": float(metrics["complete_augmented_fe"]),
        "budget_term_norms": {
            "d_b": float(metrics["noncancelling_budget"]),
            "lifted_sector_errors": [0.0] * profile.replication_count,
            "d_A": 0.0,
            "B_delta_alpha": 0.0,
        },
        "alpha_closure_residual_norm": alpha,
        "alpha_closure_original_scale": 1.0,
        "alpha_closure_frozen_scale": (
            alpha / frozen_alpha if frozen_alpha > 0.0 else 1.0
        ),
        "q_true_residuals": [
            {
                "q": q,
                "rhs_norm": 1.0,
                "true_residual_norm": float(metrics["q_solve"]),
                "true_residual_relative": float(metrics["q_solve"]),
            }
            for q in range(profile.q_count)
        ],
        "retained_mode_count": profile.mode_count,
        "native_sector_facts": sectors,
        "decomposition_closure_norm": 1.0e-12,
        "decomposition_closure_scale": 1.0,
        "state_sha256": sha256(state.encode("utf-8")).hexdigest(),
    }
    return {
        "metrics": dict(metrics),
        "frozen_scale_metrics": frozen_metrics,
        "structural_gates": {"mapping": True, "recovery": True} if structural is None else structural,
        "state_label": state,
        "state_sha256": raw["state_sha256"],
        "raw_facts": raw,
    }

def _v15_candidate_from_budget(budget, *, q_relative=0.0, state="native-budget"):
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    profile_identity = "task40extra_v15_p6_y_orbit_b0_reference_v1"
    profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    alpha_norm = 0.0
    alpha_scale = 1.0
    q_rows = [
        {
            "q": q,
            "rhs_norm": 1.0,
            "true_residual_norm": float(q_relative),
            "true_residual_relative": float(q_relative),
        }
        for q in range(profile.q_count)
    ]
    metrics = {
        "eliminated_fe": float(budget["eliminated_fe_relative"]),
        "complete_augmented_fe": float(budget["complete_augmented_fe_relative"]),
        "noncancelling_budget": float(budget["noncancelling_budget_relative"]),
        "alpha_closure": 0.0,
        "q_solve": float(q_relative),
    }
    state_hash = augmented_state_sha256(
        np.asarray([0.0j, 1.0j], dtype=np.complex128),
        np.asarray([0.5 + 0.25j, -0.5j], dtype=np.complex128),
    )
    sectors = []
    next_mode = 0
    for twist, mode_count in enumerate(profile.sector_port_counts):
        sectors.append({
            "twist_index": twist,
            "mode_indices": list(range(next_mode, next_mode + mode_count)),
        })
        next_mode += mode_count
    raw = {
        "profile_identity": profile_identity,
        "effective_rhs_scale": float(budget["effective_rhs_scale"]),
        "eliminated_fe_residual_norm": float(budget["eliminated_fe_residual_norm"]),
        "complete_augmented_fe_residual_norm": float(
            budget["complete_augmented_fe_residual_norm"]
        ),
        "budget_term_norms": dict(budget["budget_terms"]),
        "alpha_closure_residual_norm": alpha_norm,
        "alpha_closure_original_scale": alpha_scale,
        "alpha_closure_frozen_scale": alpha_scale,
        "q_true_residuals": q_rows,
        "retained_mode_count": profile.mode_count,
        "native_sector_facts": sectors,
        "decomposition_closure_norm": float(budget["decomposition_closure_norm"]),
        "decomposition_closure_scale": float(budget["decomposition_closure_scale"]),
        "state_sha256": state_hash,
    }
    return {
        "metrics": metrics,
        "frozen_scale_metrics": dict(metrics),
        "structural_gates": {
            "startup_regular_inverse_gates_passed": True,
            "all_q_phases_covered": True,
            "all_retained_modes_mapped_once": True,
            "native_decomposition_closure": True,
            "native_augmented_actions_finite": True,
        },
        "state_label": state,
        "state_sha256": state_hash,
        "raw_facts": raw,
    }


def _nonunitary_two_cell_transports():
    from src.solvers.task40_v10_p6_yorbit import YOrbitEntities, TwoCellNativeTransport

    cfg = SimpleNamespace(
        ky=0.25 + 0j,
        period_y=4.0,
        floquet_phase_y=np.exp(1j),
    )
    base = (1, ((0, 0, 0), (1, 0, 0)))
    matrices = (
        np.asarray([[1.2 + 0.2j, 0.3 - 0.1j], [0.1 + 0.05j, 0.8 - 0.2j]]),
        np.asarray([[0.9 - 0.1j, 0.2 + 0.3j], [-0.15 + 0.1j, 1.1 + 0.2j]]),
        np.asarray([[1.3 + 0.1j, -0.1 + 0.2j], [0.25 + 0.1j, 0.7 - 0.15j]]),
        np.asarray([[0.85 + 0.2j, 0.15 - 0.1j], [0.1 + 0.2j, 1.25 - 0.1j]]),
    )

    def entities(ny, records):
        return YOrbitEntities(
            independent=np.arange(2 * ny, dtype=np.int64),
            full_rows=2 * ny + 3,
            ny=ny,
            width=2,
            bases=(base,),
            records={
                (orbit, base): (
                    np.asarray([2 * orbit, 2 * orbit + 1], dtype=np.int64),
                    matrix.astype(np.complex128),
                )
                for orbit, matrix in enumerate(records)
            },
            slots={base: (0, 2)},
            dimension_counts={1: 2 * ny, 3: ny},
            y_widths=np.ones(ny),
        )

    full = entities(4, matrices)
    local = entities(2, matrices[:2])
    return tuple(
        TwoCellNativeTransport(
            full,
            local,
            twist_index=twist,
            eta=np.exp(1j * (1.0 + 2.0 * np.pi * twist) / 4),
            cfg=cfg,
        )
        for twist in (0, 1)
    )


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


def test_profile_sized_correction_accepts_eight_calls_only_with_all_eight_q_rows():
    q_rows = [
        {"q": q, "rhs_norm": 1.0, "true_residual_norm": 1e-12,
         "true_residual_relative": 1e-12}
        for q in range(8)
    ]

    def raw_eight_q(_fe, _port):
        return np.zeros(1, dtype=np.complex128), np.zeros(1, dtype=np.complex128), {
            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
            "factor_calls_before": 3,
            "factor_calls_after": 11,
            "q_true_residuals": q_rows,
        }

    result = apply_one_augmented_residual_correction(
        np.zeros(1, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        np.ones(1, dtype=np.complex128),
        np.ones(1, dtype=np.complex128),
        raw_inverse=raw_eight_q,
        require_verified_solve_counter=True,
        expected_q_count=8,
    )

    assert result.audit["extra_mat_solve_count"] == 8
    assert result.audit["expected_q_count"] == 8
    assert result.audit["q_phase_coverage"] == list(range(8))
    assert result.audit["all_q_phases_covered"] is True
    assert result.audit["all_four_q_phases_covered"] is False

    duplicate_q = [*q_rows[:-1], {**q_rows[-1], "q": 6}]
    with pytest.raises(ValueError, match="8-call factors.calls delta and coverage"):
        apply_one_augmented_residual_correction(
            np.zeros(1, dtype=np.complex128),
            np.zeros(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            raw_inverse=lambda *_: (
                np.zeros(1, dtype=np.complex128),
                np.zeros(1, dtype=np.complex128),
                {
                    "counter_source": FACTOR_CALL_COUNTER_SOURCE,
                    "factor_calls_before": 3,
                    "factor_calls_after": 11,
                    "q_true_residuals": duplicate_q,
                },
            ),
            require_verified_solve_counter=True,
            expected_q_count=8,
        )


def test_production_counter_must_be_bounded_and_cover_all_q_phases():
    def raw_with_bad_delta(_fe, _port):
        return np.ones(1, dtype=np.complex128), np.ones(1, dtype=np.complex128), {
            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
            "factor_calls_before": 12,
            "factor_calls_after": 17,
            "q_true_residuals": _q_rows(),
        }

    with pytest.raises(ValueError, match="4-extra-MatSolve"):
        apply_one_augmented_residual_correction(
            np.zeros(1, dtype=np.complex128),
            np.zeros(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            np.ones(1, dtype=np.complex128),
            raw_inverse=raw_with_bad_delta,
            require_verified_solve_counter=True,
        )


def test_production_counter_rejects_missing_before_after_counter():
    with pytest.raises(ValueError, match="verified 4-call"):
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
    assert q_solve_limit(NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15) == 1e-8
    assert STRICT_REFERENCE_PASS == "STRICT_REFERENCE_PASS"


def test_v15_non_cancelling_budget_catches_sector_errors_that_cancel_in_global_residual():
    identity = lambda values: np.asarray(values, dtype=np.complex128).copy()
    result = evaluate_v15_non_cancelling_budget(
        effective_rhs=np.array([1.0, 0.0], dtype=np.complex128),
        global_eliminated_action=np.array([1.0, 0.0], dtype=np.complex128),
        original_fe_rhs=np.array([1.0, 0.0], dtype=np.complex128),
        port_elimination_action=np.zeros(2, dtype=np.complex128),
        complete_augmented_fe_residual=np.zeros(2, dtype=np.complex128),
        modal_alpha_defect_action=np.zeros(2, dtype=np.complex128),
        sectors=(
            {
                "rhs": np.array([0.6, 0.0], dtype=np.complex128),
                "action": np.array([0.5, 0.0], dtype=np.complex128),
                "lift_dual": identity,
            },
            {
                "rhs": np.array([0.4, 0.0], dtype=np.complex128),
                "action": np.array([0.5, 0.0], dtype=np.complex128),
                "lift_dual": identity,
            },
        ),
    )

    assert result["eliminated_fe_relative"] == 0.0
    assert result["noncancelling_budget_relative"] == pytest.approx(0.2)
    assert result["decomposition_closure_relative"] == 0.0


def test_v15_budget_preserves_tiny_scale_and_rejects_nonzero_fe_when_scale_is_zero():
    identity = lambda values: np.asarray(values, dtype=np.complex128).copy()
    tiny = evaluate_v15_non_cancelling_budget(
        effective_rhs=np.array([1.0e-250], dtype=np.complex128),
        global_eliminated_action=np.array([1.0e-250], dtype=np.complex128),
        original_fe_rhs=np.array([1.0e-250], dtype=np.complex128),
        port_elimination_action=np.array([0.0], dtype=np.complex128),
        complete_augmented_fe_residual=np.array([0.0], dtype=np.complex128),
        modal_alpha_defect_action=np.array([0.0], dtype=np.complex128),
        sectors=(
            {
                "rhs": np.array([1.0e-250], dtype=np.complex128),
                "action": np.array([1.0e-250], dtype=np.complex128),
                "lift_dual": identity,
            },
        ),
    )
    assert tiny["effective_rhs_scale"] > 0.0
    assert tiny["effective_rhs_scale"] == pytest.approx(1.0e-250, rel=1e-15, abs=0.0)
    assert tiny["noncancelling_budget_relative"] == 0.0

    zero_scale = evaluate_v15_non_cancelling_budget(
        effective_rhs=np.array([1.0], dtype=np.complex128),
        global_eliminated_action=np.array([0.0], dtype=np.complex128),
        original_fe_rhs=np.zeros(1, dtype=np.complex128),
        port_elimination_action=np.zeros(1, dtype=np.complex128),
        complete_augmented_fe_residual=np.zeros(1, dtype=np.complex128),
        modal_alpha_defect_action=np.zeros(1, dtype=np.complex128),
        sectors=(
            {
                "rhs": np.zeros(1, dtype=np.complex128),
                "action": np.zeros(1, dtype=np.complex128),
                "lift_dual": identity,
            },
        ),
    )
    assert zero_scale["effective_rhs_scale"] == 0.0
    assert np.isinf(zero_scale["noncancelling_budget_relative"])


def test_v15_selection_keeps_whole_state_and_enforces_q_limit():
    good = _v15_candidate(
        {
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 5e-10,
            "q_solve": 9e-9,
        },
        frozen={
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 8e-10,
        },
        state="initial",
    )
    bad_q = {
        **good,
        "metrics": {**good["metrics"], "q_solve": 1.01e-8},
        "raw_facts": {
            **good["raw_facts"],
            "q_true_residuals": [
                {
                    "q": q,
                    "rhs_norm": 1.0,
                    "true_residual_norm": 1.01e-8,
                    "true_residual_relative": 1.01e-8,
                }
                for q in range(4)
            ],
            "state_sha256": sha256(b"bad-q").hexdigest(),
        },
        "state_sha256": sha256(b"bad-q").hexdigest(),
        "state_label": "bad-q",
    }
    selection = select_v15_reference_pc_candidate([bad_q])
    assert selection["admitted"] is False
    assert selection["admission"] != "V15_REFERENCE_PC_PASS"

    corrected = {
        **good,
        "metrics": {**good["metrics"], "noncancelling_budget": 8e-9},
        "frozen_scale_metrics": {
            **good["frozen_scale_metrics"], "noncancelling_budget": 8e-9
        },
        "raw_facts": {
            **good["raw_facts"],
            "budget_term_norms": {
                **good["raw_facts"]["budget_term_norms"],
                "d_b": 8e-9,
            },
            "state_sha256": sha256(b"corrected").hexdigest(),
        },
        "state_sha256": sha256(b"corrected").hexdigest(),
        "state_label": "corrected",
    }
    initial_fail = {
        **good,
        "metrics": {**good["metrics"], "noncancelling_budget": 2e-8},
        "frozen_scale_metrics": {
            **good["frozen_scale_metrics"], "noncancelling_budget": 2e-8
        },
        "raw_facts": {
            **good["raw_facts"],
            "budget_term_norms": {
                **good["raw_facts"]["budget_term_norms"],
                "d_b": 2e-8,
            },
        },
    }
    selection = select_v15_reference_pc_candidate([initial_fail, corrected])
    assert selection["admitted"] is True
    assert selection["selected_candidate_index"] == 1


def test_v15_parent_recheck_recomputes_all_metrics_and_q_rows():
    candidate = _v15_candidate(
        {
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 5e-10,
            "q_solve": 9e-9,
        },
        frozen={
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 8e-10,
        },
        state="initial",
    )
    facts = {
        "reference_pc_strategy": NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        "maximum_q_true_residual_relative": 9e-9,
        "port_identity_relative": 5e-10,
        "all_q_used": True,
        "all_four_q_used": True,
        "q_true_residuals_selected": [
            {
                "q": q,
                "rhs_norm": 1.0,
                "true_residual_norm": 9e-9,
                "true_residual_relative": 9e-9,
            }
            for q in range(4)
        ],
        "candidate_metrics": [candidate],
        "candidate_selection": select_v15_reference_pc_candidate([candidate]),
        "selected_decomposition_closure_relative": 1e-12,
        "selected_v15_metrics": dict(candidate["metrics"]),
        "selected_v15_raw_facts": dict(candidate["raw_facts"]),
        "selected_state_sha256": candidate["raw_facts"]["state_sha256"],
    }
    accepted = recheck_reference_pc_final_admission(
        facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert accepted["passed"] is True
    assert accepted["selection_recomputed_from_candidate_metrics"] is True

    facts["candidate_metrics"] = [{
        **candidate,
        "metrics": {**candidate["metrics"], "eliminated_fe": 1.1e-8},
        "raw_facts": {
            **candidate["raw_facts"],
            "eliminated_fe_residual_norm": 1.1e-8,
        },
    }]
    rejected = recheck_reference_pc_final_admission(
        facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert rejected["passed"] is False


def test_v15_budget_measures_errors_after_actual_nonunitary_complex_dual_lifts():
    transports = _nonunitary_two_cell_transports()
    rng = np.random.default_rng(1507)
    sector_rhs = [
        rng.normal(size=4).astype(np.complex128)
        + 1j * rng.normal(size=4).astype(np.complex128)
        for _ in transports
    ]
    local_errors = [
        np.asarray([0.17 + 0.09j, -0.04 + 0.12j, 0.08 - 0.03j, 0.02 + 0.06j]),
        np.asarray([-0.11 + 0.02j, 0.07 - 0.13j, 0.03 + 0.05j, -0.06 + 0.01j]),
    ]
    sector_actions = [rhs - error for rhs, error in zip(sector_rhs, local_errors)]
    lifted_rhs = [
        transport.lift_dual(rhs)
        for transport, rhs in zip(transports, sector_rhs)
    ]
    lifted_actions = [
        transport.lift_dual(action)
        for transport, action in zip(transports, sector_actions)
    ]
    effective_rhs = lifted_rhs[0] + lifted_rhs[1]
    global_action = lifted_actions[0] + lifted_actions[1]
    budget = evaluate_v15_non_cancelling_budget(
        effective_rhs=effective_rhs,
        global_eliminated_action=global_action,
        original_fe_rhs=effective_rhs,
        port_elimination_action=np.zeros_like(effective_rhs),
        complete_augmented_fe_residual=effective_rhs - global_action,
        modal_alpha_defect_action=np.zeros_like(effective_rhs),
        sectors=[
            {
                "rhs": rhs,
                "action": action,
                "lift_dual": transport.lift_dual,
            }
            for transport, rhs, action in zip(transports, sector_rhs, sector_actions)
        ],
        retain_lifted_errors=True,
    )

    for index, (transport, error) in enumerate(zip(transports, local_errors)):
        expected = transport.lift_dual(error)
        np.testing.assert_allclose(budget["lifted_sector_errors"][index], expected)
        assert budget["budget_terms"]["lifted_sector_errors"][index] == pytest.approx(
            stable_euclidean_norm(expected)
        )
        assert not np.isclose(
            stable_euclidean_norm(expected), stable_euclidean_norm(error)
        )
    assert budget["decomposition_closure_relative"] < 1e-14


def test_v15_wrong_adjoint_lift_fails_independent_native_budget_admission():
    transports = _nonunitary_two_cell_transports()
    sector_rhs = [
        np.asarray([0.4 + 0.2j, -0.3 + 0.1j, 0.2 - 0.5j, 0.1 + 0.3j]),
        np.asarray([-0.2 + 0.1j, 0.5 - 0.4j, 0.3 + 0.2j, -0.1 + 0.6j]),
    ]
    correct_lifts = [
        transport.lift_dual(rhs)
        for transport, rhs in zip(transports, sector_rhs)
    ]
    effective_rhs = correct_lifts[0] + correct_lifts[1]
    correct_budget = evaluate_v15_non_cancelling_budget(
        effective_rhs=effective_rhs,
        global_eliminated_action=effective_rhs,
        original_fe_rhs=effective_rhs,
        port_elimination_action=np.zeros_like(effective_rhs),
        complete_augmented_fe_residual=np.zeros_like(effective_rhs),
        modal_alpha_defect_action=np.zeros_like(effective_rhs),
        sectors=[
            {"rhs": rhs, "action": rhs, "lift_dual": transport.lift_dual}
            for transport, rhs in zip(transports, sector_rhs)
        ],
    )
    wrong_budget = evaluate_v15_non_cancelling_budget(
        effective_rhs=effective_rhs,
        global_eliminated_action=effective_rhs,
        original_fe_rhs=effective_rhs,
        port_elimination_action=np.zeros_like(effective_rhs),
        complete_augmented_fe_residual=np.zeros_like(effective_rhs),
        modal_alpha_defect_action=np.zeros_like(effective_rhs),
        sectors=[
            # A primal lift has the wrong orientation for residuals.  This is
            # deliberately supplied in place of the actual dual adjoint.
            {"rhs": rhs, "action": rhs, "lift_dual": transport.lift_primal}
            for transport, rhs in zip(transports, sector_rhs)
        ],
    )

    assert correct_budget["noncancelling_budget_relative"] == 0.0
    assert wrong_budget["noncancelling_budget_relative"] > 1e-8
    selected = select_v15_reference_pc_candidate(
        [_v15_candidate_from_budget(wrong_budget, q_relative=9e-9)]
    )
    assert selected["admitted"] is False
    assert selected["candidate_facts"][0]["q_phase_coverage"] is True
    assert (
        selected["candidate_facts"][0]["original_scale_max_normalized_exceedance"]
        > 1.0
    )


def test_v15_self_consistent_q_rows_do_not_mask_cancelling_local_error_budget():
    identity_lift = lambda values: np.asarray(values, dtype=np.complex128).copy()
    budget = evaluate_v15_non_cancelling_budget(
        effective_rhs=np.asarray([1.0 + 0.0j, 0.0j]),
        global_eliminated_action=np.asarray([1.0 + 0.0j, 0.0j]),
        original_fe_rhs=np.asarray([1.0 + 0.0j, 0.0j]),
        port_elimination_action=np.zeros(2, dtype=np.complex128),
        complete_augmented_fe_residual=np.zeros(2, dtype=np.complex128),
        modal_alpha_defect_action=np.zeros(2, dtype=np.complex128),
        sectors=(
            {
                "rhs": np.asarray([0.6 + 0.0j, 0.0j]),
                "action": np.asarray([0.5 + 0.0j, 0.0j]),
                "lift_dual": identity_lift,
            },
            {
                "rhs": np.asarray([0.4 + 0.0j, 0.0j]),
                "action": np.asarray([0.5 + 0.0j, 0.0j]),
                "lift_dual": identity_lift,
            },
        ),
    )
    candidate = _v15_candidate_from_budget(budget, q_relative=9e-9)
    selected = select_v15_reference_pc_candidate([candidate])

    assert budget["eliminated_fe_relative"] == 0.0
    assert budget["budget_terms"]["lifted_sector_errors"] == pytest.approx([0.1, 0.1])
    assert budget["noncancelling_budget_relative"] == pytest.approx(0.2)
    assert candidate["raw_facts"]["q_true_residuals"]
    assert all(
        row["true_residual_relative"]
        == row["true_residual_norm"] / row["rhs_norm"]
        for row in candidate["raw_facts"]["q_true_residuals"]
    )
    assert selected["admitted"] is False
    assert selected["candidate_facts"][0]["q_phase_coverage"] is True
    assert selected["candidate_facts"][0]["raw_facts_consistent"] is True


def test_v15_candidate_rejects_missing_q_missing_mode_and_nonfinite_budget():
    identity_lift = lambda values: np.asarray(values, dtype=np.complex128).copy()
    budget = evaluate_v15_non_cancelling_budget(
        effective_rhs=np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        global_eliminated_action=np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        original_fe_rhs=np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        port_elimination_action=np.zeros(2, dtype=np.complex128),
        complete_augmented_fe_residual=np.zeros(2, dtype=np.complex128),
        modal_alpha_defect_action=np.zeros(2, dtype=np.complex128),
        sectors=(
            {
                "rhs": np.asarray([1.0 + 0.0j]),
                "action": np.asarray([1.0 + 0.0j]),
                "lift_dual": lambda values: np.asarray([values[0], 0.0j]),
            },
            {
                "rhs": np.asarray([2.0 + 0.0j]),
                "action": np.asarray([2.0 + 0.0j]),
                "lift_dual": lambda values: np.asarray([0.0j, values[0]]),
            },
        ),
    )
    del identity_lift  # Keep the intentionally disjoint two-sector maps explicit above.
    base = _v15_candidate_from_budget(budget)

    missing_q = {
        **base,
        "raw_facts": {
            **base["raw_facts"],
            "q_true_residuals": base["raw_facts"]["q_true_residuals"][:-1],
        },
    }
    missing_mode_facts = [dict(row) for row in base["raw_facts"]["native_sector_facts"]]
    missing_mode_facts[1]["mode_indices"] = []
    missing_mode = {
        **base,
        "raw_facts": {**base["raw_facts"], "native_sector_facts": missing_mode_facts},
    }
    nonfinite_terms = dict(base["raw_facts"]["budget_term_norms"])
    nonfinite_terms["d_b"] = float("nan")
    nonfinite = {
        **base,
        "raw_facts": {
            **base["raw_facts"],
            "budget_term_norms": nonfinite_terms,
        },
    }

    missing_q_result = select_v15_reference_pc_candidate([missing_q])
    missing_mode_result = select_v15_reference_pc_candidate([missing_mode])
    nonfinite_result = select_v15_reference_pc_candidate([nonfinite])
    assert missing_q_result["admitted"] is False
    assert missing_q_result["candidate_facts"][0]["q_phase_coverage"] is False
    assert missing_mode_result["admitted"] is False
    assert missing_mode_result["candidate_facts"][0]["structural_passed"] is False
    assert nonfinite_result["admitted"] is False
    assert nonfinite_result["candidate_facts"][0]["raw_facts_consistent"] is False


def test_v18_v15_candidate_recomputes_registered_eight_q_four_twist_inventory():
    candidate = _v15_candidate(
        {
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 5e-10,
            "q_solve": 9e-9,
        },
        profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
    )
    recomputed = recompute_v15_candidate_facts(candidate)

    assert recomputed["expected_q_count"] == 8
    assert recomputed["expected_twist_count"] == 4
    assert recomputed["q_phase_coverage"] is True
    assert recomputed["sector_mode_mapping_valid"] is True
    assert recomputed["raw_facts_consistent"] is True

    old_style_raw = dict(candidate["raw_facts"])
    old_style_raw.pop("profile_identity")
    with pytest.raises(ValueError, match="explicitly record"):
        recompute_v15_candidate_facts(
            {**candidate, "raw_facts": old_style_raw},
            profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
        )
    with pytest.raises(ValueError, match="differs from its registered outer profile"):
        recompute_v15_candidate_facts(
            candidate, profile_identity="task40extra_v15_p6_y_orbit_b0_reference_v1"
        )

    bad_raw = dict(candidate["raw_facts"])
    bad_raw["q_true_residuals"] = [
        *bad_raw["q_true_residuals"][:-1],
        {**bad_raw["q_true_residuals"][-1], "q": 6},
    ]
    duplicate_q = {**candidate, "raw_facts": bad_raw}
    duplicate_result = select_v15_reference_pc_candidate([duplicate_q])
    assert duplicate_result["admitted"] is False
    assert duplicate_result["candidate_facts"][0]["q_phase_coverage"] is False

    bad_raw = dict(candidate["raw_facts"])
    bad_raw["native_sector_facts"] = bad_raw["native_sector_facts"][:-1]
    missing_twist = {**candidate, "raw_facts": bad_raw}
    assert select_v15_reference_pc_candidate([missing_twist])["admitted"] is False

    bad_raw = dict(candidate["raw_facts"])
    bad_raw["native_sector_facts"] = [dict(row) for row in bad_raw["native_sector_facts"]]
    bad_raw["native_sector_facts"][2]["mode_indices"] = bad_raw["native_sector_facts"][2]["mode_indices"][:-1]
    missing_mode = {**candidate, "raw_facts": bad_raw}
    assert select_v15_reference_pc_candidate([missing_mode])["admitted"] is False

    bad_raw = dict(candidate["raw_facts"])
    bad_budget = dict(bad_raw["budget_term_norms"])
    bad_budget["lifted_sector_errors"] = bad_budget["lifted_sector_errors"][:-1]
    bad_raw["budget_term_norms"] = bad_budget
    missing_lift = {**candidate, "raw_facts": bad_raw}
    with pytest.raises(ValueError, match="every registered twist sector"):
        select_v15_reference_pc_candidate([missing_lift])


def test_v18_parent_final_gate_uses_all_eight_q_rows_not_four_q_alias():
    candidate = _v15_candidate(
        {
            "eliminated_fe": 2e-9,
            "complete_augmented_fe": 3e-9,
            "noncancelling_budget": 5e-9,
            "alpha_closure": 5e-10,
            "q_solve": 9e-9,
        },
        profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
    )
    q_rows = candidate["raw_facts"]["q_true_residuals"]
    facts = {
        "reference_pc_strategy": NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        "maximum_q_true_residual_relative": 9e-9,
        "port_identity_relative": 5e-10,
        "all_q_used": True,
        "all_four_q_used": False,
        "q_true_residuals_selected": q_rows,
        "candidate_metrics": [candidate],
        "candidate_selection": select_v15_reference_pc_candidate([candidate]),
        "selected_decomposition_closure_relative": 1e-12,
        "selected_v15_metrics": dict(candidate["metrics"]),
        "selected_v15_raw_facts": dict(candidate["raw_facts"]),
        "selected_state_sha256": candidate["raw_facts"]["state_sha256"],
    }

    result = recheck_reference_pc_final_admission(
        facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert result["passed"] is True
    assert result["all_q_phase_rows_covered"] is True
    assert result["all_four_q_phase_rows_covered"] is False


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
