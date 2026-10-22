from __future__ import annotations

import numpy as np
from petsc4py import PETSc

from src.solvers.petsc_residual_correction import single_petsc_residual_correction


def test_single_petsc_residual_correction_reuses_inputs_and_reduces_true_residual():
    comm = PETSc.COMM_SELF
    matrix_values = np.asarray(
        [
            [4.0 + 0.2j, 1.0 - 0.4j, 0.3],
            [0.5j, 3.0 + 0.1j, -0.2 + 0.3j],
            [0.1, 0.7 + 0.2j, 2.5 - 0.3j],
        ],
        dtype=np.complex128,
    )
    exact_solution = np.asarray(
        [1.0 + 2.0j, -0.5 + 0.7j, 0.2 - 1.1j],
        dtype=np.complex128,
    )
    rhs_values = matrix_values @ exact_solution
    initial_values = exact_solution + np.asarray(
        [2.0e-6 - 1.0e-6j, -1.0e-6 + 3.0e-6j, 2.0e-6 + 0.5e-6j],
        dtype=np.complex128,
    )

    matrix = PETSc.Mat().createAIJ(size=(3, 3), nnz=3, comm=comm)
    for row in range(3):
        for column in range(3):
            matrix.setValue(row, column, PETSc.ScalarType(matrix_values[row, column]))
    matrix.assemble()

    rhs = matrix.createVecRight()
    rhs.setValues(np.arange(3, dtype=PETSc.IntType), rhs_values)
    rhs.assemble()
    solution = rhs.duplicate()
    solution.setValues(np.arange(3, dtype=PETSc.IntType), initial_values)
    solution.assemble()
    rhs_before = rhs.getArray(readonly=True).copy()
    solution_before = solution.getArray(readonly=True).copy()

    ksp = PETSc.KSP().create(comm=comm)
    ksp.setOperators(matrix)
    ksp.setType(PETSc.KSP.Type.PREONLY)
    ksp.getPC().setType(PETSc.PC.Type.LU)
    ksp.setUp()
    corrected = None
    try:
        corrected, diagnostics = single_petsc_residual_correction(
            matrix,
            rhs,
            solution,
            ksp,
        )
        assert diagnostics["ksp_converged_reason"] > 0
        assert diagnostics["corrected_relative_to_rhs"] < (
            diagnostics["initial_relative_to_rhs"] * 1.0e-8
        )
        np.testing.assert_array_equal(rhs.getArray(readonly=True), rhs_before)
        np.testing.assert_array_equal(
            solution.getArray(readonly=True), solution_before
        )
        np.testing.assert_allclose(
            corrected.getArray(readonly=True),
            exact_solution,
            rtol=2.0e-13,
            atol=2.0e-13,
        )
        assert diagnostics["matrix_or_rhs_reassembled"] is False
        assert diagnostics["ksp_operator_replaced"] is False
    finally:
        if corrected is not None:
            corrected.destroy()
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
