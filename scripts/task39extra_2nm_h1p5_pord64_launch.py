#!/usr/bin/env python3
"""Detached, single-entry launcher for the reviewed PORD64 h1.5 retry.

This file only prepares the already reviewed command; it is not executed by
the qualification step.  The caller must obtain the formal-run review before
invoking it.
"""

import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

WORKTREE = Path("/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity")
DEFAULT_INPUT = "input/task39extra_para_workstation_capacity/original_2nm_si_p6h1p5_native.dat"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default=DEFAULT_INPUT)
    args = parser.parse_args()
    command = ("source scripts/activate_task39extra_pord64.sh && "
               "exec python scripts/run_case.py " + shlex.quote(args.input))
    argv = ["/usr/bin/taskset", "-c", "9", "/bin/bash", "-lc", command]
    launch_dir = Path(tempfile.mkdtemp(prefix="task39extra-2nm-h1p5-pord64-launch."))
    log_path = launch_dir / "launcher.log"
    record_path = launch_dir / "launch.json"
    kwargs = {
        "cwd": str(WORKTREE),
        "stdin": "DEVNULL",
        "stdout": str(log_path),
        "stderr": "STDOUT",
        "start_new_session": True,
        "close_fds": True,
    }
    record = {"argv": argv, "kwargs": kwargs, "log_path": str(log_path)}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            argv,
            cwd=WORKTREE,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    record["pid"] = process.pid
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pid": process.pid, "record": str(record_path), "log": str(log_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
