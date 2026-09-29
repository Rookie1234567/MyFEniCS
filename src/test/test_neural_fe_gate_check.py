"""Reject claimed success and recompute full complex observable differences."""

import numpy as np

from benchmarks.neural_fe_gate_check import equation_gate, relative_difference


def test_equation_gate_does_not_trust_status_and_checks_recovery():
    values = dict.fromkeys(
        (
            "schur_relative",
            "augmented_relative",
            "native_relative",
            "original_total_augmented_relative",
            "port_full_rhs_relative",
            "port_operation_relative",
            "independent_DOLFINx_total_native_relative",
            "port_absolute",
            "recovery_relative",
            "slave_storage_max",
        ),
        0.0,
    )
    values["strict_pass"] = True
    assert equation_gate(values)
    values["port_operation_relative"] = 0.01
    assert not equation_gate(values)
    values["port_operation_relative"] = 0
    values["recovery_relative"] = 1e-8
    assert not equation_gate(values)


def test_complex_phase_difference_is_not_removed_and_zero_uses_absolute_rule():
    ref = np.array([1 + 2j, 0.3 - 0.4j])
    assert relative_difference(1j * ref, ref) > 1
    assert relative_difference(np.array([2e-14j]), np.array([0j])) == 2e-14
