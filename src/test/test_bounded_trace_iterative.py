"""Targeted V71 algebra, counting, immutable scope and live solver policy."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import sparse

from src.test import test_tetra_assembly_packet as fixtures
from src.solvers.hot_tetra_trace import HotTracePacket
from src.solvers.bounded_trace_pc import coarse_galerkin, local_principal, prolong, restrict


class BoundedTraceTests(unittest.TestCase):
    def test_exact_hot_complex_nonadjoint_port_and_nonzero_internal_rhs(self):
        with tempfile.TemporaryDirectory() as td:
            r,_,A,b,S=fixtures.AssemblyPacketTests().fixture(Path(td))
            service=HotTracePacket(r,action_limit=4)
            rng=np.random.default_rng(7110);t=rng.normal(size=150)+1j*rng.normal(size=150)
            before=dict(service.calls)
            for scale in (1,.3+.7j):
                np.testing.assert_allclose(service.apply_trace(scale*t),scale*(S@t),rtol=1e-12,atol=3e-12)
            self.assertEqual(service.calls['local_lu_solve'],before['local_lu_solve'])
            self.assertEqual(service.calls['class_reads'],1)
            self.assertEqual(service.calls['map_hot_reads'],0)
            recovered=service.recover(t,b);red=service.condense_rhs(b)
            np.testing.assert_allclose(b-A@recovered,service.lift_residual(red-S@t),rtol=1e-11,atol=5e-12)
            self.assertEqual(service.actual_interior_port_cells,[0])
            self.assertTrue(service.last_identity['pass_gate'])
            operation=service.identity_operation_scale(t,recovered,b)
            self.assertGreater(operation,np.linalg.norm(b-A@recovered))
            service.apply_trace(t);service.apply_trace(t)
            with self.assertRaisesRegex(RuntimeError,'budget'):service.apply_trace(t)
            self.assertEqual(service.calls['global_K_reads'],0);self.assertEqual(service.calls['global_S_reads'],0)
            path=Path(r['path']);path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'file changed'):service.apply_trace(t)

    def test_local_galerkin_nonhermitian_complex_dual_nonzero40(self):
        with tempfile.TemporaryDirectory() as td:
            r,_,_,_,S=fixtures.AssemblyPacketTests().fixture(Path(td));a=HotTracePacket(r)
            rng=np.random.default_rng(7111);Z=sparse.csr_matrix(rng.normal(size=(110,4))+1j*rng.normal(size=(110,4)))
            l=np.r_[np.ones(110),np.exp(1j*np.arange(40)*.1)]
            r=np.r_[np.ones(110),1+np.arange(40)*.02j]
            A0=coarse_galerkin(a,Z,l,r);large=sparse.block_diag((Z,sparse.eye(40))).toarray()
            expected=large.conj().T@(l[:,None]*S*r[None,:])@large
            np.testing.assert_allclose(A0.toarray(),expected,rtol=3e-12,atol=3e-10)
            self.assertGreater(np.linalg.norm(expected-expected.conj().T),1)
            ids=np.r_[np.arange(20),np.arange(50,60)]
            local=local_principal(a,ids)
            np.testing.assert_allclose(local.toarray(),S[np.ix_(ids,ids)],rtol=1e-12,atol=3e-12)
            v=rng.normal(size=44)+1j*rng.normal(size=44);w=rng.normal(size=150)+1j*rng.normal(size=150)
            self.assertLess(abs(np.vdot(prolong(Z,v),w)-np.vdot(v,restrict(Z,w))),1e-10)

    def test_same_id_scatter_add_not_overwrite(self):
        # A real repeated global id in a local map must receive BOTH rows.
        from src.solvers.tetra_assembly_packet import _seal,_read_manifest
        from src.solvers.scattering_anchor import save_arrays
        with tempfile.TemporaryDirectory() as td:
            r,_,_,_,_=fixtures.AssemblyPacketTests().fixture(Path(td));root,m=_read_manifest(r)
            from src.solvers.scattering_anchor_checks import checked_arrays
            mp=checked_arrays(m['maps'][0]);mp['E_indices'][1]=mp['E_indices'][0]
            m['maps']=[save_arrays(root/'map_dup.npz',**mp)];r=_seal(root,m)
            a=HotTracePacket(r);c,_,ids,E,key=a.cell_records[0];S=a.cache[key]['schur']
            t=np.arange(150)+1j*np.arange(150)[::-1]
            body=np.zeros(150,complex);np.add.at(body,ids,E.conj().T@(S@(E@t[ids])))
            body[:110]+=a.Ctilde@t[110:];body[110:]=a.Dtilde@t[:110]+a.Htilde@t[110:]
            np.testing.assert_allclose(a.apply_trace(t),body,rtol=1e-12,atol=1e-10)

    def test_explicit_fgmres_policy_and_old_default_unchanged(self):
        from petsc4py import PETSc
        from src.solvers.physical_retained_fgmres import run_retained_fgmres
        rhs=PETSc.Vec().createSeq(4);rhs.array[:]=[1+1j,2,3j,4]
        A=np.array([[3,1j,0,1],[.2,4,1,0],[0,1j,5,.3],[1,0,1j,6]],complex)
        counts={'evaluate':0};logs=[]
        def action(v):
            out=v.duplicate();out.array[:]=A@v.array;return out
        def evaluate(t,res):
            counts['evaluate']+=1
            rho=float(np.linalg.norm(rhs.array-A@t.array)/np.linalg.norm(rhs.array))
            return dict(true=rho,native=rho,augmented=rho,port=rho,identity=0.)
        policy=dict(original_key='true',physical_limits=dict(true=1e-6,native=1e-6,augmented=1e-6,port=1e-6),identity_limits=dict(identity=1e-10))
        import time
        start=time.monotonic()
        result=run_retained_fgmres(rhs,action,lambda v:v.copy(),evaluate=evaluate,
            checkpoint=lambda *args:None,append=lambda name,row:logs.append((name,row)),seconds=lambda:time.monotonic()-start,
            restart=2,max_it=8,residual_interval=2,candidate_rtol=1e-11,retained_tolerance=1e-11,evaluation_policy=policy)
        self.assertEqual(result['max_it'],8);self.assertEqual(result['restart'],2)
        self.assertEqual(result['ksp_solve_count'],1);self.assertEqual(result['residual_interval'],2)
        self.assertNotIn('original_A6_relative',result['final_evaluation'])
        self.assertLessEqual(result['iterations'],8);result['final_solution'].destroy();rhs.destroy()
        import inspect
        self.assertEqual(inspect.signature(run_retained_fgmres).parameters['max_it'].default,2048)

    def test_current_scope_schema_guard_and_budget(self):
        from src.solvers import bounded_trace_scope as scope
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for p in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v71_*.dat')):
            s=load_tetra_reference(p,scope_module=scope);role=s.derived['stage']
            want=[96,112,128] if role in ('PC_SETUP','ITERATE') else [64,80,96]
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],want)
            self.assertEqual(s.boundary['complete_modes'],828)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                env=preparation_memory_envelope('v71',role)
            self.assertEqual(env['planning_cap_bytes'],want[0]*2**30)
        self.assertIs(context('v71')[0],scope.window)
        self.assertEqual(storage_limits('v71')['task_storage_bytes'],632*2**30)
        self.assertEqual(scope.plan_record()['action_limit'],600)


    def test_saved_symbolic_rejection_is_not_a_solve_pass(self):
        from benchmarks.collect_bounded_trace import symbolic_gate
        import copy
        def row(mb):
            return dict(info={'infog':{'1':0,'16':mb,'17':mb}},controls={'icntl':{'22':0}},
                        estimate_mb=mb,double_bytes=2*mb*1_000_000,numeric_calls=0,rows=10,nnz=100)
        result=symbolic_gate([row(20000),row(20000)],row(1))
        self.assertFalse(result['admitted']);self.assertGreater(result['excess_bytes'],0)
        self.assertTrue(symbolic_gate([row(100)],row(1))['admitted'])
        bad=copy.deepcopy(row(100));bad['double_bytes']=0
        with self.assertRaisesRegex(ValueError,'raw symbolic'):symbolic_gate([bad],row(1))
        with self.assertRaisesRegex(ValueError,'fixed total'):symbolic_gate([row(100)],row(1),limit_bytes=96*2**30)

    def test_fixed_PC_order_nonadjoint40_ports_unique_core(self):
        from src.solvers.bounded_trace_pc import BoundedTwoLevelPC
        rng=np.random.default_rng(7121)
        A=rng.normal(size=(44,44))+1j*rng.normal(size=(44,44))+50*np.eye(44)
        Z=sparse.csr_matrix(rng.normal(size=(4,2))+1j*rng.normal(size=(4,2)))
        J=sparse.block_diag((Z,sparse.eye(40))).toarray();E0=J.conj().T@A@J
        patches=[dict(ids=np.array([0,1,2]),core=np.array([0,1])),dict(ids=np.array([1,2,3]),core=np.array([2,3]))]
        class SmallFactor:
            def __init__(self,matrix):self.matrix=matrix
            def solve_repeated(self,rhs,out):out.array[:]=np.linalg.solve(self.matrix,rhs.array)
            def destroy(self):self.matrix=None
        pc=BoundedTwoLevelPC(Z,patches,[SmallFactor(A[np.ix_(p['ids'],p['ids'])]) for p in patches],SmallFactor(E0),lambda v:A@v)
        r=rng.normal(size=44)+1j*rng.normal(size=44)
        z0=J@np.linalg.solve(E0,J.conj().T@r);remaining=r-A@z0;expected=z0.copy()
        for p in patches:
            v=np.linalg.solve(A[np.ix_(p['ids'],p['ids'])],remaining[p['ids']])
            expected[p['core']]+=v[np.searchsorted(p['ids'],p['core'])]
        actual=pc(r);np.testing.assert_allclose(actual,expected,rtol=2e-12,atol=2e-12)
        alpha=.3+.7j;np.testing.assert_allclose(pc(alpha*r),alpha*actual,rtol=2e-12,atol=2e-12)
        self.assertEqual(pc.calls,dict(apply=2,local_triangular=4,coarse_triangular=2,internal_original_action=2))
        np.testing.assert_allclose(actual[4:],z0[4:],rtol=2e-12,atol=2e-12)
        pc.destroy()
    
    
    def test_saved_owner_inventory_rejects_duplicate_writeback(self):
        from benchmarks.collect_bounded_trace import owner_gate
        a={}
        for j in range(32):
            for k,v in dict(ids=np.arange(64,dtype=np.int64),core=np.array([2*j,2*j+1]),
                            core_cells=np.array([j]),halo_cells=np.array([j]),low=np.zeros(3),high=np.ones(3)).items():
                a[f'{j}_{k}']=v
        self.assertTrue(owner_gate(a,64,32)['all_trace_writeback_once'])
        a['31_core']=np.array([0,63])
        with self.assertRaisesRegex(ValueError,'writeback'):owner_gate(a,64,32)
    
    
    def test_saved_Galerkin_checker_complex_ports_and_tampering(self):
        from benchmarks.collect_bounded_trace import galerkin_gate,csr_inventory
        rng=np.random.default_rng(7120)
        Z=sparse.csr_matrix(rng.normal(size=(5,2))+1j*rng.normal(size=(5,2)))
        J=sparse.block_diag((Z,sparse.eye(2))).toarray()
        A=rng.normal(size=(7,7))+1j*rng.normal(size=(7,7));E0=J.conj().T@A@J
        w=rng.normal(size=4)+1j*rng.normal(size=4);v=J@w;original=A@v
        a=dict(w=w,Zw=v,original=original,pulled=J.conj().T@original,coarse_action=E0@w)
        self.assertTrue(galerkin_gate(Z,E0,a)['pass_gate'])
        a['pulled']=a['pulled'].copy();a['pulled'][-1]+=1
        self.assertFalse(galerkin_gate(Z,E0,a)['pass_gate'])
        record=dict(data=np.array([1,0],dtype=np.complex128),indices=np.array([0,1],dtype=np.int64),
                    indptr=np.array([0,2],dtype=np.int64),shape=np.array([1,2],dtype=np.int64))
        self.assertEqual(csr_inventory(record)['stored_entries'],2)
        self.assertEqual(csr_inventory(record)['exact_nonzero'],1)
        record['data'][0]=np.nan
        with self.assertRaisesRegex(ValueError,'CSR inventory'):csr_inventory(record)


if __name__=='__main__':unittest.main()
