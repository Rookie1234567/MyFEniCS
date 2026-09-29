"""An expired immutable clock never grants a new path budget."""

import json
import time

from src.solvers.autonomous_batch_window import window_snapshot


def test_expired_original_clock_cannot_restart(tmp_path):
    path = tmp_path / "window.json"
    path.write_text(
        json.dumps(
            {
                "start_utc_ns": time.time_ns() - 30_000_000_000,
                "observed_utc_ns": time.time_ns(),
                "observed_monotonic": time.monotonic(),
                "heavy_limit_seconds": 10,
                "total_limit_seconds": 20,
                "carry_in_seconds": 100,
            }
        )
    )
    result = window_snapshot(path)
    assert result["heavy_remaining_seconds"] == 0
    assert result["total_remaining_seconds"] == 0
    assert result["cumulative_elapsed_including_history"] >= 130
