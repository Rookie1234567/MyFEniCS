from __future__ import annotations

import json
import os
from pathlib import Path

import benchmarks.run_task037_extra_h2b as h2b
import benchmarks.run_task037_extra_m6b as runner


RAW = Path(
    "benchmarks/artifacts/task037_extra_development/"
    "m6b_w5_disk_fgmres_41cbbd4_screen_run1"
)
WATCHDOG = Path(
    "/tmp/task037_m6b_w5_disk_fgmres_41cbbd4_watchdog_run1/"
    "m6b_w5_disk_fgmres_watchdog_summary.json"
)
SOURCE = "41cbbd454eb8336d9ea5378ed618447acfc60aac"


def _run(monkeypatch, raw: Path, watchdog: Path, output: Path) -> dict:
    worker = json.loads((RAW / "m6b_w5_summary.json").read_text())
    source = worker["source_at_start"]
    monkeypatch.setattr(h2b, "_light_source", lambda: source)
    monkeypatch.setattr(h2b, "_source_pair_valid", lambda start, end: start == end)
    rc = runner._m6b_w5_check_command(raw, watchdog, output, SOURCE)
    return {"rc": rc, "result": json.loads(output.read_text())}


def _tampered_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw_checkpoint_tamper"
    raw.mkdir()
    for name in runner.M6B_W5_RAW_ARTIFACT_NAMES:
        if name == "m6b_w5_summary.json":
            worker = json.loads((RAW / name).read_text())
            worker["screen"]["samples"]["200"]["artifacts"]["rhs"]["sha256"] = "0" * 64
            (raw / name).write_text(
                json.dumps(runner._attach_evidence(worker), sort_keys=True) + "\n"
            )
        else:
            os.symlink((RAW / name).resolve(), raw / name)
    return raw


def test_w5_frozen_checker_classifies_numeric_negative(monkeypatch, tmp_path):
    checked = _run(monkeypatch, RAW, WATCHDOG, tmp_path / "positive.json")
    result = checked["result"]
    assert checked["rc"] == 1
    assert result["classification"] == "NUMERIC_FAIL"
    assert result["execution_evidence_ok"] is True
    assert result["resource_evidence_ok"] is True
    assert result["numeric_ok"] is False
    assert result["numeric_gate"]["problems"] == ["true_residual_iter200"]
    assert result["checkpoint_recompute"]["pass"] is True


def test_w5_checker_checkpoint_tamper_is_execution_failure(monkeypatch, tmp_path):
    checked = _run(
        monkeypatch,
        _tampered_raw(tmp_path),
        WATCHDOG,
        tmp_path / "checkpoint_tamper.json",
    )
    result = checked["result"]
    assert checked["rc"] == 1
    assert result["classification"] == "EXECUTION_FAIL"
    assert result["execution_evidence_ok"] is False
    # The frozen watchdog inventory still points at the original raw directory;
    # mixed raw/inventory roots are intentionally rejected as resource evidence.
    assert result["resource_evidence_ok"] is False


def test_w5_checker_process_tamper_is_resource_failure(monkeypatch, tmp_path):
    watchdog = json.loads(WATCHDOG.read_text())
    watchdog["process"]["peak_rss_bytes"] += 1
    tampered = tmp_path / "process_tamper.json"
    tampered.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True) + "\n"
    )
    checked = _run(monkeypatch, RAW, tampered, tmp_path / "resource_tamper.json")
    result = checked["result"]
    assert checked["rc"] == 1
    assert result["classification"] == "RESOURCE_OR_EVIDENCE_FAIL"
    assert result["execution_evidence_ok"] is True
    assert result["resource_evidence_ok"] is False


def test_w5_numeric_gate_and_parser_contract():
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
            "--raw-dir", str(RAW),
            "--watchdog-summary", str(WATCHDOG),
            "--output", "/tmp/w5-check.json",
            "--expected-producer-sha", SOURCE,
        ]
    )
    assert args.command == "m6b-w5-check"
    assert args.expected_producer_sha == SOURCE
