"""V16 immutable four-hour window, with parent-death and durable journal."""

import ctypes
import json
import os
import signal
import time
from datetime import datetime, timezone

from src.io.task042_profile import ROOT

WINDOW_PATH = ROOT / 'tmp/task042/v16/window.json'
JOURNAL_PATH = ROOT / 'tmp/task042/v16/progress_journal.jsonl'
BUDGET_PATH = ROOT / 'tmp/task042/v16/route_budget.json'


def snapshot():
    row = json.loads(WINDOW_PATH.read_text())
    elapsed = max(time.time()-datetime.fromisoformat(row['start_utc']).timestamp(),
                  time.monotonic()-row['start_monotonic'], 0.)
    return dict(row, elapsed_seconds=elapsed, heavy_remaining_seconds=max(0., 13500-elapsed),
                total_remaining_seconds=max(0., 14400-elapsed))


def journal(event, **fields):
    from src.runners.task042_shared import _json_metadata
    row = dict(event=event, utc=datetime.now(timezone.utc).isoformat(),
               heavy_remaining_seconds=snapshot()['heavy_remaining_seconds'],
               shared_workstation=True, **fields)
    with JOURNAL_PATH.open('a') as stream:
        stream.write(json.dumps(_json_metadata(row), ensure_ascii=False, allow_nan=False)+'\n')
        stream.flush(); os.fsync(stream.fileno())
    return row


def freeze_route_budget():
    from src.runners.task042_shared import write_json
    if BUDGET_PATH.exists():
        return json.loads(BUDGET_PATH.read_text())
    T = snapshot()['heavy_remaining_seconds']
    B = min(2700, int((T-600)//3))
    if B < 300:
        raise RuntimeError('TIME_BUDGET_INSUFFICIENT')
    row = dict(uniform_route_wall_seconds=B, heavy_remaining_at_freeze_seconds=T,
               formula='min(2700, floor((T-600)/3))', immutable=True,
               includes_setup_loading_and_final_save=True, final_save_reserve_seconds=30)
    write_json(BUDGET_PATH, row)
    journal('uniform_route_budget_frozen', **row)
    return row


def guard_worker_parent(variable='TASK042_WATCHDOG_PARENT_PID'):
    expected = int(os.environ[variable]); library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() != expected:
        raise RuntimeError('own V16 supervisor disappeared')
    if snapshot()['heavy_remaining_seconds'] <= 0:
        raise RuntimeError('original V16 heavy deadline reached')
