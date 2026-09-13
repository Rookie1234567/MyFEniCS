"""Independent readers must retain negative resource and measured-time evidence."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from src.io.physical_intermediate_profile import SCHUR_PROFILE
from src.runners.physical_p4_schur_v14 import (
    _v14_history_facts, _v14_resource_facts, _v14_physical_checks, _v14_predecessor_gate,
)


def _resource_row(**changes):
    return dict(
        rss_bytes=600, pss_bytes=500, swap_bytes=0,
        all_status_readable=True, pss_all_readable=True,
        launch_cap_bytes=1000, inventory_memory_cap_bytes=200,
        inventory_used_bytes=20, inventory_peak_bytes=30,
        workspace_live_bytes=20, workspace_peak_bytes=30,
        memory_envelope=dict(effective_available_bytes=400, reserve_bytes=300),
        timestamp_ns=1, label='synthetic', **changes)


def test_resource_reader_streams_and_does_not_let_zero_swap_hide_rss_failure(tmp_path, monkeypatch):
    path = tmp_path/'resources.jsonl'
    second = _resource_row()
    second.update(rss_bytes=1100, pss_bytes=None, pss_all_readable=False)
    path.write_text('\n'.join(map(json.dumps, [_resource_row(), second]))+'\n')
    monkeypatch.setattr(Path, 'read_text', lambda *_args, **_kw: (_ for _ in ()).throw(
        AssertionError('resource reader must stream the trace')))
    result = _v14_resource_facts(SimpleNamespace(resources_path=path, workspace_cap=100))
    assert result['zero_swap'] and not result['gate']
    assert result['rss_peak_bytes'] == 1100
    assert result['first_failed_sample']['line'] == 2
    assert not result['first_failed_sample']['checks']['rss']
    assert not result['pss_all_readable']
    assert not result['final_parent_cleanup_included']


def test_truncated_resource_tail_preserves_prefix_and_cannot_pass(tmp_path):
    path = tmp_path/'resources.jsonl'
    path.write_text(json.dumps(_resource_row())+'\n\0\0\n')
    result = _v14_resource_facts(SimpleNamespace(resources_path=path, workspace_cap=100))
    assert result['status'] == 'READ_ERROR' and not result['gate']
    assert result['sample_count'] == 1 and result['failed_line'] == 2
    assert result['rss_peak_bytes'] == 600


def test_history_includes_v12_and_nearest_actual_node_beyond_step64(tmp_path):
    def binding(name, content):
        path = tmp_path/name
        path.write_text(content)
        return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    v5_nodes = [dict(iteration=i, solve_seconds=t, explicit_true_residual=r)
                for i, t, r in ((32, 10., .5), (64, 20., .25), (96, 35., .1))]
    v12_nodes = [dict(iteration=i, elapsed_seconds_conservative=t,
                      elapsed_seconds_monotonic=t-1, true_residual=r)
                 for i, t, r in ((8, 11., .9), (32, 30., .8), (64, 60., .7))]
    cases = [
        dict(label='V5', source_sha='a'*40, physical_model_sha256='physical',
             mode_sha256='mode', raw_binding=binding('v5.jsonl', '\n'.join(map(json.dumps, v5_nodes)))),
        dict(label='V12', source_sha='b'*40, physical_model_sha256='physical',
             operator_identity={'mode_sha256': 'mode'},
             source_record=binding('v12.json', json.dumps({'candidates': [{'node_records': v12_nodes}]}))),
    ]
    history = tmp_path/'benchmarks/artifacts/task39extra/p4_schur_v14/root_engineering/frozen_history.json'
    history.parent.mkdir(parents=True)
    history.write_text(json.dumps({'cases': cases}))
    current = dict(iterations=64, final_true_residual=.1, snapshots=[
        dict(iteration=32, solve_seconds=34., explicit_true_residual=.2),
        dict(iteration=64, solve_seconds=65., explicit_true_residual=.1)])
    result = _v14_history_facts(tmp_path, {'fine': {'mode_sha256': 'mode'}}, current,
                                notch=False, physical_sha256='physical')
    assert result['status'] == 'AVAILABLE'
    v5, v12 = result['same_identity_cases']
    assert v5['nearest_time_nodes'][0]['historical']['iteration'] == 96
    assert v12['required_32_64_nodes']['32']['explicit_true_residual'] == .8
    assert v12['required_32_64_nodes']['64']['monotonic_seconds'] == 59.
    assert not v12['nearest_time_nodes'][-1]['requested_time_inside_measured_range']
    (tmp_path/'v5.jsonl').write_text('changed')
    changed = _v14_history_facts(tmp_path, {'fine': {'mode_sha256': 'mode'}}, current,
                                 notch=False, physical_sha256='physical')
    assert changed['status'] == 'READ_ERROR'


def _physical_evidence():
    solver = dict(final_true_residual=1e-7, elapsed_seconds=100., restart=32,
                  max_it=2048, zero_start=True, ksp_create_count=1, ksp_solve_count=1)
    field = {name: dict(absolute_error_norm=1e-6, reference_norm=1., relative=0.)
             for name in ('L2', 'scaled_curl')}
    power = dict(R=.3, T=.4, A=.3, A_volume=.3)
    comparison = dict(current=dict(power), reference=dict(power),
        modal=dict(mode_count=80, amplitude_relative_difference=1e-6,
                   power_max_absolute_difference=1e-8, phase_fitting=False),
        finite={name: True for name in ('electric_finite', 'magnetic_finite',
                                        'auxiliary_finite', 'curl_postprocess_success')},
        selected_field=dict(
            coordinates={name: {'exact': True} for name in ('x_nm', 'y_nm', 'z_nm', 'interface_z_nm')},
            differences={name: dict(relative=1e-6, max_absolute=1e-6, reference_norm=1.)
                         for name in ('E_V_per_m', 'H_A_per_m', 'E_t_interface_V_per_m', 'H_t_interface_A_per_m')}))
    return solver, field, comparison


def test_physical_checker_recomputes_norm_and_power_instead_of_trusting_cached_pass():
    solver, field, comparison = _physical_evidence()
    assert all(_v14_physical_checks(solver, field, comparison).values())
    field['L2']['absolute_error_norm'] = 2e-4  # Cached relative remains zero.
    comparison['current']['A_volume'] += 3e-5
    checks = _v14_physical_checks(solver, field, comparison)
    assert not checks['L2'] and not checks['A_volume']
    assert not checks['energy_conservation'] and not checks['absorption_consistency']


def _predecessor_fixture(tmp_path):
    source = 'a'*40
    original = '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
    notch = '7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec'
    mode = 'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2'
    run = tmp_path/'original'
    (run/'watchdog').mkdir(parents=True)
    def write(name, data):
        path = run/name
        path.write_text(json.dumps(data))
        return hashlib.sha256(path.read_bytes()).hexdigest()
    solver, field, comparison = _physical_evidence()
    worker = dict(stage='Q4_ORIGINAL', source_sha=source, solver=solver,
                  field=field, comparison=comparison, stage_pass=True, official_result=True,
                  final_explicit_relative_residual=1e-7,
                  gates={'solve_clock_interval': {'budget_seconds': 101.}},
                  operator_identity={'ordered_mode_sha256': mode})
    clean_source = dict(source_sha=source, tracked_and_nonignored_untracked_clean=True)
    swap = dict(pswpin_pages=0, pswpout_pages=0)
    watchdog = dict(source_state=clean_source, classification='COMPLETED', leader_exit_code=0,
                    descendants_cleared=True, remaining_child_pids=[],
                    sampled_process_tree_swap_peak_bytes=0, sampled_process_tree_rss_peak_bytes=600,
                    global_swap_activity={'baseline': swap, 'delta': swap})
    resolved = dict(solver={'stage': 'Q4_ORIGINAL', 'preconditioner': SCHUR_PROFILE},
                    provenance={'input_sha256': 'b'*64, 'physical_model_sha256': original})
    manifest = dict(status='finished', source_sha=source, source_after=clean_source,
                    solver=resolved['solver'], input_sha256='b'*64,
                    physical_model_sha256=original,
                    resolved_config_sha256=write('resolved_config.json', resolved))
    parent = dict(status='finished', exit_status=0, result_classification='worker_exit0',
                  job_swap_qualification='qualified_zero', workflow_clock_interval={'budget_seconds': 10.})
    row = _resource_row()
    write('physical_p4_schur_v14_summary.json', worker)
    write('run_manifest.json', manifest)
    write('run_summary.json', parent)
    write('watchdog/summary.json', watchdog)
    write('watchdog/resources.jsonl', dict(row, global_swap_pages=swap))
    write('v14_worker_resources.jsonl', row)
    ledger = tmp_path/'ledger.json'
    ledger.write_text(json.dumps({'batch_identity': 'review_v14', 'stages': {'Q4_ORIGINAL': {
        'active_attempt': None, 'attempts': [dict(source_sha=source, run_directory=str(run),
                                                 settled_seconds=10., reserved_seconds=14400.)]}}}))
    runtime = SimpleNamespace(_ledger_path=ledger)
    current = {'provenance': {'physical_model_sha256': notch}}
    def gate():
        return _v14_predecessor_gate(runtime, 'Q5_NOTCH', resolved_payload=current)
    return worker, write, gate


def test_notch_predecessor_requires_final_parent_samples_and_real_physical_values(tmp_path):
    worker, write, gate = _predecessor_fixture(tmp_path)
    comparison = worker['comparison']
    assert gate()['qualified']
    worker['final_explicit_relative_residual'] = 2e-6
    write('physical_p4_schur_v14_summary.json', worker)
    assert not gate()['qualified']  # KSP residual alone cannot authorize notch.
    worker['final_explicit_relative_residual'] = 1e-7
    comparison['current']['A_volume'] += 1e-3  # PASS booleans stay true.
    write('physical_p4_schur_v14_summary.json', worker)
    assert not gate()['qualified']
    comparison['current']['A_volume'] -= 1e-3
    write('physical_p4_schur_v14_summary.json', worker)
    row = _resource_row()
    write('watchdog/resources.jsonl', dict(row, rss_bytes=1100,
                                          global_swap_pages=dict(pswpin_pages=0, pswpout_pages=0)))
    assert not gate()['qualified']  # A stale COMPLETED summary cannot hide a bad trace.


def test_settled_checker_uses_each_attempt_policy_for_overrun_qualification(tmp_path):
    worker, write, gate = _predecessor_fixture(tmp_path)
    run = tmp_path / 'original'
    worker['time_policy'] = 'observe_only'
    worker['solver']['elapsed_seconds'] = 10801.0
    worker['gates']['solve_clock_interval']['budget_seconds'] = 10801.0
    manifest = json.loads((run / 'run_manifest.json').read_text())
    manifest['v14_time_policy'] = 'observe_only'
    parent = json.loads((run / 'run_summary.json').read_text())
    parent['time_policy'] = 'observe_only'
    parent['workflow_clock_interval']['budget_seconds'] = 14401.0
    watchdog = json.loads((run / 'watchdog/summary.json').read_text())
    watchdog['time_policy'] = 'observe_only'
    write('physical_p4_schur_v14_summary.json', worker)
    write('run_manifest.json', manifest)
    write('run_summary.json', parent)
    write('watchdog/summary.json', watchdog)
    ledger = json.loads((tmp_path / 'ledger.json').read_text())
    ledger['stages']['Q4_ORIGINAL']['attempts'][0].update(
        time_policy='observe_only', settled_seconds=14401.0,
        reservation_exceeded_seconds=1.0
    )
    (tmp_path / 'ledger.json').write_text(json.dumps(ledger))
    result = gate()
    assert result['qualified']
    assert result['time_policy'] == 'observe_only'
    assert not result['time_observations']['settled_within_reservation']
    assert result['checks']['full_solve_clock']
    worker['time_policy'] = 'enforce'
    write('physical_p4_schur_v14_summary.json', worker)
    assert not gate()['qualified']


def test_original_admission_recomputes_three_rhs_and_actual_balanced_work(tmp_path):
    from copy import deepcopy
    from src.runners.physical_p4_schur_v14 import _Q1_Q2_RHS

    worker, write, _ = _predecessor_fixture(tmp_path)
    run = tmp_path/'original'
    required = 'Q3_INTERFACE_CONTROL'
    worker.update(stage=required, official_result=False,
                  delta={'current_ordered_mode_sha256': worker['operator_identity']['ordered_mode_sha256']},
                  lifecycle={'internal_factor_count': 42})
    phases = {name: [1]*42 for name in ('reduce', 'S1', 'S2', 'recover')}
    interface = dict(factor_solve_delta=[4]*42, local_patch_solve_delta=[2]*42,
        local_patch_apply_count=84, local_smoother_apply_count=2, coarse_solve_count=1,
        ksp_created=False, inner_iteration_count=0, reference_used=False,
        operation_counts=dict(route=['reduce', 'J1', 'S1', 'E1', 'S2', 'J2', 'recover'],
                              schur_action_count=2, local_action_count=2,
                              factor_solve_delta_by_phase=phases))
    worker['solve_records'] = [dict(
        stem=item['stem'], elapsed_seconds=10., fint_apply_count_delta=1,
        native_A4_residual_decomposition={'total_absolute_norm': .1, 'rhs_norm': 1.},
        field_metrics={'fields': deepcopy(worker['field'])}, interface_facts=deepcopy(interface))
        for item in _Q1_Q2_RHS]
    worker['balanced_p6_audit'] = dict(
        completed=True, q_bridge_relative=1e-12, fint_apply_delta=2, h6_apply_delta=1,
        native_A4_action_count=2,
        pc_counts=dict(C=2, smoother=1, A_structure=2, A_inner_true=0, PH_audit=0),
        coarse_calls=[{'interface_facts': deepcopy(interface)} for _ in range(2)],
        closure={'closure_norm': 1e-10, 'operation_scale': 1., 'actual_defect_norm': .5})
    resolved = json.loads((run/'resolved_config.json').read_text())
    resolved['solver']['stage'] = required
    manifest = json.loads((run/'run_manifest.json').read_text())
    manifest['solver']['stage'] = required
    manifest['resolved_config_sha256'] = write('resolved_config.json', resolved)
    write('run_manifest.json', manifest)
    write('physical_p4_schur_v14_summary.json', worker)
    ledger_path = tmp_path/'ledger.json'
    ledger = json.loads(ledger_path.read_text())
    ledger['stages'][required] = ledger['stages'].pop('Q4_ORIGINAL')
    ledger_path.write_text(json.dumps(ledger))
    def gate():
        return _v14_predecessor_gate(SimpleNamespace(_ledger_path=ledger_path), 'Q4_ORIGINAL',
            resolved_payload={'provenance': {'physical_model_sha256': manifest['physical_model_sha256']}})
    assert gate()['qualified']  # Diagnostic Q3 need not claim official physical outputs.
    row = worker['solve_records'][1]
    row['native_A4_residual_decomposition']['total_absolute_norm'] = .21
    write('physical_p4_schur_v14_summary.json', worker)
    assert not gate()['qualified']  # Frozen feedback RHS has the tighter .2 limit.
    row['native_A4_residual_decomposition']['total_absolute_norm'] = .1
    worker['balanced_p6_audit']['coarse_calls'][1]['interface_facts']['factor_solve_delta'][0] = 5
    write('physical_p4_schur_v14_summary.json', worker)
    assert not gate()['qualified']  # A cached stage_pass cannot hide excess inner work.
