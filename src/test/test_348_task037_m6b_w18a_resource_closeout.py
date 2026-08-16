"""Focused pure contracts for the W18A watchdog wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks import run_task037_extra_m6b as runner


EXPECTED_SOURCE_SHA = "a" * 40


def test_w18a_watchdog_constants_command_and_inventory() -> None:
    prediction = runner._m6b_w18a_predicted_live_set()
    command = runner._m6b_w18a_worker_command(
        Path("run"),
        Path("w7.json"),
        Path("w7_raw"),
        Path("factor.json"),
        Path("jit"),
        EXPECTED_SOURCE_SHA,
    )
    raw = runner._m6b_w16a_raw_artifacts(Path("raw"), mode="w18a")
    watchdog = runner._m6b_w16a_watchdog_artifacts(
        Path("watchdog"), mode="w18a"
    )

    assert runner.M6B_W18A_WATCHDOG_SCHEMA.endswith("w18a.watchdog.v1")
    assert runner.M6B_W18A_WATCHDOG_SUMMARY_FILENAME == "w18a_watchdog_summary.json"
    assert runner.M6B_W18A_TIMEOUT_SECONDS == 3600.0
    assert runner.M6B_W18A_WATCHDOG_RSS_LIMIT_BYTES == 1_950_000_000
    assert runner.M6B_W18A_FORMAL_RSS_LIMIT_BYTES == 1_950_000_000
    assert prediction["bytes"] == 1_734_993_014
    assert prediction["gate"] is True
    assert command[3] == "m6b-w18a-nested-auxiliary-diagnostic"
    assert len(raw) == 46
    assert len(watchdog) == 3
    assert watchdog[0]["path"] == "w18a_nested_auxiliary_timeline.jsonl"


def test_w18a_watchdog_wrapper_forces_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_shared(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w16a_watchdog", fake_shared)
    result = runner._run_m6b_w18a_watchdog(
        Path("run"),
        Path("watchdog"),
        Path("w7.json"),
        Path("w7_raw"),
        Path("factor.json"),
        Path("jit"),
        EXPECTED_SOURCE_SHA,
    )

    assert result == 17
    assert observed["kwargs"] == {"mode": "w18a"}


@pytest.mark.parametrize("worker_return_code", [0, 1])
def test_w18a_worker_completion_keeps_physical_screen_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_return_code: int,
) -> None:
    import benchmarks.run_task037_extra_h2b as h2b

    w7_compact = tmp_path / "w7.json"
    w7_compact.write_text("{}", encoding="utf-8")
    w7_raw_dir = tmp_path / "w7_raw"
    w7_raw_dir.mkdir()
    factor_manifest = tmp_path / "factor" / "manifest.json"
    factor_manifest.parent.mkdir()
    factor_manifest.write_text("{}", encoding="utf-8")
    jit_cache = tmp_path / "jit"
    jit_cache.mkdir()
    run_dir = tmp_path / "run"
    watchdog_dir = tmp_path / "watchdog"
    captured: dict[str, object] = {}

    source = {
        "source_commit_full_sha": EXPECTED_SOURCE_SHA,
        "tracked_source_dirty": False,
    }
    monkeypatch.setattr(runner, "_m6b_w16a_factor_authority", lambda *_: {})
    monkeypatch.setattr(runner, "_m6b_w9a_load_w7", lambda *_: {})
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda *_: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: dict(source))
    monkeypatch.setattr(
        h2b,
        "_monitor_phase",
        lambda *_args: {
            "return_code": worker_return_code,
            "termination": None,
        },
    )
    monkeypatch.setattr(h2b, "_bounded_process_drain", lambda *_: {"gone": True})
    monkeypatch.setattr(
        runner,
        "_m6b_w8a_timeline_valid",
        lambda *_args, **_kwargs: {"pass": True},
    )
    monkeypatch.setattr(runner, "_write_json", lambda _path, value: captured.update(value))

    result = runner._run_m6b_w18a_watchdog(
        run_dir,
        watchdog_dir,
        w7_compact,
        w7_raw_dir,
        factor_manifest,
        jit_cache,
        EXPECTED_SOURCE_SHA,
    )

    assert result == 0
    assert captured["status"] == (
        "measurement_complete" if worker_return_code == 0 else "gate_failed"
    )
    assert captured["process"]["return_code"] == worker_return_code
    assert captured["process"]["termination"] is None
    assert captured["drain"]["gone"] is True
    assert captured["formal_pass"] is False
    assert captured["pde_pass"] is False
    assert captured["official_rta"] is False
    assert captured["physical_screen_unlocked"] is False
    assert captured["physical_screen_locked"] is True
    assert captured["resource_limits"] == {
        "timeout_seconds": 3600.0,
        "watchdog_rss_bytes": 1_950_000_000,
        "completion_peak_rss_bytes": 1_950_000_000,
        "swap_bytes": 0,
    }


def test_w18a_watchdog_parser_and_main_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_watchdog(*args):
        observed["args"] = args
        return 23

    monkeypatch.setattr(runner, "_run_m6b_w18a_watchdog", fake_watchdog)
    result = runner.main(
        [
            "m6b-w18a-watchdog",
            "--run-dir",
            "run",
            "--watchdog-dir",
            "watchdog",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7_raw",
            "--shifted-factor-manifest",
            "factor.json",
            "--jit-cache-source",
            "jit",
            "--expected-source-sha",
            EXPECTED_SOURCE_SHA,
        ]
    )

    assert result == 23
    assert [Path(value).name for value in observed["args"][:-1]] == [
        "run",
        "watchdog",
        "w7.json",
        "w7_raw",
        "factor.json",
        "jit",
    ]
    assert observed["args"][-1] == EXPECTED_SOURCE_SHA
