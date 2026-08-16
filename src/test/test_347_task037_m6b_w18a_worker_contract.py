"""Focused pure contracts for the W18A worker orchestration."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w18_nested_auxiliary_pc as w18


_W18A_CORE_CHECKS = (
    "schema",
    "fixed_identity",
    "outer_audits",
    "inner_residual",
    "outer_auxiliary_residual",
    "finite",
    "repeat_identity",
    "measurements",
    "action_counts",
    "architecture",
    "lifecycle",
    "prediction",
    "source",
    "cache",
    "execution",
)


def _checks(**overrides: bool) -> dict[str, bool]:
    result = {name: True for name in _W18A_CORE_CHECKS}
    result.update(overrides)
    return result


def test_w18a_scope_prediction_and_counts_match_core() -> None:
    scope = runner._m6b_w18a_scope()
    prediction = runner._m6b_w18a_predicted_live_set()
    assert scope["schema"] == w18.W18A_SCHEMA
    assert scope["phase"] == runner.M6B_W18A_PHASE
    assert scope["action_counts"] == w18.W18A_ACTION_COUNTS
    assert runner.M6B_W18A_ACTION_COUNTS == w18.W18A_ACTION_COUNTS
    assert prediction["bytes"] == sum(prediction["components"].values())
    assert prediction["bytes"] == w18.W18A_PREDICTED_LIVE_SET_BYTES
    assert prediction["gate"] is True
    assert prediction["bytes"] <= prediction["limit_bytes"]
    assert prediction["scratch_components"] == {
        "inner_per_apply_bytes": 228_028_224,
        "inner_per_repeat_bytes": 456_056_448,
        "outer_per_repeat_bytes": 13_904_160,
        "total_per_repeat_bytes": 469_960_608,
        "two_repeat_total_bytes": 939_921_216,
    }


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        (_checks(), "PASS"),
        (_checks(inner_residual=False), "NUMERIC_FAIL"),
        (_checks(outer_auxiliary_residual=False), "NUMERIC_FAIL"),
        (_checks(source=False), "EVIDENCE_FAIL"),
    ],
)
def test_w18a_final_status_is_complete_and_fail_closed(
    checks: dict[str, bool], expected: str
) -> None:
    result = runner._m6b_w18a_final_status(checks, None)
    assert result[0] is (expected == "PASS")
    assert expected in result[2]


def test_w18a_final_status_rejects_incomplete_checks() -> None:
    result = runner._m6b_w18a_final_status(
        {"inner_residual": True, "measurements": True}, None
    )
    assert result == (
        False,
        "gate_failed",
        "W18A_EXECUTION_OR_EVIDENCE_FAIL",
    )


def test_w18a_raw_inventory_has_checkpoint_physical_and_all_scratch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    names: list[str] = []

    def fake_artifact(_root: Path, name: str) -> dict[str, str]:
        names.append(name)
        return {"path": name}

    monkeypatch.setattr(runner, "_artifact", fake_artifact)
    artifacts = runner._m6b_w16a_raw_artifacts(tmp_path, mode="w18a")
    assert len(artifacts) == 46
    assert sum("m6b_iter" in name for name in names) == 16
    assert sum(name.startswith("w18a_p_") for name in names) == 4
    scratch = [name for name in names if name.startswith("outer_scratch/")]
    assert len(scratch) == 24
    assert len(set(scratch)) == 24
    assert all(name.startswith("outer_scratch/repeat1/") or
               name.startswith("outer_scratch/repeat2/") for name in scratch)


def test_w18a_progress_mode_requires_the_complete_marker_order(
    tmp_path: Path,
) -> None:
    progress = tmp_path / runner.M6B_W18A_PROGRESS_FILENAME
    records = [
        {
            "schema": f"{runner.M6B_W18A_SCHEMA}.progress.v1",
            "phase": runner.M6B_W18A_PHASE,
            "event": event,
        }
        for event in runner.M6B_W18A_EVENTS
    ]
    progress.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    result = runner._m6b_w16a_progress_valid(progress, mode="w18a")
    assert result["pass"] is True
    assert result["events"] == list(runner.M6B_W18A_EVENTS)


def test_w18a_disk_difference_is_finite_or_raises(tmp_path: Path) -> None:
    first = np.array([1 + 2j, 3 - 1j], dtype=np.complex128)
    second = first.copy()
    first_path = tmp_path / "first.npy"
    second_path = tmp_path / "second.npy"
    np.save(first_path, first)
    np.save(second_path, second)
    assert runner._m6b_w18a_disk_relative_difference(
        first_path, second_path
    ) == 0.0
    second[0] = np.nan + 0j
    np.save(second_path, second)
    with pytest.raises(ValueError):
        runner._m6b_w18a_disk_relative_difference(first_path, second_path)


def test_w18a_fixed_dtn_work_vec_and_marker_contract() -> None:
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    assert "dtn_action.matrix.createVecRight()" in source
    assert "dtn_action.matrix.createVecLeft()" in source
    assert "dtn_action.output_vector" not in source
    assert "dtn_action.apply(dtn_source, dtn_target)" in source
    assert '"auxiliary_constructed"' in source
    assert '"finite": True' in source
    assert 'measurement["checkpoint"] = iteration' in source
    assert '"residual_closure"' in source
    assert '"w18a_formal_candidate"' in source
    assert '"physical_screen_locked": True' in source
    assert '"physical_screen_candidate": False' in source
    assert '"w18b_action_candidate"' not in source


def test_w18a_wrapper_forces_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append(kwargs)
        return 19

    monkeypatch.setattr(runner, "_run_m6b_w16a_diagnostic", fake)
    result = runner._run_m6b_w18a_diagnostic(
        Path("run"),
        Path("w7.json"),
        Path("w7raw"),
        Path("factor.json"),
        Path("jit"),
        "a" * 40,
    )
    assert result == 19
    assert calls == [{"mode": "w18a"}]


def test_w18a_worker_command_is_fixed() -> None:
    command = runner._m6b_w18a_worker_command(
        Path("run"),
        Path("w7.json"),
        Path("w7raw"),
        Path("factor.json"),
        Path("jit"),
        "a" * 40,
    )
    assert "m6b-w18a-nested-auxiliary-diagnostic" in command
    assert command[command.index("--run-dir") + 1].endswith("/run")
    assert command[command.index("--w7-compact") + 1].endswith("/w7.json")
    assert command[-1] == "a" * 40


def test_w18a_parser_and_main_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = [
        "m6b-w18a-nested-auxiliary-diagnostic",
        "--run-dir", "run",
        "--w7-compact", "w7.json",
        "--w7-raw-dir", "w7raw",
        "--shifted-factor-manifest", "factor.json",
        "--jit-cache-source", "jit",
        "--expected-source-sha", "b" * 40,
    ]
    assert runner._parser().parse_args(argv).command == argv[0]
    calls: list[tuple[object, ...]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append(args)
        return 23

    monkeypatch.setattr(runner, "_run_m6b_w18a_diagnostic", fake)
    assert runner.main(argv) == 23
    assert len(calls) == 1
