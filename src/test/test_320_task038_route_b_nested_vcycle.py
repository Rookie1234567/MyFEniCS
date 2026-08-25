"""Focused contracts for the fixed Route-B nested V-cycle core."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.fullspace_lor_hx_root_cause import M0_DIRECT_BACKEND
from src.solvers.fullspace_lor_nested_vcycle import RouteBNestedVcycle


def _identity(size: int) -> PETSc.Mat:
    indptr = np.arange(size + 1, dtype=np.int32)
    indices = np.arange(size, dtype=np.int32)
    values = np.ones(size, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(
        [size, size], csr=(indptr, indices, values), comm=PETSc.COMM_SELF
    )
    matrix.assemble()
    return matrix


class _Level:
    def __init__(self, degree: int, matrix: PETSc.Mat) -> None:
        self.degree = degree
        self.matrix = matrix


class _Transfer:
    def __init__(self, fine: _Level, coarse: _Level, values: np.ndarray) -> None:
        self.fine = fine
        self.coarse = coarse
        self.values = np.asarray(values, dtype=np.complex128)
        self.primal_apply_count = 0
        self.adjoint_apply_count = 0
        self.primal_into_apply_count = 0
        self.adjoint_into_apply_count = 0
        self.last_primal_target = None
        self.last_adjoint_target = None

    def apply_primal(self, source):
        raise AssertionError("allocating primal transfer API must not be used")

    def apply_adjoint(self, source):
        raise AssertionError("allocating adjoint transfer API must not be used")

    def apply_primal_into(self, source, target):
        target.array[:] = self.values @ np.asarray(source.array)
        self.primal_apply_count += 1
        self.primal_into_apply_count += 1
        self.last_primal_target = target
        return target

    def apply_adjoint_into(self, source, target):
        target.array[:] = self.values.conj().T @ np.asarray(source.array)
        self.adjoint_apply_count += 1
        self.adjoint_into_apply_count += 1
        self.last_adjoint_target = target
        return target


class _Extension:
    def __init__(self, level6: _Level, level2: _Level, level1: _Level) -> None:
        self.levels = {6: level6, 2: level2, 1: level1}
        self.transfers = {
            (6, 2): _Transfer(level6, level2, np.asarray(
                [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
                dtype=np.complex128,
            )),
            (2, 1): _Transfer(level2, level1, np.asarray(
                [[1, 0], [0, 1], [1, 1]], dtype=np.complex128
            )),
        }
        self.destroy_count = 0

    def apply_primal(self, pair, source):
        raise AssertionError("allocating extension API must not be used")

    def apply_adjoint(self, pair, source):
        raise AssertionError("allocating extension API must not be used")

    def apply_primal_into(self, pair, source, target):
        return self.transfers[tuple(pair)].apply_primal_into(source, target)

    def apply_adjoint_into(self, pair, source, target):
        return self.transfers[tuple(pair)].apply_adjoint_into(source, target)

    def destroy(self):
        self.destroy_count += 1


class _Foundation:
    def __init__(self, low_matrix: PETSc.Mat) -> None:
        self.low_matrix = low_matrix
        self.high_primal_source = low_matrix.createVecRight()
        self.restrict_count = 0
        self.lift_count = 0
        self.destroy_count = 0

    def restrict_into(self, source, target):
        source.copy(target)
        self.restrict_count += 1

    def lift_into(self, source, target):
        source.copy(target)
        self.lift_count += 1

    def destroy(self):
        self.destroy_count += 1


@pytest.fixture
def vcycle_bundle():
    matrices = [_identity(size) for size in (4, 3, 2)]
    levels = [_Level(degree, matrix) for degree, matrix in zip((6, 2, 1), matrices)]
    foundation = _Foundation(matrices[0])
    extension = _Extension(*levels)
    core = RouteBNestedVcycle(foundation, extension)
    try:
        yield core, foundation, extension, matrices
    finally:
        if not core._destroyed:
            core.destroy()
        foundation.high_primal_source.destroy()
        for matrix in matrices:
            matrix.destroy()


def _make_rhs(matrix: PETSc.Mat, offset: float):
    rhs = matrix.createVecRight()
    rhs.array[:] = np.arange(rhs.getLocalSize(), dtype=np.float64) + offset + 1j * (offset + 0.25)
    return rhs


def _relative(left, right) -> float:
    delta = left.copy()
    delta.axpy(-1.0, right)
    result = float(delta.norm() / max(right.norm(), np.finfo(float).tiny))
    delta.destroy()
    return result


def test_fixed_route_b_sequence_audit_and_work_reuse(vcycle_bundle) -> None:
    core, foundation, extension, _matrices = vcycle_bundle
    rhs = _make_rhs(core.level6.matrix, 0.75)
    before = rhs.array.copy()
    work_ids = tuple(id(value) for value in core.work_vectors)
    output = core.apply(rhs)
    facts = dict(core.last_apply_facts)
    try:
        assert facts["order"] == (
            "level6_pre", "p62_adjoint", "level2_pre", "p21_adjoint",
            "level1_exact_solve", "p21_primal", "level2_post", "p62_primal",
            "level6_post",
        )
        assert all(facts[key] == 1 for key in (
            "level6_pre_count", "level6_post_count", "level2_pre_count",
            "level2_post_count", "transfer_62_primal_count",
            "transfer_62_adjoint_count", "transfer_21_primal_count",
            "transfer_21_adjoint_count",
        ))
        assert facts["p1_solve_count"] == 1
        assert facts["p1_solver_backend"] == M0_DIRECT_BACKEND
        assert facts["p1_relative_residual"] <= 1.0e-11
        assert facts["output_finite"] is True
        assert np.array_equal(rhs.array, before)
        assert tuple(id(value) for value in core.work_vectors) == work_ids
        assert foundation.restrict_count == 1 and foundation.lift_count == 1
        assert extension.transfers[(6, 2)].adjoint_apply_count == 1
        assert extension.transfers[(6, 2)].primal_apply_count == 1
        assert extension.transfers[(2, 1)].adjoint_apply_count == 1
        assert extension.transfers[(2, 1)].primal_apply_count == 1
        assert extension.transfers[(6, 2)].adjoint_into_apply_count == 1
        assert extension.transfers[(6, 2)].primal_into_apply_count == 1
        assert extension.transfers[(2, 1)].adjoint_into_apply_count == 1
        assert extension.transfers[(2, 1)].primal_into_apply_count == 1
        assert extension.transfers[(6, 2)].last_adjoint_target is core._rhs2
        assert extension.transfers[(2, 1)].last_adjoint_target is core._rhs1
        assert extension.transfers[(2, 1)].last_primal_target is core._correction2
        assert extension.transfers[(6, 2)].last_primal_target is core._z6
        assert output.getSize() == foundation.high_primal_source.getSize()
    finally:
        rhs.destroy()
        output.destroy()


def test_fixed_route_b_linearity_repeat_and_forbidden_audit(vcycle_bundle) -> None:
    core, _foundation, _extension, _matrices = vcycle_bundle
    rhs1 = _make_rhs(core.level6.matrix, 1.25)
    rhs2 = _make_rhs(core.level6.matrix, 2.5)
    before1, before2 = rhs1.array.copy(), rhs2.array.copy()
    outputs = []
    try:
        out1 = core.apply(rhs1)
        out2 = core.apply(rhs2)
        outputs.extend((out1, out2))
        combo = rhs1.copy()
        combo.scale(0.37 + 0.19j)
        combo.axpy(-0.23 + 0.41j, rhs2)
        out_combo = core.apply(combo)
        outputs.extend((combo, out_combo))
        repeated = core.apply(rhs1)
        outputs.append(repeated)
        expected = out1.copy()
        expected.scale(0.37 + 0.19j)
        expected.axpy(-0.23 + 0.41j, out2)
        outputs.append(expected)
        assert _relative(out_combo, expected) <= 1.0e-12
        assert _relative(repeated, out1) <= 1.0e-13
        assert np.array_equal(rhs1.array, before1)
        assert np.array_equal(rhs2.array, before2)
        assert all(np.all(np.isfinite(np.asarray(value.array))) for value in outputs)
        assert all(
            core.last_apply_facts[f"transfer_{pair}_{kind}_total"] == 4
            for pair in ("6_2", "2_1")
            for kind in ("primal", "adjoint")
        )
        assert core.audit["levels"] == (6, 2, 1)
        assert core.audit["pairs"] == ((6, 2), (2, 1))
        assert core.audit["chebyshev_degree"] == 3
        assert core.audit["power_steps"] == 10
        assert core.audit["p1_exact_factor"] is True
        assert core.audit["outer_ksp_created"] is False
        assert core.audit["p1_factor_ksp_created"] is True
        assert core.audit["p6_exact_factor"] is False
        assert core.audit["level2_exact_factor"] is False
        assert core.audit["global_direct_coarse"] is False
        assert core.audit["global_high_order_aij"] is False
        assert core.audit["global_transfer_matrix"] is False
        assert core.audit["numeric_allgather"] is False
        assert core.audit["hx_hierarchy_built"] is False
        assert core.audit["pcgamg_hierarchy_built"] is False
    finally:
        rhs1.destroy()
        rhs2.destroy()
        for value in outputs:
            value.destroy()


def test_destroy_is_idempotent_and_preserves_caller_foundation(vcycle_bundle) -> None:
    core, foundation, extension, _matrices = vcycle_bundle
    core.destroy()
    core.destroy()
    assert core._destroyed is True
    assert extension.destroy_count == 1
    assert foundation.destroy_count == 0
    assert foundation.low_matrix.handle != 0
    assert not hasattr(foundation, "high_work_output")
    with pytest.raises(RuntimeError, match="destroyed"):
        core.apply(foundation.high_primal_source)


def test_route_b_vcycle_rejects_non_route_b_levels() -> None:
    with pytest.raises(ValueError, match=r"exactly \(6, 2, 1\)"):
        RouteBNestedVcycle(
            SimpleNamespace(low_matrix=object()),
            SimpleNamespace(levels={6: object(), 3: object(), 1: object()}),
        )
