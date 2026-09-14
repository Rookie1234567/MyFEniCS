"""Native profile wiring, V5 preservation and unchanged screen criteria."""
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import profile_facts
from src.io.run_specification import thaw
from src.solvers.physical_balanced_fgmres import BalancedScreen

INPUT = Path('input/task39extra_para_workstation_capacity/original_13p5nm_p6h10.dat')
NATIVE_INPUT = Path('input/task39extra_para_workstation_capacity/nonseparable_13p5nm_p6h10.dat')
REFERENCE_INPUT = Path('input/task39extra_para_workstation_capacity/original_13p5nm_native_matched_reference.dat')
FIVE_NM_INPUT = Path('input/task39extra_para_workstation_capacity/original_5nm_si_p6h4_native.dat')
TWO_NM_INPUT = Path('input/task39extra_para_workstation_capacity/original_2nm_si_p6h1p5_native.dat')
TWO_NM_H2_INPUT = Path('input/task39extra_para_workstation_capacity/original_2nm_si_p6h2_native.dat')


def test_native_matched_reference_is_explicit_and_hash_bound():
    reference = load_and_resolve(REFERENCE_INPUT)
    ordinary = load_and_resolve('input/task39extra/original_13p5nm_p6h10_fine_reference.dat')
    assert reference.solver['direct_solver_profile'] == 'native_matched_reference'
    assert reference.execution['timeout_seconds'] == 21600
    assert reference.execution['native_memory_policy'] == 'membind_node1'
    assert reference.output['top_probe_z_nm'] == 127.5
    assert reference.output['bottom_probe_z_nm'] == -7.5
    assert ordinary.solver['direct_solver_profile'] == 'default'
    assert ordinary.execution['timeout_seconds'] == 1800
    from src.runners.fine_reference_preflight import load_reference_witness
    with pytest.raises(ValueError, match='audit hash mismatch'):
        load_reference_witness(Path(reference.solver['reference_witness_path']), '0' * 64)


def test_native_real_modes_preserve_historical_identity(tmp_path):
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.native_mode_identity import WSL_MODE_SHA, qualify_native_modes
    cfg = simulation_config_3d_from_normalized(load_and_resolve(INPUT).as_jsonable())
    bridge, encoded = qualify_native_modes(cfg)
    assert bridge['reference_sha256'] == WSL_MODE_SHA
    assert bridge['maximum_relative_difference'] <= 1e-10
    assert len(json.loads(encoded)['modes']) == 80


def test_native_5nm_modes_bind_to_current_input_inventory():
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.native_mode_identity import qualify_native_modes
    cfg = simulation_config_3d_from_normalized(load_and_resolve(FIVE_NM_INPUT).as_jsonable())
    bridge, encoded = qualify_native_modes(cfg)
    payload = json.loads(encoded)
    assert bridge['status'] == 'CURRENT_NATIVE_MODE_INVENTORY_PASS'
    assert bridge['wavelength_nm'] == 5.0
    assert bridge['mode_count'] == len(payload['modes']) == 600
    assert bridge['reference_sha256'] is None
    assert bridge['native_sha256'] == __import__('hashlib').sha256(encoded).hexdigest()


@pytest.mark.parametrize('change', ['order', 'polarization', 'power', 'nonfinite'])
def test_native_mode_bridge_rejects_changed_physics(change):
    from src.solvers.native_mode_identity import REFERENCE, compare_mode_manifest
    data = json.loads(REFERENCE.read_bytes())
    if change == 'order':
        data['modes'][0], data['modes'][1] = data['modes'][1], data['modes'][0]
    elif change == 'polarization':
        data['modes'][0]['polarization'] = 'p'
    elif change == 'power':
        data['modes'][0]['power_per_unit_amplitude'] *= 1.001
    else:
        data['modes'][0]['alpha']['real'] = float('nan')
    with pytest.raises(ValueError):
        compare_mode_manifest(json.dumps(data).encode())


def test_native_v5_math_and_physical_identity():
    original = load_and_resolve('input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat')
    native = load_and_resolve(INPUT)
    assert original.physical_model_sha256 == native.physical_model_sha256
    old = profile_facts('balanced_h6_p4_v5')
    new = profile_facts(native.solver['preconditioner'])
    assert thaw(native.derived['physical_intermediate_profile']) == new
    for key in ('balanced', 'fine_auxiliary', 'intermediate', 'structural_calls'):
        assert new[key] == old[key]
    assert new['outer']['restart'] == old['outer']['restart'] == 32
    assert new['outer']['max_iterations'] == old['outer']['max_iterations'] == 2048
    assert new['outer']['initial_guess'] == old['outer']['initial_guess'] == 'zero'
    assert new['outer']['screen']['iterations'] == old['outer']['screen']['iterations'] == 128
    assert new['outer']['screen']['solve_seconds'] == 7200
    assert old['resources']['solve_seconds'] == 7200
    assert new['resources']['solve_seconds'] == 43200
    assert new['resources']['workflow_seconds'] == 64800


