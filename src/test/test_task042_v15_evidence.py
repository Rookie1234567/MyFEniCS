"""Forged labels and coordinates never overrule independent frozen evidence."""

import numpy as np

from src.io.local_trace_evidence_check import head_numeric,manufactured,frozen_state
from src.solvers.neural_fe_action_packet import file_hash


def numeric():
    return dict(rank_A=17,actual_vs_thin_fixed_rhs=1e-12,stationarity_UHr_fixed_rhs=1e-12,
                Hhat_solve_operation_relative=1e-16,schur_relative=1e-12,decoder_gate=True)


def test_saved_success_does_not_override_wrong_rank_or_stationarity():
    row=numeric();assert head_numeric(row,17)
    assert not head_numeric(row,18)
    row['stationarity_UHr_fixed_rhs']=1e-7
    assert not head_numeric(row,17)
    row['stationarity_UHr_fixed_rhs']=float('nan')
    assert not head_numeric(row,17)


def test_manufacture_is_not_physical_b_or_supervised_reference():
    row=dict(numeric=numeric(),known_z_relative=1e-8,homogeneous_recovery_operation_relative=1e-12,
             full_manufactured_RHS_from_original_action=True,reference_used=False,physical_b_overwritten=False,qualified=True)
    assert manufactured(row,17)
    row['physical_b_overwritten']=True;assert not manufactured(row,17)
    row['physical_b_overwritten']=False;row['reference_used']=True;assert not manufactured(row,17)


def test_large_raw_gamma_coordinates_cannot_substitute_direct_trace(tmp_path):
    trace=np.zeros(18144,complex);port=np.arange(40,dtype=float).astype(complex)
    path=tmp_path/'state.npz'
    np.savez(path,c=np.ones(17,complex),trace=trace,port=port,z=np.r_[trace,port])
    record=dict(path=str(path),sha256=file_hash(path))
    assert frozen_state(record,17)
    assert not frozen_state(record,18)
    np.savez(path,c=np.ones(17,complex),trace=trace,port=port,z=np.zeros(18184,complex))
    record['sha256']=file_hash(path)
    assert not frozen_state(record,17)
