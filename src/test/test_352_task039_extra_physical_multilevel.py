"""Pure contracts for the reusable Task039 intermediate-level core."""

from __future__ import annotations

import numpy as np
import pytest
from contextlib import ExitStack
from petsc4py import PETSc

import src.solvers.fullspace_physical_intermediate as intermediate
from src.solvers.fullspace_memory_first_krylov import (
    GMRES_RESTART,
    RESTART12,
    RESTART32,
    RESTART64,
)
from src.solvers.fullspace_physical_intermediate import (
    INTERMEDIATE_MAX_IT,
    INTERMEDIATE_RESIDUAL_LIMIT,
    INTERMEDIATE_RESTART,
    SHIFT_SIGMA,
    SMOOTHING_STEPS,
    OUTER_RESTART,
    PhysicalIntermediatePreconditioner,
    ShiftedAuxiliaryCycle,
    ShiftedPhysicalAction,
    apply_owned,
    modified_residual_accept,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    SAME_MESH_EXTENDED_TRANSFER_PAIRS,
    SAME_MESH_TRANSFER_PAIRS,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
    SAME_MESH_EXTENDED_OWNER_TRANSFER_PAIRS,
    SAME_MESH_OWNER_TRANSFER_PAIRS,
)


class _BorrowedAction:
    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.buffer = np.zeros(self.matrix.shape[0], dtype=np.complex128)
        self.apply_count = 0

    def apply(self, source: np.ndarray, target: np.ndarray) -> np.ndarray:
        self.buffer[:] = self.matrix @ source
        target[:] = self.buffer
        self.apply_count += 1
        return target


class _IdentityTransfer:
    def __init__(self) -> None:
        self.adjoint_count = 0
        self.primal_count = 0

    def apply_adjoint(self, source: np.ndarray) -> np.ndarray:
        self.adjoint_count += 1
        return np.array(source, copy=True)

    def apply_primal(self, source: np.ndarray) -> np.ndarray:
        self.primal_count += 1
        return np.array(source, copy=True)


def test_fixed_restart_and_extended_transfer_contracts_preserve_old_api() -> None:
    assert GMRES_RESTART == 20
    assert (RESTART12, RESTART32, RESTART64) == (12, 32, 64)
    assert SAME_MESH_TRANSFER_PAIRS == ((3, 1), (6, 3))
    assert SAME_MESH_OWNER_TRANSFER_PAIRS == ((3, 1), (6, 3))
    assert (4, 2) in SAME_MESH_EXTENDED_TRANSFER_PAIRS
    assert (4, 2) in SAME_MESH_EXTENDED_OWNER_TRANSFER_PAIRS


def test_borrowed_action_is_copied_and_complex_mr_is_repeatable() -> None:
    matrix = np.array([[2.0 + 1.0j, 0.25], [0.0, 1.5 - 0.5j]])
    action = _BorrowedAction(matrix)
    source = np.array([1.0 - 2.0j, 0.5 + 0.25j])
    before = source.copy()

    first = apply_owned(action, source, np.empty_like(source))
    action.buffer[:] = 99.0
    second = apply_owned(action, source, np.empty_like(source))
    np.testing.assert_allclose(first, matrix @ source)
    np.testing.assert_allclose(second, first)
    np.testing.assert_array_equal(source, before)
    assert first is not action.buffer

    residual = np.array([1.0 + 0.5j, -0.25 + 0.75j])
    residual_before = residual.copy()
    direction = np.array([0.5 - 0.25j, 1.0 + 0.5j])
    direction_before = direction.copy()
    correction, facts = modified_residual_accept(residual, direction, action)
    applied = matrix @ direction
    alpha = np.vdot(applied, residual_before) / np.vdot(applied, applied).real
    np.testing.assert_allclose(correction, alpha * direction)
    np.testing.assert_allclose(residual, residual_before - alpha * applied)
    np.testing.assert_array_equal(direction, direction_before)
    assert facts["accepted"] is True
    assert facts["finite"] is True

    zero = np.zeros_like(residual)
    zero_correction, zero_facts = modified_residual_accept(zero, direction, action)
    np.testing.assert_array_equal(zero_correction, np.zeros_like(direction))
    assert zero_facts["accepted"] is False
    assert zero_facts["reason"] == "zero_residual_or_direction"

    for scale in (1.0e-12, 1.0e12):
        scaled_residual = scale * residual_before
        scaled_direction = scale * direction
        _, scaled_facts = modified_residual_accept(
            scaled_residual, scaled_direction, action
        )
        assert scaled_facts["accepted"] is True
        assert np.isfinite(scaled_facts["rho"])


