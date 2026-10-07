"""Targeted restricted-space complex dual, adapter and namespace tests."""
import unittest
from unittest.mock import MagicMock
import numpy as np
from scipy import sparse
from src.solvers.trace_interior_restriction import dense_restricted_witness,sparse_projection,RestrictedTraceFactor,mixed_norms


class Tests(unittest.TestCase):
    def test_mixed_not_ambient(self):
        r=dense_restricted_witness()
        for k in ('recovery','lift_invariance','mixed'):self.assertLess(r[k],1e-10)
        self.assertGreater(r['ambient'],1e-3)
        self.assertGreater(r['transpose_counterexample'],.01)
        self.assertTrue(r['nonzero_internal_rhs'] and r['nonzero_40port_rhs'])

    def test_sparse_petsc_hermitian_projection_and_factor_port_scale_once(self):
        from petsc4py import PETSc
        rng=np.random.default_rng(5959)
        R=sparse.csr_matrix(rng.normal(size=(6,3))+1j*rng.normal(size=(6,3)))
        Q=sparse.block_diag((R,sparse.eye(40)),format='csr').toarray()
        A=rng.normal(size=(46,46))+1j*rng.normal(size=(46,46))+20*np.eye(46)
        csr=sparse.csr_matrix(A);mat=PETSc.Mat().createAIJ(size=A.shape,csr=(csr.indptr.astype(PETSc.IntType),csr.indices.astype(PETSc.IntType),csr.data),comm=PETSc.COMM_SELF)
        j=MagicMock();low=sparse_projection(mat,R,40,j)
        try:
            ip,ix,v=low.getValuesCSR();actual=sparse.csr_matrix((v,ix,ip),shape=low.getSize()).toarray()
            np.testing.assert_allclose(actual,Q.conj().T@A@Q,rtol=1e-13,atol=1e-11)
            f=rng.normal(size=46)+1j*rng.normal(size=46)
            class Factor:
                def solve_repeated(self,rhs,target):target.array[:]=np.linalg.solve(actual,rhs.array)
            adapter=RestrictedTraceFactor(R,40,Factor());rhs=PETSc.Vec().createSeq(46,comm=PETSc.COMM_SELF);rhs.array[:]=f;out=rhs.duplicate()
            try:
                adapter.solve_repeated(rhs,out)
                np.testing.assert_allclose(out.array,Q@np.linalg.solve(actual,Q.conj().T@f),rtol=1e-13,atol=1e-12)
            finally:rhs.destroy();out.destroy()
        finally:low.destroy();mat.destroy()

    def test_p8_optin_not_default(self):
        from src.constraints.floquet_3d import _qualified_constraint_mode
        with self.assertRaises(NotImplementedError):_qualified_constraint_mode(8,fixed_target_high_order=True)
        self.assertEqual(_qualified_constraint_mode(8,fixed_target_high_order=True,finite_authority_interior8=True),'topological_trace_p8')

    def test_dat_actual_ambient_and_mixed_inventory(self):
        from src.io.phase_notch_hp import load_phase_notch_hp
        from src.solvers import trace_interior_scope as scope
        from src.runners.port_preparation import storage_limits,preparation_memory_envelope,context
        for q in (7,8):
            s=load_phase_notch_hp(scope.ROOT/f'input/task042_neural_coarse_inverse/v59_trace6_interior{q}.dat',scope=scope)
            self.assertEqual(s.discretization['degree'],q);self.assertEqual(s.discretization['trace_degree'],6)
            self.assertEqual(s.discretization['mixed_rows'],33660);self.assertEqual(s.derived['preparation_scope'],'v59')
            self.assertEqual(s.execution['planning_memory_gib'],64);self.assertEqual(s.execution['terminate_memory_gib'],96)
            self.assertEqual(dict(s.derived['storage_limits']),storage_limits('v59'))
        self.assertEqual(context('v59')[0],scope.window)
        self.assertEqual(preparation_memory_envelope('v59')['planning_cap_bytes'],64*2**30)

    def test_pull_interior_and_trace_without_changing_denominator(self):
        class Map:
            internal_rows=np.array([0,1]);high_native_rows=np.array([2,3])
            def pull_native(self,x):return np.r_[x[:2],np.conj(1j)*x[2]+x[3]]
        v=np.array([0,0,1,1j],complex);rhs=np.ones(4,complex)
        r=mixed_norms(dict(residual=v,augmented_residual=v,port_residual=np.zeros(40),projected=np.ones(40)),rhs,Map())
        self.assertLess(r['true'],1e-14);self.assertGreater(r['ambient_relative'],.1)


if __name__=='__main__':unittest.main()
