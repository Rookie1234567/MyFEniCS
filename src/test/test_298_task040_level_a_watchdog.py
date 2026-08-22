"""Task040 Level-A runner and process-tree watchdog contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from benchmarks import task040_level_a_watchdog as watchdog
from benchmarks.task040_level_a_watchdog import (
    TASK040_LEVEL_A_HARD_STOP_BYTES,
    build_task040_level_a_watchdog_plan,
    main,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)


def _plan(tmp_path):
    return build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "input.dat",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "run",
        source_sha="a" * 40,
    )


def test_task040_watchdog_dry_run_is_frozen_and_unique(tmp_path, capsys) -> None:
    plan = _plan(tmp_path)
    command = plan["worker_argv"]
    assert not (tmp_path / "run").exists()
    module_index = command.index("-m")
    assert command[module_index + 1] == "benchmarks.task040_level_a"
    assert all(
        not token.endswith("/benchmarks/task040_level_a.py") for token in command
    )
    assert plan["method"] == "task040_level_a_bare_f_transmission"
    assert plan["profile"] == "task040.level_a.h4.bottom.v1"
    assert plan["mpi_size"] == 8
    assert plan["threads"] == 1
    assert plan["absolute_terminate_memory_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES
    assert plan["swap_limit_bytes"] == 0
    assert command[:3] == ["mpiexec", "-n", "8"]
    assert command[command.index("--run-directory") + 1] == str(
        tmp_path / "run" / "worker"
    )
    assert command.count("--input") == 1
    assert command.count("--exact-spool-root") == 1
    assert command.count("--run-directory") == 1
    assert command.count("--source-sha") == 1
    assert command.count("--memory-stages") == 1
    assert command.count("--memory-markers") == 1
    assert plan["watchdog"]["terminate_entire_process_group"] is True
    assert plan["runner_reuse"]["process_control"] == (
        "benchmarks.watchdog_process_control"
    )

    assert (
        main(
            [
                "--dry-run",
                "--input",
                str(tmp_path / "input.dat"),
                "--exact-spool-root",
                str(tmp_path / "spool"),
                "--run-directory",
                str(tmp_path / "run"),
                "--source-sha",
                "a" * 40,
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["method"] == plan["method"]
    assert output["worker_argv"] == command
    assert not (tmp_path / "run").exists()


def test_task040_watchdog_terminates_one_process_group() -> None:
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', "
        + repr(child_code)
        + "]); time.sleep(60)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", parent_code], **worker_process_group_popen_kwargs()
    )
    try:
        time.sleep(0.1)
        result = terminate_process_tree(process)
        assert result["worker_exited"] is True
        assert result["process_group_exited"] is True
    finally:
        if process.poll() is None:
            terminate_process_tree(process)


def test_task040_watchdog_hard_stop_is_process_tree_authority(
    tmp_path, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    child_code = "import time; time.sleep(60)"
    plan["worker_argv"] = [
        sys.executable,
        "-c",
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', "
        + repr(child_code)
        + "]); time.sleep(60)",
    ]

    def fake_sample(_pid, *, include_smaps=False):
        assert include_smaps is False
        return {
            "process_tree": {
                "pids": (_pid,),
                "rss_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES + 1,
                "swap_bytes": 0,
                "all_status_readable": True,
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": None,
            },
        }

    monkeypatch.setattr(watchdog, "resource_authority_sample", fake_sample)
    assert watchdog.run_task040_level_a_watchdog(plan) == 2
    summary = json.loads(
        (tmp_path / "run" / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    assert summary["termination_reason"] == "absolute_memory_limit"
    assert summary["process_control"]["process_group_exited"] is True
    assert summary["run_summary_present"] is False
    assert summary["peak_rss_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES + 1
    assert not (tmp_path / "run" / "worker").exists()
