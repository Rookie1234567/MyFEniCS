"""Focused H1f checks for the borrowed BAL_H block-LDU factory."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hybrid_fem_modal_block_ldu as block_ldu
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.test.test_241_task037b_hybrid_action_modal_schur import (
    _destroy_fixture,
    _gather_vector,
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


def test_side_balh_anderson_inner_reuses_owner_factor_and_keeps_true_operator(
    monkeypatch,
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
        )
        initial_inventory = context.inventory
        initial_inner = initial_inventory["modal_inner_solver"]
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
