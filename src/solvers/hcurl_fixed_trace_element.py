"""Globally uniform fixed-trace tensor-product H(curl) elements.

This module contains the production-safe part of the Task035b high-order
element work.  Every cell uses the same trace degree and the same
cell-interior degree.  The shared edge/face moments therefore remain
conforming, while assembly-time static condensation can eliminate the richer
cell-interior modes.

The implementation accepts only two global integer degrees and has no
per-cell policy.  It always constructs the physically active basis directly;
it never retains a maximum-order matrix and deactivates rows.
"""

from __future__ import annotations

from functools import lru_cache
import time
from typing import Any

import basix
import basix.ufl
import numpy as np
from scipy.linalg import qr

from src.adaptivity.fast_custom_element_ufl import wrap_custom_element_fast


__all__ = [
    "audit_tensor_product_exact_sequence",
    "fixed_trace_hcurl_ufl_element",
    "persistent_fixed_trace_hcurl_ufl_element",
]


def audit_tensor_product_exact_sequence(
    element: basix.finite_element.FiniteElement,
    *,
    trace_degree: int,
    interior_degree: int,
) -> dict[str, Any]:
    """Audit the local curl kernel against the mixed scalar companion.

    A tensor-product scalar companion with ``Q(trace_degree)`` boundary modes
    and ``Q(interior_degree)`` cell-bubble modes has

    ``[(t + 1)^3 - (t - 1)^3] + (i - 1)^3 - 1``

    nonconstant gradients.  The H(curl) polynomial space must expose exactly
    that many curl-null modes as a local exact-sequence prerequisite.  Global
    topology, orientation, periodicity, and stability are separate gates.
    """

    trace_degree = int(trace_degree)
    interior_degree = int(interior_degree)
    if trace_degree < 1 or interior_degree < 1:
        raise ValueError("exact-sequence audit requires positive degrees")
    points_per_axis = max(trace_degree, interior_degree) + 1
    axis_points = (
        np.polynomial.legendre.leggauss(points_per_axis)[0] + 1.0
    ) / 2.0
    points = np.asarray(
        [
            (x, y, z)
            for x in axis_points
            for y in axis_points
            for z in axis_points
        ],
        dtype=np.float64,
    )
    derivatives = element.tabulate(1, points)
    derivative_x = derivatives[1]
    derivative_y = derivatives[2]
    derivative_z = derivatives[3]
    curl_values = np.stack(
        (
            derivative_y[:, :, 2] - derivative_z[:, :, 1],
            derivative_z[:, :, 0] - derivative_x[:, :, 2],
            derivative_x[:, :, 1] - derivative_y[:, :, 0],
        ),
        axis=1,
    )
    curl_matrix = curl_values.reshape(-1, int(element.dim))
    _orthogonal, upper, _pivots = qr(
        curl_matrix,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(upper))
    rank_tolerance = (
        0.0
        if len(diagonal) == 0
        else float(
            diagonal[0]
            * max(curl_matrix.shape)
            * np.finfo(np.float64).eps
        )
    )
    curl_rank = int(np.count_nonzero(diagonal > rank_tolerance))
    curl_nullity = int(element.dim - curl_rank)
    scalar_trace_boundary_dimension = int(
        (trace_degree + 1) ** 3 - max(trace_degree - 1, 0) ** 3
    )
    scalar_cell_interior_dimension = int(
        max(interior_degree - 1, 0) ** 3
    )
    expected_gradient_dimension = int(
        scalar_trace_boundary_dimension
        + scalar_cell_interior_dimension
        - 1
    )
    difference = curl_nullity - expected_gradient_dimension
    return {
        "schema_version": "myfenics.hcurl-fixed-trace-exact-sequence.v1",
        "status": (
            "local_tensor_exact_sequence_pass"
            if difference == 0
            else "local_tensor_exact_sequence_fail"
        ),
        "pass": difference == 0,
        "cell_type": "hexahedron",
        "trace_degree": trace_degree,
        "interior_degree": interior_degree,
        "vector_space_dimension": int(element.dim),
        "scalar_trace_boundary_dimension": (
            scalar_trace_boundary_dimension
        ),
        "scalar_cell_interior_dimension": (
            scalar_cell_interior_dimension
        ),
        "expected_nonconstant_gradient_dimension": (
            expected_gradient_dimension
        ),
        "measured_curl_rank": curl_rank,
        "measured_curl_nullity": curl_nullity,
        "curl_nullity_minus_expected_gradient_dimension": difference,
        "missing_gradient_mode_count": max(-difference, 0),
        "unmatched_curl_null_mode_count": max(difference, 0),
        "points_per_axis": points_per_axis,
        "sample_point_count": len(points),
        "rank_method": "pivoted_QR_of_sampled_polynomial_curl_map",
        "rank_tolerance": rank_tolerance,
        "smallest_accepted_qr_diagonal": (
            None if curl_rank == 0 else float(diagonal[curl_rank - 1])
        ),
        "largest_rejected_qr_diagonal": (
            None
            if curl_rank >= len(diagonal)
            else float(diagonal[curl_rank])
        ),
        "scope": (
            "local polynomial exact-sequence prerequisite; global topology, "
            "orientation, periodicity, and inf-sup stability remain separate"
        ),
    }


