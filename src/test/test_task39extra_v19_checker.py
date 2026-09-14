"""A passing worker label cannot replace raw native/port residual gates."""

import numpy as np
import pytest

from benchmarks.check_dual_cell_condensed_v19 import residual_facts


def _record():
    raw = {name: np.array([1e-12 + 0j]) for name in (
        "native_residual", "augmented_port_residual", "internal_residual",
        "native_identity_difference", "schur_port_identity_difference")}
    facts = {name: 1.0 for name in (
        "native_rhs_norm", "port_operation_scale", "internal_operation_scale",
        "native_identity_operation_scale", "schur_port_identity_operation_scale")}
    facts.update({name: 1e-12 for name in (
        "original_A6_relative", "port_closure_relative", "internal_residual_relative",
        "native_identity_relative", "schur_port_identity_relative")})
    facts["status"] = "PASS"
    return raw, facts


@pytest.mark.parametrize("array,reported,value", [
    ("native_residual", "original_A6_relative", 1.1e-6),
    ("augmented_port_residual", "port_closure_relative", 1.1e-8),
    ("internal_residual", "internal_residual_relative", 1.1e-10),
    ("native_identity_difference", "native_identity_relative", 1.1e-10),
    ("schur_port_identity_difference", "schur_port_identity_relative", 1.1e-10),
])
def test_terminal_fails_a_raw_gate_despite_pass_label(array, reported, value):
    raw, facts = _record()
    assert residual_facts(raw, facts, terminal=True)["passed"]
    raw[array][:] = value
    facts[reported] = value
    assert not residual_facts(raw, facts, terminal=True)["passed"]


def test_progress_is_observation_but_reported_numbers_must_match_raw():
    raw, facts = _record()
    raw["native_residual"][:] = facts["original_A6_relative"] = 0.3
    raw["augmented_port_residual"][:] = facts["port_closure_relative"] = 0.2
    assert residual_facts(raw, facts)["passed"]
    assert not residual_facts(raw, facts, terminal=True)["passed"]
    facts["original_A6_relative"] = 1e-9
    assert not residual_facts(raw, facts)["passed"]


def test_nonfinite_progress_cannot_pass_even_with_a_matching_report():
    raw, facts = _record()
    raw["native_residual"][:] = 1e308
    facts["original_A6_relative"] = float("inf")
    with np.errstate(over="ignore", invalid="ignore"):
        assert not residual_facts(raw, facts)["passed"]
