"""Focused R1 wiring and negative raw-comparison contracts."""
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.physical_pc_comparison import (
    array_difference, primary_pc_seconds, validate_pc_records, validate_same_input_inventory,
)
from src.runners.physical_pc_profile import SCHEDULE


def raw_records():
    rows = [dict(index=i, input=name, warmup=warmup,
                 timing_delta={'PC': {'inclusive_seconds': 2.}})
            for i, (name, warmup) in enumerate(SCHEDULE, 1)]
    pcs = [dict(intermediate=dict(factor_solve_calls=1, explicit_action_count=1,
            true_residual_norm=1e-12, rhs_norm=1.)) for _ in rows]
    return rows, pcs


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'mismatch', 'path'])
def test_same_input_inventory_rejects_incomplete_evidence(mutation):
    items = [dict(name=name+'_'+role) for name in ('physical_rhs', 'checkpoint160_residual', 'random_complex')
             for role in ('B6', 'curl', 'material_mass', 'A6')]
    for item in items:
        for label in ('original', 'fast'):
            item[label] = dict(path='same_input_'+item['name']+'_'+label+'.npy')
    validate_same_input_inventory(items)
    if mutation == 'missing': items.pop()
    elif mutation == 'duplicate': items.append(items[0])
    elif mutation == 'mismatch': items[0]['name'] = 'wrong_B6'
    else: items[0]['fast']['path'] = items[1]['fast']['path']
    with pytest.raises(ValueError): validate_same_input_inventory(items)


@pytest.mark.parametrize('bad', ['schedule', 'warmup', 'p4_count', 'p4_residual', 'p4_zero_rhs',
                                  'p4_nan', 'time_zero', 'time_nan', 'time_inf', 'missing_pc'])
def test_raw_schedule_p4_and_time_gates(bad):
    rows, pcs = raw_records()
    assert max(validate_pc_records(rows, pcs)) == 1e-12
    if bad == 'schedule': rows[1]['input'] = 'random_complex'
    elif bad == 'warmup': rows[1]['warmup'] = True
    elif bad == 'p4_count': pcs[0]['intermediate']['factor_solve_calls'] = 2
    elif bad == 'p4_residual': pcs[0]['intermediate']['true_residual_norm'] = 1e-5
    elif bad == 'p4_zero_rhs': pcs[0]['intermediate']['rhs_norm'] = 0
    elif bad == 'p4_nan': pcs[0]['intermediate']['true_residual_norm'] = float('nan')
    elif bad == 'missing_pc': pcs.pop()
    else: rows[0]['timing_delta']['PC']['inclusive_seconds'] = dict(time_zero=0., time_nan=float('nan'), time_inf=float('inf'))[bad]
    with pytest.raises(ValueError): validate_pc_records(rows, pcs)


def test_primary_keeps_mandatory_logs_and_different_input_a6_is_diagnostic():
    delta = {'PC': {'inclusive_seconds': 10.}, 'PC/S6/artifact_io': {'inclusive_seconds': 2.},
             'PC/S6/artifact_io/artifact_io': {'inclusive_seconds': 1.},
             'PC/MR/log_marker': {'inclusive_seconds': 3.}, 'PC_output_check': {'inclusive_seconds': 4.}}
    assert primary_pc_seconds(delta) == 8.
    a = np.ones(4, complex)
    assert array_difference(a, a*1.0001)['passed'] is None
    assert not array_difference(a, a*1.0001, 1e-11)['passed']


def test_fast_dat_has_own_identity_and_same_physics():
    from src.io import load_and_resolve
    from src.io.physical_intermediate_profile import FAST_PROFILE, profile_facts
    from src.runners.physical_profile_budget import FAST_INPUT_SHA
    old = load_and_resolve('input/task39extra/original_13p5nm_p6h10_p4_reference.dat')
    new = load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_equivalent_fast.dat')
    assert new.input_sha256 == FAST_INPUT_SHA != old.input_sha256
    assert new.physical_model_sha256 == old.physical_model_sha256
    assert new.solver['preconditioner'] == FAST_PROFILE
    assert profile_facts(FAST_PROFILE)['resources']['solve_seconds'] == 7200
    assert profile_facts(FAST_PROFILE)['outer']['max_iterations'] == 2048


