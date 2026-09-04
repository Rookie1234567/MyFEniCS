from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_local_dtn_woodbury import (
    HYBRID_DTN_WOODBURY_MODE_COUNT,
    MUMPS_BLR_V5_H4_PROFILE,
    MUMPS_BLR_V5_H4_1E3_PROFILE,
    HybridLocalDtnWoodburyFixedBudgetKrylovAction,
    HybridLocalDtnWoodburyFixedAction,
    HybridLocalDtnWoodburyOracle,
    ResearchExactSideLuAction,
    mumps_blr_v5_h4_controls,
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


@pytest.mark.parametrize("mode_count", [HYBRID_DTN_WOODBURY_MODE_COUNT, 42])
def test_exact_woodbury_matpython_components_and_lifecycle(mode_count: int):
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    rows = 8
    rng = np.random.default_rng(239)
    base_dense = np.eye(rows, dtype=np.complex128) * (2.0 + 0.2j)
    C_dense = rng.standard_normal((rows, mode_count)) + 1j * rng.standard_normal(
        (rows, mode_count)
    )
    D_dense = rng.standard_normal((mode_count, rows)) + 1j * rng.standard_normal(
        (mode_count, rows)
    )
    H_dense = np.eye(mode_count, dtype=np.complex128) * (3.0 + 0.1j)
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
        assert diagnostics["n_aux"] == mode_count
        assert diagnostics["normal_equations"] is False
        assert diagnostics["K_rank"] == mode_count
        assert np.isfinite(diagnostics["K_condition_number"])
        assert diagnostics["streaming_w_storage"] is False
        assert diagnostics["W_resident"] is True
        assert diagnostics["W_local_nbytes"] == F.getLocalSize()[0] * mode_count * 16
        assert diagnostics["K_nbytes"] == mode_count * mode_count * 16
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


@pytest.mark.parametrize("mode_count", [HYBRID_DTN_WOODBURY_MODE_COUNT, 42])
def test_fixed_woodbury_action_is_one_apply_nonowning_and_fail_closed(mode_count: int):
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    rows = 8
    rng = np.random.default_rng(240)
    base_dense = np.eye(rows, dtype=np.complex128) * (2.0 + 0.2j)
    C_dense = rng.standard_normal((rows, mode_count)) + 1j * rng.standard_normal(
        (rows, mode_count)
    )
    D_dense = rng.standard_normal((mode_count, rows)) + 1j * rng.standard_normal(
        (mode_count, rows)
    )
    H_dense = np.eye(mode_count, dtype=np.complex128) * (3.0 + 0.1j)
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
        assert diagnostics["operator_identity"] == (
            "whole_endcap_ilu0_woodbury_fixed_action"
        )
        assert diagnostics["base_factor_count"] == 1
        assert diagnostics["base_diagnostics"]["identity"] == "tiny_fixed_non_ksp_base"
        assert diagnostics["local_direct_factor_count"] == 0
        assert diagnostics["local_direct_factor_count_owned"] == 0
        assert diagnostics["woodbury"]["K_rank"] == mode_count
        assert np.isfinite(diagnostics["woodbury"]["K_condition_number"])
        assert diagnostics["woodbury"]["K_condition_number"] <= 1.0e10
        assert diagnostics["woodbury"]["arrays_finite"] is True
        assert not hasattr(fixed, "ksp")
        assert fixed.diagnostics["woodbury"]["apply_count"] == 0
        assert base_action.apply_count == mode_count

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
            assert base_action.apply_count == mode_count + 1
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
            assert base_action.apply_count == mode_count + 6
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


def test_two_pass_residual_correction_matches_stationary_formula_and_releases_scratch():
    rows = 6
    mode_count = 1
    base_dense = np.eye(rows, dtype=np.complex128) * 2.0
    zero_c = np.zeros((rows, mode_count), dtype=np.complex128)
    zero_d = np.zeros((mode_count, rows), dtype=np.complex128)
    identity_h = np.eye(mode_count, dtype=np.complex128)
    residual_dense = np.asarray(
        [
            [1.2 + 0.1j, 0.3 - 0.2j, 0, 0, 0, 0],
            [0.1 + 0.4j, 0.9 + 0.2j, 0.2, 0, 0, 0],
            [0, -0.1j, 1.1 - 0.3j, 0.4, 0, 0],
            [0, 0, 0.2 + 0.1j, 0.8 + 0.2j, 0.1, 0],
            [0, 0, 0, 0.2, 1.3 - 0.1j, -0.2j],
            [0, 0, 0, 0, 0.1 + 0.2j, 0.7 + 0.3j],
        ],
        dtype=np.complex128,
    )
    F = _matrix_from_dense(base_dense)
    C = _matrix_from_dense(zero_c)
    D = _matrix_from_dense(zero_d)
    H = _matrix_from_dense(identity_h)
    residual_operator = _python_matrix_from_dense(residual_dense)
    residual_context = residual_operator.getPythonContext()
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    base_action = _FixedBaseAction(_DenseBaseInverse(2.0))
    fixed = HybridLocalDtnWoodburyFixedAction(
        base_action,
        components,
        operator_identity="whole_endcap_ilu1_woodbury_fixed_action",
        ilu_levels=1,
        residual_operator=residual_operator,
        residual_correction_steps=2,
    )
    source_template = F.createVecRight()
    source = _random_vector(source_template, 241)
    source_template.destroy()
    actual = F.createVecLeft()
    expected = F.createVecLeft()
    repeat = F.createVecLeft()
    other_template = F.createVecRight()
    other = _random_vector(other_template, 242)
    other_template.destroy()
    combined = F.createVecRight()
    combined_result = F.createVecLeft()
    source_result = F.createVecLeft()
    other_result = F.createVecLeft()
    try:
        fixed.apply(source, actual)
        start, end = (int(value) for value in source.getOwnershipRange())
        values = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        rhs = np.empty(rows, dtype=np.complex128)
        for first, last, local in MPI.COMM_WORLD.allgather((start, end, values)):
            rhs[first:last] = local
        first_pass = rhs / 2.0
        expected_values = first_pass + (rhs - residual_dense @ first_pass) / 2.0
        expected.getArray()[:] = expected_values[start:end]
        assert _relative_error(actual, expected) <= 1.0e-12
        diagnostics = fixed.diagnostics
        assert diagnostics["operator_identity"].startswith(
            "whole_endcap_ilu1_woodbury_fixed_action"
        )
        assert diagnostics["ilu_levels"] == 1
        assert diagnostics["operator_identity"].endswith("two_pass_residual_correction")
        assert diagnostics["residual_correction_steps"] == 2
        assert diagnostics["correction_operator_matrix_free"] is True
        assert diagnostics["residual_correction_operator_borrowed"] is True
        assert diagnostics["logical_apply_count"] == 1
        assert diagnostics["raw_apply_count"] == 2
        assert diagnostics["woodbury"]["apply_count"] == 2
        assert diagnostics["base_factor_count"] == 1
        assert diagnostics["local_direct_factor_count"] == 0
        assert diagnostics["nested_ksp_created"] is False

        fixed.apply(source, repeat)
        assert _relative_error(actual, repeat) <= 1.0e-13
        assert _global_vec_digest(actual) == _global_vec_digest(repeat)
        alpha = PETSc.ScalarType(0.7 - 0.2j)
        beta = PETSc.ScalarType(-0.3 + 0.4j)
        source.copy(combined)
        combined.scale(alpha)
        combined.axpy(beta, other)
        fixed.apply(combined, combined_result)
        fixed.apply(source, source_result)
        fixed.apply(other, other_result)
        source_result.scale(alpha)
        other_result.scale(beta)
        source_result.axpy(PETSc.ScalarType(1.0), other_result)
        assert _relative_error(combined_result, source_result) <= 1.0e-12
    finally:
        other_result.destroy()
        source_result.destroy()
        combined_result.destroy()
        combined.destroy()
        other.destroy()
        repeat.destroy()
        expected.destroy()
        actual.destroy()
        source.destroy()
        fixed.destroy()
        assert fixed.diagnostics["destroyed"] is True
        assert fixed.diagnostics["owned_action_data_released"] is True
        assert residual_context.destroyed is False
        residual_operator.destroy()
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()
        assert residual_context.destroyed is True


@pytest.mark.parametrize("passes", [1, 2, 4, 8])
def test_fixed_action_supports_reviewed_correction_passes(passes: int) -> None:
    rows = 6
    base_dense = np.eye(rows, dtype=np.complex128) * 2.0
    residual_dense = np.eye(rows, dtype=np.complex128) * 1.2
    F = _matrix_from_dense(base_dense)
    C = _matrix_from_dense(np.zeros((rows, 1), dtype=np.complex128))
    D = _matrix_from_dense(np.zeros((1, rows), dtype=np.complex128))
    H = _matrix_from_dense(np.eye(1, dtype=np.complex128))
    residual_operator = (
        _python_matrix_from_dense(residual_dense) if passes > 1 else None
    )
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    fixed = HybridLocalDtnWoodburyFixedAction(
        _FixedBaseAction(_DenseBaseInverse(2.0)),
        components,
        residual_operator=residual_operator,
        residual_correction_steps=passes,
    )
    source_template = F.createVecRight()
    source = _random_vector(source_template, 517 + passes)
    source_template.destroy()
    actual = F.createVecLeft()
    repeat = F.createVecLeft()
    try:
        fixed.apply(source, actual)
        start, end = (int(value) for value in source.getOwnershipRange())
        local = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        rhs = np.empty(rows, dtype=np.complex128)
        for first, last, packet in MPI.COMM_WORLD.allgather((start, end, local)):
            rhs[first:last] = packet
        expected = rhs / 2.0
        for _ in range(passes - 1):
            expected = expected + (rhs - residual_dense @ expected) / 2.0
        expected_vec = F.createVecLeft()
        expected_vec.getArray()[:] = expected[start:end]
        try:
            assert _relative_error(actual, expected_vec) <= 1.0e-12
        finally:
            expected_vec.destroy()
        diagnostics = fixed.diagnostics
        assert diagnostics["residual_correction_steps"] == passes
        assert diagnostics["logical_apply_count"] == 1
        assert diagnostics["raw_apply_count"] == passes
        assert diagnostics["woodbury"]["apply_count"] == passes
        fixed.apply(source, repeat)
        assert _global_vec_digest(actual) == _global_vec_digest(repeat)
    finally:
        repeat.destroy()
        actual.destroy()
        source.destroy()
        fixed.destroy()
        if residual_operator is not None:
            residual_operator.destroy()
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()


@pytest.mark.parametrize("budget", [8, 16, 32])
def test_fixed_budget_krylov_action_is_deterministic_and_borrowing(budget: int):
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    rows = 6
    operator_dense = np.asarray(
        [
            [2.0, 0.3, 0.0, 0.0, 0.0, 0.0],
            [0.1, 2.4, 0.2, 0.0, 0.0, 0.0],
            [0.0, 0.2, 2.1, 0.3, 0.0, 0.0],
            [0.0, 0.0, 0.1, 2.6, 0.2, 0.0],
            [0.0, 0.0, 0.0, 0.2, 2.2, 0.3],
            [0.0, 0.0, 0.0, 0.0, 0.1, 2.5],
        ],
        dtype=np.complex128,
    )
    operator = _python_matrix_from_dense(operator_dense)
    operator_context = operator.getPythonContext()
    C = _matrix_from_dense(np.zeros((rows, 1), dtype=np.complex128))
    D = _matrix_from_dense(np.zeros((1, rows), dtype=np.complex128))
    H = _matrix_from_dense(np.eye(1, dtype=np.complex128))
    components = SimpleNamespace(F=operator, C=C, D=D, H=H)
    fixed = HybridLocalDtnWoodburyFixedAction(
        _FixedBaseAction(_DenseBaseInverse(2.0)), components
    )
    action = HybridLocalDtnWoodburyFixedBudgetKrylovAction(
        operator, fixed, budget=budget
    )
    template = operator.createVecRight()
    source = _random_vector(template, 239 + budget)
    template.destroy()
    first = operator.createVecLeft()
    repeat = operator.createVecLeft()
    applied = operator.createVecLeft()
    residual = operator.createVecLeft()
    try:
        first.set(17.0)
        action.apply(source, first)
        operator.mult(first, applied)
        source.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), applied)
        initial_norm = float(source.norm())
        assert float(residual.norm()) / initial_norm < 1.0e-10
        first_digest = _global_vec_digest(first)

        repeat.set(-23.0)
        action.apply(source, repeat)
        assert _global_vec_digest(repeat) == first_digest
        diagnostics = action.diagnostics
        assert diagnostics["requested_budget"] == budget
        assert diagnostics["restart"] == budget
        assert diagnostics["pc_side"] == "right"
        assert diagnostics["zero_initial_guess"] is True
        assert diagnostics["right_preconditioner_borrowed"] is True
        assert diagnostics["direct_factor_count"] == 0
        assert diagnostics["global_hybrid_direct_factor_count"] == 0
        assert diagnostics["apply_count"] == 2
        assert 0 < diagnostics["last_inner_iterations"] <= budget
        assert diagnostics["last_converged_reason"] != 0
    finally:
        residual.destroy()
        applied.destroy()
        repeat.destroy()
        first.destroy()
        source.destroy()
        action.destroy()
        assert action.diagnostics["inner_ksp_destroyed"] is True
        assert action.diagnostics["pc_context_destroyed"] is True
        assert action.diagnostics["destroyed"] is True
        assert operator_context.destroyed is False
        borrowed_target = operator.createVecLeft()
        borrowed_template = operator.createVecRight()
        borrowed_source = _random_vector(borrowed_template, 240 + budget)
        borrowed_template.destroy()
        try:
            fixed.apply(borrowed_source, borrowed_target)
        finally:
            borrowed_source.destroy()
            borrowed_target.destroy()
        fixed.destroy()
        operator.destroy()
        assert operator_context.destroyed is True
        C.destroy()
        D.destroy()
        H.destroy()


