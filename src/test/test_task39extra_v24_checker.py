"""Pure-data failure tests for the Task39extra V24 offline checker."""

from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest

from benchmarks.check_laptop_speed_v24 import (
    _correction_index,
    _rho_from_denominator,
    a4_raw_facts,
    residual_packet_facts,
)


def test_rho_does_not_turn_a_zero_denominator_into_a_false_zero() -> None:
    value = _rho_from_denominator(1.0, 0.0)
    assert value > 1.0e300


@pytest.mark.parametrize("phase", ["correction", "correction_0", "correction_01", "correction_x"])
def test_noncanonical_correction_phase_is_not_accepted(phase: str) -> None:
    assert _correction_index(phase) is None


def test_duplicate_raw_sequence_is_rejected_without_overwriting(tmp_path) -> None:
    item = {"phase": "raw", "logical_call_sequence": 1}
    balance_root = tmp_path / "inexact_balance"
    balance_root.mkdir()
    for suffix in ("a", "b"):
        (balance_root / f"v24_p4_repair_{suffix}.json").write_text(
            json.dumps(item), encoding="utf-8"
        )
    summary = {
        "interface_stack": {"matrix_identity_before_factor": {}},
        "pc": {"boundary_records": []},
    }
    with pytest.raises(ValueError, match="duplicate raw logical sequence 1"):
        a4_raw_facts(summary, tmp_path)


def _tiny_residual_packet(tmp_path):
    archive = tmp_path / "tiny_residual.npz"
    np.savez(
        archive,
        rhs=np.asarray([1.0 + 0.0j]),
        applied=np.asarray([0.0 + 0.0j]),
        residual=np.asarray([1.0 + 0.0j]),
        solution=np.asarray([0.0 + 0.0j]),
    )
    packet = {
        "arrays": {"path": str(archive), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
        "rhs": {"array_key": "rhs", "dtype": "complex128", "shape": [1]},
        "applied": {"array_key": "applied", "dtype": "complex128", "shape": [1]},
        "residual": {"array_key": "residual", "dtype": "complex128", "shape": [1]},
        "solution": {"array_key": "solution", "dtype": "complex128", "shape": [1]},
        "rhs_norm": 1.0,
        "explicit_relative_residual": 1.0,
    }
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    return packet_path, packet


def test_residual_packet_recomputes_a_failed_true_residual_gate(tmp_path) -> None:
    packet_path, _ = _tiny_residual_packet(tmp_path)
    facts = residual_packet_facts(packet_path, tmp_path)
    assert facts["explicit_ratio_from_rhs_minus_applied"] == pytest.approx(1.0)
    assert facts["checks"]["residual_matches_rhs_minus_applied"] is True
    assert facts["checks"]["gate"] is False


def test_residual_packet_rejects_archive_hash_tampering(tmp_path) -> None:
    packet_path, packet = _tiny_residual_packet(tmp_path)
    packet["arrays"]["sha256"] = "0" * 64
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(ValueError, match="array archive hash mismatch"):
        residual_packet_facts(packet_path, tmp_path)
