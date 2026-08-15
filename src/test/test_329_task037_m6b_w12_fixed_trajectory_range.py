from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.checkpoint_recycle import (
    CHECKPOINT_ITERATIONS,
    W12_SCHEMA,
    run_w12_fixed_trajectory_range,
)
from src.solvers.hcurl_h2b_m5_coercive import solve_m5_b0_fixed


def _architecture() -> dict[str, object]:
    return {
        "fine_space": "uncondensed_fullspace",
        "global_matrix_materialized": False,
        "augmented_matrix_materialized": False,
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "physical_ksp_used": False,
        "pde_used": False,
    }


def _trajectory(rows: int = 4) -> dict[int, np.ndarray]:
    values = {}
    current = np.zeros(rows, dtype=np.complex128)
    for index, iteration in enumerate(CHECKPOINT_ITERATIONS):
        current = current.copy()
        current[index] = 1.0 + (index + 1) * 0.25j
        values[iteration] = current
    return values


def _solve_factory(
    solutions: dict[int, np.ndarray], *, omit: int | None = None, **changes: object
):
    def solve(observer):
        for iteration in CHECKPOINT_ITERATIONS:
            if iteration != omit:
                observer(iteration, solutions[iteration])
        result: dict[str, object] = {
            "max_it": 200,
            "ksp_type": "fgmres",
            "initial_solution": "zero_start",
            "iterations": 200,
            "converged_reason": -3,
            "true_residual": 4.0e-9,
            "solution": solutions[200].copy(),
            "pc_apply_count": 200,
            "operator_apply_count": 211,
            "finite": True,
            "restart": 20,
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "rtol": 0.0,
            "atol": 0.0,
            **changes,
        }
        return result

    return solve


def _run(
    q: np.ndarray,
    target: np.ndarray,
    *,
    physical,
    b0_solve=None,
):
    solutions = _trajectory(q.size)
    return run_w12_fixed_trajectory_range(
        q,
        target,
        b0_solve=b0_solve or _solve_factory(solutions),
        physical_action=physical,
        architecture=_architecture(),
        predicted_live_set_bytes=runner.M6B_W12_PREDICTED_LIVE_SET_BYTES,
    )


def test_w12_fixed_trajectory_builds_four_increments_and_repeats_projection() -> None:
    q = np.array([1 + 2j, -2 + 0.5j, 0.25 - 1j, 3 + 0j], dtype=np.complex128)
    target = np.array([0.5 - 1j, 2 + 0.25j, -1 + 2j, 0.75j], dtype=np.complex128)
    physical_inputs: list[np.ndarray] = []

    def physical(value: np.ndarray) -> np.ndarray:
        physical_inputs.append(value.copy())
        return value.copy()

    result = _run(q, target, physical=physical)
    assert result["schema"] == W12_SCHEMA
    assert result["classification"] == "W12_PASS"
    assert result["selected_range"] == "dX_dAX_4D"
    assert result["trajectory"]["checkpoint_iterations"] == CHECKPOINT_ITERATIONS
    assert result["trajectory"]["physical_action_count"] == 4
    assert len(physical_inputs) == 4
    assert "solution" not in result["b0"]["solve200"]
    assert result["measurement"]["q"]["repeat_exact"] is True
    assert result["measurement"]["target"]["repeat_exact"] is True
    assert all(result["checks"].values())
    expected_increments = np.column_stack(
        (
            physical_inputs[0],
            physical_inputs[1] - physical_inputs[0],
            physical_inputs[2] - physical_inputs[1],
            physical_inputs[3] - physical_inputs[2],
        )
    )
    assert np.array_equal(result["_trajectory_vectors"]["dX"], expected_increments)
    assert np.array_equal(result["_trajectory_vectors"]["dAX"], expected_increments)


def test_w12_missing_checkpoint_locks_physical_and_selected_range() -> None:
    q = np.ones(4, dtype=np.complex128)
    calls: list[np.ndarray] = []
    result = _run(
        q,
        q.copy(),
        b0_solve=_solve_factory(_trajectory(), omit=150),
        physical=lambda value: calls.append(value.copy()),
    )
    assert result["classification"] == "W12_B0_TRAJECTORY_FAIL"
    assert result["selected_range"] is None
    assert result["checks"]["checkpoint_set"] is False
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    (("iterations", 199), ("converged_reason", -2), ("pc_apply_count", 199)),
)
def test_w12_fixed_200_contract_rejects_incomplete_budget(
    field: str, value: int
) -> None:
    q = np.ones(4, dtype=np.complex128)
    calls: list[np.ndarray] = []
    result = _run(
        q,
        q.copy(),
        b0_solve=_solve_factory(_trajectory(), **{field: value}),
        physical=lambda item: calls.append(item.copy()),
    )
    assert result["classification"] == "W12_B0_TRAJECTORY_FAIL"
    assert result["selected_range"] is None
    assert calls == []


def test_w12_rank_or_projection_gate_failure_does_not_raise_or_select_range() -> None:
    q = np.ones(4, dtype=np.complex128)
    result = _run(q, q.copy(), physical=lambda value: np.zeros_like(value))
    assert result["classification"] == "W12_TRAJECTORY_RANGE_FAIL"
    assert result["selected_range"] is None
    assert result["checks"]["range"] is False
    assert result["trajectory"]["physical_action_count"] == 4

    outside = np.zeros(5, dtype=np.complex128)
    outside[-1] = 1.0
    gate_result = _run(outside, outside.copy(), physical=lambda value: value.copy())
    assert gate_result["classification"] == "W12_TRAJECTORY_RANGE_FAIL"
    assert gate_result["checks"]["q_projection"] is False
    assert gate_result["checks"]["target_projection"] is False
    assert gate_result["selected_range"] is None


