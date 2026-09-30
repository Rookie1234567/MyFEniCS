"""One immutable V12 wall-clock window and an own-supervisor death guard."""

from __future__ import annotations

import ctypes
import json
import os
import signal
import time
from datetime import datetime, timezone

from src.io.task042_profile import ROOT

WINDOW_PATH = ROOT / "tmp/task042/v12/window.json"
JOURNAL_PATH = ROOT / "tmp/task042/v12/progress_journal.jsonl"


def snapshot():
    value = json.loads(WINDOW_PATH.read_text())
    start_utc = datetime.fromisoformat(value["start_utc"]).timestamp()
    elapsed = max(time.time() - start_utc, time.monotonic() - value["start_monotonic"], 0.0)
    return dict(value, elapsed_seconds=elapsed,
                heavy_remaining_seconds=max(0.0, value["heavy_limit_seconds"] - elapsed),
                total_remaining_seconds=max(0.0, value["total_limit_seconds"] - elapsed))


def journal(event, **fields):
    row = dict(event=event, utc=datetime.now(timezone.utc).isoformat(),
               heavy_remaining_seconds=snapshot()["heavy_remaining_seconds"],
               shared_workstation=True, **fields)
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return row


def guard_worker_parent():
    expected = int(os.environ["TASK042_WATCHDOG_PARENT_PID"])
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() != expected:
        raise RuntimeError("own numerical supervisor disappeared")
    if snapshot()["heavy_remaining_seconds"] <= 0:
        raise RuntimeError("V12 heavy deadline reached")
