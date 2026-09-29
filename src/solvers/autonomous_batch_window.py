"""Finite Task042 batch clock and durable journal; no waiting or restarting."""

import ctypes
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from src.io.task042_profile import ROOT

WINDOW_PATH = ROOT / "tmp/task042/v10/window.json"
JOURNAL_PATH = ROOT / "tmp/task042/v10/progress_journal.jsonl"


def window_snapshot(path=WINDOW_PATH):
    value = json.loads(Path(path).read_text())
    utc_elapsed = (time.time_ns() - value["start_utc_ns"]) / 1e9
    mono_start = (
        value["observed_monotonic"]
        - (value["observed_utc_ns"] - value["start_utc_ns"]) / 1e9
    )
    elapsed = max(utc_elapsed, time.monotonic() - mono_start, 0.0)
    return dict(
        **value,
        elapsed_seconds=elapsed,
        heavy_remaining_seconds=max(0.0, value["heavy_limit_seconds"] - elapsed),
        total_remaining_seconds=max(0.0, value["total_limit_seconds"] - elapsed),
        cumulative_elapsed_including_history=value["carry_in_seconds"] + elapsed,
        clock_basis="max(UTC, monotonic) from immutable original start",
    )


def journal(event, **fields):
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    snapshot = window_snapshot()
    row = dict(
        event=event,
        utc=datetime.now(timezone.utc).isoformat(),
        source_sha=source,
        heavy_remaining_seconds=snapshot["heavy_remaining_seconds"],
        total_remaining_seconds=snapshot["total_remaining_seconds"],
        shared_workstation=True,
        **fields,
    )
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return row


def guard_worker_parent():
    """A disappearing own watchdog must not leave a numerical worker alive."""
    expected = int(os.environ["TASK042_WATCHDOG_PARENT_PID"])
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGTERM, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG failed")
    if os.getppid() != expected:
        raise RuntimeError("own numerical supervisor disappeared before admission")
    if window_snapshot()["heavy_remaining_seconds"] <= 0:
        raise RuntimeError("original batch heavy deadline reached")
