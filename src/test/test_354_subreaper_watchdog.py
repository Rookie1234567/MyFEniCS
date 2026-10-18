"""Real subprocess lifecycle checks, including setsid after leader exit."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_explicit_tree_cap_reuses_current_rss_without_double_counting():
    from benchmarks.subreaper_watchdog import runtime_tree_cap

    envelope = {
        'effective_available_bytes': 9 * 1024**3,
        'reserve_bytes': 4 * 1024**3,
    }
    assert runtime_tree_cap(
        8 * 1024**3,
        3 * 1024**3,
        envelope,
        explicit_tree_cap_bytes=8 * 1024**3,
    ) == 8 * 1024**3
    occupied_externally = {
        'effective_available_bytes': 8 * 1024**3,
        'reserve_bytes': 4 * 1024**3,
    }
    assert runtime_tree_cap(
        8 * 1024**3,
        3 * 1024**3,
        occupied_externally,
        explicit_tree_cap_bytes=8 * 1024**3,
    ) == 7 * 1024**3


def test_v29_reserves_host_and_task_cgroup_capacity_as_separate_domains(
    monkeypatch,
):
    import benchmarks.subreaper_watchdog as watchdog

    cgroup = Path("/sys/fs/cgroup/task")
    values = {
        cgroup / "memory.max": "1000",
        cgroup / "memory.current": "950",
        Path("/sys/fs/cgroup/memory.max"): "max",
    }
    monkeypatch.setattr(
        watchdog,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 20_000, "mem_available_bytes": 10_000},
    )
    monkeypatch.setattr(watchdog, "current_cgroup_path", lambda: cgroup)
    monkeypatch.setattr(
        watchdog.Path,
        "is_file",
        lambda path: path in values,
    )
    monkeypatch.setattr(
        watchdog.Path,
        "read_text",
        lambda path, *args, **kwargs: values[path],
    )

    envelope = watchdog.memory_envelope(
        watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY,
        host_reserve_bytes=1_000,
        task_cgroup_reserve_bytes=0,
    )

    assert envelope["host_mem_available_bytes"] == 10_000
    assert envelope["task_cgroup_available_bytes"] == 50
    assert envelope["host_launch_available_bytes"] == 9_000
    assert envelope["task_cgroup_launch_available_bytes"] == 50
    assert envelope["effective_available_after_reserves_bytes"] == 50
    assert envelope["launch_cap_bytes"] == min(9_000, 50)
    assert envelope["reserve_domains_separated"] is True


def test_split_reserve_predicate_matches_task41_false_stop_sample():
    from benchmarks.subreaper_watchdog import reserve_violation

    # Exact 2026-10-18 trigger row: the host reserve is healthy, and the
    # cgroup has 0 B of its own reserve.  Its 21,209,088 B shortfall against
    # the host reserve must not be treated as a cgroup reserve violation.
    trigger = {
        "reserve_domains_separated": True,
        "host_mem_available_bytes": 854_915_547_136,
        "reserve_bytes": 68_719_476_736,
        "effective_available_bytes": 68_698_267_648,
        "task_cgroup_available_bytes": 68_698_267_648,
        "task_cgroup_reserve_bytes": 0,
    }
    assert trigger["reserve_bytes"] - trigger["effective_available_bytes"] == 21_209_088
    assert reserve_violation(trigger) is False


@pytest.mark.parametrize(
    ("host_available", "task_available", "task_reserve", "expected"),
    [
        (999, 999, 0, False),
        (999, 100, 100, False),
        (999, 99, 100, True),
        (999, 0, 0, False),
        (99, 999, 0, True),
    ],
)
def test_split_reserve_predicate_checks_only_each_domains_own_reserve(
    host_available, task_available, task_reserve, expected
):
    from benchmarks.subreaper_watchdog import reserve_violation

    assert reserve_violation(
        {
            "reserve_domains_separated": True,
            "host_mem_available_bytes": host_available,
            "reserve_bytes": 100,
            "effective_available_bytes": min(host_available, task_available),
            "task_cgroup_available_bytes": task_available,
            "task_cgroup_reserve_bytes": task_reserve,
        }
    ) is expected


def test_legacy_reserve_predicate_keeps_effective_available_boundary():
    from benchmarks.subreaper_watchdog import reserve_violation

    envelope = {
        "reserve_domains_separated": False,
        "effective_available_bytes": 99,
        "reserve_bytes": 100,
        "host_mem_available_bytes": 10_000,
        "task_cgroup_available_bytes": 99,
        "task_cgroup_reserve_bytes": None,
    }
    assert reserve_violation(envelope) is True
    envelope["effective_available_bytes"] = 100
    assert reserve_violation(envelope) is False


def test_cli_forwards_physical_memory_and_profile_sampling_policies(
    monkeypatch, tmp_path, capsys
):
    import benchmarks.subreaper_watchdog as watchdog

    captured = {}

    def fake_supervise(command, directory, **kwargs):
        captured.update(command=command, directory=directory, **kwargs)
        return {'classification': 'COMPLETED'}

    monkeypatch.setattr(watchdog, 'supervise', fake_supervise)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'subreaper_watchdog.py',
            '--directory', str(tmp_path / 'run'),
            '--wall-seconds', '43200',
            '--timebase-guard',
            '--time-policy', 'observe_only',
            '--memory-policy', watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY,
            '--pss-sampling-policy', 'disabled_by_profile',
            '--', sys.executable, '-c', 'pass',
        ],
    )

    assert watchdog.main() == 0
    assert captured['command'] == [sys.executable, '-c', 'pass']
    assert captured['time_policy'] == 'observe_only'
    assert captured['memory_policy'] == watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY
    assert captured['pss_sampling_policy'] == 'disabled_by_profile'
    assert json.loads(capsys.readouterr().out)['classification'] == 'COMPLETED'


def test_supervise_injects_worker_envelope_when_phase_path_is_set(tmp_path):
    from benchmarks.subreaper_watchdog import supervise

    phase_path = tmp_path / "continuation_phase.json"
    envelope_path = tmp_path / "worker_envelope.json"
    worker = (
        "import json,os; from pathlib import Path; "
        "parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID']); "
        "phase=os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']; "
        "cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES']); "
        f"Path({str(envelope_path)!r}).write_text(json.dumps(dict(parent_pid=parent,"
        "phase_path=phase,launch_cap_bytes=cap)))"
    )
    result = supervise(
        [sys.executable, "-c", worker],
        tmp_path / "watchdog",
        wall_seconds=10,
        interval=0.05,
        grace_seconds=0.2,
        phase_path=phase_path,
        pss_sampling_policy="disabled_by_profile",
    )

    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert result["classification"] == "COMPLETED"
    assert result["leader_exit_code"] == 0
    assert envelope["parent_pid"] == os.getpid()
    assert envelope["phase_path"] == str(phase_path.resolve())
    assert envelope["launch_cap_bytes"] > 0



def test_explicit_accounting_root_includes_service_wrapper_rss_and_clears_children(
    tmp_path,
):
    directory = tmp_path / "run"
    monitor_pid_path = tmp_path / "monitor.pid"
    monitor = f"""
