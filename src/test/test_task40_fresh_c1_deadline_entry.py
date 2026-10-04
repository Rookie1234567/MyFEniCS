"""Focused W0 fixed-deadline and no-FE control-entry tests."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks import run_fresh_c1_p6_component as runner


FIXED_DEADLINE = "2026-10-04T12:55:26Z"


def test_control_smoke_leaf_dispatches_through_real_main_cli(tmp_path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    receipt = root / "abi_receipt.json"
    receipt.write_text("{}")
    service_pid = 12345
    monkeypatch.setattr(runner, "_qualified_runtime", lambda _receipt: None)
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", str(service_pid))
    monkeypatch.setattr(runner.os, "getppid", lambda: service_pid)
    (root / "control_smoke_contract.json").write_text(json.dumps({
        "token": "a" * 32, "service_pid": service_pid,
    }))
    common = ["--output-dir", str(root), "--abi-receipt", str(receipt)]

    # These are the exact mode/argument shapes emitted by _supervise_phase.
    assert runner.main(["--control-smoke-leaf", "worker", *common]) == 0
    assert runner.main(["--control-smoke-leaf", "checker", *common]) == 0
    worker = json.loads((root / "worker_report.json").read_text())
    checker = json.loads((root / "checker_report.json").read_text())
    assert worker["status"] == "CONTROL_SMOKE_WORKER_SENTINEL_PASS"
    assert checker["status"] == "CONTROL_SMOKE_CHECKER_SENTINEL_PASS"
    assert worker["pid"] == checker["pid"] == os.getpid()
    assert checker["worker_pid"] == worker["pid"]
    assert worker["parent_pid"] == checker["parent_pid"] == service_pid
    assert worker["PDE_solved"] is checker["PDE_solved"] is False
    assert worker["official_results"] is checker["official_results"] is False


def test_phase_budget_keeps_fixed_settlement_cleanup_reserve():
    assert runner._phase_wall_budget_seconds(100.0, 65.0) == 5.0
    assert runner._phase_wall_budget_seconds(100.0, 70.0) == 0.0
    assert runner._phase_wall_budget_seconds(100.0, 99.0) == 0.0
    assert runner._phase_wall_budget_seconds(10_000.0, 1_000.0) == 4500.0


def test_supervise_phase_caps_wall_tree_and_honors_reserve_guard(tmp_path, monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog

    root = tmp_path / "run"
    root.mkdir()
    receipt = root / "abi_receipt.json"
    receipt.write_text("{}")
    times = iter((1050.0, 1069.999, 1070.0))
    monkeypatch.setattr(runner.time, "time", lambda: next(times))
    monkeypatch.setattr(runner, "_disk_facts", lambda _root: {"stop": False})
    captured = {}

    def fake_supervise(command, directory, **kwargs):
        captured.update(command=command, directory=directory, **kwargs)
        captured["guard_before_cutoff"] = kwargs["external_guard"]()
        captured["guard_at_cutoff"] = kwargs["external_guard"]()
        return {"classification": "COMPLETED"}

    monkeypatch.setattr(watchdog, "supervise", fake_supervise)
    summary = runner._supervise_phase(root, "worker", receipt, 1100.0, control_smoke=True)

    assert summary["classification"] == "COMPLETED"
    assert captured["wall_seconds"] == 20.0
    assert captured["grace_seconds"] == runner.W0_SUBREAPER_GRACE_SECONDS == 2.0
    assert captured["tree_cap_bytes"] == 3 * 1024**3
    assert captured["stop_on_global_swap"] is True
    assert captured["command"][captured["command"].index("--control-smoke-leaf") + 1] == "worker"
    assert captured["guard_before_cutoff"]["stop"] is False
    assert captured["guard_at_cutoff"]["reason"] == "TOTAL_UTC_DEADLINE_SETTLEMENT_RESERVE"


def _install_supervised_cli_fakes(monkeypatch, phase_runner):
    import benchmarks.subreaper_watchdog as watchdog

    monkeypatch.setattr(runner, "_qualified_runtime", lambda _receipt: None)
    monkeypatch.setattr(runner, "validate_native_runtime", lambda _receipt: {
        "native_abi_identity": {"fixture": "no-fe"},
    })
    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {"launch_cap_bytes": 1})
    monkeypatch.setattr(runner, "_whole_machine_memory_occupancy_upper", lambda _env: (10, 1000))
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _path: SimpleNamespace(free=runner.MINIMUM_START_FREE_BYTES + 1))
    monkeypatch.setattr(runner, "source_identity", lambda: {"manifest_sha256": "fixture"})
    monkeypatch.setattr(runner, "_sha256", lambda _path: runner.INPUT_SHA256)
    monkeypatch.setattr(runner, "_phase_wall_budget_seconds", lambda _deadline, _now: 4500.0)
    monkeypatch.setattr(runner, "_supervise_phase", phase_runner)


def test_standard_and_control_smoke_share_worker_checker_phase_path(tmp_path, monkeypatch):
    calls = []

    def fake_phase(root, phase, _receipt, deadline_epoch, *, control_smoke=False):
        calls.append((root.name, phase, deadline_epoch, control_smoke))
        summary = {"classification": "COMPLETED", "descendants_cleared": True,
                   "remaining_child_pids": []}
        if not control_smoke:
            report = ({"standard": "worker"} if phase == "worker"
                      else {"independent_component_pass": True})
        else:
            contract = json.loads((root / "control_smoke_contract.json").read_text())
            parent = contract["service_pid"]
            report = ({"status": "CONTROL_SMOKE_WORKER_SENTINEL_PASS", "token": contract["token"],
                       "pid": 21001, "parent_pid": parent, "PDE_solved": False,
                       "official_results": False} if phase == "worker" else
                      {"status": "CONTROL_SMOKE_CHECKER_SENTINEL_PASS", "token": contract["token"],
                       "pid": 21002, "parent_pid": parent, "worker_pid": 21001,
                       "PDE_solved": False, "official_results": False})
        (root / ("worker_report.json" if phase == "worker" else "checker_report.json")).write_text(
            json.dumps(report))
        return summary

    _install_supervised_cli_fakes(monkeypatch, fake_phase)
    receipt = tmp_path / "abi_receipt.json"
    receipt.write_text("{}")
    for name, smoke in (("standard", False), ("smoke", True)):
        root = tmp_path / name
        root.mkdir()
        assert runner._supervised_cli(root, receipt, FIXED_DEADLINE,
                                      control_smoke=smoke) == 0
        expected = "CONTROL_SMOKE_PASS_NO_FE" if smoke else "PASS_COMPONENT_ONLY"
        assert json.loads((root / "run_summary.json").read_text())["status"] == expected

    assert [(name, phase, smoke) for name, phase, _deadline, smoke in calls] == [
        ("standard", "worker", False), ("standard", "checker", False),
        ("smoke", "worker", True), ("smoke", "checker", True),
    ]
    assert {deadline for _name, _phase, deadline, _smoke in calls} == {
        datetime.strptime(FIXED_DEADLINE, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    }


def test_control_smoke_cleanup_failure_is_saved_and_stops_before_checker(tmp_path, monkeypatch):
    calls = []

    def failing_worker(root, phase, _receipt, _deadline, *, control_smoke=False):
        calls.append((phase, control_smoke))
        contract = json.loads((root / "control_smoke_contract.json").read_text())
        (root / "worker_report.json").write_text(json.dumps({
            "status": "CONTROL_SMOKE_WORKER_SENTINEL_PASS", "token": contract["token"],
            "pid": 22001, "parent_pid": contract["service_pid"], "PDE_solved": False,
        }))
        return {"classification": "COMPLETED", "descendants_cleared": False,
                "remaining_child_pids": [22002]}

    _install_supervised_cli_fakes(monkeypatch, failing_worker)
    root = tmp_path / "run"
    root.mkdir()
    receipt = tmp_path / "abi_receipt.json"
    receipt.write_text("{}")

    assert runner._supervised_cli(root, receipt, FIXED_DEADLINE, control_smoke=True) == 3
    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["status"] == "CONTROL_SMOKE_WORKER_FAILED"
    assert summary["worker_supervisor"]["remaining_child_pids"] == [22002]
    assert calls == [("worker", True)]
    assert not (root / "checker_report.json").exists()


def test_native_service_entry_passes_fixed_deadline_and_smoke_to_runner(tmp_path):
    repo = Path(__file__).parents[2]
    source_entry = repo / "scripts" / "task40_fresh_c1" / "native_service_entry.sh"
    fake_repo = tmp_path / "repo"
    script_dir = fake_repo / "scripts" / "task40_fresh_c1"
    script_dir.mkdir(parents=True)
    entry = script_dir / "native_service_entry.sh"
    entry.write_bytes(source_entry.read_bytes())
    (script_dir / "activate_native_complex.sh").write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n[[ $# -eq 3 && -f "$2" ]]\n')
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    arg_record = tmp_path / "runner-argv.txt"
    python_shim = prefix / "bin" / "python"
    python_shim.write_text("#!/usr/bin/env bash\nprintf '%s\\0' \"$@\" >\"$TASK40_TEST_ARGV\"\n")
    python_shim.chmod(0o755)
    receipt = tmp_path / "abi_receipt.json"
    receipt.write_text("{}")
    run_dir = tmp_path / "run"
    (run_dir / "jit").mkdir(parents=True)
    (run_dir / "tmp").mkdir()
    env = os.environ.copy()
    env["TASK40_TEST_ARGV"] = str(arg_record)
    completed = subprocess.run(["bash", str(entry), str(fake_repo), str(prefix), str(receipt),
                                str(run_dir), FIXED_DEADLINE, "--control-smoke"],
                               cwd=fake_repo, env=env, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    argv = arg_record.read_bytes().decode().rstrip("\0").split("\0")
    assert argv == ["-m", "benchmarks.run_fresh_c1_p6_component", "--supervised",
                    "--output-dir", str(run_dir), "--abi-receipt", str(receipt),
                    "--total-deadline-utc", FIXED_DEADLINE, "--control-smoke"]


def test_native_wrapper_rejects_fractional_deadline_before_creating_run_dir(tmp_path):
    repo = Path(__file__).parents[2]
    wrapper = repo / "scripts" / "run_fresh_c1_p6_native.sh"
    run_dir = tmp_path / "must-not-exist"
    completed = subprocess.run(["bash", str(wrapper), str(tmp_path / "unused-prefix"),
                                str(run_dir), "2026-10-04T12:55:26.395534Z"],
                               cwd=repo, text=True, capture_output=True, check=False)

    assert completed.returncode == 64
    assert "whole-second UTC timestamp" in completed.stderr
    assert not run_dir.exists()