def test_shifted_cycle_has_frozen_three_step_contract_without_input_mutation(monkeypatch) -> None:
    shifted_p4 = _BorrowedAction(np.eye(3, dtype=np.complex128))
    p4 = _BorrowedAction(np.eye(3, dtype=np.complex128))
    p2 = _BorrowedAction(np.eye(3, dtype=np.complex128))
    transfer = _IdentityTransfer()
    rhs = np.array([1.0 + 0.25j, -2.0j, 0.5 - 0.5j])
    before = rhs.copy()
    def fake_fgmres(rhs, _action, _preconditioner, steps):
        return (
            np.array(rhs, copy=True),
            np.zeros_like(rhs),
            [{"ksp_type": "fgmres", "restart": steps, "iterations": steps}],
        )

    monkeypatch.setattr(intermediate, "_bounded_right_fgmres", fake_fgmres)
    cycle = ShiftedAuxiliaryCycle(
        shifted_p4,
        p4,
        p2,
        transfer,
        transfer,
        transfer,
        transfer,
        lambda source: np.array(source, copy=True),
        p4_preconditioner=object.__new__(intermediate.PositiveDiagonalJacobi),
        p2_preconditioner=object.__new__(intermediate.PositiveDiagonalJacobi),
    )

    result, facts = cycle.apply_with_facts(rhs)

    np.testing.assert_allclose(result, rhs)
    np.testing.assert_array_equal(rhs, before)
    assert facts["sigma"] == SHIFT_SIGMA == 0.5
    assert facts["smoothing_steps"] == SMOOTHING_STEPS == 3
    assert facts["p4_pre_steps"] == facts["p4_post_steps"] == 3
    assert facts["p2_pre_steps"] == facts["p2_post_steps"] == 3
    assert facts["p1_solve_count"] == 1
    assert facts["finite"] is True
    assert cycle.apply_count == 1
    assert cycle.p4_action is p4
    assert cycle.shifted_p4_action is shifted_p4
    assert transfer.adjoint_count == 2
    assert transfer.primal_count == 2


def test_nonlinear_outer_pc_uses_three_directions_and_shifted_action_is_repeatable() -> None:
    with ExitStack() as resources:
        identity = _PetscAction(np.eye(2))
        transfer = _RectangularTransfer(np.eye(2), resources)

        class DummyIntermediate:
            calls = 0

            def solve_intermediate(self, source):
                self.calls += 1
                return {"final_solution": source.copy(), "status": "INEXACT_INTERMEDIATE",
                        "iterations": 36, "shifted_cycles": [{"apply_count": 1}]}

        inner = DummyIntermediate()
        pc = PhysicalIntermediatePreconditioner(identity, identity, transfer, inner)
        rhs = _vec([1+1j, -.5+.25j], resources)
        before = rhs.array.copy()
        correction = pc.apply(rhs)
        resources.callback(correction.destroy)
        np.testing.assert_allclose(correction.array, before)
        np.testing.assert_array_equal(rhs.array, before)
        assert pc.last_apply_facts["direction_count"] == 3
        assert [f["stage"] for f in pc.last_apply_facts["direction_facts"]] == [
            "positive_pre", "physical_middle", "positive_post"]
        assert pc.last_apply_facts["intermediate"]["iterations"] == 36
        assert inner.calls == 1
        shifted = ShiftedPhysicalAction(identity, identity, k0=2.0)
        for _ in range(2):
            result = shifted.apply(rhs)
            resources.callback(result.destroy)
            np.testing.assert_allclose(result.array, (1-2j)*before)
        np.testing.assert_array_equal(rhs.array, before)
        zero = pc.apply(_vec([0, 0], resources))
        resources.callback(zero.destroy)
        assert zero.norm() == 0 and inner.calls == 1


