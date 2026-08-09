from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from petsc4py import PETSc

from benchmarks.run_task032_phase6_augmented import _parse_args
from benchmarks.run_task033_memory_watchdog import (
    _parse_args as _watchdog_parse_args,
    _task034_terminal_record_is_complete,
    _task034_terminal_worker_drain,
    _task037b_v4_energy_contract,
    _worker_command,
    _task037b_v5_linear_disposition,
)
import src.solvers.hybrid_fem_modal_block_ldu as block_ldu
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduFullSolveResult,
    multimetric_true_residual_decision,
    create_action_block_ldu_preconditioner,
    solve_action_block_ldu_full,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)

from src.test.test_242_task037b_v2_block_screen_runner import (
    _DenseFixedAction,
    _destroy_fixture,
    _tiny_fixture,
)


def _row(value: float = 0.5, **overrides: float) -> dict[str, float]:
    row = {
        "reported_relative_residual": value,
        "global_true_relative_residual": value,
        "bottom_true_relative_residual": value,
        "top_true_relative_residual": value,
        "modal_true_relative_residual": value,
    }
    row.update(overrides)
    return row


def _v5_parser_args() -> list[str]:
    return [
        "--task037b-v5-gate",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "block-ldu-action-full-solve",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--comparison-solver-path",
        "fast",
        "--bottom-interface-nm",
        "10",
        "--top-interface-nm",
        "110",
        "--incident-grazing-deg",
        "10",
        "--polarization-kind",
        "s",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--full3d-reference",
        "/tmp/v5-full3d-reference.json",
        "--full3d-reference-sha256",
        "0" * 64,
        "--task035c-p6-preflight-authority",
        "/tmp/v5-preflight-authority.json",
        "--task035c-p6-preflight-sha256",
        "1" * 64,
        "--verified-clean-sha",
        "2" * 40,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]


def _watchdog_v4_v5_args(*, v5: bool) -> list[str]:
    args = [
        "--target",
        "hybrid",
        "--case-label",
        "task037b-v5-command-test",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--mpi-size",
        "8",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "block-ldu-action-full-solve",
        "--comparison-solver-path",
        "fast",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--bottom-interface-nm",
        "10",
        "--top-interface-nm",
        "110",
        "--incident-grazing-deg",
        "10",
        "--polarization-kind",
        "s",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--full3d-reference",
        "/tmp/v5-full3d-reference.json",
        "--full3d-reference-sha256",
        "0" * 64,
        "--task035c-p6-preflight-authority",
        "/tmp/v5-preflight-authority.json",
        "--task035c-p6-preflight-sha256",
        "1" * 64,
        "--task037b-v4-gate",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "7200",
        "--verified-clean-sha",
        "2" * 40,
        "--run-dir",
        "/tmp/v5-worker-run",
        "--summary-output",
        "/tmp/v5-worker-summary.json",
        "--container-image",
        "myfenics-stage4:task28",
        "--container-digest",
        "sha256:" + "3" * 64,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]
    if v5:
        args.append("--task037b-v5-gate")
    return args


