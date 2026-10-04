"""Opt-in bounded real FE/MPC p6-to-p3 component witnesses only."""
import hashlib
import importlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import pytest
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

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
pytestmark = pytest.mark.skipif(os.environ.get('TASK39EXTRA_P3_ACTUAL_COMPONENTS') != '1',
                               reason='explicit bounded p6-to-p3 real FE/MPC component campaign only')
PORT_CACHE_ROLES = ('Bi', 'Bt', 'Di', 'Dt', 'Bhat', 'Dhat', 'XiB', 'Hlocal')


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


def _process_memory_bytes():
    values = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        key, separator, rest = line.partition(':')
        if separator and key in {'VmRSS', 'VmHWM', 'VmSwap'}:
            values[key] = int(rest.strip().split()[0]) * 1024
    return values


def _array_root(array):
    root = array
    while isinstance(getattr(root, 'base', None), np.ndarray):
        root = root.base
    base = getattr(root, 'base', None)
    if base is None:
        return id(root), int(root.nbytes)
    try:
        nbytes = int(memoryview(base).nbytes)
    except TypeError:
        nbytes = int(root.nbytes)
    return id(base), nbytes


def _port_cache_inventory(action):
    roles = {
        name: [getattr(cell, name) for cell in action._cells]
        for name in PORT_CACHE_ROLES
    }
    roles.update(Hp=[action._H_p], Hhat=[action._Hhat])
    all_arrays = [array for arrays in roles.values() for array in arrays]
    role_facts = {}
    for name, arrays in roles.items():
        by_shape = {}
        object_bytes = {}
        roots = {}
        for array in arrays:
            if not isinstance(array, np.ndarray):
                raise TypeError(f'{name} cache entry is not an ndarray')
            key = f'{tuple(int(value) for value in array.shape)}|{array.dtype}'
            item = by_shape.setdefault(key, {
                'references': 0, 'referenced_nbytes_sum_overlapping': 0,
                'unique_object_ids': set(), 'unique_object_nbytes': 0,
                'unique_backing_root_ids': set(), 'unique_backing_root_nbytes': 0,
            })
            item['references'] += 1
            item['referenced_nbytes_sum_overlapping'] += int(array.nbytes)
            if id(array) not in item['unique_object_ids']:
                item['unique_object_ids'].add(id(array))
                item['unique_object_nbytes'] += int(array.nbytes)
            root_id, root_nbytes = _array_root(array)
            if root_id not in item['unique_backing_root_ids']:
                item['unique_backing_root_ids'].add(root_id)
                item['unique_backing_root_nbytes'] += root_nbytes
            object_bytes[id(array)] = int(array.nbytes)
            roots[root_id] = root_nbytes
        role_facts[name] = {
            'array_references': len(arrays),
            'referenced_nbytes_sum_overlapping': sum(int(a.nbytes) for a in arrays),
            'unique_ndarray_objects': len(object_bytes),
            'unique_ndarray_object_nbytes': sum(object_bytes.values()),
            'unique_backing_roots': len(roots),
            'unique_backing_root_nbytes': sum(roots.values()),
            'value_scan': 'NOT_READ',
            'shape_histogram': [
                {
                    'shape_dtype': key,
                    'references': value['references'],
                    'referenced_nbytes_sum_overlapping': value['referenced_nbytes_sum_overlapping'],
                    'unique_ndarray_objects': len(value['unique_object_ids']),
                    'unique_ndarray_object_nbytes': value['unique_object_nbytes'],
                    'unique_backing_roots': len(value['unique_backing_root_ids']),
                    'unique_backing_root_nbytes': value['unique_backing_root_nbytes'],
                }
                for key, value in sorted(by_shape.items())
            ],
        }
    global_objects = {id(array): int(array.nbytes) for array in all_arrays}
    global_roots = {}
    for array in all_arrays:
        root_id, root_nbytes = _array_root(array)
        global_roots[root_id] = root_nbytes
    object_roles = {}
    root_roles = {}
    for name, arrays in roles.items():
        for array in arrays:
            object_roles.setdefault(id(array), set()).add(name)
            root_id, _ = _array_root(array)
            root_roles.setdefault(root_id, set()).add(name)
    terms = tuple(action._port_terms.values())
    hlocal_zero_by_construction = sum(
        index not in action._port_terms or action._port_terms[index].H is None
        for index in range(len(action._cells))
    )
    return {
        'scope': 'bounded 18-cell p6 real FE/MPC fixture; ndarray objects and backing roots deduplicated; reference nbytes overlap and is not RSS',
        'cell_count': len(action._cells),
        'input_term_count': len(terms),
        'cells_without_input_term': len(action._cells)-len(terms),
        'input_optional_none_counts': {
            key: sum(getattr(term, key) is None for term in terms)
            for key in ('Bt', 'Dt', 'H')
        },
        'Hlocal_semantics': 'H=None is normalized to a per-cell zero (np_,np_) array and merged into Hp; explicit H contributions remain supported by the existing noncommuting contract test.',
        'Hlocal_zero_by_construction_references': hlocal_zero_by_construction,
        'Hlocal_explicit_H_references': len(action._cells)-hlocal_zero_by_construction,
        'Hlocal_zero_semantics': 'Derived from the recorded source path: absent term or term.H is None causes _normalise_port_terms to allocate np.zeros((np_,np_)); no large array values were scanned.',
        'roles': role_facts,
        'cross_role_unique_ndarray_objects': len(global_objects),
        'cross_role_unique_ndarray_object_nbytes': sum(global_objects.values()),
        'cross_role_unique_backing_roots': len(global_roots),
        'cross_role_unique_backing_root_nbytes': sum(global_roots.values()),
        'ndarray_objects_shared_between_roles': sum(len(names) > 1 for names in object_roles.values()),
        'backing_roots_shared_between_roles': sum(len(names) > 1 for names in root_roles.values()),
    }