def test_intermediate_solver_contract_is_frozen() -> None:
    assert OUTER_RESTART == 32
    assert INTERMEDIATE_RESTART == 12
    assert INTERMEDIATE_MAX_IT == 36
    assert INTERMEDIATE_RESIDUAL_LIMIT == 1.0e-2



class _PetscAction:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.calls = 0

    def apply(self, source, target):
        target.array[:] = self.matrix @ source.array
        self.calls += 1


def _vec(values, resources):
    values = np.asarray(values, dtype=np.complex128)
    result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    resources.callback(result.destroy)
    result.array[:] = values
    return result


def _arnoldi_three(matrix, rhs, diagonal):
    # Independent NumPy Arnoldi and least squares, no PETSc or production helper.
    basis = [rhs / np.linalg.norm(rhs)]
    directions = []
    h = np.zeros((4, 3), dtype=complex)
    for j in range(3):
        directions.append(basis[j] / diagonal)
        w = matrix @ directions[j]
        for i in range(j + 1):
            h[i, j] = np.vdot(basis[i], w)
            w -= h[i, j] * basis[i]
        h[j + 1, j] = np.linalg.norm(w)
        basis.append(w / h[j + 1, j])
    target = np.array([np.linalg.norm(rhs), 0, 0, 0], dtype=complex)
    return np.column_stack(directions) @ np.linalg.lstsq(h, target, rcond=None)[0]


def test_bounded_smoother_matches_independent_three_step_arnoldi():
    rng = np.random.default_rng(391)
    matrix = rng.normal(size=(5, 5)) + 1j * rng.normal(size=(5, 5))
    matrix += np.diag(np.arange(1, 6))
    assert np.linalg.norm(matrix.conj().T @ matrix - matrix @ matrix.conj().T) > 1
    b = rng.normal(size=5) + 1j * rng.normal(size=5)
    diagonal = np.arange(2, 7, dtype=float)
    expected = _arnoldi_three(matrix, b, diagonal)
    # Three scalar MR iterations are detectably different on this fixture.
    scalar_mr = np.zeros(5, dtype=complex)
    r = b.copy()
    for _ in range(3):
        d = r / diagonal
        w = matrix @ d
        alpha = np.vdot(w, r) / np.vdot(w, w)
        scalar_mr += alpha * d
        r -= alpha * w
    assert np.linalg.norm(scalar_mr - expected) > 0.1
    with ExitStack() as resources:
        rhs = _vec(b, resources)
        pc = intermediate.PositiveDiagonalJacobi(_vec(diagonal, resources))
        solution, residual, facts = intermediate._bounded_right_fgmres(
            rhs, _PetscAction(matrix), pc, steps=3)
        resources.callback(solution.destroy)
        resources.callback(residual.destroy)
        np.testing.assert_allclose(solution.array, expected, atol=1e-12, rtol=1e-12)
        np.testing.assert_allclose(residual.array, b - matrix @ expected, atol=1e-12)
        np.testing.assert_array_equal(rhs.array, b)
        assert facts[0]["iterations"] == facts[0]["pc_apply_count"] == 3
        assert facts[0]["preconditioner"] == "positive_diagonal_jacobi"


