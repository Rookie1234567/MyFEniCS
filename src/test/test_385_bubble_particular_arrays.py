"""One small complex shared-row/MPC fixture, without mesh or FE construction."""
import numpy as np
import pytest
from src.solvers.physical_bubble_particular import expand_primal,resolve_primal,cached_interior_action,gram_report,coefficient_defects
from src.runners.physical_recursive_entry import build_parser,selected_contract


def test_shared_complex_mpc_interior_action_and_cross_term_gram():
    rng=np.random.default_rng(385);phase=np.exp(.61j)
    mapping=dict(dofmap=np.array([[0,1,2,3],[1,4,5,6]]),slaves=np.array([4]),masters=np.array([0]),
        coefficients=np.array([phase]),offsets=np.array([0,0,0,0,0,1,1,1]))
    C=np.eye(7,dtype=complex);C[4,:]=0;C[4,0]=phase
    error=rng.normal(size=7)+1j*rng.normal(size=7);error[4]=0
    expanded=expand_primal(error,mapping);np.testing.assert_allclose(expanded,C@error)
    classes={};ws=[];qs=[];raw=np.zeros((7,7),complex);metric=np.zeros((7,7),complex)
    P=np.eye(4,dtype=complex)[:,:2];R=P.conj().T;Q=np.eye(4,dtype=complex)[:,3:]
    for i,rows in enumerate(mapping['dofmap']):
        A=8*np.eye(4)+rng.normal(size=(4,4))+1j*rng.normal(size=(4,4))
        W=P-Q@np.linalg.solve(Q.conj().T@A@Q,Q.conj().T@A@P)
        v=expanded[rows];w=W@(R@v);q=Q@(Q.conj().T@(v-w));ws.append(w);qs.append(q)
        defects=coefficient_defects(v,w,q,v-w-q,R,Q,np.array([0,1,2]))
        assert max(defects.values())<1e-11
        wrong=q.copy();wrong[0]+=1
        assert coefficient_defects(v,w,wrong,v-w-wrong,R,Q,np.array([0,1,2]))['Rq']>1e-3
        classes[i]=dict(A=A,boundary=np.array([0,1,2]));raw[np.ix_(rows,rows)]+=A
        X=rng.normal(size=(4,4))+1j*rng.normal(size=(4,4));metric[np.ix_(rows,rows)]+=X.conj().T@X
    w,wfacts=resolve_primal(ws,mapping['dofmap'],mapping);q,qfacts=resolve_primal(qs,mapping['dofmap'],mapping);t=error-w-q
    assert max(*wfacts.values(),*qfacts.values())<1e-12
    values=np.column_stack([expand_primal(x,mapping) for x in (w,q,t)])
    gram=values.conj().T@metric@values;report=gram_report(gram)
    expected=np.vdot(expanded,metric@expanded).real
    np.testing.assert_allclose(report['diagonal'].sum()+sum(report['cross_2real'].values()),expected,atol=1e-11)
    assert max(abs(v) for v in report['cross_2real'].values())>1e-3
    nonfinite=gram.copy();nonfinite[0,0]=np.nan
    with pytest.raises(ValueError,match='nonfinite'):gram_report(nonfinite)
    response=np.zeros(7,complex);response[[3,6]]=[1+.2j,-.3+1j]
    result=cached_interior_action(response,mapping,[0,1],classes)
    np.testing.assert_allclose(result,C.conj().T@raw@C@response,atol=1e-12)
    assert result[4]==0
    bad=response.copy();bad[1]=1
    with pytest.raises(ValueError,match='zero trace'):cached_interior_action(bad,mapping,[0,1],classes)
    changed=[v.copy() for v in ws];changed[1][0]+=1
    _,facts=resolve_primal(changed,mapping['dofmap'],mapping);assert facts['shared_relative']>1e-3
    args=build_parser().parse_args(['--input','i','--inventory','j','--output','o','--budget','b','--source-sha','s','--bubble-particular-diagnostic'])
    c=selected_contract(args);assert c['cached_A4']==2 and c['local_rhs']==504 and c['functionspace']==c['I4']==0
