"""Tiny contracts for the V8 layer block action."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_layer_block import (
    ExactBlockSchurAction,
    _supernode_factor_matrix_evidence,
    audit_supernode_factor_paths,
    build_fixed_two_layer_supernode_action,
    build_layer_block_operator,
    build_layer_sweep_action,
    relative_matvec_residual,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse


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


def _tiny_singular_matrix() -> PETSc.Mat:
    comm = MPI.COMM_WORLD
    global_rows = 8
    local_rows = global_rows // comm.size
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, global_rows), (local_rows, global_rows)),
        nnz=(2, 2),
        comm=comm,
    )
    matrix.setUp()
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        if row != 0:
            matrix.setValue(row, row, PETSc.ScalarType(2.0 + 0.1j))
    matrix.assemble()
    return matrix


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


def _collect_global_values(vector: PETSc.Vec) -> np.ndarray:
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    pieces = vector.getComm().tompi4py().allgather(local)
    return np.concatenate(pieces)


def _tiny_v9_block_chain() -> tuple[tuple[np.ndarray, ...], ...]:
    diagonal = []
    lower = []
    upper = []
    for index in range(3):
        diagonal.append(
            np.asarray(
                [
                    [3.1 + 0.15j + 0.2 * index, 0.2 - 0.1j],
                    [0.1 + 0.05j, 2.7 + 0.2j + 0.1 * index],
                ],
                dtype=np.complex128,
            )
        )
    for index in range(2):
        lower.append(
            np.asarray(
                [
                    [0.14 + 0.03j, -0.05 + 0.02j],
                    [0.04 - 0.01j, 0.11 + 0.02j],
                ],
                dtype=np.complex128,
            )
            * (1.0 + 0.1 * index)
        )
        upper.append(
            np.asarray(
                [
                    [-0.12 + 0.04j, 0.03 + 0.01j],
                    [0.02 - 0.03j, -0.09 + 0.02j],
                ],
                dtype=np.complex128,
            )
            * (1.0 - 0.08 * index)
        )
    return tuple(diagonal), tuple(lower), tuple(upper)


def _dense_from_block_chain(
    diagonal: tuple[np.ndarray, ...],
    lower: tuple[np.ndarray, ...],
    upper: tuple[np.ndarray, ...],
) -> np.ndarray:
    block_size = diagonal[0].shape[0]
    dense = np.zeros(
        (len(diagonal) * block_size, len(diagonal) * block_size),
        dtype=np.complex128,
    )
    for index, block in enumerate(diagonal):
        rows = slice(index * block_size, (index + 1) * block_size)
        dense[rows, rows] = block
        if index:
            dense[rows, slice((index - 1) * block_size, index * block_size)] = lower[
                index - 1
            ]
        if index + 1 < len(diagonal):
            dense[rows, slice((index + 1) * block_size, (index + 2) * block_size)] = (
                upper[index]
            )
    return dense


def _supernode_reference(dense: np.ndarray, rhs: np.ndarray, method: str) -> np.ndarray:
    layer_size = dense.shape[0] // 6
    groups = ((0, 1), (2, 3), (4, 5))
    indices = [
        np.concatenate(
            [
                np.arange(first * layer_size, (first + 1) * layer_size),
                np.arange(second * layer_size, (second + 1) * layer_size),
            ]
        )
        for first, second in groups
    ]
    blocks = [dense[np.ix_(item, item)] for item in indices]
    rhs_blocks = [rhs[item] for item in indices]
    lower = [dense[np.ix_(indices[index + 1], indices[index])] for index in range(2)]
    upper = [dense[np.ix_(indices[index], indices[index + 1])] for index in range(2)]
    if method == "SN2-J":
        solution = [
            np.linalg.solve(block, value) for block, value in zip(blocks, rhs_blocks)
        ]
    else:
        forward = [np.linalg.solve(blocks[0], rhs_blocks[0])]
        forward.append(
            np.linalg.solve(blocks[1], rhs_blocks[1] - lower[0] @ forward[0])
        )
        forward.append(
            np.linalg.solve(blocks[2], rhs_blocks[2] - lower[1] @ forward[1])
        )
        solution = [None, None, forward[2]]
        solution[1] = forward[1] - np.linalg.solve(blocks[1], upper[1] @ solution[2])
        solution[0] = forward[0] - np.linalg.solve(blocks[0], upper[0] @ solution[1])
    result = np.empty_like(rhs)
    for item, value in zip(indices, solution):
        result[item] = value
    return result


def _put_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _classify_singular_factor_path(
    matrix: PETSc.Mat,
    rhs_values: np.ndarray,
    *,
    factor_only_storage: bool,
) -> tuple[str, float | None]:
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    source.set(0.0)
    _put_values(source, rhs_values)
    target.set(0.0)
    factor = None
    try:
        factor = ResearchExactFactorInverse(
            matrix,
            factor_solver_type="mumps",
            factor_only_storage=factor_only_storage,
        )
        if factor_only_storage:
            factor.release_borrowed_matrix()
        factor.solve(source, target)
        values = _collect_global_values(target)
        applied = matrix.createVecLeft()
        applied.set(0.0)
        matrix.mult(target, applied)
        applied.axpy(PETSc.ScalarType(-1.0), source)
        residual = float(applied.norm()) / max(float(source.norm()), 1.0e-30)
        applied.destroy()
        finite = bool(np.all(np.isfinite(values)))
        if finite and np.isfinite(residual) and residual <= 1.0e-11:
            return "silent_pass", residual
        return "nonfinite_or_residual_failure", residual
    except Exception:
        return "explicit_factor_failure", None
    finally:
        if factor is not None:
            factor.destroy()
        target.destroy()
        source.destroy()


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


@pytest.mark.parametrize("method", ("J1", "F1"))
def test_v9_bare_f_residual_and_full_side_action_contract(method: str) -> None:
    matrix, labels = _tiny_block_tridiagonal()
    dense = np.zeros((24, 24), dtype=np.complex128)
    for row in range(24):
        dense[row, row] = 3.0 + 0.1j
        if row >= 4:
            dense[row, row - 4] = 0.7 + 0.2j
        if row < 20:
            dense[row, row + 4] = -0.4 + 0.3j
    exact_solution = np.asarray(
        [1.0 + 0.25j * (row + 1) for row in range(24)], dtype=np.complex128
    )
    second_solution = np.asarray(
        [2.0 - 0.1j * (row + 1) for row in range(24)], dtype=np.complex128
    )
    rhs_values = dense @ exact_solution
    second_rhs_values = dense @ second_solution
    direct_solution = np.linalg.solve(dense, rhs_values)
    assert (
        np.linalg.norm(direct_solution - exact_solution)
        / np.linalg.norm(exact_solution)
        <= 1.0e-12
    )
    direct_residual = np.linalg.norm(
        rhs_values - dense @ direct_solution
    ) / np.linalg.norm(rhs_values)
    assert direct_residual <= 1.0e-12

    action = build_layer_sweep_action(
        matrix, labels, layer_count=6, method=method, fine_action=matrix.mult
    )
    rhs = matrix.createVecRight()
    second_rhs = matrix.createVecRight()
    combined_rhs = matrix.createVecRight()
    actual = matrix.createVecLeft()
    repeat = matrix.createVecLeft()
    second_actual = matrix.createVecLeft()
    combined_actual = matrix.createVecLeft()
    _put_global_values(rhs, rhs_values)
    _put_global_values(second_rhs, second_rhs_values)
    alpha = PETSc.ScalarType(1.2 - 0.3j)
    beta = PETSc.ScalarType(-0.4 + 0.6j)
    combined_values = alpha * rhs_values + beta * second_rhs_values
    _put_global_values(combined_rhs, combined_values)
    action.apply_checkpoint(method, rhs, actual)
    action.apply_checkpoint(method, rhs, repeat)
    action.apply_checkpoint(method, second_rhs, second_actual)
    action.apply_checkpoint(method, combined_rhs, combined_actual)
    actual_values = _collect_global_values(actual)
    expected_values = _sweep_reference(rhs_values, method)
    assert (
        np.linalg.norm(actual_values - expected_values)
        / np.linalg.norm(expected_values)
        <= 1.0e-12
    )
    dense_residual = np.linalg.norm(
        rhs_values - dense @ actual_values
    ) / np.linalg.norm(rhs_values)
    helper_residual = relative_matvec_residual(matrix, rhs, actual)
    assert abs(helper_residual - dense_residual) <= 1.0e-12
    assert _relative_error(repeat, actual) <= 1.0e-12
    expected_linear = actual.duplicate()
    actual.copy(expected_linear)
    expected_linear.scale(alpha)
    expected_linear.axpy(beta, second_actual)
    assert _relative_error(combined_actual, expected_linear) <= 1.0e-12
    for vector in (
        expected_linear,
        combined_actual,
        second_actual,
        repeat,
        actual,
        combined_rhs,
        second_rhs,
        rhs,
    ):
        vector.destroy()
    action.destroy()
    matrix.destroy()


def test_v9_2_exact_block_schur_tiny_mpi_authority() -> None:
    diagonal, lower, upper = _tiny_v9_block_chain()
    dense = _dense_from_block_chain(diagonal, lower, upper)
    rhs = np.asarray(
        [1.0 + 0.13j * (index + 1) for index in range(dense.shape[0])],
        dtype=np.complex128,
    )
    second_rhs = np.asarray(
        [0.7 - 0.09j * (index + 2) for index in range(dense.shape[0])],
        dtype=np.complex128,
    )
    action = ExactBlockSchurAction(diagonal, lower, upper)
    expected = np.linalg.solve(dense, rhs)
    actual = action.apply(rhs)
    assert np.linalg.norm(actual - expected) / np.linalg.norm(expected) <= 1.0e-12
    assert np.linalg.norm(rhs - dense @ actual) / np.linalg.norm(rhs) <= 1.0e-12
    repeat = action.apply(rhs)
    assert np.linalg.norm(repeat - actual) / np.linalg.norm(actual) <= 1.0e-13
    alpha = 1.2 - 0.4j
    beta = -0.3 + 0.7j
    combination = alpha * rhs + beta * second_rhs
    linear_expected = alpha * action.apply(rhs) + beta * action.apply(second_rhs)
    assert (
        np.linalg.norm(action.apply(combination) - linear_expected)
        / np.linalg.norm(linear_expected)
        <= 1.0e-12
    )
    diagnostics = action.diagnostics
    assert diagnostics["factor_count_ready"] == 3
    assert diagnostics["retained_explicit_diagonal_count"] == 0
    assert diagnostics["full_side_exact_factor_count"] == 0
    assert diagnostics["global_direct_factor_count"] == 0
    gathered = MPI.COMM_WORLD.allgather(actual)
    assert all(np.array_equal(value, actual) for value in gathered)
    action.destroy()
    assert action.diagnostics["factor_count_after_cleanup"] == 0
    assert action.diagnostics["destroy_marker"] == "completed"
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(rhs)


def test_v9_2_fixed_two_layer_supernodes_share_three_petsc_factors() -> None:
    matrix, labels = _tiny_block_tridiagonal()
    dense = np.zeros((24, 24), dtype=np.complex128)
    for row in range(24):
        dense[row, row] = 3.0 + 0.1j
        if row >= 4:
            dense[row, row - 4] = 0.7 + 0.2j
        if row < 20:
            dense[row, row + 4] = -0.4 + 0.3j
    values = np.asarray(
        [1.0 + 0.11j * (index + 1) for index in range(24)],
        dtype=np.complex128,
    )
    second_values = np.asarray(
        [0.8 - 0.07j * (index + 2) for index in range(24)],
        dtype=np.complex128,
    )
    alpha = 1.15 - 0.23j
    beta = -0.4 + 0.52j
    combination_values = alpha * values + beta * second_values
    action = build_fixed_two_layer_supernode_action(matrix, labels)
    factor_refs = tuple(action._factors)
    diagnostics = action.diagnostics
    assert diagnostics["groups"] == [[0, 1], [2, 3], [4, 5]]
    assert diagnostics["factor_count_ready"] == 3
    assert diagnostics["single_factor_set"] is True
    assert diagnostics["factor_set_build_count"] == 1
    assert diagnostics["factor_count"] == 3
    assert diagnostics["supernode_row_coverage_exact"] is True
    assert sum(diagnostics["supernode_rows_global"]) == 24
    assert diagnostics["cross_lower_block_count"] == 2
    assert diagnostics["cross_upper_block_count"] == 2
    assert diagnostics["full_side_exact_factor_count"] == 0
    assert diagnostics["global_direct_factor_count"] == 0
    assert diagnostics["nested_ksp_count"] == 0

    source = matrix.createVecRight()
    second_source = matrix.createVecRight()
    combination = matrix.createVecRight()
    actual = matrix.createVecLeft()
    repeat = matrix.createVecLeft()
    second_actual = matrix.createVecLeft()
    combination_actual = matrix.createVecLeft()
    _put_values(source, values)
    _put_values(second_source, second_values)
    _put_values(combination, combination_values)
    for method in ("SN2-J", "SN2-SGS"):
        action.apply_checkpoint(method, source, actual)
        actual_values = _collect_global_values(actual)
        expected_values = _supernode_reference(dense, values, method)
        assert (
            np.linalg.norm(actual_values - expected_values)
            / np.linalg.norm(expected_values)
            <= 1.0e-12
        )
        action.apply_checkpoint(method, source, repeat)
        assert _relative_error(repeat, actual) <= 1.0e-13
        action.apply_checkpoint(method, second_source, second_actual)
        action.apply_checkpoint(method, combination, combination_actual)
        expected_second = _supernode_reference(dense, second_values, method)
        expected_combination = _supernode_reference(dense, combination_values, method)
        assert (
            np.linalg.norm(_collect_global_values(second_actual) - expected_second)
            / np.linalg.norm(expected_second)
            <= 1.0e-12
        )
        assert (
            np.linalg.norm(
                _collect_global_values(combination_actual) - expected_combination
            )
            / np.linalg.norm(expected_combination)
            <= 1.0e-12
        )
        expected_linear = alpha * expected_values + beta * expected_second
        assert (
            np.linalg.norm(_collect_global_values(combination_actual) - expected_linear)
            / np.linalg.norm(expected_linear)
            <= 1.0e-12
        )
        assert all(
            current is original
            for current, original in zip(action._factors, factor_refs)
        )

    diagnostics = action.diagnostics
    assert diagnostics["method_apply_count"] == {"SN2-J": 4, "SN2-SGS": 4}
    assert diagnostics["method_factor_solve_count"] == {
        "SN2-J": 12,
        "SN2-SGS": 20,
    }
    for vector in (
        combination_actual,
        second_actual,
        repeat,
        actual,
        combination,
        second_source,
        source,
    ):
        vector.destroy()
    action.destroy()
    assert action.diagnostics["factor_count_after_cleanup"] == 0
    assert action.diagnostics["destroy_marker"] == "completed"
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply_checkpoint("SN2-J", source, actual)
    matrix.destroy()


def test_v10_1_factor_only_matches_conventional_lu_and_zero_rhs() -> None:
    matrix, _ = _tiny_block_tridiagonal()
    rhs_values = np.asarray(
        [1.0 + 0.11j * (index + 1) for index in range(24)],
        dtype=np.complex128,
    )
    source = matrix.createVecRight()
    conventional_target = matrix.createVecLeft()
    _put_global_values(source, rhs_values)
    conventional_target.set(0.0)
    ownership = MPI.COMM_WORLD.allgather(
        (source.getOwnershipRange(), conventional_target.getOwnershipRange())
    )
    assert all(source_range == target_range for source_range, target_range in ownership)

    conventional = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=False,
    )
    conventional.solve(source, conventional_target)
    conventional_values = _collect_global_values(conventional_target)
    conventional_residual = relative_matvec_residual(
        matrix, source, conventional_target
    )
    assert np.all(np.isfinite(conventional_values))
    assert conventional_residual <= 1.0e-11
    assert conventional.diagnostics["factor_only_storage"] is False
    assert conventional.diagnostics["ksp_destroyed"] is False
    conventional.destroy()
    assert conventional.diagnostics["factor_destroyed"] is True
    assert conventional.diagnostics["direct_factor_count"] == 0

    factor_source = matrix.createVecRight()
    factor_target = matrix.createVecLeft()
    _put_global_values(factor_source, rhs_values)
    factor_target.set(0.0)
    factor_only = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=True,
    )
    factor_only.release_borrowed_matrix()
    ready = factor_only.diagnostics
    assert ready["factor_only_storage"] is True
    assert ready["ksp_destroyed"] is True
    assert ready["borrowed_matrix_released"] is True
    assert ready["factor_matrix_alive"] is True
    factor_only.solve(factor_source, factor_target)
    factor_values = _collect_global_values(factor_target)
    factor_residual = relative_matvec_residual(matrix, factor_source, factor_target)
    path_error = np.linalg.norm(factor_values - conventional_values) / max(
        np.linalg.norm(conventional_values), 1.0e-30
    )
    assert np.all(np.isfinite(factor_values))
    assert factor_residual <= 1.0e-11
    assert path_error <= 1.0e-11

    zero_source = matrix.createVecRight()
    zero_target = matrix.createVecLeft()
    zero_source.set(0.0)
    zero_target.set(0.0)
    conventional_zero_source = matrix.createVecRight()
    conventional_zero_target = matrix.createVecLeft()
    conventional_zero_source.set(0.0)
    conventional_zero_target.set(0.0)
    conventional_zero = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=False,
    )
    conventional_zero.solve(conventional_zero_source, conventional_zero_target)
    assert np.all(np.isfinite(_collect_global_values(conventional_zero_target)))
    assert float(conventional_zero_target.norm()) <= 1.0e-13
    conventional_zero.destroy()
    factor_only.solve(zero_source, zero_target)
    assert np.all(np.isfinite(_collect_global_values(zero_target)))
    assert float(zero_target.norm()) <= 1.0e-13

    matrix_probe = matrix.createVecLeft()
    matrix_probe.set(0.0)
    matrix.mult(factor_source, matrix_probe)
    assert np.all(np.isfinite(_collect_global_values(matrix_probe)))
    factor_only.destroy()
    after = factor_only.diagnostics
    assert after["factor_matrix_alive"] is False
    assert after["factor_destroyed"] is True
    assert after["exact_factor_count"] == 0
    assert after["global_hybrid_direct_factor_count"] == 0
    assert matrix.getSize() == (24, 24)
    for vector in (
        matrix_probe,
        zero_target,
        zero_source,
        conventional_zero_target,
        conventional_zero_source,
        factor_target,
        factor_source,
        conventional_target,
        source,
    ):
        vector.destroy()
    matrix.destroy()


def test_v10_1_singular_factor_is_explicitly_classified() -> None:
    matrix = _tiny_singular_matrix()
    rhs_values = np.asarray(
        [1.0 + 0.05j * (index + 1) for index in range(8)],
        dtype=np.complex128,
    )
    classifications = {
        factor_only_storage: _classify_singular_factor_path(
            matrix,
            rhs_values,
            factor_only_storage=factor_only_storage,
        )
        for factor_only_storage in (False, True)
    }
    for classification, residual in classifications.values():
        assert classification in {
            "explicit_factor_failure",
            "nonfinite_or_residual_failure",
        }
        assert classification != "silent_pass"
        if residual is not None:
            assert residual > 1.0e-11 or not np.isfinite(residual)
    matrix.destroy()


def test_v10_1_parent_layer_parent_scatter_round_trip() -> None:
    matrix, labels = _tiny_block_tridiagonal()
    operator = build_layer_block_operator(matrix, labels, layer_count=6)
    parent = matrix.createVecRight()
    restored = matrix.createVecLeft()
    values = np.asarray(
        [0.6 - 0.08j * (index + 1) for index in range(24)],
        dtype=np.complex128,
    )
    _put_global_values(parent, values)
    restored.set(0.0)
    for workspace in operator._workspaces:
        workspace.x.set(0.0)
        workspace.scatter.scatter(
            parent,
            workspace.x,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        workspace.scatter.scatter(
            workspace.x,
            restored,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
    restored.assemble()
    assert _relative_error(restored, parent) <= 1.0e-12
    assert operator.diagnostics["row_coverage_exact"] is True
    assert parent.getOwnershipRange() == restored.getOwnershipRange()
    operator.destroy()
    assert operator.diagnostics["destroy_marker"] == "completed"
    restored.destroy()
    parent.destroy()
    matrix.destroy()


def test_v10_factor_forensic_reports_explicit_norms_and_zero_gate() -> None:
    matrix, _ = _tiny_block_tridiagonal()
    rhs_vectors = {}
    try:
        zero = matrix.createVecRight()
        zero.set(0.0)
        rhs_vectors["zero_rhs"] = zero
        nonzero = matrix.createVecRight()
        values = np.asarray(
            [0.4 + 0.03j * (index + 1) for index in range(24)],
            dtype=np.complex128,
        )
        _put_global_values(nonzero, values)
        rhs_vectors["deterministic_random"] = nonzero
        events = []

        def lifecycle(event, detail):
            events.append((event, detail["path"], dict(detail)))

        report = audit_supernode_factor_paths(
            matrix, rhs_vectors, lifecycle_callback=lifecycle
        )
        assert report["path_order"] == [
            "A_conventional_ksp",
            "B_factor_only_detached",
        ]
        for path in report["path_order"]:
            path_report = report["paths"][path]
            assert path_report["path_pass"] is True
            for rhs_report in path_report["reports"]:
                assert {
                    "rhs_norm",
                    "solution_norm",
                    "relative_residual",
                    "norm_amplification",
                } <= rhs_report.keys()
                assert rhs_report["finite"] is True
                if rhs_report["label"] == "zero_rhs":
                    assert rhs_report["solution_norm"] <= 1.0e-13
                    assert rhs_report["gate_pass"] is True
                else:
                    assert rhs_report["rhs_norm"] > 1.0e-30
                    assert np.isfinite(rhs_report["norm_amplification"])
                    assert rhs_report["gate_pass"] is True
        assert [event for event, _path, _detail in events] == [
            "factor_forensic_path_begin",
            "factor_forensic_path_ready",
            "factor_forensic_path_cleanup",
            "factor_forensic_path_begin",
            "factor_forensic_path_ready",
            "factor_forensic_path_cleanup",
        ]
        assert [path for _event, path, _detail in events] == [
            "A_conventional_ksp",
            "A_conventional_ksp",
            "A_conventional_ksp",
            "B_factor_only_detached",
            "B_factor_only_detached",
            "B_factor_only_detached",
        ]
        for event, _path, detail in events:
            if event == "factor_forensic_path_cleanup":
                assert detail["factor_count_after_cleanup"] == 0
                assert detail["co_resident_factor_count"] == 0
    finally:
        for vector in rhs_vectors.values():
            vector.destroy()
        matrix.destroy()


def test_v10_matrix_evidence_handles_empty_local_rank() -> None:
    comm = MPI.COMM_WORLD
    global_rows = 1
    local_rows = 1 if comm.rank == 0 else 0
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, global_rows), (local_rows, global_rows)),
        nnz=(1, 1),
        comm=comm,
    )
    matrix.setUp()
    if local_rows:
        matrix.setValue(0, 0, PETSc.ScalarType(2.0 + 0.1j))
    matrix.assemble()
    try:
        evidence = _supernode_factor_matrix_evidence(matrix)
        assert evidence["ownership_ranges"][0] == [0, 1]
        assert evidence["diagonal_abs_min"] == pytest.approx(abs(2.0 + 0.1j))
        assert evidence["diagonal_abs_max"] == pytest.approx(abs(2.0 + 0.1j))
    finally:
        matrix.destroy()