def test_fixed_budget_zero_rhs_exact_and_nonzero_complex_is_finite():
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2, 4):
        return
    operator_dense = np.asarray(
        [[2.0 + 0.1j, 0.2 - 0.05j], [0.1 + 0.02j, 1.8 - 0.2j]],
        dtype=np.complex128,
    )
    operator = _python_matrix_from_dense(operator_dense)
    operator_context = operator.getPythonContext()
    rows = operator_dense.shape[0]
    C = _matrix_from_dense(np.zeros((rows, 1), dtype=np.complex128))
    D = _matrix_from_dense(np.zeros((1, rows), dtype=np.complex128))
    H = _matrix_from_dense(np.eye(1, dtype=np.complex128))
    components = SimpleNamespace(F=operator, C=C, D=D, H=H)
    fixed = HybridLocalDtnWoodburyFixedAction(
        _FixedBaseAction(_DenseBaseInverse(2.0)), components
    )
    action = HybridLocalDtnWoodburyFixedBudgetKrylovAction(operator, fixed, budget=8)
    zero = operator.createVecRight()
    zero.set(0.0)
    zero_target = operator.createVecLeft()
    source = _vector_from_values(
        operator, np.asarray([1.0 + 0.4j, -0.3 + 0.2j], dtype=np.complex128)
    )
    source_digest = _global_vec_digest(source)
    target = operator.createVecLeft()
    try:
        zero_target.set(13.0)
        action.apply(zero, zero_target)
        zero_diagnostics = action.diagnostics
        assert float(zero_target.norm()) == 0.0
        assert zero_diagnostics["last_inner_iterations"] == 0
        assert zero_diagnostics["last_converged_reason"] is None
        assert zero_diagnostics["last_converged_reason_label"] == "zero_rhs_exact"
        assert zero_diagnostics["zero_rhs_exact"] is True

        action.apply(source, target)
        diagnostics = action.diagnostics
        assert _global_vec_digest(source) == source_digest
        assert np.isfinite(target.norm())
        assert 0 < diagnostics["last_inner_iterations"] <= 8
        assert diagnostics["last_converged_reason_label"] == "petsc_ksp"
        assert diagnostics["zero_rhs_exact"] is False
    finally:
        target.destroy()
        source.destroy()
        zero_target.destroy()
        zero.destroy()
        action.destroy()
        fixed.destroy()
        assert operator_context.destroyed is False
        operator.destroy()
        C.destroy()
        D.destroy()
        H.destroy()
        assert operator_context.destroyed is True


