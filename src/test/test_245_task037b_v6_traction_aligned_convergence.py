from __future__ import annotations

from pathlib import Path

import numpy as np
from petsc4py import PETSc

import benchmarks.run_task033_memory_watchdog as watchdog
from benchmarks.run_task032_phase6_augmented import (
    _parse_args,
    _v4_full_fe_threshold_pass as _runner_full_fe_threshold_pass,
    _v4_not_run_validation_boundary,
)
from benchmarks.run_task033_memory_watchdog import (
    _parse_args as _watchdog_parse_args,
    _task037b_v6_linear_disposition,
    _worker_command,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
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
from src.test.test_244_task037b_v5_multimetric_convergence import (
    _v5_parser_args,
    _watchdog_v4_v5_args,
)


def _row(value: float = 1.0e-8, **overrides: float) -> dict[str, float]:
    row = {
        "reported_relative_residual": value,
        "global_true_relative_residual": value,
        "bottom_true_relative_residual": value,
        "top_true_relative_residual": value,
        "modal_true_relative_residual": value,
    }
    row.update(overrides)
    return row


def test_v6_decision_is_tight_and_profile_pair_is_frozen():
    old_v5 = multimetric_true_residual_decision(557, _row(1.0e-6))
    assert old_v5["positive"] is True
    assert old_v5["identity"] == "multimetric_true_residual_gate"

    v6_old_row = multimetric_true_residual_decision(
        557,
        _row(1.0e-6),
        max_it=1000,
        threshold=5.0e-9,
        identity="traction_aligned_multimetric_true_residual_gate",
    )
    assert v6_old_row["decision"] == "ITERATING"
    assert v6_old_row["positive"] is False

    tight_pass = multimetric_true_residual_decision(
        1,
        _row(4.0e-9),
        max_it=1000,
        threshold=5.0e-9,
        identity="traction_aligned_multimetric_true_residual_gate",
    )
    assert tight_pass["positive"] is True
    assert tight_pass["reason"] > 0
    assert tight_pass["identity"] == "traction_aligned_multimetric_true_residual_gate"

    tight_fail = multimetric_true_residual_decision(
        2,
        _row(4.0e-9, top_true_relative_residual=6.0e-9),
        max_it=1000,
        threshold=5.0e-9,
        identity="traction_aligned_multimetric_true_residual_gate",
    )
    assert tight_fail["decision"] == "ITERATING"
    assert tight_fail["positive"] is False

    for invalid in (float("nan"), float("inf"), -1.0e-9):
        result = multimetric_true_residual_decision(
            2,
            _row(invalid),
            max_it=1000,
            threshold=5.0e-9,
            identity="traction_aligned_multimetric_true_residual_gate",
        )
        assert result["decision"] == "DIVERGED_NANORINF"
        assert result["reason"] == -9

    max_result = multimetric_true_residual_decision(
        1000,
        _row(6.0e-9),
        max_it=1000,
        threshold=5.0e-9,
        identity="traction_aligned_multimetric_true_residual_gate",
    )
    assert max_result["decision"] == "DIVERGED_MAX_IT"
    assert max_result["reason"] == int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)

    with np.testing.assert_raises(ValueError):
        multimetric_true_residual_decision(
            1,
            _row(1.0e-7),
            max_it=1000,
            threshold=1.0e-6,
            identity="traction_aligned_multimetric_true_residual_gate",
        )


def test_v6_recovery_thresholds_are_profile_specific():
    helpers = (_runner_full_fe_threshold_pass, watchdog._v4_full_fe_threshold_pass)
    tight_values = (1.0e-8, 1.0e-10, 1.0e-10)
    old_values = (1.0e-6, 1.0e-8, 1.0e-8)
    for helper in helpers:
        assert helper(*tight_values, tight=True)
        assert helper(*old_values, tight=False)
        assert not helper(*old_values, tight=True)
        for index, value in enumerate(tight_values):
            exceeded = list(tight_values)
            exceeded[index] = value * (1.0 + 1.0e-6)
            assert not helper(*exceeded, tight=True)


