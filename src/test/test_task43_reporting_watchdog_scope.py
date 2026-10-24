from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.task43_hp_adaptivity.reporting.watchdog_scope import (
    watchdog_resource_qualification,
)


def test_only_r8_may_use_the_historical_partial_window_exception() -> None:
    repo = Path("/tmp/task43-reporting-test-root")
    exact_run = repo / "benchmarks/artifacts/task43/round8_p_up_attempt1/run"
    assert watchdog_resource_qualification("round8_p", False, exact_run, repo) == (
        "R8_supervisor_terminal_absent_partial_window_only"
    )
    with pytest.raises(ValueError, match="exact historical round8_p run root"):
        watchdog_resource_qualification("round8_p", False, repo / "wrong_run", repo)
    with pytest.raises(ValueError, match="exact historical round8_p run root"):
        watchdog_resource_qualification("round7_p", False, exact_run, repo)


def test_attempt_with_terminal_watchdog_summary_is_fully_classified() -> None:
    repo = Path("/tmp/task43-reporting-test-root")
    assert watchdog_resource_qualification("round7_p", True, repo / "run", repo) == (
        "complete_supervisor_record"
    )
