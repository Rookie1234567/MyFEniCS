from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_task003_outcomes_and_case_contract() -> None:
    outcomes = ROOT / "docs" / "para_task003_lu_teacher_nn_only_local_inverse" / "outcomes"
    required = {
        "summary.md",
        "changed_files.md",
        "experiment_matrix.csv",
        "teacher_resource_report.md",
        "local_quality.csv",
        "runtime_breakdown.csv",
        "memory_report.md",
        "model_and_dataset_provenance.md",
        "decision.md",
    }
    assert required <= {path.name for path in outcomes.iterdir()}
    summary = (outcomes / "summary.md").read_text(encoding="utf-8")
    assert "exact_lu_oracle_global_signal_insufficient" in summary
    assert "not_run_by_gate" in summary
    assert "840" in summary and "860" in summary

    case = ROOT / "benchmarks" / "cases" / "092_lu_teacher_nn_only_local_inverse"
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    assert expected["status"] == "exact_lu_oracle_global_signal_insufficient"
    assert expected["teacher_accuracy_gate_passed"] is True
    assert expected["three_slab_oracle_signal_passed"] is False
    assert expected["model_training_run"] is False


def test_task002_review_response_uses_frozen_classification() -> None:
    task = ROOT / "docs" / "para_task002_batched_neural_smoother_acceleration"
    response = (task / "response_v1.md").read_text(encoding="utf-8")
    summary = (task / "outcomes" / "summary.md").read_text(encoding="utf-8")
    assert "microkernel_success_global_neutral" in response
    assert "microkernel_success_global_neutral" in summary
