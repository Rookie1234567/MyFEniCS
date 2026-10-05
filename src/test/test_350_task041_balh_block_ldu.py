"""Focused H1f checks for the borrowed BAL_H block-LDU factory."""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import linecache
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hybrid_fem_modal_block_ldu as block_ldu
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.solvers.physical_balanced_h6 import H6_DEGREE, FixedH6
from src.solvers.physical_balanced_side_inverse import FixedH6ActiveTraceAction
from src.test.test_241_task037b_hybrid_action_modal_schur import (
    _destroy_fixture,
    _gather_matrix,
    _gather_vector,
    _matrix_from_dense,
    _tiny_fixture,
)
from src.test.test_349_task041_balh_side_inverse import _build_fixture

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1f focused block-LDU tests are serial/MPI2 only",
)


def _set_vector(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _relative_or_absolute(actual: np.ndarray, expected: np.ndarray) -> float:
    difference = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    denominator = float(np.linalg.norm(np.asarray(expected)))
    return difference / denominator if denominator > 0.0 else difference


def _sample_contract() -> tuple[list[int], dict[str, list[str]], str]:
    columns = [0, 1, 2, 3]
    roles = {
        "0": ["head", "bottom_positive_unattenuated"],
        "1": ["interior", "bottom_positive_unattenuated"],
        "2": ["head", "top_negative_unattenuated"],
        "3": ["tail", "top_negative_unattenuated"],
    }
    contract = {
        "columns": columns,
        "mode_count_per_direction": 2,
        "roles": roles,
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return columns, roles, contract_sha


def _side_block_fixture() -> dict[str, object]:
    tiny = _tiny_fixture()
    bottom_inverse, bottom_owned = _build_fixture(size=4)
    top_inverse, top_owned = _build_fixture(size=4)
    bottom = bottom_owned["side_system"]
    top = top_owned["side_system"]
    comm = MPI.COMM_WORLD
    for system, side in ((bottom, "bottom"), (top, "top")):
        system.side = side
        system.global_size = 4
        system.local_mesh = SimpleNamespace(mesh=SimpleNamespace(comm=comm))
        system.b = system.A.createVecRight()
    _set_vector(
        bottom.b,
        np.asarray([0.4 + 0.1j, -0.2 + 0.3j, 0.7 - 0.2j, -0.5 + 0.4j]),
    )
    _set_vector(
        top.b,
        np.asarray([-0.3 + 0.2j, 0.6 - 0.1j, -0.4 - 0.5j, 0.8 + 0.3j]),
    )
    coupling = tiny["coupling"]
    coupling.internal_equation_count = 4
    coupling.bottom.modal_rhs_correction = np.asarray(
        [0.13 - 0.07j, -0.22 + 0.11j], dtype=np.complex128
    )
    coupling.top.modal_rhs_correction = np.asarray(
        [-0.31 + 0.05j, 0.17 + 0.19j], dtype=np.complex128
    )
    layout = HybridAugmentedLayout.build(bottom, top, 4)
    return {
        "tiny": tiny,
        "bottom_inverse": bottom_inverse,
        "top_inverse": top_inverse,
        "bottom_owned": bottom_owned,
        "top_owned": top_owned,
        "bottom": bottom,
        "top": top,
        "coupling": tiny["coupling"],
        "layout": layout,
    }


def _pack(
    layout: HybridAugmentedLayout,
    bottom: object,
    top: object,
    bottom_values: np.ndarray,
    top_values: np.ndarray,
    modal_values: np.ndarray,
) -> PETSc.Vec:
    bottom_vector = bottom.A.createVecRight()
    top_vector = top.A.createVecRight()
    _set_vector(bottom_vector, bottom_values)
    _set_vector(top_vector, top_values)
    packed = layout.pack(bottom_vector, top_vector, modal_values)
    bottom_vector.destroy()
    top_vector.destroy()
    return packed


def _destroy_side_block_fixture(fixture: dict[str, object]) -> None:
    bottom_inverse = fixture["bottom_inverse"]
    top_inverse = fixture["top_inverse"]
    bottom_owned = fixture["bottom_owned"]
    top_owned = fixture["top_owned"]
    bottom_inverse.destroy()
    top_inverse.destroy()
    bottom_owned["operator"].destroy()
    top_owned["operator"].destroy()
    fixture["bottom"].b.destroy()
    fixture["top"].b.destroy()
    _destroy_fixture(fixture["tiny"])


class _TinyPositiveWindow:
    """Matrix carrier for the real FixedH6 recurrence on a tiny PETSc matrix."""

    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.audit = {"apply_count": 0}
        self.destroyed = False

    def destroy(self) -> None:
        if self.destroyed:
            return
        self.destroyed = True
        self.matrix.destroy()


def _tiny_fixed_h6_bundle(side: str) -> dict[str, object]:
    comm = MPI.COMM_WORLD
    full_rows = 8
    active_rows = 4
    full_template = PETSc.Vec().createMPI(
        (full_rows // comm.size, full_rows), comm=comm
    )
    active_local_rows = active_rows // comm.size
    active_template = PETSc.Vec().createMPI(
        (active_local_rows, active_rows), comm=comm
    )
    diagonal_factor = np.diag(np.sqrt(np.arange(2.0, 10.0))).astype(
        np.complex128
    )
    phase = 1.0 if side == "bottom" else -1.0
    for index in range(full_rows - 1):
        diagonal_factor[index, index + 1] = phase * (0.05 + 0.03j)
        diagonal_factor[index + 1, index] = phase * (0.02 - 0.04j)
    dense_h6 = diagonal_factor.conj().T @ diagonal_factor + 3.0 * np.eye(
        full_rows, dtype=np.complex128
    )
    h6_matrix = _matrix_from_dense(full_template, full_template, dense_h6)
    active_operator = _matrix_from_dense(
        active_template,
        active_template,
        np.diag(np.asarray([1.0, 1.2, 1.4, 1.6], dtype=np.complex128)),
    )
    diagonal = h6_matrix.createVecRight()
    first, last = map(int, diagonal.getOwnershipRange())
    diagonal.getArray()[:] = np.real(np.diag(dense_h6))[first:last]
    diagonal.assemble()
    seed = h6_matrix.createVecRight()
    first, last = map(int, seed.getOwnershipRange())
    seed.getArray()[:] = np.asarray(
        [1.0 + 0.1j * (row + 1) for row in range(first, last)],
        dtype=PETSc.ScalarType,
    )
    seed.assemble()
    window = _TinyPositiveWindow(h6_matrix)
    h6 = FixedH6(
        window,
        diagonal,
        seed,
        {"source": "test350 tiny SPD PETSc matrix"},
        {"source": "deterministic nonzero test seed"},
    )
    seed.destroy()

    selected_full_rows = np.asarray([0, 2, 4, 6], dtype=PETSc.IntType)
    full_first, full_last = map(int, full_template.getOwnershipRange())
    local_active_original = selected_full_rows[
        (selected_full_rows >= full_first) & (selected_full_rows < full_last)
    ].copy()

    def create_active_vector() -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (len(local_active_original), active_rows), comm=comm
        )

    condensed = SimpleNamespace(
        full_rows=full_rows,
        active_rows=active_rows,
        owned_active_rows=len(local_active_original),
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=local_active_original
        ),
        comm=comm,
        create_active_vector=create_active_vector,
    )
    full_template.destroy()
    active_template.destroy()
    return {
        "side": side,
        "selected_full_rows": selected_full_rows,
        "local_active_original": local_active_original,
        "h6_matrix": h6_matrix,
        "active_operator": active_operator,
        "window": window,
        "h6": h6,
        "condensed": condensed,
    }


def _tiny_h6_dense_action(h6: FixedH6) -> np.ndarray:
    rhs = h6.matrix.createVecRight()
    target = h6.matrix.createVecLeft()
    dense = np.empty(h6.matrix.getSize(), dtype=np.complex128)
    first, last = map(int, rhs.getOwnershipRange())
    try:
        for column in range(int(rhs.getSize())):
            rhs.set(0.0)
            if first <= column < last:
                rhs.getArray()[column - first] = 1.0
            rhs.assemble()
            h6.apply_into(rhs, target)
            dense[:, column] = _gather_vector(target)
    finally:
        target.destroy()
        rhs.destroy()
    return dense


def _tiny_fixed_h6_modal_oracle(
    fixture: dict[str, object],
    bottom_h6: np.ndarray,
    top_h6: np.ndarray,
    selected_full_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coupling = fixture["coupling"]
    blocks = fixture["blocks"]
    mode_count = int(coupling.mode_count_per_direction)
    active_h6 = [
        matrix[np.ix_(selected_full_rows, selected_full_rows)]
        for matrix in (bottom_h6, top_h6)
    ]
    backward = np.asarray(coupling.propagation.backward.factors)
    forward = np.asarray(coupling.propagation.forward.factors)
    bottom_traction = np.concatenate(
        (
            blocks["bottom_positive"],
            blocks["bottom_negative"] * backward[np.newaxis, :],
        ),
        axis=1,
    )
    top_traction = np.concatenate(
        (
            blocks["top_positive"] * forward[np.newaxis, :],
            blocks["top_negative"],
        ),
        axis=1,
    )
    bottom_feedback = np.zeros((2 * mode_count, 2 * mode_count), dtype=np.complex128)
    top_feedback = np.zeros_like(bottom_feedback)
    bottom_feedback[:mode_count, :] = (
        blocks["bottom_projection"] @ active_h6[0] @ bottom_traction
    )
    top_feedback[mode_count:, :] = (
        blocks["top_projection"] @ active_h6[1] @ top_traction
    )
    constraint = np.asarray(
        internal_modal_constraint_matrix(coupling), dtype=np.complex128
    )
    return constraint - bottom_feedback - top_feedback, bottom_feedback, top_feedback


def _fixed_h6_modal_krylov_components():
    """Build the tiny real-H6 recurrence with a dense modal-action oracle."""
    fixture = _tiny_fixture()
    bundles: list[dict[str, object]] = []
    try:
        for side in ("bottom", "top"):
            bundle = _tiny_fixed_h6_bundle(side)
            bundles.append(bundle)
            bundle["adapter"] = FixedH6ActiveTraceAction(
                bundle["active_operator"], bundle["condensed"], bundle["h6"]
            )
        selected = bundles[0]["selected_full_rows"]
        bottom_h6 = _tiny_h6_dense_action(bundles[0]["h6"])
        top_h6 = _tiny_h6_dense_action(bundles[1]["h6"])
        expected, bottom_feedback, top_feedback = _tiny_fixed_h6_modal_oracle(
            fixture, bottom_h6, top_h6, selected
        )
        assert np.linalg.norm(bottom_feedback) > 0.0
        assert np.linalg.norm(top_feedback) > 0.0
        return fixture, bundles, expected
    except BaseException:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, None)
        raise


def _destroy_fixed_h6_modal_krylov_components(
    fixture: dict[str, object],
    bundles: list[dict[str, object]],
    system: object | None,
) -> None:
    if system is not None:
        system.destroy()
    for bundle in bundles:
        adapter = bundle.get("adapter")
        if adapter is not None:
            adapter.destroy()
        h6 = bundle.get("h6")
        if h6 is not None:
            h6.destroy()
        operator = bundle.get("active_operator")
        if operator is not None:
            operator.destroy()
    _destroy_fixture(fixture)


def test_fixed_h6_modal_gmres_matches_dense_solve_and_borrows_adapters() -> None:
    fixture, bundles, dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    try:
        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=MPI.COMM_WORLD.size - 1,
        )
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        rhs_before = rhs.copy()
        for _ in range(2):
            side_applies_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
            h6_mults_before = [int(bundle["h6"].matrix_mult_count) for bundle in bundles]
            solution = system.solve(rhs)
            expected_solution = np.linalg.solve(dense_operator, rhs_before)
            independent_residual = dense_operator @ solution - rhs_before
            independent_residual_norm = float(np.linalg.norm(independent_residual))
            independent_relative = independent_residual_norm / float(np.linalg.norm(rhs_before))
            condition_number = float(np.linalg.cond(dense_operator))
            solution_error = _relative_or_absolute(solution, expected_solution)
            # For A x* = b, ||x-x*||/||x*|| is bounded by
            # cond(A) * ||A x-b||/||b||, up to floating-point roundoff.
            roundoff_allowance = (
                32.0 * np.finfo(np.float64).eps * condition_number
            )
            residual_condition_bound = (
                condition_number * independent_relative + roundoff_allowance
            )
            solve = system.diagnostics["last_solve"]

            assert np.isfinite(condition_number)
            assert independent_relative <= system.rtol
            assert solution_error <= residual_condition_bound, (
                f"dense solution relative error {solution_error:.6e} exceeds "
                f"conditioned residual bound {residual_condition_bound:.6e} "
                f"(cond={condition_number:.6e}, relative residual={independent_relative:.6e})"
            )
            assert np.array_equal(rhs, rhs_before)
            assert np.allclose(
                _gather_vector(system._rhs), rhs_before, rtol=0.0, atol=0.0
            )
            assert solve["status"] == "converged"
            assert solve["zero_initial_guess"] is True
            assert solve["initial_solution_norm"] == 0.0
            assert solve["final_residual_evaluated"] is True
            assert np.isclose(
                solve["final_residual_norm"],
                independent_residual_norm,
                rtol=1.0e-10,
                atol=1.0e-13,
            )
            assert solve["constraint_lu_factorizations"] == 1
            assert solve["local_constraint_lu_factorizations"] == (
                1 if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1 else 0
            )
            owner_attempts = solve["owner_constraint_lu_solve_attempts"]
            owner_successes = solve["owner_constraint_lu_solve_successes"]
            assert solve["local_constraint_lu_solve_attempts"] == (
                owner_attempts
                if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1
                else 0
            )
            assert solve["local_constraint_lu_solve_successes"] == (
                owner_successes
                if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1
                else 0
            )
            assert owner_attempts == owner_successes
            assert solve["constraint_lu_solve_count_scope"] == (
                "owner_authoritative_replicated_report"
            )
            assert [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_applies_before, strict=True)
            ] == [solve["total_matmult_calls"]] * 2
            assert [
                int(bundle["h6"].matrix_mult_count) - before
                for bundle, before in zip(bundles, h6_mults_before, strict=True)
            ] == [2 * solve["total_matmult_calls"]] * 2

        zero = np.zeros(4, dtype=np.complex128)
        zero_before = zero.copy()
        zero_applies_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
        zero_solution = system.solve(zero)
        zero_solve = system.diagnostics["last_solve"]
        assert np.array_equal(zero_solution, zero)
        assert np.array_equal(zero, zero_before)
        assert np.allclose(_gather_vector(system._rhs), zero, rtol=0.0, atol=0.0)
        assert zero_solve["status"] == "zero_rhs_exact"
        assert zero_solve["final_residual_norm"] == 0.0
        assert zero_solve["solver_matmult_calls"] == 0
        assert zero_solve["total_matmult_calls"] == 1
        assert zero_solve["owner_constraint_lu_solve_attempts"] == 0
        assert zero_solve["owner_constraint_lu_solve_successes"] == 0
        assert [
            bundle["adapter"].audit["apply_count"] - before
            for bundle, before in zip(bundles, zero_applies_before, strict=True)
        ] == [1, 1]

        system.destroy()
        system = None
        for bundle in bundles:
            adapter = bundle["adapter"]
            assert adapter.audit["destroyed"] is False
            source = bundle["active_operator"].createVecRight()
            target = bundle["active_operator"].createVecLeft()
            try:
                values = np.asarray([0.2 + 0.1j, -0.3 + 0.4j, 0.5 - 0.2j, 0.1 + 0.6j])
                _set_vector(source, values)
                adapter.apply(source, target)
                assert np.all(np.isfinite(_gather_vector(target)))
                assert adapter.audit["destroyed"] is False
            finally:
                target.destroy()
                source.destroy()
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_modal_gmres_synchronizes_preflight_pc_and_budget_failures() -> None:
    fixture, bundles, _dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    try:
        owner = MPI.COMM_WORLD.size - 1
        wrong_owner = owner
        if MPI.COMM_WORLD.rank == 0:
            wrong_owner = owner - 1 if owner > 0 else -1
        with pytest.raises(RuntimeError, match="input preflight") as owner_error:
            block_ldu._FixedH6ModalKrylovSystem(
                fixture["coupling"],
                bundles[0]["adapter"],
                bundles[1]["adapter"],
                modal_owner=wrong_owner,
            )
        owner_errors = MPI.COMM_WORLD.allgather(str(owner_error.value))
        assert len(set(owner_errors)) == 1
        assert "rank 0" in owner_errors[0]
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)

        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        system._reset_attempt()
        wrong_local_size = system.modal_count - 1 if MPI.COMM_WORLD.rank == owner else 0
        wrong_global_size = system.modal_count - 1
        bad_source = PETSc.Vec().createMPI(
            (wrong_local_size, wrong_global_size), comm=system._matrix.getComm()
        )
        bad_target = PETSc.Vec().createMPI(
            (wrong_local_size, wrong_global_size), comm=system._matrix.getComm()
        )
        try:
            h6_counts = [int(bundle["h6"].apply_count) for bundle in bundles]
            messages = []
            try:
                # Exercise the synchronized MatMult preflight directly.  The
                # local petsc4py files do not establish cross-rank C-callback
                # exception semantics, so this does not claim that bridge.
                system._mat_mult(bad_source, bad_target)
            except RuntimeError as exc:
                messages.append(str(exc))
            else:
                pytest.fail("malformed S_H Mat vectors were not rejected")
            preflight_messages = MPI.COMM_WORLD.allgather(messages[0])
            assert len(set(preflight_messages)) == 1
            assert f"rank {owner}" in preflight_messages[0]
            assert [int(bundle["h6"].apply_count) for bundle in bundles] == h6_counts
        finally:
            bad_target.destroy()
            bad_source.destroy()

        pc_source = system._matrix.createVecRight()
        pc_target = system._matrix.createVecRight()
        try:
            pc_source.set(1.0)
            saved_lu = system._constraint_lu
            if MPI.COMM_WORLD.rank == owner:
                system._constraint_lu = None
            try:
                system._ksp.getPC().apply(pc_source, pc_target)
            finally:
                system._constraint_lu = saved_lu
            pc_errors = MPI.COMM_WORLD.allgather(system._pc_failure_error)
            assert len(set(pc_errors)) == 1
            assert pc_errors[0] is not None
            assert np.isinf(float(pc_target.norm()))
            owner_lu_attempts = int(
                MPI.COMM_WORLD.bcast(
                    system._constraint_lu_solve_attempts
                    if MPI.COMM_WORLD.rank == owner
                    else None,
                    root=owner,
                )
            )
            owner_lu_successes = int(
                MPI.COMM_WORLD.bcast(
                    system._constraint_lu_solve_successes
                    if MPI.COMM_WORLD.rank == owner
                    else None,
                    root=owner,
                )
            )
            assert owner_lu_attempts == 1
            assert owner_lu_successes == 0
            assert system._constraint_lu_solve_attempts == (
                1 if MPI.COMM_WORLD.rank == owner else 0
            )
            assert system._constraint_lu_solve_successes == 0
        finally:
            pc_target.destroy()
            pc_source.destroy()

        saved_lu = system._constraint_lu
        if MPI.COMM_WORLD.rank == owner:
            system._constraint_lu = None
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        try:
            with pytest.raises(RuntimeError):
                system.solve(rhs)
        finally:
            system._constraint_lu = saved_lu
        snapshot = system.diagnostics
        solve = snapshot["last_solve"]
        budget_exhausted = snapshot["budget_exhausted"]
        assert solve["status"] == (
            "budget_exhausted" if budget_exhausted else "pc_apply_failed"
        )
        assert solve["ksp_status"] in {
            "raised_after_synchronized_pc_failure",
            "returned_after_marked_pc_failure",
            "raised_after_budget_exhaustion",
        }
        assert solve["pc_failure"] is not None
        assert solve["final_residual_evaluated"] is False
        assert solve["final_residual_status"] == "not_evaluated"
        assert solve.get("final_residual_norm") is None
        assert solve.get("final_relative_residual") is None
        expected_not_evaluated_reason = (
            "budget_exhausted_before_trusted_KSP_iterate"
            if budget_exhausted
            else "PC_failure_no_trusted_KSP_iterate"
        )
        assert solve["final_residual_not_evaluated_reason"] == (
            expected_not_evaluated_reason
        )
        assert solve["local_constraint_lu_solve_attempts"] == (
            1 if MPI.COMM_WORLD.rank == owner else 0
        )
        assert solve["local_constraint_lu_solve_successes"] == 0
        if solve["constraint_lu_solve_count_scope"] == (
            "owner_authoritative_replicated_report"
        ):
            assert solve["owner_constraint_lu_solve_attempts"] == 1
            assert solve["owner_constraint_lu_solve_successes"] == 0
        else:
            assert solve["constraint_lu_solve_count_scope"] == (
                "owner_value_unavailable_without_post_callback_collective"
            )
            assert solve["owner_constraint_lu_solve_attempts"] == (
                1 if MPI.COMM_WORLD.rank == owner else None
            )
            assert solve["owner_constraint_lu_solve_successes"] == (
                0 if MPI.COMM_WORLD.rank == owner else None
            )
        assert solve["ksp_reason"] is not None
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)
        system.destroy()
        system = None
        assert all(bundle["adapter"].audit["destroyed"] is False for bundle in bundles)

        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        system._reset_attempt()
        source = system._matrix.createVecRight()
        target = system._matrix.createVecLeft()
        try:
            _set_vector(source, rhs)
            side_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
            h6_before = [int(bundle["h6"].apply_count) for bundle in bundles]
            # This remains method-level budget coverage: the following direct
            # _mat_mult calls do not exercise PETSc's KSP Mat callback boundary.
            for _ in range(system.solver_matmult_limit):
                system._mat_mult(source, target)
            assert system._solver_matmult_calls == 9
            assert system._total_matmult_calls == 9
            assert [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_before, strict=True)
            ] == [9, 9]
            assert [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_before, strict=True)
            ] == [9, 9]
            messages = []
            try:
                # Nine real S_H actions consume the solver budget; this tenth
                # attempted solver action is rejected before side actions run.
                system._mat_mult(source, target)
            except RuntimeError as exc:
                messages.append(str(exc))
            else:
                pytest.fail("S_H MatMult budget did not reject the extra action")
            budget_messages = MPI.COMM_WORLD.allgather(messages[0])
            assert len(set(budget_messages)) == 1
            assert "budget exhausted" in budget_messages[0]
            relative, finite = system._final_residual(float(np.linalg.norm(rhs)))
            solve = system.diagnostics["last_solve"]
            assert relative is None
            assert finite is False
            assert solve["status"] == "budget_exhausted"
            assert solve["final_residual_evaluated"] is False
            assert solve["final_residual_status"] == "not_evaluated"
            assert solve["budget_used_solver_matmult_calls"] == 9
            assert solve["budget_used_total_matmult_calls"] == 9
            assert solve["blocked_matmult_attempts"] == 1
            assert system._total_matmult_calls == 9
        finally:
            target.destroy()
            source.destroy()
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_modal_gmres_budget_failure_crosses_real_ksp_callback() -> None:
    fixture, bundles, _dense_operator = _fixed_h6_modal_krylov_components()
    system = None
    try:
        owner = MPI.COMM_WORLD.size - 1
        system = block_ldu._FixedH6ModalKrylovSystem(
            fixture["coupling"],
            bundles[0]["adapter"],
            bundles[1]["adapter"],
            modal_owner=owner,
        )
        system.solver_matmult_limit = 1
        system.total_matmult_limit = 2
        rhs = np.asarray(
            [0.31 + 0.27j, -0.18 + 0.42j, 0.53 - 0.36j, -0.24 - 0.11j],
            dtype=np.complex128,
        )
        rhs_before = rhs.copy()
        side_before = [bundle["adapter"].audit["apply_count"] for bundle in bundles]
        h6_apply_before = [int(bundle["h6"].apply_count) for bundle in bundles]
        returned_solution = None
        solve_error = None
        try:
            returned_solution = system.solve(rhs)
        except Exception as exc:  # noqa: BLE001 - gather each rank's real KSP outcome
            solve_error = f"{type(exc).__name__}: {exc}"

        snapshot = system.diagnostics
        solve = dict(snapshot["last_solve"])
        local_record = {
            "rank": MPI.COMM_WORLD.rank,
            "solution_returned": returned_solution is not None,
            "solve_error": solve_error,
            "ksp_reason": solve.get("ksp_reason"),
            "ksp_reason_present": "ksp_reason" in solve,
            "ksp_status": solve.get("ksp_status"),
            "iterations": solve.get("iterations"),
            "status": solve.get("status"),
            "budget_exhausted": snapshot["budget_exhausted"],
            "solver_matmult_limit": system.solver_matmult_limit,
            "total_matmult_limit": system.total_matmult_limit,
            "solver_matmult_calls": solve.get("solver_matmult_calls"),
            "total_matmult_calls": solve.get("total_matmult_calls"),
            "blocked_matmult_attempts": snapshot["blocked_matmult_attempts"],
            "side_apply_deltas": [
                bundle["adapter"].audit["apply_count"] - before
                for bundle, before in zip(bundles, side_before, strict=True)
            ],
            "h6_apply_deltas": [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_apply_before, strict=True)
            ],
            "final_residual_evaluated": solve.get("final_residual_evaluated"),
            "final_residual_state": solve.get("final_residual_status"),
            "final_residual_norm": solve.get("final_residual_norm"),
            "final_relative_residual": solve.get("final_relative_residual"),
            "final_residual_not_evaluated_reason": solve.get(
                "final_residual_not_evaluated_reason"
            ),
            "raw_residual_pass": solve.get("raw_residual_pass"),
            "rhs_unchanged": bool(np.array_equal(rhs, rhs_before)),
        }
        del returned_solution
        destroy_error = None
        try:
            system.destroy()
        except Exception as exc:  # noqa: BLE001 - capture cleanup outcome before gather
            destroy_error = f"{type(exc).__name__}: {exc}"
        local_record["system_destroyed"] = system._destroyed
        local_record["destroy_error"] = destroy_error
        local_record["owned_objects_released"] = (
            system._ksp is None
            and system._matrix is None
            and system._modal_action is None
            and all(
                getattr(system, name) is None
                for name in ("_rhs", "_solution", "_image", "_residual")
            )
            and system._constraint_lu is None
            and system._constraint_pivots is None
        )
        adapter_alive = []
        h6_alive = []
        for bundle in bundles:
            try:
                adapter_alive.append(bundle["adapter"].audit["destroyed"] is False)
            except Exception:  # noqa: BLE001 - report liveness instead of rank-local exit
                adapter_alive.append(False)
            try:
                rows, columns = map(int, bundle["h6"].matrix.getSize())
                h6_alive.append(rows > 0 and rows == columns)
            except Exception:  # noqa: BLE001 - report liveness instead of rank-local exit
                h6_alive.append(False)
        local_record["borrowed_adapters_alive"] = adapter_alive
        local_record["borrowed_h6_alive"] = h6_alive

        # Each rank captures its real KSP callback outcome before this single
        # post-solve collective; returning from it proves all ranks progressed.
        records = MPI.COMM_WORLD.allgather(local_record)
        if MPI.COMM_WORLD.rank == 0:
            print(
                "FIXED_H6_KSP_BUDGET_CALLBACK="
                + json.dumps(records, sort_keys=True),
                flush=True,
            )

        collective_fields = (
            "solution_returned",
            "status",
            "budget_exhausted",
            "solver_matmult_limit",
            "total_matmult_limit",
            "solver_matmult_calls",
            "total_matmult_calls",
            "blocked_matmult_attempts",
            "final_residual_evaluated",
            "final_residual_state",
            "side_apply_deltas",
            "h6_apply_deltas",
        )
        for field in collective_fields:
            assert len({json.dumps(record[field], sort_keys=True) for record in records}) == 1
        assert len(records) == MPI.COMM_WORLD.size
        for record in records:
            assert record["solution_returned"] is False
            assert record["solve_error"] is not None
            assert record["destroy_error"] is None
            assert record["status"] == "budget_exhausted"
            assert record["budget_exhausted"] is True
            assert record["solver_matmult_limit"] == 1
            assert record["total_matmult_limit"] == 2
            assert record["solver_matmult_calls"] == 1
            assert record["total_matmult_calls"] == 1
            assert record["blocked_matmult_attempts"] == 1
            assert record["final_residual_evaluated"] is False
            assert record["final_residual_state"] == "not_evaluated"
            assert record["final_residual_norm"] is None
            assert record["final_relative_residual"] is None
            assert record["final_residual_not_evaluated_reason"] is not None
            assert record["raw_residual_pass"] is None
            assert record["side_apply_deltas"] == [1, 1]
            assert record["h6_apply_deltas"] == [1, 1]
            assert record["rhs_unchanged"] is True
            assert record["system_destroyed"] is True
            assert record["owned_objects_released"] is True
            assert record["borrowed_adapters_alive"] == [True, True]
            assert record["borrowed_h6_alive"] == [True, True]
            assert record["ksp_reason_present"] is True
    finally:
        _destroy_fixed_h6_modal_krylov_components(fixture, bundles, system)


