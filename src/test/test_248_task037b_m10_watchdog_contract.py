"""Pure contracts for the explicit frozen M10 watchdog."""

from __future__ import annotations

import csv
import inspect
import io
import json
import sys
from pathlib import Path

import pytest

from benchmarks import run_task037b_hybrid_iterative_watchdog as watchdog
from benchmarks.run_direct_memory_forensics import TIMELINE_FIELDS


SHA = "a" * 40
OTHER_SHA = "b" * 40


def _argv(tmp_path: Path, *, frozen: bool = True) -> list[str]:
    values = [
        "--case-label",
        "task037b_m10_test",
        "--run-root",
        str(tmp_path / "run"),
        "--output",
        str(tmp_path / "summary.json"),
        "--verified-clean-sha",
        SHA,
        "--h1-authority",
        str(tmp_path / "h1.json"),
        "--h1-authority-sha256",
        "c" * 64,
        "--full3d-reference",
        str(tmp_path / "full3d.json"),
        "--full3d-reference-sha256",
        "d" * 64,
        "--task035c-p6-preflight-authority",
        str(tmp_path / "p6.json"),
        "--task035c-p6-preflight-sha256",
        "e" * 64,
    ]
    return (["--frozen-m10"] if frozen else []) + values


def _resource_row(rss: float, swap: float = 0.0) -> dict[str, object]:
    return {
        "timestamp_utc": "2026-08-10T00:00:00+00:00",
        "elapsed_seconds": 1.0,
        "stage": "test_stage",
        "mpi_process_tree_rss_mb": rss,
        "mpi_process_tree_swap_mb": swap,
        "worker_rank_pss_sum_mb": rss / 2,
        "worker_rank_uss_sum_mb": rss / 3,
    }


def test_parser_requires_explicit_frozen_profile(tmp_path: Path) -> None:
    args = watchdog.parse_args(_argv(tmp_path))
    assert args.frozen_m10 is True
    assert watchdog.FROZEN_M10_MPI_SIZE == 8
    assert watchdog.SAMPLE_INTERVAL_SECONDS == 1.0
    assert watchdog.HEARTBEAT_SECONDS == 30.0
    assert watchdog.TIMEOUT_SECONDS == 7200.0
    assert watchdog.RSS_LIMIT_MIB == 6144.0
    assert watchdog.SWAP_LIMIT_MIB == 0.0
    with pytest.raises(SystemExit):
        watchdog.parse_args(_argv(tmp_path, frozen=False))


def test_worker_command_and_environment_are_frozen(tmp_path: Path) -> None:
    args = watchdog.parse_args(_argv(tmp_path))
    payload = tmp_path / "run" / "payload"
    online = tmp_path / "run" / "online_record.json"
    stages = tmp_path / "run" / "memory_stages.jsonl"
    command = watchdog.build_worker_command(args, payload, online, stages)
    assert command[:6] == [
        "mpiexec",
        "-n",
        "8",
        sys.executable,
        "-m",
        "benchmarks.run_task037b_hybrid_iterative",
    ]
    assert command.count("--frozen-m10") == 1
    for value in (
        args.h1_authority_sha256,
        args.full3d_reference_sha256,
        args.task035c_p6_preflight_sha256,
    ):
        assert value in command
    for path in (
        Path(args.h1_authority).resolve(),
        Path(args.full3d_reference).resolve(),
        Path(args.task035c_p6_preflight_authority).resolve(),
    ):
        assert str(path) in command
    assert str(payload) in command
    assert str(online) in command
    environment = watchdog._worker_environment()
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        assert environment[name] == "1"
    assert environment["PYTHONUNBUFFERED"] == "1"


def test_source_preflight_binds_clean_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_git_value(*parts: str) -> str:
        return {"rev-parse": SHA, "status": "", "branch": "local"}[parts[0]]

    monkeypatch.setattr(watchdog, "_git_value", fake_git_value)
    result = watchdog._source_preflight(SHA)
    assert result["head"] == SHA
    assert result["clean"] is True
    assert result["match"] is True
    with pytest.raises(RuntimeError):
        watchdog._source_preflight(OTHER_SHA)


