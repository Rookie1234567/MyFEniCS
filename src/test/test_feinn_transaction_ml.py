"""A rejected/aborted line search cannot become the final accepted checkpoint."""

import numpy as np
import pytest

from src.solvers.feinn_optimization import RouteStop, transactional_step


def test_abort_restores_last_complete_outer_step_and_preserves_trial():
    state = np.array([1.0, 2.0])
    observed_trial = []

    def read():
        return state.copy()

    def restore(values):
        state[:] = values

    def closure():
        observed_trial.append(state.copy())
        raise RouteStop("closure budget")

    def step(function):
        state[:] = [7.0, 8.0]
        function()

    with pytest.raises(RouteStop):
        transactional_step(step, closure, read, restore)
    np.testing.assert_array_equal(state, [1, 2])
    np.testing.assert_array_equal(observed_trial[-1], [7, 8])


def test_completed_step_commits_values():
    state = np.array([1.0])

    def step(closure):
        state[:] = 3
        return closure()

    transactional_step(
        step,
        lambda: 0,
        lambda: state.copy(),
        lambda p: state.__setitem__(slice(None), p),
    )
    np.testing.assert_array_equal(state, [3])
