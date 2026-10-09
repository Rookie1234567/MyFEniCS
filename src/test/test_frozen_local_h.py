"""Frozen mesh, scoped budgets, body reuse and honest dual normalization."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.solvers import frozen_local_h_scope as scope
from src.io.independent_tetra_reference import load_tetra_reference


class FrozenLocalTests(unittest.TestCase):
    def test_real_loader_and_live_profiles_use_frozen_mesh_and_p4(self):
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for role in scope.STAGES:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'case.dat';p.write_text(f'schema_version=1\n[task042_v66]\nstage="{role}"\nrun_id="task042_v66_fixture"\n')
                s=load_tetra_reference(p,scope_module=scope)
            expected=192 if role in scope.L4_ROLES else 64
            self.assertEqual(s.execution['planning_memory_gib'],expected)
            self.assertEqual((s.geometry['cells'],s.discretization['degree'],s.discretization['FE']),(25576,4,1042964))
            self.assertEqual(s.discretization['rows'],1044152 if role=='L4M' else 1043792)
            self.assertEqual(s.boundary['complete_modes'],1188 if role=='L4M' else 828)
            self.assertEqual((s.discretization['production_body_q'],s.discretization['oracle_body_q']),(11,13))
            self.assertEqual(s.derived['case_spec']['assembly_row_cap'],1050000)
            self.assertEqual(s.derived['case_spec']['mesh_override']['sha256'],'c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c')
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                e=preparation_memory_envelope('v66',role)
            self.assertEqual(e['planning_cap_bytes'],expected*2**30)
            self.assertEqual(e['launch_cap_bytes'],(256 if role in scope.L4_ROLES else 96)*2**30)
        self.assertIs(context('v66')[0],scope.window)
        self.assertEqual(storage_limits('v66')['task_storage_bytes'],408*2**30)

    def test_same_mesh_body_fingerprint_excludes_only_boundary_inventory(self):
        from src.solvers.tetra_body_checkpoint import body_fingerprint
        a=dict(physical=scope.physical_for('SOLVE_COMPLETE'),degree=4,local_dim=84,body_q=11,arrays={'actual_J_and_P':'frozen'},kappa=[1.,2.,0.])
        b=copy.deepcopy(a);b['physical']=scope.physical_for('L4M')
        self.assertEqual(body_fingerprint(a),body_fingerprint(b))
        for key,value in [('body_q',13),('degree',6),('kappa',[2.,2.,0.]),('arrays',{'actual_J_and_P':'different'})]:
            c=copy.deepcopy(b);c[key]=value;self.assertNotEqual(body_fingerprint(a),body_fingerprint(c))
        c=copy.deepcopy(b);c['physical']['materials']['Si_n'][0]+=.001
        self.assertNotEqual(body_fingerprint(a),body_fingerprint(c))

    def test_dual_denominators_keep_one_numerator_and_all_complex_components(self):
        from src.postprocessing.paired_field_norms import score_differences,NAMES
        samples={n:np.full((240,3),1+2j) for n in NAMES};other={n:x+1e-7j for n,x in samples.items()}
        diff=np.full(6,1e-8);large=np.full(6,4.);small=np.full(6,.25)
        a=score_differences(diff,large,samples,other);b=score_differences(diff,small,samples,other)
        self.assertTrue(a['field_and_selected_pass']);self.assertFalse(b['field_and_selected_pass'])
        for n in NAMES:
            self.assertEqual(a['fields'][n]['difference_squared'],b['fields'][n]['difference_squared'])
            self.assertAlmostEqual(b['fields'][n]['relative'],4*a['fields'][n]['relative'])
        with self.assertRaisesRegex(ValueError,'six sample'):
            score_differences(diff,large,{'E_total':samples['E_total']},other)
        with self.assertRaisesRegex(ValueError,'finite'):
            score_differences(np.full(6,np.nan),large,samples,other)
        with self.assertRaisesRegex(ValueError,'240'):
            score_differences(diff,large,{n:x[:239] for n,x in samples.items()},other)

    def test_prepare_solve_compare_and_reentry_share_case_charge(self):
        with tempfile.TemporaryDirectory() as td:
            w=scope.FrozenWindow(Path(td),label='fixture',total=36000)
            rows=[dict(role=r,folder=str(Path(td)/r),elapsed_seconds=t) for r,t in [('PREFLIGHT',90),('PREPARE',9000),('SOLVE_COMPLETE',4000),('SOLVE_COMPLETE',200),('COMPARE_GATE',1200),('L4M',1000)]]
            with patch.object(w,'ledger',return_value=dict(runs=rows,active=None)):
                self.assertEqual(w.case_used('L4F'),14400)
                self.assertEqual(w.case_remaining('L4F'),14400)
                self.assertEqual(w.case_remaining('L4M'),9800)

    def test_M_requires_joint_gate_without_early_final_freeze(self):
        with tempfile.TemporaryDirectory() as td,patch.object(scope.window,'TMP',Path(td)),patch.object(scope,'ARTIFACT',Path(td)),\
            patch.object(scope.window,'available_at_boundary',return_value=20000),patch.object(scope,'numeric_attempts',return_value=1):
            def stage(r):
                return {'PREFLIGHT':{'pass_gate':True},'PREPARE':{'checkpoint':{'hash':'sealed'}},
                    'COMPARE_GATE':{'joint_space_pass':False,'complete_physical_pass':True}}[r]
            with patch.object(scope,'stage',side_effect=stage):
                with self.assertRaisesRegex(RuntimeError,'joint'):scope.require_stage('L4M')
            good=lambda r:dict(stage(r),joint_space_pass=True)
            with patch.object(scope,'stage',side_effect=good):scope.require_stage('L4M')
            (Path(td)/'scientific_queue_frozen.json').write_text('{}')
            with patch.object(scope,'stage',side_effect=good):
                with self.assertRaisesRegex(RuntimeError,'final queue frozen'):scope.require_stage('L4M')

    def test_numeric_time_guard_keeps_estimate_plus_output_reserve(self):
        from types import SimpleNamespace
        j=SimpleNamespace(event=lambda *a,**kw:None)
        with patch.object(scope.window,'snapshot',return_value={'heavy_remaining_seconds':20000}),\
            patch.object(scope.window,'charged_wall',return_value=0),patch.object(scope.window,'case_remaining',return_value=6900):
            scope.numeric_guard('SOLVE_COMPLETE',j)
        with patch.object(scope.window,'snapshot',return_value={'heavy_remaining_seconds':20000}),\
            patch.object(scope.window,'charged_wall',return_value=0),patch.object(scope.window,'case_remaining',return_value=6899):
            with self.assertRaisesRegex(RuntimeError,'after-symbolic'):scope.numeric_guard('SOLVE_COMPLETE',j)


if __name__=='__main__':unittest.main()
