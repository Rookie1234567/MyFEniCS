"""Immutable four-hour V11 clock and own-worker death guard."""

import ctypes
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from src.io.task042_profile import ROOT

WINDOW_PATH = ROOT / "tmp/task042/v11/window.json"
JOURNAL_PATH = ROOT / "tmp/task042/v11/progress_journal.jsonl"


def snapshot():
    value = json.loads(WINDOW_PATH.read_text())
    utc_elapsed = (time.time_ns() - value["start_utc_ns"]) / 1e9
    mono_start = value["observed_monotonic"] - (
        value["observed_utc_ns"] - value["start_utc_ns"]
    ) / 1e9
    elapsed = max(utc_elapsed, time.monotonic() - mono_start, 0.0)
    return dict(value, elapsed_seconds=elapsed,
                heavy_remaining_seconds=max(0.0, value["heavy_limit_seconds"] - elapsed),
                total_remaining_seconds=max(0.0, value["total_limit_seconds"] - elapsed),
                cumulative_historical_plus_elapsed_seconds=value["carry_in_V6_to_V10_onload_seconds"] + elapsed)


def journal(event, **fields):
    row = dict(event=event, utc=datetime.now(timezone.utc).isoformat(),
               source_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               heavy_remaining_seconds=snapshot()["heavy_remaining_seconds"],
               total_remaining_seconds=snapshot()["total_remaining_seconds"],
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
        raise RuntimeError("V11 heavy deadline reached")
