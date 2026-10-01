"""V19 immutable window, four independent route quotas, monotone costs."""
import json
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.resumable_trace_window import snapshot as window_snapshot

WINDOW_PATH=ROOT/'tmp/task042/v19/window.json'
JOURNAL_PATH=ROOT/'tmp/task042/v19/progress_journal.jsonl'
BUDGET_PATH=ROOT/'tmp/task042/v19/route_budget.json'
LEDGER_PATH=ROOT/'tmp/task042/v19/ledger.json'


def snapshot():return window_snapshot(WINDOW_PATH)


def journal(event,**fields):
    # Same tested serializer/fsync, explicitly bind this profile's own paths.
    from datetime import datetime,timezone
    import os
    from src.runners.task042_shared import _json_metadata
    row=dict(event=event,utc=datetime.now(timezone.utc).isoformat(),shared_workstation=True,
             heavy_remaining_seconds=snapshot()['heavy_remaining_seconds'],**fields)
    with JOURNAL_PATH.open('a') as stream:
        stream.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    return row


def freeze_route_budget():
    if BUDGET_PATH.exists():return json.loads(BUDGET_PATH.read_text())
    remaining=snapshot()['heavy_remaining_seconds'];B=max(0,min(2700,int((remaining-900)//4)))
    row=dict(uniform_route_wall_seconds=B,heavy_remaining_at_freeze_seconds=remaining,
        formula='min(2700, floor((heavy_remaining-900)/4))',immutable=True)
    write_json(BUDGET_PATH,row);journal('uniform_method_library_budget_frozen',**row);return row


def ledger():
    if not LEDGER_PATH.exists():
        routes={a+'_'+f:dict(wall_seconds=0.,actions_upper=0,new_updates=0,status='READY')
                for a in ('P','L') for f in ('GPOLY','GNN')}
        # Only these library rows own cooldown permissions; not numerical quotas.
        routes.update({f:dict(reentries=0,status='READY') for f in ('GPOLY','GNN')})
        write_json(LEDGER_PATH,dict(actions_upper=0,audits_upper=0,new_A_columns=0,image_QR=0,field_states=0,
            runs=[],cooldown_seconds=0.,reentries=0,repairs=[],closed=False,routes=routes))
    return json.loads(LEDGER_PATH.read_text())


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    import ctypes,os,signal
    expected=int(os.environ[variable]);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:raise RuntimeError('own V19 supervisor disappeared')
    if snapshot()['heavy_remaining_seconds']<=0:raise RuntimeError('immutable V19 heavy deadline reached')


def settle_run(directory,summary,launch_wall_seconds):
    from src.io.post_lsqr_polish import stage_route
    row=ledger();active=row.pop('active',None)
    stage=summary['stage'].removeprefix('V19-');algorithm,family=stage_route(stage)
    if active is not None and active['directory']!=str(directory):raise ValueError('V19 active ownership differs')
    if active is None:
        active=dict(stage=stage,family=family,algorithm=algorithm,actions_lower=0,actions_upper=320 if family else 64,
            audits_lower=0,audits_upper=2,updates_lower=0,updates_upper=0,
            arnoldi_lower=0,arnoldi_upper=256 if algorithm=='P' else 0,source_sha=summary.get('source_state',{}).get('source_sha'))
    if (active['family'],active['algorithm'])!=(family,algorithm):raise ValueError('V19 library/method differs')
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    charged={key:active[key+'_lower' if clean else key+'_upper'] for key in ('actions','audits','updates','arnoldi')}
    row['actions_upper']+=charged['actions'];row['audits_upper']+=charged['audits']
    for key in ('new_A_columns','image_QR','field_states'):row[key]+=active.get(key,0)
    if family:
        route=row['routes'][stage];route['wall_seconds']+=launch_wall_seconds;route['actions_upper']+=charged['actions']
        route['new_updates']+=charged['updates']
    run=dict(directory=str(directory),stage=stage,family=family,algorithm=algorithm,classification=summary['classification'],
        source_sha=active.get('source_sha'),launch_wall_seconds=launch_wall_seconds,
        descendants_cleared=summary['descendants_cleared'],rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],
        swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],exact_counts=clean,numeric_io=active.get('numeric_io',{}),
        internal_Arnoldi_iterations=None if algorithm=='L' else charged['arnoldi'])
    for key in ('actions','audits','updates','arnoldi'):run[key+'_lower']=active[key+'_lower'];run[key+'_upper']=charged[key]
    row['runs'].append(run);write_json(LEDGER_PATH,row);journal('run_accounted',run=run);return row
