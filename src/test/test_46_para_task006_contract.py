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


def test_task006_final_outcomes_are_complete_and_gate_consistent() -> None:
    outcomes = TASK / "outcomes"
    required = {
        "summary.md",
        "changed_files.md",
        "experiment_matrix.csv",
        "borrowed_action_equivalence.md",
        "proxy_qualification.csv",
        "failure_injection_matrix.csv",
        "periodic_audit_report.md",
        "runtime_breakdown.csv",
        "memory_report.md",
        "live_shadow_report.md",
        "provenance.md",
        "decision.md",
    }
    assert required <= {path.name for path in outcomes.iterdir()}
    decision = (outcomes / "decision.md").read_text(encoding="utf-8")
    summary = (outcomes / "summary.md").read_text(encoding="utf-8")
    assert "audit_architecture_false_reject_failure" in decision
    assert "P3-P8 = not_run_by_gate" in decision
    assert "persistent private CSR" in summary
    expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))
    assert expected["status"] == "qualified_negative_result"
    assert (
        expected["classification"]
        == "audit_architecture_false_reject_failure"
    )
