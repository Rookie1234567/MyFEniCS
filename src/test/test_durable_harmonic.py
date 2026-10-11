"""V75 cache/coverage/batch/namespace tests; no scientific PDE."""
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from scipy import sparse

from src.solvers.durable_galerkin import durable_base,local_products,contributions_csr
from src.solvers.durable_harmonic_scope import DurableHarmonicWindow,numeric_time_admission
from src.solvers.durable_harmonic_study import formula_fingerprints
from src.solvers.bounded_trace_study import action_charge


class DummyJournal:
    source_state={'source_sha':'synthetic'}
    def event(self,*args,**kwargs):pass
    @contextlib.contextmanager
    def measured(self,*args):yield


class DurableHarmonicTests(unittest.TestCase):
    def service(self):
        rng=np.random.default_rng(7501)
        cache={};records=[]
        for j in range(5):
            key=str(j);S=rng.normal(size=(3,3))+1j*rng.normal(size=(3,3))
            cache[key]={'schur':S}
            E=sparse.csr_matrix(rng.normal(size=(3,2))+1j*rng.normal(size=(3,2)))
            records.append((j,None,np.array([j,j+1]),E,key))
        C=sparse.csr_matrix((np.arange(6)+1j)[:,None])
        D=sparse.csr_matrix((.3*np.arange(6)+.7j)[None,:])
        return SimpleNamespace(nt=6,m=1,manifest={'cells':5},cell_records=records,cache=cache,Ctilde=C,Dtilde=D,Htilde=np.array([[2-.4j]]))

    def test_different_column_and_kernel_batch_complex(self):
        rng=np.random.default_rng(7502);packed=[]
        for j in range(7):
            d=rng.normal(size=(3,2))+1j*rng.normal(size=(3,2));S=rng.normal(size=(3,3))+1j*rng.normal(size=(3,3))
            packed.append((j,np.array([j,j+2]),d,S))
        a=contributions_csr(local_products(packed),10)
        b=contributions_csr(local_products(packed,batched=True),10)
        np.testing.assert_allclose(a.toarray(),b.toarray(),rtol=1e-13,atol=1e-13)
        self.assertGreater(np.linalg.norm(a.toarray()-a.toarray().conj().T),1.)

    def test_committed_prefix_resumes_only_missing_and_ports_once(self):
        service=self.service();Z=sparse.csr_matrix(np.arange(18).reshape(6,3)*(1+.1j));journal=DummyJournal()
        identity={'operator':'synthetic_exact_nonhermitian'};calls=[]
        def live():
            calls.append(1)
            if len(calls)==2:raise RuntimeError('synthetic interruption after committed block')
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(RuntimeError,'synthetic interruption'):
                durable_base(service,Z,np.r_[np.ones(6),2],np.r_[np.ones(6),.3j],t,journal,identity=identity,require_live=live,block_cells=2)
            first=Path(t)/'block0000.npz';old=first.read_bytes()
            A,m=durable_base(service,Z,np.r_[np.ones(6),2],np.r_[np.ones(6),.3j],t,journal,identity=identity,require_live=lambda:None,block_cells=2)
            self.assertEqual(first.read_bytes(),old);self.assertEqual((m['new_blocks'],m['reused_blocks'],m['port_aggregations']),(2,1,1))
            expected=np.zeros((4,4),complex)
            for _,_,ids,E,key in service.cell_records:
                d=E@Z[ids].toarray();expected[:3,:3]+=d.conj().T@service.cache[key]['schur']@d
            expected[:3,3]=(Z.conj().T@service.Ctilde).toarray().ravel()*.3j
            expected[3,:3]=2*(service.Dtilde@Z).toarray().ravel()
            expected[3,3]=2*service.Htilde[0,0]*.3j
            np.testing.assert_allclose(A.toarray(),expected,rtol=1e-13,atol=1e-10)
            with patch('src.solvers.durable_galerkin.packed_cell',side_effect=AssertionError('completed base must not recalculate cells')):
                B,n=durable_base(service,Z,np.r_[np.ones(6),2],np.r_[np.ones(6),.3j],t,journal,identity=identity,require_live=lambda:None)
            np.testing.assert_array_equal(A.toarray(),B.toarray());self.assertEqual(n['cell_ids'],list(range(5)))

    def test_partial_does_not_count_as_commit_and_inventory_rejected(self):
        service=self.service();Z=sparse.csr_matrix(np.eye(6,3))
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'block0000.partial.npz').write_bytes(b'not a commit')
            A,m=durable_base(service,Z,np.ones(7),np.ones(7),t,DummyJournal(),identity={},require_live=lambda:None,block_cells=2)
            self.assertEqual(m['new_blocks'],3);self.assertTrue(np.isfinite(A.data).all())
            bad=json.loads((Path(t)/'manifest.json').read_text());bad['cell_ids']=[0]
            (Path(t)/'manifest.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'coverage'):
                durable_base(service,Z,np.ones(7),np.ones(7),t,DummyJournal(),identity={},require_live=lambda:None)

    def test_zero_support_still_covers_every_cell(self):
        service=self.service();Z=sparse.csr_matrix((6,3),dtype=complex)
        with tempfile.TemporaryDirectory() as t:
            _,m=durable_base(service,Z,np.ones(7),np.ones(7),t,DummyJournal(),identity={},require_live=lambda:None,block_cells=2)
            zero=[]
            for r in m['blocks']:zero.extend(json.loads(Path(r['path']).read_text())['zero_cells'])
            self.assertEqual(zero,list(range(5)))

    def test_single_clock_no_H_or_I_fallback(self):
        w=SimpleNamespace(snapshot=lambda:dict(heavy_remaining_seconds=21000),total=39600,charged_wall=lambda:1200)
        for role in ('PREFLIGHT','HARMONIC_PREPARE','HARMONIC','VERIFY_COST'):
            self.assertEqual(DurableHarmonicWindow.case_remaining(w,role),21000)
            self.assertEqual(DurableHarmonicWindow.available_at_boundary(w,role),20820)

    def test_actual_namespace_context_storage_and_input(self):
        from src.solvers import durable_harmonic_scope as scope
        from src.runners.port_preparation import context,storage_limits,scoped_tetra_memory,live_workflow_seconds
        from src.io.independent_tetra_reference import load_tetra_reference
        self.assertIs(context('v75')[0],scope.window)
        self.assertEqual(context('v75')[1],scope.ARTIFACT)
        self.assertEqual(storage_limits('v75')['task_storage_bytes'],696*2**30)
        self.assertEqual(scoped_tetra_memory('v75','HARMONIC')['sampled_stop_gib'],128)
        self.assertEqual(scoped_tetra_memory('v75','VERIFY_COST')['sampled_stop_gib'],96)
        for p in (scope.ROOT/'input/task042_neural_coarse_inverse').glob('v75_*.dat'):
            spec=load_tetra_reference(p,scope_module=scope)
            self.assertEqual(spec.derived['preparation_scope'],'v75')
            self.assertEqual(spec.execution['timeout_seconds'],39600)
        self.assertEqual(live_workflow_seconds('v75','HARMONIC_PREPARE',SimpleNamespace(remaining=lambda role:42),100),42)

    def test_full_numeric_KSP_output_reserve(self):
        self.assertFalse(numeric_time_admission(18899,3600)['admitted'])
        self.assertTrue(numeric_time_admission(18900,3600)['admitted'])
        self.assertEqual(numeric_time_admission(18900,3600)['KSP_upper_seconds'],10800)

    def test_800_and_qualification12_at_all_layers(self):
        with tempfile.TemporaryDirectory() as t:
            scope=SimpleNamespace(NAMESPACE='v75',window=SimpleNamespace(TMP=Path(t)),plan_record=lambda:dict(action_limit=800))
            for _ in range(12):action_charge('Q_test',lambda:3,scope=scope)
            with self.assertRaisesRegex(RuntimeError,'qualification'):action_charge('Q_test',lambda:3,scope=scope)
            for _ in range(788):action_charge('I_test',lambda:3,scope=scope)
            with self.assertRaisesRegex(RuntimeError,'upper cap'):action_charge('I_test',lambda:3,scope=scope)

    def test_formula_compatibility_ignores_cache_only_change(self):
        old='def macro_blocks(a):\n return a.conj().T\n\ndef logging():\n return 0\n'
        cache=old.replace('return 0','return 1')
        self.assertEqual(formula_fingerprints(old),formula_fingerprints(cache))
        wrong=old.replace('a.conj().T','a.T')
        self.assertNotEqual(formula_fingerprints(old),formula_fingerprints(wrong))


if __name__=='__main__':unittest.main()
