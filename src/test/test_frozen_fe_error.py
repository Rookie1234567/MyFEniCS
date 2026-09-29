"""A genuinely loaded complex port/body system, never a zero/zero witness."""

import numpy as np
import pytest

from src.solvers.frozen_fe_error import (
    FrozenActions,
    complex_correlation,
    defect,
    error_diagnostics,
    state_audits,
    sum_components,
)
from src.solvers.neural_fe_action_packet import ActionPacket
from src.test.test_neural_fe_action_packet import witness


def loaded_witness():
    p, S, *_ = witness()
    a = {k: v.copy() for k, v in p.a.items()}
    # Exact trace pullback of the nonzero interior particular solution.
    body0, port0, _ = p.uncondensed(
        p.recover(np.zeros(p.size, complex)), np.zeros(p.np, complex)
    )
    a["b"] = np.r_[(a["g"] - body0)[a["masters"]], a["gp"] + port0]
    return ActionPacket(a), S


def test_affine_recovery_and_all_complex_equation_identities():
    p, S = loaded_witness()
    exact = np.linalg.solve(S, p.a["b"])
    # A NONZERO accurate-reference residual must not be silently erased.
    ref = exact + np.array([1, -2j, 3 + 2j, -4]) * 1e-7
    D = np.array([0.3, 2, 0.7, 1.1])
    y = np.array([0.4 + 0.1j, -0.2j, 0.3 - 0.4j, -0.5 + 0.6j])
    z = D * y  # already physical coordinates; never multiply D again.
    actions = FrozenActions(p)
    states = {"Z0": np.zeros(p.size, complex), "LSQR8": z, "REF7": ref}
    original = {k: v.copy() for k, v in states.items()}
    cache, audits = state_audits(actions, states)
    errors, records = error_diagnostics(actions, cache)
    assert audits["REF7"]["schur_absolute"] > 1e-8
    assert np.linalg.norm(p.a["i_rhs"]) > 0
    assert np.linalg.norm(p.a["gp"]) > 0
    assert np.linalg.norm(z[p.nt :]) > 0
    for key in records:
        row = records[key]
        for name in (
            "residual_identity",
            "homogeneous_recovery",
            "affine_difference",
            "background_cancellation",
            "augmented_identity",
            "native_identity",
        ):
            assert row[name]["operation_relative"] < 1e-12
        assert row["wrong_default_recovery_error_norm"] > 1e-4
        np.testing.assert_allclose(
            errors[key]["homogeneous"], errors[key]["delta"], atol=1e-13
        )
    for key in states:
        np.testing.assert_array_equal(states[key], original[key])
        np.testing.assert_allclose(
            cache[key]["r"], p.a["b"] - S @ states[key], atol=1e-13
        )


def test_cross_terms_correlation_and_near_zero_are_not_phase_fits():
    left = np.array([1 + 2j, 3 - 0.4j])
    right = -0.8 * np.exp(0.7j) * left
    row = sum_components(left, right)
    assert abs(row["cross_imag"]) > 1
    assert row["squared_identity_absolute"] < 1e-13
    assert row["sum_squared"] != pytest.approx(
        row["left_norm"] ** 2 + row["right_norm"] ** 2
    )
    correlation = complex_correlation(
        np.vdot(left, right), np.vdot(left, left).real, np.vdot(right, right).real
    )
    assert correlation["amplitude_norm_ratio"] == pytest.approx(0.8)
    assert correlation["correlation"] == pytest.approx(-np.exp(0.7j))
    assert complex_correlation(0, 1, 0)["correlation"] is None
    assert sum_components(np.zeros(2), np.zeros(2))["cancellation_fraction"] is None
    assert defect(np.zeros(2), np.array([1e-14, 0]))["operation_relative"] == 1e-14


def test_budget_counts_failed_calls_and_refuses_extra_actions():
    p, _ = loaded_witness()
    actions = FrozenActions(p, limit=1)
    actions.apply(np.zeros(p.size))
    with pytest.raises(RuntimeError, match="action budget"):
        actions.apply(np.zeros(p.size))
    assert actions.counts["S"] == 1
