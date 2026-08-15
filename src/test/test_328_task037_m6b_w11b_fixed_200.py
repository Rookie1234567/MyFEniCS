from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.persistent_residual_one_vector import (
    W11B_SCHEMA,
    run_w11b_fixed_200_exact_proxy,
)


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


def _solve(solution: np.ndarray, residual: float = 1.0e-9) -> dict[str, object]:
    return {
        "ksp_type": "fgmres",
        "max_it": 200,
        "iterations": 200,
        "converged_reason": -3,
        "true_residual": residual,
        "solution": solution.copy(),
        "pc_apply_count": 200,
        "operator_apply_count": 400,
        "finite": True,
        "initial_solution": "zero_start",
        "restart": 20,
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "rtol": 0.0,
        "atol": 0.0,
    }


def test_w11b_fixed_200_passes_both_projection_gates_with_one_physical_action() -> None:
    q = np.array([1 + 1j, 0 + 0j, 0 + 0j, 0 + 0j], dtype=np.complex128)
    calls: list[str] = []

    def b0_solve() -> dict[str, object]:
        calls.append("b0_200")
        return _solve(q)

    def physical(value: np.ndarray) -> np.ndarray:
        calls.append("physical")
        return value.copy()

    result = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=b0_solve,
        physical_action=physical,
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )

    assert calls == ["b0_200", "physical"]
    assert result["schema"] == W11B_SCHEMA
    assert result["classification"] == "W11B_PASS"
    assert result["selected_level"] == "Q1_200"
    assert result["candidate_level"] == "Q1_200"
    assert all(result["checks"].values())
    assert result["measurement"]["q"]["schema"] == W11B_SCHEMA
    assert result["measurement"]["target"]["repeat_exact"] is True
    assert result["carrier_audit"]["counters"]["b0_solve_max_it"] == 200
    assert result["carrier_audit"]["counters"]["physical_action_count"] == 1
    assert result["b0"]["solve200"]["operator_apply_count"] == 400


def test_w11b_b0_failure_locks_physical_projection() -> None:
    q = np.array([1 + 0j, 0 + 1j], dtype=np.complex128)
    physical_calls: list[np.ndarray] = []

    def physical(value: np.ndarray) -> np.ndarray:
        physical_calls.append(value.copy())
        raise AssertionError("physical action must be locked after B0 failure")

    result = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=lambda: _solve(q, residual=1.0e-7),
        physical_action=physical,
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )

    assert result["classification"] == "W11B_B0_SOLVE_FAIL"
    assert result["selected_level"] is None
    assert "measurement" not in result
    assert physical_calls == []
    assert result["checks"]["b0_solve"] is False


def test_w11b_projection_failure_has_no_selected_level_and_execution_wins() -> None:
    q = np.array([1 + 0j, 0 + 1j], dtype=np.complex128)
    result = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=lambda: _solve(q),
        physical_action=lambda _value: np.array([0, 1], dtype=np.complex128),
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )

    assert result["classification"] == "W11B_PROJECTION_FAIL"
    assert result["selected_level"] is None
    assert result["candidate_level"] == "Q1_200"
    status, classification, checks, passed, problems = runner._m6b_w11b_finalize_status(
        result, "cache verification failed", None
    )
    assert status == "gate_failed"
    assert classification == "W11B_EXECUTION_FAIL_AFTER_NUMERIC"
    assert checks["execution"] is False
    assert passed is False
    assert "execution" in problems


@pytest.mark.parametrize(
    ("field", "value"),
    (("iterations", 199), ("converged_reason", -2), ("pc_apply_count", 199)),
)
def test_w11b_fixed_contract_rejects_incomplete_200_budget(
    field: str, value: int
) -> None:
    q = np.array([1 + 0j, 2 - 1j], dtype=np.complex128)

    def bad_solver() -> dict[str, object]:
        bad = _solve(q)
        bad[field] = value
        return bad

    physical_calls: list[np.ndarray] = []

    def physical(value: np.ndarray) -> np.ndarray:
        physical_calls.append(value.copy())
        return value.copy()

    result = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=bad_solver,
        physical_action=physical,
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )
    assert result["classification"] == "W11B_B0_SOLVE_FAIL"
    assert result["checks"]["b0_configuration"] is False
    assert physical_calls == []


