"""V76 MPC diagonal, nonlinear complex LS, effect/route and live KSP wiring."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from src.solvers.trace_residual_minimization import (
    pullback_diagonal, trace_diagonal, least_residual_weights,
    ResidualMinimizedPC, effect_gate)


class ResidualMinimizationTests(unittest.TestCase):
    def test_full_complex_MPC_diagonal_noninjective(self):
        S = np.array([[2+1j, 3-.2j, 7j], [-2j, 5, .8j], [1, 4j, 3-.6j]])
        E = sparse.csr_matrix([[1, .3j], [.2+.7j, -.2], [1j, 0]])
        expected = np.diag(E.toarray().conj().T@S@E.toarray())
        np.testing.assert_allclose(pullback_diagonal(S, E), expected)
        self.assertGreater(np.linalg.norm(expected-E.conj().T@np.diag(S)), .1)

    def test_repeated_global_ids_cannot_only_sum_cell_diagonal(self):
        S = np.array([[2+1j, 3-.2j], [4j, 5]])
        E = sparse.csr_matrix([[1], [.7j]])
        service = SimpleNamespace(nt=1, m=1, require_frozen=lambda: None,
            cell_records=[(0, None, np.array([0]), E, 'x')],
            single_maps=[(np.array([0, 0]), E.data)], cache={'x': {'schur': S}},
            Htilde=np.array([[0j]]))
        diagonal, inverse, zeros = trace_diagonal(service, np.array([1, 2j]), np.array([1, 3]))
        expected = (E.toarray().conj().T@S@E.toarray())[0, 0]
        self.assertAlmostEqual(diagonal[0], expected)
        self.assertEqual(zeros, 1); self.assertEqual(inverse[1], 1)

    def test_unshifted_nonfinite_Jacobi_rejected(self):
        service = SimpleNamespace(nt=0, m=1, require_frozen=lambda: None,
            cell_records=[], Htilde=np.array([[complex('inf')]]))
        with self.assertRaisesRegex(FloatingPointError, 'nonfinite'):
            trace_diagonal(service, np.ones(1), np.ones(1))

    def test_nonhermitian_LS_protects_bad_fixed_sum(self):
        rng=np.random.default_rng(7602)
        A=rng.normal(size=(7,7))+1j*rng.normal(size=(7,7))
        v=rng.normal(size=7)+1j*rng.normal(size=7)
        D=np.column_stack((v, np.linalg.solve(A, v), -40*np.linalg.solve(A, v)))
        W=A@D; weight, facts=least_residual_weights(v, W)
        self.assertLess(np.linalg.norm(v-W@weight), 1e-11)
        self.assertGreater(np.linalg.norm(v-W@np.array([0,1,1])), np.linalg.norm(v))
        self.assertLessEqual(facts['predicted_residual_norm'], min(r['residual_norm'] for r in facts['candidates'])+1e-12)

    def test_degenerate_and_zero_images_keep_best_single(self):
        v=np.array([1+.4j, -.3j, 2])
        W=np.column_stack((v, 2j*v, np.zeros(3)))
        weight, facts=least_residual_weights(v,W)
        self.assertEqual(facts['rank'],1)
        np.testing.assert_allclose(W@weight,v,rtol=1e-12,atol=1e-12)
        w,r=least_residual_weights(v,np.zeros((3,3),complex))
        self.assertEqual(r['rank'],0);np.testing.assert_array_equal(w,np.zeros(3))

    def test_actual_nonlinear_PC_homogeneity_and_zero(self):
        A=np.array([[2+.3j,4-.4j],[-.8j,3+1j]])
        base=SimpleNamespace(coarse_apply=lambda v:np.array([v[0]/A[0,0],0]),
            local_apply=lambda v:.03*v,calls={'apply':0},seconds={},destroy=lambda:None)
        rows=[]; pc=ResidualMinimizedPC(base,lambda v:A@v,rows.append)
        v=np.array([1+.2j,.5-.4j]);alpha=.4+.7j
        z=pc(v);np.testing.assert_allclose(pc(alpha*v),alpha*z,rtol=1e-11,atol=1e-11)
        np.testing.assert_array_equal(pc(np.zeros(2,complex)),np.zeros(2))
        self.assertTrue(all(r.get('numerical_protection_pass',True) for r in rows))
        self.assertEqual(pc.calls['SMR_zero'],1)

    def test_effect_gates_use_max_and_original_denominators(self):
        self.assertFalse(effect_gate(32,.49,.51)['pass_gate'])
        self.assertTrue(effect_gate(32,.5,.5)['pass_gate'])
        self.assertFalse(effect_gate(64,.11,.09)['pass_gate'])
        self.assertFalse(effect_gate(128,.00101,.0009)['pass_gate'])
        self.assertFalse(effect_gate(32,float('nan'),.1)['pass_gate'])
        self.assertFalse(effect_gate(16,.9,.9)['evaluated'])

    def test_live_FGMRES_first_solution_and_effect_stop(self):
        from petsc4py import PETSc
        from src.solvers.physical_retained_fgmres import run_retained_fgmres
        n=80;diagonal=np.linspace(1,10,n)*(1+.1j)
        rhs=PETSc.Vec().createSeq(n);rhs.array[:]=np.ones(n)
        def action(v):
            out=v.duplicate();out.array[:]=diagonal*v.array;return out
        def identity(v):return v.copy()
        seen=[]
        def evaluate(t,r):
            seen.append(t.array.copy())
            return dict(true=float(r.norm()/rhs.norm()), identity=0.)
        try:
            result=run_retained_fgmres(rhs,action,identity,evaluate=evaluate,
                checkpoint=lambda *args:None,append=lambda *args:None,seconds=lambda:0.,
                restart=128,max_it=32,residual_interval=256,evaluation_iterations=(0,1,32),
                retained_observation_iterations=(16,),retained_tolerance=1e-11,
                evaluation_policy=dict(original_key='true',physical_limits={'true':1e-6},identity_limits={'identity':1e-10}),
                effect_check=lambda row:dict(evaluated=row['iteration']==32,pass_gate=False))
            self.assertEqual(result['status'],'EFFECT_GATE_STOP')
            self.assertEqual(result['iterations'],32)
            self.assertGreater(np.linalg.norm(seen[1]),0)
            self.assertLess(result['snapshots'][1]['schur_true_relative_residual'],1.)
            result['final_solution'].destroy()
        finally:rhs.destroy()

    def test_scope_dispatch_role_resource_and_all_dat(self):
        from src.solvers import controlled_trace_scope as s
        from src.runners.port_preparation import context, storage_limits, scoped_tetra_memory,live_workflow_seconds
        from src.io.independent_tetra_reference import load_tetra_reference
        self.assertEqual(context('v76')[0].TMP,s.window.TMP)
        self.assertEqual(storage_limits('v76')['new_storage_bytes'],16*2**30)
        self.assertEqual(scoped_tetra_memory('v76','B0')['planning_gib'],64)
        self.assertEqual(scoped_tetra_memory('v76','SMR')['planning_gib'],96)
        self.assertEqual(live_workflow_seconds('v76','B0',SimpleNamespace(remaining=lambda r:200),400),200)
        paths=list((s.ROOT/'input/task042_neural_coarse_inverse').glob('v76_*.dat'))
        self.assertEqual(len(paths),6)
        for p in paths:
            spec=load_tetra_reference(p,scope_module=s)
            self.assertEqual(spec.derived['preparation_scope'],'v76')
            self.assertEqual(spec.solver['restart'],128)

    def test_failed_field_policy_never_enters_quadrature(self):
        from unittest.mock import patch
        from src.solvers.bounded_trace_study import finish_retained_fields
        pending={'audit':{'true':.99},'iteration':{'final_evaluation':{'solve_gate_pass':False}}}
        journal=SimpleNamespace(timings={},calls={})
        with tempfile.TemporaryDirectory() as t, patch('src.solvers.independent_tetra_fields.complete_output',side_effect=AssertionError('bad field must not integrate')):
            r=finish_retained_fields(Path(t),journal,{},None,None,None,pending,fail_fast=True)
            self.assertEqual(r['physical_output_status'],'NOT_RUN_BY_FAIL_FAST_POLICY')
            self.assertFalse(r['output']['official'])


if __name__=='__main__':unittest.main()
