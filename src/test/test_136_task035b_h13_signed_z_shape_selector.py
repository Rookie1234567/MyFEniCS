"""Pure tests for the Task035b h13 signed z-shape selector."""

from __future__ import annotations

import hashlib

import numpy as np

from src.adaptivity.h13_signed_z_shape_selector import (
    H13_REAL_GOAL_LABELS,
    H13ProtectedRealGoal,
    H13RealGoal,
    select_h13_signed_z_shape_candidate,
)


def _source_hashes() -> dict[str, str]:
    return {
        key: hashlib.sha256(f"fixture:{key}".encode()).hexdigest()
        for key in (
            "h13_base",
            "plus_epsilon_bundle",
            "minus_epsilon_bundle",
            "plus_2epsilon_bundle",
            "minus_2epsilon_bundle",
        )
    }


def _goals(
    normalized_errors: tuple[float, ...] = (
        2.0,
        1.8,
        0.8,
        0.8,
        0.9,
        0.6,
    ),
) -> tuple[H13RealGoal, ...]:
    assert abs(normalized_errors[0]) > 1.0
    assert abs(normalized_errors[1]) > 1.0
    assert np.hypot(*normalized_errors[2:4]) > 1.0
    assert np.hypot(*normalized_errors[4:6]) > 1.0
    return tuple(
        H13RealGoal(
            label=label,
            base_observable=error,
            reference=0.0,
            tolerance=1.0,
        )
        for label, error in zip(
            H13_REAL_GOAL_LABELS,
            normalized_errors,
            strict=True,
        )
    )


def _full_rank_positive_sensitivity() -> np.ndarray:
    matrix = np.zeros((6, 9), dtype=np.float64)
    matrix[:, 0] = (-2.0, -1.5, -0.8, -0.8, -0.9, -0.6)
    for row in range(6):
        matrix[row, row + 1] = 0.05
    return matrix


def _select(
    sensitivity: np.ndarray,
    *,
    coarse: np.ndarray | None = None,
    goals: tuple[H13RealGoal, ...] | None = None,
    protected_goals: tuple[H13ProtectedRealGoal, ...] = (),
    protected_sensitivity: np.ndarray | None = None,
):
    return select_h13_signed_z_shape_candidate(
        goals=_goals() if goals is None else goals,
        sensitivity_at_epsilon=sensitivity,
        sensitivity_at_2epsilon=(
            sensitivity.copy() if coarse is None else coarse
        ),
        epsilon_nm=0.2,
        source_hashes=_source_hashes(),
        protected_goals=protected_goals,
        protected_sensitivity_at_epsilon=protected_sensitivity,
        protected_sensitivity_at_2epsilon=(
            None
            if protected_sensitivity is None
            else protected_sensitivity.copy()
        ),
    )


def test_positive_candidate_is_deterministic_and_pde_is_not_run() -> None:
    sensitivity = _full_rank_positive_sensitivity()

    first = _select(sensitivity)
    second = _select(sensitivity)

    assert first == second
    assert first["status"] == "prediction_candidate_selected"
    assert first["classification"] == "positive_prediction_not_pde_qualified"
    assert first["enumeration"]["single_support_count_expected"] == 9
    assert first["enumeration"]["pair_support_count_expected"] == 36
    assert first["enumeration"]["support_count_evaluated"] == 45
    selected = first["selected_candidate"]
    assert selected is not None
    assert 1 <= selected["support_size"] <= 2
    assert selected["predicted_benefit_fraction"] >= 0.05
    assert selected["separate_protected_goals_preserved"] is True
    assert selected["geometry_pass"] is True
    assert max(abs(value) for value in selected["full_delta_nm"]) <= 0.6
    assert min(selected["material_slab_widths_nm"]) >= 10.8 - 1.0e-10
    assert max(selected["material_slab_widths_nm"]) <= 13.2 + 1.0e-10
    assert first["pde_gate"]["status"] == "not_run"
    assert first["pde_gate"]["significant_power_12_of_12"] == "not_run"
    assert (
        first["pde_gate"]["significant_complex_amplitude_12_of_12"]
        == "not_run"
    )
    assert (
        first["pde_gate"][
            "all_12_significant_channels_reserved_for_formal_PDE"
        ]
        is True
    )
    failed_gate = first["base"]["failed_gate_validation"]
    assert failed_gate["observed_failure_count"] == 4
    assert len(failed_gate["power_gates"]) == 2
    assert len(failed_gate["complex_vector_L2_gates"]) == 2
    assert failed_gate["componentwise_amplitude_passes_inferred"] is False
    assert (
        first["base"]["individual_complex_component_pass_signature"]
        == "not_defined"
    )
    assert (
        first["separate_protection_contract"]["protected_goal_count"] == 0
    )
    assert first["source_contract"]["manual_plane_override"] is False
    assert len(first["frozen_profile_sha256"]) == 64
    assert (
        len(first["input_hashes"]["complete_selector_input_sha256"]) == 64
    )


