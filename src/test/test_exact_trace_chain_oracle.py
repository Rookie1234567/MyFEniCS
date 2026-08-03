"""Focused algebraic tests for the research-only exact-trace oracle."""

from __future__ import annotations

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.solvers import hybrid_port_metric, hybrid_trace_chain
from src.solvers.hybrid_port_metric import EndpointTraceMassAction
from src.solvers.hybrid_trace_chain import (
    FullFeTraceChainAction,
    PairedEndpointSchurAction,
    solve_block_tridiagonal_recursive,
    solve_block_tridiagonal_recursive_mpi,
)
from src.solvers.one_cell_trace_schur import (
    RESEARCH_STATUS as ONE_CELL_RESEARCH_STATUS,
    EndpointActiveRows,
    build_one_cell_two_port_schur_action,
    endpoint_cauchy_balance,
    endpoint_cauchy_columns,
)


def _aij(values: np.ndarray) -> PETSc.Mat:
    array = np.asarray(values, dtype=PETSc.ScalarType)
    matrix = PETSc.Mat().createAIJ(
        size=array.shape,
        nnz=array.shape[1],
        comm=PETSc.COMM_SELF,
    )
    matrix.setValues(
        np.arange(array.shape[0], dtype=PETSc.IntType),
        np.arange(array.shape[1], dtype=PETSc.IntType),
        array,
    )
    matrix.assemble()
    return matrix


def _block_matrix(
    diagonal: tuple[np.ndarray, ...],
    lower: tuple[np.ndarray, ...],
    upper: tuple[np.ndarray, ...],
) -> np.ndarray:
    block_count = len(diagonal)
    block_size = diagonal[0].shape[0]
    matrix = np.zeros(
        (block_count * block_size, block_count * block_size),
        dtype=np.complex128,
    )
    for index, block in enumerate(diagonal):
        start = index * block_size
        matrix[start : start + block_size, start : start + block_size] = block
        if index < block_count - 1:
            next_start = start + block_size
            matrix[
                next_start : next_start + block_size,
                start : start + block_size,
            ] = lower[index]
            matrix[
                start : start + block_size,
                next_start : next_start + block_size,
            ] = upper[index]
    return matrix


def test_one_cell_schur_action_matches_explicit_partition() -> None:
    values = np.asarray(
        [
            [4.0 + 0.1j, 0.2, 0.1j, 0.3],
            [0.4, 3.0 + 0.2j, 0.2, 0.1j],
            [0.1j, 0.3, 2.5 - 0.1j, 0.2],
            [0.2, 0.1j, 0.4, 3.2 + 0.1j],
        ],
        dtype=np.complex128,
    )
    rows = EndpointActiveRows(
        left_original=np.asarray([0], dtype=PETSc.IntType),
        right_original=np.asarray([3], dtype=PETSc.IntType),
        left_active=np.asarray([0], dtype=PETSc.IntType),
        right_active=np.asarray([3], dtype=PETSc.IntType),
        interior_active=np.asarray([1, 2], dtype=PETSc.IntType),
        left_original_sha256="left-original",
        right_original_sha256="right-original",
        left_active_sha256="left-active",
        right_active_sha256="right-active",
        interior_active_sha256="interior-active",
    )
    matrix = _aij(values)
    action = build_one_cell_two_port_schur_action(matrix, rows)
    matrix.destroy()
    try:
        port = np.asarray([0, 3])
        interior = np.asarray([1, 2])
        A_pp = values[np.ix_(port, port)]
        A_pi = values[np.ix_(port, interior)]
        A_ip = values[np.ix_(interior, port)]
        A_ii = values[np.ix_(interior, interior)]
        schur = A_pp - A_pi @ np.linalg.solve(A_ii, A_ip)
        columns = np.asarray(
            [[1.0 + 0.2j, -0.3], [0.4j, 1.2 - 0.1j]],
            dtype=np.complex128,
        )
        np.testing.assert_allclose(
            action.apply_columns(columns),
            schur @ columns,
            rtol=2.0e-13,
            atol=2.0e-13,
        )
        np.testing.assert_allclose(
            action.apply_adjoint_columns(columns),
            schur.conj().T @ columns,
            rtol=2.0e-13,
            atol=2.0e-13,
        )

        recovered = action.recover_homogeneous_columns(columns)
        expected_recovered = np.zeros((4, 2), dtype=np.complex128)
        expected_recovered[port] = columns
        expected_recovered[interior] = -np.linalg.solve(A_ii, A_ip @ columns)
        np.testing.assert_allclose(
            recovered,
            expected_recovered,
            rtol=2.0e-13,
            atol=2.0e-13,
        )

        state = np.asarray(
            [[1.0 + 0.1j, 0.4], [0.2, -0.1j], [0.3j, 0.5]],
            dtype=np.complex128,
        )
        adjoint_state = np.asarray(
            [[0.7, 0.2 - 0.1j], [0.1j, 0.3], [0.4, -0.2j]],
            dtype=np.complex128,
        )
        multipliers = np.asarray([0.8 + 0.1j, 0.7 - 0.2j])
        adjoint_multipliers = np.asarray([0.9 - 0.1j, 0.6 + 0.1j])
        electric, traction, adjoint, adjoint_traction = endpoint_cauchy_columns(
            action,
            state,
            adjoint_state,
            multipliers=multipliers,
            adjoint_multipliers=adjoint_multipliers,
        )
        expected_electric = np.vstack((state[:1], state[:1] * multipliers[None, :]))
        expected_adjoint = np.vstack(
            (
                adjoint_state[:1],
                adjoint_state[:1] * adjoint_multipliers[None, :],
            )
        )
        np.testing.assert_allclose(electric, expected_electric)
        np.testing.assert_allclose(adjoint, expected_adjoint)
        np.testing.assert_allclose(
            traction,
            A_pp @ expected_electric + A_pi @ state[1:],
        )
        np.testing.assert_allclose(
            adjoint_traction,
            A_pp.conj().T @ expected_adjoint
            + A_ip.conj().T @ (adjoint_multipliers[None, :] * adjoint_state[1:]),
        )
        balance = endpoint_cauchy_balance(
            action,
            state,
            adjoint_state,
            multipliers=multipliers,
            adjoint_multipliers=adjoint_multipliers,
        )
        assert balance["columns"] == 2
        assert all(np.isfinite(value) for value in balance.values())
        assert rows.to_record()["left_right_disjoint"] is True
        assert action.dense_interface_square_formed is False
    finally:
        action.destroy()
        action.destroy()


