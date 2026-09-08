"""Input and ownership wiring tests without FE assembly or a PDE launch."""

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os

import numpy as np
import pytest

from src.io.input_loader import load_dat_input
from src.io.input_validation import resolve_loaded_input
from src.io.physical_intermediate_profile import profile_facts
from src.solvers import fullspace_same_mesh_hcurl_pmg_setup as setup
from src.solvers.fullspace_physical_intermediate_runtime import (
    release_physical_intermediate_solver_stack,
)


def test_new_dat_preserves_physics_and_exposes_frozen_solver_settings():
    root = Path(__file__).resolve().parents[2]
    old = resolve_loaded_input(load_dat_input(root / 'input/templates/full3d_iterative_example.dat'))
    new = resolve_loaded_input(load_dat_input(root / 'input/task39extra/original_13p5nm_p6h10.dat'))
    assert old.physical_model_sha256 == new.physical_model_sha256 == '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
    assert old.input_sha256 != new.input_sha256
    assert new.as_jsonable()['derived']['physical_intermediate_profile'] == profile_facts()
    assert 'physical_intermediate_profile' not in old.as_jsonable()['derived']
    from src.io.execution_plan import build_execution_plan, dry_run_payload
    assert build_execution_plan(new, '/tmp/not_created', source_sha='a'*40).adapter_available
    assert not build_execution_plan(old, '/tmp/not_created', source_sha='a'*40).adapter_available
    assert dry_run_payload(new)['resolved_method_adapter']['status'] == 'connected'
    assert dry_run_payload(old)['resolved_method_adapter']['status'] == 'unavailable'


def test_profile_matches_actual_numerical_constants():
    from src.solvers import fullspace_physical_intermediate as core

    facts = profile_facts()
    assert facts['identity'] == core.INTERMEDIATE_METHOD
    assert facts['outer']['restart'] == core.OUTER_RESTART
    assert facts['outer']['max_iterations'] == core.OUTER_MAX_IT
    assert facts['intermediate']['restart'] == core.INTERMEDIATE_RESTART
    assert facts['intermediate']['max_iterations'] == core.INTERMEDIATE_MAX_IT
    assert facts['intermediate']['relative_tolerance'] == core.INTERMEDIATE_RESIDUAL_LIMIT
    assert facts['auxiliary']['shift_sigma'] == core.SHIFT_SIGMA
    assert facts['auxiliary']['pre_steps'] == facts['auxiliary']['post_steps'] == core.SMOOTHING_STEPS
    assert facts['resources']['p1_max_rows_each'] == core.LOCAL_FACTOR_MAX_ROWS
    assert facts['resources']['p1_matrix_factor_max_bytes_each'] == core.LOCAL_FACTOR_MAX_BYTES


def test_bounded_setup_audit_never_requires_fake_ksp(monkeypatch):
    monkeypatch.setattr(setup, '_space_layout', lambda value: value)
    monkeypatch.setattr(setup, '_matrix_facts', lambda value: value)
    factor = SimpleNamespace(audit={'allocator': None, 'classification': 'derived'})
    facts = setup.audit_p6_same_mesh_setup(dict(spaces={p: p for p in (6, 4, 3, 2, 1)},
        p1_matrix='p1', p3_matrix='p3', owned_coarse_solver=factor))
    assert facts['schema'] == 'physical-intermediate.positive-s6-setup.v1'
    assert facts['p1_factor'] == factor.audit
    assert facts['shared_mesh_levels'] == [6, 4, 3, 2, 1]


def test_complete_release_both_factors_once_preserves_fine_recovery():
    events = []
    def owned(name):
        return SimpleNamespace(destroy=lambda: events.append(name))
    fine = object()
    bundle = dict(fine=fine, pc=object(), middle=object(),
        shifted_p1_factor=owned('shift_factor'), shifted_p1_matrix=owned('shift_matrix'),
        diagonals={4: owned('diag4'), 2: owned('diag2')},
        positive=dict(upper_cycle=owned('s6'), owned_coarse_solver=owned('positive_factor'),
                      p3_matrix=owned('positive3'), p1_matrix=owned('positive1')))
    release_physical_intermediate_solver_stack(bundle)
    release_physical_intermediate_solver_stack(bundle)
    assert bundle['fine'] is fine and bundle['auxiliary_stack_released']
    assert len(events) == len(set(events)) == 8
    assert events.index('shift_factor') < events.index('shift_matrix')
    assert events.index('s6') < events.index('positive_factor') < events.index('positive1')


