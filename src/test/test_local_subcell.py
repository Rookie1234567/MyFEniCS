"""Only the new local restriction and two-level algebra contracts."""
import unittest
import numpy as np
from scipy.linalg import lu_factor,lu_solve
from src.solvers.local_trace_assembly import entity_trace_support,restrict_local,exact_graph
from src.solvers.trace_interior_restriction import dense_restricted_witness


class LocalTests(unittest.TestCase):
    def test_actual_inverse_apply_saves_low_before_high_recovery(self):
        from types import SimpleNamespace as NS
        from scipy import sparse
        from petsc4py import PETSc
        from src.solvers.local_trace_assembly import LocalRestrictedInverse
        rng=np.random.default_rng(60061);n=43
        A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+100*np.eye(n)
        i=np.array([0]);b=np.arange(1,n);lu=lu_factor(A[np.ix_(i,i)])
        schur=A[np.ix_(b,b)]-A[np.ix_(b,i)]@lu_solve(lu,A[np.ix_(i,b)])
        high_constraints=NS(expansion_by_original={1:(np.array([0]),np.array([1.])),2:(np.array([1]),np.array([1.]))})
        ambient=NS(appended_rows=40,full_rows=3,cell_recovery_maps=[NS(class_key=0,interior_original_dofs=i,trace_original_dofs=np.array([1,2]))],
            trace_constraints=high_constraints,trace_from_interior_rhs_by_class={0:-A[np.ix_([1,2],i)]@lu_solve(lu,np.eye(1))},
            interior_lu_by_class={0:lu},interior_from_trace_by_class={0:-lu_solve(lu,A[np.ix_(i,[1,2])])})
        term=NS(Bi=A[np.ix_(i,np.arange(3,n))],Di=-A[np.ix_(np.arange(3,n),i)],port_indices=np.arange(40))
        restriction=NS(R=sparse.eye(2,format='csr'),high_native_rows=np.array([1,2]),R_shape=(2,2))
        system=NS(ambient=ambient,restriction=restriction,port_terms={0:term})
        class Factor:
            def solve_repeated(self,load,target):target.array[:]=np.linalg.solve(schur,load.array)
        calls=[];inverse=LocalRestrictedInverse(system,Factor(),state_callback=lambda z,f,r:calls.append(z.copy()))
        rhs=PETSc.Vec().createSeq(3);rhs.array[:]=[1+.4j,-.7+.1j,.2-.3j]
        try:
            u=inverse.apply(rhs);direct=np.linalg.solve(A,np.r_[rhs.array,np.zeros(40)])
            self.assertEqual(len(calls),1);self.assertEqual(len(inverse.last_port_solution),40)
            self.assertLess(np.linalg.norm(u.array-direct[:3]),1e-12)
            self.assertLess(np.linalg.norm(inverse.last_port_solution-direct[3:]),1e-12);u.destroy()
        finally:rhs.destroy()

    def test_worker_uses_boundary_allowance_not_launch_guard(self):
        from unittest.mock import patch
        from src.solvers import local_subcell_scope as s
        with patch.object(s.window,'remaining',side_effect=RuntimeError('launch only')), \
             patch.object(s.window,'available_at_boundary',return_value=4000), \
             patch.object(s,'stage',return_value={'pass_gate':True}):
            s.require_stage('C67')

    def test_nonmutual_40port_nonzero_internal(self):
        r=dense_restricted_witness(6001)
        self.assertLess(max(r[k] for k in ('mixed','recovery','lift_invariance')),1e-10)
        self.assertGreater(r['ambient'],1e-3)
        self.assertTrue(r['nonzero_internal_rhs'] and r['nonzero_40port_rhs'])

    def test_entity_closure_preserves_edge_face(self):
        import basix
        a=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,2)
        b=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,3)
        support=entity_trace_support(a,b)
        face=b.entity_dofs[2][0];closure=a.entity_closure_dofs[2][0]
        self.assertTrue(support[np.ix_(face,closure)].all())
        edge=b.entity_dofs[1][0]
        self.assertEqual(set(np.flatnonzero(support[edge[0]])),set(a.entity_closure_dofs[1][0]))
        self.assertFalse(support[edge[0],a.entity_dofs[3][0]].any())

    def test_complex_dual_not_transpose(self):
        rng=np.random.default_rng(6002);A=rng.normal(size=(7,7))+1j*rng.normal(size=(7,7))
        L=rng.normal(size=(7,3))+1j*rng.normal(size=(7,3))
        self.assertLess(np.linalg.norm(restrict_local(A,L)-L.conj().T@A@L),1e-12)
        self.assertGreater(np.linalg.norm(restrict_local(A,L)-L.T@A@L),1.)

    def test_two_stage_affine_recovery(self):
        rng=np.random.default_rng(6003);n=17;A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+25*np.eye(n)
        b=rng.normal(size=n)+1j*rng.normal(size=n);i=np.arange(5);t=np.arange(5,n)
        lu=lu_factor(A[np.ix_(i,i)]);S=A[np.ix_(t,t)]-A[np.ix_(t,i)]@lu_solve(lu,A[np.ix_(i,t)])
        f=b[t]-A[np.ix_(t,i)]@lu_solve(lu,b[i]);j=np.arange(4);k=np.arange(4,12)
        lu2=lu_factor(S[np.ix_(j,j)]);B=S[np.ix_(k,k)]-S[np.ix_(k,j)]@lu_solve(lu2,S[np.ix_(j,k)])
        g=f[k]-S[np.ix_(k,j)]@lu_solve(lu2,f[j]);z=np.zeros(12,complex);z[k]=np.linalg.solve(B,g)
        z[j]=lu_solve(lu2,f[j]-S[np.ix_(j,k)]@z[k]);u=np.r_[lu_solve(lu,b[i]-A[np.ix_(i,t)]@z),z]
        self.assertLess(np.linalg.norm(u-np.linalg.solve(A,b)),1e-12)

    def test_graph_is_topological(self):
        from scipy import sparse
        data=((np.array([0,1]),sparse.eye(2),True),(np.array([1,2]),sparse.eye(2),True))
        c,r=exact_graph(data,3,[0,2],2)
        self.assertEqual(r['actual_topology_nnz_envelope'],19)
        self.assertEqual(int(c.sum()),19)


if __name__=='__main__':unittest.main()