def test_fast_budget_once_and_preserves_prior_cost(tmp_path, monkeypatch):
    from src.io import load_and_resolve
    from src.runners import physical_profile_budget as budget, physical_pc_comparison as checker, task038_launcher
    from src.io.input_loader import InputError
    monkeypatch.setattr(budget, 'verified_checkpoint', lambda *args: None)
    monkeypatch.setattr(checker, 'verify_r0_profile', lambda root: dict(root=str(root), source_sha='a'*40))
    path = tmp_path/'ledger.json'
    old = dict(kind='R0_profile', status='COMPLETED', elapsed_seconds=927.)
    path.write_text(json.dumps(dict(limit_seconds=36000, attempts=[old])))
    def launch(spec, *, pc_profile):
        assert pc_profile['variant'] == checker.FAST_VARIANT
        assert pc_profile['complete_pc_limit'] == 7 and pc_profile['batch_limit_seconds'] == 1800
        return dict(result_classification='worker_exit0', run_directory='fake')
    monkeypatch.setattr(task038_launcher, 'launch_specification', launch)
    spec = load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_equivalent_fast.dat')
    budget.launch_profile(spec, tmp_path, path, variant=checker.FAST_VARIANT, r0_reference=tmp_path)
    assert json.loads(path.read_text())['attempts'][0] == old
    with pytest.raises(InputError, match='already reserved'):
        budget.launch_profile(spec, tmp_path, path, variant=checker.FAST_VARIANT, r0_reference=tmp_path)


@pytest.mark.parametrize('packed', [False, True])
def test_post_setup_install_preserves_real_windows_and_borrowed_dtn(packed):
    from dataclasses import replace
    from contextlib import ExitStack
    from mpi4py import MPI
    import ufl
    from src.common.config_3d import target_stage4_config
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels, same_mesh_positive_form
    from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction, FullspaceSplitVolumeAction
    from src.solvers.fullspace_quadrature_diagonal import build_quadrature_positive_diagonal
    from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import SameMeshP6MatrixFreeShell
    from src.solvers.fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
    from src.solvers.physical_equivalent_fast import install_equivalent_fast, release_equivalent_fast, frozen_smoother_identity
    cfg = replace(target_stage4_config(degree=2, h_nm=100), period_x=20., period_y=15.,
        grating_width_x=8., grating_width_y=15., grating_height=2., z_min=-1., z_max=3.,
        air_height=3., substrate_thickness=1., mesh_cell_type='hexahedron',
        mesh_spacing_mode='boundary_fitted', mesh_axis_cell_counts=(3, 2, 3),
        incident_theta_deg=74., incident_phi_deg=17., n_substrate=1.4+.05j, n_grating=.9+.02j)
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,))
    levels['spaces'][6], levels['floquets'][6] = levels['spaces'][2], levels['floquets'][2]
    mpc = levels['floquets'][6].mpc
    space = mpc.function_space
    form = same_mesh_positive_form(space, curl_coefficient=levels['mu'], mass_coefficient=levels['mass'])
    with ExitStack() as owned:
        b6 = FullspaceMpcFormAction(form, space, mpc=mpc)
        diagonal = build_quadrature_positive_diagonal(space, levels['mu'], levels['mass'], mpc)
        shell = SameMeshP6MatrixFreeShell(b6, diagonal); owned.callback(shell.destroy)
        smoother = FixedChebyshevJacobiPETSc(shell.matrix); owned.callback(smoother.destroy)
        forms = _build_physical_volume_terms(cfg, ufl.TrialFunction(space), ufl.TestFunction(space),
            ufl.Measure('dx', domain=space.mesh, subdomain_data=levels['mesh_data'].cell_tags))
        volume = FullspaceSplitVolumeAction(*forms, space, mpc=mpc)
        destroyed = []
        dtn = SimpleNamespace(apply=lambda x, y: np.copyto(y.array, .2j*x.array),
                              destroy=lambda: destroyed.append('dtn'))
        physical = FullspacePhysicalAction(volume, dtn); owned.callback(physical.destroy)
        positive = dict(p6_shell=shell, upper_cycle=SimpleNamespace(smoother=smoother),
                        lower_cycle=SimpleNamespace(smoother=smoother))
        factor = object()
        bundle = dict(positive=positive, levels=levels, pc=SimpleNamespace(fine_action=physical),
            fine=dict(physical_action=physical, volume_action=volume, dtn_action=dtn), reference_factor=factor)
        before = frozen_smoother_identity(positive)
        original_physical_audit = dict(physical.audit)
        from src.io.physical_intermediate_profile import PACKED_PROFILE, FAST_PROFILE
        facts = install_equivalent_fast(bundle, cfg, profile=PACKED_PROFILE if packed else FAST_PROFILE)
        owned.callback(release_equivalent_fast, bundle)
        assert all(k['contiguous_real_imag_work'] is packed for k in facts['kernels'])
        assert facts['physical_dg0_function_arrays_bytes'] == 18*2*np.dtype(np.complex128).itemsize
        assert facts['original_setup_before'] == facts['installed_after'] == before
        assert bundle['reference_factor'] is factor and bundle['fine']['physical_action'] is physical
        assert dict(physical.audit) == original_physical_audit
        x = shell.matrix.createVecRight(); owned.callback(x.destroy)
        y = x.duplicate(); owned.callback(y.destroy)
        z = x.duplicate(); owned.callback(z.destroy)
        rng = np.random.default_rng(363)
        x.array[:] = rng.normal(size=x.getLocalSize())+1j*rng.normal(size=x.getLocalSize())
        slaves = np.asarray(mpc.slaves); x.array[slaves[slaves < x.getLocalSize()]] = 0
        physical.apply(x, y)
        bundle['pc'].fine_action.apply(x, z)
        assert np.linalg.norm(y.array-z.array)/np.linalg.norm(y.array) <= 1e-11
        old = b6.apply(x).array.copy()
        assert np.linalg.norm(shell.action.apply(x).array-old)/np.linalg.norm(old) <= 1e-11
        if packed:
            from src.solvers.physical_equivalent_fast import select_equivalent_backend
            from src.solvers.physical_pc_timing import PCTiming
            # Close the old instrumentation before every action reference switch.
            for enabled in (False, True, False, True):
                select_equivalent_backend(bundle, packed=enabled)
                timer = PCTiming()
                action = shell.action
                timer.wrap(action, 'apply', 'B6')
                np.testing.assert_allclose(action.apply(x).array, old, rtol=1e-11, atol=1e-11)
                assert timer.snapshot()['B6']['calls'] == 1
                timer.close()
                assert 'apply' not in vars(action)
                assert frozen_smoother_identity(positive) == before
        release_equivalent_fast(bundle)
        assert not destroyed and shell.action is b6 and bundle['pc'].fine_action is physical
        physical.apply(x, z)
        np.testing.assert_array_equal(z.array, y.array)
    assert destroyed == ['dtn']


