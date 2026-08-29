"""Focused pure-Python contracts for the J1 no-JIT staging lane."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.task038_full3d_jit_staging import (
    append_jsonl,
    cache_manifest,
    create_fresh_cache,
    marker_files,
    prepare_fresh_root,
    process_tree_snapshot,
    write_marker,
)


SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = "benchmarks.run_task038_full3d_jit_staging"
CHECKER = "benchmarks.task038_full3d_jit_staging_checker"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_runner(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", RUNNER, "--mode", "j1-contract", "--artifact-root", str(root), "--source-sha", SOURCE_SHA],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_checker(record: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", CHECKER, "--record", str(record), "--expected-source-sha", SOURCE_SHA, "--output", str(output)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_helper_root_markers_process_and_cache_contract(tmp_path: Path) -> None:
    root = tmp_path / "helper-root"
    layout = prepare_fresh_root(root, root / "jit_cache")
    write_marker(layout["marker_dir"], "parent_started", {"stage": "smoke"})
    create_fresh_cache(layout["cache_dir"])
    write_marker(layout["marker_dir"], "fresh_cache_created", {"stage": "smoke"})
    with pytest.raises(ValueError):
        write_marker(layout["marker_dir"], "parent_started", {"stage": "smoke"})
    snapshot = process_tree_snapshot(os.getpid(), "smoke", exit_code=7)
    assert snapshot["exit_code"] == 7
    assert snapshot["all_status_readable"] is True
    assert snapshot["rss_bytes"] == sum(fact["rss_bytes"] for fact in snapshot["members"])
    sample_path = root / "samples.jsonl"
    append_jsonl(sample_path, snapshot)
    assert len(sample_path.read_text(encoding="utf-8").splitlines()) == 1
    artifact = layout["cache_dir"] / "one.c"
    artifact.write_bytes(b"abc")
    manifest = cache_manifest(layout["cache_dir"])
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["relative_path"] == "one.c"
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert marker_files(layout["marker_dir"])[-1].name == "001_fresh_cache_created.json"


def test_runner_checker_happy_path(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    run = _run_runner(root)
    assert run.returncode == 0, run.stderr
    record = root / "j1_record.json"
    output = tmp_path / "checker.json"
    checked = _run_checker(record, output)
    assert checked.returncode == 0, checked.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["classification"] == "J1_CONTRACT_PASS"
    assert result["identity"]["source_sha"] == SOURCE_SHA
    assert result["evidence"]["raw_record_sha256"] == _sha256(record)
    assert sorted(path.name for path in root.iterdir()) == sorted(
        ["markers", "jit_cache", "process_samples.jsonl", "cache_manifest.json", "marker_manifest.json", "j1_record.json"]
    )


def test_second_runner_attempt_is_fail_closed_and_preserves_hashes(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    first = _run_runner(root)
    assert first.returncode == 0, first.stderr
    before = _tree_hashes(root)
    second = _run_runner(root)
    assert second.returncode != 0
    assert _tree_hashes(root) == before


def test_checker_rejects_mutated_process_aggregate(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    run = _run_runner(root)
    assert run.returncode == 0, run.stderr
    record_path = root / "j1_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sample_path = root / "process_samples.jsonl"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    sample["rss_bytes"] += 1
    sample_path.write_text(json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    record["process"]["sample_sha256"] = _sha256(sample_path)
    record_path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    output = tmp_path / "checker.json"
    checked = _run_checker(record_path, output)
    assert checked.returncode != 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert any("RSS aggregate" in error for error in result["contract_errors"])