def test_rank_one_useful_direction_is_diagnostic_not_a_hard_failure() -> None:
    sensitivity = np.zeros((6, 9), dtype=np.float64)
    sensitivity[:, 0] = (-2.0, -1.5, -0.8, -0.8, -0.9, -0.6)

    result = _select(sensitivity)

    rank = result["preflight"]["failed_goal_sensitivity_rank_diagnostic"]
    assert rank["normalized_row_rank"] == 1
    assert rank["full_row_rank_required"] is False
    assert rank["rank_is_diagnostic"] is True
    assert rank["pass"] is True
    assert result["status"] == "prediction_candidate_selected"
    assert result["enumeration"]["support_count_evaluated"] == 45
    assert result["selected_candidate"] is not None
    assert result["pde_gate"]["status"] == "not_run"


def test_zero_failed_goal_sensitivity_is_fail_closed() -> None:
    sensitivity = _full_rank_positive_sensitivity()
    sensitivity[5, :] = 0.0

    result = _select(sensitivity)

    rank = result["preflight"]["failed_goal_sensitivity_rank_diagnostic"]
    assert rank["pass"] is False
    assert rank["unusable_failed_goal_rows"] == [H13_REAL_GOAL_LABELS[5]]
    assert result["status"] == "controlled_negative_unusable_sensitivity"
    assert result["enumeration"]["support_count_evaluated"] == 0
    assert result["selected_candidate"] is None
    assert result["pde_gate"]["status"] == "not_run"


def test_step_inconsistency_returns_controlled_negative() -> None:
    fine = _full_rank_positive_sensitivity()
    coarse = fine.copy()
    coarse[0, 0] *= -1.0

    result = _select(fine, coarse=coarse)

    assert result["status"] == "controlled_negative_step_inconsistent"
    consistency = result["preflight"]["failed_goal_step_consistency"]
    assert consistency["pass"] is False
    assert consistency["failure_count"] == 1
    assert consistency["failures"][0]["goal"] == H13_REAL_GOAL_LABELS[0]
    assert consistency["failures"][0]["plane_index"] == 0
    assert result["enumeration"]["support_count_evaluated"] == 0
    assert result["pde_gate"]["status"] == "not_run"


def test_passed_channel_degradation_blocks_otherwise_positive_supports() -> None:
    base = _goals((4.0, 3.8, 2.5, 2.5, 2.3, 2.0))
    sensitivity = np.zeros((6, 9), dtype=np.float64)
    sensitivity[:, 0] = (-5.0, -5.0, -4.0, -4.0, -4.0, -4.0)
    protected_goals = (
        H13ProtectedRealGoal(
            label="T_bottom(-4,0)_s.complex_vector_L2_error",
            base_observable=0.95,
            reference=0.0,
            tolerance=1.0,
        ),
    )
    protected_sensitivity = np.zeros((1, 9), dtype=np.float64)
    protected_sensitivity[0, 0] = 2.0

    result = _select(
        sensitivity,
        goals=base,
        protected_goals=protected_goals,
        protected_sensitivity=protected_sensitivity,
    )

    assert result["status"] == (
        "controlled_negative_passed_channel_degradation"
    )
    assert result["decision"] == "no_candidate"
    assert result["enumeration"]["eligible_support_count"] == 0
    assert (
        result["enumeration"]["protected_blocked_positive_support_count"] > 0
    )
    protection = result["separate_protection_contract"]
    assert protection["protected_goal_count"] == 1
    assert protection["formal_12_channel_PDE_gate_still_required"] is True
    assert (
        result["source_contract"][
            "six_failed_targets_and_protected_goals_are_separate"
        ]
        is True
    )
    assert result["selected_candidate"] is None
    assert result["pde_gate"]["status"] == "not_run"


def test_full_rank_no_signal_is_preserved_as_controlled_negative() -> None:
    sensitivity = np.zeros((6, 9), dtype=np.float64)
    sensitivity[:, :6] = np.eye(6) * 1.0e-3

    result = _select(sensitivity)

    assert (
        result["preflight"]["failed_goal_sensitivity_rank_diagnostic"]["pass"]
        is True
    )
    assert result["status"] == "controlled_negative_no_signal"
    assert result["classification"] == "controlled_negative"
    assert result["enumeration"]["support_count_evaluated"] == 45
    assert result["enumeration"]["eligible_support_count"] == 0
    assert result["selected_candidate"] is None
    assert result["pde_gate"]["status"] == "not_run"
