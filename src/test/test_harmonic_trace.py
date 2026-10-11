"""Necessary new harmonic algebra/dual/closure and cumulative counter tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from src.solvers.harmonic_trace_coarse import HarmonicTransfer,local_extension,entity_on_parent_boundary
from src.solvers.bounded_trace_pc import BoundedTwoLevelPC
from src.solvers.bounded_trace_study import action_charge


class HarmonicTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(7400)
        self.A=rng.normal(size=(8,8))+1j*rng.normal(size=(8,8))+np.diag(np.arange(8)+8)
        self.J=np.array([2,3,4]);self.Q=np.array([0,1,5,6,7])
        self.P=np.array([[1,.2j],[.3,1],[1j,-.2]])
        self.ZB=sparse.csr_matrix((6,2),dtype=complex).tolil();self.ZB[[0,1,5],:]=self.P;self.ZB=self.ZB.tocsr()
        self.map=np.zeros((5,4),complex);self.map[:3,:2]=self.P;self.map[3:,2:]=np.eye(2)
        F=self.A[np.ix_(self.J,self.J)]
        AJQ=self.A[np.ix_(self.J,self.Q)]@self.map
        AQJ=self.map.conj().T@self.A[np.ix_(self.Q,self.J)]
        U,self.correction=local_extension(F,AJQ,AQJ)
        self.T=HarmonicTransfer(self.ZB,[dict(rows=self.J,columns=np.arange(4),values=U)],2)
        self.Z=np.column_stack([self.T.prolong(np.eye(4,dtype=complex)[:,i]) for i in range(4)])

    def test_nonhermitian_nonzero_port_condensation(self):
        S=self.A[np.ix_(self.Q,self.Q)]-self.A[np.ix_(self.Q,self.J)]@np.linalg.solve(self.A[np.ix_(self.J,self.J)],self.A[np.ix_(self.J,self.Q)])
        EH=self.map.conj().T@S@self.map
        np.testing.assert_allclose(EH,self.Z.conj().T@self.A@self.Z,rtol=1e-13,atol=1e-13)
        np.testing.assert_allclose((self.A@self.Z)[self.J],0,atol=1e-13)
        self.assertGreater(np.linalg.norm(self.Z[self.J,2:]),.01)
        wrong=self.map.conj().T@self.A[np.ix_(self.Q,self.Q)]@self.map-self.correction
        self.assertGreater(np.linalg.norm(EH-wrong),.01)

    def test_full_complex_dual_has_interior_port_feedback(self):
        r=np.arange(8)*(1+.2j);w=np.arange(4)*(.3+.4j)
        np.testing.assert_allclose(self.T.restrict(r),self.Z.conj().T@r,atol=1e-13)
        self.assertAlmostEqual(abs(np.vdot(self.T.prolong(w),r)-np.vdot(w,self.T.restrict(r))),0,places=12)
        self.assertGreater(np.linalg.norm(self.T.restrict(r)[2:]-r[6:]),.01)

    def test_coarse_pc_uses_explicit_transfer_protocol(self):
        EH=self.Z.conj().T@self.A@self.Z
        pc=BoundedTwoLevelPC(self.ZB,[],[],EH,lambda v:self.A@v,transfer=self.T)
        pc.solve=lambda A,b:np.linalg.solve(A,b)
        r=np.arange(8)*(1+.4j)
        np.testing.assert_allclose(pc.coarse_apply(r),self.Z@np.linalg.solve(EH,self.Z.conj().T@r))

    def test_single_parent_exterior_is_skeleton(self):
        v=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
        self.assertTrue(entity_on_parent_boundary(v[[1,2,3]],v))
        self.assertTrue(entity_on_parent_boundary(v[[0,1]],v))
        self.assertFalse(entity_on_parent_boundary(np.array([[.1,.1,.1],[.2,.2,.2]]),v))
        with self.assertRaisesRegex(ValueError,'outside'):entity_on_parent_boundary(np.array([[2,0,0]]),v)

    def test_resident_capacity_and_singular_local_rejection(self):
        with self.assertRaises(MemoryError):HarmonicTransfer(self.ZB,self.T.lifts,2,limit_bytes=1)
        with self.assertRaises(np.linalg.LinAlgError):local_extension(np.zeros((2,2)),np.ones((2,1)),np.ones((1,2)))

    def test_local_assembly_full_port_and_conjugate_maps(self):
        from src.solvers.harmonic_trace_coarse import macro_blocks
        rng=np.random.default_rng(7404)
        E=rng.normal(size=(110,5))+1j*rng.normal(size=(110,5))
        S=rng.normal(size=(110,110))+1j*rng.normal(size=(110,110))
        C=rng.normal(size=(5,3))+1j*rng.normal(size=(5,3))
        D=rng.normal(size=(3,5))+1j*rng.normal(size=(3,5))
        Z=rng.normal(size=(5,2))+1j*rng.normal(size=(5,2));J=np.array([1,2]);Z[J]=0
        service=SimpleNamespace(nt=5,cell_records=[(0,None,np.arange(5),sparse.csr_matrix(E),'a')],
            cache={'a':{'schur':S}},Ctilde=sparse.csr_matrix(C),Dtilde=sparse.csr_matrix(D))
        left=np.r_[np.ones(5),[2,3,4]];right=np.r_[np.ones(5),[.2j,.3j,.4j]]
        F,AR,AL,cols=macro_blocks(service,[0],J,sparse.csr_matrix(Z),left,right)
        K=E.conj().T@S@E
        np.testing.assert_allclose(F.toarray(),K[np.ix_(J,J)],rtol=1e-13,atol=1e-10)
        np.testing.assert_allclose(AR,np.column_stack((K[J]@Z,C[J]*right[5:])),atol=1e-10)
        np.testing.assert_allclose(AL,np.row_stack((Z.conj().T@K[:,J],left[5:,None]*D[:,J])),atol=1e-10)
        np.testing.assert_array_equal(cols,np.arange(5))

    def test_800_cumulative_no_inherited_600_cap(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'action_counts.json';p.write_text(json.dumps(dict(started=600,completed=600,by_kind={})))
            scope=SimpleNamespace(NAMESPACE='v74',window=SimpleNamespace(TMP=Path(d)),plan_record=lambda:dict(action_limit=800))
            for i in range(200):self.assertEqual(action_charge('I_outer',lambda:3,scope=scope),3)
            with self.assertRaisesRegex(RuntimeError,'upper cap'):action_charge('I_outer',lambda:3,scope=scope)
            self.assertEqual(json.loads(p.read_text())['started'],800)

    def test_hot_instance_explicit_800(self):
        from src.solvers.hot_tetra_trace import HotTracePacket
        h=HotTracePacket.__new__(HotTracePacket);h.require_frozen=lambda:None
        h.nt=1;h.m=1;h.retained=np.arange(2);h.action_limit=800
        h.Ctilde=sparse.csr_matrix([[1j]]);h.Dtilde=sparse.csr_matrix([[2+1j]]);h.Htilde=np.array([[3j]])
        h.groups={};h.calls=dict(trace_action=599,boundary_C=0,boundary_D=0)
        for i in range(201):np.testing.assert_allclose(h.apply_trace(np.ones(2,complex)),[1j,2+4j])
        with self.assertRaisesRegex(RuntimeError,'budget'):h.apply_trace(np.ones(2,complex))
        self.assertEqual(h.calls['trace_action'],800)

    def test_live_launcher_uses_own_storage_and_memory(self):
        from src.runners.port_preparation import storage_limits,context,scoped_tetra_memory
        from src.solvers import harmonic_trace_scope as scope
        p=scope.plan_record()
        self.assertEqual(storage_limits('v74')['task_storage_bytes'],696*2**30)
        self.assertIs(context('v74')[0],scope.window)
        self.assertEqual(scoped_tetra_memory('v74','HARMONIC_PREPARE')['planning_gib'],96)
        self.assertEqual(scoped_tetra_memory('v74','PREFLIGHT')['planning_gib'],64)
        self.assertEqual(scope.memory_budget('HARMONIC')['sampled_stop_gib'],128)
        self.assertEqual(p['action_limit'],800)

    def test_live_H_interval_equals_same_settled_interval(self):
        from unittest.mock import patch
        from src.solvers.harmonic_trace_scope import HarmonicWindow
        with tempfile.TemporaryDirectory() as d:
            clock=Path(d)/'window.json';clock.write_text(json.dumps(dict(start_monotonic=0)))
            book=dict(runs=[dict(role='PREFLIGHT',elapsed_seconds=100),dict(role='focused',elapsed_seconds=20)],
                active=dict(role='HARMONIC_PREPARE',before_clock=dict(observed_monotonic=1000)))
            settled=[120.]
            w=SimpleNamespace(total=39600,WINDOW_PATH=clock,ledger=lambda:book,charged_wall=lambda:settled[0])
            with patch('src.solvers.harmonic_trace_scope.time.monotonic',return_value=2000):
                live=HarmonicWindow.case_remaining(w,active=True)
                book['runs'].append(dict(role='HARMONIC_PREPARE',elapsed_seconds=1000))
                book['active']=None;settled[0]+=1000
                boundary=HarmonicWindow.case_remaining(w,case='HARMONIC_PREPARE')
            self.assertEqual(live,boundary)
            self.assertEqual(live,14400-2000)

    def test_qualification_counter_12(self):
        with tempfile.TemporaryDirectory() as d:
            scope=SimpleNamespace(NAMESPACE='v74',window=SimpleNamespace(TMP=Path(d)),plan_record=lambda:dict(action_limit=800))
            for i in range(12):action_charge('Q_harmonic',lambda:3,scope=scope)
            with self.assertRaisesRegex(RuntimeError,'qualification'):action_charge('D_physical',lambda:3,scope=scope)


if __name__=='__main__':unittest.main()
