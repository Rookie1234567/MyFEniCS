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
