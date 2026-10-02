"""Raw-metric counterexamples, without reading any historical reference arrays."""
from copy import deepcopy

import numpy as np
import pytest

from benchmarks.check_trace_galerkin_evidence import equation_pass, physical_pass


def row():
    a = dict.fromkeys(("schur_relative", "native_relative", "augmented_relative",
                      "original_total_augmented_relative", "port_full_rhs_relative",
                      "port_operation_relative"), 1e-9)
    a.update(recovery_relative=1e-12, schur_original_identity_operation_relative=1e-12,
             slave_storage_max=0., independent_DOLFINx_total_native_relative=1e-9,
             strict_pass=True)
    return dict(audit=a, fields=dict(total_E=1e-7, scattered_E=1e-7),
                comparison=dict(ordered_complex_ports_relative=1e-7,
                                power_absolute_differences=dict(R=1e-7, T=1e-7),
                                max_channel_power_difference=1e-7, energy_closure_absolute=1e-7))


@pytest.mark.parametrize("key,value", [("schur_relative", 1.01e-6),
                                      ("port_operation_relative", 1.01e-6),
                                      ("recovery_relative", 1.01e-10),
                                      ("slave_storage_max", 1e-30),
                                      ("native_relative", np.nan)])
def test_declared_pass_cannot_override_original_equation(key, value):
    r = row(); r["audit"][key] = value
    assert r["audit"]["strict_pass"] and not equation_pass(r["audit"])
    assert not physical_pass(r, True)


def test_equation_pass_does_not_replace_power_and_scattered_field_checks():
    r = row(); assert physical_pass(r, True)
    for key, value in [("max_channel_power_difference", 1.01e-6),
                       ("energy_closure_absolute", 1.01e-5)]:
        other = deepcopy(r); other["comparison"][key] = value
        assert equation_pass(other["audit"]) and not physical_pass(other, True)
    r["fields"]["scattered_E"] = 1.01e-4
    assert not physical_pass(r, True)
    assert not physical_pass(row(), False)
