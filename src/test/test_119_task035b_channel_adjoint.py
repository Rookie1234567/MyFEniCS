from __future__ import annotations

import numpy as np
import pytest
from petsc4py import PETSc

from src.adaptivity.dtn_goal_adjoint import (
    DtnChannelGoal,
    build_dtn_channel_goal_gradient,
    dtn_channel_goal_value,
    task035b_failed_channel_goals,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d


def _distributed_state(values: np.ndarray) -> PETSc.Vec:
    state = PETSc.Vec().createMPI(len(values))
    start, end = state.getOwnershipRange()
    if end > start:
        state.setValues(
            np.arange(start, end, dtype=PETSc.IntType),
            np.asarray(values[start:end], dtype=PETSc.ScalarType),
        )
    state.assemble()
    return state


def test_review_v1_failed_channel_goal_contract_is_independent() -> None:
    goals = task035b_failed_channel_goals()
    assert len(goals) == 16
    assert len({goal.label for goal in goals}) == 16
    assert sum(goal.quantity == "power" for goal in goals) == 6
    assert sum(goal.quantity == "amplitude_real" for goal in goals) == 5
    assert sum(goal.quantity == "amplitude_imag" for goal in goals) == 5
    assert {
        (goal.side, goal.m, goal.n)
        for goal in goals
        if goal.quantity == "power"
    } == {
        (side, m, 0)
        for side in ("top", "bottom")
        for m in (-2, -4, -5)
    }


@pytest.mark.parametrize("goal", task035b_failed_channel_goals())
def test_single_channel_gradient_matches_directional_difference(
    goal: DtnChannelGoal,
) -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    count = len(modes)
    auxiliary = np.asarray(
        [
            complex(0.002 * (index + 1), -0.0015 * (index + 2))
            for index in range(count)
        ],
        dtype=np.complex128,
    )
    incident = np.zeros(count, dtype=np.complex128)
    n_fe = 3
    state_values = np.concatenate(
        (np.asarray((0.2 + 0.1j, -0.3j, 0.4)), auxiliary)
    )
    state = _distributed_state(state_values)
    context = {
        "num_fem_dofs_after_mpc": n_fe,
        "modes": modes,
        "auxiliary_values": auxiliary,
        "incident_projections": incident,
    }
    gradient, metadata = build_dtn_channel_goal_gradient(
        state,
        config,
        context,
        goal=goal,
    )
    direction_values = np.asarray(
        [
            complex(
                np.cos(0.31 * (index + 1)),
                np.sin(0.17 * (index + 2)),
            )
            for index in range(len(state_values))
        ],
        dtype=np.complex128,
    )
    direction = _distributed_state(direction_values)
    step = 1.0e-7
    auxiliary_direction = direction_values[n_fe:]
    plus = dtn_channel_goal_value(
        config,
        modes,
        auxiliary + step * auxiliary_direction,
        incident,
        goal=goal,
    )
    minus = dtn_channel_goal_value(
        config,
        modes,
        auxiliary - step * auxiliary_direction,
        incident,
        goal=goal,
    )
    finite_difference = (plus - minus) / (2.0 * step)
    analytic = float(np.real(gradient.dot(direction)))
    assert finite_difference == pytest.approx(
        analytic,
        rel=2.0e-8,
        abs=2.0e-10,
    )
    assert metadata["canonical_channel_identity"] == {
        "side": goal.side,
        "m": goal.m,
        "n": goal.n,
        "polarization": goal.polarization,
    }
    assert metadata["gradient_norm"] > 0.0
    direction.destroy()
    gradient.destroy()
    state.destroy()


def test_channel_goal_fails_closed_when_mode_is_absent() -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    auxiliary = np.zeros(len(modes), dtype=np.complex128)
    incident = np.zeros(len(modes), dtype=np.complex128)
    with pytest.raises(ValueError, match="exactly one auxiliary mode"):
        dtn_channel_goal_value(
            config,
            modes,
            auxiliary,
            incident,
            goal=DtnChannelGoal(
                "top",
                -999,
                0,
                "s",
                "power",
            ),
        )
