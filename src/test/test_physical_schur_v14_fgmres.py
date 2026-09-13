"""V14 progress gates and a real, single-KSP finite-restart check."""

import numpy as np
import pytest

from src.solvers.physical_balanced_fgmres import V14SchurScreen, run_balanced_fgmres


@pytest.mark.parametrize(
    'relative,seconds,passed',
    [(.10, 1800., True), (.10001, 100., False), (.09, 1800.01, False)],
)
def test_window64_requires_both_residual_and_cost(relative, seconds, passed):
    screen = V14SchurScreen()
    assert screen.inspect(56, .8, 100.) is None
    assert screen.check_due(64, seconds)
    decision = screen.inspect(64, relative, seconds)
    assert decision['passed'] is passed
    assert screen.window64_checked


def test_window64_pass_does_not_skip_later_time_gates():
    screen = V14SchurScreen()
    assert screen.inspect(64, .09, 900.)['passed']
    assert screen.check_due(73, 1800.)
    decision = screen.inspect(73, .11, 1800.)
    assert decision['gate'] == 'early_time'
    assert not decision['passed']
    assert len(screen.decisions) == 2
    assert screen.inspect(80, .01, 1900.) == decision


def test_early_time_gate_can_stop_before64_and_mid_gate_remains_independent():
    screen = V14SchurScreen()
    assert not screen.inspect(13, .4, 1800.)['passed']
    screen = V14SchurScreen()
    assert screen.inspect(64, .09, 800.)['passed']
    assert screen.inspect(100, .08, 1800.)['passed']
    assert screen.inspect_mid_budget(200, .002, 5399.) is None
    assert not screen.inspect_mid_budget(201, .002, 5400.)['passed']


def test_v14_policy_is_exclusive_and_has_frozen_solve_budget():
    arguments = dict(checkpoint=None, append=None, seconds=None)
    with pytest.raises(ValueError, match='mutually exclusive'):
        run_balanced_fgmres(None, None, None, v14_policy=True, v9_policy=True,
                           **arguments)
    with pytest.raises(ValueError, match='10800'):
        run_balanced_fgmres(None, None, None, v14_policy=True, **arguments)
    with pytest.raises(ValueError, match='requires the frozen'):
        run_balanced_fgmres(None, None, None, v14_policy=True,
                           solve_limit_seconds=10800, screen_enabled=False,
                           **arguments)


def test_goal_before64_finishes_without_filling_the_window():
    from petsc4py import PETSc

    rhs = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    rhs.set(1)
    result = None
    try:
        result = run_balanced_fgmres(
            rhs, lambda x: x.copy(), lambda x: x.copy(),
            checkpoint=lambda *_: None, append=lambda *_: None,
            seconds=lambda: 1., v14_policy=True, solve_limit_seconds=10800,
        )
        assert result['status'] == 'TRUE_RESIDUAL_PASS'
        assert result['iterations'] == 1
        assert result['pc_apply_count'] == 1
        assert result['progress_decisions'] == []
    finally:
        if result is not None:
            result['final_solution'].destroy()
        rhs.destroy()


def test_real_restart32_keeps_one_ksp_and_stops_at64():
    """The bidiagonal chain needs a long Krylov space; no PDE/factor is used."""
    from petsc4py import PETSc

    rhs = PETSc.Vec().createSeq(128, comm=PETSc.COMM_SELF)
    rhs.set(0)
    rhs.array[0] = 1
    checkpoints, records = [], []

    def action(source):
        result = source.copy()
        result.array[1:] -= source.array[:-1]
        return result

    result = None
    try:
        result = run_balanced_fgmres(
            rhs, action, lambda source: source.copy(),
            checkpoint=lambda iteration, _x, rho: checkpoints.append((iteration, rho)),
            append=lambda name, row: records.append((name, row)),
            seconds=lambda: 1., v14_policy=True, solve_limit_seconds=10800,
        )
        assert result['iterations'] == 64
        assert result['status'] == 'V14_PROGRESS_SCREEN_STOP'
        assert result['final_true_residual'] > .10
        assert result['ksp_create_count'] == result['ksp_solve_count'] == 1
        assert result['ksp_destroy_count'] == 1
        assert result['pc_apply_count'] == 64
        assert result['restart'] == 32
        assert [it for it, _ in checkpoints] == [0, 32, 64]
        assert {row['iteration'] for name, row in records
                if name == 'monitor_residuals.jsonl'} == set(range(0, 65, 8))
        error = action(result['final_solution'])
        try:
            error.axpy(-1, rhs)
            np.testing.assert_allclose(error.norm(), result['final_true_residual'])
        finally:
            error.destroy()
    finally:
        if result is not None:
            result['final_solution'].destroy()
        rhs.destroy()