def _standard_hexa_hcurl(
    degree: int,
) -> basix.finite_element.FiniteElement:
    return basix.ufl.element(
        "N1curl",
        "hexahedron",
        int(degree),
    ).basix_element


def _flatten_entity_dofs(
    element: basix.finite_element.FiniteElement,
    dimensions: range,
) -> np.ndarray:
    return np.asarray(
        [
            int(dof)
            for dimension in dimensions
            for entity in element.entity_dofs[dimension]
            for dof in entity
        ],
        dtype=np.int32,
    )


def _selected_interpolation_operator(
    source: basix.finite_element.FiniteElement,
    target: basix.finite_element.FiniteElement,
    source_dofs: np.ndarray,
) -> np.ndarray:
    """Form only requested columns of a same-map Basix interpolation."""

    selected = np.asarray(source_dofs, dtype=np.int32)
    if selected.ndim != 1:
        raise ValueError("selected interpolation DoFs must be one-dimensional")
    if len(np.unique(selected)) != len(selected):
        raise ValueError("selected interpolation DoFs must be unique")
    if len(selected) and (
        int(np.min(selected)) < 0
        or int(np.max(selected)) >= int(source.dim)
    ):
        raise ValueError("selected interpolation DoF is outside the source")
    if int(source.interpolation_nderivs) != 0:
        raise NotImplementedError(
            "selected interpolation currently requires derivative-free "
            "source moments"
        )
    if int(target.interpolation_nderivs) != 0:
        raise NotImplementedError(
            "selected interpolation currently requires derivative-free "
            "target moments"
        )
    if tuple(source.value_shape) != tuple(target.value_shape):
        raise ValueError(
            "selected interpolation requires identical source/target "
            "value shape"
        )
    if source.map_type != target.map_type:
        raise ValueError(
            "selected interpolation requires identical source/target maps"
        )

    points = np.asarray(target.points)
    tabulated = np.asarray(source.tabulate(0, points)[0])
    value_size = int(np.prod(source.value_shape, dtype=np.int64))
    expected_shape = (len(points), int(source.dim), value_size)
    if tuple(tabulated.shape) != expected_shape:
        raise RuntimeError(
            "selected interpolation tabulation shape changed: "
            f"observed={tabulated.shape}, expected={expected_shape}"
        )
    interpolation_matrix = np.asarray(target.interpolation_matrix)
    expected_columns = len(points) * value_size
    if tuple(interpolation_matrix.shape) != (
        int(target.dim),
        expected_columns,
    ):
        raise RuntimeError(
            "selected interpolation matrix shape changed: "
            f"observed={interpolation_matrix.shape}, "
            f"expected={(int(target.dim), expected_columns)}"
        )
    selected_values = np.ascontiguousarray(
        tabulated[:, selected, :].transpose(2, 0, 1)
    ).reshape(expected_columns, len(selected))
    return np.asarray(interpolation_matrix @ selected_values)


