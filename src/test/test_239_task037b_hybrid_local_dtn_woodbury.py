from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_local_dtn_woodbury import (
    R4_MODAL_COUNT,
    HybridLocalDtnWoodburyOracle,
)


class _DenseBaseInverse:
    def __init__(self, diagonal: complex) -> None:
        self.diagonal = complex(diagonal)

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128)
            / self.diagonal
        )


class _DenseMatPythonAction:
    def __init__(self, dense: np.ndarray) -> None:
        self.dense = np.asarray(dense, dtype=np.complex128)
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        comm = source.getComm().tompi4py()
        start, end = (int(value) for value in source.getOwnershipRange())
        local = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        values = np.empty(source.getSize(), dtype=np.complex128)
        for first, last, packet in comm.allgather((start, end, local)):
            values[first:last] = packet
        target_start, target_end = (int(value) for value in target.getOwnershipRange())
        result = self.dense @ values
        target.getArray()[:] = result[target_start:target_end]

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True


def _relative_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _matrix_from_dense(values: np.ndarray) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(values.shape, comm=MPI.COMM_WORLD)
    matrix.setUp()
    start, end = (int(value) for value in matrix.getOwnershipRange())
    for row in range(start, end):
        matrix.setValues(
            row, np.arange(values.shape[1], dtype=PETSc.IntType), values[row]
        )
    matrix.assemble()
    return matrix


def _python_matrix_from_dense(values: np.ndarray) -> PETSc.Mat:
    context = _DenseMatPythonAction(values)
    matrix = PETSc.Mat().createPython(
        values.shape,
        context=context,
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    return matrix


def _random_vector(template: PETSc.Vec, seed: int) -> PETSc.Vec:
    vector = template.duplicate()
    rng = np.random.default_rng(seed)
    start, end = (int(value) for value in vector.getOwnershipRange())
    values = rng.standard_normal(vector.getSize()) + 1j * rng.standard_normal(
        vector.getSize()
    )
    vector.getArray()[:] = np.asarray(values[start:end], dtype=PETSc.ScalarType)
    return vector


def test_exact_woodbury_matpython_components_and_lifecycle():
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    rows = 8
    rng = np.random.default_rng(239)
    base_dense = np.eye(rows, dtype=np.complex128) * (2.0 + 0.2j)
    C_dense = rng.standard_normal((rows, R4_MODAL_COUNT)) + 1j * rng.standard_normal(
        (rows, R4_MODAL_COUNT)
    )
    D_dense = rng.standard_normal((R4_MODAL_COUNT, rows)) + 1j * rng.standard_normal(
        (R4_MODAL_COUNT, rows)
    )
    H_dense = np.eye(R4_MODAL_COUNT, dtype=np.complex128) * (3.0 + 0.1j)
    F = _matrix_from_dense(base_dense)
    C = _python_matrix_from_dense(C_dense)
    D = _python_matrix_from_dense(D_dense)
    H = _matrix_from_dense(H_dense)
    c_context = C.getPythonContext()
    d_context = D.getPythonContext()
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    base = _DenseBaseInverse(base_dense[0, 0])
    oracle = HybridLocalDtnWoodburyOracle(base, components)
    try:
        diagnostics = oracle.diagnostics
        assert diagnostics["n_aux"] == R4_MODAL_COUNT
        assert diagnostics["normal_equations"] is False
        assert diagnostics["K_rank"] == R4_MODAL_COUNT
        assert np.isfinite(diagnostics["K_condition_number"])
        assert (
            diagnostics["W_local_nbytes"] == F.getLocalSize()[0] * R4_MODAL_COUNT * 16
        )
        assert diagnostics["K_nbytes"] == R4_MODAL_COUNT * R4_MODAL_COUNT * 16
        for seed in (1, 2, 3):
            source_template = F.createVecRight()
            source = _random_vector(source_template, seed)
            source_template.destroy()
            actual = F.createVecLeft()
            reference = F.createVecLeft()
            try:
                oracle.apply(source, actual)
                start, end = (int(value) for value in source.getOwnershipRange())
                values = np.asarray(
                    source.getArray(readonly=True), dtype=np.complex128
                ).copy()
                packets = comm.allgather((start, end, values))
                rhs = np.empty(rows, dtype=np.complex128)
                for first, last, local in packets:
                    rhs[first:last] = local
                reference_values = np.linalg.solve(
                    base_dense - C_dense @ np.linalg.solve(H_dense, D_dense), rhs
                )
                reference.getArray()[:] = reference_values[start:end]
                assert _relative_error(actual, reference) <= 1.0e-11
                repeat = F.createVecLeft()
                try:
                    oracle.apply(source, repeat)
                    assert _relative_error(actual, repeat) <= 1.0e-12
                finally:
                    repeat.destroy()
            finally:
                actual.destroy()
                reference.destroy()
                source.destroy()
    finally:
        oracle.destroy()
        assert oracle.diagnostics["destroyed"] is True
        assert c_context.destroyed is False
        assert d_context.destroyed is False
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()
        assert c_context.destroyed is True
        assert d_context.destroyed is True
