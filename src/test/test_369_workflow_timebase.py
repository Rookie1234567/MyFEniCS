"""Tiny clock gate and parent/worker wiring checks; no PDE construction."""
import json
import subprocess
import sys

import pytest

from src.runners.workflow_timebase import (TimebaseInconsistency, checked_interval,
    ClockBudget, CONSERVATIVE_REALTIME)


def sample(mono, boot, utc):
    return dict(monotonic=mono, boottime=boot, utc_ns=int(utc*1e9))


def test_conservative_budget_and_tolerance():
    result = checked_interval(sample(0, 0, 0), sample(1000, 1008, 1004))
    assert result['budget_seconds'] == 1008
    for end in (sample(1000, 1020, 1000), sample(1, 1, 8), sample(-1, 1, 1)):
        with pytest.raises(TimebaseInconsistency):
            checked_interval(sample(0, 0, 0), end)
    with pytest.raises(TimebaseInconsistency):
        checked_interval(dict(monotonic=0, boottime=None, utc_ns=0), sample(1, 1, 1))


def test_worker_records_error_before_raising(tmp_path, monkeypatch):
    import src.runners.physical_intermediate as worker
    monkeypatch.setenv('PHYSICAL_TIMEBASE_GUARD', '1')
    monkeypatch.setattr(worker, 'clock_sample', lambda: sample(0, 0, 0))
    phase = tmp_path/'phase.json'
    ledger = worker.WorkflowLedger(tmp_path, phase)
    ledger.set_phase('solve')
    monkeypatch.setattr(worker, 'clock_sample', lambda: sample(1, 1, 8))
    with pytest.raises(TimebaseInconsistency):
        ledger.marker('injected_difference', {})
    record = json.loads(phase.read_text())
    assert record['clock_error'] and record['clock_info']['boottime']['available']
    assert record['phase_started_clock'] == sample(0, 0, 0)


