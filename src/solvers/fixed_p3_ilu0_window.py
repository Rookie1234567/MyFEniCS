"""V20 immutable window and monotone original/PC/setup accounting."""
import json
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.resumable_trace_window import snapshot as window_snapshot

TMP=ROOT/'tmp/task042/v20'
WINDOW_PATH=TMP/'window.json'
LEDGER_PATH=TMP/'ledger.json'
JOURNAL_PATH=TMP/'progress_journal.jsonl'
BUDGET_PATH=TMP/'route_budget.json'
CAPS=dict(actions=35000,audits=120,B0=35000,F=35000,K_assemblies=2,factor_setups=5,field_states=12)


def snapshot():return window_snapshot(WINDOW_PATH)


def journal(event,**fields):
    import os
    from datetime import datetime,timezone
    from src.runners.task042_shared import _json_metadata
    row=dict(event=event,utc=datetime.now(timezone.utc).isoformat(),shared_workstation=True,
             heavy_remaining_seconds=snapshot()['heavy_remaining_seconds'],**fields)
    with JOURNAL_PATH.open('a') as f:
        f.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    return row


def ledger():
    if not LEDGER_PATH.exists():
        row=dict(charged=dict.fromkeys(CAPS,0),runs=[],active=None,closed=False,
                 reentries=0,cooldown_seconds=0.,repairs=[],routes={})
        write_json(LEDGER_PATH,row)
    return json.loads(LEDGER_PATH.read_text())


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    # Common parent-death check has a V19 deadline: use the same mechanism but
    # this profile's own immutable timestamp instead.
    import ctypes,os,signal
    expected=int(os.environ[variable]);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:raise RuntimeError('V20 own supervisor disappeared')
    if snapshot()['heavy_remaining_seconds']<=0:raise RuntimeError('V20 deadline reached')


def settle_run(directory,summary,launch_wall_seconds):
    row=ledger();active=row.pop('active',None)
    if active is None or active['directory']!=str(directory):raise ValueError('V20 accounting actor identity absent/different')
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    charged={k:active['completed'].get(k,0) if clean else active['upper'].get(k,0) for k in CAPS}
    for k,v in charged.items():row['charged'][k]+=v
    name=summary['stage'].removeprefix('V20-')
    route=row['routes'].setdefault(name,dict(wall_seconds=0.))
    route['wall_seconds']+=launch_wall_seconds
    item=dict(directory=str(directory),stage=name,source_sha=active['source_sha'],
              classification=summary['classification'],exact_counts=clean,charged=charged,
              completed=active['completed'],launch_wall_seconds=launch_wall_seconds,
              rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],
              swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],
              descendants_cleared=summary['descendants_cleared'])
    row['active']=None;row['runs'].append(item);write_json(LEDGER_PATH,row)
    journal('one_run_accounted',run=item)
    return row
