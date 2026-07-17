from __future__ import annotations

import argparse
import json

import numpy as np

from benchmarks.neural_pc.benchmark_all_slab_exact_oracle import (
    SCHEMA,
    _prediction,
    run,
)
from benchmarks.neural_pc.data_contract import save_operator
from src.solvers.local_slab_solver import LocalCsrOperator


G4 = {0, 5, 10, 15}
G8 = {0, 2, 5, 7, 8, 10, 13, 15}
G16 = set(range(16))


def _operator(slab: int) -> LocalCsrOperator:
    return LocalCsrOperator(
        shape=(3, 3),
        indptr=np.arange(4, dtype=np.int64),
        indices=np.arange(3, dtype=np.int64),
        values=np.asarray([2 + 0.1j, 3 - 0.2j, 4 + 0.3j]),
        metadata={"slab_id": slab, "owner_rank": slab % 2},
    )


def test_frozen_oracle_sets_are_nested_and_complete() -> None:
    assert G4 < G8 < G16
    assert len(G4) == 4
    assert len(G8) == 8
    assert len(G16) == 16


def test_prediction_uses_conservative_peak_and_half_memory_stop() -> None:
    rows = [
        {
            "owner_rank": 0,
            "factor_storage_bytes": 100,
            "removed_ilu_storage_bytes": 20,
        },
        {
            "owner_rank": 0,
            "factor_storage_bytes": 50,
            "removed_ilu_storage_bytes": 10,
        },
        {
            "owner_rank": 1,
            "factor_storage_bytes": 80,
            "removed_ilu_storage_bytes": 20,
        },
    ]
    prediction = _prediction(
        rows,
        available_memory_bytes=1000,
        baseline_peak_total_bytes=200,
    )
    assert prediction["predicted_peak_worker_rss_conservative_upper_bytes"] == 350
    assert prediction["warning_threshold_bytes"] == 400
    assert prediction["stop_threshold_bytes"] == 500
    assert prediction["safety_gate_passed"] is True


def test_two_slab_factor_census_schema_and_destroy(tmp_path) -> None:
    capture = tmp_path / "capture"
    for slab in range(2):
        save_operator(
            capture / f"rank_{slab % 2:04d}" / f"slab_{slab:03d}",
            _operator(slab),
        )
    output = tmp_path / "census.json"
    payload = run(
        argparse.Namespace(
            capture_root=str(capture),
            baseline_record=None,
            output=str(output),
            expected_slabs=2,
            ordering="COLAMD",
            seed=20260717,
            residual_limit=1.0e-11,
        )
    )
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == SCHEMA
    assert persisted["schema"] == SCHEMA
    assert len(payload["rows"]) == 2
    assert payload["all_factors_finite"] is True
    assert payload["all_residuals_pass"] is True
    assert payload["all_destroyed"] is True
    assert output.with_suffix(".csv").is_file()