def test_native_5nm_si_no_deadline_opt_in_preserves_non_time_gates():
    specification = load_and_resolve(FIVE_NM_INPUT)
    profile = profile_facts(specification.solver['preconditioner'])
    assert specification.incidence['wavelength_nm'] == 5.0
    assert specification.materials['substrate_name'] == 'Si / silicon'
    assert specification.materials['grating_name'] == 'Si / silicon'
    assert tuple(specification.materials['n_substrate']) == (0.99396854453, 0.00435380777)
    assert tuple(specification.materials['n_grating']) == (0.99396854453, 0.00435380777)
    assert specification.discretization['mesh_target_nm'] == 4.0
    assert specification.execution['time_limit_mode'] == 'none'
    assert specification.execution['timeout_seconds'] is None
    assert profile['resources']['solve_seconds'] is None
    assert profile['resources']['workflow_seconds'] is None
    assert profile['resources']['batch_limit_seconds'] is None
    assert profile['outer']['screen']['iterations'] == 128
    assert profile['outer']['screen']['solve_seconds'] is None
    assert profile['outer']['max_iterations'] == 2048
    assert profile['outer']['restart'] == 32
    assert profile['outer']['initial_guess'] == 'zero'


@pytest.mark.parametrize(
    ('path', 'mesh_target'),
    [(TWO_NM_INPUT, 1.5), (TWO_NM_H2_INPUT, 2.0)],
)
def test_native_2nm_si_no_deadline_profiles_are_explicit(path, mesh_target):
    specification = load_and_resolve(path)
    profile = profile_facts(specification.solver['preconditioner'])
    assert specification.incidence['wavelength_nm'] == 2.0
    assert specification.materials['substrate_name'] == 'Si / silicon'
    assert specification.materials['grating_name'] == 'Si / silicon'
    assert tuple(specification.materials['n_substrate']) == (0.99880148307, 0.000213688647)
    assert tuple(specification.materials['n_grating']) == (0.99880148307, 0.000213688647)
    assert specification.discretization['mesh_target_nm'] == mesh_target
    assert specification.execution['time_limit_mode'] == 'none'
    assert specification.execution['timeout_seconds'] is None
    assert profile['resources']['solve_seconds'] is None
    assert profile['resources']['workflow_seconds'] is None
    assert profile['resources']['batch_limit_seconds'] is None
    assert profile['outer']['screen']['iterations'] == 128
    assert profile['outer']['screen']['solve_seconds'] is None
    assert profile['outer']['max_iterations'] == 2048
    assert profile['outer']['restart'] == 32
    assert profile['outer']['initial_guess'] == 'zero'


def test_no_deadline_screen_still_enforces_iteration_gate():
    screen = BalancedScreen(None)
    assert screen.inspect(127, 1.0, 10**12) is None
    decision = screen.inspect(128, 1.0e-2, 10**12)
    assert decision['status'] == 'SCREEN_CONTINUE_SAME_LIVE_KSP'
    assert decision['iteration'] == 128


def test_checker_no_deadline_screen_still_uses_iteration_not_time():
    from benchmarks.physical_intermediate_checker import recompute_balanced_screen

    rows = [
        {'iteration': 31, 'explicit_true_residual': .1, 'solve_seconds': 10**12},
        {'iteration': 128, 'explicit_true_residual': .1, 'solve_seconds': 10**12},
    ]
    result = recompute_balanced_screen(
        {'screen_enabled': True, 'screen_seconds': None,
         'screen': {'iteration': 128, 'passed': False}}, rows)
    assert result['matches']


def test_checker_time_limits_preserve_bounded_and_none_contracts():
    from benchmarks.physical_intermediate_checker import _check_optional_time_limits

    summary = {
        'status': 'RUNNING',
        'solve_conservative_seconds': 11,
        'solve_monotonic_seconds': 11,
        'elapsed_conservative_seconds': 21,
        'elapsed_monotonic_seconds': 21,
    }

    def collect(resources):
        errors = []

        def require(condition, message, *, expected=False):
            if not condition:
                errors.append((message, expected))

        _check_optional_time_limits(summary, resources, require)
        return errors

    assert collect({'solve_seconds': 10, 'workflow_seconds': 20}) == [
        ('solve budget exceeded', False),
        ('workflow budget exceeded before checker', False),
    ]
    assert collect({'solve_seconds': None, 'workflow_seconds': None}) == []