@pytest.mark.parametrize("scale", [1e-100, 1.0, 1e100])
def test_petsc_mr_complex_alpha_against_numpy_vdot(scale):
    matrix = np.array([[2+1j, .25], [.3j, 1.5-.5j]])
    b = scale * np.array([1+.5j, -.25+.75j])
    d = scale * np.array([.5-.25j, 1+.5j])
    w = matrix @ d
    alpha = np.vdot(w / scale, b / scale) / np.vdot(w / scale, w / scale)
    assert abs(alpha.imag) > .01
    with ExitStack() as resources:
        residual, direction = _vec(b, resources), _vec(d, resources)
        correction, facts = modified_residual_accept(residual, direction, _PetscAction(matrix))
        resources.callback(correction.destroy)
        np.testing.assert_allclose(complex(*facts["alpha"]), alpha, rtol=1e-12)
        np.testing.assert_allclose(correction.array / scale, alpha * d / scale, atol=1e-12)
        np.testing.assert_allclose(residual.array / scale, (b-alpha*w) / scale, atol=1e-12)
        np.testing.assert_array_equal(direction.array, d)
        assert facts["raw_unit_rho"] == pytest.approx(np.linalg.norm((b-w)/scale)/np.linalg.norm(b/scale))
        assert facts["rho"] <= 1 + 1e-12


def test_zero_action_is_checked_before_division_and_input_preserved():
    with ExitStack() as resources:
        residual = _vec([1+2j, 3-1j], resources)
        direction = _vec([1j, 2], resources)
        before = residual.array.copy()
        correction, facts = modified_residual_accept(residual, direction, _PetscAction(np.zeros((2, 2))))
        resources.callback(correction.destroy)
        np.testing.assert_array_equal(residual.array, before)
        assert correction.norm() == 0
        assert facts["reason"] == "zero_action_direction"
        assert facts["rho"] == facts["raw_unit_rho"] == 1


def test_borrowed_petsc_buffer_survives_shared_action_context():
    from src.solvers.fullspace_memory_first_krylov import _ActionContext
    with ExitStack() as resources:
        buffer = _vec([0, 0], resources)
        class Borrowed:
            def apply(self, source):
                source.copy(buffer)
                buffer.scale(2j)
                return buffer
        action = intermediate.BorrowedActionAdapter(Borrowed())
        context = _ActionContext(lambda source: apply_owned(action, source))
        source, target = _vec([1+2j, 3], resources), _vec([0, 0], resources)
        for _ in range(2):
            context.mult(None, source, target)
            np.testing.assert_allclose(target.array, 2j * source.array)
            assert buffer.getSize() == 2


class _RectangularTransfer:
    def __init__(self, matrix, resources):
        self.matrix = np.asarray(matrix, dtype=complex)
        self.resources = resources
        self.outputs = []

    def _result(self, values):
        result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
        result.array[:] = values
        self.outputs.append(result)
        return result

    def apply_adjoint(self, source):
        assert source.getSize() == self.matrix.shape[0]
        return self._result(self.matrix.conj().T @ source.array)

    def apply_primal(self, source):
        assert source.getSize() == self.matrix.shape[1]
        return self._result(self.matrix @ source.array)


def _cycle(resources, matrix, bottom_failure=False):
    physical = _PetscAction(matrix)
    shifted = _PetscAction(matrix - .5j * np.eye(len(matrix)))
    p42 = _RectangularTransfer(np.eye(len(matrix), 4), resources)
    p21 = _RectangularTransfer(np.eye(4, 2), resources)
    a2 = p42.matrix.conj().T @ shifted.matrix @ p42.matrix
    a1 = p21.matrix.conj().T @ a2 @ p21.matrix
    def bottom(rhs):
        if bottom_failure:
            raise RuntimeError("injected bottom failure")
        result = rhs.copy()
        result.array[:] = np.linalg.solve(a1, rhs.array)
        return result
    cycle = ShiftedAuxiliaryCycle(
        shifted, physical, _PetscAction(a2), p42, p21, p21, p42, bottom,
        p4_preconditioner=intermediate.PositiveDiagonalJacobi(_vec(np.ones(len(matrix)), resources)),
        p2_preconditioner=intermediate.PositiveDiagonalJacobi(_vec(np.ones(4), resources)))
    return cycle, p42, p21