import json,os,sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
root_pid = int(os.environ["TASK40_TEST_TREE_ROOT_PID"])
Path({str(monitor_pid_path)!r}).write_text(str(os.getpid()))
summary = supervise(
    [sys.executable, "-c", "print('checker complete')"],
    Path({str(directory)!r}),
    wall_seconds=10,
    interval=.05,
    grace_seconds=.2,
    tree_accounting_root_pid=root_pid,
)
print(json.dumps(summary))
"""
    root_pid = os.getpid()
    process = subprocess.run(
        [sys.executable, "-c", monitor],
        env={**os.environ, "TASK40_TEST_TREE_ROOT_PID": str(root_pid)},
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads((directory / "summary.json").read_text())
    monitor_pid = int(monitor_pid_path.read_text())
    rows = [
        json.loads(line)
        for line in (directory / "resources.jsonl").read_text().splitlines()
    ]

    assert summary["descendants_cleared"] is True
    assert summary["sampled_process_tree_rss_peak_bytes"] > 0
    assert Path(f"/proc/{root_pid}").exists()
    assert rows
    assert all(row["root_pid"] == root_pid for row in rows)
    assert any(
        member["pid"] == root_pid
        for row in rows
        for member in row["members"]
    )
    assert any(
        member["pid"] == monitor_pid
        for row in rows
        for member in row["members"]
    )
    assert rows[-1]["live_or_unreaped_children"] == []


@pytest.mark.parametrize('terminate', [False, True])
def test_orphan_setsid_child_is_sampled_and_reaped(tmp_path, terminate):
    directory = tmp_path / 'run'
    proof = tmp_path / 'proof'
    child = (
        'import os,signal,time,pathlib; os.setsid(); '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        'payload=bytearray(20_000_000); '
        f'pathlib.Path({str(proof)!r}).write_text(str(os.getpid())); '
        f'time.sleep({60 if terminate else 1.5})'
    )
    worker = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
    result = subprocess.run(
        [sys.executable, '-m', 'benchmarks.subreaper_watchdog',
         '--directory', str(directory), '--wall-seconds', '2' if terminate else '10',
         '--interval', '.05', '--grace-seconds', '.1', '--',
         sys.executable, '-c', worker], capture_output=True, text=True)
    assert result.returncode == (2 if terminate else 0), result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    child_pid = int(proof.read_text())
    assert child_pid in summary['observed_child_pids']
    assert not Path(f'/proc/{child_pid}').exists()
    assert summary['descendants_cleared'] and summary['cache_metadata_stable']
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    adopted = [row for row in rows if row['exit_code'] == 0
               and child_pid in row['live_or_unreaped_children']]
    assert adopted, 'sampling must continue after the worker leader exits'
    assert any(member['pid'] == child_pid and member['rss_bytes'] > 20_000_000
               for row in adopted for member in row['members'])
    assert rows[-1]['live_or_unreaped_children'] == []
    assert set(summary['global_swap_activity']['delta']) == {'pswpin_pages', 'pswpout_pages'}


def test_monitor_failure_cleans_live_child_and_records_original_error(tmp_path):
    directory, proof = tmp_path / 'run', tmp_path / 'proof'
    worker = ('import os,time,pathlib; '
              f'pathlib.Path({str(proof)!r}).write_text(str(os.getpid())); time.sleep(60)')
    monitor = f'''
import json,sys,time
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
def broken(*args, **kwargs):
    deadline=time.monotonic()+3
    while not Path({str(proof)!r}).exists() and time.monotonic()<deadline:
        time.sleep(.01)
    raise OSError('injected sampler failure with live child')
watchdog.process_tree_snapshot=broken
result=watchdog.supervise([sys.executable,'-c',{worker!r}],Path({str(directory)!r}),wall_seconds=10,interval=.05)
print(json.dumps(result))
'''
    process = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads((directory / 'summary.json').read_text())
    assert result['classification'] == 'MONITORING_FAILED'
    assert result['exception_stage'] == 'resource_sample'
    assert result['exception_type'] == 'OSError'
    assert 'injected sampler failure' in result['exception_message']
    assert result['descendants_cleared']
    assert result['sampled_process_tree_rss_peak_bytes'] is None
    assert not Path('/proc/' + proof.read_text()).exists()


def test_solve_deadline_interrupts_child_without_waiting_for_pc_return(tmp_path):
    directory, phase = tmp_path / 'run', tmp_path / 'phase.json'
    worker = ('import json,os,time,pathlib,signal; '
              'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
              'p=pathlib.Path(os.environ["PHYSICAL_WATCHDOG_PHASE_PATH"]); '
              'p.write_text(json.dumps(dict(phase="solve",phase_started_monotonic=time.monotonic(),stage="inner_pc_blocked"))); '
              'time.sleep(60)')
    monitor = f'''
import sys,json
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
summary=supervise([sys.executable,'-c',{worker!r}],Path({str(directory)!r}),wall_seconds=20,
    solve_seconds=.3,phase_path=Path({str(phase)!r}),interval=.05,grace_seconds=.1)
print(json.dumps(summary))
'''
    process = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    result = json.loads((directory / 'summary.json').read_text())
    assert result['classification'] == 'PERFORMANCE_CONTROLLED_STOP'
    assert result['elapsed_seconds'] < 10 and result['descendants_cleared']
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert any(row['worker_phase'].get('stage') == 'inner_pc_blocked' for row in rows)


@pytest.mark.parametrize('resource_stop', [False, True])
def test_profile_opt_in_grace_preserves_safe_record_but_resource_kills_immediately(tmp_path, resource_stop):
    directory, ready, safe = tmp_path/'run', tmp_path/'ready', tmp_path/'safe'
    worker = f'''
import os,signal,time,pathlib,sys
def stop(*args):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(2.1)
    pathlib.Path({str(safe)!r}).write_text('last safe')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))
time.sleep(60)
'''
    monitor = f'''
import sys,json
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
original = watchdog.process_tree_snapshot
def sample(*args, **kwargs):
    result = original(*args, **kwargs)
    if {resource_stop!r} and Path({str(ready)!r}).exists():
        result['rss_bytes'] = 10**15  # Inject the Gate, do not allocate this memory.
    return result
watchdog.process_tree_snapshot = sample
result = watchdog.supervise([sys.executable,'-c',{worker!r}],Path({str(directory)!r}),
    wall_seconds={10 if resource_stop else .5}, interval=.05, grace_seconds=3,
    hard_stop_immediate=True)
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads((directory/'summary.json').read_text())
    assert summary['descendants_cleared'] and not Path('/proc/'+ready.read_text()).exists()
    if resource_stop:
        assert summary['classification'] == 'RESOURCE_CONTROLLED_STOP'
        assert 'first_SIGKILL' in summary and 'first_SIGTERM' not in summary
        assert not safe.exists()
    else:
        assert summary['classification'] == 'PERFORMANCE_CONTROLLED_STOP'
        assert safe.read_text() == 'last safe'
        assert 'first_SIGTERM' in summary and 'first_SIGKILL' not in summary
