"""Pure fixtures for a V30 serial queue; no solver, field or resource PASS."""

from copy import deepcopy
import json
import os

import pytest

from src.runners import neural_wave_dependencies as queue


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def history(path, rows):
    path.write_text("\n".join(json.dumps(v) for v in rows) + "\n")


def rows():
    return [dict(timestamp_ns=(100 + i) * 10**9, root_pid=42,
        rss_bytes=100, swap_bytes=0, all_status_readable=True,
        opt_in_health_check=dict(stop_reason=None,
            memory_pressure=dict(some=dict(avg10=0.0), full=dict(avg10=0.0)),
            memory=dict(launch_cap_bytes=1024, planning_cap_bytes=1024)))
        for i in range(61)]


def test_wait_ledger_deduplicates_receipts_and_retains_stability(tmp_path):
    write(tmp_path / "a/pressure_stable_window.json", dict(observed_seconds=60.2))
    write(tmp_path / "b/pressure_stable_window.json", dict(observed_seconds=60.3))
    for name in ("admission", "admission_sample_00", "outer_admission"):
        write(tmp_path / f"a/{name}.json", dict(utc="u0", sample_interval_seconds=1.1))
    write(tmp_path / "b/admission.json", dict(utc="u1", sample_interval_seconds=1.2))
    assert queue.resource_observation_cost(tmp_path) == pytest.approx(122.8)


