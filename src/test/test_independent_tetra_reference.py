"""Only the newly introduced topology, complex pullback and receiver contracts."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from src.solvers.independent_tetra_reference import periodic_expansion
from src.io.independent_tetra_reference import load_tetra_reference
from src.solvers import independent_tetra_scope as scope


class TetraReferenceTests(unittest.TestCase):
    def test_complex_periodic_primal_and_Hermitian_dual(self):
        phase=np.exp(.37j)
        class Masters:
            def links(self,row):return np.array([0,1]) if row==3 else np.array([row])
        mpc=SimpleNamespace(slaves=np.array([3]),masters=Masters(),coefficients=lambda:(np.array([phase,1j]),np.array([0,0,0,0,2])))
        V=SimpleNamespace(dofmap=SimpleNamespace(index_map=SimpleNamespace(size_local=4)))
        P,masters=periodic_expansion(V,mpc)
        self.assertEqual(list(masters),[0,1,2])
        self.assertEqual(P.shape,(4,3));self.assertEqual(P[3,0],phase)
        rng=np.random.default_rng(62);A=rng.normal(size=(4,4))+1j*rng.normal(size=(4,4));b=np.arange(4)+1j
        self.assertGreater(np.linalg.norm(P.T@A@P-P.conj().T@A@P),.1)
        x=np.linalg.solve(P.conj().T@A@P,P.conj().T@b)
        self.assertLess(np.linalg.norm(P.conj().T@(b-A@P@x)),1e-12)

    def test_nonmutual_ports_and_nonzero_full_RHS(self):
        rng=np.random.default_rng(621);K=5*np.eye(6)+rng.normal(size=(6,6))+1j*rng.normal(size=(6,6))
        C=rng.normal(size=(6,40))+1j*rng.normal(size=(6,40));D=rng.normal(size=(40,6))+1j*rng.normal(size=(40,6));H=np.diag(np.arange(40)+4.)
        A=sparse.bmat([[K,C],[-D,H]]).toarray();b=rng.normal(size=46)+1j*rng.normal(size=46);x=np.linalg.solve(A,b)
        self.assertLess(np.linalg.norm(b-A@x)/np.linalg.norm(b),1e-12)
        self.assertGreater(np.linalg.norm(D-C.conj().T),1.)
        self.assertGreater(np.linalg.norm(b[6:]),1.)
        self.assertLess(np.linalg.norm((-D@x[:6]+H@x[6:])-b[6:]),1e-12)

    def test_actual_one_run_descriptor_not_hex_template(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'case.dat'
            for role in scope.STAGES:
                p.write_text('schema_version = 1\n[task042_v62]\nstage = '+json.dumps(role)+'\nrun_id = "task042_v62_test"\n')
                s=load_tetra_reference(p)
                self.assertEqual(s.discretization['cell_type'],'tetrahedron')
                self.assertFalse(s.discretization['static_condensation'])
                self.assertEqual(s.boundary['complete_modes'],828)
                self.assertEqual(s.execution['planning_memory_gib'],64)
                self.assertEqual(s.geometry['cells'],scope.case_spec(role)['cells'])
                self.assertEqual(len(s.geometry['axes_nm']['z']),21 if role=='TH3' else 11)


if __name__=='__main__':unittest.main()