def test_fixed_h6_active_trace_action_matches_full_modal_feedback_oracle() -> None:
    """Exercise the real FixedH6 recurrence on tiny noncontiguous trace rows."""

    fixture = _tiny_fixture()
    bundles: list[dict[str, object]] = []
    modal_action = None
    inputs = (
        np.asarray([0.3 + 0.7j, -0.2 + 0.1j, 0.6 - 0.4j, 0.5 + 0.2j]),
        np.asarray([-0.4 + 0.2j, 0.8 - 0.3j, 0.1 + 0.9j, -0.7 + 0.5j]),
    )
    modal_inputs = (
        np.asarray([0.2 + 0.5j, -0.6 + 0.1j, 0.7 - 0.3j, -0.1 + 0.8j]),
        np.asarray([-0.3 + 0.4j, 0.5 - 0.7j, 0.2 + 0.6j, 0.9 - 0.2j]),
    )
    try:
        assert H6_DEGREE == 3
        for side in ("bottom", "top"):
            bundle = _tiny_fixed_h6_bundle(side)
            bundles.append(bundle)
            bundle["adapter"] = FixedH6ActiveTraceAction(
                bundle["active_operator"], bundle["condensed"], bundle["h6"]
            )

        selected = bundles[0]["selected_full_rows"]
        assert np.array_equal(selected, np.asarray([0, 2, 4, 6]))
        for bundle in bundles:
            assert np.array_equal(bundle["selected_full_rows"], selected)
            bundle["matrix_before"] = _gather_matrix(bundle["h6_matrix"])
            bundle["dense_h6"] = _tiny_h6_dense_action(bundle["h6"])
        expected, bottom_feedback, top_feedback = _tiny_fixed_h6_modal_oracle(
            fixture,
            bundles[0]["dense_h6"],
            bundles[1]["dense_h6"],
            selected,
        )
        assert np.linalg.norm(bottom_feedback) > 0.0
        assert np.linalg.norm(top_feedback) > 0.0

        for bundle in bundles:
            adapter = bundle["adapter"]
            h6 = bundle["h6"]
            source = bundle["active_operator"].createVecRight()
            target = bundle["active_operator"].createVecLeft()
            alias_target = bundle["active_operator"].createVecLeft()
            active_h6 = bundle["dense_h6"][np.ix_(selected, selected)]
            try:
                _set_vector(source, inputs[0])
                source_before = _gather_vector(source)
                h6_applies = int(h6.apply_count)
                h6_mults = int(h6.matrix_mult_count)
                adapter_applies = adapter.audit["apply_count"]
                adapter_mults = adapter.audit["matrix_mult_count"]
                rank_target = source if MPI.COMM_WORLD.rank == 0 else alias_target
                with pytest.raises(
                    ValueError, match="source and target PETSc vectors alias"
                ) as alias_error:
                    adapter.apply(source, rank_target)
                alias_errors = MPI.COMM_WORLD.allgather(str(alias_error.value))
                assert len(set(alias_errors)) == 1
                assert "rank 0" in alias_errors[0]
                assert np.array_equal(_gather_vector(source), source_before)
                assert int(h6.apply_count) == h6_applies
                assert int(h6.matrix_mult_count) == h6_mults
                assert adapter.audit["apply_count"] == adapter_applies
                assert adapter.audit["matrix_mult_count"] == adapter_mults

                for values in (*inputs, inputs[0], np.zeros(4, dtype=np.complex128)):
                    _set_vector(source, values)
                    source_before = _gather_vector(source)
                    h6_applies = int(h6.apply_count)
                    h6_mults = int(h6.matrix_mult_count)
                    adapter.apply(source, target)
                    assert _relative_or_absolute(
                        _gather_vector(target), active_h6 @ values
                    ) <= 2.0e-12
                    assert np.array_equal(_gather_vector(source), source_before)
                    assert int(h6.apply_count) - h6_applies == 1
                    assert int(h6.matrix_mult_count) - h6_mults == 2
                assert adapter.audit["apply_count"] == 4
                assert adapter.audit["matrix_mult_count"] == 8
                assert "frozen for adapter lifetime" in adapter.audit[
                    "linearity_condition"
                ]
                assert adapter.audit["reentrant"] is False
                assert adapter.audit["h6_is_positive_surrogate"] is True
                assert adapter.audit["action"] == "J H6 J^H"
            finally:
                alias_target.destroy()
                target.destroy()
                source.destroy()

        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"], bundles[0]["adapter"], bundles[1]["adapter"]
        )
        vectors = (
            modal_inputs[0],
            modal_inputs[1],
            modal_inputs[0],
            np.zeros(4, dtype=np.complex128),
            (0.37 + 0.21j) * modal_inputs[0]
            + (-0.13 + 0.29j) * modal_inputs[1],
        )
        outputs = []
        for values in vectors:
            values_before = values.copy()
            h6_before = [int(bundle["h6"].apply_count) for bundle in bundles]
            mult_before = [int(bundle["h6"].matrix_mult_count) for bundle in bundles]
            output = modal_action.apply(values)
            outputs.append(output)
            assert _relative_or_absolute(output, expected @ values) <= 2.0e-12
            assert np.array_equal(values, values_before)
            assert [
                int(bundle["h6"].apply_count) - before
                for bundle, before in zip(bundles, h6_before, strict=True)
            ] == [1, 1]
            assert [
                int(bundle["h6"].matrix_mult_count) - before
                for bundle, before in zip(bundles, mult_before, strict=True)
            ] == [2, 2]
        assert _relative_or_absolute(outputs[2], outputs[0]) <= 2.0e-12
        assert np.linalg.norm(outputs[3]) <= 2.0e-12
        assert _relative_or_absolute(
            outputs[4], (0.37 + 0.21j) * outputs[0] + (-0.13 + 0.29j) * outputs[1]
        ) <= 2.0e-12
        for bundle in bundles:
            adapter = bundle["adapter"]
            assert adapter.audit["apply_count"] == 9
            assert adapter.audit["matrix_mult_count"] == 18
            assert np.array_equal(
                _gather_matrix(bundle["h6_matrix"]), bundle["matrix_before"]
            )

        modal_action.destroy()
        modal_action = None
        for bundle in bundles:
            adapter = bundle["adapter"]
            operator = bundle["active_operator"]
            h6 = bundle["h6"]
            window = bundle["window"]
            adapter.destroy()
            assert adapter.audit["destroyed"] is True
            assert h6.matrix is bundle["h6_matrix"]
            assert window.destroyed is False
            assert operator.isAssembled()
            h6.destroy()
            bundle["h6_destroyed"] = True
            assert window.destroyed is True
    finally:
        if modal_action is not None:
            modal_action.destroy()
        for bundle in bundles:
            adapter = bundle.get("adapter")
            if adapter is not None:
                adapter.destroy()
            h6 = bundle.get("h6")
            if h6 is not None:
                h6.destroy()
            operator = bundle.get("active_operator")
            if operator is not None:
                operator.destroy()
        _destroy_fixture(fixture)


