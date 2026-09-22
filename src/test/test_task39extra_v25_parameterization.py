"""Minimal V25 input and worker-dispatch contracts."""

import json
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    COARSE_DEGREE_SPEED_PROFILE,
    profile_facts,
)
from src.io.run_specification import thaw
from src.runners import task038_full3d_iterative as dispatch
from src.runners import task038_launcher as launcher


ROOT = Path(__file__).resolve().parents[2]


def test_v25_inputs_bind_direct_coarse_degree_to_each_stage():
    expected = {
        "v25_q4_speed_h7p5.dat": ("Q4_ORIGINAL", 4),
        "v25_q3_speed_h7p5.dat": ("Q3_ORIGINAL", 3),
        "v25_q2_speed_h7p5.dat": ("Q2_ORIGINAL", 2),
    }
    facts = profile_facts(COARSE_DEGREE_SPEED_PROFILE)
    for name, (stage, degree) in expected.items():
        specification = load_and_resolve(ROOT / "input/task39extra" / name)
        assert specification.solver["preconditioner"] == COARSE_DEGREE_SPEED_PROFILE
        assert specification.solver["stage"] == stage
        assert specification.solver["coarse_degree"] == degree
        assert specification.solver["physical_operator_backend"] == (
            "isotropic_sum_factorized_n1e_v26"
        )
        assert specification.solver["h6_backend_rule"] == (
            "isotropic_sum_factorized_n1e_v26_apply_and_power10"
        )
        assert specification.solver["thread_contract"] == "mpi1_omp1_blas1_v25"
        assert specification.as_jsonable()["derived"]["physical_intermediate_profile"] == thaw(facts)


def test_v24_resolved_identity_does_not_gain_v25_backend_fields():
    specification = load_and_resolve(
        ROOT / "input/task39extra/v24_laptop_speed_original_h7p5.dat"
    )
    assert all(
        key not in specification.solver
        for key in (
            "physical_operator_backend",
            "h6_backend_rule",
            "thread_contract",
        )
    )


def test_v25_worker_dispatch_keeps_explicit_stage_degree(monkeypatch, tmp_path):
    specification = load_and_resolve(
        ROOT / "input/task39extra/v25_q3_speed_h7p5.dat"
    )
    captured = {}

    def fake_runner(payload, run_directory, **kwargs):
        captured.update(kwargs)
        captured["payload"] = payload
        captured["run_directory"] = run_directory
        return {"passed": False, "errors": ["dispatch probe"]}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_runner)
    result = dispatch.run_full3d_iterative(
        specification.as_jsonable(), tmp_path, source_sha="s" * 40
    )
    assert result["errors"] == ["dispatch probe"]
    assert captured["coarse_degree"] == 3
    assert captured["allowed_stages"] == (
        "Q4_ORIGINAL",
        "Q3_ORIGINAL",
        "Q2_ORIGINAL",
    )
    assert captured["evidence_prefix"] == "v25q3"
    assert captured["profile_identity"] == COARSE_DEGREE_SPEED_PROFILE


def test_v25_public_launcher_accepts_observe_only_policy(capsys):
    from scripts.run_case import main as run_case_main

    assert run_case_main(
        [
            str(ROOT / "input/task39extra/v25_q4_speed_h7p5.dat"),
            "--validate-only",
            "--v14-time-policy",
            "observe_only",
        ]
    ) == 0
    capsys.readouterr()


