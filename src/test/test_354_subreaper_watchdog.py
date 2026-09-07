"""Real subprocess lifecycle checks, including setsid after leader exit."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


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