def test_w11b_pass_writes_two_hash_bound_candidate_vectors_and_failure_writes_none(
    tmp_path: Path,
) -> None:
    q = np.array([1 + 1j, 0 + 0j], dtype=np.complex128)
    passing = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=lambda: _solve(q),
        physical_action=lambda value: value.copy(),
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )
    vectors = passing.pop("_candidate_vectors")
    records = runner._m6b_w11b_write_candidate_vectors(tmp_path, vectors)
    for role, record in records.items():
        path = Path(record["path"])
        assert path.is_file()
        loaded = np.load(path, allow_pickle=False)
        assert record["bytes"] == path.stat().st_size
        assert record["shape"] == list(loaded.shape)
        assert record["dtype"] == str(loaded.dtype)
        assert record["array_sha256"] == runner._m6b_w2_array_sha256(loaded)
        assert record["file_sha256"] == runner._sha256_file(path)
        assert role in {"preimage", "physical_image"}

    failed_dir = tmp_path / "failed"
    failed_dir.mkdir()
    failed = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=lambda: _solve(q, residual=1.0e-7),
        physical_action=lambda value: value.copy(),
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )
    assert failed["classification"] == "W11B_B0_SOLVE_FAIL"
    assert not list(failed_dir.iterdir())


@pytest.mark.parametrize("failure", ("execution", "cache", "lifecycle"))
def test_w11b_pass_is_not_promoted_after_final_failure(
    tmp_path: Path, failure: str
) -> None:
    q = np.array([1 + 1j, 0 + 0j], dtype=np.complex128)
    passing = run_w11b_fixed_200_exact_proxy(
        q,
        q.copy(),
        b0_solve=lambda: _solve(q),
        physical_action=lambda value: value.copy(),
        architecture=_architecture(),
        predicted_live_set_bytes=1_272_714_790,
    )
    vectors = passing.pop("_candidate_vectors")
    core = {
        "classification": "W11B_PASS",
        "checks": {"projection": True, "lifecycle": True},
        "_candidate_vectors": vectors,
    }
    error = "final execution failed" if failure == "execution" else None
    cache_error = "final cache failed" if failure == "cache" else None
    lifecycle_ok = failure != "lifecycle"
    records = runner._m6b_w11b_promote_candidate_vectors(
        tmp_path,
        core,
        error=error,
        jit_cache_final_error=cache_error,
        lifecycle_ok=lifecycle_ok,
    )
    assert records is None
    assert "_candidate_vectors" not in core
    assert not list(tmp_path.iterdir())


def test_w11b_scope_parser_and_lifetime_contract_are_fixed() -> None:
    scope = runner._m6b_w11b_scope()
    prediction = runner._m6b_w11b_predicted_live_set()
    assert scope["schema"] == runner.M6B_W11B_SCHEMA
    assert scope["phase"] == runner.M6B_W11B_PHASE
    assert scope["beta"] == 0.0
    assert scope["b0"].endswith("restart20 max_it200")
    assert scope["target_used_for_construction"] is False
    assert prediction["bytes"] == 1_272_714_790
    assert prediction["gate"] is True
    assert runner._m6b_w11a_scope()["phase"] == "w11a_persistent_residual_one_vector"

    command = runner._parser().parse_args(
        [
            "m6b-w11b-diagnostic",
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
    assert command.command == "m6b-w11b-diagnostic"
    assert not hasattr(command, "max_it")
    source = inspect.getsource(runner._run_m6b_w11a_diagnostic)
    physical_start = source.index("def physical_numpy")
    assert source.index("release_b0()", physical_start) < source.index(
        "ensure_physical_action()", physical_start
    )
    assert '"lifecycle_events"' in source
    promote_pos = source.index("_m6b_w11b_promote_candidate_vectors(")
    assert promote_pos > source.index("source_end = h2b._light_source()")
    assert promote_pos > source.index("lifecycle_ok = action_audit.get")
