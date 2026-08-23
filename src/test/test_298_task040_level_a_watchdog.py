"""Task040 Level-A runner and process-tree watchdog contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from benchmarks import task040_level_a_watchdog as watchdog
from benchmarks.task040_level_a_watchdog import (
    TASK040_LEVEL_A_HARD_STOP_BYTES,
    TASK040_V1_1_SCALAR_KRYLOV_FLAG,
    TASK040_V1_2_INTERFACE_SCHUR_FLAG,
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


class _FakeWatchdogProcess:
    def __init__(self, polls, worker_directory: str) -> None:
        self.pid = 4321
        self._polls = iter(polls)
        self.returncode = None
        self.worker_directory = worker_directory

    def prepare_worker_output(self) -> None:
        worker_path = Path(self.worker_directory)
        worker_path.mkdir(parents=True)
        (worker_path / "run_summary.json").write_text("{}\n", encoding="utf-8")

    def poll(self):
        value = next(self._polls)
        if value is not None:
            self.returncode = value
        return value


def _fake_resource_sample(readable: bool, rss_bytes: int) -> dict[str, object]:
    return {
        "process_tree": {
            "pids": [4321],
            "rss_bytes": rss_bytes,
            "swap_bytes": 0,
            "all_status_readable": readable,
        },
        "job_cgroup": {
            "dedicated_job_cgroup": False,
            "swap_current_bytes": None,
        },
    }


def _run_fake_watchdog(monkeypatch, plan, polls, samples):
    process = _FakeWatchdogProcess(polls, plan["worker_run_directory"])
    sample_iter = iter(samples)

    def fake_popen(*args, **kwargs):
        process.prepare_worker_output()
        return process

    monkeypatch.setattr(watchdog.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        watchdog,
        "resource_authority_sample",
        lambda _pid, *, include_smaps=False: next(sample_iter),
    )
    monkeypatch.setattr(
        watchdog,
        "terminate_process_tree",
        lambda _process: {
            "worker_exited": True,
            "process_group_exited": True,
        },
    )
    monkeypatch.setattr(watchdog.time, "sleep", lambda _seconds: None)
    return watchdog.run_task040_level_a_watchdog(plan)


def test_task040_v1_1_opt_in_does_not_change_legacy_plan(tmp_path) -> None:
    legacy = _plan(tmp_path / "legacy")
    scalar = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "scalar" / "input.dat",
        exact_spool_root=tmp_path / "scalar" / "spool",
        run_directory=tmp_path / "scalar" / "run",
        source_sha="b" * 40,
        scalar_krylov=True,
    )
    assert legacy["schema"] == "task040.level_a.bare_f_transmission.v1"
    assert legacy["method"] == "task040_level_a_bare_f_transmission"
    assert legacy["profile"] == "task040.level_a.h4.bottom.v1"
    assert scalar["schema"] == "task040.v1_1.scalar_krylov.v1"
    assert scalar["method"] == "task040_v1_1_scalar_krylov"
    assert scalar["profile"] == "task040.v1_1.h4.bottom.scalar_krylov.v1"
    assert scalar["scalar_krylov"] is True
    assert scalar["worker_argv"].count(TASK040_V1_1_SCALAR_KRYLOV_FLAG) == 1
    assert TASK040_V1_1_SCALAR_KRYLOV_FLAG not in legacy["worker_argv"]
    for key in (
        "mpi_size",
        "threads",
        "timeout_seconds",
        "absolute_terminate_memory_bytes",
        "swap_limit_bytes",
        "forbidden",
    ):
        assert scalar[key] == legacy[key]


def test_task040_v1_2_interface_schur_is_explicit_and_frozen(tmp_path, capsys) -> None:
    plan = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "input.dat",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "run",
        source_sha="c" * 40,
        interface_schur=True,
    )
    assert plan["schema"] == "task040.v1_2.interface_schur.v1"
    assert plan["method"] == "task040_v1_2_interface_schur"
    assert plan["profile"] == "task040.v1_2.h4.run_b.v1"
    assert plan["interface_schur"] is True
    assert plan["probe_manifest_sha256"] == (
        "7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad"
    )
    assert plan["selected_manifest_sha256"] == (
        "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
    )
    assert plan["exact_spool_catalog_sha256"] == (
        "a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384"
    )
    assert plan["absolute_terminate_memory_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES
    assert plan["swap_limit_bytes"] == 0
    assert plan["worker_argv"].count(TASK040_V1_2_INTERFACE_SCHUR_FLAG) == 1
    assert TASK040_V1_1_SCALAR_KRYLOV_FLAG not in plan["worker_argv"]
    assert not (tmp_path / "run").exists()
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
                "c" * 40,
                TASK040_V1_2_INTERFACE_SCHUR_FLAG,
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["worker_argv"].count(TASK040_V1_2_INTERFACE_SCHUR_FLAG) == 1
    assert output["method"] == plan["method"]
    assert not (tmp_path / "run").exists()


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


def test_task040_watchdog_excludes_process_exit_during_sample(
    tmp_path, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    result = _run_fake_watchdog(
        monkeypatch,
        plan,
        polls=[None, None, None, 0],
        samples=[
            _fake_resource_sample(True, 100),
            _fake_resource_sample(False, 1),
        ],
    )
    summary = json.loads(
        (tmp_path / "run" / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    assert result == 0
    assert summary["sample_count"] == 1
    assert summary["authoritative_sample_count"] == 1
    assert summary["terminal_teardown_excluded_count"] == 1
    assert summary["all_status_readable"] is True
    assert summary["swap_authority_readable"] is True
    rows = [
        json.loads(line)
        for line in (tmp_path / "run" / "process_tree_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert rows[-1]["terminal_teardown_excluded"] is True
    assert rows[-1]["authoritative_sample"] is False


def test_task040_watchdog_terminal_high_rss_still_hard_stops(
    tmp_path, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    result = _run_fake_watchdog(
        monkeypatch,
        plan,
        polls=[None, None, None, 0],
        samples=[
            _fake_resource_sample(True, 100),
            _fake_resource_sample(False, TASK040_LEVEL_A_HARD_STOP_BYTES + 1),
        ],
    )
    summary = json.loads(
        (tmp_path / "run" / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    assert result == 2
    assert summary["termination_reason"] == "absolute_memory_limit"
    assert summary["sample_count"] == 1
    assert summary["terminal_teardown_excluded_count"] == 1
    assert summary["peak_rss_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES + 1


def test_task040_watchdog_keeps_live_unreadable_sample_as_failure(
    tmp_path, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    result = _run_fake_watchdog(
        monkeypatch,
        plan,
        polls=[None, None, None, None, 0],
        samples=[
            _fake_resource_sample(True, 100),
            _fake_resource_sample(False, 200),
        ],
    )
    summary = json.loads(
        (tmp_path / "run" / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    assert result == 2
    assert summary["sample_count"] == 2
    assert summary["terminal_teardown_excluded_count"] == 0
    assert summary["all_status_readable"] is False
    assert summary["swap_authority_readable"] is False