@pytest.mark.parametrize("qualified", [False, True], ids=["historical", "qualified"])
def test_research_exact_side_action_matches_explicit_schur_and_releases_factor(
    qualified,
):
    rows = 4
    modes = 2
    rng = np.random.default_rng(283)
    F_dense = np.asarray(
        [
            [3.0 + 0.2j, 0.1, 0.0, 0.0],
            [0.0, 2.7 - 0.1j, 0.2, 0.0],
            [0.0, 0.0, 2.4 + 0.3j, 0.1],
            [0.1, 0.0, 0.0, 3.2 - 0.2j],
        ],
        dtype=np.complex128,
    )
    C_dense = (
        rng.standard_normal((rows, modes))
        + 1j * rng.standard_normal((rows, modes)) * 0.02
    )
    D_dense = (
        rng.standard_normal((modes, rows))
        + 1j * rng.standard_normal((modes, rows)) * 0.02
    )
    H_dense = np.diag(np.asarray([2.0 + 0.1j, 2.7 - 0.2j]))
    F = _matrix_from_dense(F_dense)
    C = _matrix_from_dense(C_dense)
    D = _matrix_from_dense(D_dense)
    H = _matrix_from_dense(H_dense)
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    action_kwargs = (
        {
            "qualification_scope": "task039_v3_p6h5_m480_1deg_s",
            "explicit_opt_in": True,
        }
        if qualified
        else {}
    )
    action = ResearchExactSideLuAction(
        F, components, factor_solver_type=None, **action_kwargs
    )
    source_template = F.createVecRight()
    source = _random_vector(source_template, 284)
    source_template.destroy()
    actual = F.createVecLeft()
    start, end = (int(value) for value in source.getOwnershipRange())
    rhs = np.empty(rows, dtype=np.complex128)
    local_rhs = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
    for first, last, values in MPI.COMM_WORLD.allgather((start, end, local_rhs)):
        rhs[first:last] = values
    expected = np.linalg.solve(
        F_dense - C_dense @ np.linalg.solve(H_dense, D_dense),
        rhs,
    )
    try:
        expected_vec = _vector_from_values(F, expected)
        action.apply(source, actual)
        try:
            assert _relative_error(actual, expected_vec) <= 1.0e-11
        finally:
            expected_vec.destroy()
        diagnostics = action.diagnostics
        assert diagnostics["research_only"] is (not qualified)
        assert diagnostics["factor_only_storage"] is False
        assert diagnostics["woodbury"]["compact_storage"] is False
        if qualified:
            assert diagnostics["case_qualification_opt_in"] is True
            assert diagnostics["general_production"] is False
            assert diagnostics["ordinary_default"] is False
            assert diagnostics["nested_iterative_ksp_count"] == 0
            assert diagnostics["local_direct_preonly_ksp_count"] == 1
        else:
            assert "case_qualification_opt_in" not in diagnostics
        assert diagnostics["direct_factor_count"] == 1
        assert diagnostics["direct_factor_count_owned"] == 1
        assert diagnostics["ilu_factor_count"] == 0
        assert diagnostics["global_hybrid_direct_factor_count"] == 0
        assert diagnostics["woodbury"]["K_rank"] == modes
    finally:
        actual.destroy()
        source.destroy()
        action.destroy()
        assert action.diagnostics["destroyed"] is True
        assert action.diagnostics["woodbury"]["K_shape"] is None
        assert action.diagnostics["woodbury"]["LU_shape"] is None
        assert F.getSize() == (rows, rows)
        C.destroy()
        D.destroy()
        H.destroy()
        F.destroy()


