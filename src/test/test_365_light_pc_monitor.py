"""R3 actual PETSc monitor lifecycle, H6 counts and bounded input contracts."""
from contextlib import ExitStack
from types import SimpleNamespace
import json
from pathlib import Path

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles, destroy_krylov_result
from src.solvers.physical_safe_monitor import PhysicalSafeMonitor, conservative_stagnation


@pytest.mark.parametrize('nonzero_initial', [False, True])
def test_actual_fgmres_buildsolution_mid_terminal_and_nonzero_second_cycle(nonzero_initial):
    n = 96
    matrix = np.diag(np.geomspace(1., 1e4, n).astype(complex))
    matrix += np.diag(np.full(n-1, .1+.2j), 1)
    rng = np.random.default_rng(365)
    with ExitStack() as owned:
        rhs = PETSc.Vec().createSeq(n); owned.callback(rhs.destroy)
        initial = rhs.duplicate(); owned.callback(initial.destroy)
        rhs.array[:] = rng.normal(size=n)+1j*rng.normal(size=n)
        initial.array[:] = .01*(rng.normal(size=n)+1j*rng.normal(size=n)) if nonzero_initial else 0
        calls = {'pc': 0}
        def action(x):
            out = rhs.duplicate(); out.array[:] = matrix@x.array; return out
        def pc(x):
            calls['pc'] += 1; return x.copy()
        kwargs = dict(max_it=64, residual_limit=1e-30, resource_sample=lambda: {},
                      initial_solution=initial if nonzero_initial else None,
                      start_iteration=0, first_checkpoint_iteration=None, checkpoint_interval=128,
                      ksp_type='fgmres', restart=32, stop_on_true_residual=False)
        baseline = run_fixed_restart_cycles(rhs, action, pc, **kwargs)
        owned.callback(destroy_krylov_result, baseline)
        baseline_pc = calls['pc']; calls['pc'] = 0
        saved, logs, boundary = {}, [], {}
        def save(iteration, vector, relative):
            assert iteration not in saved
            saved[iteration] = (vector.array.copy(), relative)
        monitor = PhysicalSafeMonitor(rhs, action, save, lambda name, row: logs.append((name, row)), lambda: False)
        owned.callback(monitor.destroy)
        def observe(iteration, vector, cycle): boundary[iteration] = vector.array.copy()
        current = run_fixed_restart_cycles(rhs, action, pc, **kwargs,
            iteration_observer=monitor, cycle_observer=observe)
        owned.callback(destroy_krylov_result, current)
        np.testing.assert_array_equal(current['final_solution'].array, baseline['final_solution'].array)
        assert calls['pc'] == baseline_pc == current['pc_apply_count'] == 64
        assert set(saved) == set(range(8, 65, 8))
        for iteration, (vector, relative) in saved.items():
            actual = np.linalg.norm(rhs.array-matrix@vector)/rhs.norm()
            assert abs(actual-relative) <= 1e-12*max(1., actual)
            reported = next(row['reported_relative'] for name, row in logs
                            if name == 'iterations.jsonl' and row['iteration'] == iteration)
            assert abs(actual-reported) <= 1e-10*max(1., actual)
        for iteration in (32, 64):
            np.testing.assert_array_equal(saved[iteration][0], boundary[iteration])
            row = next(row for name, row in logs if name == 'monitor_residuals.jsonl' and row['iteration'] == iteration)
            report = next(row for name, row in logs if name == 'iterations.jsonl' and row['iteration'] == iteration)
            assert row['solution_source'] == ('terminal_vec_sol' if report['terminal'] else 'intermediate_buildSolution')
        reports = [row for name, row in logs if name == 'iterations.jsonl']
        assert len(reports) == 65 and monitor.action_count == 8
        assert reports[-1]['outer_pc_count'] == 64 and reports[-1]['outer_matvec_count'] > 0
        print('PETSc', PETSc.Sys.getVersion(), 'nonzero_initial', nonzero_initial,
              'PC calls', calls['pc'], 'snapshots',
              [(row['iteration'], row['reason'], row['solution_source']) for name, row in logs
               if name == 'monitor_residuals.jsonl'], flush=True)


