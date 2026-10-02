"""V24 immutable UTC/monotonic window and durable conservative accounting."""
import json,os,time
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json,_json_metadata
from src.solvers.exact_recycle_window import evaluate_window

TMP=ROOT/'tmp/task042/v24';WINDOW_PATH=TMP/'window.json'
LEDGER_PATH=TMP/'ledger.json';JOURNAL_PATH=TMP/'progress_journal.jsonl'
CAPS=dict(actions=45000,L8=25000,local_lu_solve=210000,local_triangular_pass=420000,
          R_triangular=14000,audits=160,field_states=12,block_assemblies=1,local_factors=8,
          DL_SVD=1,factor_readers=5)

def snapshot():
    return evaluate_window(json.loads(WINDOW_PATH.read_text()),utc_seconds=time.time(),monotonic=time.monotonic(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())

def require_live(*,heavy=True,margin=0):
    row=snapshot()
    if row['heavy_remaining_seconds' if heavy else 'total_remaining_seconds']<=margin:raise RuntimeError('immutable V24 deadline reached')
    return row

def journal(event,**fields):
    row=dict(event=event,clock=snapshot(),shared_workstation=True,**fields)
    with JOURNAL_PATH.open('a') as f:f.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    return row

def ledger():
    if not LEDGER_PATH.exists():write_json(LEDGER_PATH,dict(charged=dict.fromkeys(CAPS,0),runs=[],routes={},active=None,closed=False,
        reentries=0,cooldown_seconds=0.,repairs=[]))
    return json.loads(LEDGER_PATH.read_text())

def guard_worker_parent():
    import ctypes,signal
    expected=int(os.environ['TASK042_WATCHDOG_PARENT_PID']);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:raise RuntimeError('V24 own supervisor disappeared')
    require_live()

def settle_run(directory,summary,launch_wall_seconds):
    row=ledger();active=row['active']
    if active is None:active=dict(directory=str(directory),source_sha=summary.get('source_state',{}).get('source_sha'),completed=dict.fromkeys(CAPS,0),upper=dict.fromkeys(CAPS,0))
    if active['directory']!=str(directory):raise ValueError('V24 owned actor accounting differs')
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    charged=active['completed'] if clean else active['upper']
    for key,value in charged.items():row['charged'][key]+=value
    name=summary['stage'].removeprefix('V24-');route=row['routes'].setdefault(name,dict(wall_seconds=0.,actions=0))
    route['wall_seconds']+=launch_wall_seconds;route['actions']+=charged['actions']
    item=dict(directory=str(directory),stage=name,source_sha=active['source_sha'],classification=summary['classification'],
        exact_counts=clean,charged=charged,completed=active['completed'],upper=active['upper'],launch_wall_seconds=launch_wall_seconds,
        rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],descendants_cleared=summary['descendants_cleared'])
    row['active']=None;row['runs'].append(item);write_json(LEDGER_PATH,row);journal('one_run_accounted',run=item)
    return row