@pytest.mark.parametrize('bad_clock', [False, True])
def test_parent_stops_and_clears_worker(tmp_path, bad_clock):
    directory, phase = tmp_path/'run', tmp_path/'phase.json'
    worker = '''import os,time,json
from pathlib import Path
from src.runners.workflow_timebase import clock_sample
c=clock_sample()
Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']).write_text(json.dumps(dict(
    phase='solve',phase_started_monotonic=c['monotonic'],phase_started_clock=c,
    clock_error=ERROR)))
time.sleep(60)
'''.replace('ERROR', repr('injected UTC disagreement' if bad_clock else None))
    parent = f'''import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
supervise([sys.executable,'-c',{worker!r}],Path({str(directory)!r}),wall_seconds=15,
    solve_seconds=.2,phase_path=Path({str(phase)!r}),interval=.05,grace_seconds=.1,
    hard_stop_immediate=True,timebase_guard=True)
'''
    result = subprocess.run([sys.executable, '-c', parent], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads((directory/'summary.json').read_text())
    assert summary['classification'] == ('TIMEBASE_INCONSISTENCY' if bad_clock
                                         else 'PERFORMANCE_CONTROLLED_STOP')
    assert summary['descendants_cleared'] and summary['clock_end']
    rows = [json.loads(line) for line in (directory/'resources.jsonl').read_text().splitlines()]
    assert any(row.get('solve_clock_interval') for row in rows) if not bad_clock else summary['clock_error']


def test_realtime_accumulation_never_refunds_and_keeps_monotone_gate():
    budget = ClockBudget(sample(0, 0, 0), policy=CONSERVATIVE_REALTIME)
    assert budget.update(sample(1, 1, 9))['budget_seconds'] == 9
    result = budget.update(sample(2, 2, 2))
    assert result['budget_seconds'] == 10  # UTC reversal cannot refund the forward jump.
    assert result['step']['elapsed_seconds']['utc'] == -7
    assert budget.update(sample(3, 3, 11))['budget_seconds'] == 19
    assert budget.utc_positive_excess_seconds == 16
    for end in (sample(-1, 0, 1000), sample(10, 16, 100000),
                dict(monotonic=float('nan'), boottime=0, utc_ns=0),
                dict(monotonic=0, boottime=None, utc_ns=0)):
        with pytest.raises(TimebaseInconsistency):
            checked_interval(sample(0, 0, 0), end, policy=CONSERVATIVE_REALTIME)


def test_worker_opt_in_records_adjustment_without_strict_failure(tmp_path, monkeypatch):
    import src.runners.physical_intermediate as worker
    monkeypatch.setenv('PHYSICAL_TIMEBASE_GUARD', '1')
    monkeypatch.setenv('PHYSICAL_TIMEBASE_POLICY', CONSERVATIVE_REALTIME)
    monkeypatch.setattr(worker, 'clock_sample', lambda: sample(0, 0, 0))
    phase = tmp_path/'phase.json'
    ledger = worker.WorkflowLedger(tmp_path, phase)
    monkeypatch.setattr(worker, 'clock_sample', lambda: sample(1, 1, 9))
    ledger.marker('forward_adjustment', {})
    monkeypatch.setattr(worker, 'clock_sample', lambda: sample(2, 2, 2))
    ledger.marker('backward_adjustment', {})
    record = json.loads(phase.read_text())
    assert 'clock_error' not in record
    assert record['workflow_clock_interval']['budget_seconds'] == 10
    assert record['phase_clock_interval']['budget_seconds'] == 10
    assert record['workflow_clock_interval']['policy'] == CONSERVATIVE_REALTIME


@pytest.mark.parametrize('wall_seconds', [2, 30])
def test_opt_in_parent_charges_utc_jump_and_clears_real_child(tmp_path, wall_seconds):
    directory = tmp_path/'run'
    parent = f'''import sys,time,json
from pathlib import Path
import benchmarks.subreaper_watchdog as w
real=w.clock_sample
start=time.monotonic()
def adjusted():
    c=real()
    if time.monotonic()-start>.1:c['utc_ns']+=8_000_000_000
    return c
w.clock_sample=adjusted
w.supervise([sys.executable,'-c','import time;time.sleep(.3)'],Path({str(directory)!r}),
    wall_seconds={wall_seconds},interval=.05,grace_seconds=.1,
    hard_stop_immediate=True,timebase_guard=True,timebase_policy='conservative_realtime')
'''
    result = subprocess.run([sys.executable, '-c', parent], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads((directory/'summary.json').read_text())
    assert summary['classification'] == ('PERFORMANCE_CONTROLLED_STOP' if wall_seconds == 2 else 'COMPLETED')
    assert summary['descendants_cleared']
    assert summary['workflow_clock_interval']['budget_seconds'] >= 8
    assert 'clock_error' not in summary


@pytest.mark.parametrize('classification', ['COMPLETED', 'RESOURCE_CONTROLLED_STOP', 'USER_CONTROLLED_STOP'])
@pytest.mark.parametrize('bad_final_clock', [False, True])
def test_terminal_manifest_uses_nonoverlapping_parent_charge(tmp_path, monkeypatch, classification, bad_final_clock):
    import src.runners.physical_diagnosis as diagnosis
    import src.runners.task038_launcher as launcher
    monkeypatch.setattr(launcher, '_physical_source_gate', lambda *args: {})
    clocks = iter([sample(0, 0, 0), sample(1, 1, 1), sample(4, 40 if bad_final_clock else 4, 4)])
    monkeypatch.setattr(diagnosis, 'clock_sample', lambda: next(clocks))
    monkeypatch.setattr(diagnosis, 'supervise_diagnosis', lambda *args, **kwargs: dict(
        classification=classification, clock_start=sample(2, 2, 2), clock_end=sample(3, 3, 3),
        workflow_clock_interval=dict(budget_seconds=9)))
    input_path, inventory = tmp_path/'input.dat', tmp_path/'inventory.json'
    input_path.write_text('fixture')
    inventory.write_text('{}')
    root = tmp_path/'diagnosis'
    monkeypatch.setattr(sys, 'argv', ['diagnosis', '--directory', str(root), '--input', str(input_path),
        '--inventory', str(inventory), '--expected-sha', 'a'*40, '--remaining-seconds', '10'])
    assert diagnosis.main() == 2
    record = json.loads((root/'launch.json').read_text())
    assert record['supervision']['classification'] == classification
    if bad_final_clock:
        assert record['final_clock_error']
        assert record['classification'] == ('TIMEBASE_INCONSISTENCY' if classification == 'COMPLETED' else classification)
    else:
        assert record['interval']['budget_seconds'] == 12  # pre2 + parent9 + post1, not endpoint4.
        assert record['classification'] == ('PERFORMANCE_CONTROLLED_STOP' if classification == 'COMPLETED' else classification)


@pytest.mark.parametrize('classification', ['COMPLETED', 'RESOURCE_CONTROLLED_STOP'])
def test_terminal_manifest_records_post_cache_failure(tmp_path, monkeypatch, classification):
    import src.runners.physical_diagnosis as diagnosis
    import src.runners.task038_launcher as launcher
    monkeypatch.setattr(launcher, '_physical_source_gate', lambda *args: {})
    clocks = iter([sample(0, 0, 0), sample(1, 1, 1), sample(4, 4, 4)])
    monkeypatch.setattr(diagnosis, 'clock_sample', lambda: next(clocks))
    monkeypatch.setattr(diagnosis, 'supervise_diagnosis', lambda *args, **kwargs: dict(
        classification=classification, clock_start=sample(2, 2, 2), clock_end=sample(3, 3, 3),
        workflow_clock_interval=dict(budget_seconds=1)))
    calls = []
    def cache_files(*args):
        calls.append(True)
        if len(calls) == 2:
            raise OSError('injected post-cache read failure')
        return []
    monkeypatch.setattr(diagnosis.Path, 'rglob', cache_files)
    input_path, inventory = tmp_path/'input.dat', tmp_path/'inventory.json'
    input_path.write_text('fixture')
    inventory.write_text('{}')
    root = tmp_path/'diagnosis'
    monkeypatch.setattr(sys, 'argv', ['diagnosis', '--directory', str(root), '--input', str(input_path),
        '--inventory', str(inventory), '--expected-sha', 'a'*40, '--remaining-seconds', '10',
        '--cache-path', str(tmp_path/'cache')])
    with pytest.raises(OSError, match='post-cache'):
        diagnosis.main()
    record = json.loads((root/'launch.json').read_text())
    assert record['supervision']['classification'] == classification
    assert record['finalization_error']['type'] == 'OSError'
    assert record['classification'] == ('LAUNCH_OR_FINALIZATION_FAILED' if classification == 'COMPLETED' else classification)
