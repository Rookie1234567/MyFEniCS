from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_local_dtn_woodbury import HybridLocalDtnWoodburyFixedAction
from src.solvers.hybrid_side_subspace_correction import (
    FixedSideErrorSubspaceCorrectionAction,
)


class _DenseBaseAction:
    def __init__(self, inverse_diagonal: np.ndarray) -> None:
        self.inverse_diagonal = np.asarray(inverse_diagonal, dtype=np.complex128)
        self.apply_count = 0

    @property
    def diagnostics(self) -> dict[str, object]:
        return {"factor_count": 1, "ksp_created": False}

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128)
            * self.inverse_diagonal[
                int(target.getOwnershipRange()[0]) : int(target.getOwnershipRange()[1])
            ]
        )
        self.apply_count += 1


class _DenseMatPythonAction:
    def __init__(self, dense: np.ndarray) -> None:
        self.dense = np.asarray(dense, dtype=np.complex128)
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        comm = source.getComm().tompi4py()
        first, last = (int(value) for value in source.getOwnershipRange())
        local = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        values = np.empty(source.getSize(), dtype=np.complex128)
        for packet_first, packet_last, packet_values in comm.allgather(
            (first, last, local)
        ):
            values[packet_first:packet_last] = packet_values
        target_first, target_last = (int(value) for value in target.getOwnershipRange())
        target.getArray()[:] = (self.dense @ values)[target_first:target_last]

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True


def _python_matrix_from_dense(values: np.ndarray) -> PETSc.Mat:
    matrix = PETSc.Mat().createPython(
        values.shape,
        context=_DenseMatPythonAction(values),
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    return matrix


def _matrix_from_dense(values: np.ndarray) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(values.shape, comm=MPI.COMM_WORLD)
    matrix.setUp()
    first, last = (int(value) for value in matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValues(
            row,
            np.arange(values.shape[1], dtype=PETSc.IntType),
            values[row],
        )
    matrix.assemble()
    return matrix


def _seed_vector(operator: PETSc.Mat, seed: int) -> PETSc.Vec:
    vector = operator.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    indices = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = np.sin((seed + 1.0) * (indices + 1.0) * 0.173) + 1j * np.cos(
        (seed + 2.0) * (indices + 1.0) * 0.119
    )
    return vector


def _vector_from_formula(operator: PETSc.Mat) -> PETSc.Vec:
    vector = operator.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    indices = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = 0.7 * np.cos((indices + 1.0) * 0.071) + 1j * 0.4 * np.sin(
        (indices + 1.0) * 0.113
    )
    return vector


def _digest(vector: PETSc.Vec) -> str:
    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).tobytes()
    digest = hashlib.sha256()
    for packet_first, packet_last, payload in sorted(
        comm.allgather((first, last, local))
    ):
        digest.update(np.asarray((packet_first, packet_last), dtype="<i8").tobytes())
        digest.update(payload)
    return digest.hexdigest()


def _relative_residual(
    operator: PETSc.Mat, source: PETSc.Vec, solution: PETSc.Vec
) -> float:
    applied = operator.createVecLeft()
    residual = operator.createVecLeft()
    try:
        operator.mult(solution, applied)
        source.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), applied)
        return float(residual.norm()) / max(float(source.norm()), 1.0e-30)
    finally:
        applied.destroy()
        residual.destroy()


