from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _local_two_way_multiplane_diagnostic,
)
from benchmarks.run_task036_exact_cauchy_port_audit import (
    _modal_port_matrix,
    _selected_conormal_continuity,
    _stable_unit_and_log10_norm,
    _stable_vdot,
)
from src.solvers.one_cell_discrete_bloch import (
    OneCellTwoPortSchurAction,
    ProjectedTwoPortSchur,
    bloch_residual_metrics,
    compose_projected_two_port_schur,
    scalar_cg_sign_fixture,
)
from src.solvers.hybrid_local_dtn import HybridLocalOneSidedSchurAction
from src.solvers.hybrid_trace_chain import (
    FullFeTraceChainAction,
    PairedEndpointSchurAction,
    solve_block_tridiagonal_recursive,
    solve_block_tridiagonal_recursive_mpi,
)


class Task036OneCellDiscreteBlochAlgebraTests(unittest.TestCase):
    def test_paired_endpoint_mpi8_bulk_and_local_rhs_payload(self) -> None:
        if MPI.COMM_WORLD.size != 8:
            self.skipTest("paired endpoint seam requires MPI8")
        from benchmarks.run_task036_transfer_optimal_port_capacity import (
            _build_d2_mpi_endpoint_rhs,
        )

        class FakeTransfer:
            source_size = target_size = 2

            def primal(self, values: np.ndarray) -> np.ndarray:
                return np.asarray(values, dtype=np.complex128).copy()

            def dual(self, values: np.ndarray) -> np.ndarray:
                return 3.0 * np.asarray(values, dtype=np.complex128)

        class FakeAction:
            def __init__(self, matrix: np.ndarray) -> None:
                self.matrix = matrix
                self.apply_count = 0
                self.condense_count = 0
                self.destroy_count = 0

            def apply_trace_columns(self, values: np.ndarray) -> np.ndarray:
                self.apply_count += 1
                return self.matrix @ values

            @staticmethod
            def _replicated_values(vector: object) -> np.ndarray:
                return np.asarray(vector.values, dtype=np.complex128).copy()

            def condense_rhs_columns(self, values: np.ndarray) -> np.ndarray:
                self.condense_count += 1
                return 2.0 * np.asarray(values, dtype=np.complex128)

            def destroy(self) -> None:
                self.destroy_count += 1

        class FakeVec:
            def __init__(self, values: np.ndarray) -> None:
                self.values = values

        class FakeSystem:
            def __init__(self, values: np.ndarray) -> None:
                self.b = FakeVec(values)

        rank = MPI.COMM_WORLD.rank
        bottom_matrix = np.asarray([[1.0 + 0.2j, 0.1], [0.0, 0.8 - 0.1j]])
        top_matrix = np.asarray([[0.7 - 0.1j, 0.0], [0.2, 1.1 + 0.3j]])
        bottom_action = FakeAction(bottom_matrix) if rank < 4 else None
        top_action = FakeAction(top_matrix) if rank >= 4 else None
        bottom_transfer = FakeTransfer() if rank < 4 else None
        top_transfer = FakeTransfer() if rank >= 4 else None
        paired = PairedEndpointSchurAction(
            bottom_action,
            bottom_transfer,
            0,
            top_action,
            top_transfer,
            4,
        )
        columns = np.asarray(
            [[1.0 + 0.4j, -0.2j, 0.3], [0.5 - 0.1j, 0.7, -0.4j]],
            dtype=np.complex128,
        )
        bottom, top = paired.apply_pair(columns, columns)
        np.testing.assert_allclose(
            bottom, 3.0 * bottom_matrix @ columns, rtol=1e-12, atol=1e-12
        )
        np.testing.assert_allclose(
            top, 3.0 * top_matrix @ columns, rtol=1e-12, atol=1e-12
        )
        local_action = bottom_action if rank < 4 else top_action
        self.assertEqual(local_action.apply_count, 1)
        bottom_system = (
            FakeSystem(np.zeros(2, dtype=np.complex128)) if rank < 4 else None
        )
        top_system = (
            FakeSystem(np.asarray([3.0, 4.0], dtype=np.complex128))
            if rank >= 4
            else None
        )
        setup = {
            "endpoint_bundles": {
                "bottom": {
                    "action": bottom_action,
                    "system": bottom_system,
                    "transfer": bottom_transfer,
                },
                "top": {
                    "action": top_action,
                    "system": top_system,
                    "transfer": top_transfer,
                },
            }
        }

        class FakeChain:
            plane_size = 2
            global_size = 22

        actual_rhs, rhs_record, bottom_values, top_values = _build_d2_mpi_endpoint_rhs(
            setup, FakeChain()
        )
        np.testing.assert_allclose(actual_rhs[:2, 0], 0.0, atol=1.0e-12)
        np.testing.assert_allclose(
            actual_rhs[-2:, 0], [18.0, 24.0], rtol=1.0e-12, atol=1.0e-12
        )
        self.assertLessEqual(rhs_record["bottom_b_norm"], 1.0e-12)
        self.assertAlmostEqual(rhs_record["top_b_norm"], 5.0)
        self.assertIsNotNone(bottom_values if rank < 4 else top_values)
        self.assertIsNone(top_values if rank < 4 else bottom_values)
        if rank < 4:
            np.testing.assert_allclose(bottom_values, bottom_system.b.values)
        else:
            np.testing.assert_allclose(top_values, top_system.b.values)
        self.assertEqual(local_action.condense_count, 1)
        paired.destroy()
        self.assertEqual(local_action.destroy_count, 1)

    def test_recursive_block_tridiagonal_direct_solver_matches_numpy(self) -> None:
        rng = np.random.default_rng(36061)
        block_count, block_size, rhs_columns = 4, 3, 2
        diagonal = []
        lower = []
        upper = []
        for index in range(block_count):
            block = rng.normal(size=(block_size, block_size)) + 1j * rng.normal(
                size=(block_size, block_size)
            )
            block += (3.0 + 0.2j * (index + 1)) * np.eye(block_size)
            diagonal.append(block)
            if index < block_count - 1:
                lower.append(rng.normal(size=(block_size, block_size)) + 1j * rng.normal(size=(block_size, block_size)))
                upper.append(rng.normal(size=(block_size, block_size)) + 1j * rng.normal(size=(block_size, block_size)))
        rhs = [
            rng.normal(size=(block_size, rhs_columns))
            + 1j * rng.normal(size=(block_size, rhs_columns))
            for _ in range(block_count)
        ]
        full = np.zeros((block_count * block_size, block_count * block_size), dtype=np.complex128)
        for index, block in enumerate(diagonal):
            row = slice(index * block_size, (index + 1) * block_size)
            full[row, row] = block
            if index < block_count - 1:
                next_row = slice((index + 1) * block_size, (index + 2) * block_size)
                full[row, next_row] = upper[index]
                full[next_row, row] = lower[index]
        rhs_full = np.vstack(rhs)
        solution, telemetry = solve_block_tridiagonal_recursive(
            diagonal, lower, upper, rhs
        )
        expected = np.linalg.solve(full, rhs_full)
        np.testing.assert_allclose(solution, expected, rtol=0.0, atol=1.0e-12)
        np.testing.assert_allclose(full @ solution - rhs_full, 0.0, rtol=0.0, atol=1.0e-12)
        self.assertEqual(telemetry, {"block_count": 4, "block_size": 3, "rhs_columns": 2})

    def test_mpi_column_sharded_block_direct_solver_matches_serial(self) -> None:
        rng = np.random.default_rng(36062)
        block_count, block_size, rhs_columns = 4, 8, 3
        diagonal = []
        lower = []
        upper = []
        for index in range(block_count):
            block = rng.normal(size=(block_size, block_size)) + 1j * rng.normal(
                size=(block_size, block_size)
            )
            diagonal.append(block + (5.0 + 0.2j * (index + 1)) * np.eye(block_size))
            if index < block_count - 1:
                lower.append(
                    0.08
                    * (rng.normal(size=(block_size, block_size)) + 1j * rng.normal(size=(block_size, block_size)))
                )
                upper.append(
                    0.07
                    * (rng.normal(size=(block_size, block_size)) + 1j * rng.normal(size=(block_size, block_size)))
                )
        rhs = [
            rng.normal(size=(block_size, rhs_columns))
            + 1j * rng.normal(size=(block_size, rhs_columns))
            for _ in range(block_count)
        ]
        full = np.zeros(
            (block_count * block_size, block_count * block_size),
            dtype=np.complex128,
        )
        for index, block in enumerate(diagonal):
            row = slice(index * block_size, (index + 1) * block_size)
            full[row, row] = block
            if index < block_count - 1:
                next_row = slice((index + 1) * block_size, (index + 2) * block_size)
                full[row, next_row] = upper[index]
                full[next_row, row] = lower[index]
        expected = np.linalg.solve(full, np.vstack(rhs))
        serial, _ = solve_block_tridiagonal_recursive(diagonal, lower, upper, rhs)
        sharded, telemetry = solve_block_tridiagonal_recursive_mpi(
            diagonal, lower, upper, rhs, comm=MPI.COMM_WORLD
        )
        np.testing.assert_allclose(sharded, serial, rtol=0.0, atol=1.0e-12)
        np.testing.assert_allclose(sharded, expected, rtol=0.0, atol=1.0e-12)
        np.testing.assert_allclose(full @ sharded - np.vstack(rhs), 0.0, atol=1.0e-12)
        self.assertEqual(telemetry["column_shards"], MPI.COMM_WORLD.size)
        self.assertEqual(telemetry["columns_per_rank"], block_size // MPI.COMM_WORLD.size)

    def test_two_port_homogeneous_recovery_uses_active_row_permutation(self) -> None:
        def matrix(values: np.ndarray) -> PETSc.Mat:
            rows, cols = values.shape
            indptr = [0]
            indices = []
            data = []
            for row in range(rows):
                nz = np.flatnonzero(values[row])
                indices.extend(nz.tolist())
                data.extend(values[row, nz].tolist())
                indptr.append(len(indices))
            result = PETSc.Mat().createAIJ(
                size=(rows, cols),
                csr=(
                    np.asarray(indptr, dtype=PETSc.IntType),
                    np.asarray(indices, dtype=PETSc.IntType),
                    np.asarray(data, dtype=np.complex128),
                ),
                comm=PETSc.COMM_SELF,
            )
            result.assemble()
            return result

        a_ii = np.asarray(
            [[2.3 - 0.4j, 0.2 + 0.1j], [-0.35 + 0.25j, 1.7 + 0.3j]],
            dtype=np.complex128,
        )
        a_ip = np.asarray(
            [[0.4 + 0.2j, -0.3 + 0.1j], [0.15 - 0.25j, 0.5 + 0.05j]],
            dtype=np.complex128,
        )
        p = np.asarray([[1.0 - 0.2j], [-0.4 + 0.7j]])
        expected_i = -np.linalg.solve(a_ii, a_ip @ p)
        action = OneCellTwoPortSchurAction(
            A_pp=matrix(np.asarray([[1.0 + 0.2j, 0.1], [0.2j, 1.4 - 0.1j]])),
            A_pi=matrix(
                np.asarray(
                    [[0.2, -0.1 + 0.3j], [0.4 - 0.2j, 0.15]],
                    dtype=np.complex128,
                )
            ),
            A_ip=matrix(a_ip),
            A_ii=matrix(a_ii),
            factor=PETSc.KSP().create(PETSc.COMM_SELF),
            left_rows=1,
            right_rows=1,
            interior_rows=2,
            interior_matrix_nnz=int(np.count_nonzero(a_ii)),
            port_active=np.asarray([2, 0], dtype=PETSc.IntType),
            interior_active=np.asarray([3, 1], dtype=PETSc.IntType),
        )
        action.factor.setOperators(action.A_ii)
        action.factor.setType("preonly")
        action.factor.getPC().setType("lu")
        action.factor.setUp()
        try:
            recovered = action.recover_homogeneous_columns(p)
            expected_recovered = np.zeros(4, dtype=np.complex128)
            expected_recovered[action.port_active] = p[:, 0]
            expected_recovered[action.interior_active] = expected_i[:, 0]
            np.testing.assert_allclose(
                recovered[:, 0],
                expected_recovered,
                rtol=0.0,
                atol=1.0e-13,
            )
            np.testing.assert_allclose(
                a_ip @ recovered[action.port_active, 0]
                + a_ii @ recovered[action.interior_active, 0],
                np.zeros(2),
                rtol=0.0,
                atol=1.0e-13,
            )
        finally:
            action.destroy()

    def test_two_port_bulk_columns_use_one_factor_mat_solve(self) -> None:
        def matrix(values: np.ndarray) -> PETSc.Mat:
            rows, cols = values.shape
            indptr = [0]
            indices = []
            data = []
            for row in range(rows):
                nz = np.flatnonzero(values[row])
                indices.extend(nz.tolist())
                data.extend(values[row, nz].tolist())
                indptr.append(len(indices))
            result = PETSc.Mat().createAIJ(
                size=(rows, cols),
                csr=(
                    np.asarray(indptr, dtype=PETSc.IntType),
                    np.asarray(indices, dtype=PETSc.IntType),
                    np.asarray(data, dtype=np.complex128),
                ),
                comm=PETSc.COMM_SELF,
            )
            result.assemble()
            return result

        class CountingFactor:
            def __init__(self, coefficient: np.ndarray) -> None:
                self.coefficient = coefficient
                self.mat_solve_calls = 0
                self.solve_calls = 0

            def matSolve(self, rhs: PETSc.Mat, solution: PETSc.Mat) -> None:
                self.mat_solve_calls += 1
                solution.getDenseArray()[:, :] = np.linalg.solve(
                    self.coefficient, rhs.getDenseArray()
                )
                solution.assemble()

            def solve(self, *_args: object) -> None:
                self.solve_calls += 1
                raise AssertionError("scalar factor.solve must not be used")

            def getConvergedReason(self) -> int:
                return 1

            def destroy(self) -> None:
                return None

        a_pp = np.asarray(
            [[1.0 + 0.2j, 0.1 - 0.3j], [0.2 + 0.4j, 1.4 - 0.1j]],
            dtype=np.complex128,
        )
        a_pi = np.asarray(
            [[0.2 - 0.1j, -0.1 + 0.3j], [0.4 - 0.2j, 0.15 + 0.05j]],
            dtype=np.complex128,
        )
        a_ip = np.asarray(
            [[0.4 + 0.2j, -0.3 + 0.1j], [0.15 - 0.25j, 0.5 + 0.05j]],
            dtype=np.complex128,
        )
        a_ii = np.asarray(
            [[2.3 - 0.4j, 0.2 + 0.1j], [-0.35 + 0.25j, 1.7 + 0.3j]],
            dtype=np.complex128,
        )
        factor = CountingFactor(a_ii)
        action = OneCellTwoPortSchurAction(
            A_pp=matrix(a_pp),
            A_pi=matrix(a_pi),
            A_ip=matrix(a_ip),
            A_ii=matrix(a_ii),
            factor=factor,
            left_rows=1,
            right_rows=1,
            interior_rows=2,
            interior_matrix_nnz=int(np.count_nonzero(a_ii)),
            port_active=np.asarray([0, 1], dtype=PETSc.IntType),
            interior_active=np.asarray([2, 3], dtype=PETSc.IntType),
        )
        try:
            columns = np.asarray(
                [
                    [1.0 - 0.2j, -0.4 + 0.7j, 0.3 + 0.1j],
                    [0.2 + 0.5j, 0.6 - 0.1j, -0.8 + 0.4j],
                ],
                dtype=np.complex128,
            )
            expected = a_pp @ columns - a_pi @ np.linalg.solve(a_ii, a_ip @ columns)
            np.testing.assert_allclose(
                action.apply_columns(columns), expected, rtol=1.0e-12, atol=1.0e-12
            )
            self.assertEqual(factor.mat_solve_calls, 1)
            self.assertEqual(factor.solve_calls, 0)
        finally:
            action.destroy()

        a_hh = np.asarray(
            [[1.2 + 0.1j, -0.2 + 0.3j], [0.15 - 0.25j, 1.7 - 0.2j]],
            dtype=np.complex128,
        )
        a_hc = np.asarray(
            [[0.2 - 0.1j, -0.1 + 0.2j], [0.3 + 0.05j, 0.25 - 0.15j]],
            dtype=np.complex128,
        )
        a_ch = np.asarray(
            [[-0.15 + 0.2j, 0.1 - 0.05j], [0.25 + 0.1j, -0.2 - 0.15j]],
            dtype=np.complex128,
        )
        a_cc = np.asarray(
            [[2.1 + 0.4j, 0.2 - 0.1j], [-0.15 + 0.2j, 1.6 - 0.3j]],
            dtype=np.complex128,
        )
        factor.coefficient = a_cc
        factor.mat_solve_calls = 0
        factor.solve_calls = 0
        action = HybridLocalOneSidedSchurAction(
            A_HH=matrix(a_hh),
            A_Hc=matrix(a_hc),
            A_cH=matrix(a_ch),
            A_cc=matrix(a_cc),
            factor=factor,
            retained_indices=np.asarray([0, 1], dtype=PETSc.IntType),
            complement_indices=np.asarray([2, 3], dtype=PETSc.IntType),
            retained_rows=2,
            complement_rows=2,
            external_auxiliary_rows=0,
            canonical_sign=-1.0 + 0.2j,
        )
        try:
            columns = np.asarray(
                [
                    [0.8 - 0.3j, -0.4 + 0.2j, 0.1 + 0.6j],
                    [0.2 + 0.5j, 0.6 - 0.1j, -0.8 + 0.4j],
                ],
                dtype=np.complex128,
            )
            expected = action.canonical_sign * (
                a_hh @ columns - a_hc @ np.linalg.solve(a_cc, a_ch @ columns)
            )
            np.testing.assert_allclose(
                action.apply_trace_columns(columns),
                expected,
                rtol=1.0e-12,
                atol=1.0e-12,
            )
            self.assertEqual(factor.mat_solve_calls, 1)
            self.assertEqual(factor.solve_calls, 0)
        finally:
            action.destroy()

    def test_full_fe_trace_chain_matches_block_operator(self) -> None:
        class FakeTransfer:
            def __init__(self, matrix: np.ndarray) -> None:
                self.matrix = matrix
                self.source_size, self.target_size = matrix.shape[1], matrix.shape[0]

            def primal(self, values: np.ndarray) -> np.ndarray:
                return self.matrix @ values

            def dual(self, values: np.ndarray) -> np.ndarray:
                return self.matrix.conj().T @ values

        class FakeAction:
            def __init__(
                self,
                matrix: np.ndarray,
                rows: int,
                canonical_sign: complex = 1.0,
            ) -> None:
                self.matrix = matrix
                self.left_rows = rows
                self.right_rows = rows
                self.canonical_sign = canonical_sign
                self.destroy_count = 0

            def apply_columns(self, values: np.ndarray) -> np.ndarray:
                return self.matrix @ values

            def destroy(self) -> None:
                self.destroy_count += 1

        rng = np.random.default_rng(36061)
        p = 2
        cell_matrix = np.asarray(
            [
                [2.0 + 0.1j, 0.2, -0.4j, 0.1],
                [0.3, 1.5 - 0.2j, 0.2, -0.1j],
                [-0.2j, 0.4, 1.2 + 0.3j, 0.25],
                [0.1, -0.3j, 0.15, 1.7 - 0.1j],
            ],
            dtype=np.complex128,
        )
        cell_transfer = FakeTransfer(
            np.asarray([[1.0 + 0.1j, 0.2], [0.3j, 0.8 - 0.1j]])
        )
        bottom_transfer = FakeTransfer(
            np.asarray([[0.9 + 0.2j, -0.1], [0.25, 1.1 - 0.1j]])
        )
        top_transfer = FakeTransfer(
            np.asarray([[1.2 - 0.1j, 0.15], [-0.2j, 0.7 + 0.2j]])
        )
        bottom_matrix = np.asarray(
            [[1.4 + 0.1j, 0.2], [-0.3j, 1.1 - 0.2j]],
            dtype=np.complex128,
        )
        top_matrix = np.asarray(
            [[1.0 - 0.2j, -0.15], [0.25j, 1.3 + 0.1j]],
            dtype=np.complex128,
        )
        cell_action = FakeAction(cell_matrix, p)
        bottom_action = FakeAction(bottom_matrix, p)
        top_action = FakeAction(top_matrix, p)
        chain = FullFeTraceChainAction(
            cell_action,
            cell_transfer,
            bottom_action,
            bottom_transfer,
            top_action,
            top_transfer,
        )
        try:
            explicit_matrix, explicit_record = chain.build_explicit_trace_matrix(
                column_block_size=1,
                comm=PETSc.COMM_SELF,
            )
            try:
                self.assertEqual(explicit_record["rows"], 11 * p)
                self.assertEqual(explicit_record["stored_nnz"], 31 * p * p)
                self.assertIn("aij", explicit_record["matrix_type"].lower())
                self.assertFalse(explicit_record["global_dense_formed"])
                explicit_dense = np.column_stack(
                    [
                        chain.apply_columns(
                            np.eye(11 * p, dtype=np.complex128)[:, column]
                        )[:, 0]
                        for column in range(11 * p)
                    ]
                )
                explicit_probe = (
                    rng.standard_normal((11 * p, 2))
                    + 1j * rng.standard_normal((11 * p, 2))
                )
                def apply_explicit(values: np.ndarray) -> np.ndarray:
                    result = np.empty_like(values)
                    for column in range(values.shape[1]):
                        rhs_vec = explicit_matrix.createVecRight()
                        result_vec = explicit_matrix.createVecLeft()
                        try:
                            rhs_vec.getArray()[:] = values[:, column]
                            rhs_vec.assemble()
                            explicit_matrix.mult(rhs_vec, result_vec)
                            result[:, column] = result_vec.getArray()
                        finally:
                            result_vec.destroy()
                            rhs_vec.destroy()
                    return result

                explicit_rhs = explicit_dense @ explicit_probe
                explicit_result = apply_explicit(explicit_probe)
                np.testing.assert_allclose(
                    explicit_result,
                    explicit_rhs,
                    rtol=0.0,
                    atol=1.0e-11,
                )
                ksp = PETSc.KSP().create(PETSc.COMM_SELF)
                ksp.setOperators(explicit_matrix)
                ksp.setType("preonly")
                ksp.getPC().setType("lu")
                ksp.setUp()
                solved = np.empty_like(explicit_probe)
                try:
                    for column in range(explicit_probe.shape[1]):
                        rhs_vec = explicit_matrix.createVecLeft()
                        solution_vec = explicit_matrix.createVecRight()
                        try:
                            rhs_vec.getArray()[:] = explicit_rhs[:, column]
                            rhs_vec.assemble()
                            ksp.solve(rhs_vec, solution_vec)
                            solved[:, column] = solution_vec.getArray()
                        finally:
                            solution_vec.destroy()
                            rhs_vec.destroy()
                finally:
                    converged_reason = int(ksp.getConvergedReason())
                    ksp.destroy()
                self.assertGreater(converged_reason, 0)
                np.testing.assert_allclose(
                    solved,
                    explicit_probe,
                    rtol=0.0,
                    atol=1.0e-11,
                )
                true_residual = np.linalg.norm(
                    explicit_dense @ solved - explicit_rhs
                ) / max(np.linalg.norm(explicit_rhs), 1.0e-30)
                self.assertLessEqual(true_residual, 1.0e-11)
            finally:
                explicit_matrix.destroy()
            source = rng.standard_normal((11 * p, 3)) + 1j * rng.standard_normal(
                (11 * p, 3)
            )
            expected = np.zeros_like(source).reshape(11, p, 3)
            source_planes = source.reshape(11, p, 3)
            for cell in range(10):
                port_input = np.vstack(
                    (source_planes[cell], cell_transfer.matrix @ source_planes[cell + 1])
                )
                port_output = cell_matrix @ port_input
                expected[cell] += port_output[:p]
                expected[cell + 1] += cell_transfer.matrix.conj().T @ port_output[p:]
            expected[0] += bottom_transfer.matrix.conj().T @ bottom_matrix @ (
                bottom_transfer.matrix @ source_planes[0]
            )
            expected[10] += top_transfer.matrix.conj().T @ top_matrix @ (
                top_transfer.matrix @ source_planes[10]
            )
            expected = expected.reshape(11 * p, 3)
            result = chain.apply_columns(source)
            np.testing.assert_allclose(result, expected, rtol=0.0, atol=1.0e-12)
            compact, compact_record = chain.build_compact_trace_blocks(
                column_block_size=1
            )
            self.assertEqual(compact_record["unique_operator_blocks"], 5)
            compact_dense = np.zeros(
                (11 * p, 11 * p), dtype=np.complex128
            )
            for plane in range(11):
                row = slice(plane * p, (plane + 1) * p)
                diagonal = (
                    compact["bottom_diagonal"]
                    if plane == 0
                    else compact["top_diagonal"]
                    if plane == 10
                    else compact["middle_diagonal"]
                )
                compact_dense[row, row] = diagonal
                if plane < 10:
                    next_row = slice((plane + 1) * p, (plane + 2) * p)
                    compact_dense[row, next_row] = compact["upper"]
                    compact_dense[next_row, row] = compact["lower"]
            np.testing.assert_allclose(
                compact_dense @ source,
                result,
                rtol=0.0,
                atol=1.0e-12,
            )
            compact_solution, compact_solver_record = (
                solve_block_tridiagonal_recursive(
                    (compact["bottom_diagonal"],)
                    + (compact["middle_diagonal"],) * 9
                    + (compact["top_diagonal"],),
                    (compact["lower"],) * 10,
                    (compact["upper"],) * 10,
                    tuple(result.reshape(11, p, 3)),
                )
            )
            np.testing.assert_allclose(
                compact_solution,
                source,
                rtol=0.0,
                atol=1.0e-12,
            )
            self.assertEqual(compact_solver_record["rhs_columns"], 3)
            np.testing.assert_allclose(
                result,
                np.column_stack(
                    [chain.apply_columns(source[:, i])[:, 0] for i in range(3)]
                ),
                rtol=0.0,
                atol=1.0e-12,
            )
            class FakeComm:
                def tompi4py(self) -> "FakeComm":
                    return self

                def allgather(self, packet: object) -> list[object]:
                    return [packet]

            class FakeVec:
                def __init__(self, values: np.ndarray) -> None:
                    self.values = values.copy()
                    self.comm = FakeComm()

                def getOwnershipRange(self) -> tuple[int, int]:
                    return 0, len(self.values)

                def getComm(self) -> FakeComm:
                    return self.comm

                def getArray(self, readonly: bool = False) -> np.ndarray:
                    return self.values

                def getSize(self) -> int:
                    return len(self.values)

                def assemble(self) -> None:
                    return None

            x_vec = FakeVec(source[:, 0])
            y_vec = FakeVec(np.zeros(source.shape[0], dtype=np.complex128))
            chain.mult(None, x_vec, y_vec)
            np.testing.assert_allclose(y_vec.values, result[:, 0], atol=1.0e-12)
            probe = rng.standard_normal(p) + 1j * rng.standard_normal(p)
            dual_probe = rng.standard_normal(p) + 1j * rng.standard_normal(p)
            np.testing.assert_allclose(
                np.vdot(cell_transfer.primal(probe), dual_probe),
                np.vdot(probe, cell_transfer.dual(dual_probe)),
                rtol=0.0,
                atol=1.0e-12,
            )
            wrong_top = FakeAction(-top_matrix, p)
            wrong_cell_action = FakeAction(cell_matrix, p)
            wrong_bottom_action = FakeAction(bottom_matrix, p)
            wrong_chain = FullFeTraceChainAction(
                wrong_cell_action,
                cell_transfer,
                wrong_bottom_action,
                bottom_transfer,
                wrong_top,
                top_transfer,
            )
            try:
                self.assertGreater(
                    np.linalg.norm(wrong_chain.apply_columns(source) - result),
                    1.0e-6,
                )
            finally:
                wrong_chain.destroy()
            bad_top = FakeAction(top_matrix, p, canonical_sign=-1.0)
            with self.assertRaises(ValueError):
                FullFeTraceChainAction(
                    FakeAction(cell_matrix, p),
                    cell_transfer,
                    FakeAction(bottom_matrix, p),
                    bottom_transfer,
                    bad_top,
                    top_transfer,
                )
            np.testing.assert_array_equal(
                chain.apply_columns(np.zeros_like(source)), np.zeros_like(source)
            )
            self.assertEqual(chain.cell_action_instances, 1)
            self.assertFalse(chain.dense_global_formed)
            chain.destroy(object())
            chain.destroy(object())
            chain.destroy()
        finally:
            chain.destroy()
        self.assertEqual(cell_action.destroy_count, 1)
        self.assertEqual(bottom_action.destroy_count, 1)
        self.assertEqual(top_action.destroy_count, 1)

    def test_one_sided_augmented_recovery_matches_complex_schur_algebra(self) -> None:
        def matrix(value: complex) -> PETSc.Mat:
            result = PETSc.Mat().createAIJ(
                size=(1, 1),
                csr=(
                    np.asarray([0, 1], dtype=PETSc.IntType),
                    np.asarray([0], dtype=PETSc.IntType),
                    np.asarray([value], dtype=np.complex128),
                ),
                comm=PETSc.COMM_SELF,
            )
            result.assemble()
            return result

        action = HybridLocalOneSidedSchurAction(
            A_HH=matrix(1.4 + 0.2j),
            A_Hc=matrix(-0.35 + 0.15j),
            A_cH=matrix(0.27 - 0.22j),
            A_cc=matrix(2.1 + 0.4j),
            factor=PETSc.KSP().create(PETSc.COMM_SELF),
            retained_indices=np.asarray([0], dtype=PETSc.IntType),
            complement_indices=np.asarray([1], dtype=PETSc.IntType),
            retained_rows=1,
            complement_rows=1,
            external_auxiliary_rows=0,
            canonical_sign=1.0 + 0.0j,
        )
        action.factor.setOperators(action.A_cc)
        action.factor.setType("preonly")
        action.factor.getPC().setType("lu")
        action.factor.setUp()
        try:
            trace = np.asarray([[0.8 - 0.3j]], dtype=np.complex128)
            rhs = np.asarray([[0.0 + 0.0j], [0.45 + 0.2j]], dtype=np.complex128)
            recovered = action.recover_augmented_columns(trace, rhs)
            expected_complement = (
                rhs[1, 0] - (0.27 - 0.22j) * trace[0, 0]
            ) / (2.1 + 0.4j)
            np.testing.assert_allclose(
                recovered[:, 0],
                np.asarray([trace[0, 0], expected_complement]),
                rtol=0.0,
                atol=1.0e-13,
            )
        finally:
            action.destroy()

    def test_selected_conormal_continuity_uses_side_specific_petrov_maps(self) -> None:
        left_petrov = np.asarray([[2.0], [0.0]], dtype=np.complex128)
        right_petrov = np.asarray([[0.0], [3.0]], dtype=np.complex128)
        left_flux = np.asarray(
            [[1.0, -1.5], [4.0, 2.0]], dtype=np.complex128
        )
        right_flux = np.asarray(
            [[7.0, 8.0], [1.0, 9.0]], dtype=np.complex128
        )
        # At the internal plane, right Petrov sees 3*1 and left Petrov sees
        # 2*(-1.5), even though the raw vectors cannot be added by row index.
        residuals = _selected_conormal_continuity(
            left_flux, right_flux, left_petrov, right_petrov
        )
        self.assertEqual(residuals, [0.0])

    def test_cauchy_audit_scaled_norm_and_pairing_avoid_overflow(self) -> None:
        values = np.asarray((1.0e200 + 2.0e200j, -3.0e200j))
        unit, log10_norm = _stable_unit_and_log10_norm(values)
        self.assertAlmostEqual(np.linalg.norm(unit), 1.0)
        self.assertIsNotNone(log10_norm)
        self.assertTrue(np.isfinite(log10_norm))
        paired = _stable_vdot(
            values,
            np.asarray((2.0e-200 - 1.0e-200j, 4.0e-200j)),
        )
        expected = np.vdot(
            values / 1.0e200,
            np.asarray((2.0 - 1.0j, 4.0j)),
        )
        self.assertAlmostEqual(paired.real, expected.real)
        self.assertAlmostEqual(paired.imag, expected.imag)
        zero_unit, zero_log = _stable_unit_and_log10_norm(
            np.zeros(4, dtype=np.complex128)
        )
        self.assertFalse(np.any(zero_unit))
        self.assertIsNone(zero_log)

    def test_one_cell_modal_port_reconstructs_same_projected_schur(self) -> None:
        count = 3
        diagonal = np.diag(
            np.asarray((2.0 + 0.1j, 2.5 - 0.2j, 3.0 + 0.3j))
        )
        coupling = np.diag(
            np.asarray((-0.4 + 0.05j, -0.3j, -0.2 - 0.1j))
        )
        port = ProjectedTwoPortSchur(
            S_LL=diagonal,
            S_LR=coupling,
            S_RL=coupling,
            S_RR=diagonal,
            port_rows=2 * count,
            interior_rows=0,
            interior_matrix_nnz=0,
        )
        forward = np.asarray((0.8 + 0.1j, 0.7 - 0.2j, 0.6 + 0.05j))
        backward = np.asarray((0.75 - 0.1j, 0.65 + 0.2j, 0.55 - 0.05j))
        negative = np.asarray(
            [
                [1.0, 0.1j, 0.0],
                [0.0, 1.0, -0.05j],
                [0.02, 0.0, 1.0],
            ],
            dtype=np.complex128,
        )
        actual, audit = _modal_port_matrix(
            port,
            negative,
            forward,
            backward,
            1,
        )
        expected = np.block(
            [[port.S_LL, port.S_LR], [port.S_RL, port.S_RR]]
        )
        self.assertLess(
            np.linalg.norm(actual - expected, ord="fro")
            / np.linalg.norm(expected, ord="fro"),
            1.0e-13,
        )
        self.assertLess(audit["boundary_resolver_relative_residual"], 1.0e-13)

    def test_projected_port_star_product_matches_explicit_schur(self) -> None:
        rng = np.random.default_rng(3604)
        count = 4

        def block() -> np.ndarray:
            return (
                rng.standard_normal((count, count))
                + 1j * rng.standard_normal((count, count))
            ) / 20.0

        left = ProjectedTwoPortSchur(
            S_LL=2.0 * np.eye(count) + block(),
            S_LR=block(),
            S_RL=block(),
            S_RR=2.5 * np.eye(count) + block(),
            port_rows=2 * count,
            interior_rows=3,
            interior_matrix_nnz=10,
        )
        right = ProjectedTwoPortSchur(
            S_LL=3.0 * np.eye(count) + block(),
            S_LR=block(),
            S_RL=block(),
            S_RR=3.5 * np.eye(count) + block(),
            port_rows=2 * count,
            interior_rows=5,
            interior_matrix_nnz=12,
        )
        combined, audit = compose_projected_two_port_schur(left, right)

        full = np.block(
            [
                [left.S_LL, left.S_LR, np.zeros((count, count))],
                [left.S_RL, left.S_RR + right.S_LL, right.S_LR],
                [np.zeros((count, count)), right.S_RL, right.S_RR],
            ]
        )
        endpoint = np.r_[np.arange(count), np.arange(2 * count, 3 * count)]
        interior = np.arange(count, 2 * count)
        expected = full[np.ix_(endpoint, endpoint)] - full[
            np.ix_(endpoint, interior)
        ] @ np.linalg.solve(
            full[np.ix_(interior, interior)],
            full[np.ix_(interior, endpoint)],
        )
        actual = np.block(
            [
                [combined.S_LL, combined.S_LR],
                [combined.S_RL, combined.S_RR],
            ]
        )
        self.assertLess(
            np.linalg.norm(actual - expected, ord="fro")
            / np.linalg.norm(expected, ord="fro"),
            1.0e-13,
        )
        self.assertLess(audit["pivot_solve_relative_residual"], 1.0e-13)

    def test_outward_flux_sign_fixture_rejects_wrong_sign(self) -> None:
        audit = scalar_cg_sign_fixture(0.8 + 0.02j)
        self.assertLess(audit["polynomial_relative_residual"], 1.0e-13)
        self.assertLess(
            audit["outward_flux_balance_relative_residual"],
            1.0e-13,
        )
        self.assertGreater(
            audit["wrong_sign_negative_control_relative_residual"],
            1.0e-3,
        )

    def test_projected_polynomial_detects_cross_mode_mixing(self) -> None:
        multipliers = np.asarray(
            [0.81 + 0.04j, 0.72 - 0.03j],
            dtype=np.complex128,
        )
        S_lr = np.asarray(
            [[-1.2 + 0.1j, 0.0], [0.0, -0.9 - 0.06j]],
            dtype=np.complex128,
        )
        S_rl = S_lr.copy()
        S_sum = np.diag(
            [
                -(S_rl[index, index] + multipliers[index] ** 2 * S_lr[index, index])
                / multipliers[index]
                for index in range(2)
            ]
        )
        schur = ProjectedTwoPortSchur(
            S_LL=0.5 * S_sum,
            S_LR=S_lr,
            S_RL=S_rl,
            S_RR=0.5 * S_sum,
            port_rows=4,
            interior_rows=2,
            interior_matrix_nnz=4,
        )
        clean = bloch_residual_metrics(schur, multipliers)
        self.assertLess(clean["forward"]["max_rho"], 1.0e-13)
        self.assertLess(
            clean["forward"]["projected_offdiagonal_ratio"],
            1.0e-13,
        )

        mixed = ProjectedTwoPortSchur(
            S_LL=schur.S_LL.copy(),
            S_LR=schur.S_LR.copy(),
            S_RL=schur.S_RL.copy(),
            S_RR=schur.S_RR.copy(),
            port_rows=4,
            interior_rows=2,
            interior_matrix_nnz=4,
        )
        mixed.S_RL[0, 1] = 2.0e-3 - 1.0e-3j
        failed = bloch_residual_metrics(mixed, multipliers)
        self.assertGreater(
            failed["forward"]["projected_offdiagonal_ratio"],
            1.0e-5,
        )

    def test_multiplane_resolver_handles_nonidentity_negative_trace_map(
        self,
    ) -> None:
        lam = np.asarray([0.83 + 0.11j, 0.76 - 0.08j])
        mu = np.asarray([0.79 - 0.06j, 0.71 + 0.04j])
        coordinates = np.asarray(
            [[1.0 + 0.0j, 0.07 - 0.02j], [-0.03j, 0.94 + 0.01j]]
        )
        a0 = np.asarray([0.4 + 0.1j, -0.2 + 0.05j])
        b_top = np.asarray([-0.1 + 0.2j, 0.15 - 0.08j])
        cells = 4
        planes = np.stack(
            [
                lam**plane * a0
                + coordinates @ (mu ** (cells - plane) * b_top)
                for plane in range(cells + 1)
            ]
        )
        report = _local_two_way_multiplane_diagnostic(
            planes,
            lam,
            mu,
            coordinates,
            groups=[(0, 1)],
            positive_trace_metric=np.eye(2),
        )
        self.assertLess(
            report["forward_cross_cell_trace_metric_relative_l2"],
            1.0e-13,
        )
        self.assertLess(
            report["backward_cross_cell_trace_metric_relative_l2"],
            1.0e-13,
        )
        self.assertLess(report["pair_reconstruction_relative_l2"], 1.0e-13)

        perturbed = planes.copy()
        perturbed[2, 0] += 2.0e-3 - 1.0e-3j
        failed = _local_two_way_multiplane_diagnostic(
            perturbed,
            lam,
            mu,
            coordinates,
            groups=[(0, 1)],
            positive_trace_metric=np.eye(2),
        )
        self.assertGreater(
            failed["forward_cross_cell_trace_metric_relative_l2"],
            1.0e-4,
        )


if __name__ == "__main__":
    unittest.main()
