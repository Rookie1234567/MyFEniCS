"""Only the new face complement, complex restriction and namespace contracts."""
import unittest
import numpy as np
from src.solvers.face_trace_basis import mass_complement,dense_face_witness


class FaceTraceTests(unittest.TestCase):
    def test_keeps_original_and_uses_physical_mass(self):
        rng=np.random.default_rng(612);P=rng.normal(size=(12,4))+1j*rng.normal(size=(12,4));copy=P.copy()
        M=rng.normal(size=(12,12));G=M.T@M+np.eye(12)
        Z,r=mass_complement(P,G)
        self.assertTrue(r['pass_gate']);np.testing.assert_array_equal(P,copy)
        self.assertEqual(Z.shape,(12,8));self.assertEqual(np.linalg.matrix_rank(np.c_[P,Z]),12)
        self.assertGreater(np.linalg.norm(P.conj().T@Z),1e-3)

    def test_rejects_bad_mass_and_dependent_columns(self):
        P=np.ones((5,2),complex)
        with self.assertRaises(ValueError):mass_complement(P,np.eye(5))
        P=np.eye(5,dtype=complex)[:,:2];G=np.eye(5,dtype=complex);G[0,1]=1j
        with self.assertRaises(ValueError):mass_complement(P,G)

    def test_nonmutual_ports_affine_recovery_and_ambient_failure(self):
        r=dense_face_witness()
        self.assertLess(max(r['mixed'],r['recovery']),1e-12)
        self.assertGreater(r['ambient'],1e-3);self.assertGreater(r['wrong_transpose'],.1)
        self.assertTrue(r['nonzero_internal']);self.assertTrue(r['nonzero_40port'])

    def test_actual_dat_namespace_dimensions_and_memory(self):
        from src.solvers import face_trace_scope as scope
        from src.io.phase_notch_hp import load_phase_notch_hp
        from src.runners.port_preparation import storage_limits,context
        for name,role,rows in [('v61_face_x_enrichment','FX',66300),('v61_face_xy_enrichment','FXY',98940)]:
            s=load_phase_notch_hp(scope.ROOT/'input/task042_neural_coarse_inverse'/f'{name}.dat',scope=scope)
            self.assertEqual(s.derived['preparation_scope'],'v61');self.assertEqual(s.derived['stage'],role)
            self.assertEqual(s.discretization['condensed_rows'],rows)
            self.assertEqual(s.discretization['face_complement'],204)
            self.assertEqual(s.execution['planning_memory_gib'],64)
            self.assertEqual(s.execution['terminate_memory_gib'],96)
        self.assertEqual(storage_limits('v61')['task_storage_bytes'],180*2**30)
        self.assertIs(context('v61')[0],scope.window)
        self.assertNotEqual(context('v60')[0].WINDOW_PATH,scope.window.WINDOW_PATH)

    def test_sparse_port_pullback_keeps_nonmutual_complex_dual(self):
        from scipy import sparse
        from src.solvers.face_trace_mapping import FaceEnrichedMap
        rng=np.random.default_rng(618);M=rng.normal(size=(11,7))+1j*rng.normal(size=(11,7))
        m=FaceEnrichedMap.__new__(FaceEnrichedMap);m.J=sparse.csr_matrix(M);rows=np.array([1,4,9]);v=rng.normal(size=3)+1j*rng.normal(size=3)
        np.testing.assert_allclose(m.pull_port(rows,v),M[rows].conj().T@v,rtol=1e-13,atol=1e-13)
        np.testing.assert_allclose(m.pull_port(rows,v,dual=False),M[rows].T@v,rtol=1e-13,atol=1e-13)
        self.assertGreater(np.linalg.norm(m.pull_port(rows,v)-m.pull_port(rows,v,dual=False)),1.)


if __name__=='__main__':unittest.main()
