"""Independent explicit complex least squares, curvature and transaction tests."""

import numpy as np
import pytest
from src.solvers.damped_gauss_newton import (
    DampedGNState,
    damped_cg,
    range_ritz,
    apply_ritz_inverse,
)


@pytest.mark.parametrize("rank_deficient", [False, True])
def test_complex_nonhermitian_damped_solve_and_actual_predicted_decrease(
    rank_deficient,
):
    rng = np.random.default_rng(421901)
    A = rng.normal(size=(8, 8)) + 1j * rng.normal(size=(8, 8))
    J = rng.normal(size=(8, 6)) + 1j * rng.normal(size=(8, 6))
    if rank_deficient:
        J[:, -1] = J[:, 0]
    M = rng.normal(size=(8, 8)) + 1j * rng.normal(size=(8, 8))
    G = M.conj().T @ M + np.eye(8)
    f = rng.normal(size=8) + 1j * rng.normal(size=8)
    d = float(np.vdot(f, np.linalg.solve(G, f)).real)
    B = A @ J
    K = (B.conj().T @ np.linalg.solve(G, B)).real / d
    theta = rng.normal(size=6)

    def objective(t):
        r = B @ t - f
        return float(np.vdot(r, np.linalg.solve(G, r)).real / (2 * d))

    r = B @ theta - f
    g = (B.conj().T @ np.linalg.solve(G, r)).real / d
    mu = 0.003 * np.linalg.norm(K)
    s, record = damped_cg(lambda v: K @ v, g, mu, max_iter=12, tolerance=1e-11)
    np.testing.assert_allclose(
        s, np.linalg.solve(K + mu * np.eye(6), -g), rtol=1e-10, atol=1e-11
    )
    pred = -g @ s - 0.5 * s @ K @ s
    np.testing.assert_allclose(
        objective(theta) - objective(theta + s), pred, rtol=1e-11
    )
    assert record["true_relative"] < 1e-10
    assert np.linalg.norm(A - A.conj().T) > 1
    assert np.min(np.linalg.eigvalsh(K)) > -1e-12 * np.linalg.norm(K)


def test_fixed_range_ritz_inverse_and_spd_against_explicit_small_inverse():
    rng = np.random.default_rng(421902)
    M = rng.normal(size=(9, 9))
    K = M.T @ M
    V, lam, record = range_ritz(lambda v: K @ v, 9, rank=5)
    mu = 0.01
    P = mu * np.eye(9) + (V * lam) @ V.T
    for _ in range(3):
        v = rng.normal(size=9)
        np.testing.assert_allclose(
            apply_ritz_inverse(v, V, lam, mu),
            np.linalg.solve(P, v),
            rtol=1e-10,
            atol=1e-10,
        )
        assert v @ apply_ritz_inverse(v, V, lam, mu) > 0
    assert record["K_actions"] == 10 and record["orthogonality"] < 1e-12
    with pytest.raises(ValueError, match="NEGATIVE"):
        range_ritz(lambda v: -v, 9, rank=5)


def test_nonlinear_actual_trial_exception_restores_committed_parameter_state():
    live = np.array([0.25])
    start = live.copy()
    state = DampedGNState(1.0)

    def evaluate(theta, restore_only=False):
        live[:] = theta
        if not restore_only:
            raise RuntimeError("nonlinear trial failure")

    with pytest.raises(RuntimeError, match="trial failure"):
        state.propose(start, 1.0, np.array([1.0]), lambda v: v, evaluate)
    np.testing.assert_array_equal(live, start)
    assert state.accepted == 0


def test_nonlinear_bad_local_model_rejects_then_accepts_true_loss():
    theta = np.array([0.1])
    live = theta.copy()

    def loss(t):
        return float((t[0] ** 2 - 1) ** 2 / 2)

    g = np.array([2 * theta[0] * (theta[0] ** 2 - 1)])
    K = np.array([[4 * theta[0] ** 2]])
    logs = []
    state = DampedGNState(float(K[0, 0]))

    def evaluate(t, restore_only=False):
        live[:] = t
        return None if restore_only else loss(t)

    updated, row = state.propose(
        theta, loss(theta), g, lambda v: K @ v, evaluate, logs.append
    )
    assert updated is not None and loss(updated) < loss(theta)
    assert any(r.get("accepted") is False for r in logs)
    assert row["eta"] >= 0.1
    np.testing.assert_array_equal(live, theta)
    restored = DampedGNState(1.0)
    restored.load_state_dict(state.state_dict())
    assert restored.mu == state.mu and restored.accepted == state.accepted