def test_artifact_hash_and_bad_online_json_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "online.json"
    path.write_text(json.dumps({"online_pass": True, "status": "candidate"}))
    state = watchdog._read_online_record(path)
    assert state["json_valid"] is True
    assert state["record"]["online_pass"] is True
    assert state["descriptor"]["bytes"] == path.stat().st_size
    assert state["descriptor"]["sha256"] == watchdog._sha256(path)
    path.write_text("{")
    invalid = watchdog._read_online_record(path)
    assert invalid["json_valid"] is False
    assert invalid["record"] is None
    assert invalid["failures"]


def test_resource_limits_are_fail_closed_at_strict_boundary() -> None:
    empty = watchdog._resource_summary([])
    assert empty["sample_count"] == 0
    assert empty["pass"] is False
    at_limit = watchdog._resource_summary([_resource_row(6144.0)])
    assert at_limit["rss_pass"] is True
    assert at_limit["swap_pass"] is True
    assert at_limit["pass"] is True
    above_limit = watchdog._resource_summary([_resource_row(6144.0001)])
    assert above_limit["rss_pass"] is False
    assert above_limit["pass"] is False
    swapped = watchdog._resource_summary([_resource_row(100.0, 0.001)])
    assert swapped["swap_pass"] is False
    assert swapped["pass"] is False


def test_qualification_requires_worker_online_resource_and_clean_group() -> None:
    resource = watchdog._resource_summary([_resource_row(100.0)])
    control = {"worker_exited": True, "process_group_exited": True}
    passed = watchdog._qualification_summary(0, True, resource, "natural_exit", control)
    assert passed["pass"] is True
    failed = watchdog._qualification_summary(
        1, False, resource, "wall_timeout", control
    )
    assert failed["pass"] is False
    assert set(failed["checks"]) == {
        "worker_exit0",
        "online_pass",
        "resource_pass",
        "swap_zero",
        "no_timeout",
        "process_group_clean",
    }
    orphan = watchdog._qualification_summary(
        0,
        True,
        resource,
        "natural_exit",
        {"worker_exited": True, "process_group_exited": False},
    )
    assert orphan["pass"] is False


def test_overlimit_sampling_terminates_once_without_long_sleep() -> None:
    class FakeProcess:
        pid = 17
        returncode = -15

        def poll(self) -> None:
            return None

    samples = iter([_resource_row(6144.0), _resource_row(6144.1)])
    clock_values = iter([0.0, 0.0, 1.0])
    terminate_calls: list[object] = []
    sleeps: list[float] = []

    def fake_terminate(process: object) -> dict[str, object]:
        terminate_calls.append(process)
        return {
            "method": "fake",
            "worker_exited": True,
            "process_group_exited": True,
        }

    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
    writer.writeheader()
    result = watchdog._sampling_loop(
        FakeProcess(),
        Path("memory_stages.jsonl"),
        writer,
        stream,
        sample_fn=lambda _pid, _stage, _elapsed: next(samples),
        terminator=fake_terminate,
        clock=lambda: next(clock_values),
        sleep_fn=sleeps.append,
        heartbeat_fn=lambda _message: None,
    )
    assert result["termination_classification"] == "rss_limit_exceeded"
    assert result["termination_calls"] == 1
    assert len(terminate_calls) == 1
    assert sleeps == [1.0]
    assert len(result["rows"]) == 2


def test_generic_sampling_helpers_are_used_without_legacy_runner() -> None:
    source = inspect.getsource(watchdog)
    assert watchdog._sample.__module__ == "benchmarks.run_direct_memory_forensics"
    assert (
        watchdog.worker_process_group_popen_kwargs.__module__
        == "benchmarks.watchdog_process_control"
    )
    assert (
        watchdog._add_cpu_core_equivalents.__module__
        == "benchmarks.run_direct_memory_forensics"
    )
    assert (
        watchdog.terminate_process_tree.__module__
        == "benchmarks.watchdog_process_control"
    )
    assert "TIMELINE_FIELDS" in source
    for forbidden in (
        "run_task032_phase6_augmented",
        "run_task033_memory_watchdog",
        ".communicate(",
        "retry",
        "campaign",
        "registry",
        "fallback",
        "disposition",
    ):
        assert forbidden not in source.lower()
