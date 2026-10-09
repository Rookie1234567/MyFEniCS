"""Opt-in dedicated parent for a saved-field checker inside an FE worker tree.

MPI may already own children of the FE worker. Only this fresh pure process
becomes the checker subreaper; it remains under the outer task watchdog.
"""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from time import monotonic

from src.io.neural_wave_campaign import ROOT
from src.runners.guarded_exec import ticks
from src.solvers.neural_wave_greedy import atomic_json


def run_checker(command, directory, deadline, source_sha):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    contract = directory / "contract.json"
    atomic_json(
        contract,
        dict(command=command, deadline_monotonic=deadline, source_sha=source_sha),
    )
    shell = (
        "source scripts/activate_task42extra.sh pure && exec python -m src.runners.saved_field_supervision "
        + shlex.quote(str(contract))
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.runners.guarded_exec",
            str(os.getpid()),
            str(ticks(os.getpid())),
            "bash",
            "-lc",
            shell,
        ],
        cwd=ROOT,
        check=False,
    )
    summary = json.loads((directory / "supervised/summary.json").read_text())
    if (
        process.returncode
        or summary["classification"] != "COMPLETED"
        or summary["leader_exit_code"] != 0
        or not summary["descendants_cleared"]
    ):
        raise ValueError("INDEPENDENT_SAVED_FIELD_CHECKER_FAILED")
    return summary


def main(contract_file):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import envelope

    file = Path(contract_file)
    contract = json.loads(file.read_text())
    hard = 2 * 2**30
    summary = supervise(
        contract["command"],
        file.parent / "supervised",
        wall_seconds=max(0, contract["deadline_monotonic"] - monotonic()),
        rss_hard_limit_bytes=hard,
        rss_warning_bytes=int(1.875 * 2**30),
        startup_headroom_bytes=envelope(hard)["reserve_bytes"],
        memory_envelope_provider=lambda: envelope(hard),
        hard_stop_immediate=True,
        resource_stop_policy="measured_tree_rss_only_v3",
        source_state=dict(
            source_sha=contract["source_sha"], role="independent_saved_field_checker"
        ),
    )
    return (
        0
        if summary["classification"] == "COMPLETED"
        and summary["leader_exit_code"] == 0
        and summary["descendants_cleared"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
