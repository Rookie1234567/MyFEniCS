"""Focused new-backend, transactional block, original dual and live scope tests."""
import contextlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np
from src.postprocessing.phase_volume_quadrature import material_metrics,phase_volume_absorption,checked_block
from src.solvers.phase_saved_uncondensed import local_vectors
from src.solvers.phase_target_bridge import layout
from src.solvers.scattering_anchor import save_arrays
from src.solvers import phase_saved_closure_scope as scope


def cfg():
    return NS(k0=3.,tags=NS(air=1,substrate=2,grating=3),eps_air=1.,eps_substrate=.9+.07j,eps_grating=.8+.03j,
        grating_index=.9+.02j,substrate_index=.95+.04j,grating_material_label=None,substrate_material_label=None)


class Journal:
    def measured(self,*_):return contextlib.nullcontext()
    def event(self,*_,**__):pass


class SavedClosureTests(unittest.TestCase):
    def test_absorption_total_complex_cross_terms_and_both_regions(self):
        c=cfg();rows=np.array([[1,100.,9.],[2,5.,2.],[3,7.,3.]])
        m=material_metrics(c,rows,2.,dict(R_total=.2,T_total=.3,A_balance=.5))
        self.assertAlmostEqual(m['A_volume_total'],3./4*(.07*5+.03*7))
        self.assertEqual(m['regions']['substrate']['cell_count'],1)
        self.assertEqual(m['regions']['grating']['volume_nm3'],3.)
        self.assertAlmostEqual(m['energy_closure_error_port_volume'],.5+m['A_volume_total']-1)
        c.eps_grating=.8-.03j
        self.assertLess(material_metrics(c,rows,2.)['A_grating'],0.)

    def test_cell_blocks_are_reused_and_corruption_or_new_identity_rejected(self):
        mesh=NS(comm=NS(size=1),geometry=NS(x=np.zeros((8,3)),dofmap=np.zeros((2,8),int)),topology=NS(index_map=lambda _:NS(size_local=2)))
        space=NS(mesh=mesh,element=NS(basix_element=NS(coefficient_matrix=np.eye(2),degree=7)))
        function=NS(function_space=space,x=NS(array=np.array([1+2j,3-4j])))
        md=NS(cell_tags=NS(indices=np.arange(2),values=np.array([2,3])))
        class Evaluator:
            calls=0
            def __init__(self,*_,**__):
                self.points=np.array([[.25,.4,.6],[.75,.4,.6]]);self.weights=np.array([.5,.5]);self.geometry=[(np.eye(3),np.zeros(3),1.),(np.eye(3),np.zeros(3),2.)];self.eval_checks=[]
            def at(self,*args):
                Evaluator.calls+=1
                return {'E':np.tile(np.array([1+2j,2-1j,3j]),(len(args[2]),1))}
        with tempfile.TemporaryDirectory() as d,patch('src.solvers.phase_evaluation_cache.CachedPhaseEvaluator',Evaluator):
            a=phase_volume_absorption(md,cfg(),function,np.zeros(3),Path(d),incident_power=2.,journal=Journal(),cell_block=1,point_block=1)
            calls=Evaluator.calls
            b=phase_volume_absorption(md,cfg(),function,np.zeros(3),Path(d),incident_power=2.,journal=Journal(),cell_block=1,point_block=1)
            self.assertEqual(a['A_volume_total'],b['A_volume_total']);self.assertEqual(Evaluator.calls,calls)
            self.assertEqual(b['reused_cells'],2);self.assertTrue(b['quadrature_pass'])
            function.x.array[0]+=1
            with self.assertRaisesRegex(ValueError,'identity changed'):
                phase_volume_absorption(md,cfg(),function,np.zeros(3),Path(d),incident_power=2.,journal=Journal(),cell_block=1,point_block=1)
            path=next((Path(d)/'volume_q31').glob('*.json'));r=json.loads(path.read_text());Path(r['arrays']['path']).write_bytes(b'half written')
            with self.assertRaisesRegex(ValueError,'whole-file identity'):checked_block(path,r['identity'])

    def test_complete_Ckappa_test_dual_nonhermitian_and_multiple_vectors(self):
        rng=np.random.default_rng(56001);v=rng.normal(size=(9,8,3));curl=rng.normal(size=(9,8,3));co=rng.normal(size=(8,3))+1j*rng.normal(size=(8,3))
        J=np.array([[1.3,.2,.1],[0.,.7,.1],[0.,0.,1.1]]);w=rng.random(9);k=np.array([2.3,-.7,0.]);eps=.8+.04j
        a,b=local_vectors(v,curl,co,J,w,k,3.,eps,1.)
        N=v@np.linalg.inv(J);C=curl@J.T/np.linalg.det(J)+1j*np.cross(k,N)
        dense=np.zeros((8,8),complex)
        for q in range(9):dense+=w[q]*np.linalg.det(J)*(C[q].conj()@C[q].T-9*eps*N[q].conj()@N[q].T)
        self.assertLess(np.linalg.norm(a+b-dense@co)/np.linalg.norm(dense@co),1e-13)
        self.assertGreater(np.linalg.norm(dense-dense.conj().T),.01)
        wrong_a,wrong_b=local_vectors(v,curl,co,J,w,np.zeros(3),3.,eps,1.)
        self.assertGreater(np.linalg.norm(wrong_a+wrong_b-a-b)/np.linalg.norm(a+b),.01)

    def test_complex_MPC_dual_once_not_twice(self):
        g=np.array([[1,0],[0,1],[np.exp(.7j),0]],complex);a=np.arange(9).reshape(3,3)+1j*np.eye(3)
        u=np.array([1+2j,3-4j]);expected=g.conj().T@a@g@u
        local=a@(g@u);pull=np.array([local[0]+np.exp(-.7j)*local[2],local[1]])
        np.testing.assert_allclose(pull,expected)
        self.assertGreater(np.linalg.norm(np.array([local[0]+np.exp(.7j)*local[2],local[1]])-expected),.1)

    def test_three_explicit_dat_stages_actual_dimensions_and_unknown_rejected(self):
        from src.io.phase_notch_hp import load_phase_notch_hp
        root=scope.ROOT/'input/task042_neural_coarse_inverse'
        for name,role,p,rows in [('complete_saved_h7','S',7,89756),('notch_x2z2_p6_m828','T6',6,66492),('verify_cost_bridge','VERIFY_COST',7,89756)]:
            spec=load_phase_notch_hp(root/('v56_'+name+'.dat'),scope=scope)
            self.assertEqual(spec.derived['stage'],role);self.assertEqual(spec.solver['degree'],p)
            self.assertEqual(spec.discretization['condensed_rows'],rows);self.assertEqual(spec.boundary['complete_modes'],828)
            self.assertEqual(spec.execution['planning_memory_gib'],64);self.assertEqual(spec.execution['terminate_memory_gib'],96)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'x.dat';path.write_text('schema_version=1\n[task042_v56]\nstage="H7"\nrun_id="task042_v56_illegal"\n')
            with self.assertRaises(ValueError):load_phase_notch_hp(path,scope=scope)

    def test_conditional_T_cannot_start_before_complete_saved_consumer(self):
        with tempfile.TemporaryDirectory() as d,patch.object(scope.window,'TMP',Path(d)),patch.object(scope,'stage',return_value=dict(complete_saved_closure=False)):
            with self.assertRaisesRegex(RuntimeError,'closure incomplete'):scope.require_stage('T6')
            with self.assertRaisesRegex(RuntimeError,'conditional new solve'):scope.require_stage('H7')

    def test_live_launcher_preserves_old_defaults_and_V56_64_80_96(self):
        from src.runners.port_preparation import preparation_memory_envelope,storage_limits,context
        raw=dict(effective_available_bytes=1500*2**30,reserve_bytes=500*2**30,system_reserve_bytes=128*2**30)
        with patch('src.runners.port_preparation.shared_envelope',return_value=raw.copy()):
            env=preparation_memory_envelope('v56');self.assertEqual(env['planning_cap_bytes'],64*2**30);self.assertEqual(env['launch_cap_bytes'],96*2**30)
        self.assertEqual(storage_limits('v56')['task_storage_bytes'],92*2**30)
        self.assertEqual(context('v56')[0].TMP,scope.ROOT/'tmp/task042/v56')

    def test_frozen_time_and_paid_failed_work_do_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            w=scope.ClosureWindow(Path(d),total=18000,component=18000,auxiliary=18000,bootstrap=0)
            with patch.object(w,'require_ready'),patch.object(w,'ledger',return_value=dict(runs=[dict(role='S',folder=d,elapsed_seconds=4200)])),patch.object(w,'charged_wall',return_value=4200),patch.object(w,'snapshot',return_value=dict(heavy_remaining_seconds=10000)):
                self.assertEqual(w.remaining('S'),1200)
                with patch.object(w,'charged_wall',return_value=17500):self.assertLess(w.remaining('T6'),0)

    def test_H7_layout_formula_and_no_accuracy_extrapolation(self):
        r=layout(4,4,20,7)
        self.assertEqual((r['independent_FE'],r['trace'],r['internal']),(330848,88928,241920))
        self.assertEqual(r['one_full_complex128_vector_bytes'],16*330848)

    def test_saved_vector_checker_rejects_half_written_and_missing_metrics(self):
        from benchmarks.collect_phase_saved_closure import vector_check
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.npz';r=save_arrays(p,rhs=np.array([1+1j]))
            with self.assertRaises(KeyError):vector_check(r)
            p.write_bytes(b'half')
            with self.assertRaisesRegex(ValueError,'whole-file identity'):vector_check(r)


if __name__=='__main__':unittest.main()