def _synthetic_outputs(directory):
    from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
    from src.solvers.hcurl_canonical_vector import canonical_key

    directory.mkdir(exist_ok=True)
    rows = [dict(side=side, m=0, n=0, polarization='s', R=r, T=t, power_ratio=r+t)
            for side, r, t in [('top', .2, 0.), ('bottom', 0., .3)]]
    (directory / 'dtn_port_diffraction_orders_3d.json').write_text(json.dumps({'orders': rows}))
    (directory / 'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps([{'real': .2, 'imag': .1}]*2))
    samples = directory / 'samples.npz'
    np.savez(samples, E_V_per_m=np.ones((1, 1, 1, 3), dtype=complex),
             H_A_per_m=np.ones((1, 1, 1, 3), dtype=complex), x_nm=[0.], y_nm=[0.], z_nm=[1.])
    key = canonical_key(role='full_fe', entity_dimension=1, physical_entity=((0, 0, 0), (1, 0, 0)),
                        entity_local_basis_index=0, orientation_state=('edge', 'canonical'))
    canonical = write_canonical_packet_shard(directory / 'canonical.jsonl', [(key, 1+2j)], audit_packets=True)
    return dict(port_metrics=dict(R_total=.2, T_total=.3, A_balance=.5, dtn_port_mode_count=2),
                volume_metrics=dict(A_volume_total=.5), canonical_vector=canonical,
                field_export=dict(full3d_reference_archive=str(samples),
                                  full3d_reference_archive_sha256=hashlib.sha256(samples.read_bytes()).hexdigest()))


@pytest.mark.parametrize('ending', ['pass', 'breakdown', 'budget', 'timebase'])
@pytest.mark.parametrize('reference', [False, True])
def test_mock_workflow_last_safe_release_recovery_checker_and_terminal_gates(tmp_path, monkeypatch, ending, reference):
    from petsc4py import PETSc
    from benchmarks import physical_intermediate_checker as checker
    from benchmarks import subreaper_watchdog, task038_full3d_jit_staging
    from src.runners import physical_intermediate as runner
    from src.solvers import fullspace_physical_intermediate_runtime as runtime
    from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as physical
    from src.solvers import fullspace_memory_first_krylov as krylov

    root = Path(__file__).resolve().parents[2]
    name = 'original_13p5nm_p6h10_p4_reference.dat' if reference else 'original_13p5nm_p6h10.dat'
    payload = resolve_loaded_input(load_dat_input(root / 'input/task39extra' / name)).as_jsonable()
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PARENT_PID', str(os.getppid()))
    monkeypatch.setenv('PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES', '12000000000')
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PHASE_PATH', str(tmp_path / 'phase.json'))
    events, clock = [], [100.]
    monkeypatch.setattr(runner.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(task038_full3d_jit_staging, 'process_tree_snapshot',
                        lambda *args: dict(all_status_readable=True, rss_bytes=1, swap_bytes=0))
    monkeypatch.setattr(subreaper_watchdog, 'memory_envelope',
                        lambda: dict(effective_available_bytes=10, reserve_bytes=1))
    fine = dict(physical_action=SimpleNamespace(apply_into=lambda source, target: source.copy(target)), mode_sha256='a'*64)
    bundle = dict(fine=fine, positive={}, shifted_p1_factor=SimpleNamespace(audit={}),
                  shifted_p1_matrix_facts={}, jacobi_facts={}, actions={'volume_quadrature_metadata': [{}, {}]})
    if reference:
        bundle.pop('shifted_p1_factor'); bundle.pop('shifted_p1_matrix_facts')
        bundle.update(reference_factor=SimpleNamespace(audit={'diagnostic_only':True}), reference_matrix_facts={})
        bundle['pc'] = SimpleNamespace(apply=lambda rhs:rhs.copy(), last_apply_facts={
            'intermediate':dict(diagnostic_only=True, iterations=0, factor_solve_calls=1,
                explicit_action_count=1, true_residual_norm=0., rhs_norm=1., final_true_residual=0.),
            'wall_seconds':.1, 'direction_facts':[]})
    def build(*args, **kwargs):
        assert kwargs.get('reference', False) == reference
        return bundle
    monkeypatch.setattr(runtime, 'build_physical_intermediate_solver', build)
    monkeypatch.setattr(runtime, 'qualify_physical_intermediate_setup', lambda *args, **kwargs: {})
    monkeypatch.setattr(setup, 'audit_p6_same_mesh_setup', lambda bundle: {})
    def make_rhs(fine):
        rhs = PETSc.Vec().createSeq(3)
        rhs.set(1)
        return rhs, {}
    monkeypatch.setattr(physical, 'build_physical_rhs', make_rhs)
    def solve(rhs, action, pc, **kwargs):
        if reference:
            returned = pc(rhs)
            returned.destroy()
        assert kwargs['restart'] == 32 and kwargs['start_iteration'] == 0
        assert kwargs['max_it'] == 512 and kwargs['checkpoint_interval'] == 128
        solution = rhs.copy()
        cycle = dict(end_iteration=32, explicit_true_residual=0., reported_final_residual=0.)
        kwargs['cycle_observer'](32, solution, cycle)
        if ending in ('budget', 'timebase'):
            clock[0] += 3601
        if ending == 'timebase':
            from src.runners.workflow_timebase import TimebaseInconsistency
            raise TimebaseInconsistency('injected failure with expired workflow')
        return dict(final_solution=solution, final_true_residual=0., cycles=[cycle],
                    reason=-5 if ending == 'breakdown' else 1, iterations=32)
    monkeypatch.setattr(krylov, 'run_fixed_restart_cycles', solve)
    def release(value):
        events.append('release')
        value['auxiliary_stack_released'] = True
    monkeypatch.setattr(runtime, 'release_physical_intermediate_solver_stack', release)
    monkeypatch.setattr(runtime, 'destroy_physical_intermediate_solver', lambda value: events.append('cleanup'))
    def recover(fine, solution, directory, **kwargs):
        assert events[-1] == 'release'
        assert kwargs['export_all_port_modes'] and callable(kwargs['canonical_export'])
        events.append('recovery')
        return _synthetic_outputs(directory)
    monkeypatch.setattr(physical, 'recover_p0_outputs', recover)
    def independent_check(argv, **kwargs):
        events.append('checker')
        checked = checker.check(tmp_path)
        (tmp_path / 'checker.json').write_text(json.dumps(checked))
        return SimpleNamespace(returncode=0 if not checked['gate_failures'] else 2)
    monkeypatch.setattr(runner.subprocess, 'run', independent_check)
    if ending == 'timebase':
        from src.runners.workflow_timebase import TimebaseInconsistency
        with pytest.raises(TimebaseInconsistency):
            runner.run_physical_intermediate(payload, tmp_path, source_sha='a'*40)
        summary = json.loads((tmp_path / 'physical_intermediate_summary.json').read_text())
        assert summary['status'] == 'TIMEBASE_INCONSISTENCY'
        return
    outcome = runner.run_physical_intermediate(payload, tmp_path, source_sha='a'*40)
    assert outcome['passed'] == (ending == 'pass')
    assert events == (['release', 'recovery', 'checker', 'cleanup'] if ending == 'pass'
                      else ['release', 'checker', 'cleanup'])
    safe = json.loads((tmp_path / 'last_safe_checkpoint.json').read_text())
    assert safe['iteration'] == 32 and not safe['regular_128_boundary']
    summary = json.loads((tmp_path / 'physical_intermediate_summary.json').read_text())
    assert summary['reference_authority'] == 'PENDING_A4_not_compared'
    if ending == 'pass':
        if reference:
            assert summary['status'] == 'REFERENCE_ONLY_PASS'
            counts = json.loads((tmp_path/'cycles.jsonl').read_text().splitlines()[0])['pc_costs']
            assert counts['reference_factor_solves'] == counts['inner_explicit_actions'] == 1
        # A real raw-artifact mutation must override the previously passing status.
        with np.load(tmp_path / 'final_residual_arrays.npz') as data:
            arrays = dict(data)
        arrays['action'][0] = np.nan
        np.savez(tmp_path / 'final_residual_arrays.npz', **arrays)
        summary['residual_arrays']['sha256'] = hashlib.sha256((tmp_path / 'final_residual_arrays.npz').read_bytes()).hexdigest()
        (tmp_path / 'physical_intermediate_summary.json').write_text(json.dumps(summary))
        assert checker.check(tmp_path)['classification'] != 'DISCRETE_SOLVER_OUTPUT_PASS'


@pytest.mark.parametrize('failure', ['source_after', 'unresolved_swap', 'full_wall'])
def test_parent_final_verdict_preserves_measured_evidence(tmp_path, monkeypatch, failure):
    from src.io import load_and_resolve
    from src.io.input_loader import InputError
    from src.runners import task038_launcher as launcher
    from benchmarks import subreaper_watchdog

    root = Path(__file__).resolve().parents[2]
    text = (root / 'input/task39extra/original_13p5nm_p6h10.dat').read_text()
    path = tmp_path / 'input.dat'
    path.write_text(text.replace('results_root = "results"', f'results_root = "{tmp_path}/results"'))
    calls, clock = [0], [0.]
    def source_gate(*args):
        calls[0] += 1
        if calls[0] == 2 and failure == 'source_after':
            raise InputError('injected source changed after run')
        return {'source_sha': 'a'*40, 'actual_git_directory': '/qualified/git'}
    monkeypatch.setattr(launcher, '_physical_source_gate', source_gate)
    def supervise(*args, **kwargs):
        if failure == 'full_wall':
            clock[0] = 7201.
        return dict(leader_exit_code=0, classification='COMPLETED', launch_envelope={'launch_cap_bytes': 12_000_000_000},
                    memory_scope='parent and descendants', sampled_process_tree_rss_peak_bytes=1234,
                    job_swap_activity='UNRESOLVED_global_activity_cannot_be_attributed' if failure == 'unresolved_swap'
                    else 'zero_supported_by_zero_global_activity')
    monkeypatch.setattr(subreaper_watchdog, 'supervise', supervise)
    result = launcher.launch_specification(load_and_resolve(path), source_sha='a'*40,
                                          monotonic=lambda: clock[0])
    assert result['result_classification'] == ('PERFORMANCE_CONTROLLED_STOP' if failure == 'full_wall' else 'EVIDENCE_INCOMPLETE')
    manifest = json.loads(Path(result['manifest']).read_text())
    summary = json.loads(Path(result['summary']).read_text())
    assert manifest['status'] == 'finished'
    assert summary['resource_authority']['sampled_process_tree_rss_peak_bytes'] == 1234
    assert manifest['effective_watchdog_authority']['legacy_resource_fields_enforced'] is False
