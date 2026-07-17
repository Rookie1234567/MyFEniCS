from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from benchmarks.neural_pc.screen_task005_linear import _structured_synthetic
from benchmarks.neural_pc.screen_task005_nonlinear import (
    _build_mlp,
    _numpy_forward,
)
from src.solvers.local_slab_solver import LocalCsrOperator


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


def test_task005_p2_pool_is_frozen_and_bounded() -> None:
    pool = json.loads(
        (CASE / "p2_candidate_pool.json").read_text(encoding="utf-8")
    )
    candidates = pool["candidates"]
    assert pool["frozen_before_screening"] is True
    assert pool["representative_slabs"] == [0, 5, 9, 15]
    assert len(candidates) <= 16
    assert {
        row["rank"] for row in candidates if row["lane"] == "A"
    }.issuperset({32, 64, 96, 128})
    lane_b = [row for row in candidates if row["lane"] == "B"]
    assert {row["rank"] for row in lane_b}.issuperset({32, 64, 96})
    assert {row["hidden"] for row in lane_b} == {64, 128}
    assert {row["depth"] for row in lane_b} == {2, 3}
    assert {row["activation"] for row in lane_b}.issuperset(
        {"tanh", "relu"}
    )
    assert {row["map"] for row in lane_b} == {"direct", "skip"}
    assert {row["recipe"] for row in candidates} == {"D0", "D1"}


def test_task005_structured_synthetic_pairs_use_true_operator_action() -> None:
    size = 32
    diagonal = np.linspace(2.0, 4.0, size) + 0.25j
    operator = LocalCsrOperator(
        shape=(size, size),
        indptr=np.arange(size + 1, dtype=np.int64),
        indices=np.arange(size, dtype=np.int64),
        values=diagonal,
        metadata={"slab_id": 0},
    )
    rng = np.random.default_rng(17)
    real_target = rng.standard_normal((16, size)) + 1j * rng.standard_normal(
        (16, size)
    )
    rhs, target, families = _structured_synthetic(
        operator, real_target, count=25, seed=19
    )
    np.testing.assert_allclose(rhs, target * diagonal, rtol=1e-13, atol=1e-13)
    assert rhs.shape == target.shape == (25, size)
    assert set(families) == {
        "smooth_low_frequency",
        "interface_localized",
        "boundary_localized",
        "high_frequency_randomized",
        "real_error_pod_combination",
    }


def test_task005_numpy_nonlinear_export_matches_torch() -> None:
    import torch

    torch.manual_seed(23)
    packed = np.random.default_rng(29).standard_normal((5, 8)).astype(
        np.float32
    )
    for activation in ("tanh", "relu", "gelu"):
        model = _build_mlp(4, 7, 3, activation).eval()
        expected = model(torch.from_numpy(packed)).detach().numpy()
        actual = _numpy_forward(
            model, packed, activation=activation, base=None
        )
        np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=2e-6)


def test_task005_early_stop_is_gate_driven_and_fully_recorded() -> None:
    outcomes = TASK / "outcomes"
    required = {
        "summary.md",
        "changed_files.md",
        "experiment_matrix.csv",
        "data_and_teacher_report.md",
        "local_quality_by_slab.csv",
        "model_ablation.csv",
        "runtime_backend_report.md",
        "owner_batch_report.md",
        "shadow_safety_report.md",
        "global_ab.csv",
        "robustness_matrix.csv",
        "memory_report.md",
        "amortization_report.md",
        "model_and_dataset_provenance.md",
        "decision.md",
    }
    assert required.issubset({path.name for path in outcomes.iterdir()})
    summary = (outcomes / "summary.md").read_text(encoding="utf-8")
    decision = (outcomes / "decision.md").read_text(encoding="utf-8")
    experiment = (outcomes / "experiment_matrix.csv").read_text(
        encoding="utf-8"
    )
    assert "learned_pc_memory_budget_failure" in summary
    assert "68.282 MiB" in summary
    assert "P2 = FAIL_STORAGE_GATE" in decision
    assert "P3,not_run_by_gate" in experiment
