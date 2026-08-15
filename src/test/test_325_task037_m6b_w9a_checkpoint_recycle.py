from __future__ import annotations

from copy import deepcopy
import inspect

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.solvers import checkpoint_recycle as recycle


def _checkpoint_fixture():
    increments = {
        "solution": np.asarray(
            [[1 + 0.2j, 0, 0, 0], [0, 1 - 0.1j, 0, 0], [0, 0, 2 + 0.3j, 0], [0, 0, 0, 1 - 0.4j], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=np.complex128,
        ),
        "action": np.asarray(
            [[1, 0, 0, 0], [0, 1 + 0.1j, 0, 0], [0, 0, 2 - 0.2j, 0], [0, 0, 0, 1 + 0.5j], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=np.complex128,
        ),
    }
    solutions = np.cumsum(increments["solution"], axis=1)
    actions = np.cumsum(increments["action"], axis=1)
    return {
        iteration: {"solution": solutions[:, index], "outer_action": actions[:, index]}
        for index, iteration in enumerate(recycle.CHECKPOINT_ITERATIONS)
    }, increments


def _measurement(role, matrix, residual):
    first = recycle.project_residual(matrix, residual)
    second = recycle.project_residual(matrix, residual)
    repeat = {
        "repeat_exact": np.array_equal(first["singular_values"], second["singular_values"])
        and np.array_equal(first["coefficients"], second["coefficients"])
        and first["rho"] == second["rho"]
        and first["normal_closure"] == second["normal_closure"]
    }
    return runner._m6b_w9a_result(
        first,
        role=role,
        residual_hash="a" * 64,
        repeat=repeat,
    )


def test_w9a_fixed_increments_complex_projection_and_span_closure():
    checkpoints, expected = _checkpoint_fixture()
    built = recycle.build_checkpoint_increments(checkpoints)
    assert built["checkpoint_iterations"] == recycle.CHECKPOINT_ITERATIONS
    assert np.array_equal(built["dX"], expected["solution"])
    assert np.array_equal(built["dAX"], expected["action"])

    coefficients = np.asarray([0.4 - 0.2j, -0.3 + 0.1j, 0.7 + 0.2j, -0.1 - 0.4j])
    result = recycle.project_residual(built["dAX"], built["dAX"] @ coefficients)
    assert result["finite"] is True
    assert result["rank"] == 4
    assert result["normal_closure"] <= 1.0e-11
    assert result["rho"] <= 1.0e-11

    control = _measurement("control_w5_iter200", built["dAX"], np.asarray([0, 0, 0, 0, 1, 0], dtype=np.complex128))
    target = _measurement("target_w7_cumulative400", built["dAX"], built["dAX"] @ coefficients + np.asarray([0, 0, 0, 0, 0.2, 0.1j]))
    gate = runner._m6b_w9a_numeric_gate({control["role"]: control, target["role"]: target})
    assert gate["pass"] is True
    tampered = deepcopy(target)
    tampered["pass"] = True
    tampered["rho"] = 0.95
    assert runner._m6b_w9a_numeric_gate({control["role"]: control, tampered["role"]: tampered})["pass"] is False


def test_w9a_rank_and_contract_fail_closed():
    matrix = np.ones((6, 4), dtype=np.complex128)
    residual = np.ones(6, dtype=np.complex128)
    result = recycle.project_residual(matrix, residual)
    assert result["pass"] is False
    assert result["rank"] < 4
    with pytest.raises(ValueError):
        recycle.build_checkpoint_increments({20: {"solution": residual, "outer_action": residual}})
    source = inspect.getsource(runner._run_m6b_w9a_check)
    assert all(token not in source for token in ("dolfinx", "PETSc", "MPI", "build_m6b_outer_mat"))


def test_w9a_raw_file_array_hash_shape_dtype_and_missing_key_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 2)
    values = np.asarray([1 + 2j, 3 - 4j], dtype=np.complex128)
    path = tmp_path / "m6b_iter200_solution.npy"
    np.save(path, values)
    record = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(values),
    }
    loaded, artifact = runner._m6b_w9a_load_array(tmp_path, record, path.name)
    assert np.array_equal(loaded, values)
    assert artifact["file_sha256"] == record["sha256"]

    bad = dict(record)
    del bad["array_sha256"]
    with pytest.raises((KeyError, ValueError)):
        runner._m6b_w9a_load_array(tmp_path, bad, path.name)
    bad_file_sha = dict(record, sha256="0" * 64)
    with pytest.raises(ValueError):
        runner._m6b_w9a_load_array(tmp_path, bad_file_sha, path.name)

    wrong_shape = np.asarray([1 + 2j], dtype=np.complex128)
    np.save(path, wrong_shape)
    wrong_shape_record = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(wrong_shape),
    }
    with pytest.raises(ValueError):
        runner._m6b_w9a_load_array(tmp_path, wrong_shape_record, path.name)

    nan_values = np.asarray([np.nan + 0j, 2 + 3j], dtype=np.complex128)
    np.save(path, nan_values)
    nan_record = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(nan_values),
    }
    with pytest.raises(ValueError):
        runner._m6b_w9a_load_array(tmp_path, nan_record, path.name)


def test_w9a_parser_fixed_and_no_solver_dispatch(tmp_path):
    args = runner._parser().parse_args(
        [
            "m6b-w9a-check",
            "--w5-raw-dir", str(tmp_path / "w5"),
            "--w5-compact", str(tmp_path / "w5.json"),
            "--w7-raw-dir", str(tmp_path / "w7"),
            "--w7-compact", str(tmp_path / "w7.json"),
            "--output", str(tmp_path / "out.json"),
            "--expected-source-sha", "a" * 40,
        ]
    )
    assert args.command == "m6b-w9a-check"
    assert args.expected_source_sha == "a" * 40
    assert runner.M6B_W9A_TARGET_RHO_LIMIT == 0.90
