"""False PASS or background-dominated ports cannot hide scattered defects."""

import copy

from benchmarks.neural_head_gate_check import check_candidate


def fixture():
    audit = {
        key: 1e-12
        for key in (
            "schur_relative",
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "port_full_rhs_relative",
            "port_operation_relative",
            "recovery_relative",
            "schur_original_identity_operation_relative",
            "independent_DOLFINx_total_native_relative",
        )
    }
    audit["slave_storage_max"] = 0.0
    port = [{"real": 1.0, "imag": 0.0} for _ in range(40)]
    scatter = [{"real": 0.001, "imag": 0.0} for _ in range(40)]
    row = {
        "audit": audit,
        "ordered_complex_port_vector": port,
        "ordered_complex_scattered_port_vector": scatter,
        "ordered_per_channel_power": [0.0] * 40,
        "selected_E": [[{"real": 1.0, "imag": 0.0}]],
        "selected_H_code": [[{"real": 1.0, "imag": 0.0}]],
        "port": {"R_total": 0.0, "T_total": 1.0, "A_balance": 0.0},
        "volume": {"A_volume_total": 0.0, "energy_closure_error_port_volume": 0.0},
    }
    for key in (
        "full_FE_L2_relative",
        "full_FE_scaled_curl_relative",
        "scattered_FE_L2_relative",
        "scattered_scaled_curl_relative",
        "selected_E_relative",
        "selected_H_relative",
    ):
        row[key] = 0.0
    candidate = {
        "baseline_audit": {**audit, "schur_relative": 1.0, "native_relative": 1.0}
    }
    verification = {
        "candidate": "B0",
        "status": "SAME_DISCRETE_QUALIFIED",
        "physics": {
            "rows": {"B0": copy.deepcopy(row), "REFERENCE": copy.deepcopy(row)}
        },
    }
    return candidate, verification


def test_false_saved_pass_cannot_mask_scattered_curl():
    candidate, record = fixture()
    assert check_candidate(candidate, record)["status"] == "SAME_DISCRETE_QUALIFIED"
    record["physics"]["rows"]["B0"]["scattered_scaled_curl_relative"] = 0.001
    assert check_candidate(candidate, record)["status"] == "NOT_QUALIFIED"


def test_scattered_ports_must_pass_in_their_original_scale():
    candidate, record = fixture()
    record["physics"]["rows"]["B0"]["ordered_complex_scattered_port_vector"][0][
        "real"
    ] = 0.002
    result = check_candidate(candidate, record)
    assert result["channel_checks"]["ordered_complex_port_vector"]["passed"]
    assert not result["channel_checks"]["ordered_complex_scattered_port_vector"][
        "passed"
    ]
    assert result["status"] == "NOT_QUALIFIED"


def test_progress_checks_use_original_native_and_frozen_baseline():
    candidate, record = fixture()
    row = record["physics"]["rows"]["B0"]
    row["audit"]["schur_relative"] = 0.2
    row["audit"]["native_relative"] = 2.0
    row["scattered_FE_L2_relative"] = 0.4
    result = check_candidate(candidate, record)
    assert result["progress_signal"] == "NEGATIVE"
    assert not result["E_admitted"]


def test_saved_zero_selected_error_does_not_override_complex_samples():
    candidate, record = fixture()
    row = record["physics"]["rows"]["B0"]
    row["selected_E"][0][0]["real"] = 2.0
    assert row["selected_E_relative"] == 0.0
    result = check_candidate(candidate, record)
    assert result["original_field_errors"]["selected_E_relative"] == 1.0
    assert result["status"] == "NOT_QUALIFIED"
