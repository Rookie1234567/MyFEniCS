"""Foreground F0 checks only; enforce the busy-workstation 2 GiB tree limit.

Reuses the existing dedicated subreaper. Never waits for a workstation slot,
never launches a PDE, and can only signal descendants of its own invocation.
CPU affinity must be selected from a separate current host resource audit.
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.subreaper_watchdog import supervise

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--wall-seconds", type=float, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT) or directory.exists():
        raise ValueError("choose a fresh local evidence directory")
    if Path.cwd().resolve() != ROOT or os.environ.get("TASK042_ACTIVATION") != "1":
        raise ValueError("activate Task042 in NN-Lab first")
    if len(os.sched_getaffinity(0)) != 1:
        raise ValueError("F0 must use one independently audited spare physical core")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("F0 cannot expose a GPU")
    if any(
        os.environ.get(key) != "1"
        for key in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "BLIS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        )
    ):
        raise ValueError("F0 math threads must equal one")
    state = {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ),
        "stage": "F0",
        "formal_pde": False,
        "command": command,
        "utc": datetime.now(timezone.utc).isoformat(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "environment_mode": os.environ["TASK042_ENV_MODE"],
        "gpu_visible": False,
    }
    summary = supervise(
        command,
        directory,
        wall_seconds=args.wall_seconds,
        interval=0.1,
        source_state=state,
        hard_stop_immediate=True,
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.5 * 2**30),
        stop_on_global_swap=False,
        resource_stop_policy="legacy",
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "classification",
                    "leader_exit_code",
                    "descendants_cleared",
                    "elapsed_seconds",
                    "sampled_process_tree_rss_peak_bytes",
                    "sampled_process_tree_swap_peak_bytes",
                )
            }
        )
    )
    return (
        0
        if (
            summary["classification"] == "COMPLETED"
            and summary["leader_exit_code"] == 0
            and summary["descendants_cleared"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
