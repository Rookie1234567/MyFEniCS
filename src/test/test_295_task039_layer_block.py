"""Tiny contracts for the V8 layer block action."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_layer_block import build_layer_block_operator


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
