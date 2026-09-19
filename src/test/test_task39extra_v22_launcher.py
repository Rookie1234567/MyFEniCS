"""Bounded V22 input, lease, and existing-worker-dispatch contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
    ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)
from src.runners import task038_launcher as launcher
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]
V21_CASE = ROOT / "input/task39extra/v21_z3_original_h7p5.dat"
V22_CASE = ROOT / "input/task39extra/v22_b_capacity_original_h7p5.dat"


def _clock(seconds: float = 0.0) -> dict[str, float]:
    return {
        "monotonic_seconds": float(seconds),
        "boottime_seconds": float(seconds),
        "utc_seconds": float(seconds),
    }


def _copy_v21_ledger(destination: Path) -> bytes:
    # Keep the unit test independent of ignored historical artifacts. The
    # production hash gate is patched to this fixture's bytes by each caller.
    ledger = {
        "schema": "task039extra.v21.shared-workflow-ledger.v1",
        "batch_identity": "review_v21_dual_condensed_geometry_h7p5",
        "total_budget_seconds": 43200.0,
        "elapsed_seconds": 12.5,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [
            {"id": "known-history", "seconds": 3.0, "actual_elapsed_seconds": 3.0}
        ],
        "fresh_worker_count": 2,
        "source_attempts": [],
        "stages": {
            "Z2_NOTCH_H10": {
                "active_attempt": None,
                "attempts": [
                    {
                        "status": "worker_exit0",
                        "reserved_seconds": 43200.0,
                        "settled_seconds": 12.5,
                        "actual_elapsed_seconds": 12.5,
                    }
                ],
            },
            "Z3_ORIGINAL_H7P5": {
                "active_attempt": None,
                "attempts": [
                    {
                        "status": "WORKER_FAILED",
                        "reserved_seconds": 43200.0,
                        "settled_seconds": None,
                        "actual_elapsed_seconds": None,
                    }
                ],
            },
        },
        "unique_bug_replay_count": 0,
        "replay_policy": "one evidence-bound implementation-bug replay",
        "predecessors": {},
    }
    payload = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return payload


def test_v22_dat_preserves_original_b_identity_and_reserves_one_independent_attempt(
    tmp_path: Path, capsys, monkeypatch
):
    v21 = load_and_resolve(V21_CASE)
    v22 = load_and_resolve(V22_CASE)

    # The new profile and memory policy are the only solver-side changes; the
    # resolved physical/mesh inputs and their compatibility identity remain B.
    for section in (
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
        "execution",
        "output",
    ):
        assert getattr(v22, section) == getattr(v21, section)
    assert v22.physical_model_sha256 == v21.physical_model_sha256
    assert v22.solver["preconditioner"] == CAPACITY_DUAL_CELL_CONDENSED_PROFILE
    assert v22.solver["stage"] == launcher.V22_STAGE
    assert (
        v22.derived["physical_intermediate_profile"]["resources"]["time_policy"]
        == "observe_only"
    )
    assert run_case_main(
        [str(V22_CASE), "--validate-only", "--v14-time-policy", "observe_only"]
    ) == 0
    capsys.readouterr()

    v21_source = launcher._dual_condensed_robustness_v21_shared_ledger_path(tmp_path)
    v21_bytes = _copy_v21_ledger(v21_source)
    monkeypatch.setattr(
        launcher,
        "V22_PREDECESSOR_V21_LEDGER_SHA256",
        hashlib.sha256(v21_bytes).hexdigest(),
    )
    v22_path = launcher._dual_condensed_capacity_v22_shared_ledger_path(tmp_path)
    stage_budget = profile_facts(CAPACITY_DUAL_CELL_CONDENSED_PROFILE)["resources"][
        "stage_budgets"
    ][launcher.V22_STAGE]
    lease = launcher._reserve_v22_shared_budget(
        tmp_path,
        tmp_path / "v22-first",
        source_sha="a" * 40,
        stage=launcher.V22_STAGE,
        stage_budget=stage_budget,
        workflow_clock_start=_clock(),
        time_policy="observe_only",
    )
    ledger = json.loads(v22_path.read_text(encoding="utf-8"))
    historical = json.loads(v21_source.read_text(encoding="utf-8"))
    assert lease["path"] == str(v22_path)
    assert ledger["batch_identity"] == launcher.V22_BATCH_IDENTITY
    assert ledger["allowed_stages"] == [launcher.V22_STAGE]
    assert ledger["unique_bug_replay_count"] == 0
    assert ledger["predecessors"]["v21"]["read_only"] is True
    assert ledger["predecessors"]["v21"]["historical_ledger_snapshot"] == historical
    assert v21_source.read_bytes() == v21_bytes

    with pytest.raises(InputError, match="unsettled"):
        launcher._reserve_v22_shared_budget(
            tmp_path,
            tmp_path / "v22-second-before-settle",
            source_sha="b" * 40,
            stage=launcher.V22_STAGE,
            stage_budget=stage_budget,
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )
    launcher._settle_v14_shared_budget(
        lease,
        status="WORKER_FAILED",
        authority=None,
        parent_interval={"budget_seconds": 1.0},
        parent_clock_end=_clock(1.0),
    )
    with pytest.raises(InputError, match="replay are disabled"):
        launcher._reserve_v22_shared_budget(
            tmp_path,
            tmp_path / "v22-second-after-settle",
            source_sha="b" * 40,
            stage=launcher.V22_STAGE,
            stage_budget=stage_budget,
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )
    with pytest.raises(InputError, match="only Z3_ORIGINAL_H7P5"):
        launcher._reserve_v22_shared_budget(
            tmp_path,
            tmp_path / "v22-wrong-stage",
            source_sha="c" * 40,
            stage="Z2_NOTCH_H10",
            stage_budget=stage_budget,
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )


def test_v22_launcher_entry_uses_new_lease_and_keeps_v21_ledger_read_only(
    tmp_path: Path, monkeypatch
):
    specification = load_and_resolve(V22_CASE)
    v21_destination = launcher._dual_condensed_robustness_v21_shared_ledger_path(
        tmp_path
    )
    v21_bytes = _copy_v21_ledger(v21_destination)
    monkeypatch.setattr(
        launcher,
        "V22_PREDECESSOR_V21_LEDGER_SHA256",
        hashlib.sha256(v21_bytes).hexdigest(),
    )
    v22_path = launcher._dual_condensed_capacity_v22_shared_ledger_path(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_dual_condensed_robustness_v21_shared_ledger_path",
        lambda _repo_root: v21_destination,
    )
    monkeypatch.setattr(
        launcher,
        "_dual_condensed_capacity_v22_shared_ledger_path",
        lambda _repo_root: v22_path,
    )
    run_directory = tmp_path / "launcher-run"

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir()
        return run_directory

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
    monkeypatch.setattr(
        launcher,
        "_reserve_v21_shared_budget",
        lambda *_args, **_kwargs: pytest.fail("V22 must not use the V21 lease"),
    )
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda *_args, **_kwargs: {
            "source_sha": "a" * 40,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )

    from benchmarks import subreaper_watchdog

    captured = {}

    def fake_supervise(argv, *_args, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = dict(kwargs)
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "zero_supported_by_zero_global_activity",
            "launch_envelope": {},
            "memory_scope": "synthetic mock process tree",
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    result = launcher.launch_specification(
        specification,
        source_sha="a" * 40,
        v14_time_policy="observe_only",
    )

    assert result["result_classification"] == "worker_exit0"
    assert "src.runners.task038_input_worker" in captured["argv"]
    watchdog_kwargs = captured["kwargs"]
    assert watchdog_kwargs["tree_cap_bytes"] == 8 * 1024**3
    assert watchdog_kwargs["time_policy"] == "observe_only"
    assert watchdog_kwargs["stop_on_global_swap"] is True
    assert watchdog_kwargs["worker_environment"] == {
        "PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH": str(v22_path),
        "PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX": "0",
    }
    ledger = json.loads(v22_path.read_text(encoding="utf-8"))
    assert ledger["batch_identity"] == launcher.V22_BATCH_IDENTITY
    assert ledger["stages"][launcher.V22_STAGE]["active_attempt"] is None
    assert ledger["stages"][launcher.V22_STAGE]["attempts"][0]["status"] == "worker_exit0"
    assert v21_destination.read_bytes() == v21_bytes


def test_v22_worker_dispatch_selects_existing_capacity_worker(monkeypatch, tmp_path):
    payload = load_and_resolve(V22_CASE).as_jsonable()
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as worker

    captured = {}

    def fake_capacity_worker(*_args, **kwargs):
        captured.update(kwargs)
        return {"passed": False, "errors": ["mock capacity worker"], "summary": None}

    monkeypatch.setattr(worker, "_run_physical_dual_cell_condensed_lowmem", fake_capacity_worker)
    monkeypatch.setattr(worker, "v22_capacity_context", lambda: {"mock": True})

    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="full3d_iterative",
        output_directory=tmp_path,
        expected_source_sha="a" * 40,
    )

    assert status == 4
    assert errors == ["mock capacity worker"]
    assert captured["profile_identity"] == CAPACITY_DUAL_CELL_CONDENSED_PROFILE
    assert captured["allowed_stages"] == (launcher.V22_STAGE,)
    assert captured["batch_identity"] == launcher.V22_BATCH_IDENTITY
    assert captured["evidence_prefix"] == "v22"
    assert captured["save_complete_field_packet"] is True
    assert captured["capacity_trial"] is True


def test_v22_rejects_mutated_read_only_v21_ledger(tmp_path, monkeypatch):
    destination = launcher._dual_condensed_robustness_v21_shared_ledger_path(tmp_path)
    original = _copy_v21_ledger(destination)
    mutated = json.loads(original.decode("utf-8"))
    mutated["elapsed_seconds"] = float(mutated["elapsed_seconds"]) + 1.0
    destination.write_text(json.dumps(mutated), encoding="utf-8")
    monkeypatch.setattr(
        launcher,
        "V22_PREDECESSOR_V21_LEDGER_SHA256",
        hashlib.sha256(original).hexdigest(),
    )
    with pytest.raises(InputError, match="predecessor V21 ledger hash changed"):
        launcher._reserve_v22_shared_budget(
            tmp_path,
            tmp_path / "tampered-v22",
            source_sha="a" * 40,
            stage=launcher.V22_STAGE,
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )


def test_v21_default_profile_contract_remains_unchanged():
    specification = load_and_resolve(V21_CASE)
    facts = profile_facts(ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE)
    assert specification.solver["preconditioner"] == ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE
    assert facts["resources"]["time_policy"] == "observe_only"
    assert set(facts["resources"]["stage_budgets"]) == {
        "Z2_NOTCH_H10",
        "Z3_ORIGINAL_H7P5",
        "Z4_NOTCH_H7P5",
    }
    assert specification.derived["v21_identity"]["physical_hash_projection"] == (
        "compatibility_projection_v5_reference"
    )
