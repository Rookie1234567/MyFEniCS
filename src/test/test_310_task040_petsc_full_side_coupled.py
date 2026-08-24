"""Tiny PETSc owner-local carrier checks for Task040 V3-2."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_petsc_coupled import (
    build_petsc_coupled_full_side_action,
)
from src.test.test_309_task040_full_side_coupled import _fixture


def _petsc_matrix(values: np.ndarray) -> PETSc.Mat:
    comm = MPI.COMM_WORLD
    size = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    columns = np.arange(size, dtype=PETSc.IntType)
    for row in range(first, last):
        matrix.setValues(
            row,
            columns,
            np.asarray(values[row, :], dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix


def _petsc_vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


def _local_rows(rows: tuple[int, ...], first: int, last: int) -> np.ndarray:
    return np.asarray([row for row in rows if first <= row < last], dtype=PETSc.IntType)


def _carrier(data: dict[str, object], matrix: PETSc.Mat, joint: np.ndarray):
    first, last = map(int, matrix.getOwnershipRange())
    lower_local = _local_rows((0, 1), first, last)
    upper_local = _local_rows((2, 3), first, last)
    gamma_rows = np.concatenate((lower_local, upper_local))[::-1]
    group_rows = (
        _local_rows((4, 0, 1, 5), first, last),
        _local_rows((2, 0, 6, 1, 3, 7), first, last),
        _local_rows((8, 2, 9, 3), first, last),
    )
    return build_petsc_coupled_full_side_action(
        bare_f=matrix,
        group_rows=group_rows,
        lower_support=lower_local,
        upper_support=upper_local,
        gamma_rows_local=gamma_rows,
        local_z=np.asarray(data["z"])[gamma_rows, :],
        local_y=np.asarray(data["y"])[gamma_rows, :],
        joint_matrix=joint,
        factor_solver_type="mumps",
    )


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), 1.0e-30))


def test_petsc_carrier_matches_direct_full_solve_and_lifecycle() -> None:
    data = _fixture()
    matrix = _petsc_matrix(np.asarray(data["full"]))
    action = _carrier(data, matrix, np.asarray(data["joint"]))
    source = _petsc_vector(matrix, np.asarray(data["source"]))
    target = matrix.createVecRight()
    action.apply(source, target)
    first, last = map(int, target.getOwnershipRange())
    direct = np.linalg.solve(np.asarray(data["full"]), np.asarray(data["source"]))
    assert _relative(target.array, direct[first:last]) <= 1.0e-12
    residual = matrix.createVecRight()
    matrix.mult(target, residual)
    residual.axpy(PETSc.ScalarType(-1.0), source)
    assert residual.norm() / source.norm() <= 1.0e-12

    diagnostics = action.diagnostics
    assert diagnostics["packet_dependent"] is True
    assert diagnostics["cross_section_group_factor_count"] == 3
    assert diagnostics["exact_interface_schur_oracle_object_count"] == 0
    assert diagnostics["full_side_exact_factor_count"] == 0
    assert diagnostics["global_direct_factor_count"] == 0
    assert diagnostics["reduced_dense_factor_count"] == 1
    assert diagnostics["fe_numeric_allgather"] is False
    assert diagnostics["cross_interior_coupling_pass"] is True
    assert len(diagnostics["cross_interior_coupling_norms"]) == 6
    assert diagnostics["joint_sha256"]
    assert diagnostics["gamma_rows_local_sha256"]

    zero = matrix.createVecRight()
    zero.set(0.0)
    zero_target = matrix.createVecRight()
    action.apply(zero, zero_target)
    assert zero_target.norm() == 0.0
    repeated = matrix.createVecRight()
    action.apply(source, repeated)
    repeated.axpy(PETSc.ScalarType(-1.0), target)
    assert repeated.norm() / target.norm() <= 1.0e-12

    other_values = np.roll(np.asarray(data["source"]), 1)
    other = _petsc_vector(matrix, other_values)
    other_target = matrix.createVecRight()
    action.apply(other, other_target)
    combined = matrix.createVecRight()
    combined_values = 1.7 * np.asarray(data["source"]) - 0.4j * other_values
    combined_source = _petsc_vector(matrix, combined_values)
    action.apply(combined_source, combined)
    expected = combined.duplicate()
    expected.set(0.0)
    expected.axpy(PETSc.ScalarType(1.7), target)
    expected.axpy(PETSc.ScalarType(-0.4j), other_target)
    expected_norm = expected.norm()
    combined.axpy(PETSc.ScalarType(-1.0), expected)
    assert combined.norm() / expected_norm <= 1.0e-12

    target.destroy()
    zero_target.destroy()
    zero.destroy()
    repeated.destroy()
    expected.destroy()
    combined_source.destroy()
    combined.destroy()
    other_target.destroy()
    other.destroy()
    residual.destroy()
    source.destroy()
    action.destroy()
    after = action.diagnostics
    assert after["factor_count_after_cleanup"] == 0
    assert after["reduced_dense_factor_retained"] is False
    assert after["destroyed"] is True
    matrix.destroy()


def test_petsc_carrier_cross_omission_is_not_a_full_solve() -> None:
    data = _fixture()
    matrix = _petsc_matrix(np.asarray(data["full"]))
    omitted = np.asarray(data["schur"]).copy()
    omitted[:2, 2:] = 0.0
    omitted[2:, :2] = 0.0
    omitted_joint = np.asarray(data["y"]).conj().T @ omitted @ np.asarray(data["z"])
    action = _carrier(data, matrix, omitted_joint)
    source = _petsc_vector(matrix, np.asarray(data["source"]))
    target = matrix.createVecRight()
    action.apply(source, target)
    residual = matrix.createVecRight()
    matrix.mult(target, residual)
    residual.axpy(PETSc.ScalarType(-1.0), source)
    assert residual.norm() / source.norm() > 0.25
    residual.destroy()
    target.destroy()
    source.destroy()
    action.destroy()
    matrix.destroy()


def test_petsc_carrier_rejects_one_way_interior_coupling() -> None:
    data = _fixture()
    values = np.asarray(data["full"]).copy()
    values[6, 4] += 0.2
    values[7, 5] += 0.2
    matrix = _petsc_matrix(values)
    with pytest.raises(ValueError, match="cross-group interior coupling"):
        _carrier(data, matrix, np.asarray(data["joint"]))
    matrix.destroy()


def test_petsc_carrier_owner_layout_is_collective() -> None:
    data = _fixture()
    matrix = _petsc_matrix(np.asarray(data["full"]))
    action = _carrier(data, matrix, np.asarray(data["joint"]))
    diagnostics = action.diagnostics
    gathered = MPI.COMM_WORLD.allgather(
        (diagnostics["gamma_rows_local"], diagnostics["gamma_rows_local_sha256"])
    )
    assert sum(item[0] for item in gathered) == 4
    assert all(item[1] for item in gathered)
    action.destroy()
    matrix.destroy()
