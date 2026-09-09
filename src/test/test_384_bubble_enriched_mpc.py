"""One complex local/MPC fixture; real global owner qualification is a formal gate."""
import numpy as np
from src.solvers.physical_bubble_local import harmonic_bubble_check
from src.solvers.physical_bubble_global import constrained_cell_correction
from src.runners.physical_recursive_entry import build_parser,selected_contract


def test_complex_bubble_mpc_adjoint_and_existing_graph_insertion():
    rng=np.random.default_rng(384)
    A=8*np.eye(5)+rng.normal(size=(5,5))+1j*rng.normal(size=(5,5))
    P=np.eye(5,dtype=complex)[:,:3];R=P.conj().T
    h=harmonic_bubble_check(A,P,R,[2,3,4],retained_bubble_rank=1,save=lambda *_:None)
    W=h['W'];phase=np.exp(.73j)
    # Third coarse row has two links, one repeated target. Test summation and
    # complex conjugation independently of the helper's compressed expansion.
    targets=np.array([[0,-1,-1],[1,-1,-1],[0,1,0]])
    coeff=np.array([[1,0,0],[1,0,0],[phase,.2j,.3*phase]],complex)
    E=np.array([[1,0],[0,1],[1.3*phase,.2j]])
    rows,delta=constrained_cell_correction(h['S']-P.conj().T@A@P,targets,coeff)
    np.testing.assert_array_equal(rows,[0,1])
    globalW=W@E;globalP=P@E
    assembled=globalP.conj().T@A@globalP+delta
    np.testing.assert_allclose(assembled,globalW.conj().T@A@globalW,atol=1e-12)
    q=rng.normal(size=2)+1j*rng.normal(size=2);z=rng.normal(size=5)+1j*rng.normal(size=5)
    np.testing.assert_allclose(np.vdot(globalW@q,z),np.vdot(q,E.conj().T@(W.conj().T@z)),atol=1e-12)
    np.testing.assert_allclose(R@W,np.eye(3),atol=1e-12)
    assert np.linalg.norm(delta)>1e-2
    args=build_parser().parse_args(['--input','x','--inventory','b','--budget','c','--output','o','--source-sha','s','--bubble-enriched-component'])
    contract=selected_contract(args)
    assert contract['workflow_seconds']==900 and contract['I4_calls']==1 and contract['outer_calls']==0
    assert contract['bottom']['unified_bytes_cap']==512*1024**2
