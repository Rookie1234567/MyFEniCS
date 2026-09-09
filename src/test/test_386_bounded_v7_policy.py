"""Focused V7 contract tests; no FE assembly or formal PDE."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_balanced_profile import (
    BOUNDED_ENTITY_PROFILE,
    BOUNDED_PROFILES,
    BOUNDED_PROJECTED_PROFILE,
)
from src.io.physical_intermediate_profile import profile_facts


def test_v7_dat_and_profile_contract_is_single_source_of_truth():
    for identity in BOUNDED_PROFILES:
        specification = load_and_resolve(
            Path('input/task39extra') / f'original_13p5nm_p6h10_{identity}.dat')
        facts = profile_facts(identity)
        assert specification.solver['preconditioner'] == identity
        assert facts['intermediate']['restart'] == 16
        assert facts['intermediate']['max_iterations'] == 16
        assert facts['intermediate']['seconds'] == 30
        assert facts['intermediate']['safe_return_seconds'] == 25
        assert facts['fine_auxiliary']['calls_per_PC'] == dict(I4=2, H6=1)
        assert facts['resources']['reference_p4_factors'] == 0
        assert facts['storage']['p4_global_aij'] == 0
    assert profile_facts(BOUNDED_PROJECTED_PROFILE)['route_b']['status'] == 'registered_not_implemented'
    assert profile_facts(BOUNDED_ENTITY_PROFILE)['route'] == 'ENTITY16'


class _Vector:
    def __init__(self, value):
        self.array = np.asarray(value, dtype=complex).copy()
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def _fake_result(status='INNER_APPROXIMATE_RETURN', timeout=False, legal=1):
    return dict(
        solution=_Vector([1]), applied=_Vector([1]), residual=_Vector([0]),
        facts=dict(status=status, iterations=16, seconds=31.0 if timeout else 4.0,
                   actual_elapsed_seconds=31.0 if timeout else 4.0,
                   final_true_residual=.2, legal_direction_count=legal,
                   timeout_exceeded=timeout, stop_reason='I4_HARD_TIME_EXCEEDED' if timeout else 'MAX_IT'))


def test_v7_admission_is_thin_and_zero_does_not_reset_timeout_streak(monkeypatch):
    from src.solvers import physical_bounded_policy as policy

    calls = []
    sequence = iter([_fake_result(timeout=True), _fake_result(status='INNER_ZERO_RHS', timeout=False, legal=0),
                     _fake_result(timeout=True), _fake_result(timeout=True)])

    def fake_solver(rhs, action, pc, **kwargs):
        calls.append(kwargs)
        return next(sequence)

    saved = []
    monkeypatch.setattr(policy, 'solve_physical_i4', fake_solver)
    admission = policy.BoundedI4Admission(lambda x: x, lambda x: x,
        sample=lambda: None, save=lambda name, facts: saved.append((name, facts)),
        stop_requested=lambda: False)
    rhs = _Vector([2])
    admission(rhs)
    admission(rhs)
    admission(rhs)
    with pytest.raises(policy.BoundedI4CostBlocked):
        admission(rhs)
    assert len(calls) == 4
    assert all(kwargs['max_it'] == kwargs['restart'] == 16 for kwargs in calls)
    assert all(kwargs['soft_seconds'] == 25 and kwargs['hard_seconds'] == 30 for kwargs in calls)
    assert all(kwargs['v7_policy'] and kwargs['target'] == 1e-4 for kwargs in calls)
    assert admission.timeout_streak == 3
    assert not hasattr(admission, 'scalar_history')
    assert saved and saved[-1][0] == 'bounded_i4_cost_blocked'


def test_bounded_projected_registration_fails_closed_before_formal_setup():
    from src.solvers.physical_bounded_runtime import build_formal_bounded

    ledger = SimpleNamespace(marker=lambda *_: None)
    with pytest.raises(ValueError, match='route B is not implemented'):
        build_formal_bounded(SimpleNamespace(), None,
            profile_facts(BOUNDED_PROJECTED_PROFILE), sample=lambda: None,
            ledger=ledger, directory=Path('.'), identity=BOUNDED_PROJECTED_PROFILE,
            save=lambda *_: None, append=lambda *_: None, stop_requested=lambda: False)


def test_v7_outer_screen_seeds_zero_and_checks_non8_mid_boundary():
    from src.solvers.physical_balanced_fgmres import BoundedScreen

    screen = BoundedScreen()
    assert screen.inspect(0, 1.0, 0.0) is None
    assert screen.inspect(8, .70, 100.0) is None
    decision = screen.inspect(16, .20, 1800.0)
    assert decision['passed'] and decision['status'] == 'SCREEN_CONTINUE_SAME_LIVE_KSP'
    assert decision['checkpoints'] == [(0, 1.0), (8, .70), (16, .20)]

    screen = BoundedScreen()
    assert screen.inspect_mid_budget(19, .2, 5399.0) is None
    mid = screen.inspect_mid_budget(19, .2, 5400.0)
    assert mid['status'] == 'PROGRESS_INSUFFICIENT_AT_MID_BUDGET'
    assert screen.inspect_mid_budget(20, .9, 5401.0) is mid

    screen = BoundedScreen()
    assert screen.inspect_mid_budget(19, .0005, 5400.0) is not None
    assert screen.mid_budget['passed']


def test_v7_batch_charges_one_outer_dual_clock_for_setup_and_failure(monkeypatch, tmp_path):
    from src.runners import physical_bounded_budget as budget_module

    specification = load_and_resolve(
        Path('input/task39extra/original_13p5nm_p6h10_bounded_entity16_v7.dat'))
    path = tmp_path / 'budget.json'
    path.write_text(json.dumps(dict(
        schema=budget_module.SCHEMA,
        limit_seconds=budget_module.LIMIT_SECONDS,
        attempts=[
            dict(kind='setup', status='COMPLETED', elapsed_seconds=11.0),
            dict(kind='controls', status='COMPLETED', elapsed_seconds=7.0),
            dict(kind='focused_test', status='FAILED', elapsed_seconds=3.0),
            dict(kind='recovery', status='COMPLETED', elapsed_seconds=5.0),
        ])))
    samples = iter([
        dict(monotonic=10.0, boottime=20.0, utc_ns=100_000_000_000),
        dict(monotonic=12.0, boottime=22.0, utc_ns=102_000_000_000),
    ])
    monkeypatch.setattr(budget_module, 'clock_sample', lambda: next(samples))
    monkeypatch.setattr(
        'src.runners.task038_launcher.launch_specification',
        lambda _spec: dict(result_classification='worker_exit0'),
    )

    result = budget_module.launch_bounded_workflow(specification, path)
    assert result['result_classification'] == 'worker_exit0'
    budget = json.loads(path.read_text())
    entry = budget['attempts'][-1]
    assert entry['elapsed_seconds'] == pytest.approx(2.0)
    assert budget['charged_seconds'] == pytest.approx(28.0)
    assert budget['remaining_seconds'] == pytest.approx(43172.0)
    assert entry['nested_intervals_not_added']


def test_v7_failed_launch_is_charged_and_route_b_is_rejected(monkeypatch, tmp_path):
    from src.runners import physical_bounded_budget as budget_module

    specification = load_and_resolve(
        Path('input/task39extra/original_13p5nm_p6h10_bounded_entity16_v7.dat'))
    path = tmp_path / 'budget.json'
    path.write_text(json.dumps(dict(schema=budget_module.SCHEMA,
                                    limit_seconds=budget_module.LIMIT_SECONDS,
                                    attempts=[])))
    samples = iter([
        dict(monotonic=30.0, boottime=40.0, utc_ns=300_000_000_000),
        dict(monotonic=34.0, boottime=44.0, utc_ns=304_000_000_000),
    ])
    monkeypatch.setattr(budget_module, 'clock_sample', lambda: next(samples))

    def fail(_spec):
        raise RuntimeError('controlled fixture failure')

    monkeypatch.setattr('src.runners.task038_launcher.launch_specification', fail)
    with pytest.raises(RuntimeError, match='controlled fixture failure'):
        budget_module.launch_bounded_workflow(specification, path)
    budget = json.loads(path.read_text())
    assert budget['attempts'][-1]['status'] == 'FAILED'
    assert budget['attempts'][-1]['elapsed_seconds'] == pytest.approx(4.0)
    assert budget['charged_seconds'] == pytest.approx(4.0)

    projected = load_and_resolve(
        Path('input/task39extra/original_13p5nm_p6h10_bounded_projected_seq2_16_v7.dat'))
    with pytest.raises(InputError, match='route B is not implemented'):
        budget_module.launch_bounded_workflow(projected, path)

    notch = load_and_resolve(
        Path('input/task39extra/nonseparable_13p5nm_p6h10_bounded_entity16_v7.dat'))
    empty_path = tmp_path / 'empty-budget.json'
    empty_path.write_text(json.dumps(dict(schema=budget_module.SCHEMA,
                                          limit_seconds=budget_module.LIMIT_SECONDS,
                                          attempts=[])))
    with pytest.raises(InputError, match='qualified route-A original first'):
        budget_module.launch_bounded_workflow(notch, empty_path)


def test_v7_shared_i4_truncation_and_eps_difference_petsc_fixture():
    """Use the real shared PETSc KSP on two fresh, constrained RHS vectors."""
    from petsc4py import PETSc
    from src.solvers.physical_recursive_coarse import solve_physical_i4

    n = 40
    slaves = np.array([0, 7], dtype=np.int32)
    diagonal = np.geomspace(.2, 9.0, n) * (1.0 + .17j)
    vectors = []

    def own(value):
        vectors.append(value)
        return value

    def action(value):
        output = own(value.duplicate())
        output.array[:] = diagonal * value.array
        return output

    def precondition(value):
        output = own(value.duplicate())
        output.array[:] = value.array
        output.array[slaves] = 0
        return output

    rhs = own(PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF))
    rhs.array[:] = np.arange(n) + 1j*np.arange(1, n + 1)
    rhs.array[slaves] = 0
    rhs_before = rhs.array.copy()
    saved = []

    def run(current_rhs):
        result = solve_physical_i4(
            current_rhs, action, precondition, target=1e-4,
            sample=lambda: None, save=lambda name, facts: saved.append((name, facts)),
            clock=lambda: 0.0, residual_action=action, max_it=16, restart=16,
            soft_seconds=25, hard_seconds=30, v7_policy=True)
        for name in ('solution', 'applied', 'residual'):
            vectors.append(result[name])
        return result

    try:
        first = run(rhs)
        assert first['facts']['status'] == 'INNER_APPROXIMATE_RETURN'
        assert first['facts']['iterations'] <= 16
        assert first['facts']['final_true_residual'] > 1e-4
        np.testing.assert_array_equal(rhs.array, rhs_before)
        assert np.all(first['solution'].array[slaves] == 0)

        a_c1 = own(action(first['solution']))
        s = own(rhs.copy())
        s.axpy(-1, a_c1)
        g2 = own(action(s))
        g2_before = g2.array.copy()
        second = run(g2)
        np.testing.assert_array_equal(g2.array, g2_before)
        assert not np.array_equal(g2.array, rhs_before)
        assert np.all(second['solution'].array[slaves] == 0)

        z = own(first['solution'].copy())
        z.axpy(1, s)
        z.axpy(-1, second['solution'])
        az = own(action(z))
        actual = own(rhs.copy())
        actual.axpy(-1, az)
        expected = own(first['residual'].copy())
        expected.axpy(-1, second['residual'])
        np.testing.assert_allclose(actual.array, expected.array, rtol=1e-11, atol=1e-11)
        assert np.all(z.array[slaves] == 0)
        assert saved == []
    finally:
        seen = set()
        for value in reversed(vectors):
            if id(value) not in seen:
                seen.add(id(value))
                value.destroy()
