"""Ill-conditioned explicit toy: slow CG can accept and trigger bounded Ritz PC."""

import numpy as np

from src.solvers.damped_gauss_newton import DampedGNState


def test_third_slow_cg_triggers_fixed_rank32_without_discarding_descent():
    eigenvalues = np.geomspace(1, 1e10, 120)
    target = -np.ones(120) / eigenvalues
    live = np.zeros(120)
    theta = live.copy()
    calls = []
    history = []
    state = DampedGNState(1.0, pc_max_builds=1)
    # Retained optimizer metadata contains two previous nonconverged CG solves.
    state.slow_streak = 2

    def K(v):
        calls.append(v.copy())
        return eigenvalues * v

    def objective(t):
        error = t - target
        return float(0.5 * np.dot(error, eigenvalues * error))

    def evaluate(t, restore_only=False):
        live[:] = t
        return None if restore_only else objective(t)

    after, row = state.propose(
        theta, objective(theta), np.ones(120), K, evaluate, history.append
    )
    assert row["accepted"] and objective(after) < objective(theta)
    assert not row["cg"]["converged"] and row["cg"]["iterations"] == 40
    builds = [x for x in history if x["kind"] == "PC_BUILD"]
    assert len(builds) == 1 and builds[0]["K_actions"] == 64
    assert builds[0]["rank_requested"] == 32 and builds[0]["source_accepted_outer"] == 0
    assert len(state.pc_builds) == 1 and state.V.shape[1] <= 32
    np.testing.assert_array_equal(live, theta)
    restored = DampedGNState(2.0)
    restored.load_state_dict(state.state_dict())
    np.testing.assert_array_equal(restored.V, state.V)
    np.testing.assert_array_equal(restored.lam, state.lam)
    assert restored.pc_builds == state.pc_builds and restored.mu == state.mu
    assert len(calls) >= 64 + 40 + 2