def _copy_v25_ledger(tmp_path):
    target = (
        tmp_path
        / "benchmarks/artifacts/task39extra/coarse_degree_speed_v25/"
        "review_v23_a6_h6_speed_and_coarse_degree/shared_workflow_ledger.json"
    )
    target.parent.mkdir(parents=True)
    settled_attempt = {
        "attempt": 1,
        "source_sha": "c" * 40,
        "run_directory": str(tmp_path / "historical-q4"),
        "status": "worker_exit0",
        "watchdog_classification": "COMPLETED",
        "actual_elapsed_seconds": 3.0,
        "settled_seconds": 3.0,
        "time_policy": "observe_only",
        "reserved_seconds": 43200.0,
    }
    ledger = {
        "schema": "task039extra.v25.shared-workflow-ledger.v1",
        "batch_identity": "review_v23_a6_h6_speed_and_coarse_degree",
        "total_budget_seconds": 129600.0,
        "elapsed_seconds": 3.0,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [],
        "fresh_worker_count": 3,
        "source_attempts": [
            {"stage": "Q4_ORIGINAL", "source_sha": "c" * 40, "attempt": 1}
        ],
        "stages": {
            "Q4_ORIGINAL": {
                "active_attempt": None,
                "attempts": [settled_attempt],
            },
            "Q3_ORIGINAL": {"active_attempt": None, "attempts": []},
            "Q2_ORIGINAL": {"active_attempt": None, "attempts": []},
        },
        "unique_bug_replay_count": 0,
        "replay_policy": "one independent original run per q stage",
        "allowed_stages": ["Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL"],
        "cross_case_recycling": False,
        "coarse_degree_by_stage": {"Q4_ORIGINAL": 4, "Q3_ORIGINAL": 3, "Q2_ORIGINAL": 2},
    }
    target.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")
    return target


def _v25_ac_repeat_auth():
    return {
        "authorization_id": launcher.V25_Q4_AC_REPEAT_AUTHORIZATION_ID,
        "run_id": launcher.V25_Q4_AC_REPEAT_RUN_ID,
        "scope": "user_authorized_performance_repeat",
        "source": launcher.V25_Q4_AC_REPEAT_AUTHORIZATION_SOURCE,
    }


def _reserve_v25_ac_repeat(tmp_path, *, source_sha="d" * 40):
    _copy_v25_ledger(tmp_path)
    return launcher._reserve_v25_shared_budget(
        tmp_path,
        tmp_path / "results" / "ac-repeat",
        source_sha=source_sha,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start={"monotonic": 1.0},
        time_policy="observe_only",
        authorized_performance_repeat=_v25_ac_repeat_auth(),
    )


def test_v25_q4_ac_repeat_authorization_is_one_fresh_non_replay(tmp_path):
    ledger_path = _copy_v25_ledger(tmp_path)
    before = ledger_path.read_bytes()
    lease = launcher._reserve_v25_shared_budget(
        tmp_path,
        tmp_path / "results" / "ac-repeat",
        source_sha="d" * 40,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start={"monotonic": 1.0},
        time_policy="observe_only",
        authorized_performance_repeat=_v25_ac_repeat_auth(),
    )
    after = json.loads(ledger_path.read_text())
    attempt = after["stages"]["Q4_ORIGINAL"]["attempts"][-1]
    snapshot = ledger_path.with_name(launcher.V25_Q4_AC_REPEAT_SNAPSHOT_FILENAME)
    assert lease["replay"] is False
    assert attempt["replay"] is False
    assert attempt["authorized_performance_repeat"]["run_id"] == launcher.V25_Q4_AC_REPEAT_RUN_ID
    assert after["unique_bug_replay_count"] == 0
    assert after["elapsed_seconds"] == 3.0
    assert after["stages"]["Q4_ORIGINAL"]["attempts"][0]["source_sha"] == "c" * 40
    assert len(after["authorized_performance_repeats"]) == 1
    assert snapshot.read_bytes() == before
    assert snapshot.stat().st_mode & 0o777 == 0o444


def test_v25_q4_ac_repeat_rejects_duplicate_authorization(tmp_path):
    _reserve_v25_ac_repeat(tmp_path)
    with pytest.raises(InputError, match="authorized performance repeat already consumed"):
        launcher._reserve_v25_shared_budget(
            tmp_path,
            tmp_path / "results" / "ac-repeat-duplicate",
            source_sha="e" * 40,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start={"monotonic": 2.0},
            time_policy="observe_only",
            authorized_performance_repeat=_v25_ac_repeat_auth(),
        )


def test_v25_old_q4_path_keeps_hash_bound_replay_gate(tmp_path):
    _copy_v25_ledger(tmp_path)
    with pytest.raises(InputError, match="repair replay requires hash-bound bug evidence"):
        launcher._reserve_v25_shared_budget(
            tmp_path,
            tmp_path / "results" / "old-path",
            source_sha="f" * 40,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start={"monotonic": 3.0},
            time_policy="observe_only",
        )
