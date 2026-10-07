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


if __name__=='__main__':unittest.main()