def _install_stage_timers(monkeypatch, report):
    calls = report.setdefault('setup_call_timings', [])

    def wrap(module_name, attribute, name_for_call):
        module = importlib.import_module(module_name)
        original = getattr(module, attribute)

        def measured(*args, **kwargs):
            name = name_for_call(*args, **kwargs)
            started_wall = perf_counter()
            started_cpu = process_time()
            try:
                return original(*args, **kwargs)
            finally:
                calls.append({
                    'stage': name,
                    'wall_seconds': perf_counter()-started_wall,
                    'process_cpu_seconds': process_time()-started_cpu,
                    'clock_scope': 'this single-process component test; nested timed children are not additive to parents',
                })

        monkeypatch.setattr(module, attribute, measured)

    wrap('src.solvers.fullspace_same_mesh_hcurl_pmg_global', '_build_same_mesh_levels',
         lambda cfg, comm, degrees, **kwargs: f'mesh_spaces_floquet_p{degrees}')
    wrap('src.solvers.fullspace_physical_intermediate_runtime', 'fine_volume_quadrature_metadata',
         lambda *_args, **_kwargs: 'fine_volume_quadrature_metadata')
    wrap('src.solvers.fullspace_same_mesh_hcurl_pmg_physical', 'build_same_mesh_physical_action',
         lambda _levels, _cfg, degree, **_kwargs: f'native_physical_action_A{degree}')

    packed_call = {'count': 0}

    def packed_name(*_args, **kwargs):
        packed_call['count'] += 1
        degree = int(kwargs.get('degree', 6))
        return f'packed_pc_physical_action_A{degree}_call{packed_call["count"]}'

    wrap('src.solvers.physical_equivalent_fast', 'build_packed_physical_action', packed_name)
    compile_call = {'count': 0}

    def compile_name(*_args, **_kwargs):
        compile_call['count'] += 1
        return 'compile_native_volume_form_p6' if compile_call['count'] == 1 else 'compile_native_volume_form_A3'

    wrap('src.runners.physical_retained_condensed_v20', '_compile_volume_form', compile_name)

    assembly_call = {'count': 0}

    def assembly_name(*_args, **kwargs):
        assembly_call['count'] += 1
        action_only = kwargs.get('materialize_global_matrix', True) is False
        operator = 'p6_action_only' if action_only else 'coarse_A3_matrix'
        return f'condensation_assembly_{operator}_call{assembly_call["count"]}'

    wrap('src.runners.physical_retained_condensed_v20',
         'build_unconstrained_assembly_time_condensation', assembly_name)
    wrap('src.runners.physical_retained_condensed_v20', 'assemble_condensed_ports',
         lambda *_args, **_kwargs: 'assemble_coarse_A3_ports')
    wrap('src.runners.physical_retained_condensed_v20',
         'build_p6_cell_condensed_action_from_carrier',
         lambda *_args, **_kwargs: 'build_p6_cell_carrier_action_and_port_caches')
    wrap('src.runners.physical_retained_condensed_v20', '_support_groups',
         lambda *_args, **_kwargs: 'map_A3_port_support_groups')
    wrap('src.solvers.physical_light_setup', 'build_light_h6_setup',
         lambda *_args, **_kwargs: 'build_reference_metric_direct_natural_H6')
    wrap('src.solvers.fullspace_same_mesh_hcurl_pmg_runtime',
         'build_same_mesh_hcurl_owner_transfer',
         lambda *_args, **_kwargs: 'build_owner_transfer_P63')

    gram_module = importlib.import_module('src.solvers.hcurl_blocked_gram_tensor')
    original_gram = gram_module.HcurlBlockedGramTensor
    gram_call = {'count': 0}

    class TimedBlockedGram(original_gram):
        def __init__(self, *args, **kwargs):
            gram_call['count'] += 1
            started_wall = perf_counter()
            started_cpu = process_time()
            try:
                super().__init__(*args, **kwargs)
            finally:
                calls.append({
                    'stage': f'construct_blocked_gram_call{gram_call["count"]}',
                    'wall_seconds': perf_counter()-started_wall,
                    'process_cpu_seconds': process_time()-started_cpu,
                    'clock_scope': 'this single-process component test; nested timed children are not additive to parents',
                })

    monkeypatch.setattr(gram_module, 'HcurlBlockedGramTensor', TimedBlockedGram)


