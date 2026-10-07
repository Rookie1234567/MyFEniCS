"""Only the new local restriction and two-level algebra contracts."""
import unittest
import numpy as np
from scipy.linalg import lu_factor,lu_solve
from src.solvers.local_trace_assembly import entity_trace_support,restrict_local,exact_graph
from src.solvers.trace_interior_restriction import dense_restricted_witness


class LocalTests(unittest.TestCase):
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
