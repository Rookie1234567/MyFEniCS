"""Saved z boundaries and counterexamples to trusted diagnostic status labels."""

import numpy as np
import pytest

from benchmarks.frozen_fe_error_check import check_report, square_sum_check
from src.io.frozen_fe_diagnostic import owned_vector
from src.solvers.frozen_fe_error import FrozenActions, error_diagnostics, state_audits
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.test.test_frozen_fe_error import loaded_witness


def test_only_saved_physical_z_is_loaded_no_double_scaling(tmp_path):
    z = np.array([0.1 + 0.2j, -0.4j, 0.7 + 0.1j])
    path = tmp_path / "frozen.npz"
    # y intentionally differs: its mere presence is not an instruction to rescale.
    np.savez(path, z=z, scaled_y=z * 91)
    record = dict(path=str(path), sha256=file_hash(path), z_sha256=array_hash(z))
    result = owned_vector(record, tmp_path, len(z))
    np.testing.assert_array_equal(result, z)
    assert not result.flags.writeable
    with pytest.raises(ValueError, match="hash ownership"):
        owned_vector({**record, "sha256": "0" * 64}, tmp_path, len(z))
    with pytest.raises(ValueError, match="inventory"):
        owned_vector(record, tmp_path, len(z) + 1)


def diagnostic_fixture():
    packet, matrix = loaded_witness()
    reference = np.linalg.solve(matrix, packet.a["b"])
    actions = FrozenActions(packet)
    states = dict(
        Z0=np.zeros(packet.size, complex),
        NN7=np.array([0.1 + 0.2j, -0.3j, 0.5, 0.7j]),
        REF7=reference,
    )
    cache, audits = state_audits(actions, states)
    errors, records = error_diagnostics(actions, cache)
    raw = dict(
        b=packet.a["b"],
        masters=packet.a["masters"],
        Hp=packet.a["Hp"],
        idofs=packet.a["idofs"],
    )
    for name, state in cache.items():
        raw.update({name + "." + key: value for key, value in state.items()})
    for name, row in errors.items():
        raw.update({name + ".error." + key: value for key, value in row.items()})
    return dict(
        status="PASS",
        trace_rows=packet.nt,
        audits=audits,
        errors=records,
        fields=None,
        action_counts=actions.counts,
    ), raw


def test_checker_recomputes_actual_vectors_and_detects_nonhomogeneous_error():
    report, raw = diagnostic_fixture()
    valid = check_report(report, raw)
    assert valid["identities_pass"]
    # Arbitrary nonzero gp has no matching physical total-field background in
    # this small fixture. The total-field reference Gate must stay false.
    assert not valid["reference_original_equations_pass"]
    assert (
        valid["status"] == "PARTIAL"
    )  # limited fixture is not the six-state FE batch.
    bad = {key: value.copy() for key, value in raw.items()}
    bad["NN7.error.homogeneous"] += raw["Z0.field"]
    assert check_report(report, bad)["status"] == "DIAGNOSTIC_SELF_CHECK_FAILED"
    bad = {key: value.copy() for key, value in raw.items()}
    bad["NN7.error.h"] *= -1
    assert not check_report(report, bad)["identities_pass"]


def test_checker_does_not_accept_raw_status_or_zeroed_reference_residual():
    report, raw = diagnostic_fixture()
    bad = {key: value.copy() for key, value in raw.items()}
    bad["NN7.error.Se"] *= 1.001
    assert not check_report(report, bad)["identities_pass"]
    report["action_counts"]["S"] = 129
    assert not check_report(report, raw)["action_budget_pass"]


def test_cross_square_audit_uses_terms_before_strong_cancellation():
    left = np.array([0.17 + 0.11j, 0.12 - 0.03j])
    right = -left + np.array([1e-6 - 2e-6j, -3e-6j])
    result = square_sum_check(left, right)
    assert result["operation_scale"] > 0.1
    assert result["operation_relative"] < 1e-14
    # A tiny result is not the scale of the operations used to check the
    # identity. Its absolute roundoff remains reported, never hidden.
    assert result["absolute"] >= 0
    assert np.linalg.norm(left + right) ** 2 < 1e-10
