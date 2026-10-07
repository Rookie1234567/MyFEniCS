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


def synthetic_saved_witness():
    from benchmarks.collect_trace_interior import restricted_array_check
    rng=np.random.default_rng(5971);ni,nh,nt,np_=4,5,2,40;N=ni+nh+1
    R=sparse.csr_matrix(rng.normal(size=(nh,nt))+1j*rng.normal(size=(nh,nt)))
    h=rng.normal(size=nh)+1j*rng.normal(size=nh)
    defect=h-R@np.linalg.lstsq(R.toarray(),h,rcond=None)[0]
    residual=np.r_[np.zeros(ni),defect,0].astype(complex)
    ids=np.arange(ni);trace=np.arange(ni,ni+nh);slaves=np.array([N-1])
    gamma=rng.normal(size=nt)+1j*rng.normal(size=nt);u=np.r_[rng.normal(size=ni),R@gamma,0].astype(complex)
    port=rng.normal(size=np_)+1j*rng.normal(size=np_);H=1+.2j+np.arange(np_)/100;projected=H*port
    rhs=rng.normal(size=N)+1j*rng.normal(size=N);rhs[-1]=0
    coupling=rng.normal(size=N)+1j*rng.normal(size=N);coupling[-1]=0
    vol=rhs-coupling-residual;inside=np.zeros(N,complex);inside[ids]=vol[ids];tr=vol-inside
    ri=(rhs-inside-tr-coupling)[ids];nums=np.linalg.norm(ri.reshape(2,-1),axis=1)
    scale=sum(np.linalg.norm(x[ids].reshape(2,-1),axis=1) for x in (rhs,inside,tr,coupling))
    v=dict(rhs=rhs,residual=residual,augmented_top=residual.copy(),volume_action=vol,volume_inside=inside,volume_trace=tr,
        volume_curl=.6*vol,volume_mass=.4*vol,coupling_action=coupling,native_boundary_action=coupling.copy(),u_storage=u,
        port_residual=np.zeros(np_,complex),projected=projected,H=H,port=port,internal_rows=ids,internal_residual=ri,
        internal_numerators=nums,internal_operation_scale=scale,slaves=slaves)
    m=dict(R_data=R.data,R_indices=R.indices,R_indptr=R.indptr,R_shape=np.array(R.shape),internal_rows=ids,high_native_rows=trace,
        low_native_rows=np.arange(nt),owner=np.zeros(nh,int))
    a=dict(u_storage=u,port=port,low_trace=gamma,rhs=rhs,slaves=slaves)
    pull=lambda x:np.r_[x[ids],R.conj().T@x[trace]]
    saved=dict(mixed_residual=pull(residual),mixed_augmented_top=pull(residual),mixed_rhs=pull(rhs),ambient_residual=residual,
        port_residual=v['port_residual'],projected=projected)
    spec=dict(mixed_trace=nt,trace=nh,internal=ni,independent=ni+nh,complete_modes=np_,cells=2)
    return restricted_array_check,v,m,a,saved,spec


class SavedCheckerTests(unittest.TestCase):
    def test_projection_capacity_counts_stored_tiny_support(self):
        from types import SimpleNamespace
        from src.solvers.trace_interior_restriction import projection_pattern_envelope
        rng=np.random.default_rng(5968)
        R=sparse.csr_matrix(rng.normal(size=(6,3))+1j*rng.normal(size=(6,3)))
        R.data[0]=1e-100
        maps=SimpleNamespace(R=R,rows=[(None,np.arange(4),0),(None,np.arange(2,6),0)],
            high_constraints=SimpleNamespace(expansion_by_original={i:(np.array([i]),np.ones(1)) for i in range(6)}))
        plan=projection_pattern_envelope(maps,40)
        Q=sparse.block_diag((R,sparse.eye(40)),format='csr').toarray()
        A=rng.normal(size=(46,46))+1j*rng.normal(size=(46,46))
        self.assertGreaterEqual(plan['intermediate_nnz_upper'],np.count_nonzero(A@Q))
        self.assertGreaterEqual(plan['low_nnz_upper'],np.count_nonzero(Q.conj().T@A@Q))
        self.assertEqual(plan['cell_low_support_max'],3)
        self.assertTrue(plan['all_stored_interpolation_entries_counted'])
        self.assertTrue(plan['no_dense_numeric_projection'])
        self.assertTrue(plan['bounded_integer_incidence_storage'])

    def test_cost_binding_uses_actual_consumer_scope(self):
        import json,tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from benchmarks.collect_phase_deployment import cost_binding
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);manifest=dict(source_sha='a'*40,input_sha256='b'*64,physical_sha256='c'*64)
            (directory/'run_manifest.json').write_text(json.dumps(manifest))
            r=cost_binding(dict(role='M67',source_sha='a'*40),manifest,directory,active_scope=SimpleNamespace(STAGES=('M67',)))
            self.assertEqual(r['binding_scope'],'formal_one_run');self.assertEqual(r['physical_sha256'],'c'*64)

    def test_correct_mixed_solution_has_nonzero_ambient_defect(self):
        check,*args=synthetic_saved_witness();r=check(*args)
        self.assertTrue(r['pass_gate']);self.assertLess(r['mixed']['true'],1e-14);self.assertGreater(r['ambient_relative'],.01)
        self.assertEqual(r['included_internal_rows'],4);self.assertEqual(r['included_port_rows'],40)

    def test_missing_internal_rows_is_not_a_false_pass(self):
        check,v,m,a,saved,spec=synthetic_saved_witness();m=dict(m,internal_rows=m['internal_rows'][:-1])
        with self.assertRaisesRegex(ValueError,'row inventory'):check(v,m,a,saved,spec)

    def test_wrong_complex_dual_is_rejected(self):
        check,v,m,a,saved,spec=synthetic_saved_witness();m=dict(m,R_data=np.conj(m['R_data']))
        with self.assertRaisesRegex(ValueError,'pullback member differs'):check(v,m,a,saved,spec)


if __name__=='__main__':unittest.main()
