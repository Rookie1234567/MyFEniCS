"""Short persistent supervised dummy for the launch-origin/save-window protocol."""

import json
import os
from pathlib import Path
import sys
from time import perf_counter, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "clock_manifest.json").read_text())
    # Delayed worker entry represents imports/loading, without importing Torch.
    sleep(0.4)
    from src.runners.feinn_workflow import replay_closure_deadline
    from src.solvers.feinn_gqr import GramColumns, ReadoutStop
    import numpy as np

    entered = perf_counter()
    cutoff = replay_closure_deadline(manifest)
    action = GramColumns(np.eye(2), deadline=cutoff)
    action(np.ones(2), "first_allowed_work")
    while perf_counter() < cutoff:
        sleep(0.05)
    try:
        action(np.ones(2), "after_cutoff")
    except ReadoutStop:
        pass
    expired = GramColumns(
        np.eye(2),
        deadline=replay_closure_deadline(
            dict(manifest, supervision_budget_origin_monotonic=entered - 200)
        ),
    )
    try:
        expired(np.ones(2), "never_started")
    except ReadoutStop:
        pass
    from src.solvers.optimization_checkpoint import atomic_json
    import torch

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    # Includes real ML import/save overhead within the declared 120s reserve.
    result = dict(
        origin=manifest["supervision_budget_origin_monotonic"],
        worker_entered=entered,
        import_delay_seconds=entered - manifest["supervision_budget_origin_monotonic"],
        cutoff=cutoff,
        numeric_work_count=action.count,
        expired_work_count=expired.count,
        finish=perf_counter(),
        declared_reserve_seconds=150,
        exit_remaining_seconds=manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - perf_counter(),
        parent_death_guard=os.environ.get("TASK42EXTRA_PARENT_DEATH_GUARD"),
    )
    assert result["numeric_work_count"] == 1 and result["expired_work_count"] == 0
    assert (
        result["import_delay_seconds"] >= 0.4
        and result["exit_remaining_seconds"] >= 120
    )
    assert result["parent_death_guard"]
    atomic_json(directory / "clock_worker_result.json", result)


def launcher(directory):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.guarded_exec import ticks

    directory = Path(directory)
    origin = perf_counter()
    (directory / "clock_manifest.json").write_text(
        json.dumps(
            dict(
                supervision_budget_origin_monotonic=origin, supervised_limit_seconds=154
            )
        )
    )
    result = supervise(
        [
            sys.executable,
            "-m",
            "src.runners.guarded_exec",
            str(os.getpid()),
            str(ticks(os.getpid())),
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            str(directory),
        ],
        directory / "supervision",
        wall_seconds=154,
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.75 * 2**30),
        interval=0.5,
        include_pss=False,
        stop_on_global_swap=False,
    )
    (directory / "clock_supervision.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    if result["leader_exit_code"] != 0 or not result["descendants_cleared"]:
        raise RuntimeError("CLOCK_DUMMY_FAILED")


def main():
    from src.runners.durable_terminal import launch_tmux

    directory = ROOT / "tmp/task42extra/durable/v5_clock_dummy"
    command = [
        "/bin/bash",
        "-lc",
        "source scripts/activate_task42extra.sh ml && exec python benchmarks/check_task42extra_clock.py launcher "
        + str(directory),
    ]
    result = launch_tmux(directory, "task42extra-v5-clock-dummy", command, ROOT)
    for _ in range(100):
        if (directory / "clock_supervision.json").exists():
            summary = json.loads((directory / "clock_supervision.json").read_text())
            if summary["leader_exit_code"] != 0:
                raise RuntimeError("CLOCK_DUMMY_FAILED")
            print(
                json.dumps(
                    dict(status="DURABLE_CLOCK_DUMMY_PASS", output=result["output"])
                )
            )
            return
        sleep(0.2)
    raise RuntimeError("CLOCK_DUMMY_NOT_COMPLETED_IN_DECLARED_SHORT_WINDOW")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "worker":
        worker(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "launcher":
        launcher(sys.argv[2])
    else:
        main()
