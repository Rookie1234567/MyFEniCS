"""Independent transformed-basis algebra and sealed CSR failure fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scipy import sparse
from src.solvers.tetra_coefficient_action import ReferenceVectorIntegral,CoefficientFullAction
from src.solvers.tetra_body_checkpoint import save_checkpoint,load_checkpoint,qualification_receipt


def transformed_basis(values,curls,weights,c,J,T,k,k0,eps,mu):
    det=np.linalg.det(J)
    b=np.einsum('ij,qjc->qic',T,values)@np.linalg.inv(J)
    ck=np.einsum('ij,qjc->qic',T,curls)@J.T/det+1j*np.cross(k,b)
    U=np.einsum('qjc,jb->qcb',b,c)
    W=np.einsum('qjc,jb->qcb',ck,c)
    return abs(det)*(np.einsum('q,qjc,qcb->jb',weights,ck.conj(),W/mu)
        -k0**2*eps*np.einsum('q,qjc,qcb->jb',weights,b.conj(),U))


class CoefficientTests(unittest.TestCase):
    def test_complex_orientation_loss_nonorthogonal_and_negative_det(self):
        r=np.random.default_rng(6501);phi=r.normal(size=(13,9,3))+1j*r.normal(size=(13,9,3))
        psi=r.normal(size=phi.shape)+1j*r.normal(size=phi.shape);w=r.random(13)
        kernel=ReferenceVectorIntegral(phi,psi,w);c=r.normal(size=(9,2))+1j*r.normal(size=(9,2))
        J=np.array([[1.2,.3,-.2],[.1,.8,.4],[.2,-.1,1.5]])
        for complex_T in (False,True):
            T=np.eye(9)+.1*r.normal(size=(9,9))
            if complex_T:T=T+.15j*r.normal(size=(9,9))
            for sign in (1,-1):
                actualJ=J.copy();actualJ[:,0]*=sign
                wanted=transformed_basis(phi,psi,w,c,actualJ,T,[.7,-.2,.4],2.3,.8+.03j,1.4+.02j)
                actual=kernel.apply(c,actualJ,T,np.array([.7,-.2,.4]),2.3,.8+.03j,1.4+.02j)
                self.assertLess(np.linalg.norm(actual-wanted)/np.linalg.norm(wanted),2e-14)
                self.assertLess(np.linalg.norm(kernel.apply(c[:,0],actualJ,T,np.array([.7,-.2,.4]),2.3,.8+.03j,1.4+.02j)-wanted[:,0])/np.linalg.norm(wanted[:,0]),2e-14)
                if complex_T:
                    wrong=kernel.apply(c,actualJ,T.conj(),np.array([.7,-.2,.4]),2.3,.8+.03j,1.4+.02j)
                    self.assertGreater(np.linalg.norm(wrong-wanted)/np.linalg.norm(wanted),.01)

    def test_shared_complex_MPC_and_40_nonmutual_ports(self):
        r=np.random.default_rng(6502);P=sparse.csr_matrix([[1,0,0],[0,1,0],[0,0,1],[np.exp(.6j),0,0],[0,1j,.2]])
        K=r.normal(size=(5,5))+1j*r.normal(size=(5,5));C=r.normal(size=(3,40))+1j*r.normal(size=(3,40))
        D=r.normal(size=(40,3))+1j*r.normal(size=(40,3));H=np.arange(40)+3.+.2j
        A=sparse.bmat([[P.conj().T@K@P,C],[-D,sparse.diags(H)]]).toarray()
        action=CoefficientFullAction.__new__(CoefficientFullAction)
        action.n=3;action.C=sparse.csr_matrix(C);action.D=sparse.csr_matrix(D);action.H=H
        action.body=lambda x:P.conj().T@(K@(P@x))
        x=r.normal(size=(43,2))+1j*r.normal(size=(43,2))
        self.assertLess(np.linalg.norm(action(x)-A@x),1e-12)
        self.assertGreater(np.linalg.norm((P.T@K@P)-(P.conj().T@K@P)),.1)
        self.assertGreater(np.linalg.norm(D-C.conj().T),1.)

    def test_atomic_checkpoint_reopen_hash_identity_and_half_write(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);K=sparse.csr_matrix([[2+1j,.3j],[4,5-2j]])
            identity=dict(p=6,kappa=[1.,2.,0.],q=15)
            receipt=save_checkpoint(d/'body',K,identity,dict(masters=np.array([1,2])),form={'q':15},source={'sha':'fixture'},boundary={'q63':'fixture'})
            a,m,v=load_checkpoint(receipt,identity)
            self.assertLess(np.linalg.norm(a.toarray()-K.toarray()),1e-15)
            self.assertEqual(m['status'],'ASSEMBLED_NOT_YET_ORACLE_VERIFIED')
            self.assertFalse(v['data'].flags.writeable)
            q=qualification_receipt(receipt,[1e-13,2e-13],{},'fixture',d/'qualified.json')
            self.assertEqual(json.loads(Path(q['path']).read_text())['status'],'ORIGINAL_ACTION_VERIFIED')
            with self.assertRaisesRegex(ValueError,'mathematical identity'):load_checkpoint(receipt,dict(identity,p=5))
            with self.assertRaises(FileExistsError):save_checkpoint(d/'body',K,identity,{},form={},source={},boundary={})
            raw=(d/'body/data.npy').read_bytes();(d/'body/data.npy').write_bytes(raw[:-4])
            with self.assertRaisesRegex(ValueError,'file hash'):load_checkpoint(receipt,identity)
            (d/'half.partial').mkdir();(d/'half.partial/manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'uncommitted'):load_checkpoint({'path':str(d/'half.partial/manifest.json'),'sha256':'bad'},identity)


if __name__=='__main__':unittest.main()
