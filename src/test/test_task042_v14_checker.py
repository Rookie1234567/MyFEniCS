"""False pass labels, near-rank failure, reference leakage and missing ports."""
from copy import deepcopy
import pytest
from src.io.orthonormal_trace_evidence_check import decoder_numeric,basis_numeric,manufactured
from src.io.actual_loss_block_descent_check import verified_field_gate

@pytest.fixture
def numeric():
    return dict(rank_A=1560,A_singular_range=[.005,1000.],driver='gelsd',cond=1e-12,
        correction_count=0,exact_optimum_claimed=False,decoder_gate=True,
        actual_vs_thin_fixed_rhs=1e-12,stationarity_UHr_fixed_rhs=1e-12,
        Hhat_solve_operation_relative=1e-17,schur_relative=1e-12)

def test_saved_pass_cannot_override_actual_thin_or_stationarity(numeric):
    assert decoder_numeric(numeric)
    for key in ('actual_vs_thin_fixed_rhs','stationarity_UHr_fixed_rhs'):
        wrong=deepcopy(numeric);wrong[key]=1e-6
        assert not decoder_numeric(wrong)

def test_fixed_rank_threshold_and_driver_cannot_be_scanned(numeric):
    wrong=deepcopy(numeric);wrong['A_singular_range']=[1e-11,1000.]
    assert not decoder_numeric(wrong)
    wrong=deepcopy(numeric);wrong['cond']=1e-14
    assert not decoder_numeric(wrong)
    wrong=deepcopy(numeric);wrong['exact_optimum_claimed']=True
    assert not decoder_numeric(wrong)

def test_mixed_manufactured_rhs_and_reference_flags(numeric):
    row=dict(numeric=numeric,known_z_relative=1e-12,homogeneous_recovery_operation_relative=1e-16,
        full_manufactured_RHS_from_original_action=True,reference_used=False,physical_b_overwritten=False)
    assert manufactured(row)
    for field in ('reference_used','physical_b_overwritten'):
        bad=deepcopy(row);bad[field]=True;assert not manufactured(bad)
    row['known_z_relative']=1e-3;assert not manufactured(row)

def test_raw_gamma_is_not_new_decoder():
    row=dict(rank_P=1560,P_singular_range=[8e-10,20.],Hhat_condition=1e4,
        P_reconstruction=1e-15,Q_orthogonality=1e-15,raw_gamma_writeback=False,main_forward='trace_EQUALS_Q_times_c')
    assert basis_numeric(row)
    row['raw_gamma_writeback']=True;assert not basis_numeric(row)

def test_missing_complex_port_or_power_failure_cannot_pass():
    keys=('schur_relative','native_relative','augmented_relative','original_total_augmented_relative',
        'port_full_rhs_relative','port_operation_relative','independent_DOLFINx_total_native_relative','recovery_relative')
    fields=('full_FE_L2_relative','full_FE_scaled_curl_relative','scattered_FE_L2_relative',
        'scattered_scaled_curl_relative','selected_E_relative','selected_H_relative')
    row=dict(audit=dict.fromkeys(keys,1e-12),fields=dict.fromkeys(fields,1e-8),
        comparison=dict(ordered_complex_ports_relative=1e-8,max_channel_power_difference=1e-8,
            energy_closure_absolute=1e-8,power_absolute_differences=dict(R_total=0.,T_total=0.,A_balance=0.,A_volume=0.)),
        ordered_complex_total_ports=[dict(real=1.,imag=.1)]*40,
        ordered_complex_scattered_ports=[dict(real=.1,imag=.2)]*40)
    row['audit']['slave_storage_max']=0.
    assert verified_field_gate(row)
    wrong=deepcopy(row);wrong['ordered_complex_total_ports'].pop();assert not verified_field_gate(wrong)
    wrong=deepcopy(row);wrong['comparison']['energy_closure_absolute']=.1;assert not verified_field_gate(wrong)
    wrong=deepcopy(row);wrong['ordered_complex_scattered_ports'][0]['imag']=float('nan');assert not verified_field_gate(wrong)

def test_frozen_state_cannot_hide_lower_precision(tmp_path):
    import numpy as np
    from src.io.orthonormal_trace_evidence_check import frozen_state
    from src.solvers.neural_fe_action_packet import array_hash,file_hash
    arrays=dict(hidden=np.zeros(8576,dtype=np.float32),c=np.zeros(1560,dtype=np.complex128),
        trace=np.zeros(18144,dtype=np.complex128),port=np.zeros(40,dtype=np.complex128),z=np.zeros(18184,dtype=np.complex128))
    path=tmp_path/'state.npz';np.savez(path,**arrays)
    record=dict(path=str(path),sha256=file_hash(path),**{k+'_sha256':array_hash(v) for k,v in arrays.items()})
    assert not frozen_state(record)
