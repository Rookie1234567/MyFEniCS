"""Tiny clock gate and parent/worker wiring checks; no PDE construction."""
import json
import subprocess
import sys

import pytest

from src.runners.workflow_timebase import TimebaseInconsistency, checked_interval


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
