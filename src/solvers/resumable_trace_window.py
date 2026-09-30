"""V17 immutable seven-hour deadline and durable, monotone campaign ledger."""
import ctypes
import json
import os
import signal
import time
from datetime import datetime, timezone
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json, _json_metadata

WINDOW_PATH=ROOT/'tmp/task042/v17/window.json'
JOURNAL_PATH=ROOT/'tmp/task042/v17/progress_journal.jsonl'
BUDGET_PATH=ROOT/'tmp/task042/v17/route_budget.json'
LEDGER_PATH=ROOT/'tmp/task042/v17/ledger.json'


def snapshot():
    row=json.loads(WINDOW_PATH.read_text())
    elapsed=max(time.time()-datetime.fromisoformat(row['start_utc']).timestamp(),time.monotonic()-row['start_monotonic'],0.)
    return dict(row,elapsed_seconds=elapsed,heavy_remaining_seconds=max(0.,row['heavy_limit_seconds']-elapsed),
                total_remaining_seconds=max(0.,row['total_limit_seconds']-elapsed))


def journal(event,**fields):
    row=dict(event=event,utc=datetime.now(timezone.utc).isoformat(),shared_workstation=True,
             heavy_remaining_seconds=snapshot()['heavy_remaining_seconds'],**fields)
    with JOURNAL_PATH.open('a') as stream:
        stream.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    return row


def freeze_route_budget():
    if BUDGET_PATH.exists():return json.loads(BUDGET_PATH.read_text())
    T=snapshot()['heavy_remaining_seconds']; B=min(9000,int((T-900)//2))
    row=dict(uniform_route_wall_seconds=max(0,B),GMRES_reserved_seconds=min(900,.2*max(0,B)),
             heavy_remaining_at_freeze_seconds=T,formula='min(9000, floor((T-900)/2))',immutable=True)
    write_json(BUDGET_PATH,row);journal('uniform_library_budget_frozen',**row)
    return row


def ledger():
    if not LEDGER_PATH.exists():
        empty=dict(actions_upper=0,audits_upper=0,new_A_columns=0,image_QR=0,field_states=0,
                   runs=[],cooldown_seconds=0.,reentries=0,repairs=[],closed=False,
                   routes={k:dict(wall_seconds=0.,actions_upper=0,new_updates=0,reentries=0,
                                 correction_restarts=0,status='READY') for k in ('GPOLY','GNN')})
        write_json(LEDGER_PATH,empty)
    return json.loads(LEDGER_PATH.read_text())


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    expected=int(os.environ[variable]);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:
        raise RuntimeError('own V17 supervisor disappeared')
    if snapshot()['heavy_remaining_seconds']<=0:raise RuntimeError('immutable V17 heavy deadline reached')


def settle_run(directory,summary,launch_wall_seconds):
    """Supervisor-owned accounting survives worker kill; upper bounds charged."""
    row=ledger();active=row.pop('active',None)
    if active is not None and active['directory']!=str(directory):raise ValueError('V17 active ledger ownership differs')
    if active is None:
        name=summary['stage'].removeprefix('V17-')
        library=name.removeprefix('GMRES_')
        active=dict(stage=name,family=library if library in row['routes'] else None,
                    actions_lower=0,actions_upper=64,audits_lower=0,audits_upper=2,
                    updates_lower=0,updates_upper=0,
                    source_sha=summary.get('source_state',{}).get('source_sha'))
    # Older failed-loading metadata may still carry the formal V17 prefix.
    # Preserve its exact directory/source and charged bounds while normalizing
    # only the library key; a different live owner remains an error above.
    active['stage']=active['stage'].removeprefix('V17-')
    name=active['stage'].removeprefix('GMRES_')
    active['family']=name if name in row['routes'] else None
    active.setdefault('audits_lower',0)
    active.setdefault('audits_upper',active['audits_lower']+2)
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    upper=active['actions_lower'] if clean else active['actions_upper']
    audits=active['audits_lower'] if clean else active['audits_upper']
    updates=active['updates_lower'] if clean else active['updates_upper']
    row['actions_upper']+=upper;row['audits_upper']+=audits
    for key in ('new_A_columns','image_QR','field_states'):row[key]+=active.get(key,0)
    family=active['family']
    if family:
        route=row['routes'][family];route['wall_seconds']+=launch_wall_seconds
        route['actions_upper']+=upper;route['new_updates']+=updates
        route['correction_restarts']=max(route['correction_restarts'],active.get('correction_restarts',0))
    row['runs'].append(dict(directory=str(directory),stage=active['stage'],family=family,
        classification=summary['classification'],source_sha=active.get('source_sha'),
        actions_lower=active['actions_lower'],actions_upper=upper,audits_lower=active['audits_lower'],audits_upper=audits,
        updates_lower=active['updates_lower'],updates_upper=updates,launch_wall_seconds=launch_wall_seconds,
        descendants_cleared=summary['descendants_cleared'],rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],
        swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],numeric_io=active.get('numeric_io',{}),exact_counts=clean))
    write_json(LEDGER_PATH,row);journal('run_accounted',run=row['runs'][-1])
    return row
