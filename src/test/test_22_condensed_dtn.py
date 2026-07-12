from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.condensed_dtn import (
    build_explicit_condensed_operator,
    condense_dense_blocks,
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
    recover_dense_auxiliary,
    recover_petsc_auxiliary,
    relative_action_error,
)


class Task026DenseCondensationTests(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(20260711)
        self.F = rng.standard_normal((7, 7)) + 1j * rng.standard_normal((7, 7))
        self.C = rng.standard_normal((7, 3)) + 1j * rng.standard_normal((7, 3))
        self.D = rng.standard_normal((3, 7)) + 1j * rng.standard_normal((3, 7))
        raw_h = rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3))
        self.H = raw_h + 4.0 * np.eye(3)
        self.b_fe = rng.standard_normal(7) + 1j * rng.standard_normal(7)
        self.b_aux = rng.standard_normal(3) + 1j * rng.standard_normal(3)

    def test_nonidentity_auxiliary_block_matches_augmented_solve(self) -> None:
        augmented = np.block([[self.F, self.C], [self.D, self.H]])
        rhs = np.concatenate([self.b_fe, self.b_aux])
        augmented_solution = np.linalg.solve(augmented, rhs)
        condensed, condensed_rhs = condense_dense_blocks(
            self.F, self.C, self.D, self.H, self.b_fe, self.b_aux
        )
        u_fe = np.linalg.solve(condensed, condensed_rhs)
        u_aux = recover_dense_auxiliary(self.D, self.H, self.b_aux, u_fe)
        np.testing.assert_allclose(
            np.concatenate([u_fe, u_aux]),
            augmented_solution,
            rtol=1.0e-12,
            atol=1.0e-12,
        )

    def test_complex_conjugation_is_not_silently_changed(self) -> None:
        condensed, _rhs = condense_dense_blocks(
            self.F, self.C, self.D, self.H, self.b_fe, self.b_aux
        )
        expected = self.F - self.C @ np.linalg.solve(self.H, self.D)
        wrong_conjugated = self.F - self.C @ np.linalg.solve(self.H, self.D.conjugate())
        np.testing.assert_allclose(condensed, expected, rtol=1.0e-13, atol=1.0e-13)
        self.assertGreater(np.linalg.norm(condensed - wrong_conjugated), 1.0e-3)

    def test_condensed_action_matches_augmented_elimination(self) -> None:
        condensed, _rhs = condense_dense_blocks(
            self.F, self.C, self.D, self.H, self.b_fe, self.b_aux
        )
        rng = np.random.default_rng(26)
        x = rng.standard_normal(7) + 1j * rng.standard_normal(7)
        low_rank_action = self.F @ x - self.C @ np.linalg.solve(self.H, self.D @ x)
        np.testing.assert_allclose(
            condensed @ x, low_rank_action, rtol=1.0e-13, atol=1.0e-13
        )


def _petsc_dense_matrix(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=PETSc.ScalarType)
    rows, cols = values.shape
    matrix = PETSc.Mat().createAIJ(size=(rows, cols), nnz=cols, comm=MPI.COMM_WORLD)
    matrix.setUp()
    start, end = matrix.getOwnershipRange()
    owned_rows = np.arange(start, end, dtype=PETSc.IntType)
    if len(owned_rows):
        matrix.setValues(
            owned_rows, np.arange(cols, dtype=PETSc.IntType), values[start:end, :]
        )
    matrix.assemble()
    return matrix