def test_actual_rectangular_cycle_and_unshifted_intermediate_repeat_and_zero():
    rng = np.random.default_rng(84)
    matrix = 4 * np.eye(6) + .2 * (rng.normal(size=(6, 6)) + 1j*rng.normal(size=(6, 6)))
    with ExitStack() as resources:
        cycle, p42, p21 = _cycle(resources, matrix)
        rhs = _vec(rng.normal(size=6)+1j*rng.normal(size=6), resources)
        before = rhs.array.copy()
        results = []
        for _ in range(2):
            result = cycle.solve_intermediate(rhs)
            resources.callback(result["final_solution"].destroy)
            results.append(result["final_solution"].array.copy())
            true = np.linalg.norm(before-matrix@results[-1])/np.linalg.norm(before)
            assert result["final_true_residual"] == pytest.approx(true, abs=1e-12)
            assert result["status"] == "CONVERGED_INTERMEDIATE"
            assert len(result["shifted_cycles"]) == result["pc_apply_count"]
            assert result["pc_apply_count"] > 0
        np.testing.assert_allclose(results[0], results[1], atol=1e-12)
        np.testing.assert_array_equal(rhs.array, before)
        count = cycle.apply_count
        zero = cycle.solve_intermediate(_vec(np.zeros(6), resources))
        resources.callback(zero["final_solution"].destroy)
        assert zero["status"] == "ZERO_RHS" and zero["iterations"] == 0
        assert cycle.apply_count == count
        assert all(not vector for vector in p42.outputs + p21.outputs)


def test_exception_cleans_rectangular_transfers_and_smoother_vectors(monkeypatch):
    created = []
    original = intermediate._bounded_right_fgmres
    def recorded(*args, **kwargs):
        solution, residual, facts = original(*args, **kwargs)
        created.extend([solution, residual])
        return solution, residual, facts
    monkeypatch.setattr(intermediate, "_bounded_right_fgmres", recorded)
    with ExitStack() as resources:
        cycle, p42, p21 = _cycle(resources, np.diag(np.arange(1, 7)), bottom_failure=True)
        rhs = _vec(np.ones(6), resources)
        with pytest.raises(RuntimeError, match="injected bottom"):
            cycle.apply(rhs)
        assert all(not vector for vector in created + p42.outputs + p21.outputs)
        np.testing.assert_array_equal(rhs.array, np.ones(6))


def test_intermediate_budget_exhaustion_is_inexact_and_retains_ledger(monkeypatch):
    import src.solvers.fullspace_memory_first_krylov as krylov
    with ExitStack() as resources:
        cycle, _, _ = _cycle(resources, np.eye(6))
        def bounded(rhs, action, pc, **settings):
            assert settings["restart"] == 12 and settings["max_it"] == 36
            assert settings["initial_solution"] is None
            result = rhs.copy()
            result.scale(.5)
            return {"final_solution": result, "final_true_residual": .5,
                    "reason": -3, "iterations": 36, "cycles": [{"iterations": 12}]*3}
        monkeypatch.setattr(krylov, "run_fixed_restart_cycles", bounded)
        result = cycle.solve_intermediate(_vec(np.ones(6), resources))
        resources.callback(result["final_solution"].destroy)
        assert result["status"] == "INEXACT_INTERMEDIATE"
        assert result["iterations"] == 36 and len(result["cycles"]) == 3


def test_mr_nonfinite_action_releases_owned_work_vectors(monkeypatch):
    created = []
    original = intermediate._new_like
    def tracked(value):
        result = original(value)
        created.append(result)
        return result
    monkeypatch.setattr(intermediate, '_new_like', tracked)
    with ExitStack() as resources:
        rhs, direction = _vec([1, 2j], resources), _vec([1j, 2], resources)
        with pytest.raises(RuntimeError, match='non-finite'):
            modified_residual_accept(rhs, direction, _PetscAction(np.full((2, 2), np.nan)))
        assert all(not vector for vector in created)
        np.testing.assert_array_equal(rhs.array, [1, 2j])