def test_side_balh_block_factory_preserves_global_action_and_borrows_sides() -> None:
    fixture = _side_block_fixture()
    original_action = None
    original_context = None
    context = None
    q1 = q2 = q1_repeat = zero = None
    pc1 = pc2 = pc1_repeat = None
    original1 = original2 = None
    original_zero = pc_zero_expected = None
    full_rhs_before = full_rhs_after = None
    try:
        bottom = fixture["bottom"]
        top = fixture["top"]
        layout = fixture["layout"]
        coupling = fixture["coupling"]
        full_rhs_before = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        full_rhs_before_values = _gather_vector(full_rhs_before)
        layout_before = (
            layout.global_size,
            layout.local_size,
            layout.combined_offsets,
            layout.bottom_local_sizes,
            layout.top_local_sizes,
        )
        q1 = _pack(
            layout,
            bottom,
            top,
            np.asarray([1.0 + 0.2j, -0.3 + 0.5j, 0.7 - 0.4j, -0.2 + 0.1j]),
            np.asarray([-0.4 + 0.3j, 0.6 - 0.2j, 0.1 + 0.8j, -0.7 - 0.1j]),
            np.asarray([0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j]),
        )
        q2 = _pack(
            layout,
            bottom,
            top,
            np.asarray([-0.2 + 0.6j, 0.8 - 0.1j, -0.5 + 0.2j, 0.3 + 0.7j]),
            np.asarray([0.5 - 0.4j, -0.1 + 0.9j, 0.6 + 0.2j, -0.8 + 0.3j]),
            np.asarray([-0.6 + 0.2j, 0.3 + 0.8j, -0.4 - 0.5j, 0.9 + 0.1j]),
        )
        q1_repeat = q1.copy()
        q1_values = _gather_vector(q1)
        q2_values = _gather_vector(q2)
        zero = layout.create_vector()
        zero.set(0.0)
        original_action, original_context = create_hybrid_assembled_block_action(
            bottom,
            top,
            coupling,
        )
        original1 = original_action.createVecLeft()
        original2 = original_action.createVecLeft()
        original_action.mult(q1, original1)
        original_action.mult(q2, original2)
        original1_values = _gather_vector(original1)
        original2_values = _gather_vector(original2)
        columns, roles, contract_sha = _sample_contract()
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
        )
        inventory = context.inventory
        assert inventory["modal_block_name"] == (
            "finite_nonlinear_side_inverse_response_columns"
        )
        assert inventory["modal_schur_scope"] == "approximate_preconditioner_only"
        assert inventory["not_original_global_operator"] is True
        assert inventory["not_original_reduced_operator"] is True
        assert inventory["global_direct_factor_count"] == 0
        assert inventory["global_hybrid_direct_factor_count"] == 0
        assert inventory["p6_factor_count"] == 0
        assert inventory["p4_factor_count"] == 2
        assert inventory["nested_iterative_ksp_count"] == 2
        assert inventory["nested_iterative_ksp_created_count"] == 2
        assert inventory["nested_iterative_ksp_destroy_count"] == 0
        modal_diagnostics = inventory["modal_schur"]
        assert modal_diagnostics["build_apply_count"] == {"bottom": 12, "top": 12}
        assert modal_diagnostics["sampled_column_diagnostics"]["columns"] == columns
        assert modal_diagnostics["sampled_column_diagnostics"]["modal_batch_size"] == 32
        assert modal_diagnostics["sampled_column_diagnostics"]["early_sample_first"] is True
        assert modal_diagnostics["batch_diagnostics"]["early_sample"]["pass"] is True
        assert modal_diagnostics["batch_diagnostics"]["full_vs_first_sample"]["pass"] is True

        pc1 = layout.create_vector()
        pc2 = layout.create_vector()
        pc1_repeat = layout.create_vector()
        context.apply(None, q1, pc1)
        context.apply(None, q2, pc2)
        context.apply(None, q1_repeat, pc1_repeat)
        assert _relative_or_absolute(_gather_vector(pc1), _gather_vector(pc1_repeat)) <= 1.0e-12
        assert np.linalg.norm(_gather_vector(pc2)) > 0.0
        original_action.mult(q1, original1)
        original_action.mult(q2, original2)
        action1_diff = _relative_or_absolute(_gather_vector(original1), original1_values)
        action2_diff = _relative_or_absolute(_gather_vector(original2), original2_values)
        assert action1_diff <= 1.0e-12
        assert action2_diff <= 1.0e-12
        assert _relative_or_absolute(_gather_vector(q1), q1_values) <= 1.0e-12
        assert _relative_or_absolute(_gather_vector(q2), q2_values) <= 1.0e-12
        full_rhs_after = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        rhs_diff = _relative_or_absolute(
            _gather_vector(full_rhs_after), full_rhs_before_values
        )
        assert rhs_diff <= 1.0e-12
        assert layout_before == (
            layout.global_size,
            layout.local_size,
            layout.combined_offsets,
            layout.bottom_local_sizes,
            layout.top_local_sizes,
        )

        original_zero = original_action.createVecLeft()
        pc_zero_expected = layout.create_vector()
        original_action.mult(zero, original_zero)
        context.apply(None, zero, pc_zero_expected)
        assert _relative_or_absolute(
            _gather_vector(original_zero), np.zeros(layout.global_size, dtype=np.complex128)
        ) == 0.0
        assert _relative_or_absolute(
            _gather_vector(pc_zero_expected), np.zeros(layout.global_size, dtype=np.complex128)
        ) == 0.0
        assert context.inventory["pc_apply_count"] == 4
        if MPI.COMM_WORLD.rank == 0:
            print(
                "H1f action1/action2/RHS diffs="
                f"{action1_diff:.3e}/{action2_diff:.3e}/{rhs_diff:.3e}; "
                "limit=1.000e-12; Schur apply counts="
                f"{modal_diagnostics['build_apply_count']}",
                flush=True,
            )

        context.destroy()
        assert context.inventory["modal_schur"]["destroyed"] is True
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        fixture["bottom_inverse"].destroy()
        fixture["top_inverse"].destroy()
        after_side_destroy = context.inventory
        assert after_side_destroy["p4_factor_count"] == 0
        assert after_side_destroy["p4_factor_created_count"] == 2
        assert after_side_destroy["p4_factor_destroy_count"] == 2
        assert after_side_destroy["nested_iterative_ksp_count"] == 0
        assert after_side_destroy["nested_iterative_ksp_created_count"] == 2
        assert after_side_destroy["nested_iterative_ksp_destroy_count"] == 2
    finally:
        for vector in (
            original_zero,
            pc_zero_expected,
            pc1,
            pc2,
            pc1_repeat,
            q1,
            q2,
            q1_repeat,
            zero,
            original1,
            original2,
            full_rhs_before,
            full_rhs_after,
        ):
            if vector is not None:
                vector.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        if not fixture["bottom_inverse"].diagnostics["destroyed"]:
            fixture["bottom_inverse"].destroy()
        if not fixture["top_inverse"].diagnostics["destroyed"]:
            fixture["top_inverse"].destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_block_factory_releases_modal_on_constructor_error(monkeypatch) -> None:
    fixture = _side_block_fixture()
    built_modal = []
    real_builder = block_ldu.build_hybrid_action_modal_schur

    def capture_modal(*args, **kwargs):
        modal = real_builder(*args, **kwargs)
        built_modal.append(modal)
        return modal

    def fail_constructor(*_args, **_kwargs):
        raise RuntimeError("focused H1f constructor failure")

    monkeypatch.setattr(block_ldu, "build_hybrid_action_modal_schur", capture_modal)
    monkeypatch.setattr(block_ldu, "HybridBlockLduPreconditioner", fail_constructor)
    try:
        columns, roles, contract_sha = _sample_contract()
        with pytest.raises(RuntimeError, match="focused H1f constructor failure"):
            block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
            )
        assert len(built_modal) == 1
        assert built_modal[0].diagnostics["destroyed"] is True
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize(
    ("complex_qr_research", "expected_mixing_method"),
    [
        (False, "petsc_snes_anderson_default"),
        (True, "complex_qr_type_ii_research"),
    ],
)
def test_side_balh_anderson_inner_reuses_owner_factor_and_keeps_true_operator(
    monkeypatch, complex_qr_research: bool, expected_mixing_method: str
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = result = rhs = None
    action_before = action_after = None
    try:
        bottom = fixture["bottom"]
        top = fixture["top"]
        layout = fixture["layout"]
        coupling = fixture["coupling"]
        rhs = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        rhs_before = _gather_vector(rhs)
        original_action, original_context = create_hybrid_assembled_block_action(
            bottom,
            top,
            coupling,
        )
        action_before = original_action.createVecLeft()
        action_after = original_action.createVecLeft()
        original_action.mult(rhs, action_before)
        action_before_values = _gather_vector(action_before)

        def reject_full_schur(*_args, **_kwargs):
            raise AssertionError("on-demand modal inner must not build Schur columns")

        monkeypatch.setattr(
            block_ldu, "build_hybrid_action_modal_schur", reject_full_schur
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=complex_qr_research,
        )
        initial_inventory = context.inventory
        initial_inner = initial_inventory["modal_inner_solver"]
        assert initial_inner["mixing_method"] == expected_mixing_method
        assert context.modal_schur is None
        assert context.modal_constraint.shape == (
            layout.modal_count,
            layout.modal_count,
        )
        assert initial_inventory["modal_schur"] is None
        assert initial_inventory["modal_schur_materialized"] is False
        assert initial_inventory["modal_schur_storage_bytes"] == 0
        assert initial_inventory["modal_block_condition"] is None
        assert initial_inventory["early_sample_gate"]["status"] == "not_run"
        assert initial_inventory["early_sample_gate"]["pass"] is None
        assert "repeat_diagnostics" not in initial_inner
        assert initial_inventory["modal_count"] == layout.modal_count
        assert initial_inner["constraint_lu_factorizations"] == 1
        assert initial_inner["constraint_lu_owner_rank"] == layout.modal_owner
        assert (initial_inner["constraint_lu_local_bytes"] > 0) is (
            MPI.COMM_WORLD.rank == layout.modal_owner
        )

        with pytest.raises(ValueError, match="requires right-preconditioned FGMRES"):
            block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=10,
                    max_it=10,
                    ksp_type="gmres",
                    fixed_preconditioner=True,
                ),
            )

        result = block_ldu.solve_hybrid_block_ldu_iterative(
            original_action,
            rhs,
            context,
            config=block_ldu.HybridBlockLduIterativeConfig(
                restart=20,
                max_it=80,
                threshold=5.0e-9,
                ksp_type="fgmres",
            ),
        )
        original_action.mult(rhs, action_after)
        action_diff = _relative_or_absolute(
            _gather_vector(action_after), action_before_values
        )
        rhs_diff = _relative_or_absolute(_gather_vector(rhs), rhs_before)
        assert action_diff <= 1.0e-12
        assert rhs_diff <= 1.0e-12
        assert result.postsolve_audit["pass"] is True
        for key in (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        ):
            value = float(result.postsolve_audit[key])
            assert np.isfinite(value) and 0.0 <= value <= 5.0e-9
        inner = result.inventory["modal_inner_solver"]
        assert inner["last_solve"]["mixing_method"] == expected_mixing_method
        assert result.inventory["modal_schur"] is None
        assert inner["constraint_lu_factorizations"] == 1
        assert inner["last_solve"]["max_iterations"] == 14
        assert inner["last_solve"]["s_evaluation_count"] <= 16
        assert inner["solve_count"] == result.inventory["pc_apply_count"]
        assert inner["solve_count"] > 1
        assert inner["s_evaluation_count"] >= inner["solve_count"]
        assert all("modal_inner_solve_count" in row for row in result.history[1:])
        if MPI.COMM_WORLD.rank == 0:
            print(
                "on-demand modal inner: "
                f"PC={inner['solve_count']}, S={inner['s_evaluation_count']}, "
                f"C_LU=1@rank{layout.modal_owner}, "
                f"five_max={result.postsolve_audit['max_true_residual']:.3e}, "
                f"operator_diff={action_diff:.3e}, RHS_diff={rhs_diff:.3e}",
                flush=True,
            )
        result.destroy()
        assert context.inventory["modal_inner_solver"]["destroyed"] is True
        assert context.inventory["modal_inner_solver"]["constraint_lu_local_bytes"] == 0
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if result is not None and not result._destroyed:
            result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        for vector in (rhs, action_before, action_after):
            if vector is not None:
                vector.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_anderson_inner_failure_is_synchronized_without_fallback(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = rhs = outer_result = None
    try:
        layout = fixture["layout"]
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
        )
        rhs = layout.pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(fixture["coupling"]),
        )
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
        )
        before = {
            "bottom": fixture["bottom_inverse"].diagnostics["apply_count"],
            "top": fixture["top_inverse"].diagnostics["apply_count"],
        }
        solver_options = []

        def nonconverged(*_args, **kwargs):
            solver_options.append(dict(kwargs))
            return {
                "status": "not_converged",
                "stop_reason": "max_iterations",
                "solution": np.ones(context.modal_count, dtype=np.complex128),
                "unscaled_residual_norm": 0.25,
                "rhs_norm": 1.0,
                "relative_residual": 0.25,
                "iterations": 8,
                "max_iterations": 14,
                "function_evaluations": 8,
                "s_evaluation_count": 9,
                "constraint_lu_solve_calls": 8,
                "snes_converged_reason": int(
                    PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                ),
                "callback_converged_reason": int(
                    PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                ),
                "budget_exhausted": False,
                "side_action_calls": {"bottom": 0, "top": 0},
                "real_coordinate_embedding": True,
                "modal_coordinate_representation": (
                    "real_parts_then_imag_parts_in_complex128"
                ),
                "modal_coordinate_count": 2 * context.modal_count,
                "modal_coordinate_extra_bytes_per_explicit_vec": (
                    context.modal_count * np.dtype(PETSc.ScalarType).itemsize
                ),
                "modal_coordinate_extra_bytes_two_explicit_vecs": (
                    2 * context.modal_count * np.dtype(PETSc.ScalarType).itemsize
                ),
                "real_coordinate_subspace_violation": False,
                "residual_evaluation_history": [
                    {
                        "evaluation": 9,
                        "source": "final_validation",
                        "raw_residual_norm": 0.25,
                        "raw_target_metric": 0.25,
                        "finite": True,
                    }
                ],
            }

        monkeypatch.setattr(
            block_ldu, "solve_action_modal_schur_anderson", nonconverged
        )
        caught = None
        try:
            outer_result = block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=5,
                    max_it=5,
                    threshold=5.0e-9,
                    ksp_type="fgmres",
                ),
            )
        except (RuntimeError, PETSc.Error, ValueError) as exc:
            caught = exc
        local_inner = context.inventory["modal_inner_solver"]["last_solve"]
        outcomes = MPI.COMM_WORLD.allgather(
            (
                caught is not None,
                local_inner["stop_reason"],
                local_inner["unscaled_residual_norm"],
                local_inner["s_evaluation_count"],
            )
        )
        assert all(outcome[0] for outcome in outcomes)
        assert len(set(outcomes)) == 1
        assert len(solver_options) == 1
        assert solver_options[0]["max_iterations"] == 14
        assert context._destroyed is True
        assert context.inventory["pc_apply_count"] == 0
        assert context.inventory["modal_inner_solver"]["not_converged_count"] == 1
        failed_inner = context.inventory["modal_inner_solver"]["last_solve"]
        assert failed_inner["max_iterations"] == 14
        assert failed_inner["s_evaluation_count"] == 9
        assert failed_inner["s_evaluation_count"] <= 16
        assert failed_inner["residual_evaluation_history"]
        after = {
            "bottom": fixture["bottom_inverse"].diagnostics["apply_count"],
            "top": fixture["top_inverse"].diagnostics["apply_count"],
        }
        assert after["bottom"] - before["bottom"] == 1
        assert after["top"] - before["top"] == 1
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if outer_result is not None:
            outer_result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if rhs is not None:
            rhs.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_anderson_inner_repeats_frozen_sample_without_schur(monkeypatch):
    fixture = _side_block_fixture()
    context = None
    try:
        columns, roles, contract_sha = _sample_contract()
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        events = []

        def reject_full_schur(*_args, **_kwargs):
            raise AssertionError("sample gate must not build Schur columns")

        monkeypatch.setattr(
            block_ldu, "build_hybrid_action_modal_schur", reject_full_schur
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha,
            marker_callback=lambda event, detail: events.append(
                (event, dict(detail))
            ),
            use_anderson_modal_inner=True,
        )
        inventory = context.inventory
        gate = inventory["early_sample_gate"]
        assert gate["status"] == "passed"
        assert gate["pass"] is True
        assert gate["columns"] == columns
        assert gate["roles"] == roles
        assert gate["sha256"] == contract_sha
        assert gate["early_sample_repeat"]["finite"] is True
        assert gate["early_sample_repeat"]["limit"] == 1.0e-10
        assert gate["early_sample_repeat"]["pass"] is True
        assert gate["full_vs_sample"] == (
            "not_applicable_full_schur_not_materialized"
        )
        for key in ("full_vs_sample", "schur_lu_repeat"):
            assert inventory[key]["status"] == "not_applicable"
            assert "pass" not in inventory[key]
        assert inventory["modal_schur"] is None
        assert inventory["modal_schur_materialized"] is False
        assert inventory["modal_schur_column_count"] == 0
        assert [event for event, _ in events] == [
            "modal_sample_begin",
            "modal_sample_ready",
        ]
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert all(
            after[side] - before[side] == 2 * len(columns)
            for side in ("bottom", "top")
        )
        context.destroy()
        context = None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if context is not None:
            context.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_anderson_inner_stops_before_outer_on_sample_repeat_failure(
    monkeypatch,
):
    fixture = _side_block_fixture()
    try:
        columns, roles, contract_sha = _sample_contract()
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        original_apply = block_ldu.HybridActionModalSchurApply.apply
        call_count = 0

        def nonrepeating_apply(modal_action, modal_values):
            nonlocal call_count
            call_count += 1
            result = original_apply(modal_action, modal_values)
            if call_count > len(columns):
                result[0] += 1.0e-5
            return result

        monkeypatch.setattr(
            block_ldu.HybridActionModalSchurApply,
            "apply",
            nonrepeating_apply,
        )
        with pytest.raises(ValueError, match="Early sampled modal repeat Gate failed"):
            block_ldu.create_side_balh_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                fixture["bottom_inverse"],
                fixture["top_inverse"],
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
                use_anderson_modal_inner=True,
            )
        assert call_count == 2 * len(columns)
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert all(
            after[side] - before[side] == 2 * len(columns)
            for side in ("bottom", "top")
        )
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        _destroy_side_block_fixture(fixture)


