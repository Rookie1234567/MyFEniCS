from __future__ import annotations

import unittest

import numpy as np
from petsc4py import PETSc

from src.solvers.local_slab_solver import LocalBackendPlan
from src.solvers.lu_teacher_local_solver import SparseLuTeacherLocalSolver
from src.solvers.physical_slab_two_level import DistributedPhysicalSlabSmoother


class ExactLuOraclePetscAdapterTests(unittest.TestCase):
    def test_owner_compute_exact_lu_matches_true_diagonal_inverse(self) -> None:
        size = 10
        diagonal = np.asarray(
            2.5 + 0.07j * np.arange(1, size + 1), dtype=PETSc.ScalarType
        )
        matrix = PETSc.Mat().createAIJ(
            size=(size, size), nnz=1, comm=PETSc.COMM_WORLD
        )
        matrix.setUp()
        start, end = matrix.getOwnershipRange()
        for row in range(start, end):
            matrix.setValue(row, row, diagonal[row])
        matrix.assemble()

        def factory(_subdomain, operator, fallback_action):
            self.assertIsNone(fallback_action)
            return SparseLuTeacherLocalSolver(operator)

        def plan(_subdomain):
            return LocalBackendPlan(
                identity="sparse_lu_teacher",
                requires_ilu_factor=False,
                requires_portable_operator=True,
                allows_fallback=False,
            )

        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            (np.arange(size, dtype=PETSc.IntType),),
            ilu_levels=0,
            factor_only_storage=True,
            local_solver_factory=factory,
            local_backend_plan_resolver=plan,
        )
        source = matrix.createVecRight()
        source_values = 1.0 + 0.13j * np.arange(1, size + 1)
        source.getArray()[:] = source_values[start:end]
        target = matrix.createVecRight()
        smoother.solve(source, target)
        np.testing.assert_allclose(
            target.getArray(readonly=True),
            (source_values / diagonal)[start:end],
            rtol=2.0e-12,
            atol=2.0e-12,
        )
        diagnostics = smoother.diagnostics
        self.assertEqual(diagnostics["exact_backend_count"], 1)
        self.assertEqual(diagnostics["ilu_factor_constructed_count"], 0)
        self.assertEqual(diagnostics["global_stored_factor_nnz"], 0)
        self.assertEqual(diagnostics["global_ilu_apply_count"], 0)
        self.assertEqual(diagnostics["hidden_fallback_count"], 0)
        backend = diagnostics["global_backend_diagnostics"][0]
        self.assertEqual(backend["identity"], "sparse_lu_teacher")
        self.assertEqual(backend["solve_count"], 1)
        smoother.destroy()
        self.assertTrue(all(row["destroyed"] for row in smoother.destroy_diagnostics))
        smoother.destroy()
        target.destroy()
        source.destroy()
        matrix.destroy()


if __name__ == "__main__":
    unittest.main()
