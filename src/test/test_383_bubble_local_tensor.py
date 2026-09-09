"""One small non-Hermitian fixture; no FFCx or real cell measurement."""
import numpy as np
from src.solvers.physical_bubble_local import harmonic_bubble_check
from src.runners.physical_recursive_entry import build_parser,selected_contract


def test_nonhermitian_bubble_schur_requires_distinct_left_coupling():
    rng=np.random.default_rng(383)
    A=6*np.eye(5)+rng.normal(size=(5,5))+1j*rng.normal(size=(5,5))
    P=np.eye(5,dtype=complex)[:,:2];R=P.conj().T;packets={}
    result=harmonic_bubble_check(A,P,R,[1,2,3,4],retained_bubble_rank=1,
        save=lambda n,v:packets.update({n:v}))
    W,Q,D=result['W'],result['Q'],result['D']
    expected=A[:2,:2]-A[:2,2:]@np.linalg.solve(A[2:,2:],A[2:,:2])
    np.testing.assert_allclose(result['S'],expected,atol=1e-12)
    np.testing.assert_allclose(R@W,np.eye(2),atol=1e-12)
    np.testing.assert_allclose(Q.conj().T@A@W,0,atol=1e-12)
    B=Q.conj().T@A@P
    wrong=P.conj().T@A@P-B.conj().T@np.linalg.solve(D,B)
    assert np.linalg.norm(result['S']-wrong)>1e-2
    assert result['facts']['basis']['nullity']==3
    assert set(('A','P','R','Q','D','T','W','S'))<=packets['bubble_harmonic'].keys()
    args=build_parser().parse_args(['--input','x','--inventory','y','--budget','b','--output','o',
                                  '--source-sha','s','--bubble-local-tensor'])
    assert selected_contract(args)['workflow_seconds']==300
    assert selected_contract(args)['p4_global_matrix']==selected_contract(args)['I4_calls']==0
