"""Focused V1-2 interface Schur algebra contracts."""

from __future__ import annotations

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    NumpyInterfaceSchurOracle,
    ProjectedExactPetrovAction,
    build_petsc_interface_schur_oracle,
)


def _tiny_bare() -> np.ndarray:
    rows = np.arange(8, dtype=float)[:, None]
    cols = np.arange(8, dtype=float)[None, :]
    matrix = (0.07 + 0.02j) * (rows + 1.0) * (cols + 2.0)
    matrix += np.diag(3.0 + 0.11j * np.arange(8))
    return np.asarray(matrix, dtype=np.complex128)


def _tiny_groups() -> tuple[tuple[int, ...], ...]:
    return ((0, 1, 2, 3), (2, 3, 4, 5, 6), (6, 7))


def _tiny_interfaces() -> tuple[tuple[int, ...], ...]:
    return ((2, 3), (6,))


def _reference_schur(
    bare: np.ndarray, group: tuple[int, ...], gamma: tuple[int, ...]
) -> np.ndarray:
    interior = tuple(row for row in group if row not in gamma)
    a_gg = bare[np.ix_(gamma, gamma)]
    a_gi = bare[np.ix_(gamma, interior)]
    a_ig = bare[np.ix_(interior, gamma)]
    return a_gg - a_gi @ np.linalg.solve(bare[np.ix_(interior, interior)], a_ig)


def test_numpy_interface_schur_matches_nonhermitian_reference():
    bare = _tiny_bare()
    oracle = NumpyInterfaceSchurOracle(bare, _tiny_groups(), _tiny_interfaces())
    try:
        directed = oracle.directed_blocks()
        assert set(directed) == {
            "group0_to_lower",
            "group1_to_lower",
            "group1_to_upper",
            "group2_to_upper",
        }
        group1_full = _reference_schur(bare, (2, 3, 4, 5, 6), (2, 3, 6))
        expected = {
            "group0_to_lower": _reference_schur(bare, (0, 1, 2, 3), (2, 3)),
            "group1_to_lower": group1_full[np.ix_((0, 1), (0, 1))],
            "group1_to_upper": group1_full[np.ix_((2,), (2,))],
            "group2_to_upper": _reference_schur(bare, (6, 7), (6,)),
        }
        for name, value in expected.items():
            assert np.allclose(directed[name], value, rtol=0.0, atol=1.0e-13)
        full_group1 = _reference_schur(bare, (2, 3, 4, 5, 6), (2, 3, 6))
        cross = oracle.cross_interface_coupling_blocks()
        assert np.allclose(cross["lower_to_upper"], full_group1[np.ix_((2,), (0, 1))])
        assert np.allclose(cross["upper_to_lower"], full_group1[np.ix_((0, 1), (2,))])
        norms = oracle.cross_interface_coupling_norms()
        assert set(norms) == {"lower_to_upper", "upper_to_lower"}
        assert norms["lower_to_upper"] != norms["upper_to_lower"]
        assert oracle.diagnostics["factor_count_ready"] == 3
    finally:
        oracle.destroy()


def test_projected_petrov_action_solves_nonorthogonal_complex_gram():
    scalar = np.asarray(
        [[2.0 + 0.1j, 0.2 - 0.3j, 0.0], [0.1 + 0.2j, 1.7, 0.4j], [0.0, 0.3, 1.2]],
        dtype=np.complex128,
    )
    exact = scalar.copy()
    exact[0, 0] += 0.7 - 0.2j
    exact[1, 1] -= 0.5 + 0.1j
    z = np.eye(3, 2, dtype=np.complex128)
    y = z.copy()
    y[:, 0] += 0.23 * z[:, 1]
    action = ProjectedExactPetrovAction(
        lambda value: scalar @ value,
        lambda value: exact @ value,
        z,
        y,
    )
    try:
        assert not np.allclose(y.conj().T @ z, np.eye(2))
        coefficients = np.asarray([0.4 - 0.7j, -0.2 + 0.3j])
        source = z @ coefficients
        assert np.allclose(action.apply(source), exact @ source, atol=1.0e-13, rtol=0.0)
        assert action.diagnostics["petrov_gram_condition"] > 1.0
    finally:
        action.destroy()


def _petsc_bare() -> PETSc.Mat:
    comm = MPI.COMM_WORLD
    size = 8
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for col in range(size):
            value = (0.04 + 0.01j) * (row + 1) * (col + 1)
            if row == col:
                value += 2.0 + 0.2j * row
            matrix.setValue(row, col, PETSc.ScalarType(value))
    matrix.assemble()
    return matrix


def _petsc_bare_dense() -> np.ndarray:
    rows = np.arange(8, dtype=float)[:, None]
    cols = np.arange(8, dtype=float)[None, :]
    matrix = (0.04 + 0.01j) * (rows + 1.0) * (cols + 1.0)
    matrix += np.diag(2.0 + 0.2j * np.arange(8))
    return np.asarray(matrix, dtype=np.complex128)


def _collect_vec(vector: PETSc.Vec) -> np.ndarray:
    first, last = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.array, dtype=np.complex128).copy()
    pieces = MPI.COMM_WORLD.allgather((first, local))
    result = np.empty(vector.getSize(), dtype=np.complex128)
    for start, values in pieces:
        result[start : start + values.size] = values
    return result


def test_petsc_interface_schur_distributed_action_and_cleanup():
    comm = MPI.COMM_WORLD
    bare = _petsc_bare()
    try:
        first, last = map(int, bare.getOwnershipRange())
        global_groups = _tiny_groups()
        local_groups = tuple(
            np.asarray(
                [row for row in rows if first <= row < last], dtype=PETSc.IntType
            )
            for rows in global_groups
        )
        oracle = build_petsc_interface_schur_oracle(
            bare, local_groups, _tiny_interfaces()
        )
        try:
            diagnostics = oracle.diagnostics
            assert diagnostics["factor_count_ready"] == 3
            assert diagnostics["dense_materialization"] is False
            dense = _petsc_bare_dense()
            expected_groups = _tiny_groups()
            expected_interfaces = _tiny_interfaces()
            saw_local_empty_gamma = False
            for group_index, block in enumerate(oracle._blocks):
                source = block._gamma_rhs.duplicate()
                target = block._gamma_output.duplicate()
                try:
                    source.set(0.0)
                    source.array[:] = np.asarray(
                        0.2
                        + 0.03j
                        * np.arange(
                            source.getOwnershipRange()[0], source.getOwnershipRange()[1]
                        ),
                        dtype=PETSc.ScalarType,
                    )
                    source.assemble()
                    oracle.apply_group(group_index, source, target)
                    gamma = tuple(
                        row
                        for row in expected_groups[group_index]
                        if row in expected_interfaces[0] + expected_interfaces[1]
                    )
                    expected = _reference_schur(
                        dense, expected_groups[group_index], gamma
                    ) @ _collect_vec(source)
                    assert np.allclose(
                        _collect_vec(target), expected, atol=1.0e-12, rtol=0.0
                    )
                    saw_local_empty_gamma |= block.gamma_rows.size == 0
                finally:
                    target.destroy()
                    source.destroy()
            if comm.size > 1:
                assert comm.allreduce(saw_local_empty_gamma, op=MPI.LOR)
        finally:
            oracle.destroy()
            assert oracle.diagnostics["factor_count_after_cleanup"] == 0
    finally:
        bare.destroy()
