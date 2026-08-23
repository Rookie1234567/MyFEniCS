"""Focused distributed Woodbury carrier tests for the conditional Run-B path."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    build_fixed_projected_group_inverse,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse


def _dense_base() -> np.ndarray:
    return np.asarray(
        [
            [2.1 + 0.2j, 0.3 - 0.1j, 0.1 + 0.05j],
            [0.2 + 0.4j, 1.7 - 0.1j, -0.2j],
            [0.05 - 0.1j, 0.25 + 0.2j, 1.4 + 0.3j],
        ],
        dtype=np.complex128,
    )


def _dense_u() -> np.ndarray:
    return np.asarray(
        [
            [0.7 + 0.2j, -0.1 + 0.3j],
            [0.2 - 0.4j, 0.5 + 0.1j],
            [-0.3 + 0.2j, 0.4 - 0.2j],
        ],
        dtype=np.complex128,
    )


def _dense_v() -> np.ndarray:
    return np.asarray(
        [
            [0.1 - 0.5j, 0.6 + 0.2j],
            [0.8 + 0.1j, -0.2 + 0.4j],
            [0.3 + 0.3j, 0.2 - 0.6j],
        ],
        dtype=np.complex128,
    )


def _distributed_matrix(values: np.ndarray) -> PETSc.Mat:
    size = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for column in range(size):
            matrix.setValue(row, column, PETSc.ScalarType(values[row, column]))
    matrix.assemble()
    return matrix


def _set_global(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _collect_global(vector: PETSc.Vec) -> np.ndarray:
    first, _last = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.array, dtype=np.complex128).copy()
    pieces = MPI.COMM_WORLD.allgather((first, local))
    values = np.empty(int(vector.getSize()), dtype=np.complex128)
    for start, part in pieces:
        values[start : start + part.size] = part
    return values


def test_fixed_projected_group_inverse_matches_dense_reference_and_releases():
    base = _dense_base()
    u = _dense_u()
    v = _dense_v()
    operator = base + u @ v.conj().T
    matrix = _distributed_matrix(base)
    layout = matrix.createVecRight()
    factor = None
    carrier = None
    vectors: list[PETSc.Vec] = []
    try:
        factor = ResearchExactFactorInverse(
            matrix,
            factor_solver_type="mumps",
            factor_only_storage=True,
        )
        factor.release_borrowed_matrix()
        matrix.destroy()
        matrix = None
        first, last = map(int, layout.getOwnershipRange())
        carrier = build_fixed_projected_group_inverse(
            layout,
            factor,
            u[first:last],
            v[first:last],
        )
        diagnostics = carrier.diagnostics
        assert diagnostics["operator_identity"] == "B_plus_U_VH"
        assert diagnostics["normal_equations"] is False
        assert diagnostics["fe_numeric_allgather"] is False
        assert diagnostics["nested_ksp_count"] == 0
        assert diagnostics["small_replicated_shapes"]["K"] == [2, 2]
        assert diagnostics["K_rank"] == 2
        assert diagnostics["base_solve_count"] == 2
        if MPI.COMM_WORLD.size >= 4:
            assert MPI.COMM_WORLD.allreduce(layout.getLocalSize() == 0, op=MPI.LOR)

        source_values = np.asarray([1.0 - 0.4j, -0.3 + 0.8j, 0.6 + 0.2j])
        second_values = np.asarray([-0.2 + 0.5j, 0.7 + 0.1j, 0.4 - 0.6j])
        outputs: list[np.ndarray] = []
        for values in (source_values, second_values, source_values):
            source = layout.duplicate()
            target = layout.duplicate()
            vectors.extend((source, target))
            _set_global(source, values)
            carrier.apply(source, target)
            outputs.append(_collect_global(target))
        combined = (1.2 - 0.3j) * source_values + (-0.4 + 0.2j) * second_values
        source = layout.duplicate()
        target = layout.duplicate()
        vectors.extend((source, target))
        _set_global(source, combined)
        carrier.apply(source, target)
        outputs.append(_collect_global(target))

        expected = [
            np.linalg.solve(operator, values)
            for values in (source_values, second_values, source_values, combined)
        ]
        for actual, reference in zip(outputs, expected):
            assert np.allclose(actual, reference, rtol=0.0, atol=1.0e-11)
        assert np.allclose(
            outputs[3],
            (1.2 - 0.3j) * outputs[0] + (-0.4 + 0.2j) * outputs[1],
            rtol=0.0,
            atol=1.0e-11,
        )
        assert carrier.diagnostics["apply_count"] == 4
        assert carrier.diagnostics["base_solve_count"] == 6
    finally:
        for vector in vectors:
            vector.destroy()
        if carrier is not None:
            carrier.destroy()
            assert carrier.diagnostics["destroyed"] is True
            assert carrier.diagnostics["base_factor_reference_released"] is True
            assert factor is not None
            assert factor.diagnostics["factor_destroyed"] is False
        layout.destroy()
        if factor is not None:
            factor.destroy()
            assert factor.diagnostics["factor_destroyed"] is True
        if matrix is not None:
            matrix.destroy()


def test_fixed_projected_group_inverse_singular_k_cleans_borrowed_state():
    base = np.eye(3, dtype=np.complex128)
    matrix = _distributed_matrix(base)
    layout = matrix.createVecRight()
    factor = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=True,
    )
    factor.release_borrowed_matrix()
    matrix.destroy()
    first, last = map(int, layout.getOwnershipRange())
    local_u = np.zeros((last - first, 1), dtype=np.complex128)
    local_v = np.zeros_like(local_u)
    if first <= 0 < last:
        local_u[0 - first, 0] = 1.0
        local_v[0 - first, 0] = -1.0
    try:
        with pytest.raises(ValueError, match="small K is singular"):
            build_fixed_projected_group_inverse(layout, factor, local_u, local_v)
        assert factor.diagnostics["factor_destroyed"] is False
    finally:
        layout.destroy()
        factor.destroy()
