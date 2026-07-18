from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.task034_p3_h3_reranking import (
    Task034RerankingError,
    comparison_metric_vector,
    rerank_against_p2_threshold,
)


def _comparison(scale: float, residual: float = 1.0e-12) -> dict:
    return {
        "scalar_observables": {
            name: {"absolute_error": scale}
            for name in ("R_total", "T_total", "A_balance", "A_volume_total")
        },
        "selected_planes": {
            "max_electric_relative_l2": scale,
            "max_magnetic_relative_l2": scale,
        },
        "interfaces": {
            "max_electric_tangential_relative_l2": scale,
            "max_magnetic_tangential_relative_l2": scale,
        },
        "diffraction_orders": {
            "power_relative_error_max": scale,
            "power_relative_error_rms": scale,
            "complex_amplitude_relative_error_max": scale,
            "complex_amplitude_relative_error_rms": scale,
        },
        "full_true_relative_residual": residual,
    }


def test_metric_vector_is_the_exact_twelve_component_d1_vector() -> None:
    vector = comparison_metric_vector(_comparison(0.25))
    assert len(vector) == 12
    assert set(vector.values()) == {0.25}


def test_reranking_uses_worst_component_ratio_and_residual_as_gate() -> None:
    rows = rerank_against_p2_threshold(
        {
            "p2_h3": _comparison(1.0),
            "better": _comparison(0.5),
            "worse": _comparison(1.1, residual=2.0e-9),
        }
    )
    assert [row["candidate"] for row in rows] == ["better", "p2_h3", "worse"]
    assert rows[0]["max_ratio_to_p2_h3_threshold"] == pytest.approx(0.5)
    assert rows[0]["componentwise_no_worse_than_p2_h3"]
    assert not rows[-1]["componentwise_no_worse_than_p2_h3"]
    assert not rows[-1]["full_true_residual_le_1e-9"]


def test_reranking_fails_closed_without_p2_threshold() -> None:
    with pytest.raises(Task034RerankingError, match="p2_h3 threshold"):
        rerank_against_p2_threshold({"candidate": _comparison(0.5)})


def test_reranking_fails_closed_on_zero_baseline_component() -> None:
    baseline = _comparison(1.0)
    baseline["scalar_observables"]["R_total"]["absolute_error"] = 0.0
    with pytest.raises(Task034RerankingError, match="strictly positive"):
        rerank_against_p2_threshold({"p2_h3": baseline})


def test_tracked_phase_d_reranking_record_preserves_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    path = (
        root
        / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
        "p3_h3_reference_summary.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    payload_sha256 = record.pop("payload_sha256")
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == payload_sha256
    assert record["status"] == "p3_h3_reference_and_reranking_pass"
    assert record["aggregation_source"][
        "worktree_clean_including_nonignored_untracked"
    ]
    assert not record["identity"]["thresholds_relaxed"]
    assert record["classification"] == {
        "p3_h3_reference_available": True,
        "p3_h5_to_h3_grid_change": "measured",
        "p3_h7p5_equal_accuracy_under_new_reference": "pass",
        "p2_h3_equal_accuracy_under_new_reference": "pass",
        "grid_convergence_proven": False,
        "continuum_reference": False,
    }
