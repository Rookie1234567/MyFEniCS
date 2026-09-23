"""Minimal V25 input and worker-dispatch contracts."""

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    COARSE_DEGREE_SPEED_PROFILE,
    SETUP_EFFICIENCY_PROFILE,
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


def test_v25_q4_swap_observe_input_is_the_only_nonzero_swap_policy():
    observed = load_and_resolve(
        ROOT / "input/task39extra/v25_q4_ac_swap_observe_h7p5.dat"
    )
    rerun = load_and_resolve(
        ROOT / "input/task39extra/v25_q4_ac_swap_observe_r2_h7p5.dat"
    )
    original = load_and_resolve(ROOT / "input/task39extra/v25_q4_speed_h7p5.dat")
    repeat = load_and_resolve(ROOT / "input/task39extra/v25_q4_ac_repeat_h7p5.dat")
    assert observed.execution["require_zero_swap"] is False
    assert rerun.execution["require_zero_swap"] is False
    assert original.execution["require_zero_swap"] is True
    assert repeat.execution["require_zero_swap"] is True
    for key in (
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
        "solver",
        "output",
    ):
        assert observed.as_jsonable()[key] == original.as_jsonable()[key]
        assert rerun.as_jsonable()[key] == original.as_jsonable()[key]


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


def test_v26_worker_dispatch_uses_v26_summary_contract(monkeypatch, tmp_path):
    specification = load_and_resolve(
        ROOT / "input/task39extra/v26_q4_setup_efficiency_original_h7p5.dat"
    )
    captured = {}

    def fake_runner(payload, run_directory, **kwargs):
        captured.update(kwargs)
        return {"passed": False, "errors": ["dispatch probe"]}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_runner)
    result = dispatch.run_full3d_iterative(
        specification.as_jsonable(), tmp_path, source_sha="s" * 40
    )
    assert result["errors"] == ["dispatch probe"]
    assert captured["coarse_degree"] == 4
    assert captured["allowed_stages"] == ("Q4_ORIGINAL",)
    assert captured["evidence_prefix"] == "v26q4"
    assert captured["profile_identity"] == SETUP_EFFICIENCY_PROFILE
    assert captured["summary_schema"] == "task039extra.v26.worker-summary.v1"
    assert captured["summary_filename"] == (
        "physical_dual_condensed_setup_efficiency_v26_summary.json"
    )
    assert captured["restore_summary_schema"] is True


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


def _v25_ac_swap_observe_auth():
    return {
        "authorization_id": launcher.V25_Q4_AC_SWAP_OBSERVE_AUTHORIZATION_ID,
        "run_id": launcher.V25_Q4_AC_SWAP_OBSERVE_RUN_ID,
        "scope": "user_authorized_swap_observe_repeat",
        "source": launcher.V25_Q4_AC_SWAP_OBSERVE_AUTHORIZATION_SOURCE,
    }


