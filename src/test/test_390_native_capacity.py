"""Native profile wiring, V5 preservation and unchanged screen criteria."""
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import profile_facts
from src.io.run_specification import thaw
from src.solvers.physical_balanced_fgmres import BalancedScreen

INPUT = Path('input/task39extra_para_workstation_capacity/original_13p5nm_p6h10.dat')
REFERENCE_INPUT = Path('input/task39extra_para_workstation_capacity/original_13p5nm_native_matched_reference.dat')


def test_native_matched_reference_is_explicit_and_hash_bound():
    reference = load_and_resolve(REFERENCE_INPUT)
    ordinary = load_and_resolve('input/task39extra/original_13p5nm_p6h10_fine_reference.dat')
    assert reference.solver['direct_solver_profile'] == 'native_matched_reference'
    assert reference.execution['timeout_seconds'] == 21600
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


def test_native_launcher_uses_actual_budget_and_isolated_cache(monkeypatch, tmp_path):
    from src.runners.task038_launcher import launch_specification
    spec = replace(load_and_resolve(INPUT), expected_output_parent=tmp_path/'run')
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate', lambda *_: {})
    seen = []

    def supervise(command, directory, **kwargs):
        assert command[:3] == ['/usr/bin/taskset', '-c', '23']
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
        'enabled': True,
        'iterations': 128,
        'solve_seconds': 7200,
        'notch_policy': 'enabled',
    }
    assert contract['solve_seconds'] == 43200
    assert contract['workflow_seconds'] == 64800
    assert contract['restart'] == 32 and contract['max_iterations'] == 2048


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
