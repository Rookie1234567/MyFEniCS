"""Focused N1 fixed-cell local spectral algebra tests."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.fullspace_local_spectral import (
    ExactClassOwnerPlan,
    LocalSpectralPatch,
    N1_FACTOR_BYTES_LIMIT,
    N1_MAX_LOCAL_ROWS,
    build_regional_rayleigh_ritz,
    canonicalize_degenerate_eigenvectors,
    canonical_pou_closure_error,
    canonical_vector_digest,
    deterministic_class_owner,
    map_mode_template_to_patch,
    packed_lower_bytes,
)


def _synthetic_patch(
    comm=MPI.COMM_SELF, gradients=None, *, plan=None, digest="a" * 64
):
    size = 10
    rng = np.random.default_rng(287)
    b_seed = rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    m_seed = rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    block = b_seed.conj().T @ b_seed + 3.0 * np.eye(size)
    local_mass = m_seed.conj().T @ m_seed + 2.0 * np.eye(size)
    if gradients is None:
        gradients = _gradients(size)
    keys = tuple(("cell", index) for index in range(size))
    if plan is None:
        plan = ExactClassOwnerPlan((digest,), comm)
    patch = LocalSpectralPatch(
        block,
        local_mass,
        gradients,
        patch_id=0,
        exact_class_digest=digest,
        row_keys=keys,
        shared_row_multiplicity=np.full(size, 2, dtype=np.int64),
        comm=comm,
        class_plan=plan,
    )
    return patch, block, local_mass


def _gradients(size=10):
    candidates = np.zeros((size, 3), dtype=np.complex128)
    candidates[:3, :] = np.eye(3, dtype=np.complex128)
    candidates[3:, :] = np.array(
        [
            [1.0 + 0.2j, 0.3 - 0.1j, -0.2j],
            [0.1, -0.4j, 0.5 + 0.1j],
            [-0.2j, 0.2, 0.7 - 0.3j],
            [0.4, 0.1j, -0.1],
            [0.2 - 0.2j, 0.3, 0.2j],
            [-0.1, 0.5 + 0.1j, 0.4],
            [0.3j, -0.2, 0.1 - 0.2j],
        ],
        dtype=np.complex128,
    )
    return candidates


def test_canonical_anchor_is_invariant_to_degenerate_eigenvector_rotation():
    diagonal_mass = np.arange(1.0, 9.0, dtype=np.float64)
    mass = np.diag(diagonal_mass).astype(np.complex128)
    eigenvalues = np.asarray([1.0] * 6 + [2.0, 3.0], dtype=np.float64)
    operator = np.diag(diagonal_mass * eigenvalues).astype(np.complex128)
    basis = np.diag(1.0 / np.sqrt(diagonal_mass)).astype(np.complex128)
    rotation_seed = np.arange(36, dtype=np.float64).reshape(6, 6)
    rotation_seed = rotation_seed + 1j * rotation_seed[::-1]
    unitary, _ = np.linalg.qr(rotation_seed)
    rotated = basis.copy()
    rotated[:, :6] = basis[:, :6] @ unitary
    keys = tuple(("cell", index) for index in range(8))
    first, first_values, first_clusters = canonicalize_degenerate_eigenvectors(
        eigenvalues, basis, mass, operator, keys, tuple(range(5))
    )
    second, second_values, second_clusters = canonicalize_degenerate_eigenvectors(
        eigenvalues, rotated, mass, operator, keys, tuple(range(5))
    )
    assert np.linalg.norm(first - second) / np.linalg.norm(first) <= 1.0e-13
    assert first_values == second_values == (1.0,) * 5
    assert first_clusters == second_clusters == (6,)

    distinct_values = np.arange(1.0, 9.0, dtype=np.float64)
    distinct_operator = np.diag(diagonal_mass * distinct_values).astype(
        np.complex128
    )
    _distinct, distinct_selected, distinct_clusters = (
        canonicalize_degenerate_eigenvectors(
            distinct_values,
            basis,
            mass,
            distinct_operator,
            keys,
            (0, 1, 2),
        )
    )
    assert np.allclose(distinct_selected, (1.0, 2.0, 3.0), rtol=0.0, atol=1.0e-14)
    assert distinct_clusters == (1, 1, 1)


def test_fixed_cell_volume_mass_modes_repeat_route_and_pou():
    patch, block, mass = _synthetic_patch(gradients=_gradients())
    modes = patch.build()
    assert modes.shape == (10, 8)
    assert patch.audit["generalized_problem"] == (
        "fixed_cell_constrained_B0_q_lambda_M_local_q"
    )
    assert patch.audit["mass_metric"] == "local_volumetric_k0_squared_abs_epsilon_mass"
    assert patch.audit["M_local_hermitian_relative_defect"] <= 1.0e-12
    assert patch.audit["generalized_eigen_residual"] <= 1.0e-11
    assert patch.audit["selected_mode_mass_orthogonality"] <= 1.0e-11
    assert patch.audit["repeat_exact"] is None
    rhs = np.arange(10, dtype=np.complex128) + 0.25j
    result = patch.solve(rhs, request_id=17)
    assert np.linalg.norm(block @ result - rhs) / np.linalg.norm(rhs) <= 1.0e-11
    assert patch.audit["last_route_request_id"] == 17
    assert patch.audit["factorization_relative_error"] <= 1.0e-11
    assert patch.audit["fixed_rhs_solve_residual"] <= 1.0e-11
    assert patch.audit["construction_workspace_released"] is True
    assert patch.block is None
    assert patch.local_mass is None

    expected = {key: complex(index + 1.0j) for index, key in enumerate(patch.row_keys)}
    first = patch.pou_contribution(np.asarray(list(expected.values())))
    second = patch.pou_contribution(np.asarray(list(expected.values())))
    assert canonical_pou_closure_error((first, second), expected) <= 1.0e-13
    assert patch.audit["pou_closure_relative_error"] is None

    repeat_patch, _repeat_block, _repeat_mass = _synthetic_patch(gradients=_gradients())
    repeat_modes = repeat_patch.build()
    assert np.array_equal(modes, repeat_modes)
    assert patch.audit["repeat_exact"] is None
    assert patch.audit["factor_bytes"] == packed_lower_bytes(10)
    assert patch.audit["factor_bytes"] <= N1_FACTOR_BYTES_LIMIT
    assert canonical_vector_digest(patch.row_keys, patch.modes[:, 0]) == (
        canonical_vector_digest(repeat_patch.row_keys, repeat_patch.modes[:, 0])
    )
    rng = np.random.default_rng(1287)
    volume_values = rng.normal(size=10) + 1j * rng.normal(size=10)
    coarse_values = rng.normal(size=8) + 1j * rng.normal(size=8)
    assert patch.restriction_prolongation_adjoint_error(
        volume_values, coarse_values
    ) <= 1.0e-13
    patch.destroy()
    repeat_patch.destroy()
    patch.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        patch.build()


def test_gradient_dependency_fails_without_fallback():
    gradients = _gradients()
    gradients[:, 2] = gradients[:, 0]
    patch, _block, _mass = _synthetic_patch(gradients=gradients)
    with pytest.raises(RuntimeError, match="gradient candidate rank|linearly dependent"):
        patch.build()


def test_class_owner_store_reuses_one_factor_per_exact_class():
    first_digest = "b" * 64
    second_digest = "c" * 64
    assert deterministic_class_owner(first_digest, 1) == 0
    assert packed_lower_bytes(882) == 6_230_448
    plan = ExactClassOwnerPlan((first_digest, second_digest), MPI.COMM_SELF)
    assert plan.audit["one_global_factor_per_class"] is True
    assert plan.audit["per_rank_factor_replication"] is False
    assert plan.audit["route"] == "bounded_owner_rhs_gather_solution_scatter"
    first, _block, _mass = _synthetic_patch(
        plan=plan, digest=first_digest, gradients=_gradients()
    )
    second, _block2, _mass2 = _synthetic_patch(
        plan=plan, digest=first_digest, gradients=_gradients()
    )
    third, _block3, _mass3 = _synthetic_patch(
        plan=plan, digest=second_digest, gradients=_gradients()
    )
    first.build()
    assert not hasattr(first, "_factor")
    assert plan.factor_count == 1
    assert plan.factor_bytes == packed_lower_bytes(10)
    second.build()
    assert second.audit["factor_reused"] is True
    assert plan.factor_count == 1
    third.build()
    assert plan.factor_count == 2
    plan.destroy()
    assert plan.factor_count == 0
    assert plan.factor_bytes == 0
    first.destroy()
    second.destroy()
    third.destroy()


def test_class_template_route_reuses_factor_and_maps_independent_patch_shards():
    digest = "e" * 64
    plan = ExactClassOwnerPlan((digest,), MPI.COMM_SELF)
    first, _block, _mass = _synthetic_patch(plan=plan, digest=digest)
    first.build()
    template_keys = first.row_keys
    routed_keys, routed_modes = plan.register_class_template(
        digest,
        template_keys,
        first.modes,
        slot=0,
        representative_rank=0,
        participant_ranks=(0,),
    )
    assert routed_keys == template_keys
    reordered_keys = tuple(reversed(template_keys))
    shard = map_mode_template_to_patch(
        routed_keys, routed_modes, reordered_keys
    )
    retained = LocalSpectralPatch.from_mode_template(
        shard,
        patch_id=1,
        exact_class_digest=digest,
        row_keys=reordered_keys,
        class_plan=plan,
        class_template_row_keys=routed_keys,
    )
    independent, _independent_block, _independent_mass = _synthetic_patch(
        plan=plan, digest=digest
    )
    independent.build()
    retained_by_key = {
        key: value for key, value in zip(retained.row_keys, retained.modes[:, 0], strict=True)
    }
    independent_by_key = {
        key: value
        for key, value in zip(
            independent.row_keys, independent.modes[:, 0], strict=True
        )
    }
    difference = np.asarray(
        [retained_by_key[key] - independent_by_key[key] for key in template_keys]
    )
    reference = np.asarray([independent_by_key[key] for key in template_keys])
    assert np.linalg.norm(difference) / np.linalg.norm(reference) <= 1.0e-11
    assert plan.factor_count == 1
    assert plan.factor_bytes == packed_lower_bytes(10)
    assert retained.audit["mode_template_reused"] is True
    assert retained.audit["dense_workspace_released"] is True
    first.destroy()
    retained.destroy()
    independent.destroy()
    plan.destroy()


def test_p6_single_cell_template_contract_has_bounded_factor_and_shard():
    rows = N1_MAX_LOCAL_ROWS
    digest = "f" * 64
    plan = ExactClassOwnerPlan((digest,), MPI.COMM_SELF)
    representative_block = 2.0 * np.eye(rows, dtype=np.complex128)
    plan.register_class_representative(
        digest, representative_block, slot=0
    )
    del representative_block
    keys = tuple(("p6-cell-relative", index) for index in range(rows))
    modes = np.zeros((rows, 8), dtype=np.complex128)
    modes[np.arange(8), np.arange(8)] = 1.0
    patch = LocalSpectralPatch.from_mode_template(
        modes,
        patch_id=0,
        exact_class_digest=digest,
        row_keys=keys,
        class_plan=plan,
        class_template_row_keys=keys,
    )
    assert len(patch.row_keys) == 882
    assert patch.modes.shape == (882, 8)
    assert plan.factor_bytes == 6_230_448
    assert plan.factor_bytes <= N1_FACTOR_BYTES_LIMIT
    assert patch.block is None
    assert patch.local_mass is None
    assert patch.audit["mode_shard_bytes_retained"] == 882 * 8 * 16
    assert patch.audit["dense_workspace_released"] is True
    patch.destroy()
    plan.destroy()


def test_tagged_owner_route_uses_fixed_request_schedule():
    digest = "c" * 64
    plan = ExactClassOwnerPlan((digest,), MPI.COMM_SELF)
    rhs = np.ones(4, dtype=np.complex128)
    plan.ensure_factor(digest, 2.0 * np.eye(4, dtype=np.complex128))
    result = plan.route_solve(
        digest,
        rhs,
        request_id=9,
        active=True,
    )
    assert np.allclose(result, 0.5 * rhs, rtol=0.0, atol=1.0e-15)


def test_class_registration_uses_one_fixed_slot_factor():
    digest = "d" * 64
    plan = ExactClassOwnerPlan((digest,), MPI.COMM_SELF)
    plan.register_class_representative(
        digest,
        3.0 * np.eye(4, dtype=np.complex128),
        slot=0,
    )
    assert plan.factor_count == 1
    assert plan.factor_bytes == packed_lower_bytes(4)
    plan.destroy()


def test_n1_core_has_no_trace_or_global_matrix_backend():
    path = Path(__file__).parents[1] / "solvers" / "fullspace_local_spectral.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"allgather", "createAIJ", "assemble_matrix"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & forbidden_calls
    for closed_name in (
        "trace_mass",
        "trace_rows",
        "interior_rows",
        "_harmonic_map",
        "M_Gamma",
    ):
        assert closed_name not in source
    assert "local_volumetric_k0_squared_abs_epsilon_mass" in source
    assert '"request_id"' in source
    assert '"class_digest"' in source
    assert '"active"' in source


def test_regional_candidate_space_keeps_shared_row_cross_terms():
    candidates = np.asarray(
        [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.complex128
    )
    cell_indices = (np.asarray([0, 1]), np.asarray([1, 2]))
    cell_b = (
        np.asarray([[2.0, 0.2], [0.2, 3.0]], dtype=np.complex128),
        np.asarray([[4.0, 0.4], [0.4, 5.0]], dtype=np.complex128),
    )
    cell_m = (
        np.eye(2, dtype=np.complex128),
        2.0 * np.eye(2, dtype=np.complex128),
    )
    expected_b = np.zeros((2, 2), dtype=np.complex128)
    expected_m = np.zeros((2, 2), dtype=np.complex128)
    for indices, block, mass in zip(cell_indices, cell_b, cell_m, strict=True):
        local = candidates[indices, :]
        expected_b += local.conj().T @ block @ local
        expected_m += local.conj().T @ mass @ local
    assert abs(expected_b[0, 1]) > 0.0
    direct_b = sum(
        candidates[indices, :].conj().T @ block @ candidates[indices, :]
        for indices, block in zip(cell_indices, cell_b, strict=True)
    )
    direct_m = sum(
        candidates[indices, :].conj().T @ mass @ candidates[indices, :]
        for indices, mass in zip(cell_indices, cell_m, strict=True)
    )
    assert np.allclose(expected_b, direct_b)
    assert np.allclose(expected_m, direct_m)
    result = build_regional_rayleigh_ritz(
        {"macro": candidates},
        {"macro": expected_b},
        {"macro": expected_m},
    )["macro"]
    assert result["candidate_count"] == 2
    assert result["projected_dimension"] == 2
    assert result["selected_rank"] == 2
    assert result["mass_orthogonality"] <= 1.0e-11
    assert result["projected_eigen_residual"] <= 1.0e-11
    assert result["regional_dense_row_operator_materialized"] is False


def test_regional_cholesky_whitening_has_generalized_residual_gate():
    rng = np.random.default_rng(288)
    size = 5
    mass_seed = rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    mass = mass_seed.conj().T @ mass_seed + 2.0 * np.eye(size)
    stiffness_seed = rng.normal(size=(size, size)) + 1j * rng.normal(
        size=(size, size)
    )
    stiffness = stiffness_seed.conj().T @ stiffness_seed + np.eye(size)
    factor = np.linalg.cholesky(mass)
    normalization = np.linalg.solve(
        factor.conj().T, np.eye(size, dtype=np.complex128)
    )
    assert np.linalg.norm(
        normalization.conj().T @ mass @ normalization - np.eye(size)
    ) <= 1.0e-12
    result = build_regional_rayleigh_ritz(
        {"region": np.eye(size, dtype=np.complex128)},
        {"region": stiffness},
        {"region": mass},
    )["region"]
    assert result["candidate_m_rank"] == size
    assert result["mass_min_eigenvalue"] > 0.0
    assert np.isfinite(result["mass_condition_estimate"])
    for value, eigenvalue in zip(
        result["coefficients"].T, result["eigenvalues"], strict=True
    ):
        residual = stiffness @ value - eigenvalue * (mass @ value)
        denominator = max(
            np.linalg.norm(stiffness @ value),
            np.linalg.norm(eigenvalue * (mass @ value)),
            np.finfo(float).tiny,
        )
        assert np.linalg.norm(residual) / denominator <= 1.0e-11
