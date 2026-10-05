"""Pure metadata/orchestration tests; no modes, mesh, form, JIT or assembly."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

PATH = Path(__file__).with_name('launch_target_chunked_surface_mass_v2.py')
spec = importlib.util.spec_from_file_location('surface_launcher_under_test', PATH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
sys.path.insert(0, str(launcher.ROOT))


class AllocationTests(unittest.TestCase):
    def test_producer_count(self):
        self.assertEqual(launcher.allocation_bytes({'predicted_total_bytes': 31,
                         'predicted_buffer_bytes': {'new': 16, 'workspace': 15}}), 31)

    def test_reference_counts_both_fields_and_workspace(self):
        facts = {'requested_bytes': 31, 'live_named_bytes': 50, 'workspace_estimate_bytes': 15,
                 'items': [{'bytes': 16}, {'bytes': 15}]}
        self.assertEqual(launcher.allocation_bytes(facts), 50)

    def test_simultaneous_schemas_count_greatest(self):
        self.assertEqual(launcher.allocation_bytes({'predicted_total_bytes': 75,
                         'predicted_buffer_bytes': {'a': 75}, 'requested_bytes': 31,
                         'live_named_bytes': 31, 'workspace_estimate_bytes': 15,
                         'items': [{'bytes': 31}]}), 75)

    def test_missing_unknown_or_understated_cannot_be_zero(self):
        for facts in ({}, {'workspace_bytes': 16}, {'requested_bytes': 31},
                      {'live_named_bytes': 31}, {'predicted_total_bytes': 1},
                      {'predicted_total_bytes': 0, 'predicted_buffer_bytes': {'new': 1}},
                      {'requested_bytes': 0, 'live_named_bytes': 31, 'items': [{'bytes': 31}],
                       'workspace_estimate_bytes': 0}):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                launcher.allocation_bytes(facts)

    def test_negative_boolean_string_and_float_bytes_rejected(self):
        for value in (-1, True, '1', 1.0, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                launcher.allocation_bytes({'predicted_total_bytes': value,
                                           'predicted_buffer_bytes': {'a': value}})


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.summary = json.loads((launcher.METADATA_RUN/'summary.json').read_text())
        self.source = self.summary['source_state']

    def test_actual_saved_worker_summary_metadata_only(self):
        launcher.require_summary(self.summary, self.source, 60)

    def test_each_boolean_resource_gate_fails_closed(self):
        for key in ('descendants_cleared', 'process_tree_all_status_readable',
                    'process_tree_all_identity_complete', 'process_tree_swap_gate_enforced',
                    'global_swap_gate_enforced', 'time_gate_evaluated'):
            bad = copy.deepcopy(self.summary)
            bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.require_summary(bad, self.source, 60)

    def test_classification_exit_resource_time_source_failures(self):
        cases = [('classification', 'WORKER_FAILED'), ('leader_exit_code', 2),
                 ('remaining_child_pids', [1]), ('sampled_process_tree_swap_peak_bytes', 1),
                 ('sampled_process_tree_rss_peak_bytes', launcher.CAP),
                 ('elapsed_seconds', 61), ('process_tree_identity_coverage', 'incomplete'),
                 ('observed_child_identity_coverage', 'incomplete'), ('source_state', {})]
        for key, value in cases:
            bad = copy.deepcopy(self.summary)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.require_summary(bad, self.source, 60)

    def test_global_swap_and_strict_clock_not_only_elapsed(self):
        for key, value in [('global_swap_activity', {'delta': {'pswpin_pages': None, 'pswpout_pages': 0}}),
                           ('workflow_clock_interval', {'budget_seconds': 61}),
                           ('time_end_observation', {'passed': False}),
                           ('timebase_policy', 'diagnostic')]:
            bad = copy.deepcopy(self.summary)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.require_summary(bad, self.source, 60)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.worker = self.root/'worker'
        self.worker.mkdir()
        members = []
        for index in range(9):
            name = 'file_'+str(index)+'.json'
            contents = json.dumps({'synthetic': index}).encode()
            (self.worker/name).write_bytes(contents)
            members.append({'path': name, 'bytes': len(contents),
                            'sha256': hashlib.sha256(contents).hexdigest()})
        self.manifest = self.root/'member_manifest.json'
        self.manifest.write_text(json.dumps({'schema': 'task40extra.complete-metadata-archive.v1',
                                            'source': launcher.HEAD, 'members': members,
                                            'total_bytes': sum(m['bytes'] for m in members)}))
        self.archive = self.root/'synthetic.zip'
        with zipfile.ZipFile(self.archive, 'w') as stream:
            stream.write(self.manifest, 'member_manifest.json')
            for item in members:
                stream.write(self.worker/item['path'], item['path'])

    def tearDown(self):
        self.directory.cleanup()

    def test_streams_every_full_readback_member(self):
        result = launcher.verify_archive(self.archive, self.manifest, self.worker)
        self.assertEqual(result['archive_members_verified'], 10)
        self.assertEqual(result['original_members_verified'], 9)

    def test_original_or_readback_drift_fails(self):
        (self.worker/'file_5.json').write_text('changed')
        with self.assertRaises(ValueError):
            launcher.verify_archive(self.archive, self.manifest, self.worker)

    def test_extra_archive_member_fails(self):
        with zipfile.ZipFile(self.archive, 'a') as stream:
            stream.writestr('unexpected', 'extra')
        with self.assertRaises(ValueError):
            launcher.verify_archive(self.archive, self.manifest, self.worker)


class SurfaceRecordTests(unittest.TestCase):
    def test_partial_or_false_completion_cannot_pass(self):
        for status in ('PARTIAL_FAILED_OR_CONTROLLED_STOP', 'SELECTED_TOP_X_REFERENCE_FAILED', None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                launcher.verify_surface_record({'status': status}, {})

    def test_import_is_stdlib_only_and_calls_no_runtime(self):
        code = PATH.read_text()
        self.assertNotIn('build_metadata_packet(', code)
        self.assertNotIn('_fresh_inventory(', code)
        self.assertEqual(launcher.PYTHON, '../complex_env_recovery/bin/python')

    def test_preflight_parser_requires_real_receipt_and_seal_hashes(self):
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            launcher.parser().parse_args(['--stage', 'preflight'])


class SavedActionTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from src.solvers.target_auto_surface_cost import reference_action_gate, jsonable
        from src.solvers.target_higher_quadrature_reference import operation_scaled_difference
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        indices = [16028, 16029, 0, 1, 6018, 6019]
        self.packet = {'selected_original_mode_indices': indices}
        values = np.arange(18, dtype=np.float64).reshape(6, 3).astype(np.complex128)
        scales = np.abs(values)
        self.record = {'contraction_artifacts': {},
                       'raw_vs_public_eval_reference': jsonable(reference_action_gate(values, values, scales)),
                       'independent_reference': {'convergence_metrics': []}}
        for name in ('primary_raw_contractions', 'contractions_degree_plus8',
                     'contractions_degree_plus16', 'operation_scales_degree_plus16'):
            value = scales if name.startswith('operation_scales') else values
            path = self.root/(name+'.npy')
            np.save(path, value, allow_pickle=False)
            self.record['contraction_artifacts'][name] = {'path': str(path),
                                                       'bytes': path.stat().st_size,
                                                       'sha256': launcher.file_sha256(path)}
        for j, index in enumerate(indices):
            for k in range(3):
                self.record['independent_reference']['convergence_metrics'].append(
                    {'selected_mode_index': j, 'inventory_index': index, 'state_index': k,
                     **operation_scaled_difference(values[j, k], values[j, k], scales[j, k])})

    def tearDown(self):
        self.temporary.cleanup()

    def test_saved_comparisons_recomputed_after_small_admission(self):
        calls = []
        def gate(label, facts):
            calls.append(launcher.allocation_bytes(facts))
        before = copy.deepcopy(self.record)
        checked = launcher.verify_saved_actions(self.record, self.packet, self.root, gate)
        self.assertEqual(calls, [1 << 20])
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['comparison_entries'], 18)
        self.assertEqual(before, self.record)

    def test_saved_exact_zero_primary_error_fails_even_with_matching_new_hash(self):
        import numpy as np
        descriptor = self.record['contraction_artifacts']['primary_raw_contractions']
        value = np.load(descriptor['path'], allow_pickle=False)
        value[0, 0] = 1e-300
        np.save(descriptor['path'], value, allow_pickle=False)
        descriptor['sha256'] = launcher.file_sha256(descriptor['path'])
        with self.assertRaises(ValueError):
            launcher.verify_saved_actions(self.record, self.packet, self.root, lambda *_: True)

    def test_saved_convergence_error_fails_even_if_report_says_pass(self):
        import numpy as np
        descriptor = self.record['contraction_artifacts']['contractions_degree_plus8']
        value = np.load(descriptor['path'], allow_pickle=False)
        value[1, 1] += 1e-5
        np.save(descriptor['path'], value, allow_pickle=False)
        descriptor['sha256'] = launcher.file_sha256(descriptor['path'])
        with self.assertRaises(ValueError):
            launcher.verify_saved_actions(self.record, self.packet, self.root, lambda *_: True)

    def test_scalar_header_rejected_before_materialization(self):
        import numpy as np
        descriptor = self.record['contraction_artifacts']['primary_raw_contractions']
        np.save(descriptor['path'], np.zeros((1000, 3), dtype=np.complex128), allow_pickle=False)
        descriptor['sha256'] = launcher.file_sha256(descriptor['path'])
        descriptor['bytes'] = Path(descriptor['path']).stat().st_size
        with patch('numpy.load', side_effect=AssertionError('must reject header before load')):
            with self.assertRaisesRegex(ValueError, 'header shape'):
                launcher.verify_saved_actions(self.record, self.packet, self.root, lambda *_: True)


class SavedMechanismTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.n=13224; self.indices=[16028,16029,0,1,6018,6019]
        raw=np.zeros((6,self.n),dtype=np.complex128); raw[:,:4]=np.array([1+2j,3-1j,-2+4j,5],dtype=np.complex128)
        self.record={'actual_native_storage_rows':self.n,'mechanism_chunked_artifacts':{},'mechanism_ffcx_components':[]}
        self.packet={'selected_original_mode_indices':self.indices};self.calls=[]
        def save(name,a):
            p=self.root/(name+'.npy');np.save(p,a,allow_pickle=False)
            return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for k in ('b_FE','raw_MPC','masked_full'):self.record['mechanism_chunked_artifacts'][k]=save('new_'+k,raw)
        for i,index in enumerate(self.indices):
            self.record['mechanism_ffcx_components'].append({'original_mode_index':index,'artifacts':{
                k:save('old_'+str(i)+'_'+k,raw[i]) for k in ('b_FE','raw_MPC','masked_full')}})
    def tearDown(self):self.temp.cleanup()
    def gate(self,label,facts):self.calls.append((label,facts));return True
    def rewrite(self,d,a):
        import numpy as np
        p=Path(d['path']);np.save(p,a,allow_pickle=False);d.update(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def test_complete_vectors_replayed_and_admitted(self):
        x=launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)
        self.assertTrue(x['passed']);self.assertEqual(x['complete_native_vectors_replayed'],18)
        self.assertEqual(self.calls[0][1]['predicted_total_bytes'],64<<20)
    def test_corrupt_raw_even_with_updated_hash_fails(self):
        import numpy as np
        d=self.record['mechanism_chunked_artifacts']['raw_MPC'];a=np.load(d['path']);a[2,1]+=0.1;self.rewrite(d,a)
        with self.assertRaisesRegex(ValueError,'equivalence'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)
    def test_coherent_wrong_mask_fails_own_rule(self):
        import numpy as np
        d=self.record['mechanism_chunked_artifacts']['masked_full'];a=np.load(d['path']);a[0,8]=1e-12;self.rewrite(d,a)
        old=self.record['mechanism_ffcx_components'][0]['artifacts']['masked_full'];b=np.load(old['path']);b[8]=1e-12;self.rewrite(old,b)
        with self.assertRaisesRegex(ValueError,'own mask'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)
    def test_bad_header_rejected_before_any_array_load(self):
        import numpy as np
        d=self.record['mechanism_chunked_artifacts']['b_FE'];self.rewrite(d,np.zeros((7,self.n),dtype=np.complex128))
        with patch('numpy.load',side_effect=AssertionError('must reject before load')):
            with self.assertRaisesRegex(ValueError,'header'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)
    def test_admission_denial_precedes_header_and_load(self):
        with patch('numpy.load',side_effect=AssertionError('no load on denial')):
            def deny(*args):raise MemoryError('denied before headers')
            with self.assertRaisesRegex(MemoryError,'denied'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,deny)
    def test_tiny_wrong_vector_cannot_underflow_to_false_pass(self):
        import numpy as np
        tiny=np.zeros((6,self.n),dtype=np.complex128);tiny[:,0]=1e-250
        zero=np.zeros_like(tiny)
        for k in ('b_FE','raw_MPC','masked_full'):
            self.rewrite(self.record['mechanism_chunked_artifacts'][k],zero if k=='masked_full' else tiny)
            for i in range(6):self.rewrite(self.record['mechanism_ffcx_components'][i]['artifacts'][k],zero[i] if k=='masked_full' else tiny[i])
        bad=tiny.copy();bad[0,0]=2e-250
        self.rewrite(self.record['mechanism_chunked_artifacts']['b_FE'],bad)
        with self.assertRaisesRegex(ValueError,'equivalence'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)
    def test_swapped_original_mode_rejected(self):
        self.record['mechanism_ffcx_components'][0]['original_mode_index']=0
        with self.assertRaisesRegex(ValueError,'index'):launcher.verify_saved_mechanism(self.record,self.packet,self.root,self.gate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
