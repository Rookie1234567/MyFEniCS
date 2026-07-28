from __future__ import annotations

from dataclasses import FrozenInstanceError

import basix
import basix.ufl
import numpy as np
import pytest

from src.adaptivity.task035e_p7_shadow import (
    P7InteriorShadowSpace,
    build_p7_interior_shadow_space,
    condense_p7_interior_shadow_tensor,
    evaluate_p7_interior_shadow_dwr,
)


def _p7_discrete_gradient(space: P7InteriorShadowSpace) -> np.ndarray:
    points = np.asarray(space.hcurl_p7_element.points)
    scalar_table = np.asarray(space.h1_p7_element.tabulate(1, points))
    gradient_values = np.stack(
        (
            scalar_table[1, :, :, 0],
            scalar_table[2, :, :, 0],
            scalar_table[3, :, :, 0],
        ),
        axis=2,
    )
    flattened = np.ascontiguousarray(
        gradient_values.transpose(2, 0, 1)
    ).reshape(3 * len(points), int(space.h1_p7_element.dim))
    return np.asarray(space.hcurl_p7_element.interpolation_matrix) @ flattened


@pytest.fixture(scope="module")
def shadow_space() -> P7InteriorShadowSpace:
    return build_p7_interior_shadow_space()


@pytest.fixture(scope="module")
def condensed(shadow_space: P7InteriorShadowSpace):
    dimension = int(shadow_space.hcurl_p7_element.dim)
    tensor = np.eye(dimension, dtype=np.complex128)
    rng = np.random.default_rng(35268)
    rhs = (
        rng.standard_normal(dimension)
        + 1j * rng.standard_normal(dimension)
    )
    return (
        tensor,
        rhs,
        condense_p7_interior_shadow_tensor(tensor, rhs),
    )


def test_p7_interior_shadow_dimensions_rank_and_no_prefix(
    shadow_space: P7InteriorShadowSpace,
) -> None:
    audit = shadow_space.audit
    assert audit["pass"] is True
    assert audit["hcurl_p6_dimension"] == 882
    assert audit["hcurl_p7_dimension"] == 1344
    assert audit["hcurl_p6_trace_dimension"] == 432
    assert audit["hcurl_p6_interior_dimension"] == 450
    assert audit["hcurl_p7_interior_dimension"] == 756
    assert audit["hcurl_extra_interior_dimension"] == 306
    assert shadow_space.hcurl_dimension == 1188
    assert audit["h1_p6_dimension"] == 343
    assert audit["h1_p7_dimension"] == 512
    assert audit["h1_extra_interior_dimension"] == 91
    assert shadow_space.h1_dimension == 434
    assert audit["checks"]["hcurl_active_rank_complete"] is True
    assert audit["checks"]["h1_active_rank_complete"] is True
    assert audit["shadow_gradient_rank"] == 433
    assert audit["prefix_assumption_used"] is False
    assert audit["hcurl_naive_prefix_error_max"] > 1.0
    assert audit["h1_naive_prefix_error_max"] > 0.5


def test_basix_p6_injection_and_zero_p7_trace_support(
    shadow_space: P7InteriorShadowSpace,
) -> None:
    p6_hcurl = basix.ufl.element(
        "N1curl",
        "hexahedron",
        6,
    ).basix_element
    p7_hcurl = basix.ufl.element(
        "N1curl",
        "hexahedron",
        7,
    ).basix_element
    expected = np.asarray(
        basix.compute_interpolation_operator(p6_hcurl, p7_hcurl)
    )
    np.testing.assert_allclose(
        shadow_space.hcurl_p6_to_p7,
        expected,
        rtol=0.0,
        atol=0.0,
    )
    p7_trace = np.asarray(
        [
            dof
            for dimension in range(3)
            for entity in p7_hcurl.entity_dofs[dimension]
            for dof in entity
        ],
        dtype=np.int32,
    )
    assert np.max(
        np.abs(shadow_space.hcurl_interior_complement[p7_trace]),
        initial=0.0,
    ) == 0.0
    gram = (
        shadow_space.hcurl_interior_complement.conj().T
        @ shadow_space.hcurl_interior_complement
    )
    np.testing.assert_allclose(
        gram,
        np.eye(306),
        rtol=2.0e-13,
        atol=2.0e-13,
    )