def test_continuous_same_tree_can_bridge_serial_activation(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    history(a, rows()[:45])
    history(b, rows()[44:])
    receipt = queue.continuity_receipt([a, b], now_ns=162 * 10**9, root_pid=42)
    assert receipt["sample_count"] == 61
    assert receipt["covered_seconds"] == 60
    assert receipt["age_seconds"] == 2
    assert receipt["root_pid"] == 42


@pytest.mark.parametrize("corruption", ["stale", "short", "gap", "swap", "psi", "reserve", "rss", "root", "unreadable"])
def test_continuous_window_refuses_corrupt_or_unobserved_history(tmp_path, corruption):
    data = deepcopy(rows())
    now = 162 * 10**9
    if corruption == "stale":
        now += 20 * 10**9
    if corruption == "short":
        data = data[1:]
    if corruption == "gap":
        data = data[:10] + data[30:]
    if corruption == "swap":
        data[20]["swap_bytes"] = 1
    if corruption == "psi":
        data[20]["opt_in_health_check"]["memory_pressure"]["full"]["avg10"] = .1
    if corruption == "reserve":
        data[20]["opt_in_health_check"]["memory"]["launch_cap_bytes"] = 1023
    if corruption == "rss":
        data[20]["rss_bytes"] = 1025
    if corruption == "root":
        data[20]["root_pid"] = 43
    if corruption == "unreadable":
        data[20]["all_status_readable"] = False
    path = tmp_path / "resources.jsonl"
    history(path, data)
    with pytest.raises(ValueError):
        queue.continuity_receipt(path, now_ns=now, root_pid=42)


def mocked_admission(monkeypatch, kinds):
    from src.runners import feinn_resources
    calls = []
    def fake(hard, **kwargs):
        kind = kinds[len(calls)]
        calls.append(kwargs)
        failures = [] if kind == "pass" else [
            "No audited unoccupied physical core; do not overlap a busy worker/SMT sibling"
            if kind == "cpu" else "memory or safety failure"]
        value = dict(cpu=2, failures=failures, utc=str(len(calls)), sample_interval_seconds=1.0)
        kwargs["observation_sink"](value)
        if failures:
            raise RuntimeError(failures[0])
        return value
    monkeypatch.setattr(feinn_resources, "admission", fake)
    monkeypatch.setattr(queue, "resource_observation_cost", lambda: 100.0)
    return calls


def test_fresh_cpu_resampling_preserves_original_scope(monkeypatch, tmp_path):
    calls = mocked_admission(monkeypatch, ["cpu", "cpu", "pass"])
    scope = {"allowed_cpus": [2]}
    assert queue.fresh_admission(tmp_path, 2048, scope=scope)["cpu"] == 2
    assert len(calls) == 3
    assert all(v["candidate_scope"] is scope for v in calls)
    assert len(list(tmp_path.glob("admission_sample_*.json"))) == 3


def test_no_resampling_of_safety_rejection(monkeypatch, tmp_path):
    calls = mocked_admission(monkeypatch, ["memory", "pass"])
    with pytest.raises(RuntimeError):
        queue.fresh_admission(tmp_path, 2048)
    assert len(calls) == 1


def test_bounded_samples_and_shared_wait_budget(monkeypatch, tmp_path):
    calls = mocked_admission(monkeypatch, ["cpu"] * 8)
    with pytest.raises(RuntimeError, match="bounded"):
        queue.fresh_admission(tmp_path, 2048)
    assert len(calls) == 8
    monkeypatch.setattr(queue, "resource_observation_cost", lambda: 1140.0)
    with pytest.raises(RuntimeError, match="BUDGET"):
        queue.fresh_admission(tmp_path / "new", 2048, reserve_s=60)
    assert len(calls) == 8


@pytest.mark.parametrize("corruption", ["none", "role", "parent", "start", "clock", "source", "guard", "mode", "cpu", "receipt"])
def test_admitted_child_requires_source_parent_freshness_and_role(monkeypatch, tmp_path, corruption):
    from src.runners import guarded_exec, neural_wave_campaign, neural_wave_worker
    monkeypatch.setattr(queue, "ROOT", tmp_path)
    child = tmp_path / "tmp/task42extra/v30/durable/test/dependencies/verify"
    spec = dict(role="verify", mode="fe", stage="v30_m5_verify")
    manifest = dict(spec=deepcopy(spec), source_sha="s", cpu=2,
        dependency_parent=dict(pid=123, start_ticks=456),
        fresh_admission_completed_monotonic=100,
        continuous_resource_receipt=dict(all_actual_rows_qualified=True, last_timestamp_ns=100 * 10**9))
    monkeypatch.setenv("TASK42EXTRA_WAVE_ADMITTED_CHILD", str(child))
    monkeypatch.setenv("TASK42EXTRA_ENV_MODE", "fe")
    monkeypatch.setenv("TASK42EXTRA_PARENT_DEATH_GUARD", "123:456:SIGKILL")
    monkeypatch.setattr(os, "getppid", lambda: 123)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {2})
    monkeypatch.setattr(queue, "monotonic", lambda: 102)
    monkeypatch.setattr(queue, "time_ns", lambda: 102 * 10**9)
    monkeypatch.setattr(guarded_exec, "ticks", lambda _: 456)
    monkeypatch.setattr(neural_wave_campaign, "source_gate", lambda: "s")
    called = []
    monkeypatch.setattr(neural_wave_worker, "main", lambda: called.append(True))
    if corruption == "role":
        spec["role"] = manifest["spec"]["role"] = "LEARNED_WAVE_GREEDY"
    if corruption == "parent":
        manifest["dependency_parent"]["pid"] = 124
    if corruption == "start":
        manifest["dependency_parent"]["start_ticks"] = 457
    if corruption == "clock":
        manifest["fresh_admission_completed_monotonic"] = 10
    if corruption == "source":
        manifest["source_sha"] = "t"
    if corruption == "guard":
        monkeypatch.setenv("TASK42EXTRA_PARENT_DEATH_GUARD", "123:456:NONE")
    if corruption == "mode":
        monkeypatch.setenv("TASK42EXTRA_ENV_MODE", "ml")
    if corruption == "cpu":
        manifest["cpu"] = 3
    if corruption == "receipt":
        manifest["continuous_resource_receipt"]["last_timestamp_ns"] = 10 * 10**9
    write(child / "run_manifest.json", manifest)
    if corruption == "none":
        assert queue.run_admitted(spec) == 0
        assert called == [True]
    else:
        with pytest.raises(ValueError):
            queue.run_admitted(spec)
        assert called == []