@pytest.mark.parametrize(
    "compressed_factor_profile",
    [None, MUMPS_BLR_V5_H4_PROFILE, MUMPS_BLR_V5_H4_1E3_PROFILE],
)
def test_research_exact_side_factor_only_mumps_releases_borrowed_components(
    compressed_factor_profile,
):
    comm = MPI.COMM_WORLD
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        return
    rows = 4
    diagonal = np.asarray(
        [2.0 + 0.1j, 2.4 - 0.2j, 2.8 + 0.15j, 3.1 - 0.05j],
        dtype=np.complex128,
    )
    F_dense = np.diag(diagonal)
    C_dense = np.asarray(
        [[0.10 + 0.02j], [0.03 - 0.01j], [0.02 + 0.01j], [-0.01 + 0.04j]],
        dtype=np.complex128,
    )
    D_dense = np.asarray(
        [[0.04 - 0.01j, 0.01 + 0.02j, -0.02 + 0.01j, 0.03 - 0.02j]],
        dtype=np.complex128,
    )
    H_dense = np.asarray([[2.0 + 0.1j]], dtype=np.complex128)
    F = _matrix_from_dense(F_dense)
    C = _matrix_from_dense(C_dense)
    D = _matrix_from_dense(D_dense)
    H = _matrix_from_dense(H_dense)
    effective_dense = F_dense - C_dense @ np.linalg.solve(H_dense, D_dense)
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    action = None
    components_released = False
    source = target = repeat = scaled = scaled_target = reference = None
    factor_reference = history_source = history_target = None
    try:
        action = ResearchExactSideLuAction(
            F,
            components,
            factor_solver_type="mumps",
            qualification_scope="task039_v5_factor_only_test",
            explicit_opt_in=True,
            factor_only_storage=True,
            compressed_factor_profile=compressed_factor_profile,
        )
        diagnostics = action.diagnostics
        assert diagnostics["factor_only_storage"] is True
        assert diagnostics["ksp_destroyed"] is True
        assert diagnostics["factor_matrix_owned"] is True
        assert diagnostics["woodbury"]["K_released"] is True
        assert diagnostics["woodbury"]["F_C_H_references_released"] is True
        assert diagnostics["woodbury"]["F_C_H_matrices_released"] is False
        if compressed_factor_profile is None:
            assert "mumps_controls_requested" not in diagnostics
            assert diagnostics["direct_factor_count"] == 1
            assert action.factor.diagnostics["exact_factor_count"] == 1
            assert action.factor.diagnostics["compressed_factor_count"] == 0
            factor_diagnostics = action.factor.diagnostics
            assert factor_diagnostics["mumps_icntl_14_requested_percent"] == 100
            assert factor_diagnostics["mumps_icntl_14_observed_percent"] == 100
            assert factor_diagnostics["mumps_workspace_relaxation_verified"] is True
            factor_inventory = factor_diagnostics["factor_inventory"]
            assert factor_inventory["mumps_api_available"] is True
            assert factor_diagnostics["mumps_infog_1"] >= 0
            assert isinstance(factor_diagnostics["mumps_infog_2"], int)
            assert factor_inventory["mumps_raw_infog"]["1"] >= 0
            assert factor_inventory["mumps_raw_infog"]["2"] == (
                factor_diagnostics["mumps_infog_2"]
            )
        else:
            assert diagnostics["operator_identity"] == (
                "research_mumps_blr_compressed_side_lu_woodbury"
            )
            assert diagnostics["exact_factor_count"] == 0
            assert diagnostics["compressed_factor_count"] == 1
            assert diagnostics["direct_factor_count"] == 1
            assert diagnostics["direct_factor_count_owned"] == 1
            assert diagnostics["global_direct_factor_count"] == 0
            assert diagnostics["research_only"] is True
            assert diagnostics["component_candidate"] is True
            assert diagnostics["general_production"] is False
            assert diagnostics["case_qualification_opt_in"] is False
            assert diagnostics["mumps_controls_verified"] is True
            assert diagnostics["mumps_controls_observed"] == mumps_blr_v5_h4_controls(
                compressed_factor_profile
            )
        F.destroy()
        C.destroy()
        H.destroy()
        components_released = True
        action.woodbury.mark_borrowed_matrices_released()
        source = action.operator.createVecRight()
        target = action.operator.createVecLeft()
        repeat = action.operator.createVecLeft()
        source.set(PETSc.ScalarType(0.75 - 0.2j))
        reference = action.operator.createVecLeft()
        first, last = (int(value) for value in source.getOwnershipRange())
        rhs = np.empty(rows, dtype=np.complex128)
        local_rhs = np.asarray(
            source.getArray(readonly=True), dtype=np.complex128
        ).copy()
        for begin, end, values in MPI.COMM_WORLD.allgather((first, last, local_rhs)):
            rhs[begin:end] = values
        factor_reference = action.operator.createVecLeft()
        factor_reference_values = np.linalg.solve(F_dense, rhs)
        factor_reference.getArray()[:] = factor_reference_values[first:last]

        target.set(PETSc.ScalarType(13.0 - 7.0j))
        action.factor.solve(source, target)
        first_factor_digest = _global_vec_digest(target)
        assert _relative_error(target, factor_reference) <= 1.0e-13

        history_source = action.operator.createVecRight()
        history_target = action.operator.createVecLeft()
        history_source.set(PETSc.ScalarType(-0.35 + 0.45j))
        history_target.set(PETSc.ScalarType(19.0 + 23.0j))
        action.apply(history_source, history_target)

        repeat.set(PETSc.ScalarType(-17.0 + 5.0j))
        action.factor.solve(source, repeat)
        assert _relative_error(repeat, target) <= 1.0e-13
        assert _global_vec_digest(repeat) == first_factor_digest
        repeat_local = np.asarray(
            repeat.getArray(readonly=True), dtype=np.complex128
        ).copy()
        repeat_values = np.empty(rows, dtype=np.complex128)
        for begin, end, values in comm.allgather((first, last, repeat_local)):
            repeat_values[begin:end] = values
        factor_residual = F_dense @ repeat_values - rhs
        assert np.linalg.norm(factor_residual) / np.linalg.norm(rhs) <= 1.0e-13

        reference_values = np.linalg.solve(effective_dense, rhs)
        reference.getArray()[:] = reference_values[first:last]
        action.apply(source, target)
        assert _relative_error(target, reference) <= 1.0e-12
        action.apply(source, repeat)
        assert _relative_error(repeat, target) <= 1.0e-12
        scaled = source.duplicate()
        source.copy(scaled)
        scaled.scale(PETSc.ScalarType(2.0))
        scaled_target = action.operator.createVecLeft()
        action.apply(scaled, scaled_target)
        expected_scaled = target.duplicate()
        target.copy(expected_scaled)
        expected_scaled.scale(PETSc.ScalarType(2.0))
        try:
            assert _relative_error(scaled_target, expected_scaled) <= 1.0e-12
        finally:
            expected_scaled.destroy()
        local_target = np.asarray(
            target.getArray(readonly=True), dtype=np.complex128
        ).copy()
        target_values = np.empty(rows, dtype=np.complex128)
        for begin, end, values in MPI.COMM_WORLD.allgather((first, last, local_target)):
            target_values[begin:end] = values
        residual = effective_dense @ target_values - rhs
        assert np.linalg.norm(residual) / np.linalg.norm(rhs) <= 1.0e-12
    finally:
        for vector in (
            reference,
            factor_reference,
            history_target,
            history_source,
            scaled_target,
            scaled,
            repeat,
            target,
            source,
        ):
            if vector is not None:
                vector.destroy()
        if action is not None:
            action.destroy()
            assert action.operator is None
            assert action.components is None
            assert action.factor.diagnostics["factor_matrix_alive"] is False
            assert action.diagnostics["direct_factor_count"] == 0
            if compressed_factor_profile is not None:
                assert action.diagnostics["compressed_factor_count"] == 0
        D.destroy()
        if not components_released:
            F.destroy()
            C.destroy()
            H.destroy()