def test_fixed_side_error_subspace_correction_is_fixed_linear_and_releases_borrowed_objects():
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    size = 24
    diagonal = np.linspace(1.8, 3.6, size).astype(np.complex128)
    diagonal[0] += 0.2j
    diagonal[1] -= 0.15j
    f_dense = np.diag(diagonal)
    c_dense = np.zeros((size, 2), dtype=np.complex128)
    d_dense = np.zeros((2, size), dtype=np.complex128)
    c_dense[0, 0] = 0.18 + 0.04j
    c_dense[1, 1] = -0.14 + 0.03j
    d_dense[0, 0] = 0.23 - 0.02j
    d_dense[1, 1] = 0.16 + 0.01j
    h_dense = np.diag(np.asarray([1.7 + 0.1j, 2.2 - 0.15j], dtype=np.complex128))
    operator_dense = f_dense - c_dense @ np.linalg.solve(h_dense, d_dense)
    f_matrix = _python_matrix_from_dense(f_dense)
    f_context = f_matrix.getPythonContext()
    operator = _python_matrix_from_dense(operator_dense)
    operator_context = operator.getPythonContext()
    c_matrix = _matrix_from_dense(c_dense)
    d_matrix = _matrix_from_dense(d_dense)
    h_matrix = _matrix_from_dense(h_dense)
    components = SimpleNamespace(F=f_matrix, C=c_matrix, D=d_matrix, H=h_matrix)
    inverse = 1.0 / diagonal
    inverse[:2] *= 0.5
    base = _DenseBaseAction(inverse)
    fixed = HybridLocalDtnWoodburyFixedAction(base, components)
    seeds = [_seed_vector(operator, seed) for seed in range(8)]
    action = FixedSideErrorSubspaceCorrectionAction(operator, fixed, seeds)
    source = _vector_from_formula(operator)
    other = _seed_vector(operator, 19)
    combined = operator.createVecRight()
    base_solution = operator.createVecLeft()
    corrected = operator.createVecLeft()
    corrected_repeat = operator.createVecLeft()
    linear_left = operator.createVecLeft()
    linear_right = operator.createVecLeft()
    f_applied = f_matrix.createVecLeft()
    a_applied = operator.createVecLeft()
    try:
        f_matrix.mult(source, f_applied)
        operator.mult(source, a_applied)
        a_applied.axpy(PETSc.ScalarType(-1.0), f_applied)
        assert float(a_applied.norm()) / max(float(source.norm()), 1.0e-30) > 1.0e-6
        fixed.apply(source, base_solution)
        base_error = _relative_residual(operator, source, base_solution)
        action.apply(source, corrected)
        corrected_error = _relative_residual(operator, source, corrected)
        assert corrected_error < base_error * 1.0e-8
        digest = _digest(corrected)
        action.apply(source, corrected_repeat)
        assert _digest(corrected_repeat) == digest

        source.copy(combined)
        combined.axpy(PETSc.ScalarType(1.0), other)
        action.apply(combined, linear_left)
        action.apply(source, linear_right)
        other_result = operator.createVecLeft()
        try:
            action.apply(other, other_result)
            linear_right.axpy(PETSc.ScalarType(1.0), other_result)
            linear_left.axpy(PETSc.ScalarType(-1.0), linear_right)
            assert float(linear_left.norm()) <= 1.0e-11
        finally:
            other_result.destroy()

        diagnostics = action.diagnostics
        assert diagnostics["seed_count"] == 8
        assert diagnostics["arnoldi_depth"] == 16
        assert diagnostics["seed_block_is_layer_one"] is True
        assert diagnostics["rank"] <= 128
        assert diagnostics["rank"] > 0
        assert diagnostics["normal_equations"] is False
        assert diagnostics["svd"] is False
        assert diagnostics["direct_factor_count"] == 0
        assert diagnostics["global_hybrid_direct_factor_count"] == 0
        assert diagnostics["base_ilu_factor_count"] == 1
        assert diagnostics["base_nested_ksp_created"] is False
        assert diagnostics["q_orthogonality_error"] <= 1.0e-11
        assert diagnostics["qr_reconstruction_relative_error"] <= 1.0e-11
        assert np.isfinite(diagnostics["R_condition_number"])
        assert diagnostics["apply_count"] == 5
    finally:
        linear_right.destroy()
        linear_left.destroy()
        a_applied.destroy()
        f_applied.destroy()
        corrected_repeat.destroy()
        corrected.destroy()
        base_solution.destroy()
        combined.destroy()
        other.destroy()
        source.destroy()
        action.destroy()
        assert action.diagnostics["destroyed"] is True
        assert operator_context.destroyed is False
        assert f_context.destroyed is False
        fixed.destroy()
        operator.destroy()
        f_matrix.destroy()
        c_matrix.destroy()
        d_matrix.destroy()
        h_matrix.destroy()
        for seed in seeds:
            seed.destroy()
        assert operator_context.destroyed is True
        assert f_context.destroyed is True
