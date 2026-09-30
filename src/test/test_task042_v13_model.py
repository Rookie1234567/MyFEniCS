"""Pure-array V13 real-coordinate response/port and acceptance contracts."""

import numpy as np
import pytest

from src.solvers.tangent_head_model import (bar_action,real_local_step,common_radius,
                                          predicted_gain,fixed_head_scale,loss_resolution,accept_step)
from src.solvers.stable_head_varpro import PortBlocks
from src.test.test_task042_v12_actual_loss import DensePacket


def test_complex_nonhermitian_homogeneous_port_tangent():
    rng=np.random.default_rng(421401);n=44
    S=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))
    S[-40:,-40:]=np.diag(np.linspace(2,3,40)+.3j)
    rhs=rng.normal(size=n)+1j*rng.normal(size=n)
    packet=DensePacket(S,rhs);ports=PortBlocks(packet,S[:,4:])
    dt=rng.normal(size=4)+1j*rng.normal(size=4)
    value,dz=bar_action(packet,ports,dt)
    assert np.linalg.norm(S@dz-np.r_[value,np.zeros(40)])/np.linalg.norm(S@dz)<1e-13
    z,_=ports.closed(dt,rhs)
    assert np.linalg.norm(z-dz)>1e-2 # nonzero port RHS must NOT enter tangent
    q=rng.normal(size=4)+1j*rng.normal(size=4)
    assert abs(np.vdot(q,value)-np.vdot(ports.adjoint(q),dt))<1e-10


def test_real_local_model_recovers_only_real_hidden_coefficients():
    rng=np.random.default_rng(421402)
    V=rng.normal(size=(20,3))+1j*rng.normal(size=(20,3))
    D=np.eye(3);G=1j*np.eye(3)
    a=np.array([.2,-.3,.4]);dh,dg,v,meta=real_local_step(D,G,V,V@a)
    assert not np.iscomplexobj(dh)
    assert np.allclose(dh,a) and np.allclose(dg,1j*a) and np.allclose(v,V@a)
    assert meta['rank']==3
    with pytest.raises(ValueError,match='real hidden'):
        real_local_step(D.astype(complex),G,V,V@a)


def test_response_step_sign_prediction_and_shared_radius():
    r=np.array([1+1j,2-.5j]);v=np.array([.4+.7j,.5-1j]);bnorm=3.
    derivative=-np.vdot(v,r).real/bnorm**2
    row=fixed_head_scale(np.ones(10),r,v,bnorm,derivative)
    assert row['sign_trustworthy'] and row['s']>0 and row['pred']>0
    assert np.isclose(row['pred'],predicted_gain(r,row['alpha']*v,bnorm))
    tau=common_radius(np.ones(4),np.ones(3,dtype=complex),np.ones(4)*100,np.ones(3)*1e5j)
    assert tau*200<=1e-4*2*(1+1e-12)
    assert tau*np.linalg.norm(np.ones(3)*1e5)<=.1*np.sqrt(3)*(1+1e-12)


def test_trial_requires_actual_descent_audit_and_local_prediction():
    audit=dict(recovery_relative=1e-13,schur_original_identity_operation_relative=1e-13,
               port_full_rhs_relative=1e-14,port_operation_relative=1e-14,slave_storage_max=0,
               native_relative=.3)
    old={'loss':1.};new={'loss':.9}
    assert accept_step(old,new,.11,1e-14,1e-14,audit,audit)['accepted']
    assert not accept_step(old,{'loss':1.},.11,1e-14,1e-14,audit,audit)['accepted']
    assert not accept_step(old,new,.11,1e-14,1e-14,audit,dict(audit,port_operation_relative=.01))['accepted']
    assert not accept_step(old,new,.11,1e-14,.01,audit,audit)['accepted']


def test_resolution_includes_residual_operation_difference():
    first={'loss':.2,'bar_residual':np.ones(3,dtype=complex)}
    second=dict(first,bar_residual=first['bar_residual']+1e-6j)
    row=loss_resolution([first,second],2.)
    assert row['delta_J']>1e-7 and row['observed_loss_differences']==[0.]


def test_four_v13_inputs_explicit_only():
    from src.io.tangent_head_compensation import load_tangent_head,STAGES
    from src.io.task042_profile import ROOT
    for filename in ('v13_tangent_check.dat','v13_response_step.dat','v13_head_compensation.dat','v13_verify.dat'):
        specification=load_tangent_head(ROOT/'input/task042_neural_coarse_inverse'/filename)
        assert specification.derived['stage'].split('-')[1] in STAGES
        assert specification.physical_model_sha256=='2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de'
    assert load_tangent_head(ROOT/'input/task042_neural_coarse_inverse/v12_block_descent.dat') is None


def test_refinement_is_bounded_same_frozen_C_and_carries_identity(tmp_path,monkeypatch):
    from src.io import tangent_head_compensation as loader
    from src.io.task042_profile import ROOT
    from src.io.input_loader import InputError
    (tmp_path/'compensation_1').mkdir()
    np.savez(tmp_path/'compensation_1/directions.npz',dot_gamma=np.ones((1560,1),complex))
    old_path=tmp_path/'stage_result.json';old_path.write_text('{}')
    old=dict(status='C_JOINT_TANGENT_UNRESOLVED',accepted_C=0,trials=[],source_sha='frozen-source')
    monkeypatch.setattr(loader,'read_result',lambda name:(old,old_path))
    path=ROOT/'input/task042_neural_coarse_inverse/v13_head_compensation_refine.dat'
    spec=loader.load_tangent_head(path)
    assert spec.derived['refine_frozen_joint_taylor'] is True
    assert spec.derived['refinement_identity']['source_sha']=='frozen-source'
    old['bounded_joint_Taylor_refinement']={}
    with pytest.raises(InputError,match='one frozen'):
        loader.load_tangent_head(path)


def test_stable_compensation_minus_sign_original_nonhermitian_action():
    from src.solvers.tangent_head_model import compensation_solve
    rng=np.random.default_rng(421407);nt=6;n=nt+40
    S=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))
    S[-40:,-40:]=np.eye(40)*(4+.2j)
    packet=DensePacket(S,np.ones(n,dtype=complex));ports=PortBlocks(packet,S[:,nt:])
    P=rng.normal(size=(nt,2))+1j*rng.normal(size=(nt,2))
    fixed=rng.normal(size=(nt,3))+1j*rng.normal(size=(nt,3))
    dg,pt,thin,record=compensation_solve(packet,ports,P,fixed)
    bar=S[:nt,:nt]-S[:nt,nt:]@np.linalg.solve(S[nt:,nt:],S[nt:,:nt])
    assert np.linalg.norm(fixed+bar@pt-thin)<1e-11
    assert record['compensation_triangular_operation_error']<1e-12
    assert np.linalg.norm(thin)<np.linalg.norm(fixed)
    assert record['rank_P']==2 and record['rank_A']==2
