"""V11 compact checker must reject a corrupt saved success label."""

from copy import deepcopy

from src.io.stable_head_varpro_check import (
    corrected_manufactured_gate,
    manufactured_gate,
    same_discrete_gate,
    stable_head_gate,
)


def test_manufactured_rejects_status_only_success():
    row = {"stable": {"full_rhs_residual": {"relative": 3e-7},
                      "known_z_relative": 1e-9,
                      "homogeneous_recovery_pair": 1e-15},
           "stable_gate": True}
    assert not manufactured_gate(row)
    assert not corrected_manufactured_gate(row["stable"])


def test_head_rejects_rank_only_success():
    point = {key: 1e-12 for key in (
        "network_vs_Pgamma_trace_relative", "Pgamma_vs_Zc_trace_relative",
        "actual_vs_thin_residual_fixed_physical_b",
        "actual_stationarity_UHr_fixed_physical_b")}
    assert stable_head_gate(point, 1560)
    point["actual_vs_thin_residual_fixed_physical_b"] = 4e-8
    assert not stable_head_gate(point, 1560)


def test_full_field_gate_reads_every_raw_component():
    row = {
        "audit": {key: 1e-12 for key in (
            "schur_relative", "native_relative", "augmented_relative",
            "original_total_augmented_relative", "port_full_rhs_relative",
            "port_operation_relative", "independent_DOLFINx_total_native_relative",
            "recovery_relative")},
        "fields": {key: 1e-12 for key in (
            "full_FE_L2_relative", "full_FE_scaled_curl_relative",
            "scattered_FE_L2_relative", "scattered_scaled_curl_relative",
            "selected_E_relative", "selected_H_relative")},
        "ordered_complex_total_ports": [0] * 40,
        "ordered_complex_scattered_ports": [0] * 40,
        "comparison": {"ordered_complex_ports_relative": 1e-12,
                       "power_absolute_differences": {key: 1e-12 for key in (
                           "R_total", "T_total", "A_balance", "A_volume")},
                       "max_channel_power_difference": 1e-12,
                       "energy_closure_absolute": 1e-12},
    }
    row["audit"]["slave_storage_max"] = 0
    assert same_discrete_gate(row)
    corrupted = deepcopy(row)
    corrupted["fields"]["scattered_FE_L2_relative"] = 0.73
    assert not same_discrete_gate(corrupted)
    corrupted = deepcopy(row)
    corrupted["ordered_complex_total_ports"].pop()
    assert not same_discrete_gate(corrupted)
    corrupted = deepcopy(row)
    corrupted["comparison"]["power_absolute_differences"]["A_volume"] = 1e-3
    assert not same_discrete_gate(corrupted)
