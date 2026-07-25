from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseCoarseVector,
    SparseGalerkinTwoLevelPc,
    balanced_subdomain_owners,
    certify_fixed_linear_preconditioner,
    gather_global_subdomain_indices,
)


class _IdentitySmoother:
    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)


class _SolveAdapter:
    def __init__(self, smoother: DistributedPhysicalSlabSmoother) -> None:
        self.smoother = smoother

    def apply(self, _pc, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.smoother.solve(source, target)


def _distributed_matrix(values: np.ndarray) -> PETSc.Mat:
    size = values.shape[0]
    matrix = PETSc.Mat().createAIJ(size=(size, size), nnz=size, comm=PETSc.COMM_WORLD)
    matrix.setUp()
    start, end = matrix.getOwnershipRange()
    for row in range(start, end):
        columns = np.flatnonzero(values[row]).astype(PETSc.IntType)
        matrix.setValues(row, columns, values[row, columns])
    matrix.assemble()
    return matrix


class PhysicalSlabTwoLevelTests(unittest.TestCase):
    @staticmethod
    def _two_step_fixture():
        size = 8
        diagonal = (2.0 + 0.1j * np.arange(1, size + 1)).astype(np.complex128)
        matrix = _distributed_matrix(np.diag(diagonal))
        subdomains = (
            np.arange(0, 5, dtype=PETSc.IntType),
            np.arange(3, 8, dtype=PETSc.IntType),
        )
        source_values = 1.0 + 0.2j * np.arange(1, size + 1)
        source = matrix.createVecRight()
        start, end = source.getOwnershipRange()
        source.getArray()[:] = source_values[start:end]
        return matrix, subdomains, source, source_values, diagonal

    def test_global_subdomain_gather_and_owner_balance(self) -> None:
        rank = MPI.COMM_WORLD.rank
        local = (
            np.asarray([rank], dtype=PETSc.IntType),
            np.asarray([rank + 10], dtype=PETSc.IntType),
        )
        complete = gather_global_subdomain_indices(local)
        np.testing.assert_array_equal(
            complete[0], np.arange(MPI.COMM_WORLD.size, dtype=PETSc.IntType)
        )
        np.testing.assert_array_equal(
            complete[1],
            np.arange(10, 10 + MPI.COMM_WORLD.size, dtype=PETSc.IntType),
        )
        owners = balanced_subdomain_owners(complete, MPI.COMM_WORLD.size)
        self.assertEqual(len(owners), 2)
        self.assertTrue(all(0 <= owner < MPI.COMM_WORLD.size for owner in owners))

    def test_owner_computes_action_and_empty_owner(self) -> None:
        size = 8
        values = np.diag(4.0 + 0.05j * np.arange(1, size + 1)).astype(np.complex128)
        values += np.diag(-0.5 * np.ones(size - 1), 1)
        values += np.diag(-0.5 * np.ones(size - 1), -1)
        matrix = _distributed_matrix(values)
        subdomains = (
            np.arange(0, 5, dtype=PETSc.IntType),
            np.arange(3, 8, dtype=PETSc.IntType),
        )
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            local_ksp_iterations=2,
            local_ksp_type="richardson",
            assembly_order="two_color",
        )
        source = matrix.createVecRight()
        start, end = source.getOwnershipRange()
        source_values = 1.0 + 0.1j * np.arange(1, size + 1)
        source.getArray()[:] = source_values[start:end]
        target = matrix.createVecRight()
        smoother.solve(source, target)
        expected = np.zeros(size, dtype=np.complex128)
        for indices in subdomains:
            expected[indices] += np.linalg.solve(
                values[np.ix_(indices, indices)], source_values[indices]
            )
        np.testing.assert_allclose(
            target.getArray(readonly=True), expected[start:end], rtol=2e-12, atol=2e-12
        )
        if MPI.COMM_WORLD.size > len(subdomains):
            self.assertEqual(smoother.diagnostics["minimum_owner_rows"], 0)
        target.destroy()
        source.destroy()
        smoother.destroy()
        matrix.destroy()

    def test_fixed_coarse_cache_is_true_action_certified(self) -> None:
        size = 8
        values = np.diag(2.0 + 0.1j * np.arange(1, size + 1)).astype(np.complex128)
        matrix = _distributed_matrix(values)
        start, end = matrix.getOwnershipRange()
        owned = np.arange(start, end, dtype=PETSc.IntType)
        basis = []
        for parity in (0, 1):
            indices = owned[owned % 2 == parity]
            basis.append(
                SparseCoarseVector(
                    indices=indices,
                    values=np.full(indices.size, 0.5, dtype=PETSc.ScalarType),
                    slab=parity,
                    eigenvalue=1.0,
                    eigenpair_residual=0.0,
                )
            )
        reference = SparseGalerkinTwoLevelPc(matrix, _IdentitySmoother(), basis)
        coarse = reference.coarse_matrix
        reference.destroy()
        cached = SparseGalerkinTwoLevelPc(
            matrix, _IdentitySmoother(), basis, coarse_matrix=coarse
        )
        self.assertEqual(cached.coarse_rank, 2)
        self.assertLess(cached.coarse_action_relative_error, 1e-13)
        template = matrix.createVecRight()
        certificate = certify_fixed_linear_preconditioner(cached, template)
        self.assertLess(certificate["linearity_relative_error"], 1e-11)
        self.assertLess(certificate["determinism_relative_error"], 1e-13)
        self.assertEqual(certificate["global_size"], size)
        template.destroy()
        cached.destroy()
        invalid = coarse.copy()
        invalid[0, 0] += 0.1
        with self.assertRaisesRegex(RuntimeError, "true-action certification"):
            SparseGalerkinTwoLevelPc(
                matrix, _IdentitySmoother(), basis, coarse_matrix=invalid
            )
        matrix.destroy()

    def test_complex_two_level_action_matches_exact_dense_formula(self) -> None:
        """Protect the single Galerkin correction and complex-adjoint algebra."""

        size = 6
        values = np.diag(
            2.5 + 0.2j * np.arange(1, size + 1)
        ).astype(np.complex128)
        values += np.diag(
            np.asarray(
                [-0.4 + 0.1j, 0.2 - 0.3j, -0.1j, 0.35, -0.25 + 0.05j],
                dtype=np.complex128,
            ),
            1,
        )
        values += np.diag(
            np.asarray(
                [0.1 - 0.2j, -0.15, 0.3 + 0.1j, -0.2j, 0.4 - 0.1j],
                dtype=np.complex128,
            ),
            -1,
        )
        dense_basis = np.asarray(
            [
                [1.0, 0.2j],
                [0.3 + 0.1j, -0.4],
                [-0.2j, 0.6 + 0.1j],
                [0.5, -0.3j],
                [-0.25 + 0.2j, 0.45],
                [0.1j, -0.2 + 0.3j],
            ],
            dtype=np.complex128,
        )
        source_values = np.asarray(
            [
                0.4 + 0.1j,
                -0.2 + 0.7j,
                0.8 - 0.3j,
                -0.5 - 0.2j,
                0.3 + 0.6j,
                -0.1 + 0.4j,
            ],
            dtype=np.complex128,
        )

        matrix = _distributed_matrix(values)
        start, end = matrix.getOwnershipRange()
        owned = np.arange(start, end, dtype=PETSc.IntType)
        basis = tuple(
            SparseCoarseVector(
                indices=owned.copy(),
                values=np.asarray(
                    dense_basis[start:end, column],
                    dtype=PETSc.ScalarType,
                ),
                slab=column,
                eigenvalue=float("nan"),
                eigenpair_residual=0.0,
            )
            for column in range(dense_basis.shape[1])
        )
        two_level = SparseGalerkinTwoLevelPc(
            matrix,
            _IdentitySmoother(),
            basis,
            post_smooth=True,
        )
        source = matrix.createVecRight()
        actual = matrix.createVecLeft()
        source.getArray()[:] = source_values[start:end]
        try:
            two_level.apply(None, source, actual)

            pre_smoothed = source_values.copy()
            residual = source_values - values @ pre_smoothed
            coarse = dense_basis.conj().T @ values @ dense_basis
            coefficients = np.linalg.solve(
                coarse,
                dense_basis.conj().T @ residual,
            )
            corrected = pre_smoothed + dense_basis @ coefficients
            expected = corrected + (source_values - values @ corrected)
            np.testing.assert_allclose(
                actual.getArray(readonly=True),
                expected[start:end],
                rtol=5.0e-13,
                atol=5.0e-13,
            )
        finally:
            actual.destroy()
            source.destroy()
            two_level.destroy()
            matrix.destroy()

    def test_two_step_inner_gmres_matches_explicit_small_reference(self) -> None:
        matrix, subdomains, source, source_values, diagonal = self._two_step_fixture()
        sm1 = DistributedPhysicalSlabSmoother(
            matrix, subdomains, ilu_levels=0, smoother_iterations=1
        )
        sm2 = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            smoother_iterations=2,
            action_operator=matrix,
        )
        one_step = matrix.createVecRight()
        two_step = matrix.createVecRight()
        sm1.solve(source, one_step)
        sm2.solve(source, two_step)
        start, end = source.getOwnershipRange()
        expected = source_values / diagonal
        local_sm1_error = np.linalg.norm(
            one_step.getArray(readonly=True) - expected[start:end]
        )
        global_sm1_error = (
            MPI.COMM_WORLD.allreduce(local_sm1_error**2, op=MPI.SUM) ** 0.5
        )
        self.assertGreater(global_sm1_error, 1.0e-6)
        np.testing.assert_allclose(
            two_step.getArray(readonly=True),
            expected[start:end],
            rtol=2e-12,
            atol=2e-12,
        )
        two_step.destroy()
        one_step.destroy()
        sm2.destroy()
        sm1.destroy()
        source.destroy()
        matrix.destroy()

    def test_exact_factor_fingerprints_detect_only_exact_duplicates(self) -> None:
        size = 8
        values = np.diag(3.0 + 0.1j * np.arange(size)).astype(np.complex128)
        matrix = _distributed_matrix(values)
        duplicate = np.arange(size, dtype=PETSc.IntType)
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            (duplicate, duplicate.copy()),
            ilu_levels=0,
            factor_only_storage=True,
        )
        diagnostics = smoother.diagnostics
        self.assertEqual(len(diagnostics["factor_fingerprints"]), 2)
        self.assertEqual(diagnostics["unique_factor_classes"], 1)
        self.assertEqual(diagnostics["exact_duplicate_factor_count"], 1)
        self.assertEqual(
            diagnostics["factor_fingerprints"][0]["sha256"],
            diagnostics["factor_fingerprints"][1]["sha256"],
        )
        # Detection alone must not create unsafe shared PETSc ownership.
        factor_matrices = [factor.factor_matrix for factor in smoother._factors]
        self.assertEqual(
            MPI.COMM_WORLD.allreduce(len(factor_matrices), op=MPI.SUM), 2
        )
        if len(factor_matrices) == 2:
            self.assertIsNot(factor_matrices[0], factor_matrices[1])
        smoother.destroy()
        matrix.destroy()

    def test_two_step_smoother_repeated_apply_is_stable(self) -> None:
        matrix, subdomains, source, _source_values, _diagonal = self._two_step_fixture()
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            smoother_iterations=2,
            action_operator=matrix,
        )
        first = matrix.createVecRight()
        repeated = matrix.createVecRight()
        smoother.solve(source, first)
        for _ in range(3):
            smoother.solve(source, repeated)
            np.testing.assert_allclose(
                repeated.getArray(readonly=True),
                first.getArray(readonly=True),
                rtol=2e-12,
                atol=2e-12,
            )
        self.assertEqual(smoother.diagnostics["smoother_iterations"], 2)
        repeated.destroy()
        first.destroy()
        smoother.destroy()
        source.destroy()
        matrix.destroy()

    def test_two_step_richardson_action_is_fixed_linear(self) -> None:
        matrix, subdomains, source, _source_values, _diagonal = self._two_step_fixture()
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            smoother_iterations=2,
            smoother_ksp_type="richardson",
            action_operator=matrix,
        )
        certificate = certify_fixed_linear_preconditioner(
            _SolveAdapter(smoother), source
        )
        self.assertLess(certificate["linearity_relative_error"], 1e-11)
        self.assertLess(certificate["determinism_relative_error"], 1e-13)
        self.assertEqual(smoother.diagnostics["smoother_ksp_type"], "richardson")
        smoother.destroy()
        source.destroy()
        matrix.destroy()

    def test_selective_jacobi_slab_is_deterministic_and_reported(self) -> None:
        matrix, subdomains, source, source_values, diagonal = self._two_step_fixture()
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            factor_only_storage=True,
            local_solver_types=("jacobi", "ilu"),
        )
        target = matrix.createVecRight()
        smoother.solve(source, target)
        expected = np.zeros_like(source_values)
        for indices in subdomains:
            expected[indices] += source_values[indices] / diagonal[indices]
        start, end = target.getOwnershipRange()
        np.testing.assert_allclose(
            target.getArray(readonly=True), expected[start:end], rtol=2e-12, atol=2e-12
        )
        diagnostics = smoother.diagnostics
        self.assertEqual(diagnostics["local_solver_type_counts"]["jacobi"], 1)
        self.assertEqual(diagnostics["local_solver_type_counts"]["ilu"], 1)
        smoother.destroy()
        target.destroy()
        source.destroy()
        matrix.destroy()

    def test_subdomain_local_diagonal_shift_matches_explicit_shift(self) -> None:
        matrix, subdomains, source, _source_values, _diagonal = self._two_step_fixture()
        shift = matrix.createVecLeft()
        shift.getArray()[:] = -0.25j
        explicit = matrix.copy()
        explicit_diagonal = explicit.createVecLeft()
        explicit.getDiagonal(explicit_diagonal)
        explicit_diagonal.axpy(PETSc.ScalarType(1.0), shift)
        explicit.setDiagonal(explicit_diagonal)
        explicit.assemble()
        local_shift = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            diagonal_shift=shift,
        )
        explicit_shift = DistributedPhysicalSlabSmoother(
            explicit,
            subdomains,
            ilu_levels=0,
        )
        factor_only = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            diagonal_shift=shift,
            factor_only_storage=True,
        )
        actual = matrix.createVecRight()
        expected = matrix.createVecRight()
        compact = matrix.createVecRight()
        local_shift.solve(source, actual)
        explicit_shift.solve(source, expected)
        factor_only.solve(source, compact)
        np.testing.assert_allclose(
            actual.getArray(readonly=True),
            expected.getArray(readonly=True),
            rtol=2e-12,
            atol=2e-12,
        )
        self.assertTrue(local_shift.diagnostics["subdomain_local_diagonal_shift"])
        np.testing.assert_allclose(
            compact.getArray(readonly=True),
            expected.getArray(readonly=True),
            rtol=2e-12,
            atol=2e-12,
        )
        self.assertTrue(factor_only.diagnostics["factor_only_storage"])
        self.assertGreater(local_shift.diagnostics["global_stored_factor_nnz"], 0)
        self.assertEqual(
            factor_only.diagnostics["global_stored_factor_nnz"],
            local_shift.diagnostics["global_stored_factor_nnz"],
        )
        self.assertTrue(all(factor.matrix is None for factor in factor_only._factors))
        compact.destroy()
        expected.destroy()
        actual.destroy()
        factor_only.destroy()
        explicit_shift.destroy()
        local_shift.destroy()
        explicit_diagonal.destroy()
        explicit.destroy()
        shift.destroy()
        source.destroy()
        matrix.destroy()

    def test_two_step_smoother_mpi_action_consistency(self) -> None:
        matrix, subdomains, source, source_values, diagonal = self._two_step_fixture()
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            smoother_iterations=2,
            action_operator=matrix,
        )
        target = matrix.createVecRight()
        smoother.solve(source, target)
        start, end = target.getOwnershipRange()
        local_error = np.linalg.norm(
            target.getArray(readonly=True) - (source_values / diagonal)[start:end]
        )
        global_error = MPI.COMM_WORLD.allreduce(local_error**2, op=MPI.SUM) ** 0.5
        self.assertLess(global_error, 2.0e-12)
        target.destroy()
        smoother.destroy()
        source.destroy()
        matrix.destroy()

    def test_two_step_smoother_destroy_and_action_requirement(self) -> None:
        matrix, subdomains, source, _source_values, _diagonal = self._two_step_fixture()
        with self.assertRaisesRegex(ValueError, "action operator"):
            DistributedPhysicalSlabSmoother(
                matrix, subdomains, ilu_levels=0, smoother_iterations=2
            )
        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            subdomains,
            ilu_levels=0,
            smoother_iterations=2,
            action_operator=matrix,
        )
        smoother.destroy()
        smoother.destroy()
        self.assertTrue(smoother._destroyed)
        self.assertIsNone(smoother._inner_ksp)
        self.assertIsNone(smoother._inner_pc_context)
        source.destroy()
        matrix.destroy()


if __name__ == "__main__":
    unittest.main()