def test_modal_real_coordinate_embedding_is_isometric_for_complex_values() -> None:
    modal_values = np.asarray(
        [0.4 + 0.3j, -0.2 + 0.8j, 0.7 - 0.6j, -0.5 - 0.1j],
        dtype=np.complex128,
    )
    original = modal_values.copy()

    coordinates = block_ldu._encode_modal_real_coordinates(modal_values)
    restored = block_ldu._decode_modal_real_coordinates(
        coordinates, modal_values.size
    )

    assert coordinates.shape == (2 * modal_values.size,)
    assert coordinates.dtype == np.complex128
    assert np.all(coordinates.imag == 0.0)
    assert np.array_equal(restored, modal_values)
    assert np.linalg.norm(coordinates) == pytest.approx(
        np.linalg.norm(modal_values), rel=0.0, abs=1.0e-15
    )
    assert np.array_equal(modal_values, original)
    assert (
        block_ldu.solve_action_modal_schur_anderson.__kwdefaults__[
            "real_coordinate_embedding"
        ]
        is False
    )
    assert (
        block_ldu.solve_action_modal_schur_anderson.__kwdefaults__[
            "max_iterations"
        ]
        == 8
    )


def test_side_balh_modal_inner_explicitly_selects_real_coordinates(monkeypatch) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    original_rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    rhs_before = original_rhs.copy()
    captured = {}

    def solver_stub(action, rhs, **kwargs):
        captured["action"] = action
        captured["rhs"] = np.asarray(rhs, dtype=np.complex128).copy()
        captured["kwargs"] = dict(kwargs)
        return {
            "status": "not_converged",
            "stop_reason": "synthetic_route_probe",
            "solution": np.asarray(rhs, dtype=np.complex128).copy(),
            "unscaled_residual_norm": 1.0,
            "rhs_norm": float(np.linalg.norm(rhs)),
            "relative_residual": 1.0,
            "iterations": 0,
            "max_iterations": 14,
            "function_evaluations": 0,
            "s_evaluation_count": 0,
            "constraint_lu_solve_calls": 0,
            "snes_converged_reason": int(
                PETSc.SNES.ConvergedReason.DIVERGED_INNER
            ),
            "callback_converged_reason": int(
                PETSc.SNES.ConvergedReason.DIVERGED_INNER
            ),
            "budget_exhausted": False,
            "side_action_calls": {"bottom": 0, "top": 0},
            "residual_evaluation_history": [],
            "real_coordinate_embedding": True,
            "modal_coordinate_representation": (
                "real_parts_then_imag_parts_in_complex128"
            ),
            "modal_coordinate_count": 2 * len(rhs),
            "modal_coordinate_extra_bytes_per_explicit_vec": (
                len(rhs) * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": (
                2 * len(rhs) * np.dtype(PETSc.ScalarType).itemsize
            ),
            "real_coordinate_subspace_violation": False,
        }

    monkeypatch.setattr(
        block_ldu, "solve_action_modal_schur_anderson", solver_stub
    )
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
        )
        with pytest.raises(RuntimeError, match="synthetic_route_probe"):
            modal_system.solve(original_rhs)

        assert np.array_equal(original_rhs, rhs_before)
        assert captured["action"] is modal_action
        assert np.array_equal(captured["rhs"], original_rhs)
        assert captured["kwargs"]["scale_residual_by_constraint"] is True
        assert captured["kwargs"]["real_coordinate_embedding"] is True
        assert captured["kwargs"]["max_iterations"] == 14
        assert captured["kwargs"]["_borrowed_constraint_factor"] is modal_system
        diagnostics = modal_system.diagnostics
        assert diagnostics["real_coordinate_embedding"] is True
        assert diagnostics["modal_coordinate_count"] == 2 * modal_system.modal_count
        assert diagnostics["modal_coordinate_extra_bytes_per_explicit_vec"] == (
            modal_system.modal_count * np.dtype(PETSc.ScalarType).itemsize
        )
        assert diagnostics["modal_coordinate_extra_bytes_two_explicit_vecs"] == (
            2 * modal_system.modal_count * np.dtype(PETSc.ScalarType).itemsize
        )
        assert diagnostics["constraint_lu_factorizations"] == 1
        assert diagnostics["not_converged_count"] == 1
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


