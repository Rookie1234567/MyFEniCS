"""Stdlib-only saved X/XZ checker gates; no numerical or FE execution."""
from pathlib import Path
import ast
import copy
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT if (ROOT/'.git').exists() else ROOT.parents[2]/'repo'


def module(name):
    spec = importlib.util.spec_from_file_location('_XZ_checker_'+name, ROOT/'benchmarks'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


checker = module('check_y_orbit_direct_probe')
generic = module('check_y_orbit_quotient_probe')


def fixture_functions():
    tree = ast.parse((REPO/'src/test/test_y_orbit_direct_pipeline_metadata.py').read_text())
    scope = {'checker': checker, 'copy': copy}
    names = {'profile', 'report', 'artifacts', 'provenance', 'events'}
    exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in names], type_ignores=[]), '<existing stdlib X fixtures>', 'exec'), scope)
    return scope


def saved_report(stage='solve', name='XZ'):
    fixtures = fixture_functions()
    report = fixtures['report'](stage)
    metadata = checker.reviewed_direct_profile_metadata(name)
    report['direct_profile'] = name
    report['profile'] = json.loads(json.dumps(metadata.identity()))
    for block in report['reformed_blocks']:
        width = metadata.augmented_rows_per_q[block['q']]
        block['shape'] = [width, width]
    for block in report['direct_provider_blocks']:
        block['shape'] = [metadata.augmented_rows_per_q[block['global_p']],
                          metadata.augmented_rows_per_q[block['global_q']]]
    if stage == 'solve':
        report['factor']['input_blocks'] = copy.deepcopy(report['reformed_blocks'])
    report['artifacts'] = fixtures['artifacts'](report, stage)
    return report


def envelope(memory=3):
    required = memory*1024**3 + checker.RESERVE_BYTES
    return {'launch_cap_bytes': required, 'effective_available_bytes': required+4*1024**3,
        'effective_total_bytes': 16*1024**3, 'reserve_bytes': 4*1024**3,
        'cgroup_limits': [{'limit_bytes': 16*1024**3, 'current_bytes': 1024**3}]}


def admission(memory=3):
    return {'requested_memory_gib': memory, 'requested_tree_cap_bytes': memory*1024**3,
        'required_cap_plus_evidence_reserve_bytes': memory*1024**3+checker.RESERVE_BYTES,
        'fresh_memory_envelope': envelope(memory), 'launch_admission_passed': True}


def binding(name='XZ', stage='solve', research=True):
    fixtures = fixture_functions()
    report = saved_report(stage, name)
    provenance = fixtures['provenance'](report)
    provenance['direct_profile'] = name
    provenance['command'] = ['run.py', '--direct-profile', name]
    kwargs = {'checker_source': report['source'], 'checker_environment': report['environment'], 'stage': stage}
    if research:
        wall, memory = (1800, 2) if name == 'X' else (4500, 3)
        provenance['command'] += ['--research-wall-seconds', str(wall), '--research-memory-gib', str(memory)]
        provenance['resource_contract'].update(wall_seconds=wall, research_wall_seconds=wall,
            worker_phase_wall_seconds=wall-5.5, tree_cap_bytes=memory*1024**3, research_memory_gib=memory,
            requested_tree_cap_bytes=memory*1024**3, research_memory_launch_admission=admission(memory))
        kwargs.update(research_wall_seconds=wall, research_memory_gib=memory)
    return report, provenance, kwargs


