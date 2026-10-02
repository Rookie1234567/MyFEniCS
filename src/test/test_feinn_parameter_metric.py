"""Independent complex algebra and transaction tests for the opt-in metric."""

import numpy as np
import pytest

from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.feinn_parameter_metric import (
    ParameterMetric,
    MetricDampedGNState,
    GROUP_SIZES,
    grouped_metric,
)


@pytest.mark.parametrize("near_rank", [False, True])
@pytest.mark.parametrize("scale", [1.0, 100.0])
def test_two_damping_relations_against_independent_complex_dense(near_rank, scale):
    rng = np.random.default_rng(4211101)
    A = rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))
    J = rng.normal(size=(9, 6)) + 1j * rng.normal(size=(9, 6))
    if near_rank:
        J[:, -1] = J[:, 0] + 1e-12 * J[:, -1]
    H = rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))
    G = H.conj().T @ H + np.eye(9)
    Z = A @ J
    K = (Z.conj().T @ np.linalg.solve(G, Z)).real
    r = rng.normal(size=9) + 1j * rng.normal(size=9)
    g = (Z.conj().T @ np.linalg.solve(G, r)).real
    M = ParameterMetric(np.geomspace(1 / scale, scale, 6))
    S = M.S
    mu = 0.7
    direct = np.linalg.solve(K + mu * np.diag(M.diagonal), -g)
    y = np.linalg.solve(S[:, None] * K * S[None, :] + mu * np.eye(6), -S * g)
    np.testing.assert_allclose(S * y, direct, rtol=1e-10, atol=1e-10)
    old = np.linalg.solve(K + mu * np.eye(6), -g)
    coordinate_only = np.linalg.solve(
        S[:, None] * K * S[None, :] + mu * np.diag(S**2), -S * g
    )
    np.testing.assert_allclose(S * coordinate_only, old, rtol=1e-10, atol=1e-10)
    step, cg = M.solve(lambda v: K @ v, g, mu, max_iter=40, tolerance=1e-12)
    np.testing.assert_allclose(step, direct, rtol=1e-10, atol=1e-10)
    rho = np.linalg.norm((K + mu * np.diag(M.diagonal)) @ step + g) / np.linalg.norm(g)
    assert abs(rho - cg["original_parameter_true_relative"]) <= 1e-12


def test_original_residual_does_not_inherit_scaled_convergence():
    K = np.array([[2.0, 0.1], [0.1, 5.0]])
    g = np.array([0.001, 2.0])
    metric = ParameterMetric([1e-4, 1e4])
    s, cg = metric.solve(lambda v: K @ v, g, 1.0, max_iter=1)
    rho = np.linalg.norm(K @ s + metric.diagonal * s + g) / np.linalg.norm(g)
    assert cg["converged"] == (rho <= 0.01)
    assert abs(cg["true_relative"] - rho) < 1e-12


def test_identity_full_proposal_and_rejected_trial_restore():
    K = np.diag([1.0, 3.0, 20.0])
    g = np.array([0.2, -0.3, 0.4])
    theta = np.array([2.0, 3.0, 4.0])
    live = theta.copy()

    def evaluate(t, restore_only=False):
        live[:] = t
        delta = t - theta
        return None if restore_only else float(5 + g @ delta + 0.5 * delta @ K @ delta)

    ordinary = DampedGNState(4.0, pc_max_builds=0)
    opt = MetricDampedGNState(4.0, ParameterMetric(np.ones(3)))
    a, ar = ordinary.propose(theta, 5.0, g, lambda v: K @ v, evaluate)
    b, br = opt.propose(theta, 5.0, g, lambda v: K @ v, evaluate)
    np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-12)
    assert ar["accepted"] and br["accepted"] and ordinary.mu == opt.mu
    np.testing.assert_array_equal(live, theta)

    # True objective rejects every nonlinear trial, including Cauchy.
    def reject(t, restore_only=False):
        live[:] = t
        return None if restore_only else 100.0

    restored = opt.state_dict()
    new, row = opt.propose(theta, 5.0, g, lambda v: K @ v, reject)
    assert new is None and row["stop_reason"] == "GN_MODEL_STAGNATION"
    np.testing.assert_array_equal(live, theta)
    opt.load_state_dict(restored)
    clone = MetricDampedGNState(1.0, ParameterMetric(np.ones(3)))
    clone.load_state_dict(opt.state_dict())
    assert clone.state_dict() == opt.state_dict()
    with pytest.raises(ValueError, match="METRIC_CHANGED"):
        MetricDampedGNState(1.0, ParameterMetric([1.0, 2.0, 3.0])).load_state_dict(
            restored
        )


def test_eight_groups_and_fixed_clipping_without_dense_matrix():
    q = np.repeat(np.geomspace(1e-10, 1e5, 8)[:, None], 3, axis=1)
    metric, record = grouped_metric(q)
    assert sum(GROUP_SIZES) == 8966 and metric.diagonal.shape == (8966,)
    assert record["clipping_count"] > 0 and record["curvature_span"] >= 10
    offset = 0
    for n, value in zip(GROUP_SIZES, record["values"]):
        np.testing.assert_array_equal(metric.diagonal[offset : offset + n], value)
        offset += n
    assert metric.sha256 == ParameterMetric(metric.diagonal.copy()).sha256