def test_v5_multimetric_decision_covers_frozen_seven_cases():
    pass_row = _row(1.0e-7)
    positive = multimetric_true_residual_decision(1, pass_row)
    assert positive["positive"] is True
    assert positive["identity"] == "multimetric_true_residual_gate"
    assert positive["reason"] > 0

    bottom_only = multimetric_true_residual_decision(
        3,
        _row(
            1.0e-7,
            bottom_true_relative_residual=2.0e-6,
        ),
    )
    assert bottom_only["decision"] == "ITERATING"
    assert bottom_only["positive"] is False

    top_only = multimetric_true_residual_decision(
        3,
        _row(
            1.0e-7,
            global_true_relative_residual=1.0e-7,
            bottom_true_relative_residual=1.0e-7,
            top_true_relative_residual=2.0e-6,
            modal_true_relative_residual=1.0e-7,
        ),
    )
    assert top_only["decision"] == "ITERATING"
    assert top_only["positive"] is False

    true_only = multimetric_true_residual_decision(
        3,
        _row(
            2.0e-6,
            global_true_relative_residual=1.0e-7,
            bottom_true_relative_residual=1.0e-7,
            top_true_relative_residual=1.0e-7,
            modal_true_relative_residual=1.0e-7,
        ),
    )
    assert true_only["decision"] == "ITERATING"
    assert true_only["positive"] is False

    all_at_boundary = multimetric_true_residual_decision(700, _row(1.0e-6))
    assert all_at_boundary["positive"] is True
    assert all_at_boundary["reason"] > 0

    max_it = multimetric_true_residual_decision(700, _row(2.0e-6))
    assert max_it["decision"] == "DIVERGED_MAX_IT"
    assert max_it["reason"] == int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)

    nan_result = multimetric_true_residual_decision(20, _row(float("nan")))
    assert nan_result["decision"] == "DIVERGED_NANORINF"
    negative_result = multimetric_true_residual_decision(20, _row(-1.0e-3))
    assert negative_result["decision"] == "DIVERGED_NANORINF"
    assert (
        _task037b_v5_linear_disposition(
            contract_pass=True,
            numeric=False,
            iterations=20,
            reason=-9,
            postsolve_positive=False,
            recovery_pass=False,
            own_physics_pass=False,
            canonical_pass=False,
            direct_comparator_pass=False,
        )
        == "V5_MULTIMETRIC_NUMERICAL_NEGATIVE"
    )

    v4_replay = multimetric_true_residual_decision(
        534,
        _row(
            9.83224189598995e-7,
            global_true_relative_residual=9.832241902112744e-7,
            bottom_true_relative_residual=1.3641751886101987e-6,
            top_true_relative_residual=7.290772097898545e-7,
            modal_true_relative_residual=1.2365161175289584e-15,
        ),
    )
    assert v4_replay["decision"] == "ITERATING"
    assert v4_replay["reason"] == int(PETSc.KSP.ConvergedReason.ITERATING)


def test_v5_terminal_drain_excludes_partial_nonterminal_worker_states():
    common = {
        "task034_workstation_gate": True,
        "process_running": True,
        "authority_readable": False,
        "stage": "v4_worker_cleanup_finished",
        "terminal_record_complete": True,
        "terminal_stage": "v4_worker_cleanup_finished",
        "expected_worker_count": 8,
    }
    assert _task034_terminal_worker_drain(**common, live_worker_count=4)
    assert not _task034_terminal_worker_drain(**common, live_worker_count=8)
    assert not _task034_terminal_worker_drain(**common, live_worker_count=None)
    assert not _task034_terminal_worker_drain(
        **{**common, "terminal_record_complete": False}, live_worker_count=4
    )
    assert not _task034_terminal_worker_drain(
        **{**common, "stage": "record_and_release"}, live_worker_count=4
    )