def test_no_deadline_watchdog_keeps_resource_monitoring_active(tmp_path):
    helper = (
        'import json, sys\n'
        'from pathlib import Path\n'
        'from benchmarks.subreaper_watchdog import supervise\n'
        'summary = supervise([sys.executable, "-c", "pass"], Path(sys.argv[1]), '
        'wall_seconds=None, solve_seconds=None, interval=0.05, grace_seconds=0.1)\n'
        'print(json.dumps(summary))\n'
    )
    completed = subprocess.run(
        [sys.executable, '-c', helper, str(tmp_path / 'watchdog')],
        check=True, capture_output=True, text=True,
    )
    summary = json.loads(completed.stdout.strip().splitlines()[-1])
    assert summary['classification'] == 'COMPLETED'
    assert summary['time_limit_mode'] == 'none'
    assert summary['workflow_deadline_seconds'] is None
    assert summary['solve_deadline_seconds'] is None
    assert summary['samples'] >= 1


def test_native_launcher_uses_actual_budget_and_isolated_cache(monkeypatch, tmp_path):
    from src.runners.task038_launcher import launch_specification
    spec = replace(load_and_resolve(NATIVE_INPUT), expected_output_parent=tmp_path/'run')
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate', lambda *_: {})
    seen = []

    def supervise(command, directory, **kwargs):
        assert command[:3] == ['/usr/bin/taskset', '-c', '23']
        assert command[3:5] == ['/usr/bin/numactl', '--membind=1']
        seen.append(kwargs)
        return {'leader_exit_code': 0, 'classification': 'COMPLETED',
                    'job_swap_activity': 'zero_supported_by_zero_global_activity',
                    'launch_envelope': {}, 'memory_scope': 'test'}

    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise', supervise)
    result = launch_specification(spec, source_sha='a'*40)
    assert result['result_classification'] == 'worker_exit0'
    assert seen[0]['solve_seconds'] == 43200
    assert 64700 < seen[0]['wall_seconds'] <= 64800
    assert seen[0]['stop_on_global_swap']
    assert Path(seen[0]['cache_path']).is_relative_to(tmp_path)
    contract = json.loads(Path(result['manifest']).read_text())['native_capacity_contract']
    assert contract['screen'] == {
        'enabled': False,
        'iterations': 128,
        'solve_seconds': 7200,
        'notch_policy': 'disabled_without_extra_screen',
    }
    assert contract['solve_seconds'] == 43200
    assert contract['workflow_seconds'] == 64800
    assert contract['restart'] == 32 and contract['max_iterations'] == 2048


def test_native_5nm_launcher_passes_none_deadlines_to_watchdog(monkeypatch, tmp_path):
    from src.runners.task038_launcher import launch_specification

    spec = replace(load_and_resolve(FIVE_NM_INPUT), expected_output_parent=tmp_path/'run')
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate', lambda *_: {})
    seen = []

    def supervise(command, directory, **kwargs):
        assert command[:5] == ['/usr/bin/taskset', '-c', '23', '/usr/bin/numactl', '--membind=1']
        seen.append(kwargs)
        return {'leader_exit_code': 0, 'classification': 'COMPLETED',
                'job_swap_activity': 'zero_supported_by_zero_global_activity',
                'launch_envelope': {}, 'memory_scope': 'test'}

    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise', supervise)
    result = launch_specification(spec, source_sha='b'*40)
    assert result['result_classification'] == 'worker_exit0'
    assert seen[0]['wall_seconds'] is None
    assert seen[0]['solve_seconds'] is None
    manifest = json.loads(Path(result['manifest']).read_text())
    contract = manifest['native_capacity_contract']
    assert contract['time_limit_mode'] == 'none'
    assert contract['screen']['iterations'] == 128
    assert contract['screen']['solve_seconds'] is None
    assert contract['solve_seconds'] is None
    assert contract['workflow_seconds'] is None


