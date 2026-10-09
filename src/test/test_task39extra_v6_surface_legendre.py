"""Pure reference-cell and adjacency checks for the opt-in q160 surface path."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.native_capacity_profile import native_profile_facts
from src.solvers.fullspace_surface_legendre import (
    SURFACE_COMPONENT_PAIR_BACKEND,
    SURFACE_GEOMETRY_CACHE_MAX_BYTES,
    SURFACE_RELATIVE_GATE,
    SURFACE_SUPPORT_RELATIVE_CUTOFF,
    SURFACE_WEIGHTED_MOMENT_CONTRACTION,
    SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE,
    Q160SixLaneWeightedMomentWorkspace,
    _pointwise_surface_geometry_terms,
    add_complex_mpc_cell_contribution,
    apply_standard_dof_transform,
    assemble_face_from_moments,
    assemble_face_from_weighted_moments,
    borrow_readonly_array_view,
    clamp_ffcx_coordinate_table,
    component_pair_explicit_array_payload_bounds,
    face_trace_reference_tensor,
    face_trace_table,
    ffcx_float64_formatter_facts,
    fourier_legendre_moment,
    map_coordinate_quadrature,
    normalized_interval_legendre,
    pointwise_weighted_legendre_moments,
    pointwise_weighted_legendre_moments_pair,
    pointwise_weighted_legendre_moments_pair_from_geometry,
    pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y,
    pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y,
    relative_vector_defect,
    roundtrip_ffcx_float64_array,
    scalar_hex_coordinate_basix_element,
    significant_rows,
    surface_geometry_cache_payload_bytes,
    validate_boundary_mpc_row,
    validate_component_pair_degree,
    validate_q160_expanded_interval_tables,
    validate_weighted_moment_contraction,
    validate_weighted_moment_profile_selection,
)


@pytest.mark.parametrize("degree", [3, 6])
@pytest.mark.parametrize("component,zeta_face", [(0, 0.0), (0, 1.0), (1, 0.0), (1, 1.0)])
def test_separable_surface_moments_match_direct_q160_sum(degree, component, zeta_face):
    points0, weights0 = np.polynomial.legendre.leggauss(81)
    points = np.ascontiguousarray((points0 + 1.0) * 0.5)
    weights = np.ascontiguousarray(weights0 * 0.5)
    width = degree + 1
    dofs = 7
    rng = np.random.default_rng(7100 + degree * 10 + component + int(zeta_face))
    coefficient_matrix = np.ascontiguousarray(
        rng.normal(size=(dofs, 3 * width**3)), dtype=np.float64
    )
    basis = normalized_interval_legendre(points, degree)
    endpoint = normalized_interval_legendre(np.asarray([zeta_face]), degree)[0]
    trace = face_trace_table(
        coefficient_matrix,
        degree,
        component,
        zeta_face,
        endpoint_values=endpoint,
    )

    alpha = 8.25 - 0.013j
    gamma = -4.5 + 0.007j
    hx, hy = 0.03125, 0.046875
    h_component = hx if component == 0 else hy
    x_moment = fourier_legendre_moment(points, weights, degree, alpha, hx, polynomial_values=basis)
    y_moment = fourier_legendre_moment(points, weights, degree, gamma, hy, polynomial_values=basis)
    x0, y0, z_face = 0.125, -0.375, 1.75 if zeta_face else -2.0
    kz = 3.125 + 0.002j
    phase_origin = np.exp(1j * (alpha * x0 + gamma * y0 + kz * z_face))
    candidate = assemble_face_from_moments(
        trace,
        x_moment,
        y_moment,
        hx=hx,
        hy=hy,
        h_component=h_component,
        phase_origin=phase_origin,
    )

    # Independent 81x81 quadrature in the unreduced coefficient representation.
    tensor = coefficient_matrix.reshape(dofs, 3, width, width, width)[
        :, component, :, :, :
    ]
    local_values = np.einsum(
        "iabk,qa,rb,k->qri", tensor, basis, basis, endpoint, optimize=True
    ).reshape(-1, dofs)
    xq = np.repeat(points, points.size)
    yq = np.tile(points, points.size)
    wq = np.repeat(weights, weights.size) * np.tile(weights, weights.size)
    phases = np.exp(
        1j
        * (
            alpha * (x0 + hx * xq)
            + gamma * (y0 + hy * yq)
            + kz * z_face
        )
    )
    reference = (hx * hy / h_component) * np.sum(
        local_values * (wq * phases)[:, None], axis=0
    )
    absolute, relative = relative_vector_defect(candidate, reference)
    assert np.isfinite(absolute)
    assert relative <= SURFACE_RELATIVE_GATE


@pytest.mark.parametrize("degree", [3, 6])
@pytest.mark.parametrize("physical_component", [0, 1])
def test_pointwise_weighted_moments_match_raw_three_component_q160_sum(
    degree, physical_component
):
    points0, weights0 = np.polynomial.legendre.leggauss(81)
    points = np.ascontiguousarray((points0 + 1.0) * 0.5)
    interval_weights = np.ascontiguousarray(weights0 * 0.5)
    weights = np.repeat(interval_weights, 81) * np.tile(interval_weights, 81)
    x = np.repeat(points, 81)
    y = np.tile(points, 81)
    z = np.full_like(x, 1.0)
    width = degree + 1
    dofs = 7
    rng = np.random.default_rng(9173 + degree * 10 + physical_component)
    coefficient_matrix = np.ascontiguousarray(
        rng.normal(size=(dofs, 3 * width**3)), dtype=np.float64
    )
    basis_1d = normalized_interval_legendre(points, degree)
    endpoint = normalized_interval_legendre(np.asarray([1.0]), degree)[0]
    trace = face_trace_reference_tensor(
        coefficient_matrix,
        degree,
        1.0,
        endpoint_values=endpoint,
    )
    # A warped fake geometry keeps pointwise, non-diagonal J/K terms visible;
    # nonzero origins also distinguish the original pointwise phase from an
    # omitted or duplicated origin factor.
    physical = np.column_stack(
        (
            0.17 + 0.23 * x + 0.011 * y * z,
            -0.31 + 0.29 * y + 0.009 * x * z,
            1.7 + 0.41 * z + 0.007 * x * y,
        )
    )
    jacobians = np.empty((len(x), 3, 3), dtype=np.float64)
    jacobians[:, 0, :] = np.column_stack((
        np.full_like(x, 0.23), 0.011 * z, 0.011 * y
    ))
    jacobians[:, 1, :] = np.column_stack((
        0.009 * z, np.full_like(x, 0.29), 0.009 * x
    ))
    jacobians[:, 2, :] = np.column_stack((
        0.007 * y, 0.007 * x, np.full_like(x, 0.41)
    ))
    alpha = 7.25 - 0.019j
    gamma = -3.5 + 0.013j
    kz = 2.75 - 0.007j
    polynomial_x = np.repeat(basis_1d, 81, axis=0)
    polynomial_y = np.tile(basis_1d, (81, 1))
    moments = pointwise_weighted_legendre_moments(
        physical,
        jacobians,
        weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian=np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
        ),
        alpha=alpha,
        gamma=gamma,
        kz=kz,
        physical_component=physical_component,
    )
    pair_moments = pointwise_weighted_legendre_moments_pair(
        physical,
        jacobians,
        weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian=np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
        ),
        alpha=alpha,
        gamma=gamma,
        kz=kz,
    )
    assert pair_moments.shape == (2, 3, width, width)
    np.testing.assert_array_equal(pair_moments[physical_component], moments)
    other_component = 1 - physical_component
    other_moments = pointwise_weighted_legendre_moments(
        physical,
        jacobians,
        weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian=np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
        ),
        alpha=alpha,
        gamma=gamma,
        kz=kz,
        physical_component=other_component,
    )
    np.testing.assert_array_equal(pair_moments[other_component], other_moments)
    candidate = assemble_face_from_weighted_moments(trace, moments)

    # Independent direct q-wise reference keeps C's three reference blocks,
    # pointwise inverse-Piola, phase, measure, and the original product weight.
    tensor = coefficient_matrix.reshape(dofs, 3, width, width, width)
    reference_basis = np.einsum(
        "icabz,qa,qb,z->qic",
        tensor,
        polynomial_x,
        polynomial_y,
        endpoint,
        optimize=True,
    )
    assert reference_basis.shape == (6561, dofs, 3)
    inverse = np.linalg.inv(jacobians)
    facet_jacobian = np.asarray(
        [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
    )
    tangent0 = jacobians @ facet_jacobian[:, 0]
    tangent1 = jacobians @ facet_jacobian[:, 1]
    measure = np.linalg.norm(np.cross(tangent0, tangent1), axis=1)
    phase = np.exp(
        (1j * gamma) * physical[:, 1]
        + (1j * alpha) * physical[:, 0]
        + (1j * kz) * physical[:, 2]
    )
    reference_contributions = reference_basis * inverse[
        :, None, :, physical_component
    ]
    direct_basis = np.sum(
        reference_contributions, axis=2
    )
    reference = np.sum(
        (weights * measure * phase)[:, None] * direct_basis, axis=0
    )
    absolute, relative = relative_vector_defect(candidate, reference)
    assert np.isfinite(absolute)
    assert relative <= SURFACE_RELATIVE_GATE

    # The normal reference component contributes through the non-diagonal K
    # terms; dropping it is observably different on this witness.
    normal_contribution = np.sum(
        (weights * measure * phase)[:, None]
        * reference_contributions[:, :, 2],
        axis=0,
    )
    assert np.linalg.norm(normal_contribution) > 0.0
    assert np.any(np.abs(inverse[:, 2, physical_component]) > 0.0)
    without_normal = np.sum(
        (weights * measure * phase)[:, None]
        * np.sum(reference_contributions[:, :, :2], axis=2),
        axis=0,
    )
    assert np.linalg.norm(reference - without_normal) > 0.0
    with pytest.raises(ValueError, match="trace and pointwise moment tensors differ"):
        assemble_face_from_weighted_moments(trace[:, 0], moments)


def _weighted_q160_nonseparable_fixture():
    points0, weights0 = np.polynomial.legendre.leggauss(81)
    points = np.ascontiguousarray((points0 + 1.0) * 0.5)
    interval_weights = np.ascontiguousarray(weights0 * 0.5)
    interval_values = normalized_interval_legendre(points, 6)
    quadrilateral_weights = np.repeat(interval_weights, 81) * np.tile(
        interval_weights, 81
    )
    x = np.repeat(points, 81)
    y = np.tile(points, 81)
    z = np.full_like(x, 1.0)
    physical = np.column_stack(
        (
            0.17 + 0.23 * x + 0.011 * y * z,
            -0.31 + 0.29 * y + 0.009 * x * z,
            1.7 + 0.41 * z + 0.007 * x * y,
        )
    )
    jacobians = np.empty((len(x), 3, 3), dtype=np.float64)
    jacobians[:, 0, :] = np.column_stack((
        np.full_like(x, 0.23), 0.011 * z, 0.011 * y
    ))
    jacobians[:, 1, :] = np.column_stack((
        0.009 * z, np.full_like(x, 0.29), 0.009 * x
    ))
    jacobians[:, 2, :] = np.column_stack((
        0.007 * y, 0.007 * x, np.full_like(x, 0.41)
    ))
    determinant, cofactors, surface_measure = _pointwise_surface_geometry_terms(
        jacobians,
        np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
        ),
    )
    polynomial_x = np.ascontiguousarray(np.repeat(interval_values, 81, axis=0))
    polynomial_y = np.ascontiguousarray(np.tile(interval_values, (81, 1)))
    for array in (interval_values, polynomial_x, polynomial_y):
        array.flags.writeable = False
    return (
        physical,
        quadrilateral_weights,
        interval_values,
        polynomial_x,
        polynomial_y,
        determinant,
        cofactors,
        surface_measure,
    )


def test_q160_weighted_x_then_y_matches_full_q_nonseparable_complex_reference():
    (
        physical,
        weights,
        interval_values,
        polynomial_x,
        polynomial_y,
        determinant,
        cofactors,
        surface_measure,
    ) = _weighted_q160_nonseparable_fixture()
    basis_facts = validate_q160_expanded_interval_tables(
        interval_values, polynomial_x, polynomial_y
    )
    assert basis_facts["flatten_order"] == "x-major/y-minor; y is the fastest index"
    candidate = pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
        physical,
        weights,
        interval_values,
        determinant,
        cofactors,
        surface_measure,
        alpha=7.25 - 0.019j,
        gamma=-3.5 + 0.013j,
        kz=2.75 - 0.007j,
    )
    # Keep a separate implementation of the original full-q reduction as the
    # reference; this fixture has nonseparable complex phase and off-diagonal K.
    from src.solvers.fullspace_surface_legendre import _pointwise_surface_phase

    phase = _pointwise_surface_phase(physical, 7.25 - 0.019j, -3.5 + 0.013j, 2.75 - 0.007j)
    assert np.any(phase.imag != 0.0)
    assert np.any(cofactors[:, 0, 1] != 0.0)
    assert np.any(cofactors[:, 2, 0] != 0.0)
    reference = np.empty_like(candidate)
    pointwise_weights_by_component = np.empty(
        (2, 3, 81, 81), dtype=np.complex128
    )
    for physical_component in (0, 1):
        for reference_component in range(3):
            inverse_entry = (
                cofactors[:, reference_component, physical_component] / determinant
            )
            weighted = inverse_entry * phase
            weighted *= surface_measure
            weighted *= weights
            pointwise_weights_by_component[
                physical_component, reference_component
            ] = weighted.reshape(81, 81)
            reference[physical_component, reference_component] = (
                polynomial_x.T * weighted[None, :]
            ) @ polynomial_y
    absolute, relative = relative_vector_defect(candidate.ravel(), reference.ravel())
    assert np.isfinite(absolute)
    assert relative <= SURFACE_RELATIVE_GATE

    selected = ((0, 0, 0, 0), (0, 1, 3, 4), (0, 2, 6, 1), (1, 0, 4, 2), (1, 1, 2, 6), (1, 2, 5, 3))
    scalar_reference = []
    for physical_component, reference_component, a, b in selected:
        weighted_matrix = pointwise_weights_by_component[
            physical_component, reference_component
        ]
        scalar_value = 0.0 + 0.0j
        for j in range(81):
            x_sum = 0.0 + 0.0j
            for i in range(81):
                x_sum += (
                    interval_values[i, a] * weighted_matrix[i, j]
                )
            scalar_value += x_sum * interval_values[j, b]
        scalar_reference.append(scalar_value)
    selected_candidate = np.asarray(
        [candidate[index] for index in selected], dtype=np.complex128
    )
    _, selected_relative = relative_vector_defect(
        selected_candidate, np.asarray(scalar_reference, dtype=np.complex128)
    )
    assert selected_relative <= SURFACE_RELATIVE_GATE

    wrong_order_weights = np.roll(weights.reshape(81, 81), 1, axis=1).reshape(-1)
    wrong_order_weights.flags.writeable = False
    wrong_order_candidate = pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
        physical,
        wrong_order_weights,
        interval_values,
        determinant,
        cofactors,
        surface_measure,
        alpha=7.25 - 0.019j,
        gamma=-3.5 + 0.013j,
        kz=2.75 - 0.007j,
    )
    _, wrong_weight_relative = relative_vector_defect(
        wrong_order_candidate.ravel(), reference.ravel()
    )
    assert wrong_weight_relative > SURFACE_RELATIVE_GATE

    for bad_weights in (np.ones_like(weights), weights * 2.0):
        bad_candidate = pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
            physical,
            bad_weights,
            interval_values,
            determinant,
            cofactors,
            surface_measure,
            alpha=7.25 - 0.019j,
            gamma=-3.5 + 0.013j,
            kz=2.75 - 0.007j,
        )
        _, bad_relative = relative_vector_defect(
            bad_candidate.ravel(), reference.ravel()
        )
        assert bad_relative > SURFACE_RELATIVE_GATE

    separable_relative_values = []
    for physical_component, reference_component in ((0, 1), (1, 2)):
        weighted_matrix = pointwise_weights_by_component[
            physical_component, reference_component
        ]
        separable = (
            weighted_matrix[:, :1]
            @ (weighted_matrix[:1, :] / weighted_matrix[0, 0])
        )
        wrong_moment = (interval_values.T @ separable) @ interval_values
        _, wrong_separable_relative = relative_vector_defect(
            wrong_moment.ravel(), reference[physical_component, reference_component].ravel()
        )
        separable_relative_values.append(wrong_separable_relative)
    assert min(separable_relative_values) > SURFACE_RELATIVE_GATE


def test_q160_six_lane_candidate_matches_current_weighted_route_and_reuses_scratch():
    (
        physical,
        weights,
        interval_values,
        _polynomial_x,
        _polynomial_y,
        determinant,
        cofactors,
        surface_measure,
    ) = _weighted_q160_nonseparable_fixture()
    cofactors = cofactors.copy()
    for physical_component in (0, 1):
        for reference_component in range(3):
            if (physical_component, reference_component) == (1, 2):
                cofactors[:, reference_component, physical_component] = 0.0
            else:
                lane_scale = 1.0 + 0.031 * (3 * physical_component + reference_component)
                cofactors[:, reference_component, physical_component] *= lane_scale
                cofactors[:, reference_component, physical_component] += (
                    1.0e-4 * (1 + 3 * physical_component + reference_component)
                )
    kwargs = {
        "alpha": 7.25 - 0.019j,
        "gamma": -3.5 + 0.013j,
        "kz": 2.75 - 0.007j,
    }
    expected = pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
        physical,
        weights,
        interval_values,
        determinant,
        cofactors,
        surface_measure,
        **kwargs,
    )
    workspace = Q160SixLaneWeightedMomentWorkspace()
    assert workspace.payload_bytes == 684288
    first = pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y(
        physical,
        weights,
        interval_values,
        determinant,
        cofactors,
        surface_measure,
        workspace=workspace,
        **kwargs,
    )
    weighted_lanes, x_lanes = workspace.require_active()
    assert weighted_lanes.shape == (2, 3, 81, 81)
    assert x_lanes.shape == (2, 3, 7, 81)
    assert np.count_nonzero(weighted_lanes[1, 2]) == 0
    assert np.any(weighted_lanes.imag != 0.0)
    lane_values = [weighted_lanes[p, k].copy() for p in (0, 1) for k in range(3)]
    assert all(
        not np.array_equal(lane_values[left], lane_values[right])
        for left in range(6)
        for right in range(left + 1, 6)
    )
    absolute, relative = relative_vector_defect(first.ravel(), expected.ravel())
    assert np.isfinite(absolute)
    assert relative <= SURFACE_RELATIVE_GATE
    assert not np.shares_memory(first, weighted_lanes)
    first_saved = first.copy()
    second = pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y(
        physical,
        weights,
        interval_values,
        determinant,
        cofactors,
        surface_measure,
        workspace=workspace,
        alpha=kwargs["alpha"] + 0.17j,
        gamma=kwargs["gamma"] - 0.11j,
        kz=kwargs["kz"] + 0.09j,
    )
    assert id(workspace._weighted_values) == id(weighted_lanes)
    assert id(workspace._x_contractions) == id(x_lanes)
    assert not np.shares_memory(second, x_lanes)
    assert np.array_equal(first, first_saved)
    assert not np.array_equal(second, first)
    workspace.release()
    assert workspace._weighted_values is None
    with pytest.raises(RuntimeError, match="inactive or malformed"):
        pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y(
            physical,
            weights,
            interval_values,
            determinant,
            cofactors,
            surface_measure,
            workspace=workspace,
            **kwargs,
        )


@pytest.mark.parametrize("bad_input", ["shape", "dtype", "nonfinite"])
def test_q160_six_lane_rejects_malformed_inputs_without_fallback(bad_input):
    (
        physical,
        weights,
        interval_values,
        _polynomial_x,
        _polynomial_y,
        determinant,
        cofactors,
        surface_measure,
    ) = _weighted_q160_nonseparable_fixture()
    if bad_input == "shape":
        weights = weights[:-1]
    elif bad_input == "dtype":
        interval_values = interval_values.astype(np.float32)
    else:
        cofactors = cofactors.copy()
        cofactors[0, 1, 0] = np.nan
    workspace = Q160SixLaneWeightedMomentWorkspace()
    with pytest.raises(ValueError, match="incompatible shapes|non-finite"):
        pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y(
            physical,
            weights,
            interval_values,
            determinant,
            cofactors,
            surface_measure,
            alpha=7.25 - 0.019j,
            gamma=-3.5 + 0.013j,
            kz=2.75 - 0.007j,
            workspace=workspace,
        )
    workspace.release()


def test_six_lane_route_selection_is_only_an_explicit_profile_optin():
    validate_weighted_moment_profile_selection(
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        allow_six_lane_optin=False,
    )
    validate_weighted_moment_profile_selection(
        SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE,
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        allow_six_lane_optin=True,
    )
    with pytest.raises(ValueError, match="explicit six-lane opt-in"):
        validate_weighted_moment_profile_selection(
            SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE,
            SURFACE_WEIGHTED_MOMENT_CONTRACTION,
            allow_six_lane_optin=False,
        )


def test_context_dispatches_six_lane_route_without_fallback(monkeypatch):
    from src.solvers import fullspace_surface_legendre as legendre_module
    from src.solvers.dtn_port_3d import _SurfaceLegendreMomentContext

    context = object.__new__(_SurfaceLegendreMomentContext)
    context.backend = SURFACE_COMPONENT_PAIR_BACKEND
    context._geometry_face_local_facets = {"bottom": 0, "top": 1}
    context._geometry_cache = SimpleNamespace(
        get=lambda *_args: (
            np.zeros((6561, 3), dtype=np.float64),
            np.ones(6561, dtype=np.float64),
            np.zeros((6561, 3, 3), dtype=np.float64),
            np.ones(6561, dtype=np.float64),
        )
    )
    context._weighted_moment_contraction = SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
    context._six_lane_moment_workspace = object()
    context.quadrilateral_weights = np.ones(6561, dtype=np.float64)
    context.polynomial_values = np.ones((81, 7), dtype=np.float64)
    context._polynomial_x = np.ones((6561, 7), dtype=np.float64)
    context._polynomial_y = np.ones((6561, 7), dtype=np.float64)
    called = []

    def six_lane_spy(*args, **kwargs):
        called.append((args, kwargs))
        return np.zeros((2, 3, 7, 7), dtype=np.complex128)

    def forbidden_baseline(*_args, **_kwargs):
        raise AssertionError("six-lane route silently fell back to baseline")

    monkeypatch.setattr(
        legendre_module,
        "pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y",
        six_lane_spy,
    )
    monkeypatch.setattr(
        legendre_module,
        "pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y",
        forbidden_baseline,
    )
    mode = SimpleNamespace(
        side="bottom",
        alpha=1.0 + 0.2j,
        gamma=-0.7 + 0.1j,
        k_vector=(0.0, 0.0, 2.0 - 0.3j),
    )
    record = SimpleNamespace(
        zeta_face=0.0,
        local_facet=0,
        geometry_dofs=np.arange(8, dtype=np.int32),
    )
    result = context.pointwise_moments_pair(mode, record, record_position=2)
    assert result.shape == (2, 3, 7, 7)
    assert len(called) == 1
    assert called[0][1]["workspace"] is context._six_lane_moment_workspace
    with pytest.raises(RuntimeError, match="active cached workspace"):
        context._geometry_cache = None
        context.pointwise_moments_pair(mode, record, record_position=2)


def test_six_lane_context_releases_workspace_on_success_and_cache_error(monkeypatch):
    import src.solvers.dtn_port_3d as dtn_module

    class FakeCache:
        def __init__(self, context, *, max_bytes):
            self.context = context
            self.max_bytes = max_bytes
            self.release_calls = 0

        def release(self):
            self.release_calls += 1
            return {"released": True}

    def make_context():
        context = object.__new__(dtn_module._SurfaceLegendreMomentContext)
        context._geometry_cache_enabled = True
        context._geometry_cache_limit_bytes = SURFACE_GEOMETRY_CACHE_MAX_BYTES
        context._geometry_cache = None
        context._geometry_cache_last_facts = None
        context._weighted_moment_contraction = (
            SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
        )
        context._six_lane_moment_workspace = None
        context._prepared_trace_contractions = {}
        context._prepared_trace_release_count = 0
        return context

    monkeypatch.setattr(dtn_module, "_SurfacePointwiseGeometryCache", FakeCache)
    context = make_context()
    context.begin_geometry_cache()
    workspace = context._six_lane_moment_workspace
    assert workspace is not None and workspace.payload_bytes == 684288
    with pytest.raises(RuntimeError, match="fixture carrier failure"):
        try:
            raise RuntimeError("fixture carrier failure")
        finally:
            context.end_geometry_cache()
    assert workspace._weighted_values is None
    assert workspace._x_contractions is None
    assert context._six_lane_moment_workspace is None
    assert context.geometry_cache_facts() == {"released": True}

    class FailingCache(FakeCache):
        def release(self):
            self.release_calls += 1
            raise RuntimeError("fixture cache release failure")

    monkeypatch.setattr(dtn_module, "_SurfacePointwiseGeometryCache", FailingCache)
    context = make_context()
    context.begin_geometry_cache()
    workspace = context._six_lane_moment_workspace
    with pytest.raises(RuntimeError, match="fixture cache release failure"):
        context.end_geometry_cache()
    assert workspace is not None
    assert workspace._weighted_values is None
    assert workspace._x_contractions is None
    assert context._six_lane_moment_workspace is None


@pytest.mark.parametrize("bad_axis", ["x", "y"])
def test_q160_expanded_interval_table_rejects_bad_axis_order(bad_axis):
    (
        _physical,
        _weights,
        interval_values,
        polynomial_x,
        polynomial_y,
        _determinant,
        _cofactors,
        _surface_measure,
    ) = _weighted_q160_nonseparable_fixture()
    if bad_axis == "x":
        polynomial_x = polynomial_x.copy()
        before = polynomial_x.copy()
        polynomial_x[[0, 81]] = polynomial_x[[81, 0]]
        assert not np.array_equal(polynomial_x, before)
        polynomial_x.flags.writeable = False
        with pytest.raises(ValueError, match="x basis is not the exact"):
            validate_q160_expanded_interval_tables(
                interval_values, polynomial_x, polynomial_y
            )
    else:
        polynomial_y = polynomial_y.copy()
        before = polynomial_y.copy()
        polynomial_y[[0, 1]] = polynomial_y[[1, 0]]
        assert not np.array_equal(polynomial_y, before)
        polynomial_y.flags.writeable = False
        with pytest.raises(ValueError, match="y basis is not the exact"):
            validate_q160_expanded_interval_tables(
                interval_values, polynomial_x, polynomial_y
            )


def test_q160_weighted_contraction_rejects_nonfinite_and_bad_scope():
    (
        physical,
        weights,
        interval_values,
        _polynomial_x,
        _polynomial_y,
        determinant,
        cofactors,
        surface_measure,
    ) = _weighted_q160_nonseparable_fixture()
    validate_weighted_moment_contraction(
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        backend=SURFACE_COMPONENT_PAIR_BACKEND,
        degree=6,
        quadrature_degree=160,
        reuse_geometry_cache=True,
    )
    for invalid in (
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 3,
            "quadrature_degree": 160,
            "reuse_geometry_cache": True,
        },
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 6,
            "quadrature_degree": 160,
            "reuse_geometry_cache": False,
        },
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 6,
            "quadrature_degree": 80,
            "reuse_geometry_cache": True,
        },
    ):
        with pytest.raises(ValueError, match="requires cached p6 q160"):
            validate_weighted_moment_contraction(
                SURFACE_WEIGHTED_MOMENT_CONTRACTION, **invalid
            )

    bad_weights = weights.copy()
    bad_weights[0] = np.nan
    with pytest.raises(ValueError, match="input is non-finite"):
        pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
            physical,
            bad_weights,
            interval_values,
            determinant,
            cofactors,
            surface_measure,
            alpha=7.25 - 0.019j,
            gamma=-3.5 + 0.013j,
            kz=2.75 - 0.007j,
        )


def test_live_coordinate_mapping_preserves_physical_reference_jacobian_axes():
    coordinate_dofs = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.1, 0.0],
            [0.2, 3.0, 0.1],
            [0.0, 0.0, 4.0],
            [0.5, 0.0, 1.0],
            [1.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
            [0.25, 0.75, 1.0],
        ],
        dtype=np.float64,
    )
    values = np.asarray(
        [
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0],
        ]
    )
    derivatives = np.asarray(
        [
            [
                [-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
            ],
            [
                [-0.5, -0.5, -0.5], [0.5, 0.0, 0.0], [0.0, 0.5, 0.0],
                [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
            ],
        ],
        dtype=np.float64,
    )
    physical, jacobians = map_coordinate_quadrature(
        coordinate_dofs, values, derivatives
    )
    expected_physical = np.zeros_like(physical)
    expected = np.zeros_like(jacobians)
    for coordinate_dof in range(8):
        for physical_axis in range(3):
            expected_physical[:, physical_axis] += (
                coordinate_dofs[coordinate_dof, physical_axis]
                * values[:, coordinate_dof]
            )
            for reference_axis in range(3):
                expected[:, physical_axis, reference_axis] += (
                    coordinate_dofs[coordinate_dof, physical_axis]
                    * derivatives[:, coordinate_dof, reference_axis]
                )
    np.testing.assert_array_equal(physical, expected_physical)
    np.testing.assert_array_equal(jacobians, expected)


def test_coordinate_scalar_element_uses_live_ufl_component_and_cmap_identity():
    scalar = SimpleNamespace(
        cell_type="hexahedron",
        degree=1,
        dim=8,
        value_size=1,
        lagrange_variant=SimpleNamespace(value=3),
        hash=lambda: 7721,
    )
    coordinate_ufl = SimpleNamespace(
        basix_element=scalar,
        reference_value_shape=(3,),
        block_size=3,
    )
    domain = SimpleNamespace(ufl_coordinate_element=lambda: coordinate_ufl)
    cmap = SimpleNamespace(
        degree=1,
        dim=8,
        variant=3,
        hash=lambda: 7721,
    )
    mesh = SimpleNamespace(
        ufl_domain=lambda: domain,
        geometry=SimpleNamespace(
            cmap=cmap,
            dofmap=np.zeros((2, 8), dtype=np.int32),
            x=np.zeros((8, 3), dtype=np.float64),
        ),
    )
    element, facts = scalar_hex_coordinate_basix_element(
        mesh, hexahedron_cell_type="hexahedron"
    )
    assert element is scalar
    assert facts["basix_element_value_size"] == 1
    assert facts["basix_element_dimension"] == 8
    assert facts["basix_element_hash"] == facts["coordinate_map_hash"]

    scalar.value_size = 3
    with pytest.raises(NotImplementedError, match="scalar P1 hex/8-node"):
        scalar_hex_coordinate_basix_element(mesh, hexahedron_cell_type="hexahedron")
    scalar.value_size = 1
    cmap.hash = lambda: 7722
    with pytest.raises(NotImplementedError, match="scalar P1 hex/8-node"):
        scalar_hex_coordinate_basix_element(mesh, hexahedron_cell_type="hexahedron")


def test_coordinate_table_clamp_matches_ffcx_and_preserves_source():
    from ffcx.ir.elementtables import clamp_table_small_numbers

    source = np.asarray(
        [[-1.0 + 2.0e-10, -2.0e-10, 1.0 + 5.0e-7, 0.25]],
        dtype=np.float64,
    )
    original = source.copy()
    expected = source.copy()
    clamp_table_small_numbers(expected, rtol=1.0e-6, atol=1.0e-9)
    actual = clamp_ffcx_coordinate_table(source, rtol=1.0e-6, atol=1.0e-9)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(source, original)


def test_ffcx_formatter_roundtrip_matches_recorded_elf_samples_without_mutation():
    # These inputs are the clamped table value [0, 1] and Basix q160 product
    # weight [0] from the bounded facet0 ELF comparison receipt.
    source = np.asarray(
        [0.00021760078407031627, 3.1193891969628625e-7],
        dtype=np.float64,
    )
    original = source.copy()
    actual = roundtrip_ffcx_float64_array(source, name="known ELF samples")
    assert actual.shape == source.shape
    assert not np.shares_memory(actual, source)
    np.testing.assert_array_equal(source, original)
    assert actual.view(np.uint64).tolist() == [
        0x3F2C85788098D356,
        0x3E94EF11E0A06B51,
    ]
    facts = ffcx_float64_formatter_facts()
    assert facts["class"].endswith("CFormatter")
    assert facts["method"] == "_format_number"
    assert len(facts["module_sha256"]) == 64


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_ffcx_formatter_roundtrip_rejects_nonfinite_inputs(bad):
    with pytest.raises(ValueError, match="non-finite"):
        roundtrip_ffcx_float64_array(
            np.asarray([bad], dtype=np.float64),
            name="non-finite fixture",
        )


class _IndexProbe:
    """Array-shaped proxy that records row access and rejects bulk coercion."""

    def __init__(self, array):
        self.array = array
        self.ndim = array.ndim
        self.dtype = array.dtype
        self.size = array.size
        self.accesses = []

    def __getitem__(self, key):
        self.accesses.append(key)
        return self.array[key]

    def __array__(self, *_args, **_kwargs):
        raise AssertionError("global MPC metadata was coerced or copied")


def test_mpc_provider_arrays_are_borrowed_as_read_only_dtype_preserving_views():
    source = np.arange(8, dtype=np.int32)
    view = borrow_readonly_array_view(source, name="test offsets")
    assert view.dtype == source.dtype
    assert np.shares_memory(view, source)
    assert not view.flags.writeable
    assert source.flags.writeable
    source[3] = 17
    assert view[3] == 17


def test_boundary_mpc_validation_indexes_only_the_used_rows_and_preserves_dtype():
    slave = 5
    offsets = _IndexProbe(np.asarray([0, 0, 0, 0, 0, 0, 2], dtype=np.int32))
    coefficients = _IndexProbe(np.asarray([1.0 + 2.0j, -0.25j], dtype=np.complex128))
    is_slave = _IndexProbe(np.asarray([0, 0, 0, 0, 0, 1, 0], dtype=np.int8))
    masters = np.asarray([1, 3], dtype=np.int32)

    # The helper reads only the requested offsets and slave/master flags.
    frozen_masters, frozen_coefficients = validate_boundary_mpc_row(
        slave, offsets, coefficients, is_slave, masters, 7
    )
    assert offsets.accesses == [slave, slave + 1]
    assert coefficients.accesses == [slice(0, 2)]
    assert is_slave.accesses[0] == slave
    np.testing.assert_array_equal(is_slave.accesses[1], masters)
    assert frozen_masters.dtype == masters.dtype
    assert frozen_coefficients.dtype == np.complex128
    assert not frozen_masters.flags.writeable
    assert not frozen_coefficients.flags.writeable


@pytest.mark.parametrize(
    "offsets,coefficients,is_slave,masters,message",
    [
        (
            np.asarray([0, 0, 0], dtype=np.int32),
            np.asarray([], dtype=np.complex128),
            np.asarray([0, 1], dtype=np.int8),
            np.asarray([], dtype=np.int32),
            "malformed",
        ),
        (
            np.asarray([0, 2, 1], dtype=np.int32),
            np.asarray([1j], dtype=np.complex128),
            np.asarray([0, 1, 0], dtype=np.int8),
            np.asarray([0], dtype=np.int32),
            "offset pair",
        ),
        (
            np.asarray([0, 0, 1], dtype=np.int32),
            np.asarray([np.nan + 0j], dtype=np.complex128),
            np.asarray([0, 1, 0], dtype=np.int8),
            np.asarray([0], dtype=np.int32),
            "coefficient row is non-finite",
        ),
        (
            np.asarray([0, 0, 1], dtype=np.int32),
            np.asarray([1j], dtype=np.complex128),
            np.asarray([0, 1, 1], dtype=np.int8),
            np.asarray([2], dtype=np.int32),
            "nested slave",
        ),
    ],
)
def test_boundary_mpc_validation_rejects_invalid_or_empty_rows(
    offsets, coefficients, is_slave, masters, message
):
    with pytest.raises(ValueError, match=message):
        validate_boundary_mpc_row(1, offsets, coefficients, is_slave, masters, 3)


def test_complex_mpc_scatter_uses_conjugate_coefficients_and_rejects_empty_masters():
    local = np.asarray([1 + 2j, -0.5 + 3j, 4 - 1j], dtype=np.complex128)
    storage = np.zeros(5, dtype=np.complex128)
    cell_dofs = np.asarray([0, 2, 4], dtype=np.int32)
    add_complex_mpc_cell_contribution(
        local,
        storage,
        cell_dofs,
        [2],
        {2: [0]},
        {2: [1.0 + 2.0j]},
    )
    expected = (1.0 - 2.0j) * (-0.5 + 3j)
    assert storage[0] == expected + (1 + 2j)
    assert storage[2] == 0.0
    assert storage[4] == 4 - 1j
    wrong_nonconjugated = (1.0 + 2.0j) * (-0.5 + 3j) + (1 + 2j)
    assert storage[0] != wrong_nonconjugated
    with pytest.raises(ValueError, match="no masters"):
        add_complex_mpc_cell_contribution(
            np.asarray([1 + 0j]),
            np.zeros(1, dtype=np.complex128),
            [0],
            [0],
            {0: []},
            {0: []},
        )


class _TransformElement:
    needs_dof_transformations = True

    def __init__(self):
        self.calls = 0

    def T_apply(self, lanes, cell_info, block_size):
        self.calls += 1
        assert lanes.dtype == np.float64
        assert lanes.size == 6
        assert cell_info.dtype == np.uint32
        assert cell_info.tolist() == [9]
        assert block_size == 2
        lanes *= 2.0


def test_standard_complex_transform_matches_real_lane_bs2_contract_once():
    element = _TransformElement()
    result = apply_standard_dof_transform(
        element, np.asarray([1 + 2j, 3 - 4j, -2 + 0.5j]), 9
    )
    np.testing.assert_array_equal(result, np.asarray([2 + 4j, 6 - 8j, -4 + 1j]))
    assert element.calls == 1


def test_support_cutoff_is_existing_global_relative_rule_and_strict():
    rows = np.asarray([3, 4, 5, 6], dtype=np.int64)
    cutoff = 1.0e-13 * 2.0e5
    values = np.asarray([cutoff, np.nextafter(cutoff, np.inf), 2.0e5, 0.0])
    actual_rows, actual_values, actual_cutoff = significant_rows(
        rows, values, global_maximum=2.0e5
    )
    np.testing.assert_array_equal(actual_rows, [4, 5])
    np.testing.assert_array_equal(actual_values, values[[1, 2]])
    assert actual_cutoff == cutoff
    _, _, zero_cutoff = significant_rows(
        rows, np.zeros(4), global_maximum=0.0
    )
    assert zero_cutoff == 1.0e-30
    assert SURFACE_SUPPORT_RELATIVE_CUTOFF == 1.0e-13


def test_vector_gate_rejects_nonfinite_norm_and_keeps_zero_reference_exact():
    with pytest.raises(ValueError, match="non-finite"):
        relative_vector_defect(np.asarray([np.nan]), np.asarray([0.0]))
    with pytest.raises(ValueError, match="norm is non-finite"):
        relative_vector_defect(
            np.asarray([1.5e308, 1.5e308]), np.zeros(2)
        )
    assert relative_vector_defect(np.zeros(2), np.zeros(2)) == (0.0, 0.0)
    _absolute, relative = relative_vector_defect(np.asarray([1.0]), np.zeros(1))
    assert np.isinf(relative)


def test_component_pair_payload_is_derived_from_actual_facets_and_space_rows():
    full_side = component_pair_explicit_array_payload_bounds(
        point_count=6561,
        polynomial_width=7,
        local_dof_count=882,
        facet_count=2628,
        owned_support_rows=100_000,
        row_index_bytes=8,
    )
    shorter_side = component_pair_explicit_array_payload_bounds(
        point_count=6561,
        polynomial_width=7,
        local_dof_count=882,
        facet_count=1314,
        owned_support_rows=50_000,
        row_index_bytes=8,
    )
    assert full_side["staging_complex_values_bytes"] == 37_086_336
    assert full_side["staging_filled_flags_bytes"] == 2628
    assert full_side["explicit_numpy_payload_upper_bytes"] > (
        full_side["staging_complex_values_bytes"]
    )
    assert shorter_side["staging_complex_values_bytes"] == 18_543_168
    assert full_side["scope"].startswith("explicit NumPy arrays only; not process RSS")


def test_component_pair_backend_is_restricted_to_actual_p6():
    validate_component_pair_degree(SURFACE_COMPONENT_PAIR_BACKEND, 6)
    with pytest.raises(NotImplementedError, match="restricted to actual p6"):
        validate_component_pair_degree(SURFACE_COMPONENT_PAIR_BACKEND, 3)


def test_candidate_backend_is_explicit_only_for_new_07_profile():
    identity = "dual_condensed_balh_native_0p7nm_p3_pilot16_v6"
    options = native_profile_facts(identity)["component_options"]
    assert "dtn_surface_assembly_backend" not in options
    assert options["dtn_surface_assembly_backend_by_degree"] == {
        "p6": SURFACE_COMPONENT_PAIR_BACKEND,
        "p3": "native_ffcx",
    }
    assert options["dtn_surface_weighted_moment_contraction"] == (
        SURFACE_WEIGHTED_MOMENT_CONTRACTION
    )
    for other in (
        "dual_condensed_balh_native_13p5_p3_v6",
        "dual_condensed_balh_native_5nm_p3_v6",
        "dual_condensed_balh_native_2nm_p3_pilot16_v6",
        "dual_condensed_balh_native_2nm_pilot16_v6",
    ):
        old_options = native_profile_facts(other)["component_options"]
        assert "dtn_surface_assembly_backend" not in old_options
        assert "dtn_surface_assembly_backend_by_degree" not in old_options
        assert "dtn_surface_weighted_moment_contraction" not in old_options


def test_runtime_selects_the_explicit_degree_specific_surface_route():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "runners"
        / "physical_retained_condensed_v20.py"
    )
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    runtime_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "RetainedCondensedRuntime"
    )
    build_method = next(
        node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "build"
    )
    action_calls = [
        node
        for node in ast.walk(build_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_same_mesh_physical_action"
    ]
    assert len(action_calls) == 2
    selected = []
    for call in action_calls:
        keyword = next(
            item for item in call.keywords if item.arg == "surface_assembly_backend"
        )
        assert isinstance(keyword.value, ast.Subscript)
        assert isinstance(keyword.value.value, ast.Name)
        assert keyword.value.value.id == "surface_backend_by_degree"
        selected.append(ast.unparse(keyword.value.slice))
    assert selected == ["6", "coarse_degree"]
    for call in action_calls:
        degree_argument = call.args[2]
        contraction_keywords = [
            item
            for item in call.keywords
            if item.arg == "surface_weighted_moment_contraction"
        ]
        if isinstance(degree_argument, ast.Constant) and degree_argument.value == 6:
            assert len(contraction_keywords) == 1
            assert isinstance(contraction_keywords[0].value, ast.Name)
            assert contraction_keywords[0].value.id == "surface_weighted_moment_contraction"
        else:
            assert contraction_keywords == []


def _fake_geometry_cache_context():
    from src.solvers.dtn_port_3d import _SurfacePointwiseGeometryCache
    from src.solvers.fullspace_surface_legendre import (
        _pointwise_surface_geometry_terms,
        map_coordinate_quadrature,
    )

    class FakeContext:
        backend = SURFACE_COMPONENT_PAIR_BACKEND
        degree = 6
        quadrature_degree = 160
        _geometry_cache_enabled = True
        _geometry_cache_limit_bytes = SURFACE_GEOMETRY_CACHE_MAX_BYTES
        _weighted_moment_contraction = None

        def __init__(self):
            self.mesh_data = SimpleNamespace(mesh=object())
            self._geometry_coordinates = np.zeros((8, 3), dtype=np.float64)
            self._geometry_coordinates[0] = (1.0, 0.0, 0.0)
            self._geometry_coordinates[1] = (0.0, 1.0, 0.0)
            self._geometry_coordinates[2] = (0.0, 0.0, 1.0)
            self._geometry_coordinates[3, 0] = 1.0e-14
            self._geometry_dofmap = np.tile(
                np.arange(8, dtype=np.int32), (2, 1)
            )
            self.polynomial_values = None
            values = np.zeros((4, 8), dtype=np.float64)
            values[:, 0] = 1.0
            derivatives = np.zeros((4, 8, 3), dtype=np.float64)
            derivatives[:, 0, 0] = 1.0
            derivatives[:, 1, 1] = 1.0
            derivatives[:, 2, 2] = 1.0
            derivatives[:, 3, 1] = 1.0
            values.flags.writeable = False
            derivatives.flags.writeable = False
            self._geometry_face_tables = {
                side: (values, derivatives) for side in ("bottom", "top")
            }
            self._geometry_face_local_facets = {"bottom": 0, "top": 1}
            facet_jacobian = np.asarray(
                [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]], dtype=np.float64
            )
            facet_jacobian.flags.writeable = False
            self._facet_jacobians_by_side = {
                side: facet_jacobian for side in ("bottom", "top")
            }
            self.quadrilateral_points = np.zeros((4, 2), dtype=np.float64)
            self.quadrilateral_weights = np.full(4, 0.25, dtype=np.float64)
            self._polynomial_x = np.asarray(
                [[1.0, -1.0], [1.0, -0.25], [1.0, 0.25], [1.0, 1.0]],
                dtype=np.float64,
            )
            self._polynomial_y = self._polynomial_x[::-1].copy()
            for array in (
                self.quadrilateral_points,
                self.quadrilateral_weights,
                self._polynomial_x,
                self._polynomial_y,
            ):
                array.flags.writeable = False
            self._coordinate_element_identity = {"hash": "fake-scalar-cmap"}
            self._ffcx_coordinate_table_options = {
                "formatter_identity": "fake-ffcx-float64"
            }
            self.facts = {"quadrature_array_hashes": {"q160": "fake-q-hash"}}
            self._records_by_side = {
                "bottom": (
                    SimpleNamespace(
                        cell=0,
                        geometry_dofs=np.arange(8, dtype=np.int32),
                        local_facet=0,
                        zeta_face=0.0,
                    ),
                ),
                "top": (
                    SimpleNamespace(
                        cell=1,
                        geometry_dofs=np.arange(8, dtype=np.int32),
                        local_facet=1,
                        zeta_face=1.0,
                    ),
                ),
            }
            for records in self._records_by_side.values():
                records[0].geometry_dofs.flags.writeable = False
            self.geometry_build_calls = 0

        def _build_pointwise_geometry_entry(self, side, record):
            self.geometry_build_calls += 1
            coordinate_snapshot = np.array(
                self._geometry_coordinates[record.geometry_dofs], copy=True
            )
            values, derivatives = self._geometry_face_tables[side]
            physical, jacobians = map_coordinate_quadrature(
                coordinate_snapshot, values, derivatives
            )
            determinant, cofactors, measure = _pointwise_surface_geometry_terms(
                jacobians, self._facet_jacobians_by_side[side]
            )
            return coordinate_snapshot, physical, determinant, cofactors, measure

    owner = FakeContext()
    cache = _SurfacePointwiseGeometryCache
    return owner, cache


def test_p6_geometry_cache_is_bitwise_equal_bounded_and_released():
    from src.solvers.fullspace_surface_legendre import map_coordinate_quadrature

    context, cache_type = _fake_geometry_cache_context()
    expected_bytes = surface_geometry_cache_payload_bytes(
        point_count=4, facet_count=2
    )
    assert expected_bytes == 2 * 4 * 14 * 8
    assert surface_geometry_cache_payload_bytes(
        point_count=6561, facet_count=5256
    ) == 3_862_276_992
    assert SURFACE_GEOMETRY_CACHE_MAX_BYTES == 4 * 1024**3
    with pytest.raises(MemoryError, match="over"):
        cache_type(context, max_bytes=expected_bytes - 1)
    assert context.geometry_build_calls == 0

    cache = cache_type(context, max_bytes=expected_bytes)
    assert context.geometry_build_calls == 2
    for side in ("bottom", "top"):
        record = context._records_by_side[side][0]
        values, derivatives = context._geometry_face_tables[side]
        coordinate_dofs = context._geometry_coordinates[record.geometry_dofs]
        physical, jacobians = map_coordinate_quadrature(
            coordinate_dofs, values, derivatives
        )
        determinant, cofactors, measure = _pointwise_surface_geometry_terms(
            jacobians, context._facet_jacobians_by_side[side]
        )
        expected_geometry = (physical, determinant, cofactors, measure)
        for component_rates in (
            (0.37 + 0.11j, -0.19 + 0.07j, 0.53 + 0.03j),
            (-0.23 + 0.05j, 0.41 - 0.09j, -0.31 + 0.02j),
        ):
            cached_geometry = cache.get(context, side, 0, record)
            assert all(
                np.array_equal(cached, fresh)
                for cached, fresh in zip(
                    cached_geometry, expected_geometry, strict=True
                )
            )
            expected = pointwise_weighted_legendre_moments_pair(
                physical,
                jacobians,
                context.quadrilateral_weights,
                context._polynomial_x,
                context._polynomial_y,
                facet_jacobian=context._facet_jacobians_by_side[side],
                alpha=component_rates[0],
                gamma=component_rates[1],
                kz=component_rates[2],
            )
            actual = pointwise_weighted_legendre_moments_pair_from_geometry(
                cached_geometry[0],
                context.quadrilateral_weights,
                context._polynomial_x,
                context._polynomial_y,
                *cached_geometry[1:],
                alpha=component_rates[0],
                gamma=component_rates[1],
                kz=component_rates[2],
            )
            assert np.array_equal(actual, expected)
    facts = cache.facts()
    assert facts["geometry_build_count"] == 2
    assert facts["geometry_lookup_count"] == 4
    assert facts["peak_numeric_array_payload_bytes"] == expected_bytes
    assert facts["jacobians_retained"] is False
    released = cache.release()
    assert released["release_count"] == 1
    assert released["payload_after_release_bytes"] == 0
    assert released["peak_numeric_array_payload_bytes"] == expected_bytes

    # A later carrier begins empty and rebuilds the facet geometry once.
    second = cache_type(context, max_bytes=expected_bytes)
    assert context.geometry_build_calls == 4
    second.release()


@pytest.mark.parametrize(
    "negative",
    ["context", "mesh", "side", "facet", "record", "order", "coordinates", "quad"],
)
def test_p6_geometry_cache_rejects_stale_identity(negative):
    context, cache_type = _fake_geometry_cache_context()
    cache = cache_type(
        context,
        max_bytes=surface_geometry_cache_payload_bytes(point_count=4, facet_count=2),
    )
    record = context._records_by_side["bottom"][0]
    if negative == "context":
        target_context, side, position, target_record = object(), "bottom", 0, record
    elif negative == "mesh":
        context.mesh_data.mesh = object()
        target_context, side, position, target_record = context, "bottom", 0, record
    elif negative == "side":
        target_context, side, position, target_record = context, "top", 0, record
    elif negative == "facet":
        record.local_facet = 2
        target_context, side, position, target_record = context, "bottom", 0, record
    elif negative == "order":
        target_context, side, position, target_record = context, "bottom", 1, record
    elif negative == "record":
        target_context, side, position, target_record = (
            context,
            "bottom",
            0,
            SimpleNamespace(
                cell=0,
                geometry_dofs=record.geometry_dofs,
                local_facet=record.local_facet,
                zeta_face=record.zeta_face,
            ),
        )
    elif negative == "coordinates":
        context._geometry_coordinates[0, 0] += 1.0e-9
        target_context, side, position, target_record = context, "bottom", 0, record
    else:
        context.quadrilateral_points = context.quadrilateral_points.copy()
        target_context, side, position, target_record = context, "bottom", 0, record
    with pytest.raises((ValueError, RuntimeError)):
        cache.get(target_context, side, position, target_record)
    cache.release()


@pytest.mark.parametrize("negative", ["replacement", "writeable"])
def test_weighted_geometry_cache_binds_immutable_interval_values(negative):
    context, cache_type = _fake_geometry_cache_context()
    context._weighted_moment_contraction = SURFACE_WEIGHTED_MOMENT_CONTRACTION
    interval_values = np.arange(81 * 7, dtype=np.float64).reshape(81, 7)
    interval_values.flags.writeable = False
    context.polynomial_values = interval_values
    cache = cache_type(
        context,
        max_bytes=surface_geometry_cache_payload_bytes(point_count=4, facet_count=2),
    )
    record = context._records_by_side["bottom"][0]
    if negative == "replacement":
        context.polynomial_values = interval_values.copy()
    else:
        context.polynomial_values.flags.writeable = True
    with pytest.raises(ValueError, match="context or quadrature identity changed"):
        cache.get(context, "bottom", 0, record)
    cache.release()


def test_p6_geometry_cache_releases_partial_build(monkeypatch):
    from src.solvers.dtn_port_3d import _SurfacePointwiseGeometryCache

    context, cache_type = _fake_geometry_cache_context()
    original_builder = context._build_pointwise_geometry_entry
    original_release = cache_type.release
    calls = []
    released = []

    def fail_second_facet(side, record):
        calls.append((side, record))
        if len(calls) == 2:
            raise RuntimeError("fixture failure during partial cache construction")
        return original_builder(side, record)

    def tracked_release(cache):
        result = original_release(cache)
        released.append((cache._entries, result))
        return result

    context._build_pointwise_geometry_entry = fail_second_facet
    monkeypatch.setattr(_SurfacePointwiseGeometryCache, "release", tracked_release)

    with pytest.raises(RuntimeError, match="partial cache construction"):
        cache_type(
            context,
            max_bytes=surface_geometry_cache_payload_bytes(
                point_count=4, facet_count=2
            ),
        )

    assert len(calls) == 2
    assert len(released) == 1
    entries_after_release, facts = released[0]
    assert entries_after_release is None
    assert facts["release_count"] == 1
    assert facts["actual_numeric_array_payload_bytes"] == 0
    assert facts["payload_after_release_bytes"] == 0
