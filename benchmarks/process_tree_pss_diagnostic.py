"""Optional slow diagnostics, independent of the RSS safety loop.

Only one scan can run. The interval starts after completion, including a slow
or failed scan; a delayed scan never causes catch-up scans. No join blocks RSS.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ProcessTreePSSDiagnostic:
    def __init__(self, provider: Callable[[], dict], *, interval: float = 5.0,
                 clock: Callable[[], float] = time.monotonic):
        if interval <= 0:
            raise ValueError("diagnostic interval must be positive")
        self.provider, self.interval, self.clock = provider, interval, clock
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._next = 0.0
        self._latest: dict | None = None
        self.scan_count = 0

    def _scan(self) -> None:
        started, cpu = self.clock(), time.thread_time()
        try:
            result = {"status": "COMPLETED", "sample": self.provider()}
        except Exception as exc:  # noqa: BLE001 -- optional diagnostics must not block RSS safety
            result = {"status": "DIAGNOSTIC_FAILED", "exception": repr(exc)}
        ended = self.clock()
        result.update(started_monotonic=started, completed_monotonic=ended,
                      wall_seconds=ended-started, cpu_seconds=time.thread_time()-cpu,
                      scope="independent diagnostic scan; not simultaneous with current RSS")
        with self._lock:
            self._latest = result
            self._next = ended + self.interval

    def poll(self) -> dict | None:
        with self._lock:
            if ((self._thread is None or not self._thread.is_alive())
                    and self.clock() >= self._next):
                self.scan_count += 1
                self._thread = threading.Thread(target=self._scan, daemon=True)
                self._thread.start()
            latest = None if self._latest is None else dict(self._latest)
        if latest is not None:
            latest["age_seconds"] = self.clock()-latest["completed_monotonic"]
        return latest
