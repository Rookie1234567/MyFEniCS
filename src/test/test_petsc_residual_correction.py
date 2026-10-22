from __future__ import annotations

from unittest.mock import patch

import numpy as np
from petsc4py import PETSc

from src.solvers import petsc_residual_correction
from src.solvers.petsc_residual_correction import (
    single_petsc_residual_correction,
    single_petsc_residual_correction_in_place,
)


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


def test_in_place_residual_correction_updates_same_solution_only_after_improvement():
    comm = PETSc.COMM_SELF
    matrix_values = np.asarray(
        [[3.0 + 0.2j, 0.5 - 0.1j], [0.25j, 2.0 - 0.3j]],
        dtype=np.complex128,
    )
    exact = np.asarray([1.25 - 0.75j, -0.5 + 0.25j], dtype=np.complex128)
    rhs_values = matrix_values @ exact
    initial = exact + np.asarray([2.0e-5 - 1.0e-5j, -1.0e-5 + 0.5e-5j])
    matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=2, comm=comm)
    for row in range(2):
        for column in range(2):
            matrix.setValue(row, column, PETSc.ScalarType(matrix_values[row, column]))
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.setValues(np.arange(2, dtype=PETSc.IntType), rhs_values)
    rhs.assemble()
    solution = rhs.duplicate()
    solution.setValues(np.arange(2, dtype=PETSc.IntType), initial)
    solution.assemble()
    ksp = PETSc.KSP().create(comm=comm)
    ksp.setOperators(matrix)
    ksp.setType(PETSc.KSP.Type.PREONLY)
    ksp.getPC().setType(PETSc.PC.Type.LU)
    ksp.setUp()
    original_solve = rhs.duplicate()
    ksp.solve(rhs, original_solve)
    original_solve.destroy()
    solution_before = solution.getArray(readonly=True).copy()
    solution_identity = id(solution)
    try:
        report = single_petsc_residual_correction_in_place(
            matrix, rhs, solution, ksp, enabled=True
        )
        assert report["status"] == "passed"
        assert report["solution_updated"] is True
        assert report["original_primal_ksp"]["converged_reason"] > 0
        assert report["correction_ksp"]["converged_reason"] > 0
        assert report["initial_condensed_relative_to_rhs"] > 0.0
        assert report["corrected_condensed_relative_to_rhs"] < report[
            "initial_condensed_relative_to_rhs"
        ]
        assert id(solution) == solution_identity
        assert not np.array_equal(solution.getArray(readonly=True), solution_before)
        residual = rhs.duplicate()
        try:
            matrix.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            assert residual.norm() <= report["corrected_condensed_residual_norm"] * 1.01
        finally:
            residual.destroy()
        np.testing.assert_allclose(
            solution.getArray(readonly=True), exact, rtol=2.0e-13, atol=2.0e-13
        )
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
def test_disabled_residual_correction_is_a_petsc_free_no_op():
    report = single_petsc_residual_correction_in_place(
        None, None, None, None, enabled=False
    )
    assert report == {
        "requested": False,
        "status": "not_requested",
        "ordinary_default_changed": False,
    }


def test_non_improving_or_nonfinite_correction_does_not_mutate_solution():
    comm = PETSc.COMM_SELF
    matrix = PETSc.Mat().createAIJ(size=(1, 1), nnz=1, comm=comm)
    matrix.setValue(0, 0, PETSc.ScalarType(2.0))
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.setValue(0, PETSc.ScalarType(1.0))
    rhs.assemble()
    solution = rhs.duplicate()
    solution.setValue(0, PETSc.ScalarType(0.25))
    solution.assemble()
    ksp = PETSc.KSP().create(comm=comm)
    ksp.setOperators(matrix)
    ksp.setType(PETSc.KSP.Type.PREONLY)
    ksp.getPC().setType(PETSc.PC.Type.LU)
    ksp.setUp()
    before = solution.getArray(readonly=True).copy()

    def correction_report(corrected_relative):
        def no_improvement(*args):
            corrected = args[2].copy()
            return corrected, {
                "initial_relative_to_rhs": 0.5,
                "corrected_relative_to_rhs": corrected_relative,
                "initial_explicit_residual_norm": 1.0,
                "corrected_explicit_residual_norm": 1.0,
                "rhs_norm": 2.0,
                "correction_norm": 0.0,
                "relative_correction_norm": 0.0,
                "ksp_converged_reason": 1,
                "ksp_iterations": 1,
            }

        return no_improvement

    try:
        for corrected_relative, failure_fragment in (
            (0.5, "did not strictly improve"),
            (float("nan"), "non-finite"),
        ):
            with patch.object(
                petsc_residual_correction,
                "single_petsc_residual_correction",
                side_effect=correction_report(corrected_relative),
            ):
                report = single_petsc_residual_correction_in_place(
                    matrix, rhs, solution, ksp, enabled=True
                )
            assert report["status"] == "failed"
            assert report["solution_updated"] is False
            assert failure_fragment in report["failure_reason"]
            np.testing.assert_array_equal(solution.getArray(readonly=True), before)
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
