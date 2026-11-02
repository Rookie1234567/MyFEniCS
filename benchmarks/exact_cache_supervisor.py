"""Dedicated non-MPI watchdog entry for authorized isolated cache validation."""

import argparse
import json
import os
from pathlib import Path

from benchmarks.subreaper_watchdog import supervise

p = argparse.ArgumentParser()
p.add_argument("--directory", type=Path, required=True)
p.add_argument("command", nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command and a.command[0] == "--" else a.command
r = supervise(
    command,
    a.directory,
    wall_seconds=None,
    interval=1.0,
    grace_seconds=10.0,
    resource_stop_policy="host_available_floor_v1",
    minimum_available_bytes=68719476736,
    pss_sampling_policy="disabled_by_profile",
    worker_environment=dict(os.environ),
)
(a.directory / "supervisor_receipt.json").write_text(json.dumps(r, indent=2) + "\n")
raise SystemExit(0 if r.get("leader_exit_code", r.get("exit_code")) == 0 else 1)
