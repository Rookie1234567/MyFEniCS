from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)


@unittest.skipUnless(
    sys.platform.startswith("linux"),
    "Linux process-group contract",
)
class WatchdogProcessControlTests(unittest.TestCase):
    def test_process_group_termination_reaches_stubborn_descendant(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess,sys,time; "
                    "child=subprocess.Popen([sys.executable,'-c','import signal,time; "
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                    'print("ready",flush=True); time.sleep(60)\'],'
                    "stdout=subprocess.PIPE,text=True); child.stdout.readline(); "
                    "print(child.pid,flush=True); time.sleep(60)"
                ),
            ],
            stdout=subprocess.PIPE,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        assert process.stdout is not None
        child_pid = int(process.stdout.readline().strip())
        try:
            cleanup = terminate_process_tree(process, grace_seconds=0.5)
            self.assertTrue(cleanup["worker_exited"])
            self.assertTrue(cleanup["process_group_exited"])
            self.assertTrue(cleanup["sigkill_required"])
            deadline = time.monotonic() + 1.0
            while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(Path(f"/proc/{child_pid}").exists())
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1.0)

    def test_process_group_termination_survives_leader_exit(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess,sys,time; "
                    "child=subprocess.Popen([sys.executable,'-c','import signal,time; "
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                    "time.sleep(60)']); time.sleep(0.2); "
                    "print(child.pid,flush=True)"
                ),
            ],
            stdout=subprocess.PIPE,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        assert process.stdout is not None
        child_pid = int(process.stdout.readline().strip())
        process.wait(timeout=2.0)
        self.assertTrue(Path(f"/proc/{child_pid}").exists())
        try:
            cleanup = terminate_process_tree(process, grace_seconds=0.5)
            self.assertTrue(cleanup["worker_exited"])
            self.assertTrue(cleanup["process_group_exited"])
            self.assertTrue(cleanup["sigkill_required"])
            deadline = time.monotonic() + 1.0
            while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(Path(f"/proc/{child_pid}").exists())
        finally:
            if Path(f"/proc/{child_pid}").exists():
                os.kill(child_pid, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