def test_block_recursions_match_dense_solve() -> None:
    rng = np.random.default_rng(20260803)
    block_count = 4
    block_size = 8
    diagonal = tuple(
        5.0 * np.eye(block_size)
        + 0.04
        * (
            rng.standard_normal((block_size, block_size))
            + 1.0j * rng.standard_normal((block_size, block_size))
        )
        for _ in range(block_count)
    )
    lower = tuple(
        0.03
        * (
            rng.standard_normal((block_size, block_size))
            + 1.0j * rng.standard_normal((block_size, block_size))
        )
        for _ in range(block_count - 1)
    )
    upper = tuple(
        0.03
        * (
            rng.standard_normal((block_size, block_size))
            + 1.0j * rng.standard_normal((block_size, block_size))
        )
        for _ in range(block_count - 1)
    )
    rhs = tuple(
        rng.standard_normal((block_size, 2))
        + 1.0j * rng.standard_normal((block_size, 2))
        for _ in range(block_count)
    )
    dense = _block_matrix(diagonal, lower, upper)
    expected = np.linalg.solve(dense, np.vstack(rhs))
    serial, serial_record = solve_block_tridiagonal_recursive(
        diagonal, lower, upper, rhs
    )
    distributed, mpi_record = solve_block_tridiagonal_recursive_mpi(
        diagonal, lower, upper, rhs, comm=MPI.COMM_WORLD
    )
    np.testing.assert_allclose(serial, expected, rtol=2.0e-13, atol=2.0e-13)
    np.testing.assert_allclose(distributed, expected, rtol=2.0e-13, atol=2.0e-13)
    assert serial_record["block_count"] == block_count
    assert mpi_record["column_shards"] == MPI.COMM_WORLD.size


class _DenseAction:
    def __init__(
        self,
        matrix: np.ndarray,
        *,
        left_rows: int | None = None,
    ) -> None:
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.destroy_count = 0
        if left_rows is None:
            self.retained_rows = self.matrix.shape[0]
            self.canonical_sign = 1
        else:
            self.left_rows = int(left_rows)
            self.right_rows = int(left_rows)

    def apply_columns(self, values: np.ndarray) -> np.ndarray:
        return self.matrix @ values

    def apply_trace_columns(self, values: np.ndarray) -> np.ndarray:
        return self.matrix @ values

    def destroy(self) -> None:
        self.destroy_count += 1


class _Transfer:
    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.source_size = self.matrix.shape[1]
        self.target_size = self.matrix.shape[0]

    def primal(self, values: np.ndarray) -> np.ndarray:
        return self.matrix @ values

    def dual(self, values: np.ndarray) -> np.ndarray:
        return self.matrix.conj().T @ values