def test_v5_terminal_record_requires_real_stage_and_release(tmp_path):
    record = {
        "record_schema": "task037b.v5-multimetric-full-block-pc.v1",
        "case": {},
        "solver": {},
        "qualification": {"postprocess_release_pass": True},
        "status": "task037b_v5_linear_pass_recovery_or_physics_failed",
        "v4_telemetry": {
            "stage_markers": ["v4_worker_cleanup_finished"],
            "main_postprocess_release": {"release_pass": True},
            "multimetric": {},
        },
        "v5_telemetry": {
            "snapshot_release": {
                "snapshot_destroyed": True,
                "bottom_snapshot_destroyed": True,
                "top_snapshot_destroyed": True,
                "modal_snapshot_released": True,
            }
        },
    }
    path = tmp_path / "solver_record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert _task034_terminal_record_is_complete(path)
    for key, value in (
        ("stage_markers", ["candidate_field_recovery"]),
        ("main_postprocess_release", {"release_pass": False}),
    ):
        candidate = copy.deepcopy(record)
        candidate["v4_telemetry"][key] = value
        path.write_text(json.dumps(candidate), encoding="utf-8")
        assert not _task034_terminal_record_is_complete(path)
    candidate = copy.deepcopy(record)
    candidate["v5_telemetry"]["snapshot_release"]["modal_snapshot_released"] = False
    path.write_text(json.dumps(candidate), encoding="utf-8")
    assert not _task034_terminal_record_is_complete(path)

    legacy = {
        "schema_version": 1,
        "benchmark_id": "legacy",
        "timestamp_utc": "now",
        "status": "legacy",
        "qualification": {},
        "solve": {},
        "gates": {},
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert _task034_terminal_record_is_complete(path)
    legacy.pop("gates")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert not _task034_terminal_record_is_complete(path)


def test_v5_energy_contract_separates_measured_and_not_run_boundaries():
    measured_validation = {
        "official_record": "candidate_measured_not_official",
        "R": 0.1,
        "T": 0.2,
        "A": 0.7,
        "A_volume": {"A_volume_total": 0.7},
    }
    measured_energy = {
        "closure_error": 0.0,
        "A_balance_minus_A_volume": 0.0,
        "pass": True,
    }
    assert _task037b_v4_energy_contract(measured_validation, measured_energy) == (
        True,
        True,
    )

    not_run_energy = {
        "closure_error": -1.0e-6,
        "A_balance_minus_A_volume": 1.0e-6,
        "pass": True,
    }
    assert _task037b_v4_energy_contract(
        {"official_record": "not_run"}, not_run_energy
    ) == (True, True)
    tampered = copy.deepcopy(not_run_energy)
    tampered["closure_error"] = 2.0e-5
    assert _task037b_v4_energy_contract({"official_record": "not_run"}, tampered) == (
        False,
        False,
    )


def test_v5_parser_is_frozen_and_does_not_open_v2_options():
    ordinary = _parse_args([])
    assert ordinary.solver_path == "augmented"
    assert ordinary.task037b_v5_gate is False
    with pytest.raises(SystemExit):
        _parse_args(_v5_parser_args())
    parsed = _parse_args(_v5_parser_args() + ["--task037b-v4-gate"])
    assert parsed.task037b_v5_gate is True
    assert parsed.task037b_v4_gate is True
    assert parsed.task037b_v2_profile is None
    assert parsed.task037b_v2_max_it is None
    assert parsed.solver_path == "block-ldu-action-full-solve"
    with pytest.raises(SystemExit):
        _parse_args(_v5_parser_args() + ["--task037b-v2-profile", "double"])
    with pytest.raises(SystemExit):
        _parse_args(_v5_parser_args() + ["--task037b-v2-max-it", "200"])


def test_v5_watchdog_worker_command_has_one_v4_and_v5_flag():
    v5_args = _watchdog_parse_args(_watchdog_v4_v5_args(v5=True))
    v5_command = _worker_command(
        v5_args,
        Path("/tmp/v5-worker-record.json"),
        Path("/tmp/v5-worker-stages.jsonl"),
    )
    assert v5_command.count("--task037b-v4-gate") == 1
    assert v5_command.count("--task037b-v5-gate") == 1
    assert "--task037b-v2-profile" not in v5_command
    assert "--task037b-v2-max-it" not in v5_command

    v4_args = _watchdog_parse_args(_watchdog_v4_v5_args(v5=False))
    v4_command = _worker_command(
        v4_args,
        Path("/tmp/v4-worker-record.json"),
        Path("/tmp/v4-worker-stages.jsonl"),
    )
    assert v4_command.count("--task037b-v4-gate") == 1
    assert "--task037b-v5-gate" not in v4_command


def test_v5_watchdog_keeps_controlled_linear_negatives_out_of_implementation():
    common = {
        "recovery_pass": False,
        "own_physics_pass": False,
        "canonical_pass": False,
        "direct_comparator_pass": False,
    }
    assert (
        _task037b_v5_linear_disposition(
            contract_pass=True,
            numeric=False,
            iterations=700,
            reason=-3,
            postsolve_positive=False,
            **common,
        )
        == "MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700"
    )
    assert (
        _task037b_v5_linear_disposition(
            contract_pass=True,
            numeric=False,
            iterations=534,
            reason=2,
            postsolve_positive=False,
            **common,
        )
        == "CUSTOM_CONVERGENCE_FALSE_POSITIVE"
    )
    assert (
        _task037b_v5_linear_disposition(
            contract_pass=False,
            numeric=False,
            iterations=700,
            reason=-3,
            postsolve_positive=False,
            **common,
        )
        == "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
    )


def test_v5_full_solve_tiny_opt_in_single_history_and_retained_snapshot():
    fixture = _tiny_fixture(active_count=4)
    bottom = None
    top = None
    action_matrix = None
    action_context = None
    preconditioner = None
    rhs = None
    retained = None
    result = None
    try:
        bottom = _DenseFixedAction(fixture["bottom"].A, fixture["inverse"])
        top = _DenseFixedAction(fixture["top"].A, fixture["inverse"])
        preconditioner = create_action_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            bottom,
            top,
        )
        action_matrix, action_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        source_bottom = fixture["bottom"].A.createVecRight()
        source_top = fixture["top"].A.createVecRight()
        source_bottom.set(1.0)
        source_top.set(-0.5)
        rhs = fixture["layout"].pack(
            source_bottom,
            source_top,
            np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j]),
        )
        source_bottom.destroy()
        source_top.destroy()
        result = solve_action_block_ldu_full(
            action_matrix,
            rhs,
            preconditioner,
            max_it=700,
            v5_multimetric=True,
        )
        preconditioner = None
        assert isinstance(result, HybridBlockLduFullSolveResult)
        assert [row["iteration"] for row in result.history] == list(
            range(result.iterations + 1)
        )
        assert result.history_evaluation_count == len(result.history)
        assert result.postsolve_evaluation_count == 1
        assert result.postsolve_audit["identity"] == "multimetric_true_residual_gate"
        assert result.postsolve_audit["restart"] == 90
        assert result.release["ksp_destroyed"] is True
        assert result.release["pc_context_destroyed"] is True
        assert result.release["borrowed_side_actions_retained"] is True
        retained = action_matrix.createVecRight()
        result.solution.copy(retained)
        result.destroy()
        assert bottom.destroyed is False
        assert top.destroyed is False
        assert retained.getSize() == action_matrix.getSize()[0]
        assert action_context._destroyed is False
    finally:
        if retained is not None:
            retained.destroy()
        if result is not None:
            result.destroy()
        if preconditioner is not None:
            preconditioner.destroy()
        if rhs is not None:
            rhs.destroy()
        if action_matrix is not None:
            action_matrix.destroy()
        if action_context is not None:
            action_context.destroy()
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        _destroy_fixture(fixture)


