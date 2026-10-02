"""A single failed physical requirement must defeat flattering status fields."""
from copy import deepcopy

import pytest

from benchmarks.check_task042_local_block_records import complete, equation, reference_equation


def valid_record():
    audit = dict.fromkeys(("schur_relative", "native_relative", "augmented_relative",
                          "original_total_augmented_relative", "port_full_rhs_relative",
                          "port_operation_relative", "recovery_relative",
                          "schur_original_identity_operation_relative",
                          "independent_DOLFINx_total_native_relative"), 1e-12)
    audit["slave_storage_max"] = 0
    return dict(audit=audit, fields=dict(total_E=1e-6, scattered_E=1e-6, H=1e-6),
                comparison=dict(ordered_complex_ports_relative=1e-6,
                                power_absolute_differences=dict(R=1e-8, T=1e-8, A=1e-8, A_volume=1e-8),
                                max_channel_power_difference=1e-8, energy_closure_absolute=1e-8),
                status="SAME_DISCRETE_QUALIFIED")


def test_native_pass_cannot_replace_schur_gate():
    row = valid_record()
    assert complete(row, True)
    row["audit"]["schur_relative"] = 2.5e-6
    assert not equation(row["audit"])
    assert not complete(row, True)


def test_aggregate_power_and_fields_cannot_replace_single_channel_gate():
    row = valid_record()
    row["comparison"]["max_channel_power_difference"] = 1.67e-6
    assert equation(row["audit"])
    assert not complete(row, True)
    assert not complete(valid_record(), False)
    reference = valid_record()["audit"]
    assert reference_equation(reference)
    reference["independent_DOLFINx_total_native_relative"] = 1e-5
    assert not reference_equation(reference)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1e-8])
def test_nonfinite_or_negative_error_is_not_qualification(value):
    row = deepcopy(valid_record())
    row["fields"]["scattered_E"] = value
    assert not complete(row, True)
