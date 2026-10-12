"""One small complex scheduling fixture; no PDE or factor construction."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.solvers import uninterrupted_jacobi_scope as scope
from src.solvers.controlled_trace_study import iteration_options


class JacobiPolicyTests(unittest.TestCase):
    def test_old_and_explicit_scheduling(self):
        from src.solvers import controlled_trace_scope as old
        self.assertEqual(iteration_options('BJ','BJ',0,old)['max_it'],32)
        p=iteration_options('J128_CONTINUOUS','J128_CONTINUOUS',0,scope,scope.iteration_policy())
        self.assertEqual((p['max_it'],p['restart']),(256,128))
        for i in (0,32,64,96):
            self.assertFalse(p['effect_check'](dict(iteration=i,true=1.,schur_true_relative_residual=1.))['evaluated'])
        self.assertFalse(scope.effect_check(128,.101,.01)['pass_gate'])
        self.assertTrue(scope.effect_check(128,.09,.1)['pass_gate'])

    def test_namespace_budget_inputs(self):
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import scoped_tetra_memory,storage_limits
        paths=sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v78_*.dat'))
        self.assertEqual(len(paths),3)
        for p in paths:
            s=load_tetra_reference(p,scope_module=scope)
            self.assertEqual(s.derived['preparation_scope'],'v78')
            self.assertEqual(s.solver['max_it'],256)
            self.assertEqual(scoped_tetra_memory('v78',s.derived['stage'])['planning_gib'],64)
        self.assertEqual(storage_limits('v78')['new_storage_bytes'],8*2**30)
        self.assertEqual(scope.plan_record()['action_limit'],400)

    def test_small_complex_same_KSP_checkpoints_and_stop(self):
        from petsc4py import PETSc
        from src.solvers.physical_retained_fgmres import run_retained_fgmres
        rng=np.random.default_rng(7801);n=320
        A=np.diag(np.linspace(.001,1,n).astype(complex))
        A+=np.diag(np.full(n-1,.2+.3j),1)
        rhs=PETSc.Vec().createSeq(n,comm=PETSc.COMM_SELF);rhs.array[:]=rng.normal(size=n)+1j*rng.normal(size=n)
        def op(v):
            w=v.duplicate();w.array[:]=A@v.array;return w
        logs={};saved=[]
        def append(name,row):logs.setdefault(name,[]).append(row)
        def effect(row):
            # Independently exercise the registered gate with a deliberately
            # unresolved manufactured metric, not a physical PDE assertion.
            return scope.effect_check(row['iteration'],1.,row['schur_true_relative_residual'])
        result=run_retained_fgmres(rhs,op,lambda v:v.copy(),evaluate=lambda t,r:dict(true=1.),
            checkpoint=lambda i,v,row:None,append=append,seconds=lambda:0.,save_retained=lambda i,v:saved.append(i),
            restart=128,max_it=256,residual_interval=32,evaluation_iterations=(0,32,64,96,128),
            retained_observation_iterations=(),effect_check=effect,candidate_rtol=0.,retained_tolerance=0.,
            evaluation_policy=dict(original_key='true',physical_limits={'true':1e-6},identity_limits={}))
        try:
            self.assertEqual(result['iterations'],128)
            self.assertEqual((result['ksp_create_count'],result['ksp_solve_count'],result['ksp_destroy_count']),(1,1,1))
            self.assertEqual(result['status'],'EFFECT_GATE_STOP')
            self.assertTrue(set((0,32,64,96,128)).issubset(saved))
            for row in result['snapshots']:self.assertEqual(row['iteration'],row['ksp_instance_iteration'])
            self.assertFalse(any(r['evaluated'] for r in logs['effect_gates.jsonl'] if r['iteration']<128))
        finally:result['final_solution'].destroy()
        continued=run_retained_fgmres(rhs,op,lambda v:v.copy(),evaluate=lambda t,r:dict(true=1.),
            checkpoint=lambda i,v,row:None,append=append,seconds=lambda:0.,
            restart=128,max_it=256,residual_interval=32,evaluation_iterations=(0,32,64,96,128),
            effect_check=lambda row:scope.effect_check(row['iteration'],.01,.01),
            candidate_rtol=0.,retained_tolerance=0.,
            evaluation_policy=dict(original_key='true',physical_limits={'true':1e-6},identity_limits={}))
        try:
            self.assertEqual(continued['iterations'],256)
            self.assertEqual((continued['ksp_create_count'],continued['ksp_solve_count'],continued['ksp_destroy_count']),(1,1,1))
            self.assertIsNone(continued['continuation_basis'])
        finally:continued['final_solution'].destroy();rhs.destroy()

    def test_returned_only_dispatch(self):
        from src.solvers import uninterrupted_jacobi_study as study
        state=dict(memory_budget=scope.memory_budget('J128_CONTINUOUS'),postprocessing_resume={'synthetic':True})
        with tempfile.TemporaryDirectory() as t,patch.object(study,'Journal'),patch('src.solvers.controlled_trace_study.iterate',side_effect=AssertionError('no repeat KSP')),patch('src.solvers.controlled_trace_study.consume_returned',return_value={'saved':True}) as c:
            self.assertTrue(study.execute('J128_CONTINUOUS',Path(t),state)['saved']);c.assert_called_once()


if __name__=='__main__':unittest.main()