def test_w12_target_is_validation_only_when_its_gate_fails() -> None:
    q = np.zeros(5, dtype=np.complex128)
    q[0] = 1.0
    target_a = np.zeros(5, dtype=np.complex128)
    target_a[-1] = 1.0
    target_b = 2.0 * target_a
    first_actions: list[np.ndarray] = []
    second_actions: list[np.ndarray] = []
    first = _run(
        q,
        target_a,
        physical=lambda value: first_actions.append(value.copy()) or value.copy(),
    )
    second = _run(
        q,
        target_b,
        physical=lambda value: second_actions.append(value.copy()) or value.copy(),
    )
    assert first["classification"] == "W12_TRAJECTORY_RANGE_FAIL"
    assert second["classification"] == "W12_TRAJECTORY_RANGE_FAIL"
    assert first["checks"]["q_projection"] is True
    assert first["checks"]["target_projection"] is False
    assert first["selected_range"] is None
    assert "_trajectory_vectors" not in first
    assert "_trajectory_vectors" not in second
    assert len(first_actions) == len(second_actions) == 4
    assert all(np.array_equal(left, right) for left, right in zip(first_actions, second_actions))


def test_w12_final_artifacts_are_written_only_for_a_final_pass(tmp_path: Path) -> None:
    q = np.array([1 + 1j, 2 - 1j, 0.5j, -1 + 2j], dtype=np.complex128)
    passing = _run(q, q.copy(), physical=lambda value: value.copy())
    records = runner._m6b_w12_promote_trajectory_vectors(
        tmp_path,
        passing,
        error=None,
        jit_cache_final_error=None,
        lifecycle_ok=True,
    )
    assert records is not None
    assert set(records) == {"dX", "dAX"}
    assert "_trajectory_vectors" not in passing
    for role, record in records.items():
        path = Path(record["path"])
        loaded = np.load(path, allow_pickle=False)
        assert record["bytes"] == path.stat().st_size
        assert record["array_sha256"] == runner._m6b_w2_array_sha256(loaded)
        assert record["file_sha256"] == runner._sha256_file(path)
        assert loaded.shape == (4, 4)
        assert role in {"dX", "dAX"}

    failed_dir = tmp_path / "failed"
    failed_dir.mkdir()
    failed = _run(q, q.copy(), physical=lambda value: np.zeros_like(value))
    assert runner._m6b_w12_promote_trajectory_vectors(
        failed_dir,
        failed,
        error=None,
        jit_cache_final_error=None,
        lifecycle_ok=True,
    ) is None
    assert list(failed_dir.iterdir()) == []

    final_failure_dir = tmp_path / "final_failure"
    final_failure_dir.mkdir()
    passing_again = _run(q, q.copy(), physical=lambda value: value.copy())
    assert runner._m6b_w12_promote_trajectory_vectors(
        final_failure_dir,
        passing_again,
        error="source changed",
        jit_cache_final_error=None,
        lifecycle_ok=True,
    ) is None
    assert list(final_failure_dir.iterdir()) == []
    status = runner._m6b_w12_finalize_status(passing_again, "source changed", None)
    assert status[1] == "W12_EXECUTION_FAIL_AFTER_NUMERIC"
    assert status[3] is False


def test_w12_parser_and_runner_contract_are_fixed_without_action_or_pde() -> None:
    args = runner._parser().parse_args(
        [
            "m6b-w12-diagnostic",
            "--run-dir", "run",
            "--w5-compact", "w5.json",
            "--w5-raw-dir", "w5",
            "--w7-compact", "w7.json",
            "--w7-raw-dir", "w7",
            "--m3y-manifest", "m3y.json",
            "--jit-cache-source", "physical-jit",
            "--b0-jit-cache-source", "b0-jit",
            "--expected-source-sha", "a" * 40,
        ]
    )
    assert args.command == "m6b-w12-diagnostic"
    assert not hasattr(args, "max_it")
    assert not hasattr(args, "checkpoint_iterations")
    assert runner._m6b_w12_predicted_live_set()["bytes"] == 1_308_865_606
    assert runner._m6b_w12_scope()["resource_limits"]["predicted_live_set_bytes"] == 1_308_865_606
    solver_source = inspect.getsource(solve_m5_b0_fixed)
    assert "current.buildSolution(monitor_solution)" in solver_source
    assert "operator.mult(monitor_solution" not in solver_source
    solve_source = inspect.getsource(runner._run_m6b_w11a_diagnostic)
    assert "m6b-w11a-diagnostic" not in solve_source
    physical_source_start = solve_source.index("def physical_numpy")
    assert solve_source.index("release_b0()", physical_source_start) < solve_source.index(
        "ensure_physical_action()", physical_source_start
    )
    ensure_source = solve_source[
        solve_source.index("def ensure_b0()") : solve_source.index(
            "def b0_exact_action", solve_source.index("def ensure_b0()")
        )
    ]
    assert 'if is_w11b or is_w12:' in ensure_source
    assert 'action_audit["lifecycle_events"].append("b0_constructed")' in ensure_source
    assert 'expected_lifecycle = ["b0_constructed", "b0_released"]' in solve_source
    assert 'expected_lifecycle += ["physical_constructed", "physical_released"]' in solve_source
    assert 'measurement_fields["selected_range"]' in solve_source
    assert 'measurement_fields["selected_level"]' in solve_source