@lru_cache(maxsize=16)
def _create_trace_interior_element_data(
    trace_degree: int,
    cell_interior_degree: int,
    qualification_audit: bool = True,
) -> tuple[
    basix.finite_element.FiniteElement,
    dict[str, Any],
    dict[str, Any] | None,
]:
    """Build one globally uniform H(curl) element.

    Shared edges and faces use ``trace_degree`` moments on every cell.  Cell
    interiors use ``cell_interior_degree`` moments on every cell.
    """

    trace_degree = int(trace_degree)
    cell_interior_degree = int(cell_interior_degree)
    if not 1 <= trace_degree <= 6:
        raise ValueError("fixed-trace degree must be in [1, 6]")
    if not trace_degree <= cell_interior_degree <= 6:
        raise ValueError(
            "fixed-trace interior degree must satisfy "
            "trace_degree <= interior_degree <= 6"
        )

    total_started = time.perf_counter()
    trace_element_started = time.perf_counter()
    trace_element = _standard_hexa_hcurl(trace_degree)
    trace_element_seconds = time.perf_counter() - trace_element_started
    interior_element_started = time.perf_counter()
    interior_element = _standard_hexa_hcurl(cell_interior_degree)
    interior_element_seconds = (
        time.perf_counter() - interior_element_started
    )
    if trace_degree == cell_interior_degree:
        qualification_started = time.perf_counter()
        condition_number = (
            float(np.linalg.cond(trace_element.coefficient_matrix))
            if qualification_audit
            else None
        )
        qualification_seconds = (
            time.perf_counter() - qualification_started
        )
        return (
            trace_element,
            {
                "polynomial_subspace_rank": int(trace_element.dim),
                "coefficient_matrix_condition_number": condition_number,
                "custom": False,
                "qualification_audit_executed": bool(
                    qualification_audit
                ),
                "construction_profile": {
                    "schema_version": (
                        "task035b.fixed-trace-element-cold-build-profile.v1"
                    ),
                    "status": "standard_element_reused",
                    "strategy": "standard_equal_degree",
                    "polynomial_element_reused": True,
                    "selected_interpolation_enabled": False,
                    "numerical_identity_contract": (
                        "ordinary Basix standard element"
                    ),
                    "stage_seconds": {
                        "standard_trace_element": float(
                            trace_element_seconds
                        ),
                        "standard_interior_element": float(
                            interior_element_seconds
                        ),
                        "qualification": float(qualification_seconds),
                        "total": float(
                            time.perf_counter() - total_started
                        ),
                    },
                },
            },
            None,
        )

    polynomial_element = interior_element
    tdim = 3
    trace_dofs = _flatten_entity_dofs(trace_element, range(tdim))
    interior_dofs = np.asarray(
        interior_element.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    trace_interpolation_started = time.perf_counter()
    if qualification_audit:
        trace_to_polynomial = basix.compute_interpolation_operator(
            trace_element,
            polynomial_element,
        )[:, trace_dofs]
        trace_interpolation_strategy = "basix_full_reference_then_select"
    else:
        trace_to_polynomial = _selected_interpolation_operator(
            trace_element,
            polynomial_element,
            trace_dofs,
        )
        trace_interpolation_strategy = (
            "public_basix_tabulation_selected_columns"
        )
    trace_interpolation_seconds = (
        time.perf_counter() - trace_interpolation_started
    )
    interior_interpolation_started = time.perf_counter()
    if qualification_audit:
        interior_to_polynomial = basix.compute_interpolation_operator(
            interior_element,
            polynomial_element,
        )[:, interior_dofs]
        interior_interpolation_strategy = (
            "basix_full_reference_then_select"
        )
    else:
        interior_to_polynomial = _selected_interpolation_operator(
            interior_element,
            polynomial_element,
            interior_dofs,
        )
        interior_interpolation_strategy = (
            "public_basix_tabulation_selected_columns"
        )
    interior_interpolation_seconds = (
        time.perf_counter() - interior_interpolation_started
    )
    nodal_coefficients_started = time.perf_counter()
    nodal_coefficients = np.vstack(
        (
            trace_to_polynomial.T @ polynomial_element.coefficient_matrix,
            interior_to_polynomial.T
            @ polynomial_element.coefficient_matrix,
        )
    )
    nodal_coefficients_seconds = (
        time.perf_counter() - nodal_coefficients_started
    )
    expected_dimension = len(trace_dofs) + len(interior_dofs)
    qualification_started = time.perf_counter()
    polynomial_rank = (
        int(np.linalg.matrix_rank(nodal_coefficients))
        if qualification_audit
        else expected_dimension
    )
    if qualification_audit and polynomial_rank != expected_dimension:
        raise RuntimeError(
            "fixed trace/interior polynomial subspace is rank deficient"
        )
    qualification_rank_seconds = (
        time.perf_counter() - qualification_started
    )
    qr_started = time.perf_counter()
    orthogonal_columns, _ = np.linalg.qr(
        nodal_coefficients.T,
        mode="reduced",
    )
    qr_seconds = time.perf_counter() - qr_started
    interpolation_payload_started = time.perf_counter()
    interpolation_points: list[list[np.ndarray]] = []
    interpolation_matrices: list[list[np.ndarray]] = []
    for dimension in range(tdim + 1):
        source = (
            interior_element if dimension == tdim else trace_element
        )
        interpolation_points.append(
            [np.asarray(values).copy() for values in source.x[dimension]]
        )
        interpolation_matrices.append(
            [np.asarray(values).copy() for values in source.M[dimension]]
        )
    interpolation_payload_seconds = (
        time.perf_counter() - interpolation_payload_started
    )
    constructor = {
        "cell_type": basix.CellType.hexahedron,
        "value_shape": tuple(polynomial_element.value_shape),
        "wcoeffs": np.ascontiguousarray(orthogonal_columns.T),
        "x": interpolation_points,
        "M": interpolation_matrices,
        "interpolation_nderivs": polynomial_element.interpolation_nderivs,
        "map_type": polynomial_element.map_type,
        "sobolev_space": polynomial_element.sobolev_space,
        "discontinuous": False,
        "embedded_subdegree": min(
            trace_element.embedded_subdegree,
            interior_element.embedded_subdegree,
        ),
        "embedded_superdegree": polynomial_element.embedded_superdegree,
        "polyset_type": polynomial_element.polyset_type,
    }
    custom_element_started = time.perf_counter()
    custom = basix.create_custom_element(
        constructor["cell_type"],
        constructor["value_shape"],
        constructor["wcoeffs"],
        interpolation_points,
        interpolation_matrices,
        constructor["interpolation_nderivs"],
        constructor["map_type"],
        constructor["sobolev_space"],
        constructor["discontinuous"],
        constructor["embedded_subdegree"],
        constructor["embedded_superdegree"],
        constructor["polyset_type"],
    )
    custom_element_seconds = time.perf_counter() - custom_element_started
    identity_checks_started = time.perf_counter()
    if custom.dim != expected_dimension:
        raise RuntimeError(
            "fixed trace/interior element dimension does not close"
        )
    custom_trace = _flatten_entity_dofs(custom, range(tdim))
    custom_interior = np.asarray(
        custom.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    if (
        not np.array_equal(custom_trace, np.arange(len(trace_dofs)))
        or not np.array_equal(
            custom_interior,
            np.arange(len(trace_dofs), expected_dimension),
        )
    ):
        raise RuntimeError(
            "fixed trace/interior element did not retain trace-first numbering"
        )
    identity_checks_seconds = (
        time.perf_counter() - identity_checks_started
    )
    total_seconds = time.perf_counter() - total_started
    return (
        custom,
        {
            "polynomial_subspace_rank": polynomial_rank,
            "coefficient_matrix_condition_number": (
                float(np.linalg.cond(custom.coefficient_matrix))
                if qualification_audit
                else None
            ),
            "custom": True,
            "qualification_audit_executed": bool(
                qualification_audit
            ),
            "construction_profile": {
                "schema_version": (
                    "task035b.fixed-trace-element-cold-build-profile.v1"
                ),
                "status": "custom_element_built",
                "strategy": (
                    "basix_reference_full_interpolation"
                    if qualification_audit
                    else "selected_public_interpolation_v1"
                ),
                "polynomial_element_reused": True,
                "selected_interpolation_enabled": not bool(
                    qualification_audit
                ),
                "trace_interpolation_strategy": (
                    trace_interpolation_strategy
                ),
                "interior_interpolation_strategy": (
                    interior_interpolation_strategy
                ),
                "numerical_identity_contract": (
                    "selected columns reconstruct the public Basix "
                    "interpolation operator exactly on the qualified ABI"
                ),
                "stage_seconds": {
                    "standard_trace_element": float(
                        trace_element_seconds
                    ),
                    "standard_interior_element": float(
                        interior_element_seconds
                    ),
                    "duplicate_polynomial_element": 0.0,
                    "trace_interpolation": float(
                        trace_interpolation_seconds
                    ),
                    "interior_interpolation": float(
                        interior_interpolation_seconds
                    ),
                    "nodal_coefficient_formation": float(
                        nodal_coefficients_seconds
                    ),
                    "qualification_rank": float(
                        qualification_rank_seconds
                    ),
                    "dense_qr": float(qr_seconds),
                    "interpolation_payload_copy": float(
                        interpolation_payload_seconds
                    ),
                    "basix_create_custom_element": float(
                        custom_element_seconds
                    ),
                    "identity_checks": float(identity_checks_seconds),
                    "total": float(total_seconds),
                },
            },
        },
        constructor,
    )


def _create_trace_interior_element(
    trace_degree: int,
    cell_interior_degree: int,
    qualification_audit: bool = True,
) -> tuple[basix.finite_element.FiniteElement, dict[str, Any]]:
    """Compatibility wrapper around the cached constructor-data path."""

    element, audit, _ = _create_trace_interior_element_data(
        trace_degree,
        cell_interior_degree,
        qualification_audit,
    )
    return element, audit


def fixed_trace_hcurl_ufl_element(
    trace_degree: int,
    interior_degree: int,
):
    """Return a globally uniform fixed-trace H(curl) UFL element.

    The supported production path uses one trace degree and one richer
    interior degree on every hexahedral cell.  It omits repeated dense
    qualification work; qualification belongs to tests and release evidence.
    """

    trace_degree = int(trace_degree)
    interior_degree = int(interior_degree)
    if not 1 <= trace_degree < interior_degree <= 6:
        raise ValueError(
            "fixed-trace H(curl) requires "
            "1 <= trace_degree < interior_degree <= 6"
        )
    custom, audit = _create_trace_interior_element(
        trace_degree,
        interior_degree,
        False,
    )
    if audit["qualification_audit_executed"] is not False:
        raise RuntimeError("fixed-trace lightweight construction ran audits")
    return wrap_custom_element_fast(custom)


def persistent_fixed_trace_hcurl_ufl_element(
    trace_degree: int,
    interior_degree: int,
    *,
    cache_directory: str,
    source_sha: str,
    cache_mode: str,
    comm: Any,
):
    """Restore/build a SHA-bound globally uniform fixed-trace element."""

    from src.adaptivity.fixed_trace_element_cache import (
        fixed_trace_element_build,
        load_or_build_fixed_trace_element,
    )

    trace_degree = int(trace_degree)
    interior_degree = int(interior_degree)
    if not 1 <= trace_degree < interior_degree <= 6:
        raise ValueError(
            "persistent fixed-trace H(curl) requires "
            "1 <= trace_degree < interior_degree <= 6"
        )

    def build(
        resolved_trace_degree: int,
        resolved_interior_degree: int,
    ):
        custom, audit, constructor = _create_trace_interior_element_data(
            resolved_trace_degree,
            resolved_interior_degree,
            False,
        )
        if audit["qualification_audit_executed"] is not False:
            raise RuntimeError(
                "persistent fixed-trace construction ran qualification audits"
            )
        if constructor is None:
            raise RuntimeError(
                "persistent fixed-trace construction lacks custom payload"
            )
        return fixed_trace_element_build(
            custom,
            build_audit=audit.get("construction_profile"),
            **constructor,
        )

    custom, cache_audit = load_or_build_fixed_trace_element(
        trace_degree=trace_degree,
        interior_degree=interior_degree,
        cache_directory=cache_directory,
        source_sha=source_sha,
        cache_mode=cache_mode,
        comm=comm,
        builder=build,
    )
    return wrap_custom_element_fast(custom), cache_audit
