"""Only new physical-subdomain algebra/topology/strategy gates."""
import inspect
import unittest
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from src.solvers.physical_impedance_patch import (classify_faces,tangent_mass,
    outward_symbol,halo_matrix)


class PhysicalImpedanceTests(unittest.TestCase):
    def test_periodic_mate_before_boundary(self):
        cells=[[0],[1],[0,1],[0]];mates={0:1,1:0}
        boundary,internal=classify_faces(cells,mates,[0,1],[3])
        self.assertEqual(boundary,[(3,0,'physical_z')]);self.assertEqual(len(internal),2)
        boundary,_=classify_faces(cells,mates,[1],[3])
        self.assertIn((1,1,'artificial'),boundary)

    def test_missing_periodic_pair_rejected(self):
        with self.assertRaisesRegex(ValueError,'mate missing'):
            classify_faces([[0]],{},[0],[])

    def test_arbitrary_normal_hermitian_tangent_mass(self):
        rng=np.random.default_rng(7701);values=rng.normal(size=(8,5,3))+1j*rng.normal(size=(8,5,3))
        normal=np.array([1.,2.,-3.]);weights=np.arange(1,9)/9
        M=tangent_mass(values,weights,normal)
        self.assertLess(np.linalg.norm(M-M.conj().T),1e-12)
        self.assertGreater(np.linalg.eigvalsh(M).min(),0)
        n=normal/np.linalg.norm(normal);z=rng.normal(size=5)+1j*rng.normal(size=5)
        field=np.einsum('qja,j->qa',values,z);t=field-(field@n)[:,None]*n
        self.assertAlmostEqual(float((z.conj()@M@z).real),float(np.sum(weights[:,None]*abs(t)**2)),places=11)

    def test_outgoing_green_sign(self):
        for n in ([1,0,0],[.2,.7,-.4]):
            self.assertLess(np.linalg.norm(outward_symbol(n,[1+.2j,-.3j,.7],8.97,.9998+1e-6j)),1e-13)

    def test_nonhermitian_internal_elimination(self):
        rng=np.random.default_rng(7702);A=rng.normal(size=(7,7))+1j*rng.normal(size=(7,7))+8*np.eye(7)
        rhs=rng.normal(size=7)+1j*rng.normal(size=7)
        ii=A[4:,4:];S=A[:4,:4]-A[:4,4:]@np.linalg.solve(ii,A[4:,:4])
        g=rhs[:4]-A[:4,4:]@np.linalg.solve(ii,rhs[4:]);t=np.linalg.solve(S,g)
        x=np.r_[t,np.linalg.solve(ii,rhs[4:]-A[4:,:4]@t)]
        self.assertLess(np.linalg.norm(A@x-rhs),1e-12)
        self.assertGreater(np.linalg.norm(A[:4,4:]-A[4:,:4].conj().T),1)

    def test_halo_only_complex_mpc_dual(self):
        E=sparse.csr_matrix(np.array([[1+.5j,0],[0,.3-.8j]]))
        S=np.array([[2+.4j,3-.2j],[-1j,4-.7j]])
        a=SimpleNamespace(nt=2,cell_records=[(0,None,np.array([0,1]),E,'inside'),
            (1,None,np.array([0,1]),E,'outside')],cache={'inside':{'schur':S},'outside':{'schur':99*S}})
        p=dict(ids=np.array([0,1]),halo_cells=np.array([0]))
        faces=SimpleNamespace(boundary=lambda _: ([],[]),s={'data':SimpleNamespace(cell_tags=SimpleNamespace(values=np.array([1,2])))},mates={})
        A,rec=halo_matrix(a,p,faces)
        np.testing.assert_allclose(A.toarray(),E.toarray().conj().T@S@E.toarray(),rtol=1e-14,atol=1e-14)
        self.assertEqual(rec['body_cell_ids'],[0]);self.assertEqual(rec['body_cells_outside_halo'],0)

    def test_new_effect_policy_and_800_action_cap(self):
        from src.solvers import impedance_trace_scope as scope
        self.assertFalse(scope.effect_check(32,.31,.20)['pass_gate'])
        self.assertTrue(scope.effect_check(32,.29,.30)['pass_gate'])
        self.assertFalse(scope.effect_check(64,.10001,.08)['pass_gate'])
        self.assertEqual(scope.plan_record()['action_limit'],800)
        self.assertEqual(scope.solver_for('ITERATE')['restart'],128)
        self.assertEqual(scope.memory_budget('PREPARE')['planning_gib'],96)

    def test_explicit_factory_and_namespace_plumbing(self):
        from src.solvers.controlled_trace_study import iterate
        from src.runners.port_preparation import scoped_tetra_memory,storage_limits
        self.assertIn('pc_factory',inspect.signature(iterate).parameters)
        self.assertIn('scope',inspect.signature(iterate).parameters)
        self.assertEqual(scoped_tetra_memory('v77','ITERATE')['sampled_stop_gib'],128)
        self.assertEqual(storage_limits('v77')['new_storage_bytes'],24*2**30)


if __name__=='__main__':unittest.main()