def test_complex_qr_anderson_coefficients_match_independent_complex_lstsq() -> None:
    delta_f = np.asarray(
        [
            [1.0 + 0.5j, -0.2 + 0.9j, 0.7 - 0.4j],
            [0.3 - 0.8j, 1.1 + 0.2j, -0.6 + 0.5j],
            [-0.4 + 0.6j, 0.8 - 0.3j, 0.2 + 1.0j],
            [0.9 + 0.1j, -0.5 - 0.7j, 1.2 + 0.3j],
        ],
        dtype=np.complex128,
    )
    current_f = np.asarray(
        [0.2 + 0.7j, -0.9 + 0.1j, 0.5 - 0.6j, 0.3 + 0.4j],
        dtype=np.complex128,
    )
    original_matrix = delta_f.copy()
    original_vector = current_f.copy()

    coefficients, diagnostics = block_ldu._complex_anderson_qr_coefficients(
        delta_f, current_f
    )
    _, capture_diagnostics = block_ldu._complex_anderson_candidate_update(
        np.zeros(delta_f.shape[0], dtype=np.complex128),
        current_f,
        np.zeros_like(delta_f),
        delta_f,
        capture_coefficients=True,
    )
    expected = np.linalg.lstsq(delta_f, current_f, rcond=None)[0]
    fit_residual = delta_f @ coefficients - current_f

    assert diagnostics["effective_rank"] == delta_f.shape[1]
    assert diagnostics["discarded_column_count"] == 0
    assert np.array_equal(capture_diagnostics["_capture_gamma"], coefficients)
    assert np.allclose(coefficients, expected, rtol=2.0e-13, atol=2.0e-14)
    assert np.linalg.norm(delta_f.conj().T @ fit_residual) <= 2.0e-13
    assert np.linalg.norm(fit_residual) == pytest.approx(
        np.linalg.norm(delta_f @ expected - current_f), rel=2.0e-13, abs=2.0e-14
    )
    assert np.array_equal(delta_f, original_matrix)
    assert np.array_equal(current_f, original_vector)


