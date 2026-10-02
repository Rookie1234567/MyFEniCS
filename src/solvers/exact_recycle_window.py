"""Immutable V21 UTC/monotonic/boot deadline and conservative tree ledger."""
import ctypes
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json, _json_metadata

TMP=ROOT/'tmp/task042/v21'
WINDOW_PATH=TMP/'window.json'
LEDGER_PATH=TMP/'ledger.json'
JOURNAL_PATH=TMP/'progress_journal.jsonl'
CAPS=dict(actions=100000,audits=320,field_states=12)


def evaluate_window(row, *, utc_seconds, monotonic, boot_id):
    utc_elapsed=utc_seconds-datetime.fromisoformat(row['start_utc']).timestamp()
    clocks=[utc_elapsed,0.]
    same_boot=boot_id==row['boot_id']
    if same_boot:clocks.append(monotonic-row['start_monotonic'])
    elapsed=max(clocks)
    return dict(row,observed_utc=datetime.fromtimestamp(utc_seconds,timezone.utc).isoformat(),
        observed_monotonic=monotonic,observed_boot_id=boot_id,monotonic_same_boot=same_boot,
        elapsed_seconds=elapsed,heavy_remaining_seconds=max(0.,row['heavy_limit_seconds']-elapsed),
        total_remaining_seconds=max(0.,row['total_limit_seconds']-elapsed))


def snapshot():
    return evaluate_window(json.loads(WINDOW_PATH.read_text()),utc_seconds=time.time(),
        monotonic=time.monotonic(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())


def require_live(*, heavy=True, margin=0):
    row=snapshot()
    if row['heavy_remaining_seconds' if heavy else 'total_remaining_seconds']<=margin:
        raise RuntimeError('immutable V21 deadline reached; no new test/stage')
    return row


def journal(event,**fields):
    row=dict(event=event,clock=snapshot(),shared_workstation=True,**fields)
    with JOURNAL_PATH.open('a') as f:
        f.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    return row


def ledger():
    if not LEDGER_PATH.exists():
        write_json(LEDGER_PATH,dict(charged=dict.fromkeys(CAPS,0),runs=[],active=None,closed=False,
            reentries=0,cooldown_seconds=0.,repairs=[],routes={}))
    return json.loads(LEDGER_PATH.read_text())


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    expected=int(os.environ[variable]);lib=ctypes.CDLL(None,use_errno=True)
    if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:
        raise RuntimeError('V21 own supervisor disappeared')
    require_live(heavy=True)


def settle_run(directory,summary,launch_wall_seconds):
    row=ledger();active=row.get('active')
    if active is None:
        # Failed before constructing a numerical actor: only loading may occur.
        active=dict(directory=str(directory),source_sha=summary.get('source_state',{}).get('source_sha'),
                    completed=dict.fromkeys(CAPS,0),upper=dict.fromkeys(CAPS,0))
    if active['directory']!=str(directory):raise ValueError('V21 accounting actor ownership differs')
    clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
    charged={k:active['completed'][k] if clean else active['upper'][k] for k in CAPS}
    for k,v in charged.items():row['charged'][k]+=v
    name=summary['stage'].removeprefix('V21-')
    route=row['routes'].setdefault(name,dict(wall_seconds=0.,actions=0))
    route['wall_seconds']+=launch_wall_seconds;route['actions']+=charged['actions']
    item=dict(directory=str(directory),stage=name,source_sha=active['source_sha'],
        classification=summary['classification'],exact_counts=clean,charged=charged,
        completed=active['completed'],upper=active['upper'],launch_wall_seconds=launch_wall_seconds,
        rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],
        descendants_cleared=summary['descendants_cleared'])
    row['active']=None;row['runs'].append(item);write_json(LEDGER_PATH,row)
    journal('one_run_accounted',run=item)
    return row
