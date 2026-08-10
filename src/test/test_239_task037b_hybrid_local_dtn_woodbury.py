from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_local_dtn_woodbury import (
    HYBRID_DTN_WOODBURY_MODE_COUNT,
    HybridLocalDtnWoodburyFixedAction,
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


class _FixedBaseAction:
    def __init__(self, base: _DenseBaseInverse) -> None:
        self.base = base
        self.apply_count = 0

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "identity": "tiny_fixed_non_ksp_base",
            "factor_count": 1,
            "ksp_created": False,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply_count += 1
        self.base.solve(source, target)


def _global_vec_digest(vector: PETSc.Vec) -> str:
    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    packets = comm.allgather((first, last, local.tobytes(order="C")))
    digest = hashlib.sha256()
    for packet_first, packet_last, payload in sorted(packets):
        digest.update(np.asarray((packet_first, packet_last), dtype="<i8").tobytes())
        digest.update(payload)
    return digest.hexdigest()


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
    C_dense = rng.standard_normal(
        (rows, HYBRID_DTN_WOODBURY_MODE_COUNT)
    ) + 1j * rng.standard_normal((rows, HYBRID_DTN_WOODBURY_MODE_COUNT))
    D_dense = rng.standard_normal(
        (HYBRID_DTN_WOODBURY_MODE_COUNT, rows)
    ) + 1j * rng.standard_normal((HYBRID_DTN_WOODBURY_MODE_COUNT, rows))
    H_dense = np.eye(HYBRID_DTN_WOODBURY_MODE_COUNT, dtype=np.complex128) * (3.0 + 0.1j)
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
        assert diagnostics["n_aux"] == HYBRID_DTN_WOODBURY_MODE_COUNT
        assert diagnostics["normal_equations"] is False
        assert diagnostics["K_rank"] == HYBRID_DTN_WOODBURY_MODE_COUNT
        assert np.isfinite(diagnostics["K_condition_number"])
        assert (
            diagnostics["W_local_nbytes"]
            == F.getLocalSize()[0] * HYBRID_DTN_WOODBURY_MODE_COUNT * 16
        )
        assert (
            diagnostics["K_nbytes"]
            == HYBRID_DTN_WOODBURY_MODE_COUNT * HYBRID_DTN_WOODBURY_MODE_COUNT * 16
        )
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


def test_fixed_woodbury_action_is_one_apply_nonowning_and_fail_closed():
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    rows = 8
    rng = np.random.default_rng(240)
    base_dense = np.eye(rows, dtype=np.complex128) * (2.0 + 0.2j)
    C_dense = rng.standard_normal(
        (rows, HYBRID_DTN_WOODBURY_MODE_COUNT)
    ) + 1j * rng.standard_normal((rows, HYBRID_DTN_WOODBURY_MODE_COUNT))
    D_dense = rng.standard_normal(
        (HYBRID_DTN_WOODBURY_MODE_COUNT, rows)
    ) + 1j * rng.standard_normal((HYBRID_DTN_WOODBURY_MODE_COUNT, rows))
    H_dense = np.eye(HYBRID_DTN_WOODBURY_MODE_COUNT, dtype=np.complex128) * (3.0 + 0.1j)
    F = _matrix_from_dense(base_dense)
    C = _python_matrix_from_dense(C_dense)
    D = _python_matrix_from_dense(D_dense)
    H = _matrix_from_dense(H_dense)
    c_context = C.getPythonContext()
    d_context = D.getPythonContext()
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    base = _DenseBaseInverse(base_dense[0, 0])
    existing = HybridLocalDtnWoodburyOracle(base, components)
    base_action = _FixedBaseAction(base)
    fixed = HybridLocalDtnWoodburyFixedAction(base_action, components)
    try:
        diagnostics = fixed.diagnostics
        assert diagnostics["nested_ksp_created"] is False
        assert diagnostics["base_factor_count"] == 1
        assert diagnostics["base_diagnostics"]["identity"] == "tiny_fixed_non_ksp_base"
        assert diagnostics["local_direct_factor_count"] == 0
        assert diagnostics["local_direct_factor_count_owned"] == 0
        assert diagnostics["woodbury"]["K_rank"] == HYBRID_DTN_WOODBURY_MODE_COUNT
        assert np.isfinite(diagnostics["woodbury"]["K_condition_number"])
        assert diagnostics["woodbury"]["K_condition_number"] <= 1.0e10
        assert diagnostics["woodbury"]["arrays_finite"] is True
        assert not hasattr(fixed, "ksp")
        assert fixed.diagnostics["woodbury"]["apply_count"] == 0
        assert base_action.apply_count == 40

        template = F.createVecRight()
        source = _random_vector(template, 240)
        other = _random_vector(template, 241)
        template.destroy()
        existing_target = F.createVecLeft()
        fixed_target = F.createVecLeft()
        repeat_target = F.createVecLeft()
        combined = F.createVecRight()
        lhs = F.createVecLeft()
        source_action = F.createVecLeft()
        other_action = F.createVecLeft()
        linear_rhs = F.createVecLeft()
        try:
            existing.apply(source, existing_target)
            before_count = fixed.diagnostics["woodbury"]["apply_count"]
            fixed.apply(source, fixed_target)
            assert fixed.diagnostics["woodbury"]["apply_count"] == before_count + 1
            assert base_action.apply_count == 41
            assert _relative_error(fixed_target, existing_target) <= 1.0e-13

            alpha = PETSc.ScalarType(0.7 - 0.2j)
            beta = PETSc.ScalarType(-0.3 + 0.4j)
            source.copy(combined)
            combined.scale(alpha)
            combined.axpy(beta, other)
            fixed.apply(combined, lhs)
            fixed.apply(source, source_action)
            fixed.apply(other, other_action)
            source_action.scale(alpha)
            other_action.scale(beta)
            source_action.axpy(PETSc.ScalarType(1.0), other_action)
            source_action.copy(linear_rhs)
            assert _relative_error(lhs, linear_rhs) <= 1.0e-12

            fixed.apply(source, repeat_target)
            repeat_digest = _global_vec_digest(repeat_target)
            fixed.apply(source, existing_target)
            assert _relative_error(repeat_target, existing_target) <= 1.0e-14
            assert repeat_digest == _global_vec_digest(existing_target)
            assert fixed.diagnostics["woodbury"]["apply_count"] == 6
            assert base_action.apply_count == 46
        finally:
            linear_rhs.destroy()
            other_action.destroy()
            source_action.destroy()
            lhs.destroy()
            combined.destroy()
            repeat_target.destroy()
            fixed_target.destroy()
            existing_target.destroy()
            other.destroy()
            source.destroy()
    finally:
        fixed.destroy()
        assert fixed.diagnostics["destroyed"] is True
        assert fixed.diagnostics["owned_action_data_released"] is True
        with pytest.raises(RuntimeError, match="destroyed"):
            source = F.createVecRight()
            target = F.createVecLeft()
            try:
                fixed.apply(source, target)
            finally:
                target.destroy()
                source.destroy()
        existing_target = F.createVecLeft()
        source_template = F.createVecRight()
        source = _random_vector(source_template, 241)
        source_template.destroy()
        try:
            existing.apply(source, existing_target)
        finally:
            existing_target.destroy()
            source.destroy()
        existing.destroy()
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()
        assert c_context.destroyed is True
        assert d_context.destroyed is True
