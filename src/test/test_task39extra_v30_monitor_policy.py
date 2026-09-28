'''V30 PSS diagnostics stay out of the hard RSS watchdog path.'''

import json
import os
import signal
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from benchmarks import subreaper_watchdog
from benchmarks import task038_full3d_jit_staging as staging
import pytest
from src.runners.physical_p4_schur_v14 import (
    _v14_resource_facts,
    _v14_worker_pss_sampling_policy,
)


def test_disabled_pss_snapshot_skips_a_slow_provider(monkeypatch):
    calls = []

    def slow_pss(_pid):
        calls.append(True)
        raise AssertionError("disabled profile must not call smaps_rollup")

    monkeypatch.setattr(staging, "_live_parent_map", lambda: {os.getpid(): []})
    monkeypatch.setattr(staging, "_pss_bytes", slow_pss)
    sample = staging.process_tree_snapshot(
        os.getpid(), "test", pss_sampling_policy="disabled_by_profile"
    )

    assert calls == []
    assert sample["all_status_readable"] is True
    assert isinstance(sample["rss_bytes"], int) and sample["rss_bytes"] >= 0
    assert isinstance(sample["swap_bytes"], int) and sample["swap_bytes"] >= 0
    assert sample["pss_sampling_policy"] == "disabled_by_profile"
    assert sample["pss_status"] == "DISABLED_BY_PROFILE"
    assert sample["pss_all_readable"] is None
    assert sample["pss_bytes"] is None


