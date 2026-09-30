"""V13 immutable clock, durable progress, and own-parent death protection."""

import ctypes
import json
import os
import signal
import time
from datetime import datetime, timezone

from src.io.task042_profile import ROOT

WINDOW_PATH=ROOT/'tmp/task042/v13/window.json'
JOURNAL_PATH=ROOT/'tmp/task042/v13/progress_journal.jsonl'


def snapshot():
    record=json.loads(WINDOW_PATH.read_text())
    elapsed=max(time.time()-datetime.fromisoformat(record['start_utc']).timestamp(),
                time.monotonic()-record['start_monotonic'],0.)
    return dict(record,elapsed_seconds=elapsed,
        heavy_remaining_seconds=max(0.,record['heavy_limit_seconds']-elapsed),
        total_remaining_seconds=max(0.,record['total_limit_seconds']-elapsed))


def journal(event, **fields):
    row=dict(event=event,utc=datetime.now(timezone.utc).isoformat(),
             heavy_remaining_seconds=snapshot()['heavy_remaining_seconds'],
             shared_workstation=True,**fields)
    JOURNAL_PATH.parent.mkdir(parents=True,exist_ok=True)
    with JOURNAL_PATH.open('a') as stream:
        stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
        stream.flush();os.fsync(stream.fileno())
    return row


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    expected=int(os.environ[variable])
    library=ctypes.CDLL(None,use_errno=True)
    if library.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:
        raise RuntimeError('own V13 numerical supervisor disappeared')
    if snapshot()['heavy_remaining_seconds']<=0:
        raise RuntimeError('V13 original heavy deadline reached')