def test_discrete_gradient_commutes_and_extra_gradient_is_interior(
    shadow_space: P7InteriorShadowSpace,
) -> None:
    expanded = (
        _p7_discrete_gradient(shadow_space)
        @ shadow_space.h1_expansion
    )
    reconstructed = (
        shadow_space.hcurl_expansion @ shadow_space.discrete_gradient
    )
    np.testing.assert_allclose(
        reconstructed,
        expanded,
        rtol=3.0e-11,
        atol=3.0e-11,
    )
    p7_trace = np.asarray(
        [
            dof
            for dimension in range(3)
            for entity in shadow_space.hcurl_p7_element.entity_dofs[
                dimension
            ]
            for dof in entity
        ],
        dtype=np.int32,
    )
    assert np.max(np.abs(expanded[p7_trace, 343:]), initial=0.0) < 1e-10
    assert shadow_space.audit["checks"][
        "shadow_gradient_kernel_is_constant_only"
    ]


def test_face_d4_does_not_change_or_leak_cell_interior(
    shadow_space: P7InteriorShadowSpace,
) -> None:
    cell_info = 1 | (3 << 1)
    oriented = np.ascontiguousarray(
        shadow_space.hcurl_interior_complement.copy()
    )
    shadow_space.hcurl_p7_element.T_apply(
        oriented.ravel(),
        oriented.shape[1],
        cell_info,
    )
    np.testing.assert_allclose(
        oriented,
        shadow_space.hcurl_interior_complement,
        rtol=0.0,
        atol=0.0,
    )
    assert shadow_space.audit["hcurl_face_d4_action_count"] == 48
    assert shadow_space.audit["h1_face_d4_action_count"] == 48
    assert shadow_space.audit[
        "hcurl_face_d4_trace_support_max"
    ] == 0.0
    assert shadow_space.audit["h1_face_d4_trace_support_max"] == 0.0


def test_hermitian_projection_dense_schur_and_recovery(
    condensed,
) -> None:
    tensor, rhs, result = condensed
    expansion = result.space.hcurl_expansion
    expected_active = expansion.conj().T @ tensor @ expansion
    expected_rhs = expansion.conj().T @ rhs
    np.testing.assert_allclose(
        result.active_tensor,
        expected_active,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        result.active_tensor,
        result.active_tensor.conj().T,
        rtol=2.0e-13,
        atol=2.0e-13,
    )

    trace = result.space.hcurl_trace_dofs
    interior = result.space.hcurl_interior_dofs
    a_tt = expected_active[np.ix_(trace, trace)]
    a_ti = expected_active[np.ix_(trace, interior)]
    a_it = expected_active[np.ix_(interior, trace)]
    a_ii = expected_active[np.ix_(interior, interior)]
    direct_solutions = np.linalg.solve(
        a_ii,
        np.column_stack((a_it, expected_rhs[interior])),
    )
    direct_schur = a_tt - a_ti @ direct_solutions[:, :-1]
    direct_rhs = (
        expected_rhs[trace] - a_ti @ direct_solutions[:, -1]
    )
    np.testing.assert_allclose(
        result.schur_tensor,
        direct_schur,
        rtol=3.0e-12,
        atol=3.0e-12,
    )
    np.testing.assert_allclose(
        result.schur_rhs,
        direct_rhs,
        rtol=3.0e-12,
        atol=3.0e-12,
    )

    rng = np.random.default_rng(26801)
    trace_values = (
        rng.standard_normal(len(trace))
        + 1j * rng.standard_normal(len(trace))
    )
    active = result.recover_shadow_coefficients(trace_values)
    residual = expected_active @ active - expected_rhs
    assert np.max(np.abs(residual[interior]), initial=0.0) < 2.0e-11
    np.testing.assert_allclose(
        residual[trace],
        result.schur_tensor @ trace_values - result.schur_rhs,
        rtol=3.0e-12,
        atol=3.0e-12,
    )
    np.testing.assert_allclose(
        result.recover_p7_coefficients(trace_values),
        expansion @ active,
        rtol=0.0,
        atol=0.0,
    )
    assert result.audit["projection_convention"] == "E^H A E"
    assert result.audit["global_p7_matrix_constructed"] is False
    assert result.audit["input_p7_tensor_retained"] is False
    assert not hasattr(result, "p7_tensor")
    assert result.audit["active_trace_rows"] == 432
    assert result.audit["active_cell_interior_rows"] == 756
    assert result.audit["p7_extra_cell_interior_rows"] == 306
    assert result.audit["active_tensor_bytes"] == 1188**2 * 16
    assert result.audit["schur_tensor_bytes"] == 432**2 * 16


