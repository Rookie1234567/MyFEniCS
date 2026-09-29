"""Bounded light checks; formal stages continue to use scripts/run_case.py."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.subreaper_watchdog import supervise
from src.runners.feinn_resources import ROOT, Health, admission, envelope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.environ.get("TASK42EXTRA_ACTIVATION") != "1":
        raise RuntimeError("task-local activation required")
    directory = (
        ROOT
        / "tmp/task42extra/checks"
        / (args.label + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    directory.mkdir(parents=True)
    with (ROOT / "tmp/task42extra/numerical.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        baseline = admission(2 * 2**30)
        (directory / "admission.json").write_text(json.dumps(baseline, indent=2) + "\n")
        os.sched_setaffinity(0, {baseline["cpu"]})
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        result = supervise(
            command,
            directory / "supervision",
            wall_seconds=args.seconds,
            interval=0.5,
            rss_hard_limit_bytes=2 * 2**30,
            rss_warning_bytes=int(1.75 * 2**30),
            hard_stop_immediate=True,
            memory_envelope_provider=lambda: envelope(2 * 2**30),
            health_check=Health(directory, 2 * 2**30, baseline["neighbor_processes"]),
            include_pss=False,
            stop_on_global_swap=False,
        )
        (directory / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "classification",
                    "leader_exit_code",
                    "elapsed_seconds",
                    "sampled_process_tree_rss_peak_bytes",
                    "sampled_process_tree_swap_peak_bytes",
                    "descendants_cleared",
                )
            },
            sort_keys=True,
        )
    )
    print(directory)
    return (
        0
        if result["classification"] == "COMPLETED" and result["leader_exit_code"] == 0
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
