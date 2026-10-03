"""Immutable V26 window; counters cover the unique assembly/LU and all probes."""
import json,time
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json,_json_metadata
from src.solvers.exact_recycle_window import evaluate_window

TMP=ROOT/'tmp/task042/v26'
WINDOW_PATH=TMP/'window.json';LEDGER_PATH=TMP/'ledger.json';JOURNAL_PATH=TMP/'progress_journal.jsonl'
CAPS=dict(actions=64,joint_assemblies=1,joint_LU_attempts=1,joint_lu_solve=16,
    explicit_triangular_pass=32,gecon_calls=1,gecon_triangular_pass_upper=22,
    total_triangular_pass_upper=54,factor_readers=2,thin_decompositions=2,port_factors=2,port_solves=128)


def snapshot():
    return evaluate_window(json.loads(WINDOW_PATH.read_text()),utc_seconds=time.time(),monotonic=time.monotonic(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())


def require_live(*,heavy=True,margin=0):
    row=snapshot()
    if row['heavy_remaining_seconds' if heavy else 'total_remaining_seconds']<=margin:raise RuntimeError('immutable V26 deadline reached')
    return row


def auxiliary_wall():
    return sum(json.loads(p.read_text())['elapsed_seconds'] for p in TMP.glob('aux_*/summary.json'))


def journal(event,**fields):
    row=dict(event=event,clock=snapshot(),shared_workstation=True,**fields)
    with JOURNAL_PATH.open('a') as f:f.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');f.flush()
    return row


def ledger():
    if not LEDGER_PATH.exists():write_json(LEDGER_PATH,dict(charged=dict.fromkeys(CAPS,0),runs=[],active=None,closed=False,actor_wall_seconds=0.))
    return json.loads(LEDGER_PATH.read_text())


def validate_increment(charged,completed,key,n=1):
    if key not in CAPS or n<0 or charged[key]+completed[key]+n>CAPS[key]:raise RuntimeError('V26 '+key+' immutable cap')


def guard_worker_parent():
    import ctypes,os,signal
    expected=int(os.environ['TASK042_WATCHDOG_PARENT_PID']);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:raise RuntimeError('V26 own supervisor disappeared')
    require_live()


def settle_run(directory,summary,launch_wall_seconds):
    row=ledger();active=row['active']
    if active is None:active=dict(directory=str(directory),source_sha=summary['source_state']['source_sha'],completed=dict.fromkeys(CAPS,0),upper=dict.fromkeys(CAPS,0))
    if active['directory']!=str(directory):raise ValueError('V26 actor identity differs')
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    charge=active['completed'] if clean else active['upper']
    for key,v in charge.items():row['charged'][key]+=v
    row['actor_wall_seconds']+=summary['elapsed_seconds']
    lower=active['completed'] if clean else dict.fromkeys(CAPS,0)
    if not clean:lower['actions']=active['completed']['actions']
    row['runs'].append(dict(directory=str(directory),source_sha=active['source_sha'],classification=summary['classification'],
        counts=charge,completed=lower,upper=active['upper'],exact_counts=clean,
        actor_wall_seconds=summary['elapsed_seconds'],launch_wall_seconds=launch_wall_seconds,
        rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],
        descendants_cleared=summary['descendants_cleared']))
    row['active']=None;write_json(LEDGER_PATH,row);journal('one_run_accounted',run=row['runs'][-1]);return row