def test_local_59_goal_residual_adjoint_dwr_closure(
    shadow_space: P7InteriorShadowSpace,
) -> None:
    dimension = int(shadow_space.hcurl_p7_element.dim)
    diagonal = np.linspace(1.0, 2.0, dimension) + 1j * np.linspace(
        0.01,
        0.08,
        dimension,
    )
    tensor = np.diag(diagonal)
    rng = np.random.default_rng(26859)
    rhs = (
        rng.standard_normal(dimension)
        + 1j * rng.standard_normal(dimension)
    )
    current = (
        rng.standard_normal(882) + 1j * rng.standard_normal(882)
    )
    gradients = (
        rng.standard_normal((59, dimension))
        + 1j * rng.standard_normal((59, dimension))
    )
    result = evaluate_p7_interior_shadow_dwr(
        tensor,
        rhs,
        current,
        gradients,
    )
    complement = shadow_space.hcurl_interior_complement
    expected_residual = complement.conj().T @ (
        rhs - tensor @ (shadow_space.hcurl_p6_to_p7 @ current)
    )
    np.testing.assert_allclose(
        result.projected_residual,
        expected_residual,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        result.signed_contributions,
        result.direct_goal_deltas,
        rtol=2.0e-12,
        atol=2.0e-12,
    )
    assert result.signed_contributions.shape == (59,)
    assert result.audit["goal_count"] == 59
    assert result.audit["can_satisfy_f1_alone"] is False
    assert result.audit["requires_trace_and_h_shadow_for_f1"] is True
    assert result.audit["coverage_credit"] == "interior_lower_bound_only"
    assert result.audit["p6_saturation_status"] == "not_measured"
    assert result.audit["p6_saturation_measured_pass"] is False

    with pytest.raises(ValueError, match="exactly 59"):
        evaluate_p7_interior_shadow_dwr(
            tensor,
            rhs,
            current,
            gradients[:58],
        )


def test_component_is_immutable_and_never_selectable_as_production(
    shadow_space: P7InteriorShadowSpace,
    condensed,
) -> None:
    _tensor, _rhs, result = condensed
    with pytest.raises(ValueError):
        shadow_space.hcurl_expansion[0, 0] = 0.0
    with pytest.raises(TypeError):
        shadow_space.audit["pass"] = False
    with pytest.raises(FrozenInstanceError):
        shadow_space.shadow_only = False
    with pytest.raises(ValueError):
        result.schur_tensor[0, 0] = 0.0
    assert shadow_space.production_degrees_unchanged == frozenset(
        {4, 5, 6}
    )
    assert shadow_space.audit["production_degrees_unchanged"] == (4, 5, 6)
    assert shadow_space.shadow_only is True
    assert shadow_space.selectable_as_production is False
    assert shadow_space.next_production_plan is None
    assert shadow_space.coverage_credit == "interior_lower_bound_only"
    assert shadow_space.audit["p6_saturation_status"] == "not_measured"
    assert shadow_space.audit["p6_saturation_measured_pass"] is False
    assert shadow_space.audit["p7_trace_shadow_covered"] is False
    assert shadow_space.audit["h_shadow_covered"] is False
    assert shadow_space.audit["ordinary_default_changed"] is False
