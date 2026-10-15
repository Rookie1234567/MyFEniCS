"""Synthetic callback, closed-error and saved-only wiring; no PDE."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from src.solvers.tetra_coefficient_action import ReferenceVectorIntegral
from src.solvers.known_error_budget import partition_budget,term_budget
from src.solvers.actual_error_diagnostics import error_identity


class KnownErrorTests(unittest.TestCase):
    def test_complex_transformed_split_preserves_default(self):
        rng=np.random.default_rng(7901);phi=rng.normal(size=(11,7,3))+1j*rng.normal(size=(11,7,3))
        psi=rng.normal(size=phi.shape)+1j*rng.normal(size=phi.shape);w=rng.random(11)
        T=np.eye(7)+.1*(rng.normal(size=(7,7))+1j*rng.normal(size=(7,7)))
        c=rng.normal(size=(7,2))+1j*rng.normal(size=(7,2));J=np.array([[1.2,.3,-.1],[.2,.8,.4],[.1,-.2,-1.1]])
        k=np.array([.7,-.3,.2]);k0=2.3;eps=.91+.03j;mu=1.2+.01j
        kernel=ReferenceVectorIntegral(phi,psi,w);parts={}
        default=kernel.apply(c,J,T,k,k0,eps,mu)
        actual=kernel.apply(c,J,T,k,k0,eps,mu,diagnostic=parts.update)
        self.assertTrue(np.array_equal(default,actual))
        basis=np.einsum('ij,qjc->qic',T,phi)@np.linalg.inv(J)
        curl=np.einsum('ij,qjc->qic',T,psi)@J.T/np.linalg.det(J)+1j*np.cross(k,basis)
        U=np.einsum('qjc,jb->qcb',basis,c);W=np.einsum('qjc,jb->qcb',curl,c)
        vc=abs(np.linalg.det(J))*np.einsum('q,qjc,qcb->jb',w,curl.conj(),W/mu)
        vm=-abs(np.linalg.det(J))*k0**2*eps*np.einsum('q,qjc,qcb->jb',w,basis.conj(),U)
        for name,wanted in [('curl',vc),('mass',vm)]:
            self.assertLess(np.linalg.norm(parts[name]-wanted)/np.linalg.norm(wanted),2e-14)
        self.assertLess(np.linalg.norm(parts['curl']+parts['mass']-actual)/np.linalg.norm(actual),2e-14)

    def test_closed_error_nonmutual_ports_and_nonzero_reference_residual(self):
        rng=np.random.default_rng(7902);random=lambda shape:rng.normal(size=shape)+1j*rng.normal(size=shape)
        C=random((5,7));D=random((7,5));H=np.arange(7)+2+.2j;Kc=random((5,5));Km=random((5,5));K=Kc+Km
        full=np.block([[K,C],[-D,np.diag(H)]]);b=random((12,));xr=random((12,));xj=random((12,))
        rref=b-full@xr;rj=b-full@xj
        closed=lambda r:r[:5]-C@(r[5:]/H)
        A=K+C@(D/H[:,None]);br=closed(b)
        record=error_identity(lambda e:A@e,xr[:5],xj[:5],closed(rj),closed(rref),br-closed(rref),br-closed(rj))
        self.assertLess(record['closure_relative_to_operations'],1e-14)
        changed=xj.copy();changed[5:]+=random((7,))
        self.assertLess(np.linalg.norm(closed(b-full@changed)-closed(rj)),1e-12)
        e=xr[:5]-xj[:5];terms=term_budget(e,Kc@e,Km@e,C@((D@e)/H),A@e)
        self.assertLess(terms['closure_operation_scaled'],1e-14)
        zero=term_budget(e,e,-e,np.zeros_like(e),np.zeros_like(e))
        self.assertIsNone(zero['cancellation_ratio'])

    def test_fixed_owned_cell_partitions(self):
        per=np.arange(1,25,dtype=float).reshape(2,4,3)
        tags=np.array([0,1,2,0]);centers=np.c_[np.zeros((4,2)),[.1,.3,.6,.9]]
        result=partition_budget(per,tags,centers,np.array([.1,.2,.3,.4]),(0,1))
        self.assertEqual(result['height']['closure'],0.)
        self.assertEqual(sum(r['cells'] for r in result['materials']['rows']),4)
        with self.assertRaisesRegex(ValueError,'nonnegative'):partition_budget(-per,tags,centers,np.ones(4),(0,1))

    def test_one_batched_numerator_traversal_and_committed_block_reuse(self):
        from src.solvers import tetra_polynomial_difference as module
        calls=[]
        class Evaluator:
            def __init__(self,*args):
                self.geometry=[(np.eye(3),np.zeros(3),1.)]*2
                self.points=np.array([[.25,.25,.25]]);self.weights=np.array([1/6])
            def cell(self,f,c,k0):
                calls.append((f.value,c));v={k:np.full((1,3),f.value*j,dtype=complex) for j,k in enumerate(('E','H','curl'),1)}
                return None,None,v
        zero=SimpleNamespace(function_space=None,value=0);first=SimpleNamespace(function_space=None,value=1);second=SimpleNamespace(function_space=None,value=2)
        journal=SimpleNamespace(measured=lambda name:contextlib.nullcontext(),event=lambda *a,**k:None)
        with tempfile.TemporaryDirectory() as tmp,patch.object(module,'CachedTetraEvaluator',Evaluator),patch.object(module,'same_native_difference',side_effect=lambda x,y:y),patch.object(module,'parent_map',return_value=np.arange(2)):
            args=(zero,first,SimpleNamespace(k0=1),np.zeros(3),journal,Path(tmp),13)
            result=module.numerator(*args,parent_hashes=['fixture'],coefficient_first=True,additional_pairs=[(zero,second)])
            self.assertEqual(result[0].shape,(2,6));self.assertEqual(len(calls),4)
            self.assertTrue(np.allclose(result[0][0,3:],4*result[0][0,:3]))
            calls.clear();module.numerator(*args,parent_hashes=['fixture'],coefficient_first=True,additional_pairs=[(zero,second)])
            self.assertEqual(calls,[])

    def test_two_saved_only_inputs_and_namespace(self):
        from src.solvers import known_error_scope as scope
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,scoped_tetra_memory,storage_limits
        self.assertIs(context('v79')[0],scope.window)
        paths=sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v79_*.dat'))
        self.assertEqual(len(paths),2)
        for path in paths:
            spec=load_tetra_reference(path,scope_module=scope)
            self.assertEqual(spec.solver['kind'],'SAVED_ONLY');self.assertEqual(spec.solver['max_it'],0)
            self.assertEqual(scoped_tetra_memory('v79',spec.derived['stage'])['planning_gib'],64)
        self.assertEqual(storage_limits('v79')['new_storage_bytes'],2*2**30)


if __name__=='__main__':unittest.main()
