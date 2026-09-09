"""Native profile wiring, V5 preservation and unchanged screen criteria."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import profile_facts
from src.solvers.physical_balanced_fgmres import BalancedScreen

INPUT = Path('input/task39extra_para_workstation_capacity/original_13p5nm_p6h10.dat')


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
    for key in ('balanced', 'fine_auxiliary', 'intermediate', 'structural_calls', 'outer'):
        assert new[key] == old[key]
    assert old['resources']['solve_seconds'] == 7200
    assert new['resources']['solve_seconds'] == 14400


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
    assert seen[0]['solve_seconds'] == 14400
    assert 21500 < seen[0]['wall_seconds'] <= 21600
    assert seen[0]['stop_on_global_swap']
    assert Path(seen[0]['cache_path']).is_relative_to(tmp_path)


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