def test_research_blr_profile_rejects_non_mumps_factor_solver():
    F = _matrix_from_dense(np.eye(2, dtype=np.complex128))
    C = _matrix_from_dense(np.ones((2, 1), dtype=np.complex128) * 0.02)
    D = _matrix_from_dense(np.ones((1, 2), dtype=np.complex128) * 0.03)
    H = _matrix_from_dense(np.eye(1, dtype=np.complex128) * 2.0)
    components = SimpleNamespace(F=F, C=C, D=D, H=H)
    try:
        with pytest.raises(ValueError, match="factor_solver_type='mumps'"):
            ResearchExactSideLuAction(
                F,
                components,
                factor_solver_type=None,
                explicit_opt_in=True,
                factor_only_storage=True,
                compressed_factor_profile=MUMPS_BLR_V5_H4_PROFILE,
            )
    finally:
        F.destroy()
        C.destroy()
        D.destroy()
        H.destroy()


def test_research_blr_profile_set_is_frozen_and_unknown_fails_closed():
    assert mumps_blr_v5_h4_controls(MUMPS_BLR_V5_H4_PROFILE) == {
        "icntl_35": 1,
        "cntl_7": 1.0e-5,
        "icntl_14": 80,
    }
    assert mumps_blr_v5_h4_controls(MUMPS_BLR_V5_H4_1E3_PROFILE) == {
        "icntl_35": 1,
        "cntl_7": 1.0e-3,
        "icntl_14": 80,
    }
    with pytest.raises(ValueError, match="Unsupported compressed factor profile"):
        mumps_blr_v5_h4_controls("mumps_blr_v5_h4_unknown")