def test_explicit_snapshot_actions_are_counted_and_hash_bound():
    n = 96
    matrix = np.diag(np.geomspace(1., 1e4, n).astype(complex))
    matrix += np.diag(np.full(n - 1, .1 + .2j), 1)
    rng = np.random.default_rng(36512)
    rhs = PETSc.Vec().createSeq(n)
    try:
        rhs.array[:] = rng.normal(size=n) + 1j * rng.normal(size=n)
        calls = {'action': 0}
        snapshots = {}

        def action(x):
            calls['action'] += 1
            out = rhs.duplicate()
            out.array[:] = matrix @ x.array
            return out

        def observe(iteration, residual, solution):
            snapshots[iteration] = (solution.array.copy(), float(residual))

        result = run_fixed_restart_cycles(
            rhs, action, lambda x: x.copy(), max_it=64,
            residual_limit=1e-30, resource_sample=lambda: {},
            start_iteration=0, first_checkpoint_iteration=None,
            checkpoint_interval=32, ksp_type='fgmres', restart=32,
            stop_on_true_residual=False, explicit_residual_interval=8,
            explicit_residual_observer=observe,
        )
        try:
            assert set(snapshots) == set(range(8, 65, 8))
            assert result['explicit_monitor_residual_count'] == 8
            assert result['explicit_action_count'] == 1 + 2 + 8
            assert calls['action'] == result['matvec_count'] + result['explicit_action_count']
            for iteration, (solution, residual) in snapshots.items():
                actual = np.linalg.norm(rhs.array - matrix @ solution) / rhs.norm()
                assert abs(actual - residual) <= 1e-12 * max(1., actual)
        finally:
            result['final_solution'].destroy()
    finally:
        rhs.destroy()


@pytest.mark.parametrize('joint_mr', [False, True])
def test_actual_h6_pc_counts_and_independent_recount(tmp_path, joint_mr):
    from src.solvers.fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
    from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner
    from src.runners.physical_intermediate import WorkflowLedger
    from benchmarks.physical_intermediate_checker import recompute_positive_apply_counts
    n = 16
    with ExitStack() as owned:
        matrix = PETSc.Mat().createAIJ([n, n], nnz=1); owned.callback(matrix.destroy)
        for i in range(n): matrix.setValue(i, i, 1.+i*.2)
        matrix.assemble()
        seed = matrix.createVecRight(); owned.callback(seed.destroy)
        seed.array[:] = np.arange(n)+1+1j
        h6 = FixedChebyshevJacobiPETSc(matrix, power_seed=seed); owned.callback(h6.destroy)
        rhs = seed.copy(); owned.callback(rhs.destroy); rhs.array[0] = 0
        selected = np.array([1, 4, 7, 10])
        a = np.linspace(1., 4., n)+.1j
        calls = {'a6': 0, 'p4': 0}
        def physical(x, y): calls['a6'] += 1; y.array[:] = a*x.array
        def adjoint(x):
            result = PETSc.Vec().createSeq(4); result.array[:] = x.array[selected]; return result
        def primal(x):
            result = rhs.duplicate(); result.set(0); result.array[selected] = x.array; return result
        def solve(x):
            calls['p4'] += 1
            result = x.copy(); result.array[:] /= a[selected]
            error = np.linalg.norm(a[selected]*result.array-x.array)
            return dict(final_solution=result, diagnostic_only=True, factor_solve_calls=1, explicit_action_count=1,
                        true_residual_norm=error, rhs_norm=x.norm(), final_true_residual=error/x.norm())
        pc = PhysicalIntermediatePreconditioner(SimpleNamespace(apply=physical), h6,
            SimpleNamespace(apply_adjoint=adjoint, apply_primal=primal),
            SimpleNamespace(solver_identity='exact_augmented_A4_reference', solve_intermediate=solve),
            positive_identity='H6', outer_max_it=2048, joint_mr=joint_mr)
        before = h6.matrix_mult_count
        result = pc.apply(rhs); owned.callback(result.destroy)
        assert h6.apply_count == 2 and h6.matrix_mult_count-before == 4
        assert calls == {'a6': 4 if joint_mr else 3, 'p4': 1}
        assert result.array[0] == 0 and np.all(np.isfinite(result.array))
        assert pc.last_apply_facts['formula'].startswith('H6-MR') and pc.audit['outer_max_it'] == 2048
        ledger = WorkflowLedger(tmp_path, tmp_path/'phase.json'); ledger.record_pc(pc.last_apply_facts)
        cycle = dict(cycle_index=0, end_iteration=1, pc_apply_count=1, pc_costs=dict(ledger.pc_counts))
        counts = recompute_positive_apply_counts([pc.last_apply_facts], [cycle])['total']
        assert counts == dict(s6_apply_count=0, s3_apply_count=0, h6_apply_count=2,
                              b6_action_count=4, positive_p1_apply_count=0)
        if joint_mr:
            assert ledger.pc_counts['joint_extra_A6_count']==1
            assert ledger.pc_counts['fine_A6_direction_count']==3
            ledger.cycle(cycle)
            assert not ledger.joint_cycle
            assert (tmp_path/'joint_mr3_first_inputs.jsonl').exists()
            # Replay existing scalar facts, without another physical PC call.
            for i in range(2,34):
                ledger.record_pc(dict(pc.last_apply_facts,apply_count=i))
            assert len(ledger.joint_cycle)==32
            ledger.cycle(dict(cycle_index=1,end_iteration=33,pc_apply_count=32))
            for i in range(34,41):
                ledger.record_pc(dict(pc.last_apply_facts,apply_count=i))
            assert len(ledger.joint_cycle)==7 and ledger.pc_counts['joint_extra_A6_count']==7