class Task026PetscCondensationTests(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(2604)
        n_fe = 8
        n_aux = 4
        F = rng.standard_normal((n_fe, n_fe)) + 1j * rng.standard_normal((n_fe, n_fe))
        F += 8.0 * np.eye(n_fe)
        C = rng.standard_normal((n_fe, n_aux)) + 1j * rng.standard_normal((n_fe, n_aux))
        D = rng.standard_normal((n_aux, n_fe)) + 1j * rng.standard_normal((n_aux, n_fe))
        H = np.eye(n_aux, dtype=np.complex128)
        self.augmented_values = np.block([[F, C], [D, H]])
        self.rhs_values = rng.standard_normal(n_fe + n_aux) + 1j * rng.standard_normal(
            n_fe + n_aux
        )
        self.A = _petsc_dense_matrix(self.augmented_values)
        self.b = self.A.createVecRight()
        start, end = self.b.getOwnershipRange()
        self.b.getArray()[:] = self.rhs_values[start:end]
        self.blocks = extract_petsc_condensed_blocks(
            self.A, self.b, n_fe=n_fe, n_aux=n_aux
        )

    def tearDown(self) -> None:
        self.blocks.destroy()
        self.b.destroy()
        self.A.destroy()

    def test_explicit_and_matrix_free_actions_match_in_mpi(self) -> None:
        explicit, port = build_explicit_condensed_operator(self.blocks)
        matrix_free, context = create_matrix_free_condensed_operator(self.blocks)
        x = explicit.createVecRight()
        x.setRandom()
        error = relative_action_error(explicit, matrix_free, x)
        self.assertLess(error, 5.0e-13)
        for _ in range(1000):
            matrix_free.mult(x, self.blocks.b_fe)
        self.assertEqual(context.apply_count, 1001)
        x.destroy()
        matrix_free.destroy()
        port.destroy()
        explicit.destroy()

    def test_matrix_free_transpose_actions_match_explicit(self) -> None:
        explicit, port = build_explicit_condensed_operator(self.blocks)
        matrix_free, context = create_matrix_free_condensed_operator(self.blocks)
        x = explicit.createVecLeft()
        x.setRandom()
        reference = explicit.createVecRight()
        candidate = explicit.createVecRight()

        explicit.multTranspose(x, reference)
        matrix_free.multTranspose(x, candidate)
        candidate.axpy(PETSc.ScalarType(-1.0), reference)
        transpose_error = float(candidate.norm()) / max(
            float(reference.norm()), 1.0e-300
        )

        explicit.multHermitian(x, reference)
        matrix_free.multHermitian(x, candidate)
        candidate.axpy(PETSc.ScalarType(-1.0), reference)
        hermitian_error = float(candidate.norm()) / max(
            float(reference.norm()), 1.0e-300
        )

        self.assertLess(transpose_error, 5.0e-13)
        self.assertLess(hermitian_error, 5.0e-13)
        self.assertEqual(context.transpose_apply_count, 1)
        self.assertEqual(context.hermitian_apply_count, 1)
        candidate.destroy()
        reference.destroy()
        x.destroy()
        matrix_free.destroy()
        port.destroy()
        explicit.destroy()

    def test_petsc_complex_dot_is_conjugated_for_galerkin_products(self) -> None:
        left = self.blocks.F.createVecRight()
        right = self.blocks.F.createVecRight()
        start, end = left.getOwnershipRange()
        indices = np.arange(start, end, dtype=np.float64)
        left_values = (indices + 1.0) + 1j * (2.0 * indices + 0.5)
        right_values = (0.25 * indices - 1.0) + 1j * (indices + 2.0)
        left.getArray()[:] = left_values
        right.getArray()[:] = right_values
        local_expected = np.vdot(left_values, right_values)
        expected = MPI.COMM_WORLD.allreduce(local_expected, op=MPI.SUM)
        actual = np.conjugate(left.dot(right))
        self.assertAlmostEqual(abs(actual - expected), 0.0, places=12)
        right.destroy()
        left.destroy()

    def test_condensed_rhs_and_backsubstitution_match_augmented_solve(self) -> None:
        explicit, port = build_explicit_condensed_operator(self.blocks)
        rhs = condensed_rhs(self.blocks)
        ksp = PETSc.KSP().create(MPI.COMM_WORLD)
        ksp.setOperators(explicit)
        ksp.setType("preonly")
        ksp.getPC().setType("lu")
        if MPI.COMM_WORLD.size > 1:
            ksp.getPC().setFactorSolverType("mumps")
        u_fe = explicit.createVecRight()
        ksp.solve(rhs, u_fe)
        u_aux = recover_petsc_auxiliary(self.blocks, u_fe)

        reference = np.linalg.solve(self.augmented_values, self.rhs_values)
        fe_start, fe_end = u_fe.getOwnershipRange()
        aux_start, aux_end = u_aux.getOwnershipRange()
        np.testing.assert_allclose(
            u_fe.getArray(readonly=True),
            reference[fe_start:fe_end],
            rtol=1.0e-11,
            atol=1.0e-11,
        )
        np.testing.assert_allclose(
            u_aux.getArray(readonly=True),
            reference[self.blocks.n_fe + aux_start : self.blocks.n_fe + aux_end],
            rtol=1.0e-11,
            atol=1.0e-11,
        )
        u_aux.destroy()
        u_fe.destroy()
        ksp.destroy()
        rhs.destroy()
        port.destroy()
        explicit.destroy()


if __name__ == "__main__":
    unittest.main()
