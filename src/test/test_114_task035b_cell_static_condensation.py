from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    expand_floquet_independent_trace_solution,
    recover_full_solution,
)


def _distributed_matrix(values: np.ndarray) -> PETSc.Mat:
    rows = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=(rows, rows),
        nnz=rows,
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    start, end = matrix.getOwnershipRange()
    owned = np.arange(start, end, dtype=PETSc.IntType)
    if len(owned):
        matrix.setValues(
            owned,
            np.arange(rows, dtype=PETSc.IntType),
            np.asarray(values[start:end], dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix


def _distributed_vector(values: np.ndarray) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(len(values), comm=MPI.COMM_WORLD)
    start, end = vector.getOwnershipRange()
    vector.getArray()[:] = np.asarray(values[start:end], dtype=PETSc.ScalarType)
    return vector


class Task035bCellStaticCondensationTests(unittest.TestCase):
    def setUp(self) -> None:
        comm = MPI.COMM_WORLD
        rows_per_rank = 8
        trace_rows_per_rank = 4
        rows = rows_per_rank * comm.size
        rng = np.random.default_rng(3506)
        values = (
            0.08 * rng.standard_normal((rows, rows))
            + 0.06j * rng.standard_normal((rows, rows))
        )
        # Each rank owns three trace rows followed by one three-row cell
        # interior.  Distinct interiors must not couple to each other.
        interiors = [
            np.arange(
                rank * rows_per_rank + trace_rows_per_rank,
                (rank + 1) * rows_per_rank,
                dtype=np.int64,
            )
            for rank in range(comm.size)
        ]
        all_interior = np.concatenate(interiors)
        for left in interiors:
            for right in interiors:
                if not np.array_equal(left, right):
                    values[np.ix_(left, right)] = 0.0
        values += (rows + 2.0) * np.eye(rows)
        rhs = rng.standard_normal(rows) + 1j * rng.standard_normal(rows)
        self.values = values
        self.rhs_values = rhs
        self.A = _distributed_matrix(values)
        self.b = _distributed_vector(rhs)
        start, _end = self.A.getOwnershipRange()
        rank = start // rows_per_rank
        self.local_cells = (np.asarray(interiors[rank], dtype=PETSc.IntType),)
        self.expected_interior = len(all_interior)

    def tearDown(self) -> None:
        self.b.destroy()
        self.A.destroy()

    def test_explicit_trace_system_and_recovery_match_full_solve(self) -> None:
        condensed = build_explicit_cell_static_condensation(
            self.A,
            self.b,
            self.local_cells,
        )
        ksp = PETSc.KSP().create(MPI.COMM_WORLD)
        ksp.setOperators(condensed.matrix)
        ksp.setType("preonly")
        ksp.getPC().setType("lu")
        if MPI.COMM_WORLD.size > 1:
            ksp.getPC().setFactorSolverType("mumps")
        trace_solution = condensed.rhs.duplicate()
        ksp.solve(condensed.rhs, trace_solution)
        full, recovery = recover_full_solution(
            self.A,
            self.b,
            condensed,
            trace_solution,
        )

        reference = np.linalg.solve(self.values, self.rhs_values)
        start, end = full.getOwnershipRange()
        np.testing.assert_allclose(
            full.getArray(readonly=True),
            reference[start:end],
            rtol=2.0e-12,
            atol=2.0e-12,
        )
        residual = self.b.duplicate()
        self.A.mult(full, residual)
        residual.axpy(PETSc.ScalarType(-1.0), self.b)
        self.assertLess(float(residual.norm() / self.b.norm()), 2.0e-12)
        self.assertEqual(
            condensed.full_rows - condensed.trace_rows,
            self.expected_interior,
        )
        self.assertEqual(
            recovery["recovered_interior_rows"],
            self.expected_interior,
        )
        self.assertFalse(
            condensed.build_audit["all_cell_dense_factor_cache_retained"]
        )

        residual.destroy()
        full.destroy()
        trace_solution.destroy()
        ksp.destroy()
        condensed.destroy()

    def test_exact_embedded_slave_rows_are_physically_removed(self) -> None:
        comm = MPI.COMM_WORLD
        rows_per_rank = 5
        rows = rows_per_rank * comm.size
        values = np.zeros((rows, rows), dtype=np.complex128)
        for row in range(rows):
            values[row, row] = 5.0 + 0.25j
            if row + 1 < rows:
                values[row, row + 1] = -0.3 + 0.1j
                values[row + 1, row] = 0.2 - 0.05j
        slave_rows = np.arange(
            rows_per_rank - 1,
            rows,
            rows_per_rank,
            dtype=np.int64,
        )
        for slave in slave_rows:
            values[slave, :] = 0.0
            values[:, slave] = 0.0
            values[slave, slave] = 1.0
        rhs_values = np.arange(1, rows + 1, dtype=np.float64).astype(
            np.complex128
        )
        rhs_values[slave_rows] = 0.0
        matrix = _distributed_matrix(values)
        rhs = _distributed_vector(rhs_values)
        row_start, _row_end = matrix.getOwnershipRange()
        local_slave = np.asarray(
            [row_start + rows_per_rank - 1],
            dtype=PETSc.IntType,
        )
        identity_map = {index: index for index in range(rows)}
        independent = build_floquet_independent_trace_system(
            matrix,
            rhs,
            owned_slave_original_dofs=local_slave,
            original_to_trace=identity_map,
        )
        ksp = PETSc.KSP().create(comm)
        ksp.setOperators(independent.matrix)
        ksp.setType("preonly")
        ksp.getPC().setType("lu")
        if comm.size > 1:
            ksp.getPC().setFactorSolverType("mumps")
        active_solution = independent.rhs.duplicate()
        ksp.solve(independent.rhs, active_solution)
        expanded = expand_floquet_independent_trace_solution(
            rhs,
            independent,
            active_solution,
        )

        expected = np.linalg.solve(values, rhs_values)
        start, end = expanded.getOwnershipRange()
        np.testing.assert_allclose(
            expanded.getArray(readonly=True),
            expected[start:end],
            rtol=2.0e-12,
            atol=2.0e-12,
        )
        self.assertEqual(independent.removed_slave_rows, comm.size)
        self.assertEqual(independent.active_rows, rows - comm.size)
        self.assertLessEqual(
            independent.build_audit["maximum_slave_off_diagonal"],
            1.0e-12,
        )
        self.assertLessEqual(
            independent.build_audit["maximum_slave_rhs"],
            1.0e-12,
        )

        expanded.destroy()
        active_solution.destroy()
        ksp.destroy()
        independent.destroy()
        rhs.destroy()
        matrix.destroy()


if __name__ == "__main__":
    unittest.main()
