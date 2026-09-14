"""V18 launcher lease, immutable-history, and replay-boundary contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from src.io.input_loader import InputError
from src.runners.task038_launcher import (
    V18_PREDECESSOR_V17_LEDGER_SHA256,
    _reserve_v18_shared_budget,
    _settle_v14_shared_budget,
    _validate_v18_prerequisite,
)


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_LEDGER_DIRS = (
    "p4_schur_v14/review_v14",
    "p4_blr_v16/review_v16_p4_blr",
    "p4_blr_tradeoff_v17/review_v17_p4_blr_tradeoff",
)


def _repo_with_historical_ledgers(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for relative in HISTORICAL_LEDGER_DIRS:
        destination = (
            repo
            / "benchmarks"
            / "artifacts"
            / "task39extra"
            / relative
            / "shared_workflow_ledger.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            ROOT
            / "benchmarks"
            / "artifacts"
            / "task39extra"
            / relative
            / "shared_workflow_ledger.json",
            destination,
        )
    return repo


def _clock(seconds: float = 0.0) -> dict[str, float]:
    return {
        "monotonic_seconds": float(seconds),
        "boottime_seconds": float(seconds),
        "utc_seconds": float(seconds),
    }


def _reserve(repo: Path, run_directory: Path, *, stage: str, source: str):
    return _reserve_v18_shared_budget(
        repo,
        run_directory,
        source_sha=source,
        stage=stage,
        stage_budget={"workflow_seconds": 600, "solve_seconds": 600},
        workflow_clock_start=_clock(),
        time_policy="observe_only",
    )


def _settle(
    lease: dict,
    *,
    status: str,
    elapsed: float = 1.0,
) -> None:
    _settle_v14_shared_budget(
        lease,
        status=status,
        authority=None,
        parent_interval={"budget_seconds": float(elapsed)},
        parent_clock_end=_clock(elapsed),
    )


def _settle_worker_failure(lease: dict, fixed_source: str) -> None:
    # The lease result intentionally exposes only ledger coordinates; recover
    # the attempt directory and source SHA from the parent reservation record.
    ledger = json.loads(Path(lease["path"]).read_text(encoding="utf-8"))
    attempt = ledger["stages"][lease["stage"]]["attempts"][lease["attempt_index"]]
    run_directory = Path(attempt["run_directory"])
    run_directory.mkdir(parents=True, exist_ok=True)
    failed_source = attempt["source_sha"]
    (run_directory / "implementation_bug_replay.json").write_text(
        json.dumps(
            {
                "classification": "IMPLEMENTATION_BUG",
                "stage": lease["stage"],
                "failed_source_sha": failed_source,
                "fixed_source_sha": fixed_source,
                "bug_and_fix": "test-only bound replay fixture",
            }
        ),
        encoding="utf-8",
    )
    (run_directory / "physical_p4_cell_condensed_v18_summary.json").write_text(
        json.dumps(
            {
                "status": "FAILED",
                "result_classification": "WORKER_FAILED",
                "source_sha": failed_source,
                "error": "test-only worker exception",
            }
        ),
        encoding="utf-8",
    )
    _settle(lease, status="WORKER_FAILED")


def test_v18_ledger_is_independent_and_cumulative(tmp_path: Path):
    repo = _repo_with_historical_ledgers(tmp_path)
    lease = _reserve(
        repo,
        tmp_path / "u0",
        stage="U0_PREFLIGHT",
        source="a" * 40,
    )
    ledger_path = Path(lease["path"])
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["batch_identity"] == "review_v18_p4_cell_condensed"
    assert ledger["elapsed_seconds"] == 0.0
    assert ledger["predecessors"]["v17"]["sha256"] == V18_PREDECESSOR_V17_LEDGER_SHA256
    assert ledger["predecessors"]["v17"]["read_only"] is True
    assert ledger_path != repo / "benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json"

    _settle(lease, status="EVIDENCE_ONLY", elapsed=1.25)
    settled = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert settled["elapsed_seconds"] == pytest.approx(1.25)
    attempt = settled["stages"]["U0_PREFLIGHT"]["attempts"][0]
    assert attempt["status"] == "EVIDENCE_ONLY"
    assert attempt["actual_elapsed_seconds"] == pytest.approx(1.25)


def test_v18_selection_prerequisite_only_binds_readable_hashes(tmp_path: Path):
    ledger_path = tmp_path / "ledger" / "shared_workflow_ledger.json"
    ledger_path.parent.mkdir()
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    selection = ledger_path.parent / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "batch_identity": "review_v18_p4_cell_condensed",
                "exact_control_qualified": True,
                "evidence": [
                    {
                        "path": str(evidence),
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    facts = _validate_v18_prerequisite(ledger_path, "U3_BLR_CONTROL")
    assert facts is not None
    assert facts["selector_owned_by"] == "independent_checker_and_v18_worker"
    assert facts["evidence"][0]["bytes"] == evidence.stat().st_size

    evidence.write_text("changed\n", encoding="utf-8")
    with pytest.raises(InputError, match="evidence hash changed"):
        _validate_v18_prerequisite(ledger_path, "U3_BLR_CONTROL")


def test_v18_allows_one_batch_replay_only(tmp_path: Path):
    repo = _repo_with_historical_ledgers(tmp_path)
    first = _reserve(
        repo,
        tmp_path / "u0_first",
        stage="U0_PREFLIGHT",
        source="a" * 40,
    )
    _settle_worker_failure(first, "b" * 40)

    replay = _reserve(
        repo,
        tmp_path / "u0_replay",
        stage="U0_PREFLIGHT",
        source="b" * 40,
    )
    assert replay["replay"] is True
    _settle_worker_failure(replay, "c" * 40)

    next_stage = _reserve(
        repo,
        tmp_path / "u1_first",
        stage="U1_CONTROL_BRIDGE",
        source="d" * 40,
    )
    _settle_worker_failure(next_stage, "e" * 40)
    with pytest.raises(InputError, match="batch has exhausted"):
        _reserve(
            repo,
            tmp_path / "u1_replay",
            stage="U1_CONTROL_BRIDGE",
            source="e" * 40,
        )
