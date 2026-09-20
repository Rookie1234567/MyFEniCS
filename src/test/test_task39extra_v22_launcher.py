"""Bounded V22 input, lease, and existing-worker-dispatch contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
    PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE,
    PHYSICAL_MEMORY_POLICY_V23,
    V23_QUALIFIED_JIT_CACHE_ORIGIN,
    V23_QUALIFIED_JIT_CACHE_SOURCE,
    V23_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS,
    ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)
from src.runners import task038_launcher as launcher
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]
V21_CASE = ROOT / "input/task39extra/v21_z3_original_h7p5.dat"
V22_CASE = ROOT / "input/task39extra/v22_b_capacity_original_h7p5.dat"
V23_CASE = ROOT / "input/task39extra/v23_b_physical_memory_original_h7p5.dat"


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


def _copy_v22_ledger(destination: Path) -> bytes:
    """Small predecessor fixture; production V22 history stays ignored/read-only."""

    ledger = {
        "schema": "task039extra.v22.shared-workflow-ledger.v1",
        "batch_identity": "review_v22_original_b_capacity_trial",
        "total_budget_seconds": 43200.0,
        "elapsed_seconds": 17.25,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [
            {"id": "known-v22", "seconds": 4.5, "actual_elapsed_seconds": 4.5}
        ],
        "fresh_worker_count": 1,
        "source_attempts": [],
        "stages": {
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
            }
        },
        "unique_bug_replay_count": 0,
        "replay_policy": "one original B attempt; no automatic or bug replay",
        "allowed_stages": ["Z3_ORIGINAL_H7P5"],
        "cross_case_recycling": False,
        "predecessors": {},
    }
    payload = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
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


def test_v23_dat_preserves_original_b_identity_and_uses_physical_policy(capsys):
    v21 = load_and_resolve(V21_CASE)
    v23 = load_and_resolve(V23_CASE)
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
        assert getattr(v23, section) == getattr(v21, section)
    assert v23.physical_model_sha256 == v21.physical_model_sha256
    assert v23.solver["preconditioner"] == PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE
    assert v23.solver["memory_policy"] == PHYSICAL_MEMORY_POLICY_V23
    resources = v23.derived["physical_intermediate_profile"]["resources"]
    assert resources["watchdog_memory_policy"] == PHYSICAL_MEMORY_POLICY_V23
    assert resources["tree_cap_bytes"] is None
    assert resources["inventory_memory_cap_bytes_by_stage"] == {}
    assert resources["shared_temp_workspace_cap_bytes"] is None
    assert run_case_main(
        [str(V23_CASE), "--validate-only", "--v14-time-policy", "observe_only"]
    ) == 0
    capsys.readouterr()


def test_v23_ledger_binds_v22_history_and_allows_only_explicit_bug_replay(
    tmp_path, monkeypatch
):
    v22_destination = launcher._dual_condensed_capacity_v22_shared_ledger_path(
        tmp_path
    )
    v22_bytes = _copy_v22_ledger(v22_destination)
    monkeypatch.setattr(
        launcher,
        "V23_PREDECESSOR_V22_LEDGER_SHA256",
        hashlib.sha256(v22_bytes).hexdigest(),
    )
    v23_path = launcher._dual_condensed_physical_memory_v23_shared_ledger_path(
        tmp_path
    )
    stage_budget = profile_facts(PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE)[
        "resources"
    ]["stage_budgets"][launcher.V23_STAGE]
    lease = launcher._reserve_v23_shared_budget(
        tmp_path,
        tmp_path / "v23-first",
        source_sha="a" * 40,
        stage=launcher.V23_STAGE,
        stage_budget=stage_budget,
        workflow_clock_start=_clock(),
        time_policy="observe_only",
    )
    ledger = json.loads(v23_path.read_text(encoding="utf-8"))
    assert lease["path"] == str(v23_path)
    assert ledger["batch_identity"] == launcher.V23_BATCH_IDENTITY
    assert ledger["predecessors"]["v22"]["sha256"] == hashlib.sha256(
        v22_bytes
    ).hexdigest()
    assert ledger["predecessors"]["v22"]["known_costs_and_negative_results_preserved"]
    launcher._settle_v14_shared_budget(
        lease,
        status="WORKER_FAILED",
        authority=None,
        parent_interval={"budget_seconds": 1.0},
        parent_clock_end=_clock(1.0),
    )
    with pytest.raises(InputError, match="repair replay requires"):
        launcher._reserve_v23_shared_budget(
            tmp_path,
            tmp_path / "v23-without-bug-evidence",
            source_sha="b" * 40,
            stage=launcher.V23_STAGE,
            stage_budget=stage_budget,
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )


def test_v23_launcher_passes_same_policy_to_watchdog_and_worker(
    tmp_path, monkeypatch
):
    specification = load_and_resolve(V23_CASE)
    v22_destination = launcher._dual_condensed_capacity_v22_shared_ledger_path(
        tmp_path
    )
    v22_bytes = _copy_v22_ledger(v22_destination)
    monkeypatch.setattr(
        launcher,
        "V23_PREDECESSOR_V22_LEDGER_SHA256",
        hashlib.sha256(v22_bytes).hexdigest(),
    )
    v23_path = launcher._dual_condensed_physical_memory_v23_shared_ledger_path(
        tmp_path
    )
    monkeypatch.setattr(
        launcher,
        "_dual_condensed_capacity_v22_shared_ledger_path",
        lambda _repo_root: v22_destination,
    )
    monkeypatch.setattr(
        launcher,
        "_dual_condensed_physical_memory_v23_shared_ledger_path",
        lambda _repo_root: v23_path,
    )
    run_directory = tmp_path / "v23-launcher-run"

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir()
        return run_directory

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
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
    watchdog_kwargs = captured["kwargs"]
    assert watchdog_kwargs["memory_policy"] == PHYSICAL_MEMORY_POLICY_V23
    assert "tree_cap_bytes" not in watchdog_kwargs
    assert watchdog_kwargs["time_policy"] == "observe_only"
    assert watchdog_kwargs["stop_on_global_swap"] is True
    assert watchdog_kwargs["worker_environment"][
        "PHYSICAL_WATCHDOG_MEMORY_POLICY"
    ] == PHYSICAL_MEMORY_POLICY_V23
    assert watchdog_kwargs["worker_environment"][
        "PHYSICAL_QUALIFIED_JIT_CACHE_SOURCE"
    ] == str((ROOT / V23_QUALIFIED_JIT_CACHE_SOURCE).resolve())
    assert watchdog_kwargs["worker_environment"][
        "PHYSICAL_QUALIFIED_JIT_CACHE_ORIGIN"
    ] == V23_QUALIFIED_JIT_CACHE_ORIGIN
    assert watchdog_kwargs["worker_environment"][
        "PHYSICAL_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS"
    ] == str(V23_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS)
    assert watchdog_kwargs["worker_environment"][
        "PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH"
    ] == str(v23_path)
    assert v23_path.read_text(encoding="utf-8")


def test_v23_cache_import_uses_explicit_qualified_source(monkeypatch, tmp_path):
    from src.runners.physical_retained_outer_adapter import _v20_form_cache

    source = tmp_path / "qualified-source"
    source.mkdir(parents=True)
    (source / "qualified-module.so").write_bytes(b"qualified")
    runtime = SimpleNamespace(directory=tmp_path / "run")
    monkeypatch.setenv("PHYSICAL_QUALIFIED_JIT_CACHE_SOURCE", str(source))
    monkeypatch.setenv(
        "PHYSICAL_QUALIFIED_JIT_CACHE_ORIGIN", V23_QUALIFIED_JIT_CACHE_ORIGIN
    )
    monkeypatch.setenv(
        "PHYSICAL_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS",
        str(V23_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS),
    )
    _target, facts = _v20_form_cache(
        runtime, cache_policy="v21_reuse_all_qualified"
    )
    assert facts["source_cache_dir"] == str(source.resolve())
    assert facts["source_cache_binding"] == "explicit_qualified_formal_root"
    assert facts["qualified_source_origin"] == V23_QUALIFIED_JIT_CACHE_ORIGIN
    assert facts["qualified_expected_compiler_event_count"] == 11
    assert (runtime.directory / "v20_jit_cache/fenics/qualified-module.so").is_file()


def test_v23_runtime_ignores_legacy_caps_but_stops_on_live_physical_pressure(
    tmp_path, monkeypatch
):
    from benchmarks import subreaper_watchdog, task038_full3d_jit_staging
    from src.runners.physical_p4_schur_v14 import V14ResourceStop, _V14Runtime

    predecessor = launcher._dual_condensed_capacity_v22_shared_ledger_path(tmp_path)
    predecessor_bytes = _copy_v22_ledger(predecessor)
    monkeypatch.setattr(
        launcher,
        "V23_PREDECESSOR_V22_LEDGER_SHA256",
        hashlib.sha256(predecessor_bytes).hexdigest(),
    )
    stage_budget = profile_facts(PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE)[
        "resources"
    ]["stage_budgets"][launcher.V23_STAGE]
    lease = launcher._reserve_v23_shared_budget(
        tmp_path,
        tmp_path / "v23-runtime",
        source_sha="d" * 40,
        stage=launcher.V23_STAGE,
        stage_budget=stage_budget,
        workflow_clock_start=_clock(),
        time_policy="observe_only",
    )
    runtime_directory = tmp_path / "v23-runtime"
    runtime_directory.mkdir()
    monkeypatch.setenv("PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH", lease["path"])
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX", str(lease["attempt_index"])
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", str(os.getppid()))
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_MEMORY_POLICY", PHYSICAL_MEMORY_POLICY_V23
    )
    # A stale V22-style startup cap must not be converted to a V23 int cap.
    monkeypatch.setenv("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "1")
    monkeypatch.setattr(
        task038_full3d_jit_staging,
        "process_tree_snapshot",
        lambda *_args: {
            "rss_bytes": 1 << 30,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
    )
    monkeypatch.setattr(
        subreaper_watchdog,
        "memory_envelope",
        lambda _policy: {
            "effective_available_bytes": 12 << 30,
            "reserve_bytes": 128 << 20,
            "launch_cap_bytes": (12 << 30) - (128 << 20),
            "memory_policy": PHYSICAL_MEMORY_POLICY_V23,
        },
    )
    runtime = _V14Runtime(
        runtime_directory,
        launcher.V23_STAGE,
        profile_facts(PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE),
        root=ROOT,
        source_sha="d" * 40,
        batch_identity=launcher.V23_BATCH_IDENTITY,
        evidence_prefix="v23",
    )
    try:
        assert runtime.parent_cap is None
        assert runtime.inventory_cap is None
        assert runtime.workspace_cap is None
        runtime.reserve_inventory(
            "legacy-six-gib-test", {"payload": 7 << 30}, check_rss=False
        )
        runtime.reserve_workspace("legacy-one-gib-test", 2 << 30)
        good = runtime.sample("v23_live_pressure_ok")
        assert good["cap_policy"] == "current_tree_rss+available-reserve; no startup/static cap"
        assert good["parent_tree_cap_bytes"] is None

        monkeypatch.setattr(
            subreaper_watchdog,
            "memory_envelope",
            lambda _policy: {
                "effective_available_bytes": 64 << 20,
                "reserve_bytes": 128 << 20,
                "launch_cap_bytes": -(64 << 20),
                "memory_policy": PHYSICAL_MEMORY_POLICY_V23,
            },
        )
        with pytest.raises(V14ResourceStop, match="resource gate failed"):
            runtime.sample("v23_live_physical_pressure_stop")
    finally:
        launcher._settle_v14_shared_budget(
            lease,
            status="WORKER_FAILED",
            authority=None,
            parent_interval={"budget_seconds": 1.0},
            parent_clock_end=_clock(1.0),
        )


def test_v23_worker_dispatch_selects_physical_pressure_worker(monkeypatch, tmp_path):
    payload = load_and_resolve(V23_CASE).as_jsonable()
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as worker

    captured = {}

    def fake_capacity_worker(*_args, **kwargs):
        captured.update(kwargs)
        return {"passed": False, "errors": ["mock V23 worker"], "summary": None}

    monkeypatch.setattr(
        worker, "_run_physical_dual_cell_condensed_lowmem", fake_capacity_worker
    )
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="full3d_iterative",
        output_directory=tmp_path,
        expected_source_sha="a" * 40,
    )
    assert status == 4
    assert errors == ["mock V23 worker"]
    assert captured["profile_identity"] == PHYSICAL_MEMORY_DUAL_CELL_CONDENSED_PROFILE
    assert captured["batch_identity"] == launcher.V23_BATCH_IDENTITY
    assert captured["evidence_prefix"] == "v23"
    assert captured["capacity_policy"] == PHYSICAL_MEMORY_POLICY_V23
    assert captured["save_complete_field_packet"] is True
    assert captured["capacity_trial"] is True


def test_v23_rejects_tampered_v22_predecessor(tmp_path, monkeypatch):
    destination = launcher._dual_condensed_capacity_v22_shared_ledger_path(tmp_path)
    original = _copy_v22_ledger(destination)
    mutated = json.loads(original.decode("utf-8"))
    mutated["elapsed_seconds"] = float(mutated["elapsed_seconds"]) + 1.0
    destination.write_text(json.dumps(mutated), encoding="utf-8")
    monkeypatch.setattr(
        launcher,
        "V23_PREDECESSOR_V22_LEDGER_SHA256",
        hashlib.sha256(original).hexdigest(),
    )
    with pytest.raises(InputError, match="predecessor V22 ledger hash changed"):
        launcher._reserve_v23_shared_budget(
            tmp_path,
            tmp_path / "tampered-v23",
            source_sha="a" * 40,
            stage=launcher.V23_STAGE,
            stage_budget={"workflow_seconds": 43200.0},
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
