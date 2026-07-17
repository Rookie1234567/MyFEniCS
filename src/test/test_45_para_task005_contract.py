from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "docs" / "para_task005_comprehensive_all_slab_learned_pc"
CASE = ROOT / "benchmarks" / "cases" / "094_comprehensive_all_slab_learned_pc"


def test_case094_freezes_task005_primary_contract() -> None:
    config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
    expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))
    assert config["task"] == "PARA-Task005"
    assert config["mesh"] == "h5"
    assert config["mpi_size"] == 4
    assert config["num_slabs"] == 16
    assert config["smoother_iterations"] == 2
    assert config["representative_slabs"] == [0, 5, 9, 15]
    assert config["train_samples_per_slab"] == 1024
    assert config["validation_samples_per_slab"] == 256
    assert config["holdout_samples_per_slab"] == 256
    assert expected["true_profile_ilu_factor_count"] == 0
    assert expected["true_profile_ilu_apply_count"] == 0
    assert expected["true_profile_hidden_fallback_count"] == 0
    assert expected["paired_runs_required"] == 3
    assert config["ordinary_default_changed"] is False


def test_task004_response_and_task005_p0_are_recorded() -> None:
    response = (
        ROOT
        / "docs"
        / "para_task004_full_16_slab_exact_oracle"
        / "response_v1.md"
    ).read_text(encoding="utf-8")
    p0 = (TASK / "outcomes" / "p0_environment_and_baseline.md").read_text(
        encoding="utf-8"
    )
    assert "all_slab_oracle_positive_signal" in response
    assert "global_stored_ilu_factor_nnz" in response
    assert "852" in p0
    assert "97.252974" in p0
    assert "swap in/out delta" in p0
