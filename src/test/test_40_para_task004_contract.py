from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "docs" / "para_task004_full_16_slab_exact_oracle"
CASE = ROOT / "benchmarks" / "cases" / "093_full_16_slab_exact_oracle"


def test_task004_outcomes_and_case_records_are_complete() -> None:
    required_outcomes = {
        "summary.md",
        "changed_files.md",
        "experiment_matrix.csv",
        "oracle_ladder.csv",
        "factor_lifecycle_report.md",
        "runtime_breakdown.csv",
        "memory_report.md",
        "operator_action_report.md",
        "learned_runtime_budget.md",
        "decision.md",
    }
    assert {path.name for path in (TASK / "outcomes").iterdir()} == required_outcomes
    assert {
        path.name for path in (CASE / "records").glob("*.json")
    } == {
        "baseline.json",
        "factor_census.json",
        "oracle_ladder.json",
        "one_step.json",
        "decision.json",
    }


def test_frozen_sets_and_final_decision_match_records() -> None:
    config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
    expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))
    ladder = json.loads(
        (CASE / "records" / "oracle_ladder.json").read_text(encoding="utf-8")
    )
    decision = json.loads(
        (CASE / "records" / "decision.json").read_text(encoding="utf-8")
    )
    assert set(config["g4"]) < set(config["g8"]) < set(config["g16"])
    assert len(config["g4"]) == 4
    assert len(config["g8"]) == 8
    assert len(config["g16"]) == 16
    assert ladder["runs"][2]["exact_slabs"] == config["g16"]
    assert ladder["runs"][2]["iteration_reduction"] >= 0.20
    assert ladder["runs"][2]["iteration_reduction"] < 0.40
    assert expected["status"] == "all_slab_oracle_positive_signal"
    assert decision["classification"] == expected["status"]
    assert decision["training_started"] is False
    assert expected["ordinary_default_changed"] is False


def test_g16_hard_contract_and_one_step_negative_are_documented() -> None:
    ladder = json.loads(
        (CASE / "records" / "oracle_ladder.json").read_text(encoding="utf-8")
    )
    one_step = json.loads(
        (CASE / "records" / "one_step.json").read_text(encoding="utf-8")
    )
    summary = (TASK / "outcomes" / "summary.md").read_text(encoding="utf-8")
    decision = (TASK / "outcomes" / "decision.md").read_text(encoding="utf-8")
    assert one_step["numeric_pass"] is False
    assert one_step["official_rta_run"] is False
    for text in (summary, decision):
        assert "all_slab_oracle_positive_signal" in text
        assert "ordinary default" in text
    g16 = ladder["runs"][2]
    assert g16["exact_backend_count"] == 16
    assert g16["ilu_factor_constructed_count"] == 0
    assert g16["global_stored_ilu_factor_nnz"] == 0
    assert g16["ilu_apply_count"] == 0
    assert g16["hidden_fallback_count"] == 0
    assert "No-hidden-ILU" in summary


def test_oracle_ladder_csv_has_all_formal_points() -> None:
    with (TASK / "outcomes" / "oracle_ladder.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["run"] for row in rows] == [
        "baseline",
        "G4_two_step",
        "G8_two_step",
        "G16_two_step",
        "G16_one_step",
    ]
    assert float(rows[3]["iteration_reduction_pct"]) >= 20.0
    assert float(rows[4]["full_residual"]) > 1.0e-6