def test_native_2nm_manifest_records_user_material_authority(monkeypatch, tmp_path):
    from src.runners.task038_launcher import launch_specification

    spec = replace(load_and_resolve(TWO_NM_INPUT), expected_output_parent=tmp_path/'run')
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate', lambda *_: {})

    def supervise(command, directory, **kwargs):
        assert command[:5] == ['/usr/bin/taskset', '-c', '23', '/usr/bin/numactl', '--preferred=1']
        assert kwargs['wall_seconds'] is None
        assert kwargs['solve_seconds'] is None
        return {'leader_exit_code': 0, 'classification': 'COMPLETED',
                'job_swap_activity': 'zero_supported_by_zero_global_activity',
                'launch_envelope': {}, 'memory_scope': 'test'}

    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise', supervise)
    result = launch_specification(spec, source_sha='c'*40)
    manifest = json.loads(Path(result['manifest']).read_text())
    contract = manifest['native_capacity_contract']
    assert contract['material_authority'].startswith('user-provided')
    assert contract['time_limit_mode'] == 'none'


def test_native_preferred_node1_prefix_is_explicit_and_not_strict():
    from src.io.execution_plan import native_memory_policy_prefix

    assert native_memory_policy_prefix('preferred_node1') == ('/usr/bin/numactl', '--preferred=1')
    assert native_memory_policy_prefix('membind_node1') == ('/usr/bin/numactl', '--membind=1')


def test_native_default_does_not_silently_bind_memory(tmp_path):
    from src.io.execution_plan import build_execution_plan
    plan = build_execution_plan(load_and_resolve(INPUT), tmp_path, source_sha='a' * 40)
    assert plan.argv[:3] == ('/usr/bin/taskset', '-c', '23')
    assert plan.argv[3] != '/usr/bin/numactl'


def test_node1_meminfo_parser_uses_real_kernel_fixture():
    from src.runners.native_capacity import _parse_node1_meminfo

    path = Path('/sys/devices/system/node/node1/meminfo')
    if not path.is_file():
        pytest.skip('host has no node1 meminfo fixture')
    values = _parse_node1_meminfo(path.read_text())
    assert values['Node 1 MemTotal'] > 0
    assert values['Node 1 MemFree'] >= 0


def test_native_preexisting_external_swap_policy_keeps_new_global_gate_strict():
    from src.runners.native_capacity import _validate_preexisting_swap

    def snapshot(preexisting, *, cgroup_swap=0, second_cgroup_swap=None):
        if second_cgroup_swap is None:
            second_cgroup_swap = cgroup_swap
        return {
            'preexisting_global_swap_bytes': preexisting,
            'current_cgroup_relative': 'user.slice/task.scope',
            'current_cgroup_swap_bytes': cgroup_swap,
            'current_pid_in_cgroup': True,
            'cgroup_procs_readable': True,
            'stable_two_read_baseline': True,
            'global_pswp_delta': {'pswpin_pages': 0, 'pswpout_pages': 0},
            'swap_free_delta_bytes': 0,
            'second_read': {
                'current_cgroup_swap_bytes': second_cgroup_swap,
                'current_pid_in_cgroup': True,
                'cgroup_procs_readable': True,
            },
        }

    assert _validate_preexisting_swap(snapshot(0)) == 'zero_preexisting_global_swap'
    assert _validate_preexisting_swap(snapshot(8192)) == 'preexisting_global_swap_reported_outside_current_cgroup'
    with pytest.raises(InputError, match='current task cgroup attribution unavailable'):
        _validate_preexisting_swap(snapshot(8192, cgroup_swap=None,
                                            second_cgroup_swap=None))
    with pytest.raises(InputError, match='current task cgroup'):
        _validate_preexisting_swap(snapshot(8192, cgroup_swap=8192))


def test_native_rejects_changed_solver_and_material(tmp_path):
    for before, after in [('restart = 32', 'restart = 64'),
                          ('0.00182649365', '0.002')]:
        path = tmp_path/'case.dat'
        path.write_text(INPUT.read_text().replace(before, after))
        with pytest.raises(InputError):
            load_and_resolve(path)


def test_shortwave_screen_budget_preserves_progress_gate():
    from benchmarks.physical_intermediate_checker import recompute_balanced_screen
    screen = BalancedScreen(10800)
    assert screen.inspect(31, .1, 1800) is None
    decision = screen.inspect(31, .1, 10800)
    assert not decision['passed']
    rows = [{'iteration': 31, 'explicit_true_residual': .1, 'solve_seconds': 10800}]
    assert recompute_balanced_screen({'screen_enabled': True, 'screen_seconds': 10800,
                                         'screen': json.loads(json.dumps(decision))}, rows)['matches']


