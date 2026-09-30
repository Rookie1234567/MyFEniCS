"""Corrupted success labels must not pass V12's raw-field checker."""

from copy import deepcopy

from src.io.actual_loss_block_descent_check import (
    accepted_progress_step, fixed_head_fd_gate, state_identity, verified_field_gate,
)


def test_bad_analytic_gradient_rejected_even_if_saved_qualified():
    row={"direction":"421201","analytic":1.,"qualified":True,
         "estimates":[{"h":1e-4,"slope":2.,"signal_over_delta":100.},
                      {"h":1e-5,"slope":2.,"signal_over_delta":100.}]}
    fd={"directions":[row,dict(row,direction="421202"),
                       dict(row,direction="analytic_gradient")],
        "perturbation_points":6,"fixed_gamma_all_points":True,
        "derivative_kind":"FIXED_HEAD_PARTIAL_GRADIENT","qualified":True}
    assert not fixed_head_fd_gate(fd,1e-14)


def test_changed_gamma_hash_rejected():
    row={"state":{"gamma_sha256":"expected","hidden_sha256":"h","z_sha256":"z",
                  "port_sha256":"p"},"point":{"gamma_hash":"expected","hidden_hash":"h"},
         "gamma_frozen_within_block":True}
    assert state_identity(row)
    row["point"]["gamma_hash"]="changed"
    assert not state_identity(row)


def test_false_loss_acceptance_and_wrong_port_rejected():
    row={"gamma_sha256":"g","gamma_frozen":True,"loss":0.9,"delta_eval":1e-14,
         "backtracks":0,"alpha":1e-4,"port":1e-12,"actual_loss_accepted":True,
         "derivative_kind":"FIXED_HEAD_PARTIAL_GRADIENT"}
    assert accepted_progress_step(row,1.,"g")
    bad=deepcopy(row); bad["loss"]=1.1
    assert not accepted_progress_step(bad,1.,"g")
    bad=deepcopy(row); bad["port"]=1e-3
    assert not accepted_progress_step(bad,1.,"g")
    bad=deepcopy(row); bad["gamma_sha256"]="different"
    assert not accepted_progress_step(bad,1.,"g")


def test_missing_complex_channel_rejected():
    row={"audit":{key:1e-12 for key in (
        "schur_relative","native_relative","augmented_relative","original_total_augmented_relative",
        "port_full_rhs_relative","port_operation_relative","independent_DOLFINx_total_native_relative",
        "recovery_relative")},
         "fields":{key:1e-12 for key in (
             "full_FE_L2_relative","full_FE_scaled_curl_relative","scattered_FE_L2_relative",
             "scattered_scaled_curl_relative","selected_E_relative","selected_H_relative")},
         "ordered_complex_total_ports":[{"real":0.,"imag":0.}]*40,
         "ordered_complex_scattered_ports":[{"real":0.,"imag":0.}]*40,
         "comparison":{"ordered_complex_ports_relative":1e-12,
                       "power_absolute_differences":{key:1e-12 for key in
                           ("R_total","T_total","A_balance","A_volume")},
                       "max_channel_power_difference":1e-12,"energy_closure_absolute":1e-12}}
    row["audit"]["slave_storage_max"]=0
    assert verified_field_gate(row)
    row["ordered_complex_total_ports"].pop()
    assert not verified_field_gate(row)