@pytest.mark.parametrize('mutation', ['none', 'S6', 'component', 'hash'])
def test_independent_checker_reads_raw_arrays(tmp_path, monkeypatch, mutation):
    from src.runners import physical_pc_comparison as checker
    roots = [tmp_path/'old', tmp_path/'new']
    monkeypatch.setattr(checker, 'verify_r0_profile', lambda root: dict(root=str(root), source_sha=checker.R0_SOURCE))
    for which, root in enumerate(roots):
        directory = root/'pc_profile'
        directory.mkdir(parents=True)
        state = dict(source_sha=checker.R0_SOURCE if which == 0 else 'b'*40,
            completed=7, active_apply=None, config=dict(variant=checker.FAST_VARIANT), captures=[],
            same_input_checks=[], equivalent_fast=dict(original_setup_before={'hash': 'same'}, installed_after={'hash': 'same'}))
        def save(name, value):
            path = directory/name
            path.parent.mkdir(exist_ok=True)
            np.save(path, value)
            record = dict(path=name, shape=list(value.shape), ownership_range=[0, value.size],
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            state['captures'].append(record)
            return record
        for name in ('physical_rhs', 'checkpoint160_residual', 'random_complex'):
            save(name+'.npy', np.ones(3, complex))
            if which:
                for role in ('B6', 'curl', 'material_mass', 'A6'):
                    row = dict(name=name+'_'+role)
                    for label in ('original', 'fast'):
                        value = np.ones(3, complex)
                        if mutation == 'component' and role == 'B6' and label == 'fast': value *= 2
                        row[label] = save('same_input_'+row['name']+'_'+label+'.npy', value)
                    state['same_input_checks'].append(row)
        for i in range(1, 8):
            for name in ('S6_01.npy', 'S6_02.npy', 'PC_output.npy', 'PC_A6_output.npy',
                         'A6_01.npy', 'A6_02.npy', 'A6_03.npy', 'A6_04.npy'):
                value = np.ones(3, complex)
                # Different-input A6 discrepancy is deliberately much larger
                # than the action gate and must remain diagnostic only.
                if which and ('A6' in name): value *= 1.001
                if which and mutation == 'S6' and name.startswith('S6'): value *= 2
                save(f'apply_{i:02d}/'+name, value)
        rows, pcs = raw_records()
        for row in rows:
            row['timing_delta'] = {'PC': {'inclusive_seconds': 22.021386729524238 if not which else 15.}}
            for path, calls in {'PC/S6': 2, 'PC/S6/B6': 12, 'PC/S6/B6/assemble': 12,
                                'PC/MR/A6': 3, 'PC_output_check/A6': 1}.items():
                row['timing_delta'][path] = dict(calls=calls, inclusive_seconds=1.)
        (root/'profile_applies.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
        (root/'pc_applies.jsonl').write_text('\n'.join(json.dumps(row) for row in pcs)+'\n')
        (directory/'state.json').write_text(json.dumps(state))
    if mutation == 'hash':
        (roots[1]/'pc_profile/apply_01/PC_output.npy').write_bytes(b'changed')
        with pytest.raises(ValueError, match='hash mismatch'):
            checker.compare_profiles(*roots)
    else:
        result = checker.compare_profiles(*roots)
        assert result['passed'] == (mutation == 'none')
        assert result['speed_gate_passed']
        assert result['comparisons']['apply_01/A6_01.npy']['passed'] is None
