"""Independent small complex algebra, augmented SVD and bounded state."""

import numpy as np
import pytest
from scipy.sparse.linalg import LinearOperator
from src.solvers.joint_least_squares import (
    realify,
    complexify,
    augmented_operator,
    solve_augmented,
    prediction,
    cauchy_step,
    JointLMState,
    power_scale,
)


def problem():
    rng = np.random.default_rng(4214701)
    A = rng.normal(size=(7, 4)) + 1j * rng.normal(size=(7, 4))
    J = LinearOperator(
        (14, 4),
        matvec=lambda x: realify(A @ x),
        rmatvec=lambda u: (A.conj().T @ complexify(u)).real,
        dtype=np.float64,
    )
    return A, J, rng


def test_realification_is_norm_preserving_and_requires_real_pairing():
    A, J, rng = problem()
    v = rng.normal(size=4)
    u = rng.normal(size=14)
    np.testing.assert_array_equal(complexify(realify(A @ v)), A @ v)
    assert np.dot(realify(A @ v), realify(A @ v)) == pytest.approx(
        np.vdot(A @ v, A @ v).real
    )
    assert np.dot(J @ v, u) == pytest.approx(np.dot(v, J.rmatvec(u)), abs=1e-12)
    wrong = (A.T @ complexify(u)).real
    assert abs(v @ wrong - np.dot(J @ v, u)) > 1e-3


def test_explicit_augmented_lsmr_matches_independent_small_svd():
    A, J, rng = problem()
    e = rng.normal(size=14)
    lam = 0.7
    full = np.vstack([A.real, A.imag, np.sqrt(lam) * np.eye(4)])
    rhs = np.r_[-e, np.zeros(4)]
    U, s, Vh = np.linalg.svd(full, full_matrices=False)
    expected = Vh.T @ ((U.T @ rhs) / s)
    v, jv, record = solve_augmented(J, e, lam)
    np.testing.assert_allclose(v, expected, rtol=1e-8, atol=1e-10)
    aug = augmented_operator(J, lam)
    residual = full @ v - rhs
    assert record["true_augmented_residual_norm"] == pytest.approx(
        np.linalg.norm(residual)
    )
    assert record["true_normal_defect_norm"] == pytest.approx(
        np.linalg.norm(full.T @ residual), abs=1e-12
    )
    assert prediction(e, jv) == pytest.approx(
        (e @ e - np.linalg.norm(e + J @ v) ** 2) / 2
    )
    assert not record["original_PDE_pass_from_stop_code"]
    np.testing.assert_allclose(aug @ v, full @ v, atol=1e-14)


@pytest.mark.parametrize(
    "trial,pred,factor,accepted",
    [
        (0.8, 0.3, 1, True),
        (0.7, 0.3, 1 / 3, True),
        (0.98, 0.1, 2, True),
        (2.0, 0.3, 10, False),
        (0.9, -1.0, 10, False),
        (np.inf, 0.3, 10, False),
    ],
)
def test_true_nonlinear_acceptance_and_review_damping_bounds(
    trial, pred, factor, accepted
):
    state = JointLMState(5.0)
    before = state.mu
    row = state.decide(1.0, trial, pred)
    assert row["accepted"] == accepted and state.mu == pytest.approx(before * factor)
    assert state.trials == 1 and state.accepted == int(accepted)
    state.mu = 1e20
    state.clamp()
    assert state.mu == 5e8
    state.mu = 1e-40
    state.clamp()
    assert state.mu == 5e-12


def test_one_cauchy_step_has_correct_damped_length():
    _, J, rng = problem()
    e = rng.normal(size=14)
    lam = 2.0
    v, jv = cauchy_step(J, e, lam)
    q = J.rmatvec(e)
    alpha = (q @ q) / (np.linalg.norm(J @ q) ** 2 + lam * (q @ q))
    np.testing.assert_allclose(v, -alpha * q, rtol=1e-14)
    assert prediction(e, jv) > 0


def test_power_scale_and_pending_costs_survive_serialization():
    A, J, _ = problem()
    h, info = power_scale(J)
    assert 0 < h <= np.linalg.norm(np.vstack([A.real, A.imag]), 2) ** 2 * (1 + 1e-12)
    assert info["iterations"] == 4 and not info["exact_spectral_bound"]
    old = JointLMState(h)
    old.pending_inner = 200
    old.pending_trial = True
    new = JointLMState(h)
    new.load_state_dict(old.state_dict())
    assert new.recover_lost_inner() == 200
    assert new.lsmr_iterations == 200 and new.lost_iterations_upper_bound == 200
    assert new.trials == 1 and new.lost_trial_upper_bound == 1
    assert new.recover_lost_inner() == 0 and new.trials == 1


def test_joint_schema_keeps_original_limits_and_pure_profile():
    import json
    from pathlib import Path
    from src.io.ftt_joint_campaign import DESIGN, STAGES, validate_design
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    from src.runners.neural_wave_campaign import stage_deadline
    from src.runners.block_wave_admission import pool, wait_limit

    d = json.loads(DESIGN.read_text())
    validate_design(d)
    for stage in STAGES:
        spec = load_wave(ROOT / "input/task042extra_feinn_5nm" / f"{stage}.dat")
        assert spec["campaign_version"] == 47
        paths = profile_paths(spec)
        assert (
            paths["reserve"] == 1800 and paths["root"] == ROOT / "tmp/task42extra/v47"
        )
        assert stage_deadline(
            spec, dict(deadline_monotonic=5000), dict(deadline_monotonic=6000)
        ) == (4200, 1800)
    assert (
        pool(ROOT / "tmp/task42extra/v47/test").parent == ROOT / "tmp/task42extra/v47"
    )
    assert wait_limit(Path(ROOT / "tmp/task42extra/v47/test")) == 900
    d["execution_policies"]["formal"]["total_lsmr"] += 1
    with pytest.raises(ValueError):
        validate_design(d)
