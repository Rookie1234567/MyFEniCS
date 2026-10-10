"""New exact block/recovery algebra and live V69 one-run wiring only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import sparse

from src.solvers.exact_tetra_condensation import build_checkpoint,ExactRecovery,check_internal_graph,port_schur_preallocation
from src.solvers import exact_tetra_scope as scope


class ExactTetraTests(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(6901);n=13
        A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n));A+=20*np.eye(n)
        # Two local interiors; retained FE and three ports are all coupled.
        A[:2,2:4]=0;A[2:4,:2]=0
        rhs=rng.normal(size=n)+1j*rng.normal(size=n)
        return sparse.csr_matrix(A),rhs,(np.arange(2),np.arange(2,4))

    def test_nonhermitian_full_nonzero_loads_and_disk_service(self):
        A,b,cells=self.fixture()
        self.assertGreater(np.linalg.norm(A.toarray()-A.toarray().conj().T),1.)
        self.assertTrue(np.all(np.abs(b[-3:])>0))
        with tempfile.TemporaryDirectory() as td:
            extra=np.zeros(A.shape[0],np.int64);extra[-3:]=A.shape[0]
            r=build_checkpoint(A,b,cells,Path(td)/'sealed',identity={'case':'complex_nonzero_fi_g'},source={'source_sha':'fixture'},preallocation_extra=extra)
            first=ExactRecovery(r);g=first.condense_rhs(b);S=first.matrix.toarray()
            self.assertEqual(first.manifest['build_audit']['reserved_extra_entries'],int(extra.sum()))
            expected=np.linalg.solve(A.toarray(),b);trace=np.linalg.solve(S,g)
            full=first.recover(trace,b)
            np.testing.assert_allclose(full,expected,rtol=2e-13,atol=2e-13)
            np.testing.assert_allclose(first.arrays['rhs'],g,rtol=2e-13,atol=2e-13)
            second=ExactRecovery(r);b2=b*(.17+.43j)
            actual=second.recover(np.linalg.solve(S,second.condense_rhs(b2)),b2)
            np.testing.assert_allclose(actual,expected*(.17+.43j),rtol=2e-13,atol=2e-13)
            v=np.sin(np.arange(len(trace)))+1j*np.cos(np.arange(len(trace)))
            x=second.recover(v,b2)
            np.testing.assert_allclose(b2-A@x,second.lift_residual(second.condense_rhs(b2)-second.apply_trace(v)),rtol=2e-13,atol=2e-13)
            self.assertEqual(second.manifest['local_LU_count'],2)

    def test_wrong_hash_half_write_and_different_identity_rejected(self):
        A,b,cells=self.fixture()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'sealed';r=build_checkpoint(A,b,cells,root,identity={'id':1},source={})
            with self.assertRaisesRegex(ValueError,'COMMIT'):ExactRecovery(dict(r,sha256='wrong'))
            with self.assertRaisesRegex(ValueError,'identity'):ExactRecovery(r,identity={'id':2})
            (root/'COMMIT').write_text('half-write')
            with self.assertRaisesRegex(ValueError,'COMMIT'):ExactRecovery(r)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'uncommitted.partial';root.mkdir();(root/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'COMMIT'):ExactRecovery({'path':str(root/'manifest.json'),'sha256':'x'})

    def test_intercell_internal_coupling_is_not_silently_removed(self):
        A,b,cells=self.fixture();A[0,2]=1e-200
        with self.assertRaisesRegex(ValueError,'crosses'):check_internal_graph(A,cells)

    def test_capacity_uses_both_actual_port_sides_without_value_drop(self):
        from types import SimpleNamespace
        # Cell closures share retained row 4; only C_i touches cell 0, only
        # D_i touches cell 1. An arbitrarily small nonzero is still included.
        setup=dict(P=sparse.eye(7,format='csr'),V=SimpleNamespace(dofmap=SimpleNamespace(
            cell_dofs=lambda c:np.array([[0,1,4,5],[2,3,4,6]])[c])))
        C=sparse.csr_matrix(([1e-200],([0],[0])),shape=(7,2))
        D=sparse.csr_matrix(([1j],([1],[2])),shape=(2,7))
        extra,detail=port_schur_preallocation(setup,C,D,(np.arange(2),np.arange(2,4)))
        np.testing.assert_array_equal(extra,[0,0,0,0,2,2,2,5,5])
        self.assertEqual(detail['connected_cells'],2)
        self.assertEqual(detail['retained_FE_support'],3)
        self.assertTrue(detail['no_entries_inserted_or_dropped'])

    def test_live_schema_memory_row_scope_and_parent_no_closed_guard(self):
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for path in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v69_*.dat')):
            spec=load_tetra_reference(path,scope_module=scope);role=spec.derived['stage']
            expected=[256,320,384] if role in ('PREPARE_C5','C5','M5') else [64,80,96]
            self.assertEqual([spec.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],expected)
            self.assertEqual(spec.solver['degree'],5)
            self.assertEqual(spec.boundary['complete_modes'],1188 if role=='M5' else 828)
            self.assertEqual(spec.discretization['production_body_q'],13);self.assertEqual(spec.discretization['oracle_body_q'],15)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                envelope=preparation_memory_envelope('v69',role)
            self.assertEqual(envelope['planning_cap_bytes'],expected[0]*2**30)
        self.assertIs(context('v69')[0],scope.window)
        self.assertEqual(storage_limits('v69')['task_storage_bytes'],560*2**30)
        from src.solvers.durable_l5_study import qualification
        with patch('src.solvers.local_p_mode_scope.require_stage',side_effect=AssertionError('old closed gate')):
            qualified,p=qualification();self.assertEqual(len(qualified['errors']),2)

    def test_strict_checker_and_returns_prevent_numeric_replay(self):
        from benchmarks.collect_exact_tetra import strict_reproduction
        p=dict(fields={'E':{'relative':5e-7}},selected={'E':7e-7},
            modes={'outgoing_amplitude_at_boundary_relative':2e-7,'mode_power_max_absolute':2e-10},
            power_differences={'R':2e-9},energies=[1e-7],quadrature_operation_scaled=1e-12)
        self.assertTrue(strict_reproduction(p)['pass_gate']);p['fields']['E']['relative']=2e-6
        self.assertFalse(strict_reproduction(p)['pass_gate'])
        with tempfile.TemporaryDirectory() as td,patch.object(scope,'ARTIFACT',Path(td)),patch.object(scope.window,'TMP',Path(td)),patch.object(scope,'stage',return_value={'pass_gate':True}),patch.object(scope,'numeric_attempts',return_value=0):
            d=Path(td)/'returned';d.mkdir();(d/'returned_audit_pending.json').write_text(json.dumps({'role':'C5'}))
            with self.assertRaisesRegex(RuntimeError,'saved consumer'):scope.require_stage('C5')

    def test_final_consumers_inherit_their_case_quota_without_reset(self):
        runs=[dict(role='PREPARE_C5',folder='absent_prepare',elapsed_seconds=31),
              dict(role='VERIFY_COST',case_group='C5',folder='absent_C5',elapsed_seconds=13),
              dict(role='VERIFY_COST',case_group='M5',folder='absent_M5',elapsed_seconds=17)]
        with tempfile.TemporaryDirectory() as td,patch.object(scope.window,'TMP',Path(td)),patch.object(scope.window,'ledger',return_value=dict(runs=runs,active=None)):
            self.assertEqual(scope.window.case_remaining('C5'),25200-44)
            self.assertEqual(scope.window.case_remaining('M5'),14400-17)


if __name__=='__main__':unittest.main()
