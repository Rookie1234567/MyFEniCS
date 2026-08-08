from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_local_dtn_woodbury import (
    R4_MODAL_COUNT,
    build_hybrid_local_dtn_woodbury_local_inverse,
)
from src.solvers.hybrid_local_iterative_inverse import R3_PRECONDITIONER_PROFILE


class _DenseMatPythonAction:
    def __init__(self, dense: np.ndarray) -> None:
        self.dense = np.asarray(dense, dtype=np.complex128)
        self.destroyed = False

    def mult(self, _matrix, source: PETSc.Vec, target: PETSc.Vec) -> None:
        comm = source.getComm().tompi4py()
        first, last = (int(value) for value in source.getOwnershipRange())
        local = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        values = np.empty(source.getSize(), dtype=np.complex128)
        for packet_first, packet_last, packet in comm.allgather((first, last, local)):
            values[packet_first:packet_last] = packet
        target_first, target_last = (int(value) for value in target.getOwnershipRange())
        target.getArray()[:] = (self.dense @ values)[target_first:target_last]

    def destroy(self, _matrix=None) -> None:
        self.destroyed = True


class _FakeSmoother:
    def __init__(self, diagonal: complex, rows: int) -> None:
        self.diagonal = complex(diagonal)
        self.diagnostics = {
            "global_subdomain_count": 1,
            "global_factor_nnz": rows,
            "global_stored_factor_nnz": rows,
            "max_sender_payload_bytes": 0,
            "max_owner_payload_bytes": 0,
        }
        self.destroyed = False

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128)
            / self.diagonal
        )

    def destroy(self) -> None:
        self.destroyed = True


class _FakeWholeEndcapInverse:
    def __init__(self, diagonal: complex, rows: int) -> None:
        self.preconditioner_profile = R3_PRECONDITIONER_PROFILE
        self.smoother = _FakeSmoother(diagonal, rows)
        self.factor_count_after_destroy = None
        self.factors_released = False

    def destroy(self) -> None:
        self.smoother.destroy()
        self.factor_count_after_destroy = 0
        self.factors_released = True


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
    first, last = (int(value) for value in vector.getOwnershipRange())
    values = rng.standard_normal(vector.getSize()) + 1j * rng.standard_normal(
        vector.getSize()
    )
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    return vector


def _relative_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    finally:
        difference.destroy()


def test_r5_local_inverse_fixed_pc_linearity_repeat_and_lifecycle():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        return
    rows = 8
    rng = np.random.default_rng(240)
    fine_dense = np.eye(rows, dtype=np.complex128) * (2.0 + 0.15j)
    base_diagonal = 1.7 + 0.1j
    c_dense = rng.standard_normal((rows, R4_MODAL_COUNT)) + 1j * rng.standard_normal(
        (rows, R4_MODAL_COUNT)
    )
    d_dense = rng.standard_normal((R4_MODAL_COUNT, rows)) + 1j * rng.standard_normal(
        (R4_MODAL_COUNT, rows)
    )
    h_dense = np.eye(R4_MODAL_COUNT, dtype=np.complex128) * (3.0 + 0.2j)
    complete_dense = fine_dense - c_dense @ np.linalg.solve(h_dense, d_dense)
    F = _matrix_from_dense(fine_dense)
    C = _python_matrix_from_dense(c_dense)
    D = _python_matrix_from_dense(d_dense)
    H = _matrix_from_dense(h_dense)
    A = _python_matrix_from_dense(complete_dense)
    action = SimpleNamespace(
        A=A,
        inventory={
            "global_A_materialized": False,
            "direct_factor_count": 0,
        },
    )
    base = _FakeWholeEndcapInverse(base_diagonal, rows)
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    inverse = build_hybrid_local_dtn_woodbury_local_inverse(
        action,
        base,
        components=components,
    )
    source_template = A.createVecRight()
    rhs = _random_vector(source_template, 2401)
    r1 = _random_vector(source_template, 2402)
    r2 = _random_vector(source_template, 2403)
    p1 = A.createVecLeft()
    p2 = A.createVecLeft()
    lhs = A.createVecLeft()
    rhs_pc = A.createVecLeft()
    repeat = A.createVecLeft()
    result = None
    repeated_result = None
    try:
        alpha = PETSc.ScalarType(1.25)
        beta = PETSc.ScalarType(-0.75)
        inverse.woodbury.apply(r1, p1)
        inverse.woodbury.apply(r2, p2)
        inverse.woodbury.apply(r1, repeat)
        combined_rhs = r1.duplicate()
        try:
            r1.copy(combined_rhs)
            combined_rhs.scale(alpha)
            combined_rhs.axpy(beta, r2)
            inverse.woodbury.apply(combined_rhs, lhs)
        finally:
            combined_rhs.destroy()
        p1.copy(rhs_pc)
        rhs_pc.scale(alpha)
        rhs_pc.axpy(beta, p2)
        assert _relative_error(lhs, rhs_pc) <= 1.0e-11
        assert _relative_error(p1, repeat) <= 1.0e-12
        diagnostics = inverse.diagnostics
        assert diagnostics["woodbury"]["K_rank"] == R4_MODAL_COUNT
        assert np.isfinite(diagnostics["woodbury"]["K_condition_number"])
        assert diagnostics["woodbury"]["K_condition_number"] <= 1.0e10
        assert diagnostics["woodbury"]["arrays_finite"] is True
        assert diagnostics["no_direct_fallback"] is True
        result = inverse.solve(rhs)
        repeated_result = inverse.solve(rhs)
        assert result.converged_reason > 0
        assert result.iterations <= 300
        assert result.true_relative_residual <= 1.0e-8
        assert _relative_error(result.solution, repeated_result.solution) <= 1.0e-12
        assert inverse.diagnostics["operator"]["global_A_materialized"] is False
    finally:
        if result is not None:
            result.destroy()
        if repeated_result is not None:
            repeated_result.destroy()
        repeat.destroy()
        rhs_pc.destroy()
        lhs.destroy()
        p2.destroy()
        p1.destroy()
        r2.destroy()
        r1.destroy()
        rhs.destroy()
        source_template.destroy()
        inverse.destroy()
        assert inverse.factor_count_before_destroy == 1
        assert inverse.factor_count_after_destroy == 0
        assert inverse.factors_released is True
        assert inverse.woodbury.diagnostics["destroyed"] is True
        assert base.smoother.destroyed is True
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()
        A.destroy()