class DirectXZCheckerMetadataTests(unittest.TestCase):
    def test_exact_existing_metadata_counts_and_axes(self):
        expected = (168, 35332, 33024, 18144, 14880, 84, 18364, 16512, 9072, 7440, 8256, 3720)
        fields = ('cell_count', 'storage_rows', 'independent_rows', 'interior_rows', 'trace_rows',
            'local_cell_count', 'local_storage_rows', 'local_independent_rows', 'local_interior_rows',
            'local_trace_rows', 'rows_per_q', 'trace_rows_per_q')
        profile = saved_report()['profile']
        self.assertEqual(tuple(profile[key] for key in fields), expected)
        self.assertEqual(profile['global_axes'][2], [value*(7/135) for value in (-10, 0, 20, 40, 80, 100, 120, 130)])
        self.assertEqual(profile['augmented_rows_per_q'], [3796, 3872, 3872, 3872])
        self.assertEqual(profile['q_port_counts'], [76, 152, 152, 152])
        self.assertEqual(profile['sector_port_counts'], [228, 304])
        self.assertTrue(checker.validate_profile(profile))
        self.assertTrue(checker.validate_profile(fixture_functions()['profile']()))
        for key, value in (('name', 'Y'), ('name', 'X'), ('dimensions', [6, 4, 8]), ('global_axes', []),
            ('storage_rows', 25468), ('local_storage_rows', 13236), ('rows_per_q', 5952),
            ('q_port_counts', [76]*4), ('complete_cell_dimension', 192), ('physical_mode_count', 531),
            ('factor_allowance_aggregate_bytes', 768*1024**2), ('evidence_reserve_bytes', 0)):
            bad = copy.deepcopy(profile); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): checker.validate_profile(bad)
        for name in ('other', None, 'same80', 'xz'):
            with self.assertRaises(ValueError): checker.reviewed_direct_profile_metadata(name)

    def test_scope_shapes_and_complete_four_q_two_local_inventory(self):
        for stage in ('prefactor', 'solve'):
            report = saved_report(stage)
            self.assertTrue(checker.validate_scope(report, stage))
            self.assertTrue(checker.validate_array_inventory(report, stage))
            shapes = checker.expected_array_shapes(report, stage)
            self.assertEqual(shapes['full_mpc_slaves'], [2308])
            self.assertEqual(shapes['full_mpc_offsets'], [35333])
            self.assertEqual(shapes['twist_1_slave_storage_rows'], [1852])
            if stage == 'solve':
                self.assertEqual(shapes['q_3_rhs_a'], [3872])
                self.assertEqual(shapes['aug_q_2_FE_rhs'], [33024])
                self.assertEqual(shapes['notch_physical_recovered_field'], [35332])
            for key in ('reformed_blocks', 'direct_provider_blocks'):
                bad = copy.deepcopy(report); bad[key].pop()
                with self.assertRaises(ValueError): checker.expected_array_shapes(bad, stage)
            bad = copy.deepcopy(report); bad['profile'] = fixture_functions()['profile']()
            with self.assertRaises(ValueError): checker.validate_scope(bad, stage)
            bad = copy.deepcopy(report); bad['artifacts']['independent_storage_rows']['shape'] = [23808]
            with self.assertRaises(ValueError): checker.validate_array_inventory(bad, stage)
        report = saved_report(); report['changed_cells'] = [0, 168]
        with self.assertRaises(ValueError): checker.validate_scope(report, 'solve')
        report = saved_report(); report['scope_flags']['candidate_full_Q_created'] = True
        with self.assertRaises(ValueError): checker.validate_scope(report, 'solve')

    def test_only_exact_combined_research_memory_pairs(self):
        self.assertEqual(checker.direct_memory_cap('X', 'solve', 1800, 2), 2*1024**3)
        self.assertEqual(checker.direct_memory_cap('XZ', 'solve', 4500, 3), 3*1024**3)
        for name in (None, 'X', 'XZ'):
            self.assertEqual(checker.direct_memory_cap(name, 'prefactor', None), checker.TREE_CAP_BYTES)
        self.assertEqual(checker.direct_memory_cap('X', 'solve', 1800), checker.TREE_CAP_BYTES)
        for stage in ('prefactor', 'solve'):
            for wall in (None, 600):
                self.assertEqual(checker.direct_memory_cap('XZ', stage, wall), checker.TREE_CAP_BYTES)
            with self.assertRaises(ValueError): checker.direct_memory_cap('XZ', stage, 4500)
        invalid = [('XZ', 'solve', 1800, 3), ('XZ', 'solve', 4500, 2), ('X', 'solve', 4500, 3),
            ('other', 'solve', 4500, 3), ('XZ', 'prefactor', 4500, 3), (None, 'solve', 4500, 3)]
        invalid += [('XZ', 'solve', wall, 3) for wall in (None, 600, True, 4500., '4500')]
        invalid += [('XZ', 'solve', 4500, memory) for memory in (True, 3., '3', 0, 4)]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError): checker.direct_memory_cap(*args)

    def test_launch_and_admission_require_explicit_XZ_and_fresh_headroom(self):
        kwargs = {'direct_profile': 'XZ', 'research_wall_seconds': 4500}
        self.assertTrue(checker.validate_direct_memory_launch(envelope(), research_memory_gib=3, **kwargs))
        self.assertTrue(checker.validate_direct_memory_admission(admission(), **kwargs))
        self.assertTrue(checker.validate_direct_memory_launch(envelope(2)))
        self.assertTrue(checker.validate_direct_memory_admission(admission(2)))
        for extras in ({}, {'direct_profile': 'XZ'}, {'research_wall_seconds': 4500},
            {'direct_profile': 'X', 'research_wall_seconds': 4500}, {'direct_profile': 'XZ', 'research_wall_seconds': 1800}):
            with self.assertRaises(ValueError): checker.validate_direct_memory_launch(envelope(), research_memory_gib=3, **extras)
            with self.assertRaises(ValueError): checker.validate_direct_memory_admission(admission(), **extras)
        for memory in (None, True, 3., '3'):
            with self.assertRaises(ValueError): checker.validate_direct_memory_launch(envelope(), research_memory_gib=memory, **kwargs)
        required = 3*1024**3+checker.RESERVE_BYTES
        for key in ('launch_cap_bytes', 'effective_available_bytes', 'effective_total_bytes'):
            bad = envelope(); bad[key] = required-1
            with self.assertRaises(ValueError): checker.validate_direct_memory_launch(bad, research_memory_gib=3, **kwargs)
        bad = envelope(); bad['cgroup_limits'] = [{'limit_bytes': required, 'current_bytes': 1}]
        with self.assertRaises(ValueError): checker.validate_direct_memory_launch(bad, research_memory_gib=3, **kwargs)
        for key, value in (('reserve_bytes', 4*1024**3-1), ('launch_cap_bytes', required+1)):
            bad = envelope(); bad[key] = value
            with self.assertRaises(ValueError): checker.validate_direct_memory_launch(bad, research_memory_gib=3, **kwargs)
            receipt = admission(); receipt['fresh_memory_envelope'] = bad
            with self.assertRaises(ValueError): checker.validate_direct_memory_admission(receipt, **kwargs)
        # Historical 2GiB launch admission retains its prior reserve behavior.
        old = envelope(2); old['reserve_bytes'] = 0
        self.assertTrue(checker.validate_direct_memory_launch(old))
        old = envelope(2); old['launch_cap_bytes'] += 1
        self.assertTrue(checker.validate_direct_memory_launch(old))
        for key, value in (('requested_memory_gib', 2), ('requested_tree_cap_bytes', 2*1024**3),
            ('required_cap_plus_evidence_reserve_bytes', 3*1024**3), ('launch_admission_passed', False), ('extra', True)):
            bad = admission(); bad[key] = value
            with self.assertRaises(ValueError): checker.validate_direct_memory_admission(bad, **kwargs)

    def test_exact_argv_resource_source_and_ABI_bindings(self):
        for name in ('X', 'XZ'):
            report, provenance, kwargs = binding(name)
            self.assertTrue(checker.validate_metadata_bindings(report, provenance, report['artifacts'], **kwargs))
        report, provenance, kwargs = binding()
        for key, value in (('wall_seconds', 1800), ('research_memory_gib', 2), ('swap_bytes', 1),
            ('factor_workspace_allowance_bytes', 768*1024**2), ('evidence_reserve_bytes', 0), ('mpi', 2),
            ('worker_phase_wall_seconds', 4501), ('performance_or_target_capacity_claim', True)):
            bad = copy.deepcopy(provenance); bad['resource_contract'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                checker.validate_metadata_bindings(report, bad, report['artifacts'], **kwargs)
        for command in (['run.py', '--direct-profile', 'X', '--research-wall-seconds', '4500', '--research-memory-gib', '3'],
            provenance['command']+['--research-memory-gib', '3'], provenance['command'][:-2]):
            bad = copy.deepcopy(provenance); bad['command'] = command
            with self.assertRaises(ValueError): checker.validate_metadata_bindings(report, bad, report['artifacts'], **kwargs)
        default = {'checker_source': report['source'], 'checker_environment': report['environment'], 'stage': 'solve'}
        with self.assertRaises(ValueError): checker.validate_metadata_bindings(report, provenance, report['artifacts'], **default)
        for stage in ('prefactor', 'solve'):
            report, provenance, kwargs = binding(stage=stage, research=False)
            self.assertTrue(checker.validate_metadata_bindings(report, provenance, report['artifacts'], **kwargs))

    def test_XZ_timing_phase_allocations_and_supervision(self):
        report, provenance, _ = binding()
        seconds = provenance['resource_contract']['worker_phase_wall_seconds']
        cap = 3*1024**3
        summary = {'classification': 'COMPLETED', 'leader_exit_code': 0, 'source_state': report['source'],
            'sampled_process_tree_swap_peak_bytes': 0, 'descendants_cleared': True,
            'process_tree_all_status_readable': True, 'process_tree_all_identity_complete': True,
            'sampled_process_tree_rss_peak_bytes': 2*1024**3, 'elapsed_seconds': 4400.,
            'time_reference_seconds': {'workflow': seconds}, 'global_swap_activity': {'delta': {'pswpin_pages': 0, 'pswpout_pages': 0}},
            'launch_envelope': {**envelope(), 'dynamic_launch_cap_bytes': envelope()['launch_cap_bytes'],
                'launch_cap_bytes': cap, 'tree_cap_bytes': cap, 'cap_policy': 'min(dynamic_memory_envelope, explicit_tree_cap)'}}
        kwargs = {'direct_profile': 'XZ', 'stage': 'solve', 'research_wall_seconds': 4500, 'research_memory_gib': 3}
        self.assertTrue(checker.validate_direct_supervision(summary, report['source'], maximum_wall=seconds, **kwargs))
        events = fixture_functions()['events'](report, 'solve')
        phase = {'research_wall_seconds': 4500, 'phase_wall_seconds': seconds, 'worker_elapsed_seconds': 4400.,
            'research_memory_gib': 3, 'requested_tree_cap_bytes': cap}
        for event in events:
            if event['event'] == 'allocation_admission':
                event.update(phase, launch_cap_bytes=cap, effective_tree_cap_bytes=cap, fresh_memory_envelope=envelope())
        self.assertTrue(checker.validate_research_timing(provenance, summary, events, phase,
            direct_profile='XZ', research_wall_seconds=4500))
        self.assertTrue(checker.validate_research_memory_resources(provenance, summary, events, phase, **kwargs))
        self.assertTrue(checker.validate_direct_event_contract(events, report, 'solve', research_wall_seconds=4500, research_memory_gib=3))
        for key, value in (('research_memory_gib', 2), ('phase_wall_seconds', 1800), ('evidence_reserve_bytes', 0),
            ('remaining_factor_allowance_bytes', 768*1024**2), ('effective_tree_cap_bytes', cap+1), ('admitted', False)):
            bad = copy.deepcopy(events); bad[4][key] = value
            if key == 'phase_wall_seconds':
                with self.assertRaises(ValueError): checker.validate_research_timing(provenance, summary, bad, phase,
                    direct_profile='XZ', research_wall_seconds=4500)
            else:
                with self.assertRaises(ValueError): checker.validate_research_memory_resources(provenance, summary, bad, phase, **kwargs)
        bad = copy.deepcopy(summary); bad['global_swap_activity']['delta']['pswpout_pages'] = 1
        with self.assertRaises(ValueError): checker.validate_direct_supervision(bad, report['source'], maximum_wall=seconds, **kwargs)

    def test_same_source_XZ_dispatch_and_no_cross_HEAD_waiver(self):
        report, _, _ = binding()
        source = report['source']
        with patch.dict(sys.modules, {'benchmarks.check_y_orbit_direct_probe': checker}):
            self.assertTrue(generic.admit_checker_output(source, copy.deepcopy(source), worker_directory='/tmp/worker',
                output_directory='/tmp/new', explicit_checker_directory=True, prior_checker_output=False, direct_profile='XZ'))
            changed = copy.deepcopy(source); changed['head'] = 'e'*40
            with self.assertRaises(ValueError): generic.admit_checker_output(source, changed, worker_directory='/tmp/worker',
                output_directory='/tmp/new', explicit_checker_directory=True, prior_checker_output=False, direct_profile='XZ')
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary); (path/'provenance.json').write_text(json.dumps({'direct_profile': 'XZ'}))
                with patch.object(checker, 'check_direct', return_value={'marker': 'dispatched'}) as dispatched:
                    self.assertEqual(generic.check(path, checker_source=source, checker_environment={}, stage='solve',
                        allocation_gate=lambda *args: None, research_wall_seconds=4500, research_memory_gib=3), {'marker': 'dispatched'})
                    self.assertEqual(dispatched.call_args.kwargs['research_memory_gib'], 3)
                (path/'provenance.json').write_text(json.dumps({'direct_profile': 'other'}))
                with self.assertRaises(ValueError): generic.check(path, checker_source=source, checker_environment={},
                    stage='solve', allocation_gate=lambda *args: None)

    def test_both_profiles_keep_exact7_and13_source_roles(self):
        tree = ast.parse((REPO/'src/test/test_y_orbit_direct_event_stream_metadata.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'DirectContextSourceRoleTests')
        scope = {'Path': Path, 'checker': checker, 'unittest': unittest, 'hashlib': __import__('hashlib')}
        exec(compile(ast.Module(body=[copy.deepcopy(cls)], type_ignores=[]), '<existing source fixture>', 'exec'), scope)
        fixture = scope['DirectContextSourceRoleTests']().fixture
        for name in ('X', 'XZ'):
            metadata = checker.reviewed_direct_profile_metadata(name)
            for role, count in (('full', 7), ('twist_0', 13), ('twist_1', 13)):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary); context, source = fixture(root, role)
                    if role != 'full':
                        quotient = context['y_orbit_quotient']; quotient['contract']['direct_profile'] = name
                        quotient.update(actual_local_cells=metadata.local_cell_count, actual_local_storage_rows=metadata.local_storage_rows)
                        quotient['contract_sha256'] = checker.digest_json(quotient['contract'])
                    kwargs = {'source_root': root, 'direct_profile': name}
                    self.assertEqual(len(checker.validate_context_source_role(role, context, source, **kwargs)), count)
                    bad = copy.deepcopy(context); bad['source_sha256']['extra.py'] = 'a'*64
                    with self.assertRaises(ValueError): checker.validate_context_source_role(role, bad, source, **kwargs)
                    if name == 'XZ' and role != 'full':
                        bad = copy.deepcopy(context); bad['y_orbit_quotient']['actual_local_storage_rows'] = 13236
                        with self.assertRaises(ValueError): checker.validate_context_source_role(role, bad, source, **kwargs)
                        with self.assertRaises(ValueError): checker.validate_context_source_role(role, context, source, source_root=root)

    def test_shared_storage_XZ_entity_counts_and_negative_inventory(self):
        tree = ast.parse((REPO/'src/test/test_y_orbit_shared_storage_metadata.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SharedStorageContracts')
        fixture = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'evidence')
        fixture = copy.deepcopy(fixture); fixture.args.args = []
        scope = {}; exec(compile(ast.Module(body=[fixture], type_ignores=[]), '<existing ownership fixture>', 'exec'), scope)
        evidence, descriptors = scope['evidence']()
        metadata = checker.reviewed_direct_profile_metadata('XZ')
        evidence.update(schema='task40extra.direct-shared-transform-equivalence.v1', direct_profile='XZ', same80_p4_only=False)
        for stage in evidence['owner_stages']:
            stage['stage'] = stage['stage'].replace('_unshared_overlap', '_streamed_controls_begin')
            stage['allocation_boundary'] = 'shared_owner_receipt_'+stage['stage']
        for role in evidence['roles']:
            ny = role['ny']; records = []; offset = 0; slot = 0; definitions = []
            for dimension, count, size in ((1, 138, 4), (2, 132, 24), (3, 42, 108)):
                for index in range(count): definitions.append((dimension, slot, size)); slot += size
            template = role['records'][0]
            for orbit in range(ny):
                for index, (dimension, first, size) in enumerate(definitions):
                    item = copy.deepcopy(template); item.update(orbit=orbit, base=[dimension, index], dimension=dimension,
                        first=first, size=size, rows_offset=offset, rows_count=size, template_id=f'template-000{dimension}',
                        borrower_record_index=len(records)+1)
                    records.append(item); offset += size
            role.update(records=records, full_rows=metadata.storage_rows if ny == 4 else metadata.local_storage_rows,
                width=8256, independent_rows=ny*8256, record_count=len(records), base_count=312)
        with patch.dict(sys.modules, {'benchmarks.check_y_orbit_direct_probe': checker}):
            self.assertTrue(generic.validate_shared_storage_metadata(evidence, descriptors, direct_profile='XZ'))
            self.assertEqual([role['record_count'] for role in evidence['roles']], [1248, 624, 624])
            for key, value in (('width', 5952), ('base_count', 228), ('full_rows', 25468), ('independent_rows', 23808)):
                bad = copy.deepcopy(evidence); bad['roles'][0][key] = value
                with self.assertRaises(ValueError): generic.validate_shared_storage_metadata(bad, descriptors, direct_profile='XZ')
            bad = copy.deepcopy(evidence); bad['roles'][1]['records'].pop()
            with self.assertRaises(ValueError): generic.validate_shared_storage_metadata(bad, descriptors, direct_profile='XZ')
            with self.assertRaises(ValueError): generic.validate_shared_storage_metadata(evidence, descriptors, direct_profile='Y')

    def test_same_physical_notch_box_derives_two_cells_in_each_profile(self):
        # Tiny dictionaries test only the saved checker's support policy. The
        # original all300-column source checker is replaced with a named stub.
        source_module = ModuleType('src.solvers.y_orbit_direct_operator_qualification')
        source_module._check_source = lambda source, **kwargs: {'cell_count': kwargs['metadata'].cell_count}
        for name, z_cell in (('X', 2), ('XZ', 3)):
            metadata = checker.reviewed_direct_profile_metadata(name)
            cells = []
            for x in range(metadata.nx):
                for y in range(metadata.ny):
                    for z in range(metadata.nz):
                        cells.append({'cell_index': len(cells), 'grid': [x, y, z], 'widths': [1, 1, 1], 'cell_info': 0,
                            'tag': 2, 'native_dofs': {}, 'native_coordinates': {}, 'canonical_ids': {}, 'canonical_map': {},
                            'oriented_tensor': {'numeric_sha256': 'a'*64}, 'raw_tensor': {}, 'complete_canonical_contribution': {}})
            regular = {'cells': cells, 'native': {}, 'entities': {}, 'interior_positions': {}, 'trace_positions': {}}
            notch = copy.deepcopy(regular)
            notch.update(role='notch', explicit_shared_entity_config_for_changed_material=True)
            changed = []
            for cell in notch['cells']:
                if cell['grid'] in ([3, 1, z_cell], [3, 2, z_cell]):
                    changed.append(cell['cell_index']); cell['tag'] = 1
                    cell['oriented_tensor']['numeric_sha256'] = 'b'*64
            config = {'tags': {'grating': 2, 'air': 1}}
            report = {'direct_profile': name, 'notch_original_volume_source': notch, 'changed_cells': changed,
                'physical_config': config, 'notch_config': {**config,
                    'air_void_box_nm': [value*(7/135) for value in (25, 33.5, 6.25, 18.75, 40, 80)]}}
            saved = SimpleNamespace(load=None, gate=None)
            with patch.dict(sys.modules, {source_module.__name__: source_module}):
                checks = []
                checker.check_notch_source(report, saved=saved, regular=regular, add=lambda *args: checks.append(args))
                self.assertEqual(len(changed), 2); self.assertEqual(len(checks), 1)
                bad = copy.deepcopy(report); bad['notch_config']['air_void_box_nm'][-1] += .1
                with self.assertRaises(ValueError): checker.check_notch_source(bad, saved=saved, regular=regular, add=lambda *args: None)
                bad = copy.deepcopy(report); bad['notch_original_volume_source']['cells'][0]['tag'] = 1
                with self.assertRaises(ValueError): checker.check_notch_source(bad, saved=saved, regular=regular, add=lambda *args: None)

    def test_static_math_stream_cutoffs_and_constructor_scope_preserved(self):
        tree = ast.parse((ROOT/'benchmarks/check_y_orbit_direct_probe.py').read_text())
        previous = ast.parse(subprocess.run(['git', '-C', str(REPO), 'show',
            '2a07d23d17b527675e6ae0b904c56121e258b4fc:benchmarks/check_y_orbit_direct_probe.py'],
            check=True, capture_output=True, text=True).stdout)
        def function(source, name):
            return next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == name)
        for name in ('load_direct_events', 'residual_representation_binding',
            'validate_gauss', 'validate_descriptor_metadata', 'validate_descriptor_payload', 'operation_error', 'relative'):
            self.assertEqual(ast.dump(function(tree, name)), ast.dump(function(previous, name)), name)
        solve, old_solve = function(tree, 'check_solve'), function(previous, 'check_solve')
        def residual_tail(source):
            outer = next(node for node in source.body if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple)
                and [getattr(item, 'id', '') for item in node.target.elts] == ['label', 'family', 'source_name', 'packet'])
            first = next(i for i, node in enumerate(outer.body) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'volume_source' for target in node.targets))
            return ast.dump(ast.Module(body=outer.body[first:], type_ignores=[]))
        self.assertEqual(residual_tail(solve), residual_tail(old_solve))
        # Ny/K/sector/role normalization is explicitly new and tested in the
        # Y production-policy suite. Protect every unchanged coefficient,
        # cutoff, independent kernel/Gauss, residual and output computation.
        def dump(nodes):
            return ast.dump(ast.Module(body=nodes if isinstance(nodes,list) else [nodes],type_ignores=[]))
        def assigned(node,name):
            return isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)
        def segment(body,start,end=None):
            first=next(i for i,node in enumerate(body) if start(node))
            last=len(body) if end is None else next(i+1 for i,node in enumerate(body) if i>=first and end(node))
            return body[first:last]
        raw,old_raw=function(tree,'check_raw_carriers'),function(previous,'check_raw_carriers')
        for name in ('dense','primary','literal','masks'):
            self.assertEqual(dump(function(raw,name)),dump(function(old_raw,name)),name)
        def roles(node):
            return next(n for n in node.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)
                and getattr(n.target.elts[0],'id',None)=='role_index')
        role_nodes=[roles(n) for n in (raw,old_raw)]
        def H_append(n):
            return isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='Hs' and n.value.func.attr=='append'
        self.assertEqual(dump(segment(role_nodes[0].body,lambda n:assigned(n,'binding'),H_append)),dump(segment(role_nodes[1].body,lambda n:assigned(n,'binding'),H_append)))
        def modes(node):
            return next(n for n in node.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)
                and [getattr(v,'id',None) for v in n.target.elts]==['index','original'])
        mode_nodes=[modes(n) for n in role_nodes]
        branches=[next(n for n in t.body if isinstance(n,ast.If) and ast.unparse(n.test)=='twist is None') for t in mode_nodes]
        self.assertEqual(dump(branches[0].body),dump(branches[1].body),'full incident and original C/D')
        self.assertEqual(dump(segment(branches[0].orelse,lambda n:assigned(n,'entry'),lambda n:isinstance(n,ast.For))),dump(segment(branches[1].orelse,lambda n:assigned(n,'entry'),lambda n:isinstance(n,ast.For))),'local stored C/D')
        def packets(node):
            first=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Tuple) and getattr(t.elts[0],'id',None)=='literal_packet' for t in n.targets))
            last=next(i for i,n in enumerate(node.body) if assigned(n,'branch'))
            return node.body[first+1:last]
        self.assertEqual(dump(packets(mode_nodes[0])),dump(packets(mode_nodes[1])),'primary literal mode/context')
        self.assertEqual(dump(segment(mode_nodes[0].body,lambda n:isinstance(n,ast.If) and ast.unparse(n.test)=='role not in contexts',lambda n:assigned(n,'H'))),dump(segment(mode_nodes[1].body,lambda n:isinstance(n,ast.If) and ast.unparse(n.test)=='role not in contexts',lambda n:assigned(n,'H'))),'component hash and finite H')
        def vectors(node):
            return next(n for n in node.body if isinstance(n,ast.For) and ast.unparse(n.target)=='name' and ast.unparse(n.iter)=="('C', 'D')")
        self.assertEqual(dump(vectors(mode_nodes[0])),dump(vectors(mode_nodes[1])),'primary literal vectors')
        def rank_tail(node):
            stage=next(n for n in node.orelse if isinstance(n,ast.For) and ast.unparse(n.target)=='stage')
            first=next(i for i,n in enumerate(stage.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Tuple) and [getattr(v,'id',None) for v in t.elts]==['C','D'] for t in n.targets))
            return stage.body[first:]
        self.assertEqual(dump(rank_tail(branches[0])),dump(rank_tail(branches[1])),'lift rank-one tail')
        def factor_body(node):
            factor=next(n for n in node.body if isinstance(n,ast.For) and any(assigned(v,'matrix') for v in n.body))
            return factor.body[1:]
        self.assertEqual(dump(factor_body(solve)),dump(factor_body(old_solve)),'factor numeric controls')
        allowed = {'__future__', 'hashlib', 'json', 'math', 'pathlib', 're'}
        for node in tree.body:
            if isinstance(node, ast.Import): self.assertTrue({alias.name for alias in node.names} <= allowed)
            elif isinstance(node, ast.ImportFrom): self.assertIn(node.module, allowed)
        forbidden = {'splu', 'spsolve', 'solve', 'build_fresh_direct_carriers', 'audit_direct_original_cell_contributions',
            '_build_same_mesh_levels', 'build_same_mesh_physical_action', 'SavedQuotientSnapshotAuthority', 'SavedFullP4Authority'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
                self.assertNotIn(name, forbidden)
        self.assertEqual((checker.TREE_CAP_BYTES, checker.FACTOR_ALLOWANCE_BYTES, checker.RESERVE_BYTES),
                         (3*1024**3//2, 512*1024**2, 128*1024**2))


if __name__ == '__main__':
    unittest.main(verbosity=2)
