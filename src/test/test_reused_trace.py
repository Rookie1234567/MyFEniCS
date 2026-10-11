"""Focused reuse, live memory, kept-factor and explicit continuation controls."""
import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from scipy import sparse

from src.solvers.reused_trace_admission import reuse_gate,numeric_gate,future_workspace,continuation_state


class ReuseTests(unittest.TestCase):
    def test_old_capacity_false_and_new_math_capacity_are_separate(self):
        from benchmarks.collect_bounded_trace import symbolic_gate
        def info(mb):
            return dict(info={'infog':{'1':0,'16':mb,'17':mb}},controls={'icntl':{'22':0}},
                estimate_mb=mb,double_bytes=2*mb*1000000,numeric_calls=0,rows=7068,nnz=100)
        P=dict(analysis=[info(1046) for _ in range(38)],coarse_symbolic=info(401),matrices=[{}]*38,pass_gate=False)
        checks=dict(mathematics_pass=True,original_action={'pass_gate':True},owner={'all_trace_writeback_once':True},
                    capacity=symbolic_gate(P['analysis'],P['coarse_symbolic']))
        original=copy.deepcopy(P);r=reuse_gate(checks,P)
        self.assertFalse(r['old_capacity']['admitted']);self.assertTrue(r['pass_gate'])
        self.assertFalse(r['numeric_admission']);self.assertEqual(P,original)
        bad=copy.deepcopy(checks);bad['mathematics_pass']=False
        self.assertFalse(reuse_gate(bad,P)['pass_gate'])
        with self.assertRaises(ValueError):reuse_gate(checks,P,96*2**30)

    def test_live_RSS_remaining_factors_and_real_future_workspace(self):
        w=future_workspace(1177293,1944573,1979985,68680,18000000)
        self.assertGreaterEqual(w['reserved_bytes'],8*2**30)
        self.assertTrue(numeric_gate(dict(rss_bytes=9*2**30,swap_bytes=0),80322000000,w)['admitted'])
        self.assertFalse(numeric_gate(dict(rss_bytes=20*2**30,swap_bytes=0),80322000000,w)['admitted'])
        self.assertFalse(numeric_gate(dict(rss_bytes=9*2**30,swap_bytes=4096),80322000000,w)['admitted'])
        # Kept factors already live in RSS, so only UNFACTORED estimates remain.
        self.assertTrue(numeric_gate(dict(rss_bytes=40*2**30,swap_bytes=0),30*2**30,w)['admitted'])

    def test_continuation_rejects_reference_namespace_identity_and_RHS(self):
        a=dict(scaled_retained=np.ones(5,complex),bhat=np.arange(5,dtype=complex),left=np.ones(5),right=np.ones(5))
        expected=dict(operator_identity={'packet':'same'},**{k:a[k] for k in ('bhat','left','right')})
        r=dict(namespace='v72',operator_identity=expected['operator_identity'],iterations_consumed=32,iteration_seconds_consumed=100)
        np.testing.assert_array_equal(continuation_state(a,expected,r),a['scaled_retained'])
        for k,v in [('namespace','v70'),('iterations_consumed',256),('operator_identity',{'packet':'wrong'})]:
            with self.assertRaises(ValueError):continuation_state(a,expected,dict(r,**{k:v}))
        with self.assertRaises(ValueError):continuation_state(dict(a,bhat=a['bhat']+1),expected,r)

    def test_stream_numeric_calibrates_once_keeps_factor_and_cleans_failure(self):
        from src.solvers.bounded_trace_study import numeric_factors
        A=sparse.csr_matrix(np.array([[3,1j],[.5,4]],complex));objects=[]
        class Matrix:
            def __init__(self):self.destroyed=False
            def destroy(self):self.destroyed=True
        class Factor:
            def __init__(self,m):self.index=len(objects);self.numeric_calls=0;self.destroyed=False;self.memory=0;objects.append(self)
            def symbolic(self,m):pass
            def info(self):return {'infog':{'1':0,'16':1,'17':1}}
            def symbolic_memory_settings(self):return {'icntl':{'22':0,'23':self.memory}}
            def set_memory_limit_mb(self,v):self.memory=v
            def numeric(self,m):self.numeric_calls+=1
            def destroy(self):self.destroyed=True
        expected=dict(estimate_mb=1,double_bytes=2000000,rows=2,nnz=4)
        record=dict(matrices=[{},{}],coarse_matrix={},analysis=[expected]*2,coarse_symbolic=expected)
        sc=SimpleNamespace(NAMESPACE='v72',window=SimpleNamespace(snapshot=lambda:{'heavy_remaining_seconds':50000,'boot_id':'test'}))
        j=SimpleNamespace(measured=lambda _:contextlib.nullcontext(),event=lambda *a,**kw:None)
        with tempfile.TemporaryDirectory() as td,patch.dict('os.environ',TASK042_WATCHDOG_PARENT_PID='123'), \
                patch('src.solvers.bounded_trace_study.csr_load',return_value=A), \
                patch('src.solvers.independent_tetra_study.petsc_matrix',side_effect=lambda _:Matrix()), \
                patch('src.solvers.fullspace_v17_p3_oracle._MumpsFactor',Factor), \
                patch('benchmarks.task038_full3d_jit_staging.process_tree_snapshot',return_value=dict(rss_bytes=2*2**30,swap_bytes=0)), \
                patch('src.solvers.bounded_trace_study.BoundedTwoLevelPC.solve',side_effect=lambda f,v:np.linalg.solve(A.toarray(),v)):
            sc.window.TMP=Path(td)
            local,coarse=numeric_factors(record,j,scope=sc,folder=Path(td),workspace={'reserved_bytes':8*2**30})
            self.assertEqual(len(objects),3);self.assertTrue(all(f.numeric_calls==1 and not f.destroyed for f in objects))
            calibration=json.loads((Path(td)/'local_forecast_calibration.json').read_text())
            self.assertFalse(calibration['factor_destroyed']);self.assertFalse(calibration['rebuilt'])
            clock=(Path(td)/'numeric_qualification_clock.json').read_bytes()
            for f in [*local,coarse]:f.destroy()
            objects.clear()
            with patch('src.solvers.bounded_trace_study.BoundedTwoLevelPC.solve',side_effect=lambda f,v:np.full(2,np.nan,complex)):
                with self.assertRaises((ValueError,FloatingPointError)):
                    numeric_factors(record,j,scope=sc,folder=Path(td),workspace={'reserved_bytes':8*2**30})
            self.assertTrue(all(f.destroyed for f in objects))
            self.assertEqual((Path(td)/'numeric_qualification_clock.json').read_bytes(),clock)

    def test_actual_nonzero_KSP_initial_vector_and_cumulative_iteration(self):
        from petsc4py import PETSc
        from src.solvers.physical_retained_fgmres import run_retained_fgmres
        A=np.array([[4,1j,0,0],[.3,3,1,0],[0,.5j,5,1],[1,0,1j,6]],complex)
        rhs=PETSc.Vec().createSeq(4);rhs.array[:]=[1+1j,2,3j,4];initial=np.array([.1j,.2,.1,-.3j])
        def action(v):o=v.duplicate();o.array[:]=A@v.array;return o
        def evaluate(t,r):return dict(true=float(np.linalg.norm(rhs.array-A@t.array)/np.linalg.norm(rhs.array)),identity=0.)
        policy=dict(original_key='true',physical_limits=dict(true=1e-6),identity_limits=dict(identity=1e-10))
        saved=[];true_calls=[]
        def true_action(v):true_calls.append(1);return action(v)
        try:
            result=run_retained_fgmres(rhs,action,lambda v:v.copy(),evaluate=evaluate,checkpoint=lambda *a:None,
                append=lambda *a:None,seconds=lambda:0.,initial_vector=initial,iterations_consumed=32,
                restart=2,max_it=8,residual_interval=2,candidate_rtol=1e-12,retained_tolerance=1e-12,
                evaluation_policy=policy,true_action=true_action,save_retained=lambda i,v:saved.append((i,v.array.copy())))
            self.assertFalse(result['zero_start']);self.assertEqual(result['ksp_solve_count'],1)
            np.testing.assert_allclose(saved[0][1],initial)
            self.assertEqual(saved[0][0],32)
            self.assertEqual(result['cumulative_iterations'],32+result['iterations'])
            self.assertEqual(len(true_calls),result['explicit_action_count'])
            result['final_solution'].destroy()
        finally:rhs.destroy()

    def test_new_namespace_live_memory_and_old_closed_isolation(self):
        from src.solvers import reused_trace_scope as scope
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for p in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v72_*.dat')):
            s=load_tetra_reference(p,scope_module=scope);role=s.derived['stage'];want=[96,112,128] if role=='ITERATE' else [64,80,96]
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],want)
            self.assertEqual(s.physical_model_sha256,'df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44')
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                env=preparation_memory_envelope('v72',role)
            self.assertEqual(env['planning_cap_bytes'],want[0]*2**30)
        self.assertIs(context('v72')[0],scope.window)
        self.assertEqual(storage_limits('v72')['task_storage_bytes'],632*2**30)
        self.assertTrue(json.loads((scope.ROOT/'tmp/task042/v71/window.json').read_text())['closed'])


if __name__=='__main__':unittest.main()
