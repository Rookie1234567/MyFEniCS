"""Tiny real-child checks; no FE, Torch, matrix, reference or training."""

import sys
import time

from benchmarks.subreaper_watchdog import supervise


def control_checks(directory, artifact, marker, manifest):
    began = time.monotonic()
    time.sleep(0.25)  # Actual delayed loading witness, charged to launch clock.
    now = time.monotonic()
    deadline = manifest["numerical_cutoff_monotonic"]
    if (
        not deadline
        < manifest["supervision_budget_origin_monotonic"]
        + manifest["stage_limit_seconds"]
        or now >= deadline
    ):
        raise RuntimeError("CONTROL_DEADLINE_NOT_BOUND_TO_LAUNCH")
    child = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); raise SystemExit(7)"
    failed = supervise(
        [sys.executable, "-c", child],
        artifact / "injected_failure",
        wall_seconds=10,
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.75 * 2**30),
        interval=0.5,
        include_pss=False,
    )
    normal = supervise(
        [sys.executable, "-c", "print('control boundary saved')"],
        artifact / "normal_exit",
        wall_seconds=10,
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.75 * 2**30),
        interval=0.5,
        include_pss=False,
    )
    if (
        failed["leader_exit_code"] != 7
        or not failed["descendants_cleared"]
        or normal["leader_exit_code"] != 0
        or not normal["descendants_cleared"]
    ):
        raise RuntimeError("CONTROL_FAILURE_ACCOUNT_OR_TREE_CLEANUP_FAILED")
    marker("control_chain_verified", {})
    return dict(
        stage_qualified=True,
        launcher_origin=manifest["supervision_budget_origin_monotonic"],
        observed_after_delay=now,
        import_delay_seconds=now - began,
        save_reserve_seconds=150,
        failed_child=failed,
        normal_child=normal,
        failure_charge_preserved=True,
        sampled_scope="isolated tmux server, launcher/watchdog and descendants",
        no_FE_or_training=True,
    )
