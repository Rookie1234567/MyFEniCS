"""Tiny contracts for the V8 layer block action."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_layer_block import (
    build_layer_block_operator,
    build_layer_sweep_action,
)


def _tiny_block_tridiagonal() -> tuple[PETSc.Mat, np.ndarray]:
    comm = MPI.COMM_WORLD
    global_rows = 24
    local_rows = global_rows // comm.size
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, global_rows), (local_rows, global_rows)),
        nnz=(3, 3),
        comm=comm,
    )
    matrix.setUp()
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        layer = row // 4
        matrix.setValue(row, row, PETSc.ScalarType(3.0 + 0.1j))
        if layer:
            matrix.setValue(
                row,
                row - 4,
                PETSc.ScalarType(0.7 + 0.2j),
            )
        if layer < 5:
            matrix.setValue(
                row,
                row + 4,
                PETSc.ScalarType(-0.4 + 0.3j),
            )
    matrix.assemble()
    labels = np.repeat(np.arange(6, dtype=np.int32), 4)
    return matrix, labels


def _relative_error(actual: PETSc.Vec, reference: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), reference)
    denominator = max(float(reference.norm()), 1.0e-30)
    error = float(difference.norm()) / denominator
    difference.destroy()
    return error


def _sweep_reference(values: np.ndarray, method: str) -> np.ndarray:
    diagonal = 3.0 + 0.1j
    lower = 0.7 + 0.2j
    upper = -0.4 + 0.3j
    rows = np.asarray(values, dtype=np.complex128).reshape(6, 4)

    def fb1(rhs: np.ndarray) -> np.ndarray:
        z = np.empty_like(rows)
        y = np.empty_like(rows)
        z[0] = rhs[0]
        y[0] = z[0] / diagonal
        for layer in range(1, 6):
            z[layer] = rhs[layer] - lower * y[layer - 1]
            y[layer] = z[layer] / diagonal
        result = np.empty_like(rows)
        result[5] = z[5] / diagonal
        for layer in range(4, -1, -1):
            result[layer] = (z[layer] - upper * result[layer + 1]) / diagonal
        return result

    if method == "J1":
        result = rows / diagonal
    elif method == "F1":
        result = np.empty_like(rows)
        result[0] = rows[0] / diagonal
        for layer in range(1, 6):
            result[layer] = (rows[layer] - lower * result[layer - 1]) / diagonal
    elif method == "FB1":
        result = fb1(rows)
    else:
        result = np.zeros_like(rows)
        applications = 2 if method == "FB2" else 4
        for _ in range(applications):
            fine = diagonal * result
            fine[1:] += lower * result[:-1]
            fine[:-1] += upper * result[1:]
            result += fb1(rows - fine)
    return result.reshape(-1)


def _put_global_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def test_v8_layer_block_action_tiny_complex_nonhermitian() -> None:
    matrix, labels = _tiny_block_tridiagonal()
    operator = build_layer_block_operator(matrix, labels, layer_count=6)
    source = matrix.createVecRight()
    row_start, row_end = source.getOwnershipRange()
    source.getArray()[:] = np.asarray(
        [1.0 + 0.25j * (row + 1) for row in range(row_start, row_end)],
        dtype=PETSc.ScalarType,
    )
    expected = matrix.createVecLeft()
    actual = matrix.createVecLeft()
    matrix.mult(source, expected)
    operator.apply(source, actual)
    assert _relative_error(actual, expected) <= 1.0e-13
    repeat_actual = matrix.createVecLeft()
    operator.apply(source, repeat_actual)
    assert _relative_error(repeat_actual, actual) <= 1.0e-13
    diagnostics = operator.diagnostics
    assert diagnostics["row_coverage_exact"] is True
    assert diagnostics["nnz_partition"]["partition_exact"] is True
    assert diagnostics["long_range_nnz"] == 0
    assert diagnostics["block_half_bandwidth"] == 1
    assert len(diagnostics["blocks"]) == 16
    assert diagnostics["layer_workspace_count"] == 6
    assert all(
        workspace["global_size"] == 4
        for workspace in diagnostics["layer_workspace_layouts"]
    )
    assert all(
        sum(rank_rows[layer] for rank_rows in diagnostics["per_layer_ownership"]) == 4
        for layer in range(6)
    )
    assert all(
        diagnostics["blocks"][name]["nnz_global"] > 0
        for name in ("D_0", "D_5", "L_1", "L_5", "U_0", "U_4")
    )
    assert all(
        len(diagnostics["blocks"][name]["per_rank"]) == MPI.COMM_WORLD.size
        and diagnostics["blocks"][name]["csr_bytes_global"] > 0
        for name in diagnostics["blocks"]
    )

    second_source = source.duplicate()
    second_source.getArray()[:] = np.asarray(
        [2.0 - 0.1j * (row + 1) for row in range(row_start, row_end)],
        dtype=PETSc.ScalarType,
    )
    alpha = PETSc.ScalarType(1.3 - 0.2j)
    beta = PETSc.ScalarType(-0.4 + 0.7j)
    combination = source.duplicate()
    source.copy(combination)
    combination.scale(alpha)
    combination.axpy(beta, second_source)
    combination_expected = matrix.createVecLeft()
    first_expected = matrix.createVecLeft()
    second_expected = matrix.createVecLeft()
    combination_actual = matrix.createVecLeft()
    matrix.mult(combination, combination_expected)
    matrix.mult(source, first_expected)
    matrix.mult(second_source, second_expected)
    operator.apply(combination, combination_actual)
    assert _relative_error(combination_actual, combination_expected) <= 1.0e-13
    linear_expected = first_expected.duplicate()
    first_expected.copy(linear_expected)
    linear_expected.scale(alpha)
    linear_expected.axpy(beta, second_expected)
    assert _relative_error(combination_actual, linear_expected) <= 1.0e-13

    operator.destroy()
    assert operator.diagnostics["destroy_marker"] == "completed"
    matrix.mult(source, expected)
    with pytest.raises(RuntimeError, match="destroyed"):
        operator.apply(source, actual)
    for vector in (
        linear_expected,
        combination_actual,
        second_expected,
        first_expected,
        combination_expected,
        combination,
        second_source,
        repeat_actual,
        actual,
        expected,
        source,
    ):
        vector.destroy()
    matrix.destroy()


def test_v8_fixed_layer_sweeps_match_frozen_complex_formulas() -> None:
    matrix, labels = _tiny_block_tridiagonal()
    values = np.asarray(
        [1.0 + 0.25j * (row + 1) for row in range(24)], dtype=np.complex128
    )
    second_values = np.asarray(
        [2.0 - 0.1j * (row + 1) for row in range(24)], dtype=np.complex128
    )
    alpha = PETSc.ScalarType(1.3 - 0.2j)
    beta = PETSc.ScalarType(-0.4 + 0.7j)
    action = build_layer_sweep_action(
        matrix,
        labels,
        layer_count=6,
        method="FB1",
        fine_action=matrix.mult,
    )
    assert not hasattr(action, "_matrix")
    assert not hasattr(action, "_operator")
    assert action.factor_only_storage is True
    assert len(action._factors) == 6
    assert len({id(factor) for factor in action._factors}) == 6
    assert action.diagnostics["full_side_exact_factor_count"] == 0
    assert action.diagnostics["global_direct_factor_count"] == 0
    assert action.diagnostics["retained_explicit_diagonal_count"] == 0
    assert action.diagnostics["retained_lower_block_count"] == 5
    assert action.diagnostics["retained_upper_block_count"] == 5
    assert all(
        record["rows_global"] == 4
        and record["nnz_global"] > 0
        and isinstance(record["factor_matrix_stats"], dict)
        and record["factor_only_storage"] is True
        and record["borrowed_matrix_released"] is True
        and record["factor_matrix_alive"] is True
        for record in action.diagnostics["layer_factors"]
    )
    expected_deltas = {
        "J1": (6, 0, 0),
        "F1": (6, 0, 0),
        "FB1": (12, 0, 1),
        "FB2": (24, 1, 2),
        "FB4": (48, 3, 4),
    }
    for method in ("J1", "F1", "FB1", "FB2", "FB4"):
        before = action.diagnostics
        source = matrix.createVecRight()
        second_source = matrix.createVecRight()
        actual = matrix.createVecLeft()
        repeat = matrix.createVecLeft()
        second_actual = matrix.createVecLeft()
        combination = matrix.createVecRight()
        combination_actual = matrix.createVecLeft()
        expected = matrix.createVecLeft()
        second_expected = matrix.createVecLeft()
        combination_expected = matrix.createVecLeft()
        _put_global_values(source, values)
        _put_global_values(second_source, second_values)
        _put_global_values(combination, alpha * values + beta * second_values)
        _put_global_values(expected, _sweep_reference(values, method))
        _put_global_values(second_expected, _sweep_reference(second_values, method))
        _put_global_values(
            combination_expected,
            _sweep_reference(alpha * values + beta * second_values, method),
        )
        action.apply_checkpoint(method, source, actual)
        action.apply_checkpoint(method, source, repeat)
        action.apply_checkpoint(method, second_source, second_actual)
        action.apply_checkpoint(method, combination, combination_actual)
        assert _relative_error(actual, expected) <= 1.0e-12
        assert _relative_error(repeat, actual) <= 1.0e-13
        assert _relative_error(second_actual, second_expected) <= 1.0e-12
        assert _relative_error(combination_actual, combination_expected) <= 1.0e-12
        expected_linear = expected.duplicate()
        expected.copy(expected_linear)
        expected_linear.scale(alpha)
        expected_linear.axpy(beta, second_expected)
        assert _relative_error(combination_actual, expected_linear) <= 1.0e-13
        diagnostics = action.diagnostics
        factor_delta = [
            after - before_value
            for after, before_value in zip(
                diagnostics["layer_solve_count"], before["layer_solve_count"]
            )
        ]
        expected_solves, expected_fine, expected_fb = expected_deltas[method]
        assert sum(factor_delta) == expected_solves * 4
        assert all(value == expected_solves // 6 * 4 for value in factor_delta)
        assert diagnostics["fine_action_count"] - before["fine_action_count"] == (
            expected_fine * 4
        )
        assert diagnostics["fb_sweep_count"] - before["fb_sweep_count"] == (
            expected_fb * 4
        )
        for vector in (
            expected_linear,
            combination_expected,
            second_expected,
            expected,
            combination_actual,
            combination,
            second_actual,
            repeat,
            actual,
            second_source,
            source,
        ):
            vector.destroy()
    frozen_actual = matrix.createVecLeft()
    frozen_solved = matrix.createVecLeft()
    frozen_expected = matrix.createVecLeft()
    frozen_source = matrix.createVecRight()
    _put_global_values(frozen_source, values)
    _put_global_values(frozen_expected, _sweep_reference(values, "FB1"))
    action.apply(frozen_source, frozen_actual)
    assert _relative_error(frozen_actual, frozen_expected) <= 1.0e-12
    action.solve(frozen_source, frozen_solved)
    assert _relative_error(frozen_solved, frozen_actual) <= 1.0e-13
    action.destroy()
    assert action.diagnostics["layer_factor_count"] == 0
    assert action.diagnostics["destroy_marker"] == "completed"
    assert all(
        item["destroy_marker"] == "completed"
        for item in action.diagnostics["layer_factor_lifecycle"]
    )
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(frozen_source, frozen_actual)
    for vector in (frozen_expected, frozen_actual, frozen_solved, frozen_source):
        vector.destroy()
    matrix.destroy()
