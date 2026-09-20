"""Real subprocess lifecycle checks, including setsid after leader exit."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

V3_HEADROOM_BYTES = 128 * 1024**3
V3_EFFECTIVE_AVAILABLE_BYTES = 300 * 1024**2 + V3_HEADROOM_BYTES + 1


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
def broken(*args):
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


def test_measured_rss_policy_keeps_global_swap_observe_only_and_declares_warning(tmp_path):
    directory = tmp_path / 'run'
    worker = 'import time; time.sleep(60)'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
calls = [0]
def envelope():
    return dict(launch_cap_bytes=1, planning_cap_bytes=1,
                effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
def swap():
    calls[0] += 1
    return dict(pswpin_pages=0, pswpout_pages=max(0, calls[0]-1))
watchdog.memory_envelope = envelope
watchdog.vmstat_swap_pages = swap
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=.3, interval=.05, grace_seconds=.1, hard_stop_immediate=True,
    stop_on_global_swap=True, resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    assert summary['classification'] == 'PERFORMANCE_CONTROLLED_STOP'
    assert summary['resource_stop_policy'] == 'measured_tree_rss_only_v3'
    assert summary['rss_hard_limit_bytes'] == 300*1024**2
    assert summary['rss_warning_bytes'] == 270*1024**2
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert any(row['global_swap_stop_reason'] == 'GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED'
               for row in rows)
    assert any(row['swap_observation']['classification'] == 'global_swap_only'
               for row in rows)
    assert any(row['swap_bytes'] == 0 and row['fault_counters']['members']
               for row in rows)
    assert all('start_ticks' in member
               for row in rows for member in row['fault_counters']['members'].values()
               if member is not None)
    assert summary['descendants_cleared']


def test_measured_rss_policy_stops_on_scaled_rss_gate(tmp_path):
    directory = tmp_path / 'run'
    worker = 'import time; time.sleep(60)'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
original = watchdog.process_tree_snapshot
def over_gate(*args, **kwargs):
    sample = original(*args, **kwargs)
    sample['rss_bytes'] = 301*1024**2
    return sample
watchdog.process_tree_snapshot = over_gate
watchdog.memory_envelope = lambda: dict(
    launch_cap_bytes=1, planning_cap_bytes=1,
    effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=None, interval=.05, grace_seconds=.1, hard_stop_immediate=True,
    stop_on_global_swap=True, resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    assert summary['classification'] == 'RESOURCE_CONTROLLED_STOP'
    assert 'first_SIGKILL' in summary and summary['descendants_cleared']


def test_measured_rss_policy_records_task_swap_without_stopping(tmp_path):
    directory = tmp_path / 'run'
    worker = 'import time; time.sleep(60)'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
original = watchdog.process_tree_snapshot
def task_swap(*args, **kwargs):
    sample = original(*args, **kwargs)
    sample['swap_bytes'] = 64 * 1024
    return sample
watchdog.process_tree_snapshot = task_swap
watchdog.memory_envelope = lambda: dict(
    launch_cap_bytes=1, planning_cap_bytes=1,
    effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
watchdog.vmstat_swap_pages = lambda: dict(pswpin_pages=0, pswpout_pages=0)
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=.3, interval=.05, grace_seconds=.1, hard_stop_immediate=True,
    resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    assert summary['classification'] == 'PERFORMANCE_CONTROLLED_STOP'
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert any(row['swap_observation']['classification'] == 'task_swap_only'
               for row in rows)


def test_measured_rss_policy_recovers_from_short_unreadable_sample(tmp_path):
    directory = tmp_path / 'run'
    worker = 'import time; time.sleep(60)'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
original = watchdog.process_tree_snapshot
calls = [0]
def transient(*args, **kwargs):
    sample = original(*args, **kwargs)
    calls[0] += 1
    if calls[0] <= 2:
        sample['all_status_readable'] = False
    return sample
watchdog.process_tree_snapshot = transient
watchdog.memory_envelope = lambda: dict(
    launch_cap_bytes=1, planning_cap_bytes=1,
    effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=.3, interval=.05, grace_seconds=.1,
    resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    assert summary['classification'] == 'PERFORMANCE_CONTROLLED_STOP'
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert any(row.get('monitoring_retry', {}).get('attempt') == 1 for row in rows)
    assert any(row['all_status_readable'] for row in rows[2:])


def test_measured_rss_policy_rejects_startup_capacity_below_gate_plus_headroom(tmp_path, monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog
    monkeypatch.setattr(watchdog, 'memory_envelope', lambda: dict(
        launch_cap_bytes=10**15, planning_cap_bytes=10**15,
        effective_available_bytes=900*1024**2, reserve_bytes=100*1024**2))
    with pytest.raises(RuntimeError, match='startup capacity conflicts'):
        watchdog.supervise(
            [sys.executable, '-c', 'pass'], tmp_path / 'run', wall_seconds=None,
            resource_stop_policy='measured_tree_rss_only_v3',
            rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
            startup_headroom_bytes=V3_HEADROOM_BYTES)


def test_measured_rss_policy_labels_monitoring_loss_after_bounded_retries(tmp_path):
    directory = tmp_path / 'run'
    worker = 'import time; time.sleep(60)'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
original = watchdog.process_tree_snapshot
def unreadable(*args, **kwargs):
    sample = original(*args, **kwargs)
    sample['all_status_readable'] = False
    return sample
watchdog.process_tree_snapshot = unreadable
watchdog.memory_envelope = lambda: dict(
    launch_cap_bytes=1, planning_cap_bytes=1,
    effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=None, interval=.05, grace_seconds=.1, hard_stop_immediate=True,
    resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    assert summary['classification'] == 'MONITORING_LOST'
    assert summary['descendants_cleared']
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert max(row['monitoring_retry']['attempt'] for row in rows) >= 4


def test_measured_rss_policy_keeps_normal_exit_tail_and_pid_identity(tmp_path, monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog
    directory, proof = tmp_path / 'run', tmp_path / 'child'
    child = (
        'import os,time,pathlib; '
        f'pathlib.Path({str(proof)!r}).write_text(str(os.getpid())); time.sleep(.35)'
    )
    worker = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
    monitor = f'''
import json,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
watchdog.memory_envelope = lambda: dict(
    launch_cap_bytes=1, planning_cap_bytes=1,
    effective_available_bytes={V3_EFFECTIVE_AVAILABLE_BYTES}, reserve_bytes=100*1024**2)
result = watchdog.supervise(
    [sys.executable, '-c', {worker!r}], Path({str(directory)!r}),
    wall_seconds=None, interval=.05, grace_seconds=.1,
    resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes={V3_HEADROOM_BYTES})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((directory / 'summary.json').read_text())
    child_pid = int(proof.read_text())
    assert summary['classification'] == 'COMPLETED'
    assert child_pid in summary['observed_child_pids'] and summary['descendants_cleared']
    rows = [json.loads(line) for line in (directory / 'resources.jsonl').read_text().splitlines()]
    assert rows[-1]['live_or_unreaped_children'] == []

    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
    try:
        fields = open(f'/proc/{process.pid}/stat').read().rsplit(')', 1)[1].split()
        current_ticks = int(fields[19])
        calls = []
        monkeypatch.setattr(watchdog, '_children', lambda: {
            process.pid: (os.getpid(), current_ticks + 1)
        })
        monkeypatch.setattr(watchdog.os, 'kill', lambda *args: calls.append(args))
        watchdog._signal_children(watchdog.signal.SIGTERM)
        assert calls == []
    finally:
        process.terminate()
        process.wait(timeout=5)


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
def sample(*args):
    result = original(*args)
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
