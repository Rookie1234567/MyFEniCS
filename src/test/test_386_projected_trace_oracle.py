"""One tiny complex MPC fixture; no mesh, PDE or physical S factor."""
import weakref
import numpy as np
import pytest
from src.solvers.physical_trace_entity import checked_lu
from src.solvers.physical_projected_trace import ProjectedPatchCross, projected_local_oracle, SetupCheckedTraceFactor


def test_nonhermitian_mpc_cross_blocks_and_factor_only(monkeypatch):
    phase=np.exp(.37j)
    fine=dict(dofmap=np.array([[0,1,2],[1,3,4]]),slaves=np.array([3]),
        offsets=np.array([0,0,0,0,1,1]),masters=np.array([0]),coefficients=np.array([phase]))
    coarse=dict(dofmap=np.array([[0,1],[1,2]]),slaves=np.array([2]),
        offsets=np.array([0,0,0,1]),masters=np.array([0]),coefficients=np.array([phase]))
    C4=np.eye(5,dtype=complex);C4[3]=0;C4[3,0]=phase;C4[:,3]=0
    C2=np.eye(3,dtype=complex);C2[2]=0;C2[2,0]=phase;C2[:,2]=0
    rng=np.random.default_rng(386);classes={};Araw=np.zeros((5,5),complex);Pglobal=np.zeros((5,3),complex)
    Pglobal[0,0]=Pglobal[1,1]=1
    for i in range(2):
        A=4*np.eye(3)+rng.normal(size=(3,3))+.4j*rng.normal(size=(3,3))
        P=np.vstack([np.eye(2),np.array([[.2+.1j,-.3]])]);Q=np.eye(3,dtype=complex)[:,2:]
        D=Q.conj().T@A@Q;W=P-Q@np.linalg.solve(D,Q.conj().T@A@P)
        classes[i]=dict(A=A,P=P,Q=Q,D=D,W=W,factor=checked_lu(D)[0])
        fr=fine['dofmap'][i];Araw[np.ix_(fr,fr)]+=A
        Pglobal[fr[-1]]=P[-1]@C2[coarse['dofmap'][i]]
    cg=np.array([.4+.3j,.7-.2j,0,0,0]);pg=np.array([.1-.2j,-.3+.4j,0,0,0]);h=2.3
    c2=Pglobal.conj().T@cg;p2=pg@Pglobal
    fport=dict(mode_key=[0,'fixed'],coupling_rows=np.array([0,1]),coupling_values=cg[:2],projection_rows=np.array([0,1]),projection_values=pg[:2],normalization_h=h)
    cport=dict(mode_key=[0,'fixed'],coupling_rows=np.array([0,1]),coupling_values=c2[:2],projection_rows=np.array([0,1]),projection_values=p2[:2],normalization_h=h)
    A=C4.conj().T@Araw@C4+np.outer(cg,pg)/h;Qglobal=np.eye(5,dtype=complex)[:,[2,4]]
    E=Qglobal@np.linalg.solve(Qglobal.conj().T@A@Qglobal,Qglobal.conj().T)
    J=np.zeros((5,9),complex);J[:2]=rng.normal(size=(2,9))+1j*rng.normal(size=(2,9))
    F=(np.eye(5)-E@A)@J;W=(np.eye(5)-E@A)@Pglobal
    R=W.conj().T@A@F;L=F.conj().T@A@W;S=W.conj().T@A@W
    assert np.linalg.norm(L-R.conj().T)>1e-2
    cross=ProjectedPatchCross(fine,coarse,[0,1],classes,[dict(rows=np.array([0,1]),J=J[:2])],[0],[fport],[cport])
    np.testing.assert_allclose(cross.right(0,8),R[:,:8],atol=2e-13)
    np.testing.assert_allclose(cross.right(8,9),R[:,8:9],atol=2e-13)
    X=rng.normal(size=(3,8))+1j*rng.normal(size=(3,8));X[2]=0;before=X.copy()
    np.testing.assert_allclose(cross.left(X),L@X,atol=2e-13);np.testing.assert_array_equal(X,before)
    with pytest.raises(ValueError):cross.right(0,9)
    with pytest.raises(ValueError):cross.left(np.zeros((3,9)))
    original=20*np.eye(9)+.1*(rng.normal(size=(9,9))+1j*rng.normal(size=(9,9)));saved=original.copy();records={};calls=[]
    def solve(rhs):
        calls.append(rhs.copy());value=np.zeros(3,complex);value[:2]=np.linalg.solve(S[:2,:2],rhs[:2])
        return value,dict(relative=float(np.linalg.norm(S@value-rhs)/np.linalg.norm(rhs)),refinement=0)
    effective,Rc,facts=projected_local_oracle(cross,original,solve,save=lambda name,row:records.update({name:row}))
    expected=original-L[:,:2]@np.linalg.solve(S[:2,:2],R[:2])
    np.testing.assert_allclose(effective,expected,atol=2e-12)
    np.testing.assert_allclose(Rc,R@(np.arange(1,10)+1j),atol=5e-13)
    np.testing.assert_array_equal(original,saved)
    assert len(calls)==9 and facts['blocks']==2 and records['block_008']['stop']==9
    assert records['block_000']['Q_column_gate']['per_column_relative'].shape==(8,)
    assert records['block_008']['Q_column_gate']['column']==8
    setup={};matrix=effective.copy();reference=weakref.ref(matrix)
    def save_setup(name,row):setup[name]={k:v for k,v in row.items() if not isinstance(v,np.ndarray)}
    factor=SetupCheckedTraceFactor(matrix,save=save_setup)
    rhs=np.arange(1,10)+1j;before=rhs.copy();kept=np.linalg.solve(matrix,rhs)
    np.testing.assert_allclose(factor.apply(rhs),kept,atol=2e-12);np.testing.assert_array_equal(rhs,before)
    assert not np.shares_memory(factor.factor[0],matrix)
    del matrix
    assert reference() is None and not hasattr(factor,'D')
    assert factor.setup_facts['runtime_original_D_residual']=='not_measured'
    assert setup['factor_only_same_action']['bitwise_equal']
    with pytest.raises(ValueError):factor.apply(np.full(9,np.nan))
    # A huge accurate first RHS must not hide an inaccurate small second RHS.
    import src.solvers.physical_projected_trace as implementation
    wide=J[:2].copy();wide[:,0]*=1e10;failures={}
    bad=ProjectedPatchCross(fine,coarse,[0,1],classes,[dict(rows=np.array([0,1]),J=wide)],[0],[fport],[cport],
        save=lambda name,row:failures.update({name:row}))
    original_solve=implementation.lu_solve
    def inaccurate(factor,rhs):
        value=original_solve(factor,rhs);value[:,1]+=1e-7;return value
    with monkeypatch.context() as patch:
        patch.setattr(implementation,'lu_solve',inaccurate)
        with pytest.raises(ValueError,match='per-column'):bad.right(0,8)
    failure=next(iter(failures.values()))
    assert failure['per_column_relative'][1]>1e-11
    assert np.linalg.norm(failure['applied']-failure['rhs'])/(np.linalg.norm(failure['applied'])+np.linalg.norm(failure['rhs']))<1e-11
