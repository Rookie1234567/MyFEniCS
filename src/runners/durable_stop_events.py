"""Opt-in write-ahead stop evidence; reception does not identify the sender."""
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return dict(pid=pid, ppid=int(fields[1]), start_ticks=int(fields[19]),
                    pgid=int(fields[2]), sid=int(fields[3]))
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, identity='vanished')


class StopEvents:
    """fsync only launch/stop events, never each resource sample."""
    def __init__(self, path, budget):
        self.path, self.budget = Path(path), budget
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event, **fields):
        row = dict(event=event, utc=datetime.now(timezone.utc).isoformat(),
                   monotonic=time.monotonic(),
                   boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   controller=process_identity(os.getpid()), budget=self.budget, **fields)
        raw=(json.dumps(row, allow_nan=False)+'\n').encode()
        fd=os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            view=memoryview(raw)
            while view:
                n=os.write(fd, view)
                if n <= 0: raise OSError('stop event write incomplete')
                view=view[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        return row
