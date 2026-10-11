"""Focused V73 feedback algebra, state ownership and live PETSc wiring."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse

from src.solvers.bounded_trace_pc import BoundedTwoLevelPC,prolong,restrict
from src.solvers.reused_trace_admission import future_workspace,numeric_gate


class FeedbackTests(unittest.TestCase):
    def test_hot_packet_receives_campaign_action_limit(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from src.solvers.bounded_trace_study import service
        policy=SimpleNamespace(plan_record=lambda:dict(action_limit=1600,prepared_parent={'local_packet':'fixture'}))
        journal=SimpleNamespace(measured=lambda _:nullcontext(),owners=lambda *a:None)
        with patch('src.solvers.bounded_trace_study.HotTracePacket') as constructor:
            service(journal,scope=policy)
            self.assertEqual(constructor.call_args.kwargs['action_limit'],1600)

    def test_saved_consumer_rejects_solve_protocol_before_FE(self):
        from types import SimpleNamespace
        from src.solvers.bounded_trace_study import consume_interrupted_retained
        sc=SimpleNamespace(checked_json=lambda _:dict(mode='SAVED_RETAINED_ONLY',role='B128',new_KSP_solves=1,new_numeric_factors=0))
        with patch('src.solvers.bounded_trace_study.setup_service') as setup:
            with self.assertRaises(ValueError):consume_interrupted_retained('B128',None,None,dict(postprocessing_resume={}),scope=sc)
            setup.assert_not_called()

    def test_saved_consumer_dispatch_never_enters_iterate(self):
        from src.solvers import bounded_trace_study as study,restart_feedback_scope as sc
        state=dict(memory_budget=sc.memory_budget('B128'),postprocessing_resume={'sha256':'fixture'})
        with patch.object(study,'Journal'),patch.object(study,'consume_interrupted_retained',return_value={'consumed':True}) as consume,patch.object(study,'iterate') as iterate:
            self.assertTrue(study.execute_feedback('B128',Path('/tmp'),state)['consumed'])
            consume.assert_called_once();iterate.assert_not_called()

    def test_complex_nonhermitian_feedback_and_counts(self):
        A=np.array([[4,1j,2,1],[.3j,3,1j,2],[1,.2,5,.5j],[2j,1,3j,6]],complex)
        Z=sparse.csr_matrix(np.array([[1],[.4j],[.2]],complex));Zf=np.zeros((4,2),complex)
        Zf[:3,0]=Z.toarray()[:,0];Zf[3,1]=1
        E=Zf.conj().T@A@Zf;D=A[:3,:3];r=np.array([1+1j,2,3j,-.5j])
        patches=[dict(ids=np.arange(3),core=np.arange(3))]
        with patch.object(BoundedTwoLevelPC,'solve',side_effect=lambda f,v:np.linalg.solve(f,v)):
            old=BoundedTwoLevelPC(Z,patches,[D],E,lambda v:A@v)
            new=BoundedTwoLevelPC(Z,patches,[D],E,lambda v:A@v,variant='balanced')
            C=Zf@np.linalg.solve(E,Zf.conj().T);B=np.zeros((4,4),complex);B[:3,:3]=np.linalg.inv(D)
            P=np.eye(4)-A@C;Q=np.eye(4)-C@A
            self.assertGreater(np.linalg.norm(Q-P.conj().T),1e-2)
            np.testing.assert_allclose(old(r),(C+B@P)@r,rtol=1e-13,atol=1e-13)
            np.testing.assert_allclose(new(r),(C+Q@B@P)@r,rtol=1e-13,atol=1e-13)
            np.testing.assert_allclose(Zf.conj().T@(r-A@new(r)),0,atol=1e-12)
            self.assertEqual(old.calls,dict(apply=1,local_triangular=1,coarse_triangular=1,internal_original_action=1))
            self.assertEqual(new.calls,dict(apply=2,local_triangular=2,coarse_triangular=4,internal_original_action=4))
            np.testing.assert_allclose(restrict(Z,prolong(Z,np.array([1j,2]))),Zf.conj().T@Zf@np.array([1j,2]))

    def test_coarse_balance_does_not_guarantee_residual_decrease(self):
        A=np.array([[1,10],[0,1]],complex);Z=np.array([[0],[1]],complex)
        C=Z@np.linalg.solve(Z.conj().T@A@Z,Z.conj().T);r=np.array([0,1],complex)
        out=r-A@C@r
        np.testing.assert_allclose(Z.conj().T@out,0)
        self.assertGreater(np.linalg.norm(out),np.linalg.norm(r))

    def test_long_restart_workspace_and_rejections(self):
        w=future_workspace(1177293,1944573,2110000,68680,15000000,restart=128,minimum_bytes=12*2**30)
        self.assertEqual(w['components']['Krylov_V_Z'],4841028816)
        self.assertGreaterEqual(w['reserved_bytes'],12*2**30)
        self.assertFalse(numeric_gate(dict(rss_bytes=30*2**30,swap_bytes=0),80*2**30,w,minimum_bytes=12*2**30)['admitted'])
        with self.assertRaises(ValueError):numeric_gate(dict(rss_bytes=0,swap_bytes=0),0,dict(reserved_bytes=8*2**30),minimum_bytes=12*2**30)

    def test_scope_source_physical_role_and_old_closed(self):
        from src.solvers import restart_feedback_scope as sc
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        self.assertIs(context('v73')[0],sc.window)
        self.assertEqual(storage_limits('v73')['task_storage_bytes'],664*2**30)
        for p in sorted((sc.ROOT/'input/task042_neural_coarse_inverse').glob('v73_*.dat')):
            r=load_tetra_reference(p,scope_module=sc);role=r.derived['stage']
            self.assertEqual(r.physical_model_sha256,'df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44')
            want=96 if role in sc.SOLVES else 64
            self.assertEqual(r.execution['planning_memory_gib'],want)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                self.assertEqual(preparation_memory_envelope('v73',role)['planning_cap_bytes'],want*2**30)
        self.assertTrue(json.loads((sc.ROOT/'tmp/task042/v72/window.json').read_text())['closed'])

    def test_candidate_freeze_not_batch_freeze(self):
        from types import SimpleNamespace
        from src.solvers import restart_feedback_scope as sc
        failed=dict(iteration={'final_evaluation':dict(schur_true_relative_residual=1,true=1,native=1,augmented=1,port=1,MPC_identity=0,rhs_q47_q63=0,recovery_identity=0,Schur_original_identity=0)},audit={'pass_gate':False})
        with tempfile.TemporaryDirectory() as td,patch.object(sc,'window',SimpleNamespace(TMP=Path(td))),patch.object(sc,'stage',side_effect=lambda role:dict(pass_gate=True) if role=='PRECHECK' else failed):
            sc.freeze_candidate('R128',{'sha256':'r'},dict(source_sha='source'))
            (Path(td)/'balanced_qualification.json').write_text('{"pass_gate":true}')
            self.assertFalse((Path(td)/'scientific_queue_frozen.json').exists());sc.require_stage('B128')
            (Path(td)/'scientific_queue_frozen.json').write_text('{}')
            with self.assertRaises(RuntimeError):sc.require_stage('B128')

    def test_PC_factor_ownership_cleanup(self):
        class Factor:
            def __init__(self):self.closed=False
            def destroy(self):self.closed=True
        a,b=Factor(),Factor();pc=BoundedTwoLevelPC(sparse.eye(2,format='csr'),[],[a],b,lambda v:v)
        try:
            with patch.object(pc,'coarse_apply',side_effect=ValueError('fixed failure')):
                with self.assertRaises(ValueError):pc(np.ones(2,complex))
        finally:pc.destroy()
        self.assertTrue(a.closed and b.closed);self.assertEqual(pc.factors,[])

    def test_actual_PETSc_restart128_and_exact_state_cache(self):
        from petsc4py import PETSc
        from src.solvers.physical_retained_fgmres import run_retained_fgmres
        A=np.diag(np.arange(2,10).astype(complex))+np.diag(np.ones(7)*.1j,1)
        b=PETSc.Vec().createSeq(8);b.array[:]=1+np.arange(8)*1j;seen=[];records=[]
        def action(v):o=v.duplicate();o.array[:]=A@v.array;return o
        def evaluate(v,r):seen.append(v.array.copy());return dict(true=np.linalg.norm(r.array)/b.norm(),identity=0.)
        with tempfile.TemporaryDirectory() as td:
            try:
                r=run_retained_fgmres(b,action,lambda v:v.copy(),evaluate=evaluate,checkpoint=lambda *a:None,
                    append=lambda n,row:records.append((n,row)),seconds=lambda:0.,restart=128,max_it=256,residual_interval=32,
                    evaluation_policy=dict(original_key='true',physical_limits=dict(true=1e-6),identity_limits=dict(identity=1e-10)),
                    candidate_rtol=1e-11,retained_tolerance=1e-11,audit_identity=dict(directory=td,route='synthetic',source_sha='fixture'))
                self.assertTrue(r['final_evaluation']['solve_gate_pass']);self.assertEqual(r['actual_KSP_configuration']['type'],'fgmres')
                self.assertEqual(r['restart'],128);self.assertEqual(r['ksp_solve_count'],1)
                self.assertIn('right',Path(td,'KSP_view.txt').read_text().lower())
                states=[(row['iteration'],v.tobytes()) for (_,row),v in zip([p for p in records if p[0]=='monitor_residuals.jsonl'],seen,strict=True)]
                self.assertEqual(len(states),len(set(states)));r['final_solution'].destroy()
            finally:b.destroy()


if __name__=='__main__':unittest.main()