def test_v5_tiny_callback_continues_after_reported_pass_block_failure(monkeypatch):
    fixture = _tiny_fixture(active_count=4)
    bottom = None
    top = None
    action_matrix = None
    action_context = None
    preconditioner = None
    rhs = None
    result = None
    calls = 0
    callback_rows = []

    def fake_residual_metrics(operator, right_hand_side, solution, context):
        nonlocal calls
        calls += 1
        if calls == 1:
            value = _row(0.5)
        elif calls == 2:
            value = _row(
                1.0e-7,
                global_true_relative_residual=1.0e-7,
                bottom_true_relative_residual=2.0e-6,
                top_true_relative_residual=1.0e-7,
                modal_true_relative_residual=1.0e-7,
            )
        else:
            value = _row(1.0e-7)
        return value["global_true_relative_residual"], {
            "bottom": value["bottom_true_relative_residual"],
            "top": value["top_true_relative_residual"],
            "modal": value["modal_true_relative_residual"],
        }

    monkeypatch.setattr(block_ldu, "_residual_metrics", fake_residual_metrics)
    try:
        bottom = _DenseFixedAction(fixture["bottom"].A, fixture["inverse"])
        top = _DenseFixedAction(fixture["top"].A, fixture["inverse"])
        preconditioner = create_action_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            bottom,
            top,
        )
        action_matrix, action_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        source_bottom = fixture["bottom"].A.createVecRight()
        source_top = fixture["top"].A.createVecRight()
        source_bottom.set(1.0)
        source_top.set(-0.5)
        rhs = fixture["layout"].pack(
            source_bottom,
            source_top,
            np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j]),
        )
        source_bottom.destroy()
        source_top.destroy()
        result = solve_action_block_ldu_full(
            action_matrix,
            rhs,
            preconditioner,
            max_it=700,
            checkpoint_callback=callback_rows.append,
            v5_multimetric=True,
        )
        preconditioner = None
        block_failed_after_reported_pass = [
            row
            for row in result.history
            if row["reported_relative_residual"] <= 1.0e-6
            and row["multimetric_decision"] == "ITERATING"
            and row["bottom_true_relative_residual"] > 1.0e-6
        ]
        assert block_failed_after_reported_pass
        assert result.postsolve_audit["pass"] is True
        assert result.postsolve_evaluation_count == 1
        assert result.history_evaluation_count == len(result.history)
        assert calls == (
            result.history_evaluation_count + result.postsolve_evaluation_count
        )
        assert callback_rows
        assert all(
            {
                "multimetric_max_true_residual",
                "multimetric_decision",
                "multimetric_reason",
                "multimetric_identity",
            }
            <= row.keys()
            for row in callback_rows
        )
        assert result.history[-1]["multimetric_decision"].startswith("CONVERGED_")
        assert result.converged_reason > 0
    finally:
        if result is not None:
            result.destroy()
        if preconditioner is not None:
            preconditioner.destroy()
        if rhs is not None:
            rhs.destroy()
        if action_matrix is not None:
            action_matrix.destroy()
        if action_context is not None:
            action_context.destroy()
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        _destroy_fixture(fixture)