@pytest.mark.parametrize('bad', ['none', 'early', 'partial', 'gap', 'improved'])
def test_stagnation_exact_four_completed_cycle_boundaries(bad):
    cycles = [dict(start_iteration=i*32, end_iteration=(i+1)*32, iterations=32,
                   explicit_true_residual=.995**i) for i in range(8)]
    if bad == 'early': cycles.pop()
    elif bad == 'partial': cycles[-1]['iterations'] = 31
    elif bad == 'gap': cycles[-1]['start_iteration'] -= 1
    elif bad == 'improved': cycles[-1]['explicit_true_residual'] *= .98
    assert conservative_stagnation(cycles) == (bad == 'none')


def test_light_dat_and_stop_response_outside_solve(tmp_path):
    from src.io import load_and_resolve
    from src.io.physical_intermediate_profile import LIGHT_PROFILE, profile_facts
    from src.runners.physical_intermediate import WorkflowLedger
    spec = load_and_resolve('input/task39extra/original_13p5nm_p6h10_p6smooth_p4ref_p6smooth.dat')
    assert spec.solver['preconditioner'] == LIGHT_PROFILE
    assert spec.solver['max_iterations'] == 2048
    facts = profile_facts(LIGHT_PROFILE)
    assert facts['resources']['solve_seconds'] == 7200 and facts['resources']['workflow_seconds'] == 10800
    ledger = WorkflowLedger(tmp_path, tmp_path/'phase.json')
    assert 'application_worker' not in json.loads((tmp_path/'phase.json').read_text())
    ledger.defer_performance_stop = True; ledger.stop_signal = 15
    with pytest.raises(InterruptedError): ledger.marker('setup_stop', {})
    ledger.phase = 'solve'; ledger.marker('inside_one_pc', {})
    ledger.phase = 'recovery'
    with pytest.raises(InterruptedError): ledger.marker('recovery_stop', {})
    registered = WorkflowLedger(tmp_path, tmp_path/'registered.json', cooperative_performance_stop=True)
    identity = json.loads((tmp_path/'registered.json').read_text())['application_worker']
    import os
    assert identity['pid'] == os.getpid() and identity['start_ticks'] > 0
    registered.set_phase('solve')
    assert json.loads((tmp_path/'registered.json').read_text())['application_worker'] == identity