@pytest.mark.parametrize('restart', [12, 20, 32, 64])
def test_real_fixed_restart_preserves_all_four_supported_settings(restart):
    from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles
    with ExitStack() as resources:
        rhs = _vec([1+1j, 2-1j, 3+.5j, -.1j, 1], resources)
        action = _PetscAction(np.diag([1+1j, 2-1j, 3+.5j, 2+.1j, 4]))
        result = run_fixed_restart_cycles(
            rhs, lambda x: apply_owned(action, x), lambda x: x.copy(),
            max_it=restart, residual_limit=1e-10, resource_sample=lambda: {},
            start_iteration=0, first_checkpoint_iteration=None,
            checkpoint_interval=restart, ksp_type='fgmres', restart=restart)
        resources.callback(result['final_solution'].destroy)
        assert result['settings']['restart'] == restart
        assert result['final_true_residual'] < 1e-12


def test_real_bounded_intermediate_can_return_finite_inexact():
    rng = np.random.default_rng(191)
    matrix = rng.normal(size=(50, 50)) + 1j*rng.normal(size=(50, 50))
    with ExitStack() as resources:
        cycle, _, _ = _cycle(resources, matrix)
        rhs = _vec(rng.normal(size=50)+1j*rng.normal(size=50), resources)
        result = cycle.solve_intermediate(rhs)
        resources.callback(result['final_solution'].destroy)
        assert result['iterations'] == 36
        assert result['status'] == 'INEXACT_INTERMEDIATE'
        assert result['final_true_residual'] > 1e-2
        assert result['shifted_cost_totals']['cycle_count'] == result['pc_apply_count']
        assert result['shifted_cost_totals']['p1_solve_count'] == result['pc_apply_count']
        assert result['shifted_cost_totals']['p4_smoothing_pc_apply_count'] == 6*result['pc_apply_count']


def test_shared_krylov_initial_action_failure_cleans_solution():
    from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles
    held = []
    def broken(source):
        held.append(source)
        raise RuntimeError('injected initial action')
    with ExitStack() as resources:
        rhs = _vec([1, 2], resources)
        with pytest.raises(RuntimeError, match='injected initial action'):
            run_fixed_restart_cycles(
                rhs, broken, lambda x: x.copy(), max_it=12,
                residual_limit=1e-2, resource_sample=lambda: {}, start_iteration=0,
                first_checkpoint_iteration=None, checkpoint_interval=12,
                restart=12, ksp_type='fgmres')
        assert held and all(not vector for vector in held)


@pytest.mark.parametrize('caller_correction', [False, True])
def test_mr_action_exception_respects_correction_ownership(monkeypatch, caller_correction):
    created = []
    original = intermediate._new_like
    def tracked(value):
        result = original(value)
        created.append(result)
        return result
    class BrokenAction:
        def apply(self, source, target):
            raise RuntimeError('injected MR action')
    monkeypatch.setattr(intermediate, '_new_like', tracked)
    with ExitStack() as resources:
        rhs, direction = _vec([1, 2j], resources), _vec([1j, 2], resources)
        correction = _vec([0, 0], resources) if caller_correction else None
        with pytest.raises(RuntimeError, match='injected MR action'):
            modified_residual_accept(rhs, direction, BrokenAction(), correction=correction)
        assert all(not vector for vector in created)
        if caller_correction:
            assert correction.getSize() == 2
        np.testing.assert_array_equal(rhs.array, [1, 2j])


def test_positive_apply_into_facts_do_not_become_owned_vector():
    class Positive:
        last_apply_facts = {}
        def apply_into(self, source, target):
            source.copy(target)
            self.last_apply_facts = {'p1_solve_count': 1}
            return self.last_apply_facts
    with ExitStack() as resources:
        rhs = _vec([1, 2j], resources)
        result = apply_owned(Positive(), rhs)
        resources.callback(result.destroy)
        np.testing.assert_array_equal(result.array, rhs.array)
