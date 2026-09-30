"""V13 counterexamples for false acceptance and lost physical inventory."""

from copy import deepcopy
import numpy as np

from src.io.tangent_head_evidence_check import accepted_trial_gate,compensation_gate,dual_gate
from src.io.actual_loss_block_descent_check import verified_field_gate


def trial():
    return dict(hidden_step_real=True,actual_network_candidate=True,linear_only_candidate=False,
        hidden_change=1e-5,old_loss=1.,trial_loss=.9,pred=.11,old_delta_J=1e-14,trial_delta_J=1e-14,
        old_native=.3,accepted=True,trial_audit=dict(native_relative=.3,recovery_relative=1e-13,
        schur_original_identity_operation_relative=1e-13,slave_storage_max=0.,
        port_full_rhs_relative=1e-13,port_operation_relative=1e-13))


def test_complex_hidden_and_linear_only_fake_candidates_rejected():
    good=trial();assert accepted_trial_gate(good)
    bad=dict(good,hidden_step_real=False);assert not accepted_trial_gate(bad)
    bad=dict(good,linear_only_candidate=True);assert not accepted_trial_gate(bad)


def test_saved_acceptance_without_actual_gain_or_with_wrong_port_rejected():
    bad=dict(trial(),trial_loss=1.1);assert not accepted_trial_gate(bad)
    bad=deepcopy(trial());bad['trial_audit']['port_operation_relative']=1e-2
    assert not accepted_trial_gate(bad)


def test_true_loss_dual_required_and_operation_scale_is_used():
    pair=dict(left=2.,right=2.+1e-12,operation_scale=3.)
    rows={str(seed):dict(pair) for seed in (421301,421302)}
    rows['actual_loss_barS_adjoint']=dict(pair)
    assert dual_gate(rows)
    rows['actual_loss_barS_adjoint']['right']=3.
    assert not dual_gate(rows)


def test_wrong_compensation_sign_rejected_from_triangular_witness():
    R=np.array([[2+.3j,.2-.1j],[0,1-.2j]]);k=np.array([1+.2j,.5-.1j])
    dotgamma=np.linalg.solve(R,-k)
    assert np.linalg.norm(R@dotgamma+k)<1e-12
    row=dict(rank_P=1560,rank_A=1560,compensation_sign='R_dot_gamma_EQUALS_MINUS_k',
        compensation_triangular_operation_error=np.linalg.norm(R@dotgamma+k)/(2*np.linalg.norm(k)),
        QR_reassembly=1e-14,saved_A_three_original_checks=[1e-14]*3,Hhat_condition=10)
    assert compensation_gate(row)
    wrong=np.linalg.solve(R,k)
    row['compensation_triangular_operation_error']=np.linalg.norm(R@wrong+k)/(2*np.linalg.norm(k))
    assert not compensation_gate(row)


def test_missing_channel_rejects_false_field_pass():
    from src.test.test_task042_v12_checker import test_missing_complex_channel_rejected
    test_missing_complex_channel_rejected()


def test_cleared_head_inconsistent_with_declared_gamma_rejected(tmp_path):
    from src.io.tangent_head_evidence_check import frozen_network_gate
    from src.solvers.neural_fe_action_packet import file_hash,array_hash
    hidden=np.ones(8576);gamma=np.ones(1560,dtype=complex)
    values=np.r_[hidden,np.zeros(3120)];z=np.zeros(18184,dtype=complex);port=z[-40:]
    path=tmp_path/'state.npz'
    arrays=dict(hidden=hidden,gamma=gamma,network_parameters=values,z=z,port=port)
    np.savez(path,**arrays)
    record=dict(path=str(path),sha256=file_hash(path),**{k+'_sha256':array_hash(v) for k,v in arrays.items()})
    assert not frozen_network_gate(record)
