"""V63 new support, role budget, inventory and consumer contracts only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.solvers.tetra_boundary_support import reachable_support,compact_index,support_row
from src.solvers import fine_tetra_scope as scope
from src.io.independent_tetra_reference import load_tetra_reference


class FineTetraTests(unittest.TestCase):
    def test_failed_start_cost_is_not_a_saved_vector_resume(self):
        from benchmarks.collect_fine_tetra import deployment_accounting
        parts=[dict(start_utc='2026-01-01T00:00:00+00:00',end_utc='2026-01-01T00:00:03+00:00',elapsed_seconds=3.,exit_code=1),
            dict(start_utc='2026-01-01T00:00:20+00:00',end_utc='2026-01-01T00:00:40+00:00',elapsed_seconds=20.,exit_code=0)]
        r=deployment_accounting(parts,dict(deployment_complete=True))
        self.assertEqual(r['T_N1_process_chain_seconds'],23.)
        self.assertEqual(r['successful_final_process_T_N1_seconds'],20.)
        self.assertEqual(r['T_N1_observed_start_to_final_cleanup_seconds'],40.)
        self.assertEqual(r['prior_failed_process_count'],1)
        self.assertFalse(r['saved_vector_resume'])
        self.assertFalse(r['single_process_complete_N1'])
        self.assertIsNone(r['post_resume_new_numeric_factors'])
        post=deployment_accounting(parts,dict(deployment_complete=True,post_only=True))
        self.assertTrue(post['saved_vector_resume'])
        self.assertIsNone(post['successful_final_process_T_N1_seconds'])

    def test_saved_increment_reuse_keeps_exact_parent_and_consumer_budget(self):
        from benchmarks.collect_fine_tetra import bound_comparison
        first={'arrays':{'sha256':'A'}};second={'arrays':{'sha256':'B'}}
        negative={'parent_array_sha256':['A','B'],'pass_gate':False}
        self.assertIs(bound_comparison(negative,first,second),negative)
        with self.assertRaisesRegex(ValueError,'parent identity'):
            bound_comparison(negative,second,first)
        for role in ('compare_A','compare_gate'):
            self.assertEqual(scope.memory_budget(role)['planning_gib'],64)
            self.assertEqual(scope.memory_budget(role)['sampled_stop_gib'],96)

    def test_capacity_includes_multi_master_periodic_moments(self):
        from scipy import sparse
        from src.solvers.tetra_boundary_support import expanded_cell_graph
        P=sparse.csr_matrix([[1,1j,0,0],[0,0,1,0],[0,0,1,1j]],dtype=complex)
        graph=expanded_cell_graph(P,lambda c:np.array([0,1]),1,2)
        self.assertEqual(graph['body_upper'],9)
        self.assertEqual(graph['maximum_masters_per_native_row'],2)
        self.assertGreater(graph['body_upper'],4)

    def test_exact_owner_support_tiny_nonzero_and_outside_rejection(self):
        maps=[(np.array([0]),np.array([1.])),(np.array([4,6]),np.array([1j,.5])),(np.array([2]),np.array([1.]))]
        rows=reachable_support(lambda cell:([0,1] if cell==0 else [2]),[0],maps)
        self.assertEqual(list(rows),[0,4,6]);idx=compact_index(rows,7)
        with self.assertRaisesRegex(ValueError,'outside'):support_row(idx,2)
        full=np.zeros((2,7,2),complex);out=np.zeros((2,len(rows),2),complex)
        val=np.array([[1e-300+1e-300j,2.],[3.,4.]])
        for master,c in zip(*maps[1],strict=True):
            full[:,master,:]+=c*val;out[:,support_row(idx,int(master)),:]+=c*val
        np.testing.assert_array_equal(full[:,rows],out)
        self.assertNotEqual(out[0,support_row(idx,4),0],0)
        with self.assertRaisesRegex(ValueError,'inventory'):compact_index([0,0],7)

    def test_real_schema_and_B_only_profile(self):
        from src.runners.port_preparation import preparation_memory_envelope
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case.dat'
            for role in scope.STAGES:
                p.write_text(f'schema_version = 1\n[task042_v63]\nstage = "{role}"\nrun_id = "task042_v63_test"\n')
                r=load_tetra_reference(p,scope_module=scope)
                self.assertEqual(r.derived['preparation_scope'],'v63')
                self.assertEqual(r.execution['planning_memory_gib'],128 if role=='B' else 64)
                self.assertEqual(r.execution['terminate_memory_gib'],192 if role=='B' else 96)
                self.assertEqual(r.boundary['complete_modes'],1188 if role=='M' else 828)
                self.assertEqual(r.geometry['actual_mesh_expected_notch_tetrahedra'],192)
                self.assertEqual(tuple(len(r.geometry['axes_nm'][a])-1 for a in ('x','y','z')),(8,8,20))
                with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=1024*2**30,reserve_bytes=0,system_reserve_bytes=8*2**30)):
                    env=preparation_memory_envelope('v63',role)
                self.assertEqual(env['launch_cap_bytes'],(192 if role=='B' else 96)*2**30)
                self.assertEqual(env['planning_cap_bytes'],(128 if role=='B' else 64)*2**30)
            p.write_text('schema_version=1\n[task042_v63]\nstage="TC6"\nrun_id="task042_v63_test"\n')
            with self.assertRaises(ValueError):load_tetra_reference(p,scope_module=scope)

    def test_fixed_mode_inventory_unknown_refused(self):
        from src.solvers.independent_tetra_reference import configuration
        for role,m,n in [('A',11,4),('M',13,5)]:
            c=configuration(scope.case_spec(role),scope.physical_for(role))
            self.assertEqual((c.diffraction_order_max_m,c.diffraction_order_max_n),(m,n))
        with self.assertRaisesRegex(ValueError,'unknown'):
            configuration(dict(scope.case_spec('A'),complete_modes=900),scope.physical_for('A'))

    def test_no_old_FAIL_admission_gate_and_M_full_increment(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def stage(role):return dict(pass_gate=True,equation_pass=True,arrays={'sha256':role})
            with patch.object(scope,'ARTIFACT',root),patch.object(scope.window,'TMP',root),patch.object(scope,'stage',stage),patch.object(scope.window,'available_at_boundary',return_value=100000):
                scope.require_stage('A');scope.require_stage('B')
                (root/'A_B_gate.json').write_text(json.dumps(dict(pass_gate=False,parent_array_sha256=['A','B'])))
                with self.assertRaisesRegex(RuntimeError,'complete A/B'):scope.require_stage('M')
                (root/'A_B_gate.json').write_text(json.dumps(dict(pass_gate=True,parent_array_sha256=['A','B'])))
                scope.require_stage('M')


if __name__=='__main__':unittest.main()
