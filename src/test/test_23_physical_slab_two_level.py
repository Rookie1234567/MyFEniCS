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
    gather_global_subdomain_indices,
)


class _IdentitySmoother:
    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)


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
        cached.destroy()
        invalid = coarse.copy()
        invalid[0, 0] += 0.1
        with self.assertRaisesRegex(RuntimeError, "true-action certification"):
            SparseGalerkinTwoLevelPc(
                matrix, _IdentitySmoother(), basis, coarse_matrix=invalid
            )
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