def test_tracked_wsl_all_modal_channels_compare_without_field_arrays(tmp_path):
    from src.runners.native_capacity_output import compare_wsl_observables
    data = json.loads(Path('docs/task039_extra_physical_multilevel/outcomes/records/balanced_coupling_v5.json').read_text())
    old = data['models'][0]
    numerical = tmp_path/'numerical_output'
    numerical.mkdir()
    rows = old['all_mode_observables']
    (numerical/'dtn_port_diffraction_orders_3d.json').write_text(json.dumps({'orders': rows}))
    (numerical/'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps(rows))
    physics = old['physics']
    outputs = {'port_metrics': {'R_total': physics['R'], 'T_total': physics['T'],
                               'A_balance': physics['A']},
               'volume_metrics': {'A_volume_total': physics['A_volume']}}
    result = compare_wsl_observables({'mode_sha256': old['mode_sha']}, outputs,
                                    tmp_path, load_and_resolve(INPUT).as_jsonable())
    assert result['wsl_modal_power_passed'] and result['mode_count'] == 80
    assert result['status'] == 'REFERENCE_AUTHORITY_LIMITED'
    assert result['full_field_comparison'] == 'WSL_FULL_FIELD_COMPARISON_PARTIAL'


def test_selected_eh_reference_denominator_and_fail_closed(tmp_path):
    from src.runners.physical_balanced_output import compare_selected_eh

    reference = tmp_path/'reference'/'numerical_output'
    current = tmp_path/'current'/'numerical_output'
    reference.mkdir(parents=True)
    current.mkdir(parents=True)
    coordinates = {
        'x_nm': np.array([0.0]), 'y_nm': np.array([0.0]), 'z_nm': np.array([10.0]),
    }
    np.savez(reference/'full3d_reference_samples.npz', **coordinates,
             E_V_per_m=np.ones((1, 1, 1, 3), dtype=np.complex128),
             H_A_per_m=np.ones((1, 1, 1, 3), dtype=np.complex128))
    np.savez(current/'full3d_reference_samples.npz', **coordinates,
             E_V_per_m=np.full((1, 1, 1, 3), 2.0, dtype=np.complex128),
             H_A_per_m=np.full((1, 1, 1, 3), 2.0, dtype=np.complex128))
    failed = compare_selected_eh(reference, current)
    assert failed['status'] == 'SELECTED_EH_FAIL'
    assert failed['fields']['E_V_per_m']['relative_l2_difference'] == pytest.approx(1.0)


def test_native_reference_identity_package_precedes_supervisor(tmp_path, monkeypatch):
    import src.runners.fine_reference_preflight as preflight
    from src.runners.workflow_timebase import clock_sample
    from src.runners import physical_diagnosis, task038_launcher

    monkeypatch.setattr(task038_launcher, '_physical_source_gate', lambda *_: {'source_sha': 'a' * 40})
    monkeypatch.setattr(preflight.subprocess, 'check_output', lambda *_args, **_kwargs: b'{"qualified":true}')
    seen = {}

    def fake_supervise(command, directory, **kwargs):
        run_directory = Path(directory).parent
        seen['command'] = command
        seen['manifest'] = json.loads((run_directory / 'run_manifest.json').read_text())
        seen['files'] = {name: (run_directory / name).is_file() for name in (
            'input_original.dat', 'resolved_config.json', 'source_sha.txt',
            'input_sha256.txt', 'physical_model_sha256.txt', 'launch.json')}
        start = clock_sample()
        return {'classification': 'COMPLETED', 'clock_start': start, 'clock_end': clock_sample(),
                'workflow_clock_interval': {'budget_seconds': 0.0}}

    monkeypatch.setattr(physical_diagnosis, 'supervise_diagnosis', fake_supervise)
    code = preflight.main([
        '--input', str(REFERENCE_INPUT), '--directory', str(tmp_path / 'reference'),
        '--expected-sha', 'a' * 40, '--cache-path', str(tmp_path / 'reference' / 'cache'),
        '--solve-reference', '--witness-audit', str(Path('docs/task39extra_para_workstation_capacity/outcomes/records/r1_attempt3_reference_witness.json')),
        '--witness-audit-sha', '1b49287c8536a0be32a8edec13ae5144a2fd43b3fbd91419aaccdba6ac5ca156',
        '--workflow-seconds', '21600', '--native-matched-reference',
    ])
    assert code == 2
    assert all(seen['files'].values())
    assert seen['manifest']['workflow_limit_seconds'] == 21600.0
    assert seen['manifest']['global_swap_supervision'] is True
    assert seen['manifest']['supervisor_cpu'] == 9 and seen['manifest']['worker_cpu'] == 23
    assert seen['command'][:3] == ['/usr/bin/taskset', '-c', '23']
    assert seen['command'][3:5] == ['/usr/bin/numactl', '--membind=1']
    assert seen['manifest']['native_memory_policy'] == 'membind_node1'
