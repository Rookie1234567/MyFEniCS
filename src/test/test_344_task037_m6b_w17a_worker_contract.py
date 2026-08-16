"""Focused pure contracts for the W17A worker orchestration."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w16_global_shifted_inner_pc as core


_W17A_STATUS_KEYS = (
    "schema",
    "fixed_identity",
    "inner_audits",
    "inner_residual",
    "z_identity",
    "p_identity",
    "measurements",
    "action_counts",
    "architecture",
    "lifecycle",
    "prediction",
    "source",
    "cache",
    "execution",
)


def _status_checks(**overrides: bool) -> dict[str, bool]:
    checks = {key: True for key in _W17A_STATUS_KEYS}
    checks.update(overrides)
    return checks


def test_w17a_scope_and_prediction_reuse_core_constants() -> None:
    scope = runner._m6b_w17a_scope()
    prediction = runner._m6b_w17a_predicted_live_set()
    assert scope["schema"] == core.W17A_SCHEMA
    assert scope["auxiliary_operator"] == core.W17A_AUXILIARY_OPERATOR
    assert scope["physical_operator"] == core.W17A_PHYSICAL_OPERATOR
    assert scope["shared_dtn_instance_count"] == 1
    assert prediction["bytes"] == core.W17A_PREDICTED_LIVE_SET_BYTES
    assert prediction["components"] == core.W17A_PREDICTION_COMPONENTS
    assert prediction["scratch_two_run_total_bytes"] == 456_056_448


@pytest.mark.parametrize(
    ("checks", "error", "expected"),
    [
        (_status_checks(), None, "PASS"),
        (_status_checks(inner_residual=False), None, "NUMERIC_FAIL"),
        (_status_checks(), "failed", "EVIDENCE_FAIL"),
    ],
)
def test_w17a_final_status_classifies_numeric_only_failures(
    checks: dict[str, bool], error: str | None, expected: str
) -> None:
    result = runner._m6b_w17a_final_status(checks, error)
    assert result[0] is (expected == "PASS")
    assert expected in result[2]


def test_w17a_final_status_rejects_incomplete_checks() -> None:
    result = runner._m6b_w17a_final_status(
        {"inner_residual": True, "measurements": True}, None
    )
    assert result[0] is False
    assert "EXECUTION_OR_EVIDENCE_FAIL" in result[2]


def test_w17a_thin_wrapper_forces_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append((args, kwargs))
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w16a_diagnostic", fake)
    result = runner._run_m6b_w17a_diagnostic(
        Path("run"),
        Path("w7.json"),
        Path("w7raw"),
        Path("factor.json"),
        Path("jit"),
        "a" * 40,
    )
    assert result == 17
    assert calls[0][1] == {"mode": "w17a"}


def test_w17a_solution_hash_is_checked_without_overwrite() -> None:
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    assert 'audit["solution_sha256"] != artifact["array_sha256"]' in source
    assert '"solution_sha256": artifact["array_sha256"]' not in source


def test_w17a_parser_and_main_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = [
        "m6b-w17a-global-physical-shifted-diagnostic",
        "--run-dir", "run",
        "--w7-compact", "w7.json",
        "--w7-raw-dir", "w7raw",
        "--shifted-factor-manifest", "factor.json",
        "--jit-cache-source", "jit",
        "--expected-source-sha", "b" * 40,
    ]
    parsed = runner._parser().parse_args(argv)
    assert parsed.command == argv[0]
    calls: list[tuple[object, ...]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append(args)
        return 23

    monkeypatch.setattr(runner, "_run_m6b_w17a_diagnostic", fake)
    assert runner.main(argv) == 23
    assert len(calls) == 1
    assert runner._parser().parse_args(
        [
            "m6b-w16a-global-shifted-inner-diagnostic",
            "--run-dir", "r",
            "--w7-compact", "c",
            "--w7-raw-dir", "raw",
            "--shifted-factor-manifest", "f",
            "--jit-cache-source", "j",
            "--expected-source-sha", "c" * 40,
        ]
    ).command == "m6b-w16a-global-shifted-inner-diagnostic"
