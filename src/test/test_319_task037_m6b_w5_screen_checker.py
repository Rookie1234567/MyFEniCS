from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import benchmarks.run_task037_extra_m6b as runner


RAW = Path(
    "benchmarks/artifacts/task037_extra_development/"
    "m6b_w5_disk_fgmres_41cbbd4_screen_run1"
)


def test_w5_frozen_checkpoint_recompute_and_tamper_fail_closed():
    worker = json.loads((RAW / "m6b_w5_summary.json").read_text())
    valid = runner._m6b_w5_checkpoint_evidence(RAW, worker["screen"])
    assert valid["pass"] is True
    assert valid["checkpoint_recompute"]["residuals"]["200"] == (
        0.12750559935416836
    )

    missing = deepcopy(worker["screen"])
    del missing["samples"]["200"]
    assert runner._m6b_w5_checkpoint_evidence(RAW, missing)["pass"] is False

    tampered = deepcopy(worker["screen"])
    tampered["samples"]["20"]["artifacts"]["rhs"]["sha256"] = "0" * 64
    assert runner._m6b_w5_checkpoint_evidence(RAW, tampered)["pass"] is False


def test_w5_numeric_gate_and_checker_parser_are_fixed():
    assert runner._m6b_w5_numeric_gate(
        {"20": 0.5, "100": 0.1, "150": 0.2, "200": 0.05}
    )["pass"] is True
    negative = runner._m6b_w5_numeric_gate(
        {
            "20": 0.3237575899853163,
            "100": 0.18105272614044404,
            "150": 0.15403613391023072,
            "200": 0.12750559935416836,
        }
    )
    assert negative["problems"] == ["true_residual_iter200"]

    args = runner._parser().parse_args(
        [
            "m6b-w5-check",
            "--raw-dir",
            str(RAW),
            "--watchdog-summary",
            "/tmp/w5-watchdog.json",
            "--output",
            "/tmp/w5-check.json",
            "--expected-producer-sha",
            "41cbbd454eb8336d9ea5378ed618447acfc60aac",
        ]
    )
    assert args.command == "m6b-w5-check"
    assert args.expected_producer_sha == "41cbbd454eb8336d9ea5378ed618447acfc60aac"
