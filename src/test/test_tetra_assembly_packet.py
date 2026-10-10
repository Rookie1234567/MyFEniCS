"""Only new cell/port algebra, disk isolation and V70 early wiring."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import sparse
from src.solvers.tetra_assembly_packet import local_elimination,LocalTracePacket,RetainedPacket,_seal
from src.solvers.exact_tetra_condensation import _write_array
from src.solvers.scattering_anchor import save_arrays


class AssemblyPacketTests(unittest.TestCase):
    def test_compiled_identity_with_missing_FFCx_header(self):
        from src.solvers.tetra_cell_kernel import compiled_identity
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'module.so';p.write_bytes(b'compiled fixture')
            a=compiled_identity((None,'C source'),p)
            self.assertEqual(len(a['compiled_module_sha256']),64)
            self.assertNotEqual(a['compiled_code_sha256'],compiled_identity((None,None),p)['compiled_code_sha256'])
            p.write_bytes(b'different compiled fixture')
            self.assertNotEqual(a['compiled_module_sha256'],compiled_identity((None,'C source'),p)['compiled_module_sha256'])

    def test_packed_coefficient_kernel_key_not_first_item(self):
        from src.solvers.tetra_cell_kernel import packed_cell_coefficients
        from dolfinx import fem
        values=np.array([[1.+.17j],[2.-.2j]])
        for key in [(fem.IntegralType.cell,0),(fem.IntegralType.cell,-1),(fem.IntegralType.cell,-1,0)]:
            a,k=packed_cell_coefficients({key:values},fem.IntegralType.cell)
            np.testing.assert_array_equal(a,values);self.assertEqual(k,key)
        for packed in [{(fem.IntegralType.cell,1):values},
                       {(fem.IntegralType.cell,3,0):values},
                       {(fem.IntegralType.cell,-1,1):values},
                       {(fem.IntegralType.cell,-1,0):values,(fem.IntegralType.cell,3,0):values}]:
            with self.assertRaises(ValueError):packed_cell_coefficients(packed,fem.IntegralType.cell)

    def fixture(self,root):
        rng=np.random.default_rng(7000);n=140;m=40;nt=110
        raw=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+200*np.eye(n)
        C=(rng.normal(size=(n,m))+1j*rng.normal(size=(n,m)))*.03
        D=(rng.normal(size=(m,n))+1j*rng.normal(size=(m,n)))*.07
        H=np.arange(m)+100.+1j*np.arange(m)*.31
        E=sparse.diags(np.exp(1j*np.arange(nt)*.027)).tocsr()
        P=sparse.block_diag((sparse.eye(30),E)).toarray()
        A=np.block([[P.conj().T@raw@P,C],[-D,np.diag(H)]])
        b=rng.normal(size=n+m)+1j*rng.normal(size=n+m)
        local=local_elimination(raw,np.arange(30));classes={'one':save_arrays(root/'class.npz',**local)}
        mapping=save_arrays(root/'map.npz',cells=np.array([0]),interior=np.arange(30)[None,:],class_keys=np.array(['one']),
            active=np.arange(nt),active_offsets=np.array([0,nt]),
            E_data=E.data,E_data_offsets=np.array([0,E.nnz]),E_indices=E.indices,E_indices_offsets=np.array([0,E.nnz]),
            E_indptr=E.indptr,E_indptr_offsets=np.array([0,len(E.indptr)]))
        C=sparse.csr_matrix(C);DT=sparse.csr_matrix(D.T);retained=np.arange(30,n+m)
        arrays=dict(retained=retained,full_rhs=b,H=H,C_data=C.data,C_indices=C.indices,C_indptr=C.indptr,
            DT_data=DT.data,DT_indices=DT.indices,DT_indptr=DT.indptr)
        members={k:_write_array(root,k,v) for k,v in arrays.items()}
        r=_seal(root,dict(identity={'fixture':'nonhermitian_nonzero40'},full_FE_rows=n,ports=m,cells=1,members=members,
                          classes=classes,maps=[mapping],bytes=0))
        S=A[30:,30:]-A[30:,:30]@np.linalg.solve(A[:30,:30],A[:30,30:])
        out=root/'S';out.mkdir();Sc=sparse.csr_matrix(S)
        mm={k:_write_array(out,k,v) for k,v in dict(data=Sc.data,indices=Sc.indices,indptr=Sc.indptr,retained=retained).items()}
        sr=_seal(out,dict(local_packet=r,members=mm,bytes=0))
        return r,sr,A,b,S

    def test_arbitrary_complex_loads_nonadjoint_ports_and_local_only_action(self):
        with tempfile.TemporaryDirectory() as td:
            r,sr,A,b,S=self.fixture(Path(td));local=LocalTracePacket(r)
            self.assertGreater(np.linalg.norm(A-A.conj().T),1)
            self.assertTrue(np.all(np.abs(b[-40:])>0));self.assertTrue(np.all(np.abs(b[:30])>0))
            rng=np.random.default_rng(7010);t=rng.normal(size=150)+1j*rng.normal(size=150)
            np.testing.assert_allclose(local.apply_trace(t),S@t,rtol=4e-13,atol=4e-12)
            red=local.condense_rhs(b);full=local.recover(t,b)
            np.testing.assert_allclose(b-A@full,local.lift_residual(red-S@t),rtol=1e-11,atol=3e-12)
            t=np.linalg.solve(S,red);full=local.recover(t,b)
            np.testing.assert_allclose(full,np.linalg.solve(A,b),rtol=8e-13,atol=8e-13)
            reopened=LocalTracePacket(r);a=.31-.19j
            np.testing.assert_allclose(reopened.apply_trace(a*t),a*(S@t),rtol=4e-13,atol=4e-12)
            self.assertEqual(local.calls['global_S_reads'],0);self.assertEqual(local.calls['global_K_reads'],0)
            attached=RetainedPacket(r,sr)
            np.testing.assert_allclose(attached.matrix@t,local.apply_trace(t),rtol=4e-13,atol=4e-12)
            attached.release_matrix();self.assertIsNone(attached.matrix)
            np.testing.assert_allclose(attached.recover(t,b),full,rtol=2e-13,atol=2e-13)

    def test_wrong_hash_half_write_live_identity_and_payload(self):
        with tempfile.TemporaryDirectory() as td:
            r,_,_,_,_=self.fixture(Path(td))
            with self.assertRaisesRegex(ValueError,'COMMIT'):LocalTracePacket(dict(r,sha256='bad'))
            with self.assertRaisesRegex(ValueError,'identity'):LocalTracePacket(r,identity={'different':True})
            (Path(td)/'H.npy').write_bytes(b'half write')
            with self.assertRaisesRegex(ValueError,'member file hash'):LocalTracePacket(r)

    def test_schema_budget_scope_and_no_full_K_branch(self):
        from src.solvers import assembly_tetra_scope as scope
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for p in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v70_*.dat')):
            s=load_tetra_reference(p,scope_module=scope);role=s.derived['stage']
            v=[256,320,384] if role in ('BUILD','SOLVE') else [64,80,96]
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],v)
            self.assertEqual(s.boundary['complete_modes'],828);self.assertEqual(s.solver['degree'],5)
            self.assertEqual(s.discretization['production_body_q'],13)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                env=preparation_memory_envelope('v70',role)
            self.assertEqual(env['planning_cap_bytes'],v[0]*2**30)
        self.assertIs(context('v70')[0],scope.window)
        self.assertEqual(storage_limits('v70')['task_storage_bytes'],600*2**30)
        # Inspect only this new opt-in branch's ordering; the real dat→kernel→
        # solve→recover→original-audit is covered by the formal V70 actor.
        source=(scope.ROOT/'src/solvers/independent_tetra_study.py').read_text()
        self.assertLess(source.index('retained_provider(s,folder,journal)'),source.index('core.production_body(s,journal)'))
        self.assertLess(source.index('assembly_time_global_factor_S_released_before_full_recovery'),source.index("with journal.measured('exact_original_all_internal_recovery')"))
        with tempfile.TemporaryDirectory() as td,patch.object(scope,'ARTIFACT',Path(td)),patch.object(scope.window,'TMP',Path(td)),patch.object(scope,'stage',return_value={'pass_gate':True}):
            d=Path(td)/'legal';d.mkdir();(d/'retained_audit_pending.json').write_text(json.dumps({'role':'SOLVE'}))
            with self.assertRaisesRegex(RuntimeError,'saved-only'):scope.require_stage('SOLVE')


if __name__=='__main__':unittest.main()
