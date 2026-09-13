"""Targeted guards for the reviewed V15 R0/R1 recovery boundary."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.input_loader import InputError
from src.runners import physical_p4_schur_v14 as worker
from src.runners import task038_launcher as launcher
from src.runners.physical_v14_budget import read_v14_effective_budget


def _r0_fixture(tmp_path: Path, *, ledger_sha: str, status: str = "R0_PASS", repo=None):
    repo = repo or (tmp_path / "repo")
    directory = (
        repo / "benchmarks/artifacts/task39extra/p4_schur_v14/review_v15"
        / "r0_recheck_fixture"
    )
    directory.mkdir(parents=True, exist_ok=True)
    raw_bytes = b'{"fixture":"r0"}\n'
    kernel_bytes = b'{"fixture":"kernel"}\n'
    (directory / "r0_recheck.json").write_bytes(raw_bytes)
    (directory / "root_current_kernel_check.json").write_bytes(kernel_bytes)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    kernel_sha = hashlib.sha256(kernel_bytes).hexdigest()
    prefix = Path("benchmarks/artifacts/task39extra/p4_schur_v14/review_v15")
    accepted = {
        "schema": launcher.V15_R0_ACCEPTED_SCHEMA,
        "status": status,
        "gates": {
            "process_absence": True, "io_probe": True,
            "ledger_identity": True, "host_storage": True,
            "abi": True, "mounts_and_space": True,
        },
        "source": {
            "branch": "task39extra", "head": launcher.V15_R0_SOURCE_SHA,
            "status_porcelain": "",
        },
        "ledger": {
            "sha256_before": ledger_sha, "sha256_after": ledger_sha,
            "unchanged": True, "new_ledger_mutations": 0,
        },
        "raw_report": {"path": str(prefix / "r0_recheck_fixture/r0_recheck.json"), "sha256": raw_sha},
        "historical_log_boundary": {"current_kernel_check": {
            "path": str(prefix / "r0_recheck_fixture/root_current_kernel_check.json"),
            "sha256": kernel_sha,
        }},
    }
    accepted_bytes = (
        json.dumps(accepted, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    accepted_path = directory / "r0_recheck_accepted.json"
    accepted_path.write_bytes(accepted_bytes)
    return repo, accepted_path, hashlib.sha256(accepted_bytes).hexdigest(), raw_sha, kernel_sha


def _patch_fixture_hashes(monkeypatch, accepted_sha, raw_sha, kernel_sha):
    monkeypatch.setattr(launcher, "V15_R0_ACCEPTED_SHA256", accepted_sha)
    monkeypatch.setattr(launcher, "V15_R0_RAW_REPORT_SHA256", raw_sha)
    monkeypatch.setattr(launcher, "V15_R0_KERNEL_SHA256", kernel_sha)


def test_v15_r0_accepts_only_the_fixed_hash_bound_record(tmp_path, monkeypatch):
    repo, accepted, accepted_sha, raw_sha, kernel_sha = _r0_fixture(
        tmp_path, ledger_sha=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256
    )
    _patch_fixture_hashes(monkeypatch, accepted_sha, raw_sha, kernel_sha)
    facts = launcher._v15_r0_evidence(
        accepted, repo_root=repo,
        expected_ledger_sha256=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256,
    )
    assert facts["sha256"] == accepted_sha
    assert facts["raw_report_sha256"] == raw_sha


def test_v15_r0_rejects_mapping_tampering_and_blocked_status(tmp_path, monkeypatch):
    with pytest.raises(InputError, match="fixed JSON path"):
        launcher._v15_r0_evidence(
            {}, repo_root=tmp_path,
            expected_ledger_sha256=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256,
        )
    repo, accepted, accepted_sha, raw_sha, kernel_sha = _r0_fixture(
        tmp_path / "tamper", ledger_sha=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256
    )
    _patch_fixture_hashes(monkeypatch, accepted_sha, raw_sha, kernel_sha)
    (accepted.parent / "r0_recheck.json").write_bytes(b"tampered\n")
    with pytest.raises(InputError, match="bound file hash mismatch"):
        launcher._v15_r0_evidence(
            accepted, repo_root=repo,
            expected_ledger_sha256=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256,
        )
    blocked_repo, blocked, blocked_sha, blocked_raw, blocked_kernel = _r0_fixture(
        tmp_path / "blocked",
        ledger_sha=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256,
        status="INFRASTRUCTURE_BLOCKED",
    )
    _patch_fixture_hashes(monkeypatch, blocked_sha, blocked_raw, blocked_kernel)
    with pytest.raises(InputError, match="accepted as R0_PASS"):
        launcher._v15_r0_evidence(
            blocked, repo_root=blocked_repo,
            expected_ledger_sha256=launcher.V15_Q0_EIO_ORIGINAL_LEDGER_SHA256,
        )


def test_effective_budget_keeps_policy_allowance_and_active_reservation_separate():
    ledger = {
        "total_budget_seconds": 43_200.0, "elapsed_seconds": 10.0,
        "conservative_allowance_seconds": 3.1,
        "policy_debits": [{"recovery_id": "V15_Q0_EIO_ONCE", "seconds": 600.0}],
        "stages": {"Q0_CORE": {"active_attempt": 0, "attempts": [{"reserved_seconds": 600.0}]}},
    }
    effective = read_v14_effective_budget(ledger)
    assert effective["measured_elapsed_seconds"] == 10.0
    assert effective["policy_debit_seconds"] == 600.0
    assert effective["conservative_allowance_seconds"] == 3.1
    assert effective["active_reservations_seconds"] == 600.0
    assert effective["remaining_seconds"] == pytest.approx(41_986.9)


def _recovery_fixture(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    old_run = tmp_path / "old_q0"
    old_attempt = {
        "attempt": 1, "source_sha": launcher.V15_Q0_EIO_SOURCE_SHA,
        "run_directory": str(old_run), "status": "RESERVED",
        "reserved_seconds": 600.0,
        "workflow_clock_start": {"monotonic": 0.0, "boottime": 0.0, "utc_ns": 0},
    }
    ledger = {
        "schema": "task039extra.v14.shared-workflow-ledger.v1",
        "batch_identity": "review_v14", "total_budget_seconds": 43_200.0,
        "elapsed_seconds": 0.0, "fresh_worker_count": 1,
        "unique_bug_replay_count": 0, "source_attempts": [],
        "stages": {"Q0_CORE": {"active_attempt": 0, "attempts": [old_attempt]}},
    }
    ledger_path = repo / "shared_workflow_ledger.json"
    original_bytes = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ledger_path.write_bytes(original_bytes)
    ledger_sha = hashlib.sha256(original_bytes).hexdigest()
    evidence = _r0_fixture(tmp_path / "evidence", ledger_sha=ledger_sha, repo=repo)
    return repo, ledger_path, old_attempt, ledger_sha, evidence


def _prepare_recovery(monkeypatch, repo, ledger_path, evidence):
    monkeypatch.setattr(launcher, "_v14_shared_ledger_path", lambda _root: ledger_path)
    monkeypatch.setattr(launcher, "_source_sha", lambda _root: "b" * 40)
    monkeypatch.setattr(launcher, "_git_argv", lambda *_args: ["true"])
    _patch_fixture_hashes(monkeypatch, evidence[2], evidence[3], evidence[4])


def test_recovery_entrypoint_is_idempotent_and_preserves_old_attempt(tmp_path, monkeypatch):
    repo, ledger_path, old_attempt, ledger_sha, evidence = _recovery_fixture(tmp_path)
    _prepare_recovery(monkeypatch, repo, ledger_path, evidence)
    old_run = old_attempt["run_directory"]
    first = launcher.recover_v15_q0_eio_once(
        repo, r0_evidence=evidence[1], expected_run_directory=old_run,
        expected_original_ledger_sha256=ledger_sha,
    )
    assert first["applied"] is True
    current = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert current["elapsed_seconds"] == launcher.V15_R0_MEASURED_COLLECTION_SECONDS
    assert current["conservative_allowance_seconds"] == launcher.V15_R0_DERIVED_UPPER_SECONDS
    assert current["stages"]["Q0_CORE"]["attempts"] == [old_attempt]
    event = current["infrastructure_recoveries"][0]
    assert current["predecessor_ledger_sha256"] == ledger_sha
    assert event["actual_elapsed_seconds"] is None
    assert event["historical_terminal_coverage"] == "incomplete"
    assert current["policy_debits"] == [{
        "recovery_id": launcher.V15_Q0_EIO_RECOVERY_ID,
        "seconds": 600.0, "basis": launcher.V15_Q0_EIO_ACCOUNTING_BASIS,
        "actual_elapsed_seconds": None,
    }]
    assert first["effective_budget"]["remaining_seconds"] == pytest.approx(
        43_200.0 - 600.0 - launcher.V15_R0_TOTAL_COLLECTION_SECONDS
    )

    run = tmp_path / "new_q0"
    run.mkdir()
    lease = launcher._reserve_v14_shared_budget(
        repo, run, source_sha="b" * 40, stage="Q0_CORE",
        stage_budget={"workflow_seconds": 600.0},
        workflow_clock_start={"monotonic": 1.0, "boottime": 1.0, "utc_ns": 1_000_000_000},
    )
    active_bytes = ledger_path.read_bytes()
    second = launcher.recover_v15_q0_eio_once(
        repo, r0_evidence=evidence[1], expected_run_directory=old_run,
        expected_original_ledger_sha256=ledger_sha,
    )
    assert second["already_applied"] is True
    assert ledger_path.read_bytes() == active_bytes
    assert json.loads(active_bytes)["stages"]["Q0_CORE"]["active_attempt"] == lease["attempt_index"]
    launcher._settle_v14_shared_budget(
        lease, status="worker_exit0", authority=None,
        parent_interval={"budget_seconds": 12.0},
        parent_clock_end={"monotonic": 13.0, "boottime": 13.0, "utc_ns": 13_000_000_000},
    )
    settled_bytes = ledger_path.read_bytes()
    assert launcher.recover_v15_q0_eio_once(
        repo, r0_evidence=evidence[1], expected_run_directory=old_run,
        expected_original_ledger_sha256=ledger_sha,
    )["already_applied"] is True
    assert ledger_path.read_bytes() == settled_bytes
    with pytest.raises(InputError, match="exhausted"):
        launcher._reserve_v14_shared_budget(
            repo, tmp_path / "third_q0", source_sha="c" * 40, stage="Q0_CORE",
            stage_budget={"workflow_seconds": 600.0},
            workflow_clock_start={"monotonic": 14.0, "boottime": 14.0, "utc_ns": 14_000_000_000},
        )


def test_recovery_can_retry_after_predecessor_publish_failure(tmp_path, monkeypatch):
    repo, ledger_path, _old_attempt, ledger_sha, evidence = _recovery_fixture(tmp_path)
    _prepare_recovery(monkeypatch, repo, ledger_path, evidence)
    original_writer = launcher._write_v14_ledger
    monkeypatch.setattr(
        launcher, "_write_v14_ledger",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic publish failure")),
    )
    with pytest.raises(OSError, match="synthetic publish failure"):
        launcher.recover_v15_q0_eio_once(
            repo, r0_evidence=evidence[1], expected_run_directory=str(tmp_path / "old_q0"),
            expected_original_ledger_sha256=ledger_sha,
        )
    monkeypatch.setattr(launcher, "_write_v14_ledger", original_writer)
    result = launcher.recover_v15_q0_eio_once(
        repo, r0_evidence=evidence[1], expected_run_directory=str(tmp_path / "old_q0"),
        expected_original_ledger_sha256=ledger_sha,
    )
    assert result["applied"] is True


def test_recovery_rejects_live_old_q0_or_original_hash_mismatch(tmp_path, monkeypatch):
    repo, ledger_path, _old_attempt, ledger_sha, evidence = _recovery_fixture(tmp_path)
    _prepare_recovery(monkeypatch, repo, ledger_path, evidence)
    monkeypatch.setattr(launcher, "_v15_q0_live_processes", lambda _path: [{"pid": 123}])
    with pytest.raises(InputError, match="still live"):
        launcher.recover_v15_q0_eio_once(
            repo, r0_evidence=evidence[1], expected_run_directory=str(tmp_path / "old_q0"),
            expected_original_ledger_sha256=ledger_sha,
        )
    monkeypatch.setattr(launcher, "_v15_q0_live_processes", lambda _path: [])
    with pytest.raises(InputError, match="hash mismatch"):
        launcher.recover_v15_q0_eio_once(
            repo, r0_evidence=evidence[1], expected_run_directory=str(tmp_path / "old_q0"),
            expected_original_ledger_sha256="0" * 64,
        )


def test_q6_reports_historical_unknown_without_treating_admin_closure_as_active(tmp_path, monkeypatch):
    old_attempt = {
        "attempt": 1, "source_sha": launcher.V15_Q0_EIO_SOURCE_SHA,
        "run_directory": str(tmp_path / "old_q0"), "status": "RESERVED",
        "reserved_seconds": 600.0,
    }
    event = {
        "recovery_id": launcher.V15_Q0_EIO_RECOVERY_ID,
        "old_attempt_index": 0, "old_attempt": copy.deepcopy(old_attempt),
        "actual_elapsed_seconds": None, "historical_terminal_coverage": "incomplete",
    }
    ledger = {
        "batch_identity": "review_v14", "total_budget_seconds": 43_200.0,
        "elapsed_seconds": 0.0, "policy_debits": [{"seconds": 600.0}],
        "stages": {"Q0_CORE": {"active_attempt": None, "attempts": [old_attempt]}},
        "infrastructure_recoveries": [event],
    }
    path = tmp_path / "shared.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setattr(worker, "_save_packet", lambda *args, **kwargs: {"path": "packet"})
    runtime = SimpleNamespace(_ledger_path=path, directory=tmp_path, marker=lambda *args: None)
    result = worker._q6_finalize(runtime)
    q0 = result["stages"]["Q0_CORE"]
    assert q0["status"] == "administratively_closed"
    assert q0["historical_unknown_cost"] is True
    assert q0["historical_recovery_events"][0]["actual_elapsed_seconds"] is None
    assert result["ledger"]["historical_unknown_cost"] is True
    assert q0["status"] != "unsettled_attempt"