@pytest.mark.parametrize('wavelength', [5, 2])
def test_p3_actual_material_full_ports_tensor_action_recovery_and_c(wavelength, monkeypatch):
    if os.environ.get('TASK39EXTRA_P3_COMPONENT_WAVELENGTH') not in (None, str(wavelength)):
        pytest.skip('another wavelength selected for this process')
    specification = load_and_resolve(ROOT/('input/task39extra_para_workstation_capacity/'+
                                    f'v6_{wavelength}nm_p3_'+('full.dat' if wavelength == 5 else 'pilot16.dat')))
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    small = replace(cfg, mesh_axis_cell_counts=(3, 2, 3), mesh_axis_x_values=None,
        mesh_axis_y_values=None, mesh_axis_z_values=None, mesh_axis_z_profile=None,
        mesh_plan_id=None, mesh_plan_sha256=None)
    identity = specification.solver['preconditioner']
    options = native_profile_facts(identity)['component_options']
    runtime = None
    vectors = []
    report = {'wavelength_nm': wavelength, 'fixture_cells': 18,
        'full_input_sha256': specification.input_sha256,
        'full_physical_sha256': specification.physical_model_sha256,
        'resolved_coarse_degree': int(specification.solver['coarse_degree']),
        'coarse_operator': 'A3',
        'full_mesh_counts': None,
        'scope': 'bounded FE/MPC with all physical port modes; not a full PDE or resource qualification',
        'threads': {name: os.environ.get(name) for name in (
            'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
            'BLIS_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
        )},
        'affinity_readback': sorted(os.sched_getaffinity(0)), 'stages': [], 'tensor_witness': []}
    report['timer_contract'] = {
        'wall_clock': 'time.perf_counter monotonic elapsed seconds',
        'process_cpu_clock': 'time.process_time process CPU seconds for this test process; not child-process CPU',
        'parent_child_rule': 'build and marker intervals contain timed calls; nested parent/child timings are reported separately and must not be summed',
    }
    report['workspace_source_identity'] = os.environ.get(
        'TASK39EXTRA_P3_SOURCE_IDENTITY', 'NOT_SUPPLIED_BY_TEST_WRAPPER'
    )
    directory = Path(os.environ.get('TASK39EXTRA_P3_COMPONENT_OUTPUT', ROOT/'tmp/p3_mid_order_0p7/components'))
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/f'p3_actual_{wavelength}nm_18cell_mpi1_math1.json'
    _install_stage_timers(monkeypatch, report)
    report['process_memory_before_build'] = _process_memory_bytes()

    def save(stage, facts=None):
        report['stages'].append({
            'stage': stage,
            'monotonic': perf_counter(),
            'process_cpu_seconds': process_time(),
            'facts': facts,
        })
        output.write_text(json.dumps(_jsonable(report), sort_keys=True, allow_nan=False)+'\n')
        print(f'P3_COMPONENT {wavelength}nm {stage}', flush=True)

    try:
        save('build_started')
        started = perf_counter()
        started_cpu = process_time()
        runtime = RetainedCondensedRuntime.build(small, MPI.COMM_SELF,
            sum_factorized_work=True, geometry_identity_policy='rounded_12_representative',
            component_options=options, coarse_degree=3, profile_identity=identity,
            marker=lambda name, facts: save(name))
        report['build_seconds'] = perf_counter()-started
        report['build_process_cpu_seconds'] = process_time()-started_cpu
        interval_events = {
            row['stage']: row for row in report['stages']
            if row['stage'] in {
                'retained_volume_quadrature_metadata_complete',
                'retained_sum_factorized_physical_action_complete',
            }
        }
        interval_start = interval_events.get('retained_volume_quadrature_metadata_complete')
        interval_end = interval_events.get('retained_sum_factorized_physical_action_complete')
        report['same_shape_setup_hot_interval'] = {
            'start_marker': 'retained_volume_quadrature_metadata_complete',
            'end_marker': 'retained_sum_factorized_physical_action_complete',
            'parent_wall_seconds': (
                interval_end['monotonic']-interval_start['monotonic']
                if interval_start is not None and interval_end is not None else None
            ),
            'parent_process_cpu_seconds': (
                interval_end['process_cpu_seconds']-interval_start['process_cpu_seconds']
                if interval_start is not None and interval_end is not None else None
            ),
            'direct_timed_children': [
                item for item in report['setup_call_timings']
                if item['stage'] in {
                    'fine_volume_quadrature_metadata',
                    'native_physical_action_A6',
                    'native_physical_action_A3',
                    'packed_pc_physical_action_A6_call1',
                }
            ],
            'scope_note': '18-cell fixture only; parent includes the measured calls and other runtime work; do not extrapolate as a TB speedup.',
        }
        assert runtime.mode_count == (600 if wavelength == 5 else 3904)
        report['mode_count'] = runtime.mode_count
        report['mode_sha256'] = runtime.mode_sha256
        report['p6_build'] = runtime.p6_system.build_audit
        report['coarse_build'] = runtime.p4_system.build_audit
        report['coarse_operator'] = {
            'degree': runtime.coarse_degree,
            'name': 'A3',
            'p4_internal_names_are_compatibility_aliases': True,
        }
        assert runtime.coarse_degree == 3
        report['p6_port_cache_inventory'] = _port_cache_inventory(runtime.p6_action)
        report['process_memory_after_build'] = _process_memory_bytes()
        p2_compact_path = ROOT/'docs/task39extra_para_workstation_capacity/outcomes/records/v6_2nm_16step_pilot.json'
        p2_compact = json.loads(p2_compact_path.read_text())
        report['accepted_p2_cache_reference'] = {
            'path': str(p2_compact_path.relative_to(ROOT)),
            'sha256': hashlib.sha256(p2_compact_path.read_bytes()).hexdigest(),
            'unique_cache_bytes': p2_compact['runtime_control']['p6_buffer_inventory_unique_cache_bytes'],
            'unique_port_cache_bytes': p2_compact['runtime_control']['p6_buffer_inventory_unique_port_cache_bytes'],
            'local_carrier_cell_payload_bytes': p2_compact['runtime_control']['p6_buffer_inventory_local_carrier_cell_payload_bytes'],
            'scope': p2_compact['runtime_control']['buffer_inventory_scope'],
            'overlap_note': p2_compact['runtime_control']['buffer_inventory_overlap_note'],
            'actual_large_run_shape_breakdown': 'NOT_SAVED_BY_ORIGINAL_PRODUCER',
        }
        main_capacity_path = ROOT/'tmp/p3_main_review/p3_initial_route_capacity_review_v1.json'
        if main_capacity_path.is_file():
            main_capacity = json.loads(main_capacity_path.read_text())
            capacity_cases = {
                item['case']: {
                    'cell_count': item['cell_count'],
                    'port_channels': item['port_channels'],
                    'p3_retained_rows': item['degrees']['3']['retained_trace_plus_port_rows'],
                    'p4_retained_rows': item['degrees']['4']['retained_trace_plus_port_rows'],
                    'p3_over_p4_row_ratio': item['p3_over_p4_retained_row_ratio'],
                    'p6_65_complex128_vectors_payload_bytes': item['p6_65_complex128_vectors_payload_bytes'],
                    'one_global_M_squared_complex128_array_payload_bytes': item['one_global_M_squared_complex128_array_payload_bytes'],
                }
                for item in main_capacity['derived_rows_and_array_payloads']
            }
            report['main_readonly_capacity_crosscheck'] = {
                'path': str(main_capacity_path.relative_to(ROOT)),
                'sha256': hashlib.sha256(main_capacity_path.read_bytes()).hexdigest(),
                'cases': capacity_cases,
                'scope': 'derived row/vector payload cross-check only; not RSS/fill/factor prediction',
            }
        p6_h6_path = ROOT/'docs/task39extra_para_workstation_capacity/outcomes/records/v6_component_and_h6_only.json'
        p6_h6 = json.loads(p6_h6_path.read_text())
        prior = next(row for row in p6_h6['components'] if row['wavelength_nm'] == wavelength)
        assert prior['status'] == 'COMPONENT_PASS'
        assert prior['physical_model_sha256'] == specification.physical_model_sha256
        prior_source_identity = p6_h6['component_source_identity']
        prior_source_identity_path = Path(prior_source_identity['path'])
        assert hashlib.sha256(prior_source_identity_path.read_bytes()).hexdigest() == prior_source_identity['sha256']
        prior_component_log = p6_h6['component_log']
        prior_component_log_path = Path(prior_component_log['path'])
        assert hashlib.sha256(prior_component_log_path.read_bytes()).hexdigest() == prior_component_log['sha256']
        prior_source_identity_json = json.loads(prior_source_identity_path.read_text())
        old_test_path = 'src/test/test_task39extra_v6_actual_components.py'
        old_test_identity = next(item for item in prior_source_identity_json['files']
                                 if item['path'] == old_test_path)
        current_old_test_path = ROOT/old_test_path
        current_old_test_sha = hashlib.sha256(current_old_test_path.read_bytes()).hexdigest()
        h6_source_sha = p6_h6['h6_only']['manifest_identity']['source_sha']
        p6_h6_unchanged_paths = (
            'src/solvers/p6_cell_condensed_action.py',
            'src/solvers/physical_light_setup.py',
            'src/solvers/fullspace_physical_intermediate_runtime.py',
            'src/solvers/hcurl_assembly_time_condensation.py',
        )
        p6_h6_file_identities = {}
        for relative in p6_h6_unchanged_paths:
            baseline_bytes = subprocess.check_output(['git', 'show', f'HEAD:{relative}'])
            h6_source_bytes = subprocess.check_output(['git', 'show', f'{h6_source_sha}:{relative}'])
            current_bytes = (ROOT/relative).read_bytes()
            baseline_sha = hashlib.sha256(baseline_bytes).hexdigest()
            h6_source_sha256 = hashlib.sha256(h6_source_bytes).hexdigest()
            current_sha = hashlib.sha256(current_bytes).hexdigest()
            assert current_sha == baseline_sha == h6_source_sha256
            p6_h6_file_identities[relative] = {
                'h6_run_source_sha': h6_source_sha,
                'h6_run_source_file_sha256': h6_source_sha256,
                'baseline_sha256': baseline_sha,
                'current_sha256': current_sha,
                'identical_across_h6_source_baseline_and_current': True,
            }
        explicit_h_test = ROOT/'src/test/test_task039extra_v20_noncommuting_contract.py'
        report['prior_p6_h6_evidence'] = {
            'path': str(p6_h6_path.relative_to(ROOT)),
            'sha256': hashlib.sha256(p6_h6_path.read_bytes()).hexdigest(),
            'component_source_identity_record': {
                'path': str(prior_source_identity_path.relative_to(ROOT)),
                'sha256': prior_source_identity['sha256'],
                'base_head': prior_source_identity_json['base_head'],
                'patch_sha256': prior_source_identity_json['patch_sha256'],
                'scope': prior_source_identity_json['scope'],
            },
            'component_log_record': {
                'path': str(prior_component_log_path.relative_to(ROOT)),
                'sha256': prior_component_log['sha256'],
                'bytes': prior_component_log['bytes'],
                'result': p6_h6['component_test_result'],
            },
            'component_test_source_record': {
                'path': old_test_path,
                'captured_working_sha256': old_test_identity['working_sha256'],
                'current_worktree_sha256': current_old_test_sha,
                'same_bytes_as_historical_component_test': current_old_test_sha == old_test_identity['working_sha256'],
                'note': 'Historical test identity comes from the bound source_identity.json; a different current path hash is not substituted for it.',
            },
            'source_identity': prior_source_identity,
            'mode_count': prior['mode_count'],
            'mode_sha256': prior['mode_sha256'],
            'input_sha256': prior['input_sha256'],
            'physical_model_sha256': prior['physical_model_sha256'],
            'status': prior['status'],
            'p6_tensor_witness_relative': prior['tensor_max_relative_by_degree']['6'],
            'p6_full_action_relative': prior['full_action_relative']['6'],
            'h6_diagonal_relative': prior['h6_diagonal_relative'],
            'h6_apply_relative': prior['h6_apply_relative'],
            'h6_power_history_relative': prior['h6_power_history_relative'],
            'current_unchanged_p6_h6_source_files': p6_h6_file_identities,
            'p3_metadata_and_integration_changes_excluded_from_unchanged_fine_math_identity': [
                'src/io/native_capacity_profile.py',
                'src/io/input_schema.py',
                'src/io/input_validation.py',
                'src/runners/physical_retained_condensed_v20.py',
                'src/runners/task038_launcher.py',
                'benchmarks/physical_intermediate_checker.py',
            ],
            'explicit_H_semantics_test': {
                'path': str(explicit_h_test.relative_to(ROOT)),
                'sha256': hashlib.sha256(explicit_h_test.read_bytes()).hexdigest(),
                'witness': 'P6CellPortTerms supplies Bt, Dt and explicit nonzero H in _problem()',
                'scope': 'source-bound unit algebra witness; no production H-zero policy change',
            },
            'scope': 'hash reference for prior p6/H6 math witnesses plus unchanged p6/H6 source modules; no native p6 tensor or H6 duplicate witness in this new p3 fixture',
        }
        assert prior['mode_count'] == (600 if wavelength == 5 else 3904)
        assert prior['mode_sha256'] == runtime.mode_sha256
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
        report['native_tensor_witness_scope'] = (
            'fresh independent FFCx witness for the newly selected A3; '
            'the unchanged p6 tensor witness is hash-referenced from accepted V6 evidence'
        )
        for degree, bundle, system in ((3, runtime.p4, runtime.p4_system),):
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
                started_cpu = process_time()
                native = _tabulate_raw_tensor_class(form, kernels, coordinates,
                    tag=item['material_tag'], dimension=space.element.space_dimension)
                native_seconds = perf_counter()-started
                native_process_cpu_seconds = process_time()-started_cpu
                candidate = gram(form, kernels, coordinates,
                    tag=item['material_tag'], dimension=space.element.space_dimension)
                relative = float(np.linalg.norm(candidate-native)/np.linalg.norm(native))
                assert relative <= 1e-10
                report['tensor_witness'].append({'degree': degree, 'tag': item['material_tag'],
                    'widths': item['cell_widths'], 'relative': relative, 'native_seconds': native_seconds,
                    'native_process_cpu_seconds': native_process_cpu_seconds,
                    'native_sha256': hashlib.sha256(native.tobytes()).hexdigest()})
                save(f'p{degree}_native_tensor_witness')
        report['action_relative'] = {}
        for degree, native, fast in ((6, runtime.fine['physical_action'], runtime.pc_physical['physical_action']),
                                     (3, runtime.p4['physical_action'], runtime.fast_a4['physical_action'])):
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
        def component_sample():
            memory = _process_memory_bytes()
            return {
                'icntl23': 0,
                'reference_memory_admission': 'measured_rss',
                'launch_cap_bytes': 1_300_000_000_000,
                'rss_bytes': memory['VmRSS'],
                'swap_bytes': memory.get('VmSwap', 0),
                'all_status_readable': 'VmRSS' in memory,
                'swap_policy': 'observe_only',
                'resource_stop_policy': 'measured_tree_rss_only_v3',
            }

        report['process_memory_before_factor'] = _process_memory_bytes()
        factor = runtime.attach_p4_factor(
            sample=component_sample,
            marker=lambda name, facts: save(name, facts),
        )
        report['factor'] = factor
        bridge = runtime.build_bal_h(marker=lambda name, facts: save(name, facts))
        transfer_audit = dict(runtime.transfer_owner.audit)
        assert (
            transfer_audit['trace_map_policy']
            == options['same_mesh_trace_map_policy']
        )
        assert transfer_audit['trace_rows_replaced_per_local_map'] == 432
        assert transfer_audit['trace_interior_rows_retained_per_local_map'] == 450
        assert transfer_audit['primal_and_adjoint_derive_from_same_candidate_matrix']
        orientation_cache = transfer_audit['trace_policy_orientation_cache']
        assert orientation_cache
        assert all(
            item['trace_map_policy'] == options['same_mesh_trace_map_policy']
            and item['gate_passed'] is True
            and item['candidate_vs_unmodified_independent_max_abs'] <= 1e-11
            and item['edge_functional_relative'] <= 1e-11
            and item['gradient_commuting_relative'] <= 1e-11
            and item['curl_commuting_relative'] <= 1e-11
            and item['adjoint_work_relative'] <= 1e-11
            for item in orientation_cache
        )
        report['same_mesh_transfer_audit'] = transfer_audit
        report['h6_candidate'] = runtime.h6['light_facts']
        aq_started = perf_counter()
        aq_started_cpu = process_time()
        report['aq_projection'] = _native_aq_projection_check(runtime)
        report['aq_projection_wall_seconds'] = perf_counter()-aq_started
        report['aq_projection_process_cpu_seconds'] = process_time()-aq_started_cpu
        assert report['aq_projection']['passed']
        interior_dofs = np.unique(np.concatenate([
            cell.interior_original_dofs for cell in runtime.p4_system.cell_recovery_maps
        ])).astype(np.int64)
        rhs = PETSc.Vec().createMPI(
            (runtime.p4_system.full_rows, runtime.p4_system.full_rows), comm=MPI.COMM_SELF
        )
        rhs.set(0)
        indices = interior_dofs.astype(np.float64)+1.0
        rhs.getArray()[interior_dofs] = np.sin(0.071*indices)+1j*np.cos(0.043*indices)
        rhs.assemble()
        vectors.append(rhs)
        interior_rhs_norm = float(np.linalg.norm(rhs.getValues(interior_dofs)))
        assert interior_rhs_norm > 0.0
        carrier = runtime.p4['dtn_action'].carrier
        hdiag = np.asarray([complex(entry.normalization_h) for entry in carrier.entries], dtype=np.complex128)
        assert hdiag.shape == (runtime.mode_count,)
        assert np.isfinite(hdiag).all() and np.all(np.abs(hdiag) > 0.0)
        mode_index = np.arange(runtime.mode_count, dtype=np.float64)+1.0
        gp = 0.013*np.sin(0.017*mode_index)+1j*0.019*np.cos(0.023*mode_index)
        assert np.isfinite(gp).all() and np.linalg.norm(gp) > 0.0
        gamma = gp/hdiag
        t = np.zeros(runtime.p4_system.full_rows, dtype=np.complex128)
        for port, entry in enumerate(carrier.entries):
            rows = np.asarray(entry.coupling_rows, dtype=np.int64)
            values = np.asarray(entry.coupling_values, dtype=np.complex128)
            assert rows.shape == values.shape
            np.add.at(t, rows, values*gamma[port])
        slaves = np.asarray(runtime.levels['floquets'][3].mpc.slaves, dtype=np.int64)
        assert not len(slaves) or np.all(t[slaves] == 0.0)
        g = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128).copy()
        g_eff = g-t
        g_eff_vector = rhs.duplicate()
        g_eff_vector.getArray()[:] = g_eff
        g_eff_vector.assemble()
        vectors.append(g_eff_vector)
        reduced_rhs = runtime.p4_inverse._reduce_storage_rhs(g_eff_vector)
        try:
            reduced_port_rhs_norm = float(np.linalg.norm(
                np.asarray(reduced_rhs.getArray(readonly=True))[runtime.p4_system.active_rows:]
            ))
        finally:
            reduced_rhs.destroy()
        di_norm = float(sum(np.linalg.norm(term.Di) for term in runtime.p4_terms.values()))
        report['joint_original_augmented_rhs'] = {
            'interior_rhs_norm': interior_rhs_norm,
            'external_port_rhs_norm': float(np.linalg.norm(gp)),
            'hdiag_min_abs': float(np.min(np.abs(hdiag))),
            'hdiag_max_abs': float(np.max(np.abs(hdiag))),
            'hdiag_finite_nonzero': True,
            'B_gp_over_H_norm': float(np.linalg.norm(t)),
            'interior_induced_reduced_port_rhs_norm': reduced_port_rhs_norm,
            'sum_Di_frobenius_norms': di_norm,
            'coarse_internal_port_term_cells': len(runtime.p4_terms),
            'coarse_cells_with_port_terms': int(
                runtime.p4_system.build_audit['port_condensed_terms']['cells_with_port_terms']
            ),
            'zero_internal_port_coupling_is_valid_for_this_topology': (
                not runtime.p4_terms and di_norm == 0.0
            ),
            'induced_port_rhs_semantics': (
                'May be zero when the carrier has no interior port rows; external gp '
                'is represented by t=B*(gp/Hdiag) and g_eff=g-t.'
            ),
            'source_policy': 'g contains deterministic nonzero original FE interior forcing; gp is nonzero complex data for every channel; t=B*(gp/Hdiag); solve existing A3 ledger with g_eff=g-t',
            'source_equation': 'A3*c+t=g; Hdiag*alpha-D*c=gp; alpha=alpha_ledger+gp/Hdiag',
        }
        correction = runtime.p4_ledger.solve(g_eff_vector)
        vectors.append(correction)
        report['a3_return'] = dict(runtime.p4_ledger.last_audit)
        assert report['a3_return']['status'] == 'P4_RETURN_PASS'
        assert report['a3_return']['coarse_degree'] == 3
        assert report['a3_return']['coarse_operator'] == 'A3'
        assert report['a3_return']['p4_ledger_name_is_compatibility_alias'] is True
        ledger_alpha = np.asarray(runtime.p4_ledger.total_port_solution, dtype=np.complex128).copy()
        alpha = ledger_alpha+gamma
        native_a3_value = apply_owned(runtime.p4['physical_action'], correction)
        vectors.append(native_a3_value)
        native_a3 = np.asarray(native_a3_value.getArray(readonly=True), dtype=np.complex128)
        full_a3_residual = native_a3+t-g
        full_a3_relative = float(np.linalg.norm(full_a3_residual)/np.linalg.norm(g))
        d_times_c = np.zeros(runtime.mode_count, dtype=np.complex128)
        for port, entry in enumerate(carrier.entries):
            rows = np.asarray(entry.projection_rows, dtype=np.int64)
            values = np.asarray(entry.projection_values, dtype=np.complex128)
            d_times_c[port] = np.dot(values, correction.getValues(rows))
        port_residual = hdiag*alpha-d_times_c-gp
        port_relative = float(np.linalg.norm(port_residual)/np.linalg.norm(gp))
        report['joint_original_augmented_rhs'].update(
            alpha_norm=float(np.linalg.norm(alpha)),
            full_native_A3_relative_residual=full_a3_relative,
            original_port_relative_residual=port_relative,
            same_A3_factor_symbolic_numeric=runtime.p4_ledger._factor_counts(),
        )
        assert np.isfinite(full_a3_relative) and full_a3_relative <= 1.0e-10
        assert np.isfinite(port_relative) and port_relative <= 1.0e-10
        # The port RHS witness is the actual nonzero augmented matrix. It is
        # reported separately from the independent complete native A3 gate.
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
        fixed_pc_outputs = []
        for repeat in range(3):
            started = perf_counter()
            started_cpu = process_time()
            value = bridge.apply(source)
            assert np.all(np.isfinite(value))
            assert len(runtime.coarse_timings) == 2
            pcs.append({'repeat': repeat, 'wall_seconds': perf_counter()-started,
                'process_cpu_seconds': process_time()-started_cpu,
                'bal_h': runtime.bal_h.last_apply_facts,
                'coarse_corrections': list(runtime.coarse_timings)})
            fixed_pc_outputs.append(np.array(value, copy=True))
        report['fixed_rhs_pc_repeats'] = pcs
        artifact = directory/f'p3_pc_outputs_{wavelength}nm_18cell_mpi1_math1.npz'
        np.savez(artifact, outputs=np.stack(fixed_pc_outputs))
        report['fixed_pc_output_artifact'] = {
            'path': str(artifact.resolve()),
            'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
            'shape': [3, int(length)],
            'scope': 'bounded FE fixture only; capture and serialization outside PC timers',
        }
        report['factor_counts'] = runtime.p4_ledger._factor_counts()
        assert report['factor_counts']['symbolic_calls'] == report['factor_counts']['numeric_calls'] == 1
        report['process_memory_after_factor_and_c'] = _process_memory_bytes()
        try:
            from threadpoolctl import threadpool_info
            report['math_libraries'] = threadpool_info()
        except ImportError:
            report['math_libraries'] = None
        report['actual_task_threads'] = len(list(Path('/proc/self/task').iterdir()))
        from src.runners.math_backend_identity import math_backend_identity
        report['math_backend_readback'] = math_backend_identity()
        report['math_backend_interpretation'] = (
            'OPENBLAS/OMP env and OS task count are recorded independently; '
            'parallel_runtime is an OpenBLAS enum, not a thread count.'
        )
        report['process_memory_at_completion'] = _process_memory_bytes()
        report['status'] = 'COMPONENT_PASS'
        save('component_pass')
    except BaseException as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        save('failed')
        raise
    finally:
        for vector in reversed(vectors):
            vector.destroy()
        if runtime is not None:
            runtime.destroy()
