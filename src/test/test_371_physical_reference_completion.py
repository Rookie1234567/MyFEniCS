"""Small complex systems exercise V4 limits and failure evidence without PDE runs."""
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.fullspace_p4_reference import PhysicalP4Reference
from src.solvers.physical_reference_diagnostics import (
    DiagnosticRefinementV4, ReferenceAccuracyRejected, ReferenceDependencySkipped, EvidenceBlocked, residual_identity)
from src.solvers.physical_error_diagnostics import project_error, ProjectionLimit, coarse_diagnostics
from src.runners.physical_diagnostic_completion import independent_item, finalize_diagnostics, load_packet, reuse_v3
from src.runners.physical_diagnosis_worker import save_packet


@contextmanager
def problem(errors, save=None):
    v=np.array([[3,1j],[.2,2]],complex)
    c=np.array([1+2j,.3j]); d=np.array([.2-.5j,1j]); h=2.
    aug=np.block([[v,c[:,None]],[-d[None,:],np.array([[h]])]])
    a=v+np.outer(c,d)/h
    matrix=PETSc.Mat().createAIJ((3,3),nnz=3,comm=PETSc.COMM_SELF)
    matrix.setValues(range(3),range(3),aug);matrix.assemble()
    rhs=PETSc.Vec().createSeq(2,comm=PETSc.COMM_SELF);rhs.array[:]=[1j,2+1j]
    def apply(x,target):target.array[:]=a@x.array
    def compose(base,ports,target):target.array[:]=base.array+c*ports[0]
    carrier=SimpleNamespace(carrier=SimpleNamespace(entries=[SimpleNamespace(normalization_h=h)]),
        recover_auxiliary=lambda x:np.array([d@x.array/h]),compose_physical_rhs=compose)
    calls=[];packets=[]
    class Factor:
        def refinement_settings(self):return {'ICNTL(10)':0,'CNTL(2)':-1.,'modified':False}
        def solve_repeated(self,b,x):
            calls.append(b.array.copy())
            x.array[:]=np.linalg.solve(aug,b.array)*(1-errors[min(len(calls)-1,len(errors)-1)])
    reference=PhysicalP4Reference.__new__(PhysicalP4Reference)
    reference.matrix,reference.action=matrix,SimpleNamespace(apply=apply)
    reference.slaves=np.array([],dtype=np.int32)
    reference.sample=lambda:None;reference.marker=lambda *_:None
    reference.factor=Factor();reference.audit={'solve_calls':0}
    reference.diagnostic_refinement_v4=DiagnosticRefinementV4(
        save or (lambda name,facts:packets.append((name,facts))),carrier,np.array([1,1j]),{'source':'tiny'})
    try:yield reference,rhs,calls,packets
    finally:rhs.destroy();matrix.destroy()


def test_complex_residual_block_sign():
    g=np.array([1+2j]);y=np.array([.3j]);a=np.array([.2-.1j])
    v,c,d,h=2+1j,3-2j,.4+1j,2.
    native=(v+c*d/h)*y
    aug=np.r_[v*y+c*a,-d*y+h*a]
    rp=d*y-h*a
    facts=residual_identity(g,y,a,native,aug,v*y,c*a,c*rp/h,c*d*y/h)
    assert facts['identity_relative_to_operations']<1e-15
    assert np.linalg.norm(facts['r4']-(facts['rF']+c*rp/h))>1e-2


@pytest.mark.parametrize('errors,steps', [([0.],0),([1e-4,1e-7],1),([1e-3,1e-3,0.],2)])
def test_bounded_refinement_original_denominator_and_saved_ports(errors,steps):
    with problem(errors) as (reference,rhs,calls,packets):
        result=reference.solve_intermediate(rhs)
        try:
            assert result['refinement_steps']==steps
            assert len(calls)==steps+1
            assert result['final_true_residual']<=1e-10
            residuals=[f for name,f in packets if '_residual_' in name]
            assert all(f['original_rhs_norm']==pytest.approx(rhs.norm()) for f in residuals)
            for index,facts in enumerate(residuals[1:],1):
                np.testing.assert_allclose(calls[index][:2],residuals[index-1]['r4'])
                np.testing.assert_allclose(facts['augmented_state'],
                    residuals[index-1]['augmented_state']+facts['delta'])
            assert packets[-1][0].endswith('_decision_'+str(steps))
        finally:result['final_solution'].destroy()


def test_unresolved_saves_before_rejection_and_caps_three_calls():
    with problem([.1]) as (reference,rhs,calls,packets):
        with pytest.raises(ReferenceAccuracyRejected):reference.solve_intermediate(rhs)
        assert len(calls)==3
        assert packets[-1][1]['status']=='REFERENCE_ACCURACY_UNRESOLVED'
        assert len([n for n,_ in packets if '_residual_' in n])==3