def test_complex_qr_raw_metric_changes_gamma_objective_only() -> None:
    modal = np.asarray([0.2 + 0.4j, -0.3 + 0.1j, 0.7 - 0.2j], dtype=np.complex128)
    fixed_point = np.asarray([0.1 - 0.2j, 0.4 + 0.3j, -0.2 + 0.6j])
    delta_m = np.asarray(
        [[0.3 + 0.1j, -0.2 + 0.4j], [0.5 - 0.2j, 0.1 + 0.7j], [-0.4 + 0.3j, 0.6 - 0.1j]],
        dtype=np.complex128,
    )
    delta_f = np.asarray(
        [[0.2 + 0.8j, -0.5 + 0.1j], [0.9 - 0.4j, 0.3 + 0.6j], [-0.1 + 0.2j, 0.7 - 0.5j]],
        dtype=np.complex128,
    )
    raw_residual = np.asarray([0.6 + 0.2j, -0.1 + 0.9j, 0.4 - 0.7j])
    delta_raw = np.asarray(
        [[0.8 + 0.1j, -0.3 + 0.5j], [0.2 - 0.6j, 0.7 + 0.2j], [-0.5 + 0.4j, 0.1 + 0.9j]],
        dtype=np.complex128,
    )
    originals = tuple(
        values.copy() for values in (modal, fixed_point, delta_m, delta_f, raw_residual, delta_raw)
    )

    raw_candidate, raw_info = block_ldu._complex_anderson_candidate_update(
        modal,
        fixed_point,
        delta_m,
        delta_f,
        capture_coefficients=True,
        mixing_metric="raw_residual",
        raw_residual=raw_residual,
        delta_raw_residual=delta_raw,
    )
    expected_gamma = np.linalg.lstsq(delta_raw, raw_residual, rcond=None)[0]
    expected_fit = delta_raw @ expected_gamma - raw_residual
    expected_candidate = modal + fixed_point - (delta_m + delta_f) @ expected_gamma

    assert raw_info["mixing_metric"] == "raw_residual"
    assert raw_info["effective_rank"] == delta_raw.shape[1]
    assert np.allclose(raw_info["_capture_gamma"], expected_gamma, rtol=2.0e-13, atol=2.0e-14)
    assert np.linalg.norm(delta_raw.conj().T @ expected_fit) <= 2.0e-13
    assert raw_info["fit_residual_norm"] == pytest.approx(
        np.linalg.norm(expected_fit), rel=2.0e-13, abs=2.0e-14
    )
    assert np.allclose(raw_candidate, expected_candidate, rtol=2.0e-13, atol=2.0e-14)
    assert all(np.array_equal(actual, before) for actual, before in zip(
        (modal, fixed_point, delta_m, delta_f, raw_residual, delta_raw), originals
    ))

    identity_scaled, scaled_info = block_ldu._complex_anderson_candidate_update(
        modal,
        -raw_residual,
        delta_m,
        -delta_raw,
        capture_coefficients=True,
    )
    identity_raw, identity_info = block_ldu._complex_anderson_candidate_update(
        modal,
        -raw_residual,
        delta_m,
        -delta_raw,
        capture_coefficients=True,
        mixing_metric="raw_residual",
        raw_residual=raw_residual,
        delta_raw_residual=delta_raw,
    )
    assert scaled_info["mixing_metric"] == "C_scaled_residual"
    assert identity_info["mixing_metric"] == "raw_residual"
    assert np.allclose(
        scaled_info["_capture_gamma"], identity_info["_capture_gamma"],
        rtol=2.0e-13, atol=2.0e-14,
    )
    assert np.allclose(identity_scaled, identity_raw, rtol=2.0e-13, atol=2.0e-14)
    with pytest.raises(FloatingPointError, match="Raw Anderson residual is non-finite"):
        block_ldu._complex_anderson_candidate_update(
            modal,
            fixed_point,
            delta_m,
            delta_f,
            mixing_metric="raw_residual",
            raw_residual=np.full(modal.shape, np.nan + 0.0j),
            delta_raw_residual=delta_raw,
        )


def test_complex_qr_anderson_startup_rank_deficiency_and_nonfinite_history() -> None:
    modal = np.asarray([0.2 + 0.3j, -0.4 + 0.1j], dtype=np.complex128)
    fixed_point = np.asarray([0.05 - 0.2j, 0.3 + 0.4j], dtype=np.complex128)
    startup, startup_info = block_ldu._complex_anderson_candidate_update(
        modal, fixed_point, None, None
    )
    assert np.array_equal(startup, modal + fixed_point)
    assert startup_info["update"] == "fixed_point_startup"
    assert startup_info["history_column_count"] == 0

    independent = np.asarray([1.0 + 1.0j, 0.5 - 0.2j], dtype=np.complex128)
    dependent_history = np.column_stack((independent, 2.0 * independent))
    delta_m = np.column_stack(
        (
            np.asarray([0.3 + 0.2j, -0.1 + 0.5j]),
            np.asarray([-0.2 + 0.4j, 0.7 - 0.3j]),
        )
    ).astype(np.complex128)
    target = np.asarray([0.8 - 0.1j, -0.6 + 0.9j], dtype=np.complex128)
    candidate, rank_info = block_ldu._complex_anderson_candidate_update(
        modal, target, delta_m, dependent_history
    )
    expected_fit = np.linalg.lstsq(dependent_history, target, rcond=None)[0]
    expected_fit_residual = dependent_history @ expected_fit - target
    assert candidate is not None
    assert rank_info["effective_rank"] == 1
    assert rank_info["discarded_column_count"] == 1
    assert rank_info["fit_residual_norm"] == pytest.approx(
        np.linalg.norm(expected_fit_residual), rel=2.0e-13, abs=2.0e-14
    )

    zero_candidate, zero_info = block_ldu._complex_anderson_candidate_update(
        modal,
        fixed_point,
        np.zeros((modal.size, 1), dtype=np.complex128),
        np.zeros((modal.size, 1), dtype=np.complex128),
    )
    assert zero_candidate is None
    assert zero_info["update"] == "rank_zero_history"
    assert zero_info["effective_rank"] == 0
    with pytest.raises(FloatingPointError, match="history is non-finite"):
        block_ldu._complex_anderson_qr_coefficients(
            np.asarray([[np.nan + 0.0j], [1.0 + 0.0j]]),
            np.asarray([0.5 + 0.1j, -0.2 + 0.3j]),
        )


@pytest.mark.parametrize(
    ("raw_metric_mixing", "capture_trace", "expected_metric"),
    [
        (False, True, "C_scaled_residual"),
        (True, False, "raw_residual"),
    ],
)
def test_side_balh_complex_qr_modal_inner_keeps_raw_gate_and_borrows_sides(
    raw_metric_mixing: bool,
    capture_trace: bool,
    expected_metric: str,
) -> None:
    fixture = _side_block_fixture()
    context = None
    modal_system = None
    modal_action = None
    solution = None
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    assert np.linalg.norm(rhs) > 0.0
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    try:
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
            capture_modal_solve_trace=capture_trace,
        )
        modal_system = context.action_modal_schur_system
        modal_action = modal_system.modal_action
        assert modal_system.diagnostics["mixing_method"] == (
            "complex_qr_type_ii_research"
        )
        assert modal_system.diagnostics["mixing_metric"] == expected_metric
        assert modal_system.diagnostics["real_coordinate_embedding"] is False
        oversized_rhs = np.full(rhs.shape, 1.0e308 + 0.0j, dtype=np.complex128)
        with pytest.raises(ValueError, match="RHS norm is non-finite"):
            modal_system.solve(oversized_rhs)
        assert {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        } == before
        try:
            solution = modal_system.solve(rhs)
        except RuntimeError as exc:
            assert "Modal Anderson inner solve did not converge" in str(exc)

        diagnostics = modal_system.diagnostics
        last_solve = diagnostics["last_solve"]
        assert last_solve["mixing_method"] == "complex_qr_type_ii_research"
        assert last_solve["mixing_metric"] == expected_metric
        assert last_solve["mixing_beta"] == 1.0
        assert last_solve["real_coordinate_embedding"] is False
        assert last_solve["modal_coordinate_representation"] == "complex128_modal_values"
        assert last_solve["max_iterations"] == 14
        assert last_solve["anderson_history"] == 4
        assert 1 <= last_solve["iterations"] <= 14
        assert 2 <= last_solve["s_evaluation_count"] <= 16
        assert last_solve["constraint_lu_solve_calls"] == last_solve[
            "s_evaluation_count"
        ]
        assert last_solve["constraint_lu_factorizations"] == 0
        assert last_solve["constraint_lu_borrowed"] is True
        assert last_solve["residual_evaluation_history"][-1]["source"] == (
            "final_validation"
        )
        assert last_solve["residual_evaluation_history"][0]["source"] == (
            "complex_qr_iteration"
        )
        assert last_solve["complex_qr_mixing_history"][0]["update"] == (
            "fixed_point_startup"
        )
        assert np.isfinite(last_solve["relative_residual"])
        expected_success = (
            last_solve["convergence_callback_target_reached"] is True
            and last_solve["final_unscaled_target_reached"] is True
            and last_solve["target_reached"] is True
            and last_solve["budget_exhausted"] is False
            and last_solve["invalid_failure"] is False
            and last_solve["stop_reason"] == "unscaled_residual_target"
        )
        assert (solution is not None) is expected_success
        if solution is not None:
            assert np.all(np.isfinite(solution))
            assert last_solve["status"] == "converged"
            assert last_solve["relative_residual"] <= 1.0e-2
        else:
            assert last_solve["status"] == "not_converged"
        assert np.array_equal(rhs, rhs_before)
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        for side in ("bottom", "top"):
            actual_calls = after[side] - before[side]
            assert actual_calls == last_solve["side_action_calls"][side]
            assert actual_calls == last_solve["s_evaluation_count"]
            assert diagnostics["side_action_call_count"][side] == actual_calls
        assert diagnostics["constraint_lu_factorizations"] == 1
        capture = modal_system.export_modal_solve_capture(MPI.COMM_WORLD)
        if capture_trace:
            if MPI.COMM_WORLD.rank == 0:
                assert capture["capture_status"] == "incomplete"
                assert [row["solve_id"] for row in capture["traces"]] == [1, 2]
                assert capture["traces"][0]["capture_complete"] is False
                real_solve_trace = capture["traces"][1]
                assert real_solve_trace["rhs_sha256"] == hashlib.sha256(
                    rhs.tobytes()
                ).hexdigest()
                assert real_solve_trace["s_evaluation_count"] == len(
                    real_solve_trace["evaluations"]
                )
                if last_solve["iterations"] > 1:
                    assert any(
                        update.get("gamma") is not None
                        for update in real_solve_trace["updates"]
                    )
            else:
                assert capture is None
        else:
            assert capture is None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
        if MPI.COMM_WORLD.rank == 0:
            print(
                "complex QR modal candidate: "
                f"status={last_solve['status']}, raw={last_solve['relative_residual']:.6e}, "
                f"iterations={last_solve['iterations']}, S={last_solve['s_evaluation_count']}, "
                f"side_calls={last_solve['side_action_calls']}, "
                f"mixing={last_solve['mixing_metric']}, "
                f"mixing_steps={len(last_solve['complex_qr_mixing_history'])}",
                flush=True,
            )
    finally:
        if context is not None and not context._destroyed:
            context.destroy()
        elif modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize("raw_metric_mixing", [False, True])
