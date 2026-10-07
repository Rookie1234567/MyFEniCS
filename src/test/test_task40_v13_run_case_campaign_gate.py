"""No-FE CLI contract for V13 identities and V14-authorized assembly fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_case
from src.runners import task038_launcher

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
CAMPAIGN_WINDOW = (
    ROOT
    / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w13_wsl/"
    "campaign_window_v13.json"
)
V13_CASES = (
    (
        "b0_p6_reference_v13.dat",
        "task40extra_0p7nm_b0_p6_reference_v13",
    ),
    (
        "nonseparable_gx560_p6_reference_v13.dat",
        "task40extra_0p7nm_nonseparable_gx560_p6_reference_v13",
    ),
    (
        "nonseparable_gx784_p6_reference_v13.dat",
        "task40extra_0p7nm_nonseparable_gx784_p6_reference_v13",
    ),
)
V14_LEGACY_CASES = (
    (
        "b0_p6_reference_v13.dat",
        "task40extra_0p7nm_b0_p6_reference_v13",
        True,
    ),
    (
        "nonseparable_gx560_p6_reference_v14_legacy.dat",
        "task40extra_0p7nm_nonseparable_gx560_p6_reference_v13",
        False,
    ),
    (
        "nonseparable_gx784_p6_reference_v14_legacy.dat",
        "task40extra_0p7nm_nonseparable_gx784_p6_reference_v13",
        False,
    ),
)


def _require_campaign_artifacts() -> None:
    if not CAMPAIGN_WINDOW.is_file():
        pytest.skip("the authorized fixed V13 campaign-window artifact is unavailable")


@pytest.mark.parametrize(("filename", "run_id"), V13_CASES)
def test_run_case_validate_only_accepts_each_v13_identity_with_fixed_window(
    filename: str, run_id: str, capsys: pytest.CaptureFixture[str]
):
    _require_campaign_artifacts()
    exit_code = run_case.main(
        [
            str(INPUT_ROOT / filename),
            "--validate-only",
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err or captured.out
    assert json.loads(captured.out) == {
        "method": "full3d_iterative",
        "model_id": "task40extra_nonseparable_0p7nm",
        "run_id": run_id,
        "status": "valid",
    }


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            'run_id = "task40extra_0p7nm_b0_p6_reference_v13"',
            'run_id = "task40extra_0p7nm_b0_p6_reference_v12"',
        ),
        (
            'preconditioner = "task40extra_v10_p6_y_orbit_reference_v1"',
            'preconditioner = "full3d_scalable_v1"',
        ),
        (
            'task40_reference_pc_strategy = "STRICT_THEN_BOUNDED_INEXACT_V13"',
            'task40_reference_pc_strategy = "STRICT_ONLY"',
        ),
    ),
)
def test_run_case_rejects_v13_run_profile_or_strategy_mismatch_with_window(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    old: str,
    new: str,
):
    _require_campaign_artifacts()
    text = (INPUT_ROOT / "b0_p6_reference_v13.dat").read_text(encoding="utf-8")
    assert text.count(old) == 1
    invalid_input = tmp_path / "invalid_v13_identity.dat"
    invalid_input.write_text(text.replace(old, new, 1), encoding="utf-8")

    exit_code = run_case.main(
        [
            str(invalid_input),
            "--validate-only",
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Task38 input error:" in captured.err


def test_run_case_still_rejects_campaign_window_for_unrelated_profile(
    capsys: pytest.CaptureFixture[str],
):
    _require_campaign_artifacts()
    template = ROOT / "input/templates/full3d_iterative_example.dat"
    exit_code = run_case.main(
        [
            str(template),
            "--validate-only",
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "restricted to reviewed Task40" in captured.err


@pytest.mark.parametrize(
    ("filename", "run_id", "rewrite_to_temporary_input"), V14_LEGACY_CASES
)
def test_run_case_validate_only_accepts_reviewed_legacy_assembly_for_v13_identity(
    tmp_path: Path,
    filename: str,
    run_id: str,
    rewrite_to_temporary_input: bool,
    capsys: pytest.CaptureFixture[str],
):
    _require_campaign_artifacts()
    input_path = INPUT_ROOT / filename
    if rewrite_to_temporary_input:
        lines = input_path.read_text(encoding="utf-8").splitlines()
        matches = [
            index
            for index, line in enumerate(lines)
            if line.startswith("task40_q_assembly_strategy =")
        ]
        assert len(matches) == 1
        lines[matches[0]] = 'task40_q_assembly_strategy = "LEGACY_GLOBAL_CSR_SUM"'
        input_path = tmp_path / "b0_p6_reference_v13_legacy_probe.dat"
        input_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    exit_code = run_case.main(
        [
            str(input_path),
            "--validate-only",
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err or captured.out
    assert json.loads(captured.out)["run_id"] == run_id


def test_run_case_rejects_unreviewed_q_assembly_strategy_with_window(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    _require_campaign_artifacts()
    text = (INPUT_ROOT / V13_CASES[0][0]).read_text(encoding="utf-8")
    lines = text.splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if line.startswith("task40_q_assembly_strategy =")
    ]
    assert len(matches) == 1
    lines[matches[0]] = 'task40_q_assembly_strategy = "UNREVIEWED_Q_ASSEMBLY"'
    invalid_input = tmp_path / "invalid_q_assembly_strategy.dat"
    invalid_input.write_text("\n".join(lines) + "\n", encoding="utf-8")
    exit_code = run_case.main(
        [
            str(invalid_input),
            "--validate-only",
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Task38 input error:" in captured.err


def test_q_assembly_policy_allows_reviewed_v13_strategies_and_keeps_strict_legacy_only():
    from src.geometry.task40_nonseparable_plan import (
        TASK40_Q_ASSEMBLY_LEGACY,
        TASK40_Q_ASSEMBLY_PREALLOCATED_V13,
        TASK40_STRICT_REFERENCE_PC_STRATEGY,
        TASK40_V13_REFERENCE_PC_STRATEGY,
        task40_q_assembly_strategy_is_allowed,
    )

    assert task40_q_assembly_strategy_is_allowed(
        TASK40_V13_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_LEGACY
    )
    assert task40_q_assembly_strategy_is_allowed(
        TASK40_V13_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_PREALLOCATED_V13
    )
    assert task40_q_assembly_strategy_is_allowed(
        TASK40_STRICT_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_LEGACY
    )
    assert not task40_q_assembly_strategy_is_allowed(
        TASK40_STRICT_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_PREALLOCATED_V13
    )
    assert not task40_q_assembly_strategy_is_allowed(
        TASK40_V13_REFERENCE_PC_STRATEGY, "UNREVIEWED_Q_ASSEMBLY"
    )
    assert not task40_q_assembly_strategy_is_allowed(
        "UNKNOWN_PC", TASK40_Q_ASSEMBLY_LEGACY
    )


def test_run_case_requires_campaign_window_for_v13_formal_entry(
    capsys: pytest.CaptureFixture[str],
):
    _require_campaign_artifacts()
    exit_code = run_case.main([str(INPUT_ROOT / V13_CASES[0][0])])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "V10/V11/V13 p6 launches require" in captured.err


def test_run_case_forwards_v13_campaign_window_to_launcher(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _require_campaign_artifacts()
    forwarded: dict[str, object] = {}

    def fake_launch(specification, **kwargs):
        forwarded["run_id"] = specification.identity["run_id"]
        forwarded.update(kwargs)
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(task038_launcher, "launch_specification", fake_launch)
    exit_code = run_case.main(
        [
            str(INPUT_ROOT / V13_CASES[0][0]),
            "--task40-v10-campaign-window",
            str(CAMPAIGN_WINDOW),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err or captured.out
    assert forwarded["run_id"] == V13_CASES[0][1]
    assert forwarded["task40_v10_campaign_window"] == CAMPAIGN_WINDOW