@pytest.mark.parametrize("batch_size", [8, 16, 32])
def test_research_exact_side_streaming_w_matches_retained_factor_only(batch_size):
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        return
    rows = 8
    modes = 32
    rng = np.random.default_rng(2395)
    F_dense = np.diag(np.asarray(2.0 + 0.1j * np.arange(rows), dtype=np.complex128))
    C_dense = 0.02 * (
        rng.standard_normal((rows, modes)) + 1j * rng.standard_normal((rows, modes))
    )
    D_dense = 0.02 * (
        rng.standard_normal((modes, rows)) + 1j * rng.standard_normal((modes, rows))
    )
    H_dense = np.diag(np.asarray(3.0 + 0.03j * np.arange(modes), dtype=np.complex128))
    effective_dense = F_dense - C_dense @ np.linalg.solve(H_dense, D_dense)

    def build(streaming_batch: int | None):
        F = _matrix_from_dense(F_dense)
        C = _matrix_from_dense(C_dense)
        D = _matrix_from_dense(D_dense)
        H = _matrix_from_dense(H_dense)
        components = SimpleNamespace(F=F, C=C, D=D, H=H)
        action = ResearchExactSideLuAction(
            F,
            components,
            factor_solver_type="mumps",
            qualification_scope="task039_v5_streaming_w_test",
            explicit_opt_in=True,
            factor_only_storage=True,
            streaming_w_batch_size=streaming_batch,
        )
        return action, components, (F, C, D, H)

    retained, retained_components, retained_matrices = build(None)
    streaming, streaming_components, streaming_matrices = build(batch_size)
    retained_F, retained_C, retained_D, retained_H = retained_matrices
    streaming_F, _streaming_C, streaming_D, streaming_H = streaming_matrices
    streaming_local_rows = int(streaming_F.getLocalSize()[0])
    try:
        retained_F.destroy()
        retained_H.destroy()
        streaming_F.destroy()
        streaming_H.destroy()
        streaming.woodbury.mark_borrowed_matrices_released()
        retained_diagnostics = retained.diagnostics["woodbury"]
        streaming_diagnostics = streaming.diagnostics["woodbury"]
        assert retained_diagnostics["streaming_w_storage"] is False
        assert retained_diagnostics["W_resident"] is True
        assert streaming_diagnostics["streaming_w_storage"] is True
        assert streaming_diagnostics["K_shape"] == retained_diagnostics["K_shape"]
        assert streaming_diagnostics["K_nbytes"] == retained_diagnostics["K_nbytes"]
        assert streaming_diagnostics["LU_shape"] == retained_diagnostics["LU_shape"]
        assert (
            streaming_diagnostics["LU_array_nbytes"]
            == retained_diagnostics["LU_array_nbytes"]
        )
        assert np.isclose(
            streaming_diagnostics["K_condition_number"],
            retained_diagnostics["K_condition_number"],
        )
        assert streaming_diagnostics["streaming_w_batch_size"] == batch_size
        assert streaming_diagnostics["W_resident"] is False
        assert streaming_diagnostics["W_local_nbytes"] in (None, 0)
        assert streaming_diagnostics["setup_factor_solve_count"] == modes
        assert streaming_diagnostics["setup_d_apply_count"] == modes
        assert streaming_diagnostics["setup_batch_count"] == (
            (modes + batch_size - 1) // batch_size
        )
        assert streaming_diagnostics["streaming_w_batch_peak_bytes"] == (
            streaming_local_rows * min(batch_size, modes) * 16
        )
        assert streaming_diagnostics["streaming_w_batch_local_peak_bytes"] == (
            streaming_local_rows * min(batch_size, modes) * 16
        )
        assert (
            streaming_diagnostics["streaming_w_batch_peak_scope"]
            == "max_rank_local_dense_response_buffer"
        )
        assert streaming_components.C is None
        assert streaming_diagnostics["C_action_owned"] is True
        assert streaming_diagnostics["C_action_resident"] is True
        assert streaming_diagnostics["F_H_matrices_released"] is True
        assert streaming_diagnostics["F_C_H_matrices_released"] is False

        for seed in (1, 2):
            rhs = rng.standard_normal(rows) + 1j * rng.standard_normal(rows)
            source_values = np.asarray(rhs, dtype=np.complex128)
            source_r = _vector_from_values(retained.operator, source_values)
            source_s = _vector_from_values(streaming.operator, source_values)
            target_r = retained.operator.createVecLeft()
            target_s = streaming.operator.createVecLeft()
            expected = _vector_from_values(
                retained.operator,
                np.linalg.solve(effective_dense, source_values),
            )
            try:
                retained.apply(source_r, target_r)
                streaming.apply(source_s, target_s)
                assert _relative_error(target_r, expected) <= 1.0e-10
                assert _relative_error(target_s, expected) <= 1.0e-10
                assert _relative_error(target_s, target_r) <= 1.0e-10
                doubled_source = source_s.duplicate()
                source_s.copy(doubled_source)
                doubled_source.scale(PETSc.ScalarType(2.0))
                doubled_target = streaming.operator.createVecLeft()
                expected_doubled = target_s.duplicate()
                target_s.copy(expected_doubled)
                expected_doubled.scale(PETSc.ScalarType(2.0))
                try:
                    streaming.apply(doubled_source, doubled_target)
                    assert _relative_error(doubled_target, expected_doubled) <= 1.0e-10
                finally:
                    expected_doubled.destroy()
                    doubled_target.destroy()
                    doubled_source.destroy()
            finally:
                expected.destroy()
                target_s.destroy()
                target_r.destroy()
                source_s.destroy()
                source_r.destroy()
        assert streaming_diagnostics["apply_base_solve_count_per_apply"] == 2
        assert streaming.diagnostics["woodbury"]["apply_base_solve_count"] == 8
        assert streaming.diagnostics["woodbury"]["apply_D_count"] == 4
        assert streaming.diagnostics["woodbury"]["apply_C_count"] == 4
    finally:
        streaming.destroy()
        retained.destroy()
        assert streaming.diagnostics["woodbury"]["C_action_released"] is True
        assert streaming.diagnostics["woodbury"]["F_C_H_matrices_released"] is True
        assert (
            streaming.diagnostics["woodbury"]["borrowed_component_handles_released"]
            is True
        )
        retained_C.destroy()
        retained_D.destroy()
        retained_components.C = None
        retained_components.D = None
        streaming_D.destroy()
        streaming_components.D = None
        streaming_components.H = None
        streaming_components.F = None


def _vector_from_values(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecLeft()
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = values[first:last]
    return vector


def test_v5_streaming_component_fixture_is_deterministic():
    from benchmarks.task039_v5_streaming_woodbury_component import (
        _batch_size,
        _synthetic_fixture,
    )

    first = _synthetic_fixture()
    second = _synthetic_fixture()
    assert _batch_size("retained") is None
    assert [_batch_size(value) for value in ("8", "16", "32")] == [8, 16, 32]
    for name in ("F", "C", "D", "H", "rhs"):
        np.testing.assert_array_equal(first[name], second[name])