@pytest.mark.parametrize("stop", ["none", "common_node", "verifier_failure"])
def test_serial_dependencies_use_distinct_activation_and_do_not_replay(monkeypatch, tmp_path, stop):
    from benchmarks import subreaper_watchdog
    from src.runners import feinn_resources, fresh_component_receiver, guarded_exec, neural_wave_campaign

    monkeypatch.setattr(queue, "ROOT", tmp_path)
    artifacts = tmp_path / "benchmarks/artifacts/task42extra/v30"
    monkeypatch.setattr(queue, "ARTIFACTS", artifacts)
    directory = tmp_path / "tmp/task42extra/v30/durable/own"
    directory.mkdir(parents=True)
    write(artifacts / "nn/result.json", dict(status=
        "COMMON_COST_WORK_NODE_FROZEN_NOT_FINAL" if stop == "common_node" else "FROZEN"))
    monkeypatch.setattr(queue, "continuity_receipt", lambda *a, **kw: dict(
        all_actual_rows_qualified=True, last_timestamp_ns=100 * 10**9))
    monkeypatch.setattr(queue, "fresh_admission", lambda *a, **kw: dict(cpu=2))
    monkeypatch.setattr(neural_wave_campaign, "source_gate", lambda: "s")
    monkeypatch.setattr(fresh_component_receiver, "bind_own_terminal_core", lambda *a: None)
    monkeypatch.setattr(os, "sched_setaffinity", lambda *a: None)
    monkeypatch.setattr(guarded_exec, "ticks", lambda *a: 456)
    monkeypatch.setattr(feinn_resources, "Health", lambda *a, **kw: None)
    monkeypatch.setattr(queue, "monotonic", lambda: 100.0)
    for stage in ("v30_m5_verify", "v30_m5_saved_audit"):
        p = tmp_path / f"input/task042extra_feinn_5nm/{stage}.dat"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(stage)
    monkeypatch.setattr(queue, "load_wave", lambda p: dict(stage=p.stem,
        mode="fe" if p.stem == "v30_m5_verify" else "pure",
        role="verify" if p.stem == "v30_m5_verify" else "saved_audit",
        input=str(p.relative_to(tmp_path)), input_sha256="i", max_seconds=7200))
    called = []
    def fake_supervise(command, dest, **kwargs):
        called.append((command, kwargs))
        return dict(classification="WORKER_FAILED" if stop == "verifier_failure" else "COMPLETED",
            leader_exit_code=1 if stop == "verifier_failure" else 0, descendants_cleared=True)
    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    manifest = dict(spec=dict(stage="nn"), campaign=dict(deadline_monotonic=20000))
    terminal = dict(server=dict(pid=42), allowed_scope=dict(allowed_cpus=[2]))
    result = queue.followups(directory, manifest, terminal,
        dict(classification="COMPLETED", leader_exit_code=0))
    assert len(result) == {"none": 2, "common_node": 0, "verifier_failure": 1}[stop]
    if stop == "common_node":
        assert called == []
        return
    assert "activate_task42extra.sh fe" in called[0][0][2]
    assert "python scripts/run_case.py" in called[0][0][2]
    assert called[0][1]["sampled_root_identity"] is terminal["server"]
    if stop == "none":
        assert "activate_task42extra.sh pure" in called[1][0][2]
        assert called[0][1]["rss_hard_limit_bytes"] == 16 * 2**30
        assert called[1][1]["rss_hard_limit_bytes"] == 2 * 2**30
    write(artifacts / "v30_m5_verify/result.json", dict(status="healthy"))
    with pytest.raises(ValueError, match="ALREADY_FROZEN"):
        queue.followups(tmp_path / "another", manifest, terminal,
            dict(classification="COMPLETED", leader_exit_code=0))


def test_outer_rejection_is_saved_before_any_terminal(monkeypatch, tmp_path):
    from src.runners import durable_terminal, neural_wave_campaign

    monkeypatch.setattr(neural_wave_campaign, "ROOT", tmp_path)
    monkeypatch.setattr(neural_wave_campaign, "source_gate", lambda: "s")
    monkeypatch.setattr(neural_wave_campaign, "monotonic", lambda: 100.0)
    monkeypatch.setattr(neural_wave_campaign, "window", lambda spec=None: dict(deadline_monotonic=20000))
    monkeypatch.setattr(neural_wave_campaign, "profile_paths", lambda spec: dict(
        root=tmp_path / "tmp/task42extra/v30", reserve=1800))
    called = []
    monkeypatch.setattr(durable_terminal, "launch_tmux", lambda *a, **kw: called.append(True))
    def fail(*a, **kw):
        raise RuntimeError("RESOURCE_WINDOW_UNAVAILABLE")
    monkeypatch.setattr(queue, "fresh_admission", fail)
    with pytest.raises(RuntimeError, match="RESOURCE_WINDOW_UNAVAILABLE"):
        neural_wave_campaign.durable(dict(stage="s", max_seconds=10000, input_sha256="i"), origin=100)
    result = json.loads((tmp_path / "tmp/task42extra/v30/durable/s_attempt1/run_summary.json").read_text())
    assert result["classification"] == "RESOURCE_ADMISSION_REJECTED_BEFORE_TERMINAL"
    assert result["worker_started"] is False
    assert result["descendants_cleared"] is True
    assert called == []