def test_strict_default_still_single_rejected_backsolve():
    with problem([1e-3]) as (reference,rhs,calls,packets):
        reference.diagnostic_refinement_v4=None
        with pytest.raises(RuntimeError,match='original A4 reference'):reference.solve_intermediate(rhs)
        assert len(calls)==1 and not packets


def test_exact_rejected_rhs_skipped_without_second_logical_solve():
    with problem([.1]) as (reference,rhs,calls,packets):
        with pytest.raises(ReferenceAccuracyRejected):reference.solve_intermediate(rhs)
        with pytest.raises(ReferenceDependencySkipped):reference.solve_intermediate(rhs)
        assert len(calls)==3 and reference.diagnostic_refinement_v4.logical_rhs==1
        assert packets[-1][1]['status']=='skipped'
        rhs.array[0]+=1e-15
        with pytest.raises(ReferenceAccuracyRejected):reference.solve_intermediate(rhs)
        assert len(calls)==6 and reference.diagnostic_refinement_v4.logical_rhs==2


def test_evidence_failure_precedes_factor_call():
    def broken(*_):raise OSError('disk full')
    with problem([0.],save=broken) as (reference,rhs,calls,_):
        with pytest.raises(EvidenceBlocked):reference.solve_intermediate(rhs)
        assert calls==[]


def test_local_projection_limit_retains_last_approximation_and_shared_errors_propagate():
    mass=lambda x:np.array([1.,2.])*x
    count=0
    def limit():
        nonlocal count
        count+=1
        if count==2:raise ProjectionLimit('local')
    result=project_error(lambda x:x,lambda x:x,mass,np.ones(2),np.array([1,1j]),checkpoint=limit)
    assert result['status']=='PROJECTION_UNRESOLVED'
    assert result['iterations']==1 and np.linalg.norm(result['coarse'])>0
    assert result['interpretation']=='approximation upper bound only'
    def shared():raise RuntimeError('resource')
    with pytest.raises(RuntimeError,match='resource'):
        project_error(lambda x:x,lambda x:x,mass,np.ones(2),np.array([1,1j]),checkpoint=shared)


def test_local_rejection_continues_independent_item_but_common_errors_escape():
    summary={};saved=[]
    def reject():raise ReferenceAccuracyRejected({'final_true_residual':1e-8})
    args=(lambda *x:saved.append(x),summary,lambda *_:None)
    assert independent_item('coarse',reject,*args) is None
    assert independent_item('mass',lambda:3,*args)==3
    for error in (ValueError('mapping'),ValueError('nonfinite'),RuntimeError('resource')):
        def fail():raise error
        with pytest.raises(type(error),match=str(error)):independent_item('fatal',fail,*args)


def test_cleanup_writes_summary_and_preserves_primary():
    summary={'status':'FAILED'};events=[]
    def bad():raise RuntimeError('destroy')
    primary=ValueError('mapping')
    finalize_diagnostics(summary,[bad,lambda:events.append('second')],lambda:events.append('write'),primary)
    assert events==['second','write'] and summary['status']=='FAILED'
    assert summary['cleanup_errors'][0]['message']=='destroy'
    with pytest.raises(RuntimeError,match='cleanup'):
        finalize_diagnostics({},[bad],lambda:events.append('write'))


def test_coarse_packet_can_precede_separate_identity_rejection():
    calls=[]
    def solve(x):
        calls.append(x)
        if len(calls)>1:raise ReferenceAccuracyRejected({'final_true_residual':1e-8})
        return x
    e=np.array([1,1j]);identity=lambda x:x
    projection=dict(parallel=e,perpendicular=e*0,error_energy=2.,status='PROJECTION_CLOSED')
    result=coarse_diagnostics(identity,identity,identity,identity,solve,e,projection,identity_check=False)
    assert len(calls)==1 and result['unit_remaining_energy']==0


def test_atomic_packet_roundtrip(tmp_path):
    save_packet(tmp_path,'packet',dict(value=np.array([1+2j]),status='failed'))
    np.testing.assert_array_equal(load_packet(tmp_path/'packet.json')['value'],[1+2j])
    assert not list(tmp_path.glob('*.tmp'))


def test_old_packets_recompute_when_artifacts_available():
    import json
    from pathlib import Path
    inventory=json.loads(Path('docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json').read_text())
    if not Path(inventory['latest_formal_attempt']['root']).is_dir():
        pytest.skip('historical ignored V3 artifacts unavailable in this clone')
    packets,evidence=reuse_v3(inventory)
    assert len(packets)==len(evidence)==13


def test_actual_mumps_refinement_settings_readonly():
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    with problem([0.]) as (reference,_,__,___):
        factor=_MumpsFactor(reference.matrix)
        try:
            factor.symbolic(reference.matrix);factor.numeric(reference.matrix)
            first=factor.refinement_settings();second=factor.refinement_settings()
            assert first==second and first['modified'] is False
        finally:factor.destroy()
