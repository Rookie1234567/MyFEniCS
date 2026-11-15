"""Thin, non-FE checks for the opt-in p6 iterative diagnostic entry."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from src.io.input_loader import load_dat_input
from src.runners import pstddm_p6_convergence as profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ITERATIVE_INPUT = (
    REPOSITORY_ROOT
    / "input/pstddm_p6_convergence_workstation/13p5_h10_pstddm_iterative_diagnostic.dat"
)


def test_iterative_dat_uses_1e8_while_direct_validator_keeps_1e10():
    document = load_dat_input(ITERATIVE_INPUT).document
    iterative = profile._validate_iterative_case(document)
    assert iterative["full_residual_tolerance"] == 1.0e-8

    direct_document = dict(iterative)
    direct_document.update(
        mode="direct",
        case_id=profile.CASE_IDS[10.0],
        full_residual_tolerance=1.0e-10,
    )
    assert profile._validate_case(direct_document)["full_residual_tolerance"] == 1.0e-10

    with pytest.raises(ValueError, match="exactly 1e-8"):
        profile._validate_iterative_case({**document, "full_residual_tolerance": 1.0e-10})
    with pytest.raises(ValueError, match="full_residual_tolerance"):
        profile._validate_case({**direct_document, "full_residual_tolerance": 1.0e-8})


def test_retry5_baseline_loader_verifies_the_tracked_compact_record_hash():
    baseline = profile._load_direct_retry5_reference(REPOSITORY_ROOT)
    assert baseline["evidence_sha256"] == profile.DIRECT_RETRY5_EVIDENCE_SHA256
    assert baseline["source_sha"] == profile.DIRECT_RETRY5_REFERENCE["source_sha"]
    assert baseline["input_sha256"] == profile.DIRECT_RETRY5_REFERENCE["input_sha256"]
    assert baseline["full_residual"] > profile.FULL_RESIDUAL_TOLERANCE
    assert len(baseline["run_summary_sha256"]) == 64


def test_residual_gate_failure_stays_failure_when_field_samples_are_unavailable(tmp_path):
    baseline = profile._load_direct_retry5_reference(REPOSITORY_ROOT)
    closure = baseline["R_total"] + baseline["T_total"] + baseline["A_volume_total"] - 1.0
    summary = {
        "cell_static_condensation": {
            "full_explicit_true_residual": {
                "original_full_augmented_residual": {"relative_residual": 2.0e-8, "passed": False}
            }
        },
        "R_total": baseline["R_total"],
        "T_total": baseline["T_total"],
        "A_volume_total": baseline["A_volume_total"],
        "energy_closure_error_port_volume": closure,
    }

    gates = profile._iterative_gates(summary, tmp_path / "diagnostic", REPOSITORY_ROOT)
    assert gates["field_comparison_gate_pass"] is None
    assert gates["residual_gate_pass"] is False
    assert gates["diagnostic_gate_pass"] is False


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        ("PSTDDM_DIAGNOSTIC_GATE_FAIL", 4),
        ("PSTDDM_DIAGNOSTIC_COMPLETED_COMPARISON_UNAVAILABLE", 5),
    ],
)
def test_run_case_keeps_failure_and_incomplete_comparison_non_success(
    monkeypatch, capsys, status, expected_exit
):
    from scripts.run_case import main

    monkeypatch.setattr(
        profile,
        "run_p6_convergence_case",
        lambda *_args, **_kwargs: {"status": status, "case_id": profile.ITERATIVE_CASE_ID},
    )
    assert main([str(ITERATIVE_INPUT)]) == expected_exit
    assert status in capsys.readouterr().out


def test_stage4_solver_receives_the_explicit_linear_solver_port(monkeypatch, tmp_path):
    module_name = "src.solvers.solve_maxwell_3d_stage_4b_block_grating"
    stage4_module = ModuleType(module_name)
    calls = {}

    def fake_run(cfg, output, **kwargs):
        calls.update(cfg=cfg, output=output, **kwargs)
        return "stage4-result"

    stage4_module.run_stage4b_block_grating_3d_case = fake_run
    monkeypatch.setitem(sys.modules, module_name, stage4_module)

    port = object()
    observer = object()
    result = profile._run_p6_stage4_solver(
        "fixture-config", tmp_path, observer, linear_solver_port=port
    )
    assert result == "stage4-result"
    assert calls["linear_solver_port"] is port
    assert calls["solution_observer"] is observer
    assert calls["diagnostic_reference_incident_quadrature"] is True