def test_v6_parser_and_worker_command_require_v4_v5_pair():
    ordinary = _parse_args([])
    assert ordinary.task037b_v6_gate is False

    with np.testing.assert_raises(SystemExit):
        _parse_args(_v5_parser_args() + ["--task037b-v6-gate"])

    parsed = _parse_args(
        _v5_parser_args() + ["--task037b-v4-gate", "--task037b-v6-gate"]
    )
    assert parsed.task037b_v5_gate is True
    assert parsed.task037b_v6_gate is True

    watchdog_args = _watchdog_parse_args(
        _watchdog_v4_v5_args(v5=True) + ["--task037b-v6-gate"]
    )
    command = _worker_command(
        watchdog_args,
        Path("/tmp/v6-worker-record.json"),
        Path("/tmp/v6-worker-stages.jsonl"),
    )
    assert command.count("--task037b-v4-gate") == 1
    assert command.count("--task037b-v5-gate") == 1
    assert command.count("--task037b-v6-gate") == 1
    assert "--task037b-v2-profile" not in command
    assert "--task037b-v2-max-it" not in command


def test_v6_dispositions_keep_physics_and_parent_control_lanes_separate():
    common = {
        "recovery_pass": False,
        "own_physics_pass": False,
        "canonical_pass": False,
        "direct_comparator_pass": False,
    }
    assert (
        _task037b_v6_linear_disposition(
            contract_pass=True,
            numeric=False,
            iterations=1000,
            reason=-3,
            postsolve_positive=False,
            **common,
        )
        == "TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000"
    )
    assert (
        _task037b_v6_linear_disposition(
            contract_pass=True,
            numeric=False,
            iterations=100,
            reason=2,
            postsolve_positive=False,
            **common,
        )
        == "TIGHT_CUSTOM_CONVERGENCE_FALSE_POSITIVE"
    )
    assert (
        _task037b_v6_linear_disposition(
            contract_pass=True,
            numeric=True,
            iterations=100,
            reason=2,
            postsolve_positive=True,
            recovery_pass=True,
            own_physics_pass=False,
            canonical_pass=False,
            direct_comparator_pass=False,
            traction_pass=False,
        )
        == "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL"
    )
    assert (
        _task037b_v6_linear_disposition(
            contract_pass=True,
            numeric=True,
            iterations=100,
            reason=2,
            postsolve_positive=True,
            recovery_pass=True,
            own_physics_pass=False,
            canonical_pass=False,
            direct_comparator_pass=False,
            traction_pass=None,
        )
        == "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
    )
    assert set(_v4_not_run_validation_boundary().values()) == {"not_run"}


def test_v6_evaluator_routes_traction_disposition(monkeypatch):
    observed: dict[str, object] = {}

    def record_v6_route(**kwargs: object) -> str:
        observed.update(kwargs)
        return "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL"

    monkeypatch.setattr(watchdog, "_task037b_v6_linear_disposition", record_v6_route)
    record = {
        "record_schema": "task037b.v6-traction-aligned-full-block-pc.v1",
        "case": {},
        "solver": {},
        "qualification": {},
        "validation": {},
        "v4_telemetry": {
            "screen": {},
            "history": [],
            "physics_gates": {
                "exact_traction_dual": {"pass": False},
            },
        },
        "v6_telemetry": {"postsolve_audit": {}},
    }
    result = watchdog._task037b_v4_evaluate_record(record)
    assert observed["traction_pass"] is False
    assert result["disposition"] == "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL"
    assert "evaluator_exception" not in result["failures"]


def test_v6_tiny_solve_has_one_decision_row_per_iteration_and_postsolve_audit():
    fixture = _tiny_fixture(active_count=4)
    bottom = top = action_matrix = action_context = preconditioner = rhs = result = None
    callback_rows: list[dict[str, object]] = []
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
            max_it=1000,
            checkpoint_callback=callback_rows.append,
            v5_multimetric=True,
            v6_traction_aligned=True,
        )
        preconditioner = None
        assert [row["iteration"] for row in result.history] == list(
            range(result.iterations + 1)
        )
        assert result.history_evaluation_count == len(result.history)
        assert result.postsolve_evaluation_count == 1
        assert result.postsolve_audit["identity"] == (
            "traction_aligned_multimetric_true_residual_gate"
        )
        assert result.postsolve_audit["threshold"] == 5.0e-9
        assert result.postsolve_audit["restart"] == 90
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
        assert len({row["iteration"] for row in callback_rows}) == len(callback_rows)
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
