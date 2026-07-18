from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks" / "cases" / "095_zero_copy_learned_pc_audit"
TASK = ROOT / "docs" / "para_task006_zero_copy_audit_architecture"


def test_case095_freezes_zero_copy_audit_contract() -> None:
    config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
    expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))

    assert config["task"] == "PARA-Task006"
    assert config["mesh"] == "h5"
    assert config["mpi_size"] == 4
    assert config["representative_slabs"] == [0, 5, 9, 15]
    assert config["reused_candidate"] == "A_D0_R64"
    assert config["audit_period_candidates"] == [4, 8, 16, 32]
    assert expected["private_persistent_local_csr_bytes"] == 0
    assert expected["borrowed_action_relative_error_max"] == 1.0e-12
    assert expected["proxy_false_accept_max"] == 0
    assert expected["proxy_must_accept_at_least_one"] is True
    assert expected["full16_training_allowed"] is False
    assert expected["learned_active_global_allowed"] is False
    assert expected["ordinary_default_changed"] is False


def test_task006_p0_provenance_records_frozen_r4() -> None:
    text = (TASK / "outcomes" / "provenance.md").read_text(encoding="utf-8")
    assert "consumed screening split" in text
    assert "A_D0_R64" in text
    assert "没有 retraining" in text
    for slab in (0, 5, 9, 15):
        assert f"| {slab} |" in text