def _v25_ac_swap_observe_r2_auth():
    return {
        "authorization_id": launcher.V25_Q4_AC_SWAP_OBSERVE_R2_AUTHORIZATION_ID,
        "run_id": launcher.V25_Q4_AC_SWAP_OBSERVE_R2_RUN_ID,
        "scope": "user_authorized_swap_observe_r2",
        "source": launcher.V25_Q4_AC_SWAP_OBSERVE_R2_AUTHORIZATION_SOURCE,
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


def test_v25_q4_swap_observe_uses_an_independent_immutable_snapshot(tmp_path):
    ledger_path = _copy_v25_ledger(tmp_path)
    before = ledger_path.read_bytes()
    lease = launcher._reserve_v25_shared_budget(
        tmp_path,
        tmp_path / "results" / "ac-swap-observe",
        source_sha="d" * 40,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start={"monotonic": 1.0},
        time_policy="observe_only",
        authorized_performance_repeat=_v25_ac_swap_observe_auth(),
    )
    after = json.loads(ledger_path.read_text())
    snapshot = ledger_path.with_name(
        launcher.V25_Q4_AC_SWAP_OBSERVE_SNAPSHOT_FILENAME
    )
    attempt = after["stages"]["Q4_ORIGINAL"]["attempts"][-1]
    assert lease["authorized_performance_repeat"]["run_id"] == (
        launcher.V25_Q4_AC_SWAP_OBSERVE_RUN_ID
    )
    assert attempt["authorized_performance_repeat"]["scope"] == (
        "user_authorized_swap_observe_repeat"
    )
    assert after["authorized_performance_repeats"][-1]["run_id"] == (
        launcher.V25_Q4_AC_SWAP_OBSERVE_RUN_ID
    )
    assert snapshot.read_bytes() == before
    assert snapshot.stat().st_mode & 0o777 == 0o444


def test_v25_q4_swap_observe_rejects_duplicate_authorization(tmp_path):
    auth = _v25_ac_swap_observe_auth()
    _copy_v25_ledger(tmp_path)
    for directory_name in ("first", "duplicate"):
        if directory_name == "first":
            launcher._reserve_v25_shared_budget(
                tmp_path,
                tmp_path / "results" / directory_name,
                source_sha="d" * 40,
                stage="Q4_ORIGINAL",
                stage_budget={"workflow_seconds": 43200.0},
                workflow_clock_start={"monotonic": 1.0},
                time_policy="observe_only",
                authorized_performance_repeat=auth,
            )
            continue
        with pytest.raises(InputError, match="authorized performance repeat already consumed"):
            launcher._reserve_v25_shared_budget(
                tmp_path,
                tmp_path / "results" / directory_name,
                source_sha="e" * 40,
                stage="Q4_ORIGINAL",
                stage_budget={"workflow_seconds": 43200.0},
                workflow_clock_start={"monotonic": 2.0},
                time_policy="observe_only",
                authorized_performance_repeat=auth,
            )


def test_v25_q4_swap_observe_r2_is_independent_and_rejects_duplicate(tmp_path):
    _copy_v25_ledger(tmp_path)
    auth = _v25_ac_swap_observe_r2_auth()
    lease = launcher._reserve_v25_shared_budget(
        tmp_path,
        tmp_path / "results" / "r2",
        source_sha="f" * 40,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start={"monotonic": 1.0},
        time_policy="observe_only",
        authorized_performance_repeat=auth,
    )
    ledger_path = launcher._dual_condensed_coarse_degree_v25_shared_ledger_path(
        tmp_path
    )
    ledger = json.loads(ledger_path.read_text())
    snapshot = ledger_path.with_name(
        launcher.V25_Q4_AC_SWAP_OBSERVE_R2_SNAPSHOT_FILENAME
    )
    assert lease["authorized_performance_repeat"] == auth
    assert ledger["authorized_performance_repeats"][-1]["run_id"] == auth["run_id"]
    assert snapshot.read_bytes() != ledger_path.read_bytes()
    assert snapshot.stat().st_mode & 0o777 == 0o444
    with pytest.raises(InputError, match="authorized performance repeat already consumed"):
        launcher._reserve_v25_shared_budget(
            tmp_path,
            tmp_path / "results" / "r2-duplicate",
            source_sha="0" * 40,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start={"monotonic": 2.0},
            time_policy="observe_only",
            authorized_performance_repeat=auth,
        )


def test_v25_watchdog_swap_observation_records_without_bypassing_memory_gate(
    monkeypatch, tmp_path
):
    from benchmarks import subreaper_watchdog

    original_snapshot = subreaper_watchdog.process_tree_snapshot

    def swapped_snapshot(*args, **kwargs):
        row = original_snapshot(*args, **kwargs)
        if row["exit_code"] is None:
            row["swap_bytes"] = 1
        return row

    monkeypatch.setattr(subreaper_watchdog, "process_tree_snapshot", swapped_snapshot)
    monkeypatch.setattr(
        subreaper_watchdog,
        "vmstat_swap_pages",
        lambda: {"pswpin_pages": 0, "pswpout_pages": 0},
    )
    command = [sys.executable, "-c", "import time; time.sleep(.08)"]
    enforced = subreaper_watchdog.supervise(
        command,
        tmp_path / "enforced",
        wall_seconds=2.0,
        interval=0.01,
        grace_seconds=0.1,
        hard_stop_immediate=True,
        stop_on_global_swap=True,
    )
    observed = subreaper_watchdog.supervise(
        command,
        tmp_path / "observed",
        wall_seconds=2.0,
        interval=0.01,
        grace_seconds=0.1,
        hard_stop_immediate=True,
        allow_swap_observation=True,
    )
    assert enforced["classification"] == "RESOURCE_CONTROLLED_STOP"
    assert observed["classification"] == "COMPLETED"
    assert observed["swap_policy"] == "observe_only"
    assert observed["sampled_process_tree_swap_peak_bytes"] == 1
    assert observed["job_swap_activity"] == "observed_process_tree_swap"


def test_v25_watchdog_swap_observation_records_global_activity(monkeypatch, tmp_path):
    from benchmarks import subreaper_watchdog

    original_snapshot = subreaper_watchdog.process_tree_snapshot

    def swapped_snapshot(*args, **kwargs):
        row = original_snapshot(*args, **kwargs)
        if row["exit_code"] is None:
            row["swap_bytes"] = 1
        return row

    swap_calls = 0

    def vmstat():
        nonlocal swap_calls
        swap_calls += 1
        return {
            "pswpin_pages": 0,
            "pswpout_pages": 0 if swap_calls == 1 else 1,
        }

    monkeypatch.setattr(subreaper_watchdog, "process_tree_snapshot", swapped_snapshot)
    monkeypatch.setattr(subreaper_watchdog, "vmstat_swap_pages", vmstat)
    result = subreaper_watchdog.supervise(
        [sys.executable, "-c", "import time; time.sleep(.08)"],
        tmp_path / "global-growth",
        wall_seconds=2.0,
        interval=0.01,
        grace_seconds=0.1,
        hard_stop_immediate=True,
        allow_swap_observation=True,
    )
    assert result["classification"] == "COMPLETED"
    assert result["global_swap_activity"]["delta"]["pswpout_pages"] == 1
    assert result["job_swap_activity"] == "observed_process_tree_swap"


@pytest.mark.parametrize(
    "failure", ["physical_memory", "monitoring"],
)
def test_v25_swap_observation_keeps_physical_safety_gates(
    monkeypatch, tmp_path, failure
):
    from benchmarks import subreaper_watchdog

    original_snapshot = subreaper_watchdog.process_tree_snapshot
    original_envelope = subreaper_watchdog.memory_envelope
    envelope_calls = 0

    def snapshot(*args, **kwargs):
        row = original_snapshot(*args, **kwargs)
        if row["exit_code"] is None:
            row["swap_bytes"] = 1
            if failure == "monitoring":
                row["all_status_readable"] = False
        return row

    def envelope(policy=subreaper_watchdog.LEGACY_MEMORY_POLICY):
        nonlocal envelope_calls
        envelope_calls += 1
        row = original_envelope(policy)
        if failure == "physical_memory" and envelope_calls >= 2:
            row["effective_available_bytes"] = row["reserve_bytes"] - 1
        return row

    monkeypatch.setattr(subreaper_watchdog, "process_tree_snapshot", snapshot)
    monkeypatch.setattr(subreaper_watchdog, "memory_envelope", envelope)
    monkeypatch.setattr(
        subreaper_watchdog,
        "vmstat_swap_pages",
        lambda: {"pswpin_pages": 0, "pswpout_pages": 0},
    )
    result = subreaper_watchdog.supervise(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        tmp_path / failure,
        wall_seconds=2.0,
        interval=0.01,
        grace_seconds=0.1,
        hard_stop_immediate=True,
        allow_swap_observation=True,
    )
    assert result["classification"] == (
        "RESOURCE_CONTROLLED_STOP"
        if failure == "physical_memory"
        else "MONITORING_FAILED"
    )
    assert result["descendants_cleared"] is True


def test_v25_worker_resource_facts_keep_observed_swap_outside_observe_gate(tmp_path):
    from src.runners.physical_p4_schur_v14 import _v14_resource_facts

    path = tmp_path / "worker_resources.jsonl"
    row = {
        "rss_bytes": 100,
        "swap_bytes": 1,
        "memory_envelope": {
            "effective_available_bytes": 1000,
            "reserve_bytes": 100,
        },
        "inventory_memory_cap_bytes": None,
        "inventory_used_bytes": 0,
        "workspace_live_bytes": 0,
        "all_status_readable": True,
        "pss_bytes": 100,
        "pss_all_readable": True,
        "launch_cap_bytes": 200,
        "inventory_peak_bytes": 0,
        "workspace_peak_bytes": 0,
        "timestamp_ns": 1,
        "label": "synthetic",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    runtime = SimpleNamespace(
        resources_path=path,
        inventory_cap=None,
        physical_memory_pressure=True,
        workspace_cap=None,
        require_zero_swap=False,
    )
    facts = _v14_resource_facts(runtime)
    assert facts["zero_swap"] is False
    assert facts["swap_gate_enforced"] is False
    assert facts["gate"] is True
    strict_facts = _v14_resource_facts(
        SimpleNamespace(
            resources_path=path,
            inventory_cap=None,
            physical_memory_pressure=True,
            workspace_cap=None,
            require_zero_swap=True,
        )
    )
    assert strict_facts["zero_swap"] is False
    assert strict_facts["swap_gate_enforced"] is True
    assert strict_facts["gate"] is False


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