def test_side_balh_complex_qr_budget_reserves_real_final_check(
    monkeypatch, raw_metric_mixing: bool
) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    monkeypatch.setattr(block_ldu, "_MODAL_ANDERSON_S_EVALUATION_LIMIT", 2)
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
        )
        with pytest.raises(RuntimeError, match="did not converge"):
            modal_system.solve(rhs)

        last_solve = modal_system.diagnostics["last_solve"]
        assert last_solve["status"] == "not_converged"
        assert last_solve["mixing_metric"] == (
            "raw_residual" if raw_metric_mixing else "C_scaled_residual"
        )
        assert last_solve["stop_reason"] == "budget_exhausted"
        assert last_solve["budget_exhausted"] is True
        assert last_solve["budget_reason"] == "S_EVALUATION_LIMIT"
        assert last_solve["invalid_failure"] is False
        assert last_solve["convergence_callback_target_reached"] is False
        assert last_solve["final_validation_evaluations"] == 1
        assert last_solve["budget_callback_skipped"] is False
        assert last_solve["function_evaluations"] == 1
        assert last_solve["iterations"] == 1
        assert last_solve["s_evaluation_count"] == 2
        assert [
            row["source"] for row in last_solve["residual_evaluation_history"]
        ] == ["complex_qr_iteration", "final_validation"]
        assert last_solve["constraint_lu_solve_calls"] == 2
        assert last_solve["constraint_lu_borrowed"] is True
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {
            side: after[side] - before[side] for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {"bottom": 2, "top": 2}
        assert np.array_equal(rhs, rhs_before)
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


@pytest.mark.parametrize("raw_metric_mixing", [False, True])
def test_side_balh_complex_qr_zero_rhs_uses_absolute_raw_gate(
    raw_metric_mixing: bool,
) -> None:
    fixture = _side_block_fixture()
    modal_action = None
    modal_system = None
    rhs = np.zeros(fixture["layout"].modal_count, dtype=np.complex128)
    rhs_before = rhs.copy()
    before = {
        side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
        for side in ("bottom", "top")
    }
    try:
        modal_action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        modal_system = block_ldu.HybridActionModalSchurAndersonSystem(
            modal_action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            raw_metric_mixing=raw_metric_mixing,
        )
        solution = modal_system.solve(rhs)
        last_solve = modal_system.diagnostics["last_solve"]
        assert np.array_equal(solution, np.zeros_like(solution))
        assert last_solve["status"] == "converged"
        assert last_solve["mixing_metric"] == (
            "raw_residual" if raw_metric_mixing else "C_scaled_residual"
        )
        assert last_solve["stop_reason"] == "unscaled_residual_target"
        assert last_solve["zero_rhs_absolute_residual"] is True
        assert last_solve["rhs_norm"] == 0.0
        assert last_solve["relative_residual"] == 0.0
        assert last_solve["convergence_callback_target_reached"] is True
        assert last_solve["final_unscaled_target_reached"] is True
        assert last_solve["budget_exhausted"] is False
        assert last_solve["invalid_failure"] is False
        assert last_solve["iterations"] == 0
        assert last_solve["function_evaluations"] == 1
        assert last_solve["final_validation_evaluations"] == 1
        assert last_solve["s_evaluation_count"] == 2
        assert last_solve["constraint_lu_solve_calls"] == 2
        assert last_solve["constraint_lu_borrowed"] is True
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {
            side: after[side] - before[side] for side in ("bottom", "top")
        }
        assert last_solve["side_action_calls"] == {"bottom": 2, "top": 2}
        assert np.array_equal(rhs, rhs_before)
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_action is not None and not modal_action._destroyed:
            modal_action.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_modal_trace_keeps_two_solves_and_gathers_owner_payload(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    rhs = np.asarray(
        [0.2 + 0.4j, -0.5 + 0.1j, 0.7 - 0.3j, -0.2 - 0.6j],
        dtype=np.complex128,
    )
    original_rhs = rhs.copy()
    owned_objects = []

    def run_two_solves(capture: bool):
        action = block_ldu.HybridActionModalSchurApply(
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
        )
        system = block_ldu.HybridActionModalSchurAndersonSystem(
            action,
            modal_owner=fixture["layout"].modal_owner,
            complex_qr_research=True,
            capture_modal_solve_trace=capture,
        )
        owned_objects.append(system)
        before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        solutions = []
        summaries = []
        errors = []
        for _ in range(2):
            try:
                solutions.append(system.solve(rhs).copy())
                errors.append(None)
            except RuntimeError as exc:
                solutions.append(None)
                errors.append(str(exc))
            summaries.append(copy.deepcopy(system.diagnostics["last_solve"]))
        after = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        calls = {side: after[side] - before[side] for side in ("bottom", "top")}
        return system, solutions, summaries, errors, calls

    try:
        off_system, off_solutions, off_summaries, off_errors, off_calls = (
            run_two_solves(False)
        )
        assert off_system.export_modal_solve_capture(MPI.COMM_WORLD) is None
        on_system, on_solutions, on_summaries, on_errors, on_calls = (
            run_two_solves(True)
        )
        calls_before_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        capture = on_system.export_modal_solve_capture(MPI.COMM_WORLD)
        calls_after_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert off_calls == on_calls
        assert off_calls == {
            side: sum(summary["side_action_calls"][side] for summary in off_summaries)
            for side in ("bottom", "top")
        }
        assert calls_before_export == calls_after_export
        assert np.array_equal(rhs, original_rhs)
        assert off_errors == on_errors
        for off_solution, on_solution, off_summary, on_summary in zip(
            off_solutions, on_solutions, off_summaries, on_summaries
        ):
            assert off_summary["status"] == on_summary["status"]
            assert off_summary["stop_reason"] == on_summary["stop_reason"]
            assert off_summary["target_reached"] == on_summary["target_reached"]
            assert off_summary["unscaled_residual_norm"] == pytest.approx(
                on_summary["unscaled_residual_norm"], rel=0.0, abs=0.0
            )
            off_scaled = off_summary["residual_evaluation_history"][-1][
                "scaled_residual_norm"
            ]
            on_scaled = on_summary["residual_evaluation_history"][-1][
                "scaled_residual_norm"
            ]
            assert off_scaled == pytest.approx(on_scaled, rel=0.0, abs=0.0)
            assert off_summary["s_evaluation_count"] == on_summary["s_evaluation_count"]
            assert off_summary["side_action_calls"] == on_summary["side_action_calls"]
            assert off_summary["relative_residual"] == pytest.approx(
                on_summary["relative_residual"], rel=0.0, abs=0.0
            )
            assert (off_solution is None) == (on_solution is None)
            if off_solution is not None:
                assert np.array_equal(off_solution, on_solution)
                assert off_summary["status"] == "converged"
                assert off_summary["relative_residual"] <= 1.0e-2
        if MPI.COMM_WORLD.rank == 0:
            assert capture["owner_rank"] == fixture["layout"].modal_owner
            assert capture["writer_rank"] == 0
            assert [row["solve_id"] for row in capture["traces"]] == [1, 2]
            assert [row["rhs_sha256"] for row in capture["traces"]] == [
                hashlib.sha256(rhs.tobytes()).hexdigest()
            ] * 2
            assert capture["array_payload_bytes"] <= capture[
                "array_payload_limit_bytes"
            ]
            assert capture["array_payload_limit_bytes"] == (
                block_ldu._modal_trace_array_limit_bytes(rhs.size)
            )
            assert capture["serialized_payload_size_basis"] == "compact_utf8_json"
            encoded_capture_size = len(
                json.dumps(
                    capture,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            assert encoded_capture_size <= capture[
                "serialized_payload_limit_bytes"
            ]
            assert capture["capture_complete"] is True
            assert capture["capture_status"] == "complete"
            for trace, summary in zip(capture["traces"], on_summaries):
                assert summary["status"] in {"converged", "not_converged"}
                assert trace["solver_status"] == summary["status"]
                assert trace["solver_stop_reason"] == summary["stop_reason"]
                assert trace["s_evaluation_count"] == summary["s_evaluation_count"]
                assert trace["capture_complete"] is True
                assert trace.get("capture_incomplete_reason") is None
                assert trace["g"] is not None
                assert len(trace["evaluations"]) == summary["s_evaluation_count"]
                assert all(
                    row["capture_complete"] is True
                    and all(row.get(key) is not None for key in ("m", "raw", "scaled"))
                    for row in trace["evaluations"]
                )
                assert trace["evaluations"][-1]["raw_target_metric"] == pytest.approx(
                    summary["relative_residual"], rel=0.0, abs=0.0
                )
                encoded = trace["g"]
                encoded_arrays = [encoded]
                encoded_arrays.extend(
                    row[key]
                    for row in trace["evaluations"]
                    for key in ("m", "raw", "scaled")
                    if row.get(key) is not None
                )
                encoded_arrays.extend(
                    row["gamma"]
                    for row in trace["updates"]
                    if row.get("gamma") is not None
                )
                trace_array_bytes = 0
                for descriptor in encoded_arrays:
                    raw = base64.b64decode(descriptor["data"], validate=True)
                    assert descriptor["dtype"] == "complex128"
                    assert descriptor["order"] == "C"
                    assert hashlib.sha256(raw).hexdigest() == descriptor["sha256"]
                    assert len(raw) == (
                        np.prod(descriptor["shape"]) * np.dtype(np.complex128).itemsize
                    )
                    trace_array_bytes += len(raw)
                assert trace_array_bytes == trace["captured_array_bytes"]
                g_raw = base64.b64decode(encoded["data"], validate=True)
                assert np.array_equal(
                    np.frombuffer(g_raw, dtype=np.complex128).reshape(encoded["shape"]),
                    rhs,
                )
                iteration_rows = [
                    row
                    for row in trace["evaluations"]
                    if row["source"] == "complex_qr_iteration"
                ]
                gamma_updates = [
                    row for row in trace["updates"] if row.get("gamma") is not None
                ]
                assert gamma_updates
                for update in gamma_updates:
                    source_count = update["source_evaluation_index"]
                    states = [
                        row
                        for row in iteration_rows
                        if row["evaluation"] <= source_count
                    ][-block_ldu._MODAL_SOLVE_TRACE_HISTORY_LIMIT - 1 :]
                    fixed_point_history = [
                        -np.frombuffer(
                            base64.b64decode(row["scaled"]["data"], validate=True),
                            dtype=np.complex128,
                        ).reshape(row["scaled"]["shape"])
                        for row in states
                    ]
                    delta_f = np.column_stack(
                        [
                            fixed_point_history[index + 1] - fixed_point_history[index]
                            for index in range(len(fixed_point_history) - 1)
                        ]
                    )
                    rcond = np.finfo(np.float64).eps * max(delta_f.shape)
                    expected_gamma, _, oracle_rank, _ = np.linalg.lstsq(
                        delta_f, fixed_point_history[-1], rcond=rcond
                    )
                    encoded_gamma = update["gamma"]
                    decoded_gamma = np.frombuffer(
                        base64.b64decode(encoded_gamma["data"], validate=True),
                        dtype=np.complex128,
                    ).reshape(encoded_gamma["shape"])
                    actual_fit = delta_f @ decoded_gamma - fixed_point_history[-1]
                    oracle_fit = delta_f @ expected_gamma - fixed_point_history[-1]
                    assert np.allclose(
                        delta_f @ decoded_gamma,
                        delta_f @ expected_gamma,
                        rtol=2.0e-13,
                        atol=2.0e-14,
                    )
                    assert np.linalg.norm(actual_fit) == pytest.approx(
                        np.linalg.norm(oracle_fit), rel=2.0e-13, abs=2.0e-14
                    )
                    if oracle_rank == delta_f.shape[1]:
                        assert update["mixing_scalars"]["effective_rank"] == oracle_rank
                        assert np.allclose(
                            decoded_gamma,
                            expected_gamma,
                            rtol=2.0e-13,
                            atol=2.0e-14,
                        )
                        orthogonality = np.linalg.norm(delta_f.conj().T @ actual_fit)
                        orthogonality_scale = max(
                            1.0,
                            np.linalg.norm(delta_f)
                            * np.linalg.norm(fixed_point_history[-1]),
                        )
                        assert orthogonality <= 5.0e-13 * orthogonality_scale
                for side in ("bottom", "top"):
                    side_rows = [
                        item["side_actions"][side]
                        for item in trace["evaluations"]
                    ]
                    assert all(
                        row["audit_index"] == "unknown"
                        and row["apply_count_source"] == "action_apply_count"
                        and row["apply_count"] > 0
                        for row in side_rows
                    )
                    last_applies = [row["last_apply"] for row in side_rows]
                    assert all(
                        "residual_norm" in row
                        and "iterations" in row
                        and "reason" in row
                        for row in last_applies
                    )
                    zero_rhs_records = [
                        row
                        for row in last_applies
                        if row["status"] == "ZERO_RHS_EXACT"
                    ]
                    assert zero_rhs_records
                    assert all(
                        row["reason"] is None
                        and row["iterations"] == 0
                        and row["rhs_norm"] == 0.0
                        and row["residual_norm"] == 0.0
                        for row in zero_rhs_records
                    )
                    nonzero_ksp_records = [
                        row for row in last_applies if row["rhs_norm"] > 0.0
                    ]
                    assert nonzero_ksp_records
                    assert all(
                        row["reason"] is not None and row["iterations"] > 0
                        for row in nonzero_ksp_records
                    )
            assert capture["serialized_payload_limit_bytes"] == 640 * 1024
            assert capture["array_payload_bytes"] == sum(
                trace["captured_array_bytes"] for trace in capture["traces"]
            )
        else:
            assert capture is None
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            assert on_system._modal_solve_trace_records == []

        overflow_solver_state = {
            "status": "not_converged",
            "stop_reason": "synthetic_existing_failure",
            "error": "original solver error remains unchanged " + ("x" * 4096),
        }
        on_system._last_solve = copy.deepcopy(overflow_solver_state)
        overflow_records = [
            {
                "solve_id": solve_id,
                "captured_array_bytes": 0,
                "capture_complete": True,
                "capture_incomplete_reason": None,
                "evaluations": [],
                "updates": [],
                "solver_status": overflow_solver_state["status"],
                "solver_stop_reason": overflow_solver_state["stop_reason"],
                "solver_error": overflow_solver_state["error"],
            }
            for solve_id in (1, 2)
        ]
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            on_system._modal_solve_trace_records.extend(
                copy.deepcopy(overflow_records)
            )
        monkeypatch.setattr(
            block_ldu, "_MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES", 2048
        )
        overflow_capture = on_system.export_modal_solve_capture(MPI.COMM_WORLD)
        assert on_system.diagnostics["last_solve"] == overflow_solver_state
        if MPI.COMM_WORLD.rank == 0:
            assert overflow_capture["capture_status"] == "incomplete"
            assert overflow_capture["capture_complete"] is False
            assert overflow_capture["capture_incomplete_reason"] == (
                "serialized_payload_limit_exceeded"
            )
            assert overflow_capture["traces"] == []
            assert overflow_capture["trace_arrays_omitted"] is True
            assert overflow_capture["array_payload_bytes"] == 0
            assert overflow_capture["array_payload_bytes"] <= overflow_capture[
                "array_payload_limit_bytes"
            ]
            assert overflow_capture["serialized_payload_size_basis"] == (
                "compact_utf8_json"
            )
            overflow_json_bytes = len(
                json.dumps(
                    overflow_capture,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            assert overflow_json_bytes <= overflow_capture[
                "serialized_payload_limit_bytes"
            ]
            assert overflow_records[0]["solver_status"] == "not_converged"
            assert overflow_records[0]["solver_error"] == (
                overflow_solver_state["error"]
            )
        else:
            assert overflow_capture is None

        pending_trace = {
            "solve_id": 1,
            "captured_array_bytes": 0,
            "capture_complete": True,
            "evaluations": [],
            "updates": [],
        }
        if MPI.COMM_WORLD.rank == fixture["layout"].modal_owner:
            off_system._modal_solve_trace_records.append(pending_trace)
        calls_before_destroy = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        off_system.destroy()
        assert off_system._modal_solve_trace_records == []
        calls_after_destroy = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        assert calls_before_destroy == calls_after_destroy
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False
    finally:
        for system in owned_objects:
            system.destroy()
        _destroy_side_block_fixture(fixture)


def test_side_balh_modal_trace_handoff_survives_real_ksp_pc_cleanup(
    monkeypatch,
) -> None:
    fixture = _side_block_fixture()
    original_action = original_context = context = rhs = None
    outer_result = None
    try:
        layout = fixture["layout"]
        rhs = layout.pack(
            fixture["bottom"].b,
            fixture["top"].b,
            internal_modal_rhs_correction(fixture["coupling"]),
        )
        original_action, original_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        context = block_ldu.create_side_balh_block_ldu_preconditioner(
            layout,
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            fixture["bottom_inverse"],
            fixture["top_inverse"],
            sampled_columns=None,
            sampled_column_roles=None,
            sampled_column_contract_sha256=None,
            use_anderson_modal_inner=True,
            complex_qr_research=True,
            capture_modal_solve_trace=True,
        )
        real_context_destroy = block_ldu.HybridBlockLduPreconditioner.destroy
        destroy_events = []

        def observe_context_destroy(instance, pc=None):
            if instance is context:
                frame = inspect.currentframe()
                caller = None
                try:
                    caller = None if frame is None else frame.f_back
                    if caller is None:
                        caller_function = "unknown"
                        caller_filename = "unknown"
                        caller_lineno = None
                        caller_source_line = "unknown"
                    else:
                        caller_function = caller.f_code.co_name
                        caller_filename = caller.f_code.co_filename
                        caller_lineno = int(caller.f_lineno)
                        caller_source_line = linecache.getline(
                            caller_filename, caller_lineno
                        ).strip()[:180]
                    if "ksp.destroy()" in caller_source_line:
                        cleanup_entry = "ksp_destroy_call"
                    elif "context.destroy()" in caller_source_line:
                        cleanup_entry = "context_destroy_fallback"
                    else:
                        cleanup_entry = "unknown"
                    handoff = instance._modal_solve_trace_handoff
                    destroy_events.append(
                        {
                            "rank": int(layout.comm.rank),
                            "pc_argument_is_none": pc is None,
                            "handoff_trace_count_before_destroy": (
                                0 if handoff is None else len(handoff)
                            ),
                            "adapter_trace_count_before_destroy": len(
                                instance.action_modal_schur_system._modal_solve_trace_records
                            ),
                            "caller_function": caller_function,
                            "caller_filename": caller_filename,
                            "caller_lineno": caller_lineno,
                            "caller_source_line": caller_source_line,
                            "cleanup_entry": cleanup_entry,
                        }
                    )
                finally:
                    del caller
                    del frame
            return real_context_destroy(instance, pc)

        monkeypatch.setattr(
            block_ldu.HybridBlockLduPreconditioner,
            "destroy",
            observe_context_destroy,
        )
        modal_system = context.action_modal_schur_system
        real_candidate_update = block_ldu._complex_anderson_candidate_update
        failure_triggered = {"value": False}

        def fail_second_inner_update(*args, **kwargs):
            if modal_system._solve_count == 2:
                failure_triggered["value"] = True
                raise np.linalg.LinAlgError("controlled bounded inner failure")
            return real_candidate_update(*args, **kwargs)

        monkeypatch.setattr(
            block_ldu,
            "_complex_anderson_candidate_update",
            fail_second_inner_update,
        )
        side_calls_before = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        caught = None
        try:
            outer_result = block_ldu.solve_hybrid_block_ldu_iterative(
                original_action,
                rhs,
                context,
                config=block_ldu.HybridBlockLduIterativeConfig(
                    restart=20,
                    max_it=80,
                    threshold=5.0e-9,
                    ksp_type="fgmres",
                ),
            )
        except (RuntimeError, PETSc.Error, ValueError) as exc:
            caught = exc

        assert caught is not None
        assert "Modal Anderson inner solve did not converge" in str(caught)
        failure_triggered_by_rank = MPI.COMM_WORLD.allgather(
            bool(failure_triggered["value"])
        )
        assert [
            rank for rank, triggered in enumerate(failure_triggered_by_rank) if triggered
        ] == [layout.modal_owner]
        assert modal_system._solve_count == 2
        assert context._destroyed is True
        destroy_call_counts = MPI.COMM_WORLD.allgather(len(destroy_events))
        assert destroy_call_counts == [1] * MPI.COMM_WORLD.size
        destroy_event = destroy_events[0]
        destroy_handoff_counts = MPI.COMM_WORLD.allgather(
            destroy_event["handoff_trace_count_before_destroy"]
        )
        assert destroy_handoff_counts == [
            2 if rank == layout.modal_owner else 0
            for rank in range(MPI.COMM_WORLD.size)
        ]
        destroy_adapter_trace_counts = MPI.COMM_WORLD.allgather(
            destroy_event["adapter_trace_count_before_destroy"]
        )
        assert destroy_adapter_trace_counts == [0] * MPI.COMM_WORLD.size
        destroy_events_by_rank = MPI.COMM_WORLD.allgather(destroy_event)
        if MPI.COMM_WORLD.rank == 0:
            print(
                json.dumps(
                    {"destroy_events_by_rank": destroy_events_by_rank},
                    sort_keys=True,
                ),
                flush=True,
            )
        assert modal_system.diagnostics["destroyed"] is True
        assert modal_system.constraint_lu is None
        assert fixture["bottom_inverse"].diagnostics["destroyed"] is False
        assert fixture["top_inverse"].diagnostics["destroyed"] is False

        handoff = context._modal_solve_trace_handoff
        handoff_counts = MPI.COMM_WORLD.allgather(
            0 if handoff is None else len(handoff)
        )
        assert handoff_counts == [
            2 if rank == layout.modal_owner else 0
            for rank in range(MPI.COMM_WORLD.size)
        ]
        assert modal_system._modal_solve_trace_records == []
        s_evaluations_before_export = modal_system._s_evaluation_count
        side_calls_before_export = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        capture = modal_system.export_modal_solve_capture(
            MPI.COMM_WORLD,
            writer_rank=0,
            trace_records=handoff,
        )
        context._modal_solve_trace_handoff = None
        assert modal_system._s_evaluation_count == s_evaluations_before_export
        assert side_calls_before_export == {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            for side in ("bottom", "top")
        }
        side_calls_for_solver = {
            side: fixture[f"{side}_inverse"].diagnostics["apply_count"]
            - side_calls_before[side]
            for side in ("bottom", "top")
        }
        assert all(value > 0 for value in side_calls_for_solver.values())
        if MPI.COMM_WORLD.rank == 0:
            assert capture is not None
            assert capture["owner_rank"] == layout.modal_owner
            assert capture["writer_rank"] == 0
            assert [trace["solve_id"] for trace in capture["traces"]] == [1, 2]
            assert capture["traces"][0]["solver_status"] == "converged"
            assert capture["traces"][0]["capture_complete"] is True
            assert capture["traces"][1]["solver_status"] == "not_converged"
            assert capture["traces"][1]["s_evaluation_count"] <= 16
            assert capture["traces"][1]["solver_stop_reason"] == (
                "nonfinite_or_invalid_anderson_update"
            )
            assert capture["traces"][1]["capture_incomplete_reason"] == (
                "anderson_update_failed"
            )
            assert capture["array_payload_bytes"] > 0
            assert capture["array_payload_bytes"] <= capture[
                "array_payload_limit_bytes"
            ]
        else:
            assert capture is None
        assert context._modal_solve_trace_handoff is None
        unconsumed = [{"solve_id": 99}]
        context._modal_solve_trace_handoff = unconsumed
        context.release_modal_solve_trace_handoff()
        assert unconsumed == []
        assert context._modal_solve_trace_handoff is None
    finally:
        if outer_result is not None:
            outer_result.destroy()
        if context is not None and not context._destroyed:
            context.destroy()
        if rhs is not None:
            rhs.destroy()
        if original_action is not None:
            original_action.destroy()
        if original_context is not None:
            original_context.destroy()
        _destroy_side_block_fixture(fixture)
