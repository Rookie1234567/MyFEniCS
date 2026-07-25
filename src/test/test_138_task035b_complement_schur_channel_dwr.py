"""Exact tiny tests for the Task035b complement Schur/DWR kernel."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse.linalg import LinearOperator

from src.adaptivity.complement_schur_channel_dwr import (
    ChannelGoal,
    ComplementSchurOperator,
    WholeOrbitBlock,
    evaluate_complement_channel_dwr,
)


def _linear_operator(matrix: np.ndarray) -> LinearOperator:
    values = np.asarray(matrix, dtype=np.complex128)
    return LinearOperator(
        values.shape,
        matvec=lambda vector: values @ vector,
        rmatvec=lambda vector: values.conj().T @ vector,
        dtype=np.complex128,
    )


def test_action_only_schur_and_dwr_match_full_complex_block_system() -> None:
    a_ll = np.asarray(
        [
            [4.0 + 0.3j, 0.2 - 0.1j],
            [-0.1 + 0.25j, 3.2 - 0.4j],
        ],
        dtype=np.complex128,
    )
    a_lh = np.asarray(
        [
            [0.4 + 0.2j, -0.3j, 0.1],
            [0.2 - 0.1j, 0.35, -0.2 + 0.15j],
        ],
        dtype=np.complex128,
    )
    a_hl = np.asarray(
        [
            [0.3 - 0.2j, 0.1],
            [-0.2j, 0.25 + 0.1j],
            [0.15, -0.1 + 0.2j],
        ],
        dtype=np.complex128,
    )
    a_hh = np.asarray(
        [
            [2.8 + 0.2j, 0.1, -0.05j],
            [-0.15j, 2.4 - 0.1j, 0.2],
            [0.05, -0.1j, 2.1 + 0.3j],
        ],
        dtype=np.complex128,
    )
    b_low = np.asarray([1.0 + 0.2j, -0.3 + 0.7j])
    b_high = np.asarray([0.4 - 0.1j, -0.2 + 0.3j, 0.5 + 0.2j])
    g_low = np.asarray([0.2 - 0.4j, 0.6 + 0.1j])
    g_high = np.asarray([0.7 + 0.2j, -0.1j, 0.3 - 0.2j])

    schur_dense = a_hh - a_hl @ np.linalg.solve(a_ll, a_lh)
    operator = ComplementSchurOperator(
        low_dimension=2,
        high_dimension=3,
        a_hh=_linear_operator(a_hh),
        a_hl=_linear_operator(a_hl),
        a_lh=_linear_operator(a_lh),
        a_ll_solve=lambda rhs: np.linalg.solve(a_ll, rhs),
        a_ll_adjoint_solve=lambda rhs: np.linalg.solve(
            a_ll.conj().T,
            rhs,
        ),
        schur_solve=lambda rhs: np.linalg.solve(schur_dense, rhs),
        schur_adjoint_solve=lambda rhs: np.linalg.solve(
            schur_dense.conj().T,
            rhs,
        ),
    )
    retained_state = np.linalg.solve(a_ll, b_low)
    retained_adjoint = np.linalg.solve(a_ll.conj().T, g_low)
    result = evaluate_complement_channel_dwr(
        operator,
        missing_right_hand_side=b_high,
        retained_state=retained_state,
        goals=(
            ChannelGoal(
                label="T_m-4_n0_s_amplitude_real",
                component="complex_amplitude_real",
                tolerance=2.0e-3,
                missing_gradient=g_high,
                retained_adjoint=retained_adjoint,
                actual_channel_gradient=True,
                retained_adjoint_qualified=True,
                baseline_signed_error=1.0e-3,
            ),
        ),
        orbits=(
            WholeOrbitBlock(
                orbit_id="all_missing_trace",
                complement_indices=(0, 1, 2),
                member_entity_ids=(20, 21),
                periodic_orbit_closed=True,
            ),
        ),
    )

    full_operator = np.block([[a_ll, a_lh], [a_hl, a_hh]])
    full_rhs = np.concatenate((b_low, b_high))
    full_solution = np.linalg.solve(full_operator, full_rhs)
    full_gradient = np.concatenate((g_low, g_high))
    full_adjoint = np.linalg.solve(
        full_operator.conj().T,
        full_gradient,
    )
    embedded_low_solution = np.concatenate(
        (retained_state, np.zeros(3, dtype=np.complex128))
    )
    exact_goal_difference = complex(
        np.vdot(full_gradient, full_solution - embedded_low_solution)
    )

    expected_r_high = b_high - a_hl @ retained_state
    np.testing.assert_allclose(result.primal_residual, expected_r_high)
    np.testing.assert_allclose(
        result.complement_correction,
        full_solution[2:],
    )
    channel = result.goals["T_m-4_n0_s_amplitude_real"]
    np.testing.assert_allclose(
        channel.goal_complement,
        g_high - a_lh.conj().T @ retained_adjoint,
    )
    np.testing.assert_allclose(
        channel.complement_adjoint,
        full_adjoint[2:],
    )
    np.testing.assert_allclose(
        channel.correction_pairing,
        exact_goal_difference,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        channel.residual_weighted_pairing,
        exact_goal_difference,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    assert channel.identity_relative_error < 2.0e-13
    assert operator.audit["Schur_matrix_materialized_by_kernel"] is False
    assert operator.audit["block_storage"] == {
        "A_HH": "linear_operator",
        "A_HL": "linear_operator",
        "A_LH": "linear_operator",
    }


def test_real_power_re_im_normalization_orbit_ranking_and_rrqr() -> None:
    identity_high = np.eye(6, dtype=np.complex128)
    zero_hl = np.zeros((6, 1), dtype=np.complex128)
    zero_lh = np.zeros((1, 6), dtype=np.complex128)
    operator = ComplementSchurOperator(
        low_dimension=1,
        high_dimension=6,
        a_hh=_linear_operator(identity_high),
        a_hl=_linear_operator(zero_hl),
        a_lh=_linear_operator(zero_lh),
        a_ll_solve=lambda rhs: rhs.copy(),
        a_ll_adjoint_solve=lambda rhs: rhs.copy(),
        schur_solve=lambda rhs: rhs.copy(),
        schur_adjoint_solve=lambda rhs: rhs.copy(),
    )
    residual = np.asarray(
        [-0.1, -0.05, 2.0, 0.0, 1.0 + 2.0j, 0.5 + 1.0j]
    )
    target_gradient = np.asarray([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    protected_gradient = np.asarray([0.0, 0.0, 0.0, 0.0, 1.0, 1.0])
    goals = (
        ChannelGoal(
            label="T_m-4_n0_s_power",
            component="real_power",
            tolerance=1.0,
            missing_gradient=target_gradient,
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=True,
            baseline_signed_error=0.2,
        ),
        ChannelGoal(
            label="R_m-5_n0_s_power",
            component="real_power",
            tolerance=1.0,
            missing_gradient=protected_gradient,
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=False,
            protected=True,
            baseline_signed_error=0.2,
        ),
        ChannelGoal(
            label="R_m-5_n0_s_amplitude_real",
            component="complex_amplitude_real",
            tolerance=0.5,
            missing_gradient=protected_gradient,
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=False,
        ),
        ChannelGoal(
            label="R_m-5_n0_s_amplitude_imag",
            component="complex_amplitude_imag",
            tolerance=0.5,
            missing_gradient=1j * protected_gradient,
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=False,
        ),
    )
    result = evaluate_complement_channel_dwr(
        operator,
        missing_right_hand_side=residual,
        retained_state=np.zeros(1),
        goals=goals,
        orbits=(
            WholeOrbitBlock(
                orbit_id="target_orbit",
                complement_indices=(0, 1),
                member_entity_ids=(10, 11),
                periodic_orbit_closed=True,
            ),
            WholeOrbitBlock(
                orbit_id="large_reverse_target_orbit",
                complement_indices=(2, 3),
                member_entity_ids=(14, 15),
                periodic_orbit_closed=True,
            ),
            WholeOrbitBlock(
                orbit_id="protected_orbit",
                complement_indices=(4, 5),
                member_entity_ids=(12, 13),
                periodic_orbit_closed=True,
            ),
        ),
    )

    assert (
        result.goals["T_m-4_n0_s_power"].normalized_signed_correction
        == pytest.approx(1.85)
    )
    assert result.goals["R_m-5_n0_s_power"].normalized_signed_correction == 1.5
    assert (
        result.goals[
            "R_m-5_n0_s_amplitude_real"
        ].normalized_signed_correction
        == 3.0
    )
    assert (
        result.goals[
            "R_m-5_n0_s_amplitude_imag"
        ].normalized_signed_correction
        == 6.0
    )
    assert result.ranked_orbits[0].orbit_id == "target_orbit"
    target = result.ranked_orbits[0]
    reverse = next(
        orbit
        for orbit in result.ranked_orbits
        if orbit.orbit_id == "large_reverse_target_orbit"
    )
    protected = next(
        orbit
        for orbit in result.ranked_orbits
        if orbit.orbit_id == "protected_orbit"
    )
    assert target.rank == 1
    assert target.selection_score == pytest.approx(0.15)
    assert target.target_regression_count == 0
    assert target.target_gate_crossing_count == 0
    assert target.goals["T_m-4_n0_s_power"][
        "normalized_absolute_error_improvement"
    ] == pytest.approx(0.15)
    assert target.protected_regression_count == 0
    assert reverse.rank > 1
    assert reverse.selection_score == 0.0
    assert reverse.target_regression_count == 1
    assert reverse.target_gate_crossing_count == 1
    assert reverse.target_regression_penalty == pytest.approx(2.0)
    assert reverse.goals["T_m-4_n0_s_power"][
        "target_regression"
    ] is True
    assert reverse.goals["T_m-4_n0_s_power"][
        "target_gate_crossing"
    ] is True
    assert protected.protected_regression_count == 1
    assert protected.protected_gate_crossing_count == 1
    assert protected.goals["R_m-5_n0_s_power"][
        "protected_regression"
    ] is True
    diagnostics = result.svd_rrqr_diagnostics
    np.testing.assert_allclose(
        diagnostics["singular_values"],
        [np.sqrt(47.25), np.sqrt(4.0225), 0.0],
    )
    assert diagnostics["numerical_rank"] == 2
    assert diagnostics["rrqr_pivot_orbit_ids"] == [
        "protected_orbit",
        "large_reverse_target_orbit",
        "target_orbit",
    ]
    assert diagnostics["rrqr_operates_on_whole_orbit_columns"] is True


def test_fail_closed_orbits_channel_provenance_and_external_audit() -> None:
    operator = ComplementSchurOperator(
        low_dimension=1,
        high_dimension=2,
        a_hh=np.eye(2),
        a_hl=np.zeros((2, 1)),
        a_lh=np.zeros((1, 2)),
        a_ll_solve=lambda rhs: rhs,
        a_ll_adjoint_solve=lambda rhs: rhs,
        schur_solve=lambda rhs: rhs,
        schur_adjoint_solve=lambda rhs: rhs,
    )
    unqualified = ChannelGoal(
        label="R_m-4_n0_s_power",
        component="real_power",
        tolerance=1.0,
        missing_gradient=np.ones(2),
        retained_adjoint=np.zeros(1),
        actual_channel_gradient=False,
        retained_adjoint_qualified=True,
        baseline_signed_error=0.5,
    )
    closed = WholeOrbitBlock(
        orbit_id="closed",
        complement_indices=(0, 1),
        member_entity_ids=(1, 2),
        periodic_orbit_closed=True,
    )
    with pytest.raises(RuntimeError, match="not an actual channel gradient"):
        evaluate_complement_channel_dwr(
            operator,
            missing_right_hand_side=np.ones(2),
            retained_state=np.zeros(1),
            goals=(unqualified,),
            orbits=(closed,),
        )

    qualified = ChannelGoal(
        label="R_m-4_n0_s_power",
        component="real_power",
        tolerance=1.0,
        missing_gradient=np.ones(2),
        retained_adjoint=np.zeros(1),
        actual_channel_gradient=True,
        retained_adjoint_qualified=True,
        baseline_signed_error=0.5,
    )
    with pytest.raises(RuntimeError, match="not certified closed"):
        evaluate_complement_channel_dwr(
            operator,
            missing_right_hand_side=np.ones(2),
            retained_state=np.zeros(1),
            goals=(qualified,),
            orbits=(
                WholeOrbitBlock(
                    orbit_id="open",
                    complement_indices=(0, 1),
                    member_entity_ids=(1, 2),
                    periodic_orbit_closed=False,
                ),
            ),
        )
    with pytest.raises(ValueError, match="must partition"):
        evaluate_complement_channel_dwr(
            operator,
            missing_right_hand_side=np.ones(2),
            retained_state=np.zeros(1),
            goals=(qualified,),
            orbits=(
                WholeOrbitBlock(
                    orbit_id="partial",
                    complement_indices=(0,),
                    member_entity_ids=(1,),
                    periodic_orbit_closed=True,
                ),
            ),
        )

    result = evaluate_complement_channel_dwr(
        operator,
        missing_right_hand_side=np.ones(2),
        retained_state=np.zeros(1),
        goals=(qualified,),
        orbits=(closed,),
    )
    assert result.audit["physical_candidate_qualification_authorized"] is False
    assert result.audit["inactive_p6_rows_allocated_by_kernel"] is False
    assert result.audit["ordinary_default_changed"] is False
    assert set(result.audit["external_integration"].values()) == {"not_run"}


def test_selection_roles_and_true_relative_solve_residual_fail_closed() -> None:
    with pytest.raises(ValueError, match="baseline signed error"):
        ChannelGoal(
            label="missing_baseline",
            component="real_power",
            tolerance=1.0,
            missing_gradient=np.ones(2),
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=True,
        )
    with pytest.raises(ValueError, match="both selection_target and protected"):
        ChannelGoal(
            label="ambiguous_role",
            component="real_power",
            tolerance=1.0,
            missing_gradient=np.ones(2),
            retained_adjoint=np.zeros(1),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=True,
            protected=True,
            baseline_signed_error=0.1,
        )

    common = {
        "low_dimension": 1,
        "high_dimension": 2,
        "a_hh": np.eye(2),
        "a_hl": np.zeros((2, 1)),
        "a_lh": np.zeros((1, 2)),
        "a_ll_solve": lambda rhs: rhs.copy(),
        "a_ll_adjoint_solve": lambda rhs: rhs.copy(),
        "schur_adjoint_solve": lambda rhs: rhs.copy(),
    }
    small_rhs_bad_solve = ComplementSchurOperator(
        **common,
        schur_solve=lambda rhs: np.zeros_like(rhs),
    )
    with pytest.raises(RuntimeError, match="residual gate"):
        small_rhs_bad_solve.solve(np.asarray([1.0e-15, 0.0]))

    zero_rhs_bad_solve = ComplementSchurOperator(
        **common,
        schur_solve=lambda rhs: np.asarray([1.0e-30, 0.0]),
    )
    with pytest.raises(RuntimeError, match="residual gate"):
        zero_rhs_bad_solve.solve(np.zeros(2))

    zero_rhs_exact_solve = ComplementSchurOperator(
        **common,
        schur_solve=lambda rhs: rhs.copy(),
    )
    np.testing.assert_array_equal(
        zero_rhs_exact_solve.solve(np.zeros(2)),
        np.zeros(2),
    )