@pytest.mark.parametrize('stop', [False, True])
def test_time_or_stop_snapshot_uses_updated_terminal_solution(stop):
    with ExitStack() as owned:
        rhs = PETSc.Vec().createSeq(3); owned.callback(rhs.destroy); rhs.set(1)
        solution = rhs.copy(); owned.callback(solution.destroy); solution.scale(.5)
        now, snapshots, rows = [0.], [], []
        monitor = PhysicalSafeMonitor(rhs, lambda x: x.copy(),
            lambda iteration, x, residual: snapshots.append((iteration, x.array.copy(), residual)),
            lambda name, row: rows.append(row), lambda: stop, clock=lambda: now[0])
        owned.callback(monitor.destroy)
        def invalid_rebuild(*args): raise AssertionError('terminal correction must not be added twice')
        ksp = SimpleNamespace(getConvergedReason=lambda: -3, buildSolution=invalid_rebuild)
        now[0] = 121. if not stop else 1.
        if stop:
            with pytest.raises(InterruptedError): monitor(3, rhs.norm()*.5, ksp, solution, {})
        else:
            monitor(3, rhs.norm()*.5, ksp, solution, {})
        assert len(snapshots) == 1 and snapshots[0][0] == 3 and snapshots[0][2] == .5
        np.testing.assert_array_equal(snapshots[0][1], solution.array)
        assert rows[-1]['solution_source'] == 'terminal_vec_sol'


def test_light_launch_reservation_cache_and_watchdog(tmp_path, monkeypatch):
    from src.io import load_and_resolve
    from src.io.input_loader import InputError
    from src.runners import physical_profile_budget as budget, task038_launcher as launcher
    from benchmarks import subreaper_watchdog
    spec = load_and_resolve('input/task39extra/original_13p5nm_p6h10_p6smooth_p4ref_p6smooth.dat')
    run = tmp_path/'run'; run.mkdir()
    path = tmp_path/'ledger.json'
    previous = dict(kind='R1_profile', status='COMPLETED', elapsed_seconds=1357.)
    path.write_text(json.dumps(dict(limit_seconds=36000, attempts=[previous])))
    monkeypatch.setattr(launcher, '_timestamp_directory', lambda *args: run)
    monkeypatch.setattr(launcher, '_source_sha', lambda *args: 'a'*40)
    monkeypatch.setattr(launcher, '_physical_source_gate', lambda *args: {'source_sha': 'a'*40})
    def supervise(*args, **kwargs):
        reservation = json.loads(path.read_text())['attempts'][-1]
        assert reservation['status'] == 'RESERVED' and reservation['reserved_seconds'] == 10860
        assert 10790 <= kwargs['wall_seconds'] <= 10800 and kwargs['solve_seconds'] == 7200
        assert kwargs['grace_seconds'] == 60 and kwargs['hard_stop_immediate'] is True
        assert kwargs['cooperative_performance_stop'] is True
        assert set(kwargs['worker_environment']) == {'XDG_CACHE_HOME'}
        cache = Path(kwargs['worker_environment']['XDG_CACHE_HOME'])
        assert cache == run/'jit_cache' and not list(cache.iterdir())
        assert json.loads((run/'run_manifest.json').read_text())['execution_cache']['empty_before_launch']
        return dict(leader_exit_code=0, classification='COMPLETED', launch_envelope={},
                    memory_scope='test', job_swap_activity='zero_supported_by_zero_global_activity')
    monkeypatch.setattr(subreaper_watchdog, 'supervise', supervise)
    budget.launch_light_workflow(spec, path)
    assert json.loads(path.read_text())['attempts'][0] == previous
    with pytest.raises(InputError, match='already reserved'): budget.launch_light_workflow(spec, path)
    path.write_text(json.dumps(dict(limit_seconds=36000, attempts=[dict(elapsed_seconds=26000)])))
    with pytest.raises(InputError, match='insufficient cumulative'): budget.launch_light_workflow(spec, path)
