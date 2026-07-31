"""Shared process-group control for external MPI watchdogs."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any


def worker_process_group_popen_kwargs() -> dict[str, Any]:
    """Return the one platform-specific option needed for an isolated worker."""

    if os.name == "posix":
        return {"start_new_session": True}
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {}


def _posix_process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_process_tree(
    process: subprocess.Popen[Any], *, grace_seconds: float = 5.0
) -> dict[str, Any]:
    """Terminate an isolated worker tree, escalate, and verify it is gone."""

    grace = max(float(grace_seconds), 0.05)
    result: dict[str, Any] = {
        "requested": True,
        "method": None,
        "grace_seconds": grace,
        "sigkill_required": False,
        "worker_exited": False,
        "process_group_exited": False,
    }
    if os.name == "posix":
        # ``start_new_session=True`` makes the leader PID the process-group ID.
        # Retain that stable ID even when the leader exits before the watchdog;
        # descendants may still be alive in the original group.
        process_group_id = process.pid
        if not _posix_process_group_exists(process_group_id):
            result.update(
                {
                    "method": "already_exited",
                    "worker_exited": process.poll() is not None,
                    "process_group_exited": True,
                }
            )
            return result
        result["method"] = "POSIX process group SIGTERM then SIGKILL"
        result["process_group_id"] = process_group_id
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            # The isolated group can disappear between the existence probe and
            # signal delivery. Continue through wait and final verification.
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            process.poll()
            if not _posix_process_group_exists(process_group_id):
                break
            time.sleep(0.02)
        if _posix_process_group_exists(process_group_id):
            result["sigkill_required"] = True
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                # The group exited after the final grace-period probe.
                pass
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace)
        deadline = time.monotonic() + grace
        while (
            _posix_process_group_exists(process_group_id)
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        result["process_group_exited"] = not _posix_process_group_exists(
            process_group_id
        )
    else:
        if process.poll() is not None:
            result.update(
                {
                    "method": "already_exited",
                    "worker_exited": True,
                    "process_group_exited": True,
                }
            )
            return result
        result["method"] = "psutil recursive terminate then kill"
        import psutil

        root = psutil.Process(process.pid)
        processes = [*root.children(recursive=True), root]
        for member in processes:
            member.terminate()
        _, alive = psutil.wait_procs(processes, timeout=grace)
        if alive:
            result["sigkill_required"] = True
            for member in alive:
                member.kill()
            _, alive = psutil.wait_procs(alive, timeout=grace)
        result["process_group_exited"] = not alive
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace)

    result["worker_exited"] = process.poll() is not None
    if not result["worker_exited"] or not result["process_group_exited"]:
        raise RuntimeError(f"MPI worker process tree did not terminate: {result}")
    return result