def test_full_fe_chain_compact_blocks_and_recursive_solve() -> None:
    p = 2
    cell_matrix = np.asarray(
        [
            [4.0, 0.1j, 0.2, 0.0],
            [-0.1j, 3.5, 0.0, 0.15],
            [0.3, 0.0, 3.2, 0.05j],
            [0.0, 0.2, -0.05j, 3.8],
        ],
        dtype=np.complex128,
    )
    bottom_matrix = np.asarray([[1.2, 0.1j], [-0.1j, 1.1]])
    top_matrix = np.asarray([[1.4, -0.05j], [0.05j, 1.3]])
    cell_action = _DenseAction(cell_matrix, left_rows=p)
    cell_transfer = _Transfer(np.asarray([[1.0, 0.1], [0.0, 0.9j]]))
    endpoint_transfer = _Transfer(np.eye(p))
    if MPI.COMM_WORLD.size == 2:
        bottom_action = (
            _DenseAction(bottom_matrix) if MPI.COMM_WORLD.rank == 0 else None
        )
        top_action = _DenseAction(top_matrix) if MPI.COMM_WORLD.rank == 1 else None
        bottom_transfer = endpoint_transfer if bottom_action is not None else None
        top_transfer = endpoint_transfer if top_action is not None else None
        bottom_root = 0
        top_root = 1
        pair_world = MPI.COMM_WORLD
    else:
        bottom_action = _DenseAction(bottom_matrix)
        top_action = _DenseAction(top_matrix)
        bottom_transfer = endpoint_transfer
        top_transfer = endpoint_transfer
        bottom_root = top_root = 0
        pair_world = MPI.COMM_SELF
    paired = PairedEndpointSchurAction(
        bottom_action,
        bottom_transfer,
        bottom_root,
        top_action,
        top_transfer,
        top_root,
        world=pair_world,
    )
    chain = FullFeTraceChainAction(
        cell_action,
        cell_transfer,
        cell_count=3,
        paired_endpoints=paired,
    )
    try:
        blocks, telemetry = chain.build_compact_trace_blocks(column_block_size=1)
        diagonal = (
            blocks["bottom_diagonal"],
            blocks["middle_diagonal"],
            blocks["middle_diagonal"],
            blocks["top_diagonal"],
        )
        lower = (blocks["lower"],) * 3
        upper = (blocks["upper"],) * 3
        dense = _block_matrix(diagonal, lower, upper)
        rng = np.random.default_rng(17)
        columns = rng.standard_normal((8, 3)) + 1.0j * rng.standard_normal((8, 3))
        np.testing.assert_allclose(
            chain.apply_columns(columns),
            dense @ columns,
            rtol=2.0e-13,
            atol=2.0e-13,
        )
        rhs = dense @ columns
        solved, _ = solve_block_tridiagonal_recursive(
            diagonal,
            lower,
            upper,
            tuple(np.split(rhs, 4)),
        )
        np.testing.assert_allclose(solved, columns, rtol=2.0e-13, atol=2.0e-13)
        assert telemetry["unique_operator_blocks"] == 5
        assert telemetry["global_dense_formed"] is False
        assert chain.dense_global_formed is False
        assert chain.cell_count == 3
    finally:
        chain.destroy()
        chain.destroy()
    assert cell_action.destroy_count == 1
    if bottom_action is not None:
        assert bottom_action.destroy_count == 1
    if top_action is not None:
        assert top_action.destroy_count == 1


def test_endpoint_metric_uses_sparse_actions_and_implicit_inverse() -> None:
    values = np.asarray(
        [[3.0, 1.0 + 0.2j], [1.0 - 0.2j, 2.0]],
        dtype=np.complex128,
    )
    matrix = _aij(values)
    solver = PETSc.KSP().create(PETSc.COMM_SELF)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.LU)
    solver.setOperators(matrix)
    solver.setErrorIfNotConverged(True)
    solver.setUp()
    action = EndpointTraceMassAction(
        matrix=matrix,
        solver=solver,
        active_rows=np.asarray([3, 7]),
        hermitian_relative_defect=0.0,
        constraint_action_relative_error=0.0,
        solve_relative_residual=0.0,
    )
    columns = np.asarray(
        [[1.0 + 0.1j, 0.4], [0.2j, -0.3 + 0.2j]],
        dtype=np.complex128,
    )
    expected_solve = np.linalg.solve(values, columns)
    np.testing.assert_allclose(action.multiply_columns(columns), values @ columns)
    np.testing.assert_allclose(action.solve_columns(columns), expected_solve)
    np.testing.assert_allclose(
        action.dual_gram(columns), columns.conj().T @ expected_solve
    )
    assert not hasattr(action, "inverse")
    assert "aij" in action.matrix.getType().lower()
    action.destroy()
    action.destroy()


def test_oracle_modules_are_explicitly_research_only() -> None:
    assert ONE_CELL_RESEARCH_STATUS == "research_only_correctness_oracle"
    assert hybrid_trace_chain.RESEARCH_STATUS == "research_only_correctness_oracle"
    assert hybrid_port_metric.RESEARCH_STATUS == "research_only_endpoint_metric"
