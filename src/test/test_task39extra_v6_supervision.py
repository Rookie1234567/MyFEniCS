"""Bounded lifecycle witnesses for the new profile's RSS-only supervision."""
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from benchmarks.process_tree_pss_diagnostic import ProcessTreePSSDiagnostic
from benchmarks.task038_full3d_jit_staging import process_tree_snapshot


def test_disabled_profile_never_calls_pss_provider(monkeypatch):
    import benchmarks.task038_full3d_jit_staging as sampler
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PSS_POLICY', 'disabled_by_profile')
    def forbidden(_pid):
        pytest.fail('disabled profile attempted smaps/PSS')
    monkeypatch.setattr(sampler, '_pss_bytes', forbidden)
    sample = process_tree_snapshot(os.getpid(), 'component')
    assert sample['all_status_readable']
    assert sample['rss_bytes'] > 0
    assert sample['pss_bytes'] is None and sample['pss_all_readable'] is None
    assert sample['pss_status'] == 'DISABLED_BY_PROFILE'
    assert all(row['pss_bytes'] is None for row in sample['members'])


def test_slow_diagnostic_does_not_block_or_catch_up():
    release, entered = threading.Event(), threading.Event()
    clock = [10.0]
    calls = []
    def provider():
        calls.append(clock[0])
        entered.set()
        release.wait(2)
        return {'pss_bytes': 123}
    diagnostic = ProcessTreePSSDiagnostic(provider, interval=5, clock=lambda: clock[0])
    assert diagnostic.poll() is None
    assert entered.wait(1)
    clock[0] = 100.0
    started = time.monotonic()
    for _ in range(10):
        assert diagnostic.poll() is None
    assert time.monotonic()-started < .2
    assert len(calls) == 1
    release.set()
    for _ in range(200):
        result = diagnostic.poll()
        if result is not None:
            break
        time.sleep(.005)
    assert result['completed_monotonic'] == 100
    assert result['sample']['pss_bytes'] == 123
    clock[0] = 104.99
    diagnostic.poll()
    assert len(calls) == 1
    clock[0] = 105.0
    diagnostic.poll()
    for _ in range(200):
        if len(calls) == 2:
            break
        time.sleep(.005)
    assert len(calls) == 2


@pytest.mark.parametrize('case', ['normal', 'failed', 'rss_gate', 'slow_pss'])
def test_real_watchdog_tree_lifecycle(tmp_path, case):
    directory = tmp_path / case
    disabled = case != 'slow_pss'
    body = f'''
import json, sys, time
from pathlib import Path
import benchmarks.subreaper_watchdog as w
import benchmarks.task038_full3d_jit_staging as sampler
calls = [0]
def pss(_pid):
    calls[0] += 1
    if {disabled!r}:
        raise AssertionError('smaps provider called in disabled profile')
    time.sleep(.65)
    return 100
sampler._pss_bytes = pss
w.memory_envelope = lambda: dict(launch_cap_bytes=1,
    effective_available_bytes=10**12, reserve_bytes=10**11)
if {case == 'rss_gate'!r}:
    original = w.process_tree_snapshot
    def over_gate(*a, **kw):
        sample = original(*a, **kw)
        sample['rss_bytes'] = 301*1024**2
        return sample
    w.process_tree_snapshot = over_gate
worker = 'import sys,time; time.sleep(.5); sys.exit({7 if case == 'failed' else 0})'
result = w.supervise([sys.executable, '-c', worker], Path({str(directory)!r}),
    wall_seconds=None, interval=.03, grace_seconds=.1, hard_stop_immediate=True,
    resource_stop_policy='measured_tree_rss_only_v3',
    rss_hard_limit_bytes=300*1024**2, rss_warning_bytes=270*1024**2,
    startup_headroom_bytes=128*1024**3,
    pss_sampling_policy={'disabled_by_profile' if disabled else 'sampled'!r})
result['pss_provider_calls'] = calls[0]
print(json.dumps(result))
'''
    completed = subprocess.run([sys.executable, '-c', body], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    expected = {'failed': 'WORKER_FAILED', 'rss_gate': 'RESOURCE_CONTROLLED_STOP'}.get(case, 'COMPLETED')
    assert result['classification'] == expected
    assert result['descendants_cleared'] and not result['remaining_child_pids']
    if disabled:
        assert result['pss_provider_calls'] == 0
        assert result['sampled_process_tree_pss_peak_bytes'] is None
    else:
        assert result['pss_provider_calls'] > 0
        rows = [json.loads(line) for line in (directory/'resources.jsonl').read_text().splitlines()]
        assert len(rows) >= 8
        assert max(row['resource_sample_cost']['wall_seconds'] for row in rows) < .4
    if case == 'rss_gate':
        assert 'first_SIGKILL' in result
    if case in {'normal', 'failed'}:
        assert not any('SIG' in key for key in result)
