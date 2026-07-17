from __future__ import annotations

import unittest

import numpy as np
from petsc4py import PETSc

from src.solvers.local_slab_solver import IluLocalSlabSolver
from src.solvers.neural_local_pc import NeuralLocalSlabSolver
from src.solvers.physical_slab_two_level import DistributedPhysicalSlabSmoother


class _ExactDiagonalModel:
    def __init__(self, operator):
        self.operator_fingerprint = operator.fingerprint
        self.packed_size = 2 * operator.shape[0]
        self.storage_bytes = 0
        self.checkpoint_sha256 = "petsc-adapter-fixture"
        diagonal = np.empty(operator.shape[0], dtype=np.complex128)
        for row in range(operator.shape[0]):
            first, last = operator.indptr[row : row + 2]
            columns = operator.indices[first:last]
            diagonal[row] = operator.values[first:last][columns == row][0]
        self.diagonal = diagonal

    def predict(self, rhs):
        return rhs / self.diagonal


class NeuralSlabPetscAdapterTests(unittest.TestCase):
    def test_owner_compute_neural_adapter_matches_diagonal_inverse(self) -> None:
        size = 8
        diagonal = np.asarray(
            2.0 + 0.1j * np.arange(1, size + 1), dtype=PETSc.ScalarType
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
            fallback = IluLocalSlabSolver(operator.shape[0], fallback_action)
            return NeuralLocalSlabSolver(
                operator,
                _ExactDiagonalModel(operator),
                fallback=fallback,
                residual_ratio_limit=1.0e-12,
            )

        smoother = DistributedPhysicalSlabSmoother(
            matrix,
            (np.arange(size, dtype=PETSc.IntType),),
            ilu_levels=0,
            factor_only_storage=True,
            local_solver_factory=factory,
        )
        source = matrix.createVecRight()
        source_values = 1.0 + 0.2j * np.arange(1, size + 1)
        source.getArray()[:] = source_values[start:end]
        target = matrix.createVecRight()
        smoother.solve(source, target)
        np.testing.assert_allclose(
            target.getArray(readonly=True),
            (source_values / diagonal)[start:end],
            rtol=2.0e-12,
            atol=2.0e-12,
        )
        diagnostics = smoother.diagnostics["local_backend_diagnostics"]
        if diagnostics:
            self.assertEqual(diagnostics[0]["identity"], "neural")
            self.assertEqual(diagnostics[0]["fallback_count"], 0)
        smoother.destroy()
        target.destroy()
        source.destroy()
        matrix.destroy()


if __name__ == "__main__":
    unittest.main()
