"""Opt-in bounded FE qualification; no outer PDE or large factor is run."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np
import pytest
from dolfinx.la.petsc import create_vector
from mpi4py import MPI

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.io.native_capacity_profile import native_profile_facts
from src.runners.physical_intermediate import _jsonable
from src.runners.physical_retained_condensed_v20 import (
    RetainedCondensedRuntime,
    _compile_volume_form,
    _native_aq_projection_check,
)
from src.solvers.fullspace_physical_intermediate import apply_owned
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _tabulate_raw_tensor_class,
)
from src.solvers.hcurl_blocked_gram_tensor import HcurlBlockedGramTensor

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get('TASK39EXTRA_V6_ACTUAL_COMPONENTS') != '1',
                               reason='explicit bounded real FE/MPC component campaign only')


def _vector(space, seed):
    vector = create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])
    indices = np.arange(vector.getLocalSize())
    vector.array[:] = np.sin((indices+1)*(0.021+seed*.001))+1j*np.cos((indices+1)*.037)
    vector.assemble()
    return vector


def _difference(left, right):
    delta = left.copy()
    try:
        delta.axpy(-1, right)
        return float(delta.norm()/max(right.norm(), np.finfo(float).tiny))
    finally:
        delta.destroy()


@pytest.mark.parametrize('wavelength', [5, 2])
def test_actual_material_full_ports_tensor_action_recovery_and_c(wavelength):
    if os.environ.get('TASK39EXTRA_V6_COMPONENT_WAVELENGTH') not in (None, str(wavelength)):
        pytest.skip('another wavelength selected for this process')
    specification = load_and_resolve(ROOT/('input/task39extra_para_workstation_capacity/'+
                                    f'v6_{wavelength}nm_'+('full.dat' if wavelength == 5 else 'pilot16.dat')))
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    small = replace(cfg, mesh_axis_cell_counts=(3, 2, 3), mesh_axis_x_values=None,
        mesh_axis_y_values=None, mesh_axis_z_values=None, mesh_axis_z_profile=None,
        mesh_plan_id=None, mesh_plan_sha256=None)
    identity = specification.solver['preconditioner']
    options = native_profile_facts(identity)['component_options']
    runtime = old_h6 = None
    vectors = []
    report = {'wavelength_nm': wavelength, 'fixture_cells': 18,
        'full_input_sha256': specification.input_sha256,
        'full_physical_sha256': specification.physical_model_sha256,
        'full_mesh_counts': None,
        'scope': 'bounded FE/MPC with all physical port modes; not a full PDE',
        'threads': {name: os.environ.get(name) for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS')},
        'affinity': sorted(os.sched_getaffinity(0)), 'stages': [], 'tensor_witness': []}
    directory = Path(os.environ.get('TASK39EXTRA_V6_COMPONENT_OUTPUT', ROOT/'tmp/review_v6_components'))
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/f'actual_{wavelength}nm_math{os.environ.get("OPENBLAS_NUM_THREADS", "unknown")}.json'

    def save(stage, facts=None):
        report['stages'].append({'stage': stage, 'monotonic': perf_counter(), 'facts': facts})
        output.write_text(json.dumps(_jsonable(report), sort_keys=True, allow_nan=False)+'\n')
        print(f'V6_COMPONENT {wavelength}nm {stage}', flush=True)

    try:
        save('build_started')
        started = perf_counter()
        runtime = RetainedCondensedRuntime.build(small, MPI.COMM_SELF,
            sum_factorized_work=True, geometry_identity_policy='rounded_12_representative',
            component_options=options, marker=lambda name, facts: save(name))
        report['build_seconds'] = perf_counter()-started
        assert runtime.mode_count == (600 if wavelength == 5 else 3904)
        report['mode_count'] = runtime.mode_count
        report['mode_sha256'] = runtime.mode_sha256
        report['p6_build'] = runtime.p6_system.build_audit
        report['p4_build'] = runtime.p4_system.build_audit
        from src.geometry.mesh_builder_3d import _stage4_axis_plan
        plan = _stage4_axis_plan(cfg, 1)
        report['full_mesh_counts'] = [len(plan.x_values)-1, len(plan.y_values)-1, len(plan.z_values)-1]
        groups = {}
        raw_classes = set()
        # Metadata only: actual full-case widths/tags, without its FE mesh.
        for x0, x1 in zip(plan.x_values[:-1], plan.x_values[1:]):
            for y0, y1 in zip(plan.y_values[:-1], plan.y_values[1:]):
                for z0, z1 in zip(plan.z_values[:-1], plan.z_values[1:]):
                    x, y, z = (x0+x1)/2, (y0+y1)/2, (z0+z1)/2
                    tag = cfg.tags.substrate if z < cfg.interface_z else cfg.tags.air
                    if (cfg.grating_x_min <= x <= cfg.grating_x_max and
                        cfg.grating_y_min <= y <= cfg.grating_y_max and
                        cfg.grating_z_min <= z <= cfg.grating_z_max):
                        tag = cfg.tags.grating
                    widths = (float(x1-x0), float(y1-y0), float(z1-z0))
                    raw_classes.add((int(tag), *widths))
                    key = (int(tag), *(round(v, 12) for v in widths))
                    previous = groups.get(key)
                    groups[key] = min(previous, widths) if previous else widths
        assert len(groups) == 6
        report['full_mesh_geometry_metadata'] = {'raw_classes': len(raw_classes),
            'tensor_groups': len(groups), 'representative_widths': {str(k): v for k, v in groups.items()},
            'raw_classes_verified_not_rounded_for_LU': True}
        # Native FFCx independently witnesses every raw tensor group present
        # in this fixture, with the exact compiled form and unrounded input.
        thread_comparison = os.environ.get('TASK39EXTRA_V6_COMPONENT_THREAD_COMPARISON') == '1'
        report['native_tensor_witness_scope'] = ('covered by E2 actual_attempt3; E3 fixed-work comparison'
            if thread_comparison else 'fresh independent FFCx for all actual tensor groups')
        for degree, bundle, system in (() if thread_comparison else
                                      ((6, runtime.fine, runtime.p6_system),
                                       (4, runtime.p4, runtime.p4_system))):
            space = runtime.levels['spaces'][degree]
            form = _compile_volume_form(bundle['volume_action'])
            kernels = _cell_integral_kernels(form, sum_duplicate_cell_integrals=True)
            gram = HcurlBlockedGramTensor(space.element.basix_element, small,
                bundle['volume_action'].bilinear_form, compiled_form=form)
            classes = [{'material_tag': k[0], 'cell_widths': v} for k, v in sorted(groups.items())]
            canonical, widths = _canonical_axis_aligned_coordinates(runtime.levels['mesh'], 0,
                tolerance=1e-11, geometry_identity_policy='raw_unrounded')
            template = canonical.reshape(-1, 3)/np.asarray(widths)
            for item in classes:
                # The template carries native hexahedron vertex ordering.
                coordinates = (template*np.asarray(item['cell_widths'])).reshape(-1)
                started = perf_counter()
                native = _tabulate_raw_tensor_class(form, kernels, coordinates,
                    tag=item['material_tag'], dimension=space.element.space_dimension)
                native_seconds = perf_counter()-started
                candidate = gram(form, kernels, coordinates,
                    tag=item['material_tag'], dimension=space.element.space_dimension)
                relative = float(np.linalg.norm(candidate-native)/np.linalg.norm(native))
                assert relative <= 1e-10
                report['tensor_witness'].append({'degree': degree, 'tag': item['material_tag'],
                    'widths': item['cell_widths'], 'relative': relative, 'native_seconds': native_seconds,
                    'native_sha256': hashlib.sha256(native.tobytes()).hexdigest()})
                save(f'p{degree}_native_tensor_witness')
        report['action_relative'] = {}
        for degree, native, fast in ((6, runtime.fine['physical_action'], runtime.pc_physical['physical_action']),
                                   (4, runtime.p4['physical_action'], runtime.fast_a4['physical_action'])):
            source = _vector(runtime.levels['spaces'][degree], degree)
            vectors.append(source)
            source.array[runtime.levels['floquets'][degree].mpc.slaves] = 0
            old = apply_owned(native, source)
            new = apply_owned(fast, source)
            vectors.extend((old, new))
            relative = _difference(new, old)
            assert relative <= 1e-10
            report['action_relative'][str(degree)] = relative
        save('native_complete_actions_pass')
        # Exactly one symbolic/numeric for this configuration, then all RHS
        # and both corrections reuse it. No factor per probe or per vector.
        factor = runtime.attach_p4_factor(sample=lambda: {'icntl23': 0,
            'reference_memory_admission': 'measured_rss', 'launch_cap_bytes': 1_300_000_000_000,
            'rss_bytes': 0, 'swap_bytes': 0, 'all_status_readable': True, 'swap_policy': 'observe_only',
            'resource_stop_policy': 'measured_tree_rss_only_v3'}, marker=lambda name, facts: save(name, facts))
        report['factor'] = factor
        bridge = runtime.build_bal_h(marker=lambda name, facts: save(name, facts))
        from src.solvers.physical_light_setup import build_light_h6_setup
        old_h6 = build_light_h6_setup(runtime.levels, small, lambda *a: None,
            packed_power10=True, packed_apply=True, sum_factorized_work=True,
            sum_factorized_power10=True)
        report['h6_candidate'] = runtime.h6['light_facts']
        report['h6_native_diagonal_control'] = old_h6['light_facts']
        diagonal_relative = _difference(runtime.h6['p6_shell'].diagonal, old_h6['p6_shell'].diagonal)
        assert diagonal_relative <= 1e-10
        positive_source = _vector(runtime.levels['spaces'][6], 7)
        vectors.append(positive_source)
        positive_source.array[runtime.levels['floquets'][6].mpc.slaves] = 0
        old_value = old_h6['h6'].apply(positive_source)
        new_value = runtime.h6['h6'].apply(positive_source)
        vectors.extend((old_value, new_value))
        h6_relative = _difference(new_value, old_value)
        assert h6_relative <= 1e-10
        report['h6_diagonal_relative'] = diagonal_relative
        report['h6_apply_relative'] = h6_relative
        report['h6_power_history_relative'] = float(np.linalg.norm(
            np.asarray(runtime.h6['light_facts']['power_history'])-
            np.asarray(old_h6['light_facts']['power_history']))/
            np.linalg.norm(old_h6['light_facts']['power_history']))
        assert report['h6_power_history_relative'] <= 1e-10
        report['aq_projection'] = _native_aq_projection_check(runtime)
        assert report['aq_projection']['passed']
        rhs = _vector(runtime.levels['spaces'][4], 1)
        vectors.append(rhs)
        rhs.array[runtime.levels['floquets'][4].mpc.slaves] = 0
        correction = runtime.p4_ledger.solve(rhs)
        vectors.append(correction)
        report['p4_return'] = dict(runtime.p4_ledger.last_audit)
        assert report['p4_return']['status'] == 'P4_RETURN_PASS'
        # The port RHS witness is the actual nonzero augmented matrix. It is
        # reported separately from the independent complete native A4 gate.
        matrix = runtime.p4_system.matrix
        augmented_rhs = matrix.createVecRight()
        augmented_rhs.set(0)
        augmented_rhs.array[-runtime.mode_count:] = 0.01+0.02j
        augmented_solution = augmented_rhs.duplicate()
        augmented_residual = augmented_rhs.duplicate()
        vectors.extend((augmented_rhs, augmented_solution, augmented_residual))
        runtime.p4_factor.solve_repeated(augmented_rhs, augmented_solution)
        matrix.mult(augmented_solution, augmented_residual)
        augmented_residual.axpy(-1, augmented_rhs)
        report['explicit_port_rhs_condensed_residual'] = float(augmented_residual.norm()/augmented_rhs.norm())
        assert report['explicit_port_rhs_condensed_residual'] <= 1e-10
        length = runtime.p6_system.active_rows+runtime.mode_count
        source = np.sin(.019*(np.arange(length)+1))+1j*.13*np.cos(.029*(np.arange(length)+1))
        pcs = []
        for repeat in range(3):
            started = perf_counter()
            value = bridge.apply(source)
            assert np.all(np.isfinite(value))
            pcs.append({'repeat': repeat, 'wall_seconds': perf_counter()-started,
                'bal_h': runtime.bal_h.last_apply_facts,
                'coarse_corrections': list(runtime.coarse_timings)})
        report['fixed_rhs_pc_repeats'] = pcs
        report['factor_counts'] = runtime.p4_ledger._factor_counts()
        assert report['factor_counts']['symbolic_calls'] == report['factor_counts']['numeric_calls'] == 1
        try:
            from threadpoolctl import threadpool_info
            report['math_libraries'] = threadpool_info()
        except ImportError:
            report['math_libraries'] = None
        report['actual_task_threads'] = len(list(Path('/proc/self/task').iterdir()))
        from src.runners.math_backend_identity import math_backend_identity
        report['math_backend_readback'] = math_backend_identity()
        report['status'] = 'COMPONENT_PASS'
        save('component_pass')
    except BaseException as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        save('failed')
        raise
    finally:
        for vector in reversed(vectors):
            vector.destroy()
        if old_h6 is not None:
            old_h6['h6'].destroy()
            old_h6['p6_shell'].destroy()
        if runtime is not None:
            runtime.destroy()
