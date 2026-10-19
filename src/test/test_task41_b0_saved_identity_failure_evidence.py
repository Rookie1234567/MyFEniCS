from __future__ import annotations

import hashlib
import json

import pytest

from src.solvers.fullspace_dtn_action import _canonical_json_bytes
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    _task41_b0_require_saved_identity_match,
)
from src.solvers.task40_v25_complete_volume import _atomic_write_json


def test_saved_identity_match_passes_and_mismatch_is_saved_before_strict_failure(
    tmp_path,
):
    actual = {
        "mesh": {"module_path": "/jit/cache-a/kernel.py"},
        "modes": [{"identity_sha256": "mode-a"}],
    }
    expected = {
        "mesh": {"module_path": "/jit/cache-b/kernel.py"},
        "modes": [{"identity_sha256": "mode-a"}],
    }
    current_context = {"gauss": {"verified": True}, "source_sha256": {"form.py": "a"}}
    reconstructed_context = {
        "gauss": {"verified": True},
        "source_sha256": {"form.py": "a"},
    }
    bridge = {"status": "VERIFIED", "producer_identity_sha256": "producer-sha"}
    evidence_path = tmp_path / "task41_b0_saved_surface_identity_failure.json"
    callback_facts = []

    def persist_failure(facts):
        callback_facts.append(dict(facts))
        _atomic_write_json(evidence_path, facts["identity_failure_evidence"])

    common = {
        "current_assembly_context": current_context,
        "reconstructed_assembly_context": reconstructed_context,
        "source_equivalence_bridge": bridge,
        "producer_identity_sha256": "producer-sha",
        "failure_callback": persist_failure,
    }
    assert _task41_b0_require_saved_identity_match(actual, actual, **common) is None
    assert callback_facts == []
    assert not evidence_path.exists()

    with pytest.raises(
        ValueError,
        match="Task41 B0 donor fresh mesh/MPC/orientation/config/ABI/math identity differs",
    ):
        _task41_b0_require_saved_identity_match(actual, expected, **common)

    assert len(callback_facts) == 1
    assert callback_facts[0]["phase"] == "task41_b0_saved_donor_identity_mismatch"
    assert callback_facts[0]["status"] == "FAILED"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == "task41.p0.b0.saved_surface_identity_failure.v1"
    assert evidence["producer_identity_sha256"] == "producer-sha"
    assert evidence["current_assembly_context"] == current_context
    assert evidence["reconstructed_assembly_context"] == reconstructed_context
    assert evidence["source_equivalence_bridge"] == bridge
    difference = evidence["leaf_differences"]
    assert len(difference) == 1
    assert difference[0]["path"] == "$.mesh.module_path"
    assert difference[0]["actual"] == actual["mesh"]["module_path"]
    assert difference[0]["expected"] == expected["mesh"]["module_path"]
    assert difference[0]["actual_sha256"] == hashlib.sha256(
        _canonical_json_bytes(actual["mesh"]["module_path"])
    ).hexdigest()
    assert difference[0]["expected_sha256"] == hashlib.sha256(
        _canonical_json_bytes(expected["mesh"]["module_path"])
    ).hexdigest()
    assert len(evidence["actual_identity_sha256"]) == 64
    assert len(evidence["expected_identity_sha256"]) == 64
