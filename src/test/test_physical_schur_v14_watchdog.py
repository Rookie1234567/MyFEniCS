"""A blocked PC is killed independently of the whole solve deadline."""

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize('active_limit,complete_pc', [(.2, False), (1., True), (None, False)])
def test_pc_deadline_is_opt_in_and_only_counts_active_pc(tmp_path, active_limit, complete_pc):
    run = tmp_path/'watchdog'
    phase = tmp_path/'phase.json'
    worker = f'''
import json,os,pathlib,signal,time
from src.runners.workflow_timebase import clock_sample
signal.signal(signal.SIGTERM, signal.SIG_IGN)
p=pathlib.Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH'])
start=clock_sample()
record={{'phase':'solve','phase_started_clock':start,
         'phase_started_monotonic':start['monotonic'],
         'active_pc':{{'sequence':1,'started_clock':start}}}}
def save():
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(record))
    tmp.replace(p)
save()
if {complete_pc!r}:
    time.sleep(.05)
    record['active_pc']=None
    save()
    time.sleep(1.2)
else:
    time.sleep({60 if active_limit is not None else .4})
'''
    monitor = f'''
import json,sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
result=supervise([sys.executable,'-c',{worker!r}],Path({str(run)!r}),
    wall_seconds=20,solve_seconds=15,active_pc_seconds={active_limit!r},
    phase_path=Path({str(phase)!r}),interval=.02,grace_seconds=.1,
    hard_stop_immediate=True,timebase_guard=True,timebase_policy='conservative_realtime')
print(json.dumps(result))
'''
    process = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads((run/'summary.json').read_text())
    assert result['descendants_cleared']
    rows = [json.loads(x) for x in (run/'resources.jsonl').read_text().splitlines()]
    if active_limit is not None and not complete_pc:
        assert result['classification'] == 'PC_TIME_CONTROLLED_STOP'
        assert 'first_SIGKILL' in result
        assert 'first_SIGTERM' not in result
        assert any(x.get('pc_clock_interval', {}).get('budget_seconds', 0) >= active_limit
                   for x in rows)
        assert result['elapsed_seconds'] < 3
    else:
        assert result['classification'] == 'COMPLETED'
        assert 'first_SIGKILL' not in result
    starts = [x['worker_phase']['phase_started_clock'] for x in rows
              if x.get('worker_phase', {}).get('phase') == 'solve']
    assert starts and all(x == starts[0] for x in starts)
    if active_limit is None:
        assert not any('pc_clock_interval' in x for x in rows)


def test_observe_only_records_overruns_without_time_termination(tmp_path):
    run = tmp_path / 'observe_watchdog'
    phase = tmp_path / 'phase.json'
    worker = '''import json,os,pathlib,time
from src.runners.workflow_timebase import clock_sample
p=pathlib.Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH'])
c=clock_sample()
record=dict(
    phase='solve', phase_started_monotonic=c['monotonic'],
    phase_started_clock=c, active_pc=dict(sequence=1, started_clock=c))
tmp=p.with_suffix('.tmp')
tmp.write_text(json.dumps(record))
tmp.replace(p)
time.sleep(.25)
'''
    monitor = f'''import json,sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
result=supervise([sys.executable,'-c',{worker!r}],Path({str(run)!r}),
    wall_seconds=.05, solve_seconds=.05, active_pc_seconds=.05,
    phase_path=Path({str(phase)!r}), interval=.01, grace_seconds=.1,
    hard_stop_immediate=True, timebase_guard=True,
    timebase_policy='conservative_realtime', time_policy='observe_only')
print(json.dumps(result))
'''
    process = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads((run / 'summary.json').read_text())
    assert summary['classification'] == 'COMPLETED'
    assert summary['time_policy'] == 'observe_only'
    assert summary['time_gate_evaluated'] is False
    assert summary['time_exceeded']['workflow']
    assert summary['time_exceeded']['solve']
    assert summary['time_exceeded']['active_pc']
    assert 'first_SIGKILL' not in summary
    assert summary['time_end_observation']['exceeded']


def test_observe_only_does_not_bypass_resource_tree_cap(tmp_path):
    run = tmp_path / 'observe_resource_watchdog'
    monitor = f'''import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
supervise([sys.executable,'-c','import time;time.sleep(60)'],
    Path({str(run)!r}), wall_seconds=60, interval=.01, grace_seconds=.1,
    hard_stop_immediate=True, tree_cap_bytes=1, time_policy='observe_only')
'''
    process = subprocess.run([sys.executable, '-c', monitor], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads((run / 'summary.json').read_text())
    assert summary['classification'] == 'RESOURCE_CONTROLLED_STOP'
    assert summary['time_policy'] == 'observe_only'
    assert summary['descendants_cleared']
