"""One small complex shared-row/MPC fixture, without mesh or FE construction."""
import numpy as np
import pytest
from src.solvers.physical_bubble_particular import expand_primal,resolve_primal,cached_interior_action,gram_report,coefficient_defects
from src.runners.physical_recursive_entry import build_parser,selected_contract
from src.solvers.physical_bubble_amplification import combine_full_pq,saved_cell_action


def test_shared_complex_mpc_interior_action_and_cross_term_gram(tmp_path):
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
    # Same shared/MPC fixture, now arbitrary trace input and non-Hermitian PQ.
    full_action=C.conj().T@raw@C
    saved={k:dict(S=v['A']) for k,v in classes.items()}
    np.testing.assert_allclose(saved_cell_action(error,mapping,[0,1],saved),full_action@error,atol=1e-12)
    p=np.eye(7,dtype=complex)[:,:2];qglobal=np.eye(7,dtype=complex)[:,[3,6]]
    E=qglobal@np.linalg.solve(qglobal.conj().T@full_action@qglobal,qglobal.conj().T)
    W=(np.eye(7)-E@full_action)@p
    S=W.conj().T@full_action@W
    CW=W@np.linalg.solve(S,W.conj().T)
    rhs=error;Eg=E@rhs;Cg=CW@rhs;delta=CW@full_action@Eg
    correct=combine_full_pq(Eg,Cg,delta)
    VH=p.conj().T@(np.eye(7)-full_action@E)
    np.testing.assert_allclose(correct,Eg+W@np.linalg.solve(S,VH@rhs),atol=1e-12)
    assert np.linalg.norm(correct-(Eg+Cg))>1e-3
    assert np.linalg.norm(VH-W.conj().T)>1e-3
    from src.solvers.physical_trace_entity import (checked_lu,condensed_entity_block,complete_pq,entity_injection,cell_volume,PhysicalTraceEntities)
    from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
    lu,_=checked_lu(qglobal.conj().T@full_action@qglobal)
    J=np.eye(7,dtype=complex)[:,[2,5]]
    schur,facts=condensed_entity_block(full_action,qglobal,lu,[2,5])
    F=(np.eye(7)-E@full_action)@J
    np.testing.assert_allclose(schur,F.conj().T@full_action@F,atol=1e-12)
    assert max(facts.values())<1e-11
    dual=J.conj().T@(rhs-full_action.conj().T@E.conj().T@rhs)
    np.testing.assert_allclose(dual,F.conj().T@rhs,atol=1e-12)
    assert np.linalg.norm(dual-J.conj().T@(rhs-full_action.conj().T@E@rhs))>1e-3
    np.testing.assert_allclose(cell_volume(rhs,mapping,[0,1],classes,adjoint=True),full_action.conj().T@rhs,atol=1e-12)
    null,rank=entity_injection([np.diag([1.,2.,0.,0.])],2)
    assert rank['rank']==2 and null.shape==(4,2)
    D=np.diag(np.diag(schur));HT=F@np.linalg.solve(D,F.conj().T)
    # Exercise the actual cached-volume/E/EH/J/F/FH/HT methods without a mesh
    # or the fixed 1566-block constructor.
    entity=PhysicalTraceEntities.__new__(PhysicalTraceEntities)
    entity.mapping=mapping;entity.cells=[0,1];entity.sample=lambda:None;entity.elapsed={}
    entity.counts=dict(E=0,EH=0,Q_apply_rhs=0,volume=0,volume_adjoint=0,HT=0,entity_apply_rhs=0,F=0,FH=0)
    entity.classes={};entity.members={};entity.factors={};entity.blocks=[]
    for i in range(2):
        local_Q=np.eye(4,dtype=complex)[:,3:];local_A=classes[i]['A'];local_D=local_Q.conj().T@local_A@local_Q
        entity.classes[i]=dict(A=local_A,Q=local_Q,D=local_D)
        entity.members[i]=np.array([i]);entity.factors[i]=checked_lu(local_D)[0]
        block_D=schur[i:i+1,i:i+1].copy()
        entity.blocks.append(dict(rows=np.array([2 if i==0 else 5]),J=np.ones((1,1),complex),D=block_D,factor=checked_lu(block_D)[0]))
    coeff=[np.array([.2+1j]),np.array([-.7+.3j])]
    np.testing.assert_allclose(entity.F(coeff),F@np.concatenate(coeff),atol=1e-12)
    np.testing.assert_allclose(np.concatenate(entity.FH(rhs)),F.conj().T@rhs,atol=1e-12)
    np.testing.assert_allclose(entity.apply(rhs),HT@rhs,atol=1e-12)
    CU=lambda r:complete_pq(r,lambda v:E@v,lambda v:full_action@v,lambda v:CW@v)
    coupling=PhysicalBalancedCoupling(lambda v:full_action@v,CU,lambda v:HT@v,
        lambda v:np.concatenate([W.conj().T@v,qglobal.conj().T@v]),route='BAL_H')
    actual=coupling.apply(rhs)
    expected=CU(rhs)+(np.eye(7)-np.column_stack([CU(full_action[:,i]) for i in range(7)]))@HT@(rhs-full_action@CU(rhs))
    np.testing.assert_allclose(actual,expected,atol=1e-12)
    residual=rhs-full_action@actual
    np.testing.assert_allclose(W.conj().T@residual,0,atol=1e-11)
    np.testing.assert_allclose(qglobal.conj().T@residual,0,atol=1e-11)
    assert np.isfinite(np.linalg.norm(residual)/np.linalg.norm(rhs))
    doubled=result.copy();doubled[0]+=np.conj(phase)*(raw@C@response)[4]
    assert np.linalg.norm(doubled-result)>1e-3
    assert result[4]==0
    bad=response.copy();bad[1]=1
    with pytest.raises(ValueError,match='zero trace'):cached_interior_action(bad,mapping,[0,1],classes)
    changed=[v.copy() for v in ws];changed[1][0]+=1
    _,facts=resolve_primal(changed,mapping['dofmap'],mapping);assert facts['shared_relative']>1e-3
    args=build_parser().parse_args(['--input','i','--inventory','j','--output','o','--budget','b','--source-sha','s','--bubble-particular-diagnostic'])
    c=selected_contract(args);assert c['cached_A4']==2 and c['local_rhs']==504 and c['functionspace']==c['I4']==0
    args=build_parser().parse_args(['--input','i','--inventory','j','--output','o','--budget','b','--source-sha','s','--bubble-amplification-diagnostic'])
    c=selected_contract(args);assert c['p2_logical']==1 and c['max_refinements']==2 and c['A4']==c['I4']==0
    # The reviewed fix uses the existing packet writer, not a new serializer.
    from types import MappingProxyType
    from src.runners.physical_diagnosis_worker import save_packet
    from src.runners.physical_diagnostic_completion import load_packet
    audit=MappingProxyType(dict(primal_count=1,adjoint_count=1))
    save_packet(tmp_path,'recording',dict(owner=dict(audit),AEg=Eg,rhs=rhs))
    recorded=load_packet(tmp_path/'recording.json')
    assert recorded['owner']==dict(audit)
    np.testing.assert_array_equal(recorded['AEg'],Eg)
    from src.runners.physical_recursive_entry import amplification_recording_retry
    with pytest.raises(ValueError,match='already attempted'):
        amplification_recording_retry(args,dict(bubble_amplification_diagnostic_attempts=[{}]))
    args.amplification_recording_retry=True
    with pytest.raises(ValueError,match='unique frozen'):
        amplification_recording_retry(args,dict(bubble_amplification_diagnostic_attempts=[{},{}]))
    args=build_parser().parse_args(['--input','i','--inventory','j','--output','o','--budget','b','--source-sha','s','--high-trace-component'])
    c=selected_contract(args);assert c['workflow_seconds']==600 and c['B4_limit']==65 and c['I4']['seconds']==60
    # Real two-row KSP, no FE/factor: default authority and explicit override.
    from petsc4py import PETSc
    from src.solvers.physical_recursive_coarse import solve_physical_i4
    from src.solvers.physical_trace_entity import CachedPhysicalTraceAction
    class ArrayVector:
        def __init__(self,value):self.array=np.array(value,copy=True)
    class SparseBoundary:
        def apply(self,source,target):target.array[:]=.07*source.array
    cached=CachedPhysicalTraceAction(mapping,[0,1],classes,SparseBoundary())
    source=ArrayVector(error);target=ArrayVector(np.zeros_like(error));cached.apply_into(source,target)
    np.testing.assert_allclose(target.array,full_action@error+.07*error,atol=1e-12)
    np.testing.assert_array_equal(source.array,error)
    small=PETSc.Vec().createSeq(2);small.array[:]=[1+1j,2-.5j]
    calls=dict(matvec=0,authority=0)
    def small_action(v):
        calls['matvec']+=1;out=v.duplicate();out.array[:]=np.array([2.,3.])*v.array;return out
    def authority(v):
        calls['authority']+=1;out=v.duplicate();out.array[:]=np.array([2.,3.])*v.array;return out
    results=[]
    try:
        for override in (None,authority):
            calls.update(matvec=0,authority=0)
            answer=solve_physical_i4(small,small_action,lambda v:v.copy(),target=1e-4,sample=lambda:None,
                save=lambda *_:None,clock=lambda:0.,residual_action=override)
            results.append(answer['solution'].array.copy())
            assert answer['facts']['explicit_uses_separate_action']==(override is not None)
            assert calls['authority']==(answer['facts']['explicit_A4'] if override else 0)
            assert calls['matvec']==answer['facts']['A4_matvec']+(0 if override else answer['facts']['explicit_A4'])
            np.testing.assert_allclose(answer['applied'].array+answer['residual'].array,small.array,atol=1e-12)
            for k in ('solution','applied','residual'):answer[k].destroy()
        np.testing.assert_allclose(results[0],results[1],atol=1e-12)
    finally:small.destroy()