def test_parent_watchdog_rss_polling_never_queues_slow_pss(tmp_path):
    run = tmp_path / "watchdog"
    marker = tmp_path / "pss_provider_called"
    monitor = f'''
import json, sys, time
from pathlib import Path
from benchmarks import task038_full3d_jit_staging as staging
from benchmarks.subreaper_watchdog import supervise
marker = Path({str(marker)!r})
def slow_pss(pid):
    marker.write_text(str(pid))
    time.sleep(0.2)
    return 0
staging._pss_bytes = slow_pss
result = supervise(
    [sys.executable, "-c", "import time; time.sleep(0.08)"],
    Path({str(run)!r}), wall_seconds=4, interval=0.02, grace_seconds=0.1,
    pss_sampling_policy="disabled_by_profile",
)
print(json.dumps(result))
'''
    completed = subprocess.run(
        [sys.executable, "-c", monitor], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not marker.exists()
    samples = [
        json.loads(line)
        for line in (run / "resources.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(samples) >= 3
    assert all(row["pss_sampling_policy"] == "disabled_by_profile" for row in samples)
    assert all(row["pss_status"] == "DISABLED_BY_PROFILE" for row in samples)
    assert all(row["pss_all_readable"] is None and row["pss_bytes"] is None for row in samples)
    summary = json.loads((run / "summary.json").read_text())
    assert summary["pss_status"] == "DISABLED_BY_PROFILE"
    assert summary["sampled_process_tree_pss_peak_bytes"] is None
    assert summary["descendants_cleared"] is True


def test_resource_checker_treats_disabled_pss_as_unknown_not_failure(tmp_path):
    row = {
        "rss_bytes": 600,
        "pss_bytes": None,
        "pss_all_readable": None,
        "pss_sampling_policy": "disabled_by_profile",
        "pss_status": "DISABLED_BY_PROFILE",
        "swap_bytes": 0,
        "all_status_readable": True,
        "launch_cap_bytes": 1000,
        "inventory_memory_cap_bytes": 200,
        "inventory_used_bytes": 20,
        "inventory_peak_bytes": 30,
        "workspace_live_bytes": 20,
        "workspace_peak_bytes": 30,
        "memory_envelope": {"effective_available_bytes": 400, "reserve_bytes": 300},
        "timestamp_ns": 1,
        "label": "synthetic",
    }
    path = tmp_path / "resources.jsonl"
    path.write_text(json.dumps(row) + "\n")
    worker_summary = {"profile": "physical_p6_trace_workstation_guided_v30"}
    pss_policy = _v14_worker_pss_sampling_policy(worker_summary)
    assert pss_policy == "disabled_by_profile"
    assert _v14_worker_pss_sampling_policy(
        {"profile": "physical_p6_trace_a4_tensor_h6_v29"}
    ) == "sampled"
    result = _v14_resource_facts(
        SimpleNamespace(
            resources_path=path, workspace_cap=100,
            pss_sampling_policy=pss_policy,
        )
    )
    assert result["gate"] is True
    assert result["pss_sampling_policy"] == "disabled_by_profile"
    assert result["pss_status"] == "DISABLED_BY_PROFILE"
    assert result["pss_all_readable"] is None
    assert result["pss_peak_bytes"] is None


@pytest.mark.parametrize(
    ("vanished", "expected_readable", "expected_vanished"),
    [(True, True, [202]), (False, False, [])],
)
def test_disabled_pss_preserves_vanished_and_unreadable_status_handling(
    monkeypatch, vanished, expected_readable, expected_vanished
):
    calls = []

    def fact(pid, stage, *, collect_pss=True):
        calls.append((pid, collect_pss))
        if pid == 101:
            return {
                "pid": 101, "ppid": 1, "comm": "python", "state": "S",
                "cmdline": "python monitor", "stage": stage, "rss_bytes": 80,
                "pss_bytes": None, "swap_bytes": 0, "timestamp_ns": 1,
                "exit_code": None,
            }
        return None

    monkeypatch.setattr(staging, "_live_parent_map", lambda: {101: [202]})
    monkeypatch.setattr(staging, "_process_fact", fact)
    monkeypatch.setattr(staging, "_pid_vanished", lambda _pid: vanished)
    monkeypatch.setattr(staging.time, "sleep", lambda _seconds: None)

    sample = staging.process_tree_snapshot(
        101, "status-fixture", pss_sampling_policy="disabled_by_profile"
    )

    expected_calls = [(101, False)] + [(202, False)] * (2 if vanished else 3)
    assert calls == expected_calls
    assert sample["all_status_readable"] is expected_readable
    assert sample["vanished_pids"] == expected_vanished
    assert sample["pss_bytes"] is None
    assert sample["pss_all_readable"] is None
    assert sample["pss_status"] == "DISABLED_BY_PROFILE"
    assert sample["rss_bytes"] == (80 if expected_readable else None)


@pytest.mark.parametrize(
    ("changes", "failed_check"),
    [
        ({"rss_bytes": 1000}, "rss"),
        ({"all_status_readable": False}, "readable"),
        ({"swap_bytes": 1}, "zero_swap"),
        ({"memory_envelope": {"effective_available_bytes": 299, "reserve_bytes": 300}}, "reserve"),
    ],
)
def test_disabled_pss_does_not_weaken_rss_or_lifecycle_resource_gates(
    tmp_path, changes, failed_check
):
    row = {
        "rss_bytes": 600, "pss_bytes": None, "pss_all_readable": None,
        "pss_sampling_policy": "disabled_by_profile",
        "pss_status": "DISABLED_BY_PROFILE", "swap_bytes": 0,
        "all_status_readable": True, "launch_cap_bytes": 1000,
        "inventory_memory_cap_bytes": 200, "inventory_used_bytes": 20,
        "inventory_peak_bytes": 30, "workspace_live_bytes": 20,
        "workspace_peak_bytes": 30,
        "memory_envelope": {"effective_available_bytes": 400, "reserve_bytes": 300},
        "timestamp_ns": 1, "label": "synthetic",
    }
    row.update(changes)
    path = tmp_path / "resources.jsonl"
    path.write_text(json.dumps(row) + "\n")
    result = _v14_resource_facts(
        SimpleNamespace(
            resources_path=path, workspace_cap=100,
            pss_sampling_policy="disabled_by_profile",
        )
    )
    assert result["gate"] is False
    assert result["first_failed_sample"]["checks"][failed_check] is False
    assert result["pss_status"] == "DISABLED_BY_PROFILE"
    assert result["pss_all_readable"] is None
    assert result["pss_peak_bytes"] is None


def test_subreaper_never_signals_a_reused_pid(monkeypatch):
    pid = 900001
    signals = []
    original_read_text = Path.read_text

    def fake_read_text(path, *args, **kwargs):
        if str(path) == f"/proc/{pid}/stat":
            fields = ["S"] + ["0"] * 18 + ["22"]
            return f"{pid} (reused-process) " + " ".join(fields)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(subreaper_watchdog, "_children", lambda: {pid: (1, 11)})
    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(subreaper_watchdog.os, "kill", lambda *args: signals.append(args))

    subreaper_watchdog._signal_children(signal.SIGKILL)

    assert signals == []


def test_disabled_pss_watchdog_stops_on_rss_and_cleans_reparented_setsid_child(tmp_path):
    run_dir = tmp_path / "orphan-watchdog"
    marker = tmp_path / "orphan-identity.json"
    supervisor = f'''\
import json, os, sys
from pathlib import Path
from benchmarks import subreaper_watchdog as wd
from benchmarks import task038_full3d_jit_staging as staging
marker = Path({str(marker)!r})
real_snapshot = wd.process_tree_snapshot
ready = []
def verified_snapshot(*args, **kwargs):
    sample = real_snapshot(*args, **kwargs)
    exit_code = args[2] if len(args) > 2 else kwargs.get("exit_code")
    if exit_code is not None and marker.is_file() and not ready:
        identity = json.loads(marker.read_text())
        member = next((item for item in sample["members"] if item["pid"] == identity["pid"]), None)
        if member is not None:
            stat = Path(f"/proc/{{identity['pid']}}/stat").read_text().rsplit(")", 1)[1].split()
            if int(stat[19]) == identity["start_ticks"] and member["ppid"] == os.getpid():
                ready.append(identity)
                sample["rss_bytes"] = 1 << 50  # Synthetic gate after identity verification.
    return sample
wd.process_tree_snapshot = verified_snapshot
staging._pss_bytes = lambda _pid: (_ for _ in ()).throw(AssertionError("PSS must stay disabled"))
wd.wsl_memory_snapshot = lambda: {{"mem_total_bytes": 16 << 30, "mem_available_bytes": 12 << 30}}
wd.current_cgroup_path = lambda: None
wd.vmstat_swap_pages = lambda: {{"pswpin_pages": 0, "pswpout_pages": 0}}
child_code = """import json, os, time
from pathlib import Path
marker = Path(MARKER_PATH)
read_fd, write_fd = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(read_fd)
    os.setsid()
    fields = Path('/proc/' + str(os.getpid()) + '/stat').read_text().rsplit(')', 1)[1].split()
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps({{'pid': os.getpid(), 'start_ticks': int(fields[19])}}))
    os.replace(temporary, marker)
    os.write(write_fd, b'R')
    os.close(write_fd)
    while True:
        time.sleep(30)
else:
    os.close(write_fd)
    os.read(read_fd, 1)
    os.close(read_fd)
    os._exit(0)
""".replace("MARKER_PATH", repr(str(marker)))
result = wd.supervise(
    [sys.executable, "-c", child_code], Path({str(run_dir)!r}),
    wall_seconds=5, interval=0.02, grace_seconds=0.1,
    tree_cap_bytes=1 << 50, hard_stop_immediate=True,
    pss_sampling_policy="disabled_by_profile",
)
print(json.dumps({{"result": result, "ready_verified": bool(ready), "identity": ready[0] if ready else None}}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", supervisor], capture_output=True, text=True,
        check=False, timeout=15,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    result = payload["result"]
    identity = payload["identity"]
    assert payload["ready_verified"] is True
    assert identity["pid"] in result["observed_child_pids"]
    assert result["classification"] == "RESOURCE_CONTROLLED_STOP"
    assert result["descendants_cleared"] is True
    assert not Path(f"/proc/{identity['pid']}/stat").exists()
    assert result["sampled_process_tree_rss_peak_bytes"] == 1 << 50
    assert result["pss_status"] == "DISABLED_BY_PROFILE"
    assert result["sampled_process_tree_pss_peak_bytes"] is None
    assert marker.exists()
    samples = [
        json.loads(line)
        for line in (run_dir / "resources.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert samples
    assert all(row["pss_bytes"] is None for row in samples)
    assert all(row["pss_status"] == "DISABLED_BY_PROFILE" for row in samples)

def test_fake_clock_slow_pss_provider_does_not_block_or_catch_up_disabled_rss_loop(tmp_path):
    run_dir = tmp_path / "fake-clock-watchdog"
    supervisor = f'''\
import json, sys, time
from pathlib import Path
from benchmarks import subreaper_watchdog as wd
from benchmarks import task038_full3d_jit_staging as staging
real_sleep = time.sleep
clock = [0.0]
def monotonic(): return clock[0]
def fake_sleep(seconds):
    clock[0] += seconds
    real_sleep(min(max(seconds, 0.0), 0.001))
wd.time.monotonic = monotonic
wd.time.sleep = fake_sleep
calls = []
def slow_pss(pid):
    calls.append(pid)
    clock[0] += 1.0  # 50 RSS polling intervals if invoked.
    real_sleep(0.01)
    return 0
staging._pss_bytes = slow_pss
samples_at = []
original_snapshot = wd.process_tree_snapshot
def measured_snapshot(*args, **kwargs):
    result = original_snapshot(*args, **kwargs)
    samples_at.append(clock[0])
    return result
wd.process_tree_snapshot = measured_snapshot
wd.wsl_memory_snapshot = lambda: {{"mem_total_bytes": 16 << 30, "mem_available_bytes": 12 << 30}}
wd.current_cgroup_path = lambda: None
wd.vmstat_swap_pages = lambda: {{"pswpin_pages": 0, "pswpout_pages": 0}}
result = wd.supervise(
    [sys.executable, "-c", "import time; time.sleep(0.06)"],
    Path({str(run_dir)!r}), wall_seconds=5, interval=0.02,
    grace_seconds=0.1, pss_sampling_policy="disabled_by_profile",
)
print(json.dumps({{"result": result, "samples_at": samples_at, "slow_provider_calls": calls, "fake_elapsed": clock[0]}}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", supervisor], capture_output=True, text=True,
        check=False, timeout=15,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    stamps = payload["samples_at"]
    gaps = [right - left for left, right in zip(stamps, stamps[1:])]
    assert payload["slow_provider_calls"] == []
    assert payload["fake_elapsed"] >= 1.0  # Cache-stable completion requires one fake second.
    assert payload["result"]["classification"] == "COMPLETED"
    assert payload["result"]["cache_metadata_stable"] is True
    assert len(stamps) > 1
    assert max(gaps) < 0.5
    assert payload["result"]["descendants_cleared"] is True
