"""Conforming reduced-trace H(curl) elements for Task035b regionwise p.

The first production-independent building block keeps one globally conforming
low-order edge/face trace while exposing a richer cell-interior polynomial
space.  It is a genuine Basix custom element: adjacent cells share the low
trace DoFs, and the high cell modes remain cell-local.  Assembly-time static
condensation can therefore remove every interior mode from the global matrix
instead of retaining inactive max-p rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import time
from typing import Any

import basix
import basix.ufl
import numpy as np
from scipy.linalg import qr


@dataclass(frozen=True)
class ReducedTraceHcurlElement:
    """One custom element and the lower-interior embedding it contains."""

    element: basix.finite_element.FiniteElement
    low_element: basix.finite_element.FiniteElement
    trace_degree: int
    low_interior_degree: int
    interior_degree: int
    trace_dofs: np.ndarray
    high_interior_dofs: np.ndarray
    low_interior_dofs: np.ndarray
    low_to_reduced: np.ndarray
    low_interior_embedding: np.ndarray
    audit: dict[str, Any]


def audit_tensor_product_exact_sequence(
    element: basix.finite_element.FiniteElement,
    *,
    trace_degree: int,
    interior_degree: int,
) -> dict[str, Any]:
    """Audit the local curl kernel against the mixed scalar companion.

    A tensor-product scalar companion with Q(trace) boundary modes and
    Q(interior) cell-bubble modes has

    ``[(t+1)^3-(t-1)^3] + (i-1)^3 - 1``

    nonconstant gradients. The H(curl) polynomial space must expose exactly
    that many curl-null modes as a prerequisite for a local de Rham sequence.
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
        "schema_version": "task035b.local-tensor-exact-sequence-audit.v1",
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


def _standard_hexa_hcurl(degree: int) -> basix.finite_element.FiniteElement:
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
    """Form only requested columns of a same-map Basix interpolation.

    ``basix.compute_interpolation_operator`` tabulates every source basis
    function at the target interpolation points and then applies the target
    interpolation matrix.  The fixed-trace constructor only consumes the
    edge/face columns of the trace element and the cell-interior columns of
    the interior element.  Forming just those columns avoids two large,
    immediately discarded dense blocks.

    This helper is deliberately limited to the derivative-free, equal-value,
    equal-map case used by the hexahedral N1curl constructor.  The ordinary
    qualified element path continues to call Basix's reference routine.
    """

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
    """Build one H(curl) element with independent trace/interior orders."""

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

    # The maximum-order polynomial element is already one of the two source
    # elements. Reusing that immutable Basix object is bitwise equivalent to
    # constructing a duplicate and removes one high-order element build.
    polynomial_element = (
        trace_element
        if trace_degree > cell_interior_degree
        else interior_element
    )
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
            "mixed trace/interior polynomial subspace is rank deficient"
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
        raise RuntimeError("mixed trace/interior element dimension does not close")
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
            "mixed trace/interior element did not retain trace-first numbering"
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


@lru_cache(maxsize=16)
def create_reduced_trace_hcurl_element(
    trace_degree: int,
    interior_degree: int,
    low_interior_degree: int | None = None,
) -> ReducedTraceHcurlElement:
    """Create a high space plus an exact lower-interior embedded cell space."""

    trace_degree = int(trace_degree)
    interior_degree = int(interior_degree)
    low_interior_degree = (
        trace_degree
        if low_interior_degree is None
        else int(low_interior_degree)
    )
    if not 1 <= low_interior_degree <= trace_degree < interior_degree <= 6:
        raise ValueError(
            "Task035b regionwise H(curl) requires "
            "1 <= low_interior_degree <= trace_degree "
            "< interior_degree <= 6"
        )
    custom, high_element_audit = _create_trace_interior_element(
        trace_degree,
        interior_degree,
    )
    low_element, low_element_audit = _create_trace_interior_element(
        trace_degree,
        low_interior_degree,
    )
    tdim = 3
    custom_trace_dofs = _flatten_entity_dofs(custom, range(tdim))
    custom_interior_dofs = np.asarray(
        custom.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    low_trace_dofs = _flatten_entity_dofs(low_element, range(tdim))
    low_interior_dofs = np.asarray(
        low_element.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    low_to_reduced = basix.compute_interpolation_operator(
        low_element,
        custom,
    )
    low_interior_trace_leakage = float(
        np.max(
            np.abs(
                low_to_reduced[
                    np.ix_(custom_trace_dofs, low_interior_dofs)
                ]
            ),
            initial=0.0,
        )
    )
    low_trace_identity_error = float(
        np.max(
            np.abs(
                low_to_reduced[
                    np.ix_(custom_trace_dofs, low_trace_dofs)
                ]
                - np.eye(len(custom_trace_dofs))
            ),
            initial=0.0,
        )
    )
    low_interior_embedding = np.asarray(
        low_to_reduced[
            np.ix_(custom_interior_dofs, low_interior_dofs)
        ],
        dtype=np.float64,
    )
    low_embedding_rank = int(np.linalg.matrix_rank(low_interior_embedding))
    low_space_rank = int(np.linalg.matrix_rank(low_to_reduced))
    if (
        low_interior_trace_leakage > 1.0e-11
        or low_trace_identity_error > 1.0e-11
        or low_embedding_rank != len(low_interior_dofs)
        or low_space_rank != low_element.dim
    ):
        raise RuntimeError(
            "lower mixed-interior space is not embedded exactly"
        )
    entity_counts = [
        [len(entity) for entity in dimension]
        for dimension in custom.entity_dofs
    ]
    high_exact_sequence = audit_tensor_product_exact_sequence(
        custom,
        trace_degree=trace_degree,
        interior_degree=interior_degree,
    )
    low_exact_sequence = audit_tensor_product_exact_sequence(
        low_element,
        trace_degree=trace_degree,
        interior_degree=low_interior_degree,
    )
    audit = {
        "schema_version": "task035b.reduced-trace-hcurl-element.v2",
        "status": "reduced_trace_hcurl_element_built",
        "pass": True,
        "cell_type": "hexahedron",
        "trace_degree": trace_degree,
        "low_interior_degree": low_interior_degree,
        "interior_degree": interior_degree,
        "custom_dimension": int(custom.dim),
        "standard_low_dimension": int(low_element.dim),
        "standard_high_dimension": int(
            _standard_hexa_hcurl(interior_degree).dim
        ),
        "trace_dimension": int(len(custom_trace_dofs)),
        "low_interior_dimension": int(len(low_interior_dofs)),
        "high_interior_dimension": int(len(custom_interior_dofs)),
        "polynomial_subspace_rank": high_element_audit[
            "polynomial_subspace_rank"
        ],
        "coefficient_matrix_condition_number": high_element_audit[
            "coefficient_matrix_condition_number"
        ],
        "low_element_custom": low_element_audit["custom"],
        "low_polynomial_subspace_rank": low_element_audit[
            "polynomial_subspace_rank"
        ],
        "low_coefficient_matrix_condition_number": low_element_audit[
            "coefficient_matrix_condition_number"
        ],
        "entity_dofs": entity_counts,
        "low_space_embedding_rank": low_space_rank,
        "low_interior_embedding_rank": low_embedding_rank,
        "low_trace_identity_error_max": low_trace_identity_error,
        "low_interior_trace_leakage_max": low_interior_trace_leakage,
        "high_exact_sequence": high_exact_sequence,
        "low_exact_sequence": low_exact_sequence,
        "both_high_and_low_exact_sequence_pass": bool(
            high_exact_sequence["pass"] and low_exact_sequence["pass"]
        ),
        "map_type": str(custom.map_type),
        "sobolev_space": str(custom.sobolev_space),
        "continuity_policy": (
            "shared edges/faces use the trace-degree moments; selected "
            "cell-interior modes remain local"
        ),
        "ordinary_default_changed": False,
    }
    return ReducedTraceHcurlElement(
        element=custom,
        low_element=low_element,
        trace_degree=trace_degree,
        low_interior_degree=low_interior_degree,
        interior_degree=interior_degree,
        trace_dofs=custom_trace_dofs,
        high_interior_dofs=custom_interior_dofs,
        low_interior_dofs=low_interior_dofs,
        low_to_reduced=np.asarray(low_to_reduced, dtype=np.float64),
        low_interior_embedding=low_interior_embedding,
        audit=audit,
    )


def reduced_trace_hcurl_ufl_element(
    trace_degree: int,
    interior_degree: int,
):
    """Return the UFL wrapper for a cached reduced-trace Basix element."""

    return basix.ufl.wrap_element(
        create_reduced_trace_hcurl_element(
            trace_degree,
            interior_degree,
        ).element
    )


def fixed_trace_hcurl_ufl_element(
    trace_degree: int,
    interior_degree: int,
):
    """Build and byte-wrap the fixed-trace element without repeated audits.

    The custom polynomial basis and entity moments are identical to
    :func:`create_reduced_trace_hcurl_element`.  Only the repeated
    matrix-rank/condition-number, lower-space embedding, and sampled curl-null
    qualification are omitted from each new solver process.  The caller must
    explicitly opt into this research path; ordinary reduced-trace runs retain
    the legacy Basix UFL wrapper.
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
    from .fast_custom_element_ufl import wrap_custom_element_fast

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
    """Restore/build and byte-wrap an opt-in cached fixed-trace element."""

    from .fixed_trace_element_cache import (
        fixed_trace_element_build,
        load_or_build_fixed_trace_element,
    )
    from .fast_custom_element_ufl import wrap_custom_element_fast

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
        trace_degree=int(trace_degree),
        interior_degree=int(interior_degree),
        cache_directory=cache_directory,
        source_sha=source_sha,
        cache_mode=cache_mode,
        comm=comm,
        builder=build,
    )
    return wrap_custom_element_fast(custom), cache_audit


def regionwise_interior_p_dof_budget(
    *,
    global_edges: int,
    global_faces: int,
    global_cells: int,
    high_interior_cells: int,
    trace_degree: int,
    low_interior_degree: int,
    high_interior_degree: int,
) -> dict[str, Any]:
    """Count the physically active basis modes for fixed-trace regionwise p."""

    counts = {
        "global_edges": int(global_edges),
        "global_faces": int(global_faces),
        "global_cells": int(global_cells),
        "high_interior_cells": int(high_interior_cells),
    }
    if (
        min(counts.values()) < 0
        or counts["high_interior_cells"] > counts["global_cells"]
    ):
        raise ValueError("regionwise-p entity and cell counts are invalid")
    if not (
        1
        <= int(low_interior_degree)
        <= int(trace_degree)
        < int(high_interior_degree)
        <= 6
    ):
        raise ValueError(
            "regionwise-p budget requires 1 <= low interior p <= trace p "
            "< high interior p <= 6"
        )
    trace = _standard_hexa_hcurl(int(trace_degree))
    low = _standard_hexa_hcurl(int(low_interior_degree))
    high = _standard_hexa_hcurl(int(high_interior_degree))
    edge_dofs = len(trace.entity_dofs[1][0])
    face_dofs = len(trace.entity_dofs[2][0])
    low_interior_dofs = len(low.entity_dofs[3][0])
    high_interior_dofs = len(high.entity_dofs[3][0])
    low_cells = counts["global_cells"] - counts["high_interior_cells"]
    trace_dofs = (
        counts["global_edges"] * edge_dofs
        + counts["global_faces"] * face_dofs
    )
    interior_dofs = (
        low_cells * low_interior_dofs
        + counts["high_interior_cells"] * high_interior_dofs
    )
    active_full3d_equivalent_dofs = trace_dofs + interior_dofs
    return {
        "schema_version": "task035b.regionwise-interior-p-dof-budget.v1",
        "status": "active_mode_count_complete",
        "pass": True,
        "trace_degree": int(trace_degree),
        "low_interior_degree": int(low_interior_degree),
        "high_interior_degree": int(high_interior_degree),
        **counts,
        "low_interior_cells": int(low_cells),
        "edge_dofs_per_entity": int(edge_dofs),
        "face_interior_dofs_per_entity": int(face_dofs),
        "low_cell_interior_dofs": int(low_interior_dofs),
        "high_cell_interior_dofs": int(high_interior_dofs),
        "active_trace_dofs": int(trace_dofs),
        "active_cell_interior_dofs": int(interior_dofs),
        "active_full3d_equivalent_dofs": int(active_full3d_equivalent_dofs),
        "inactive_max_p_rows_retained_in_matrix": False,
        "matrix_semantics": (
            "cell interiors are local Schur modes; only the shared low-order "
            "trace is globally numbered"
        ),
    }


__all__ = [
    "ReducedTraceHcurlElement",
    "audit_tensor_product_exact_sequence",
    "create_reduced_trace_hcurl_element",
    "fixed_trace_hcurl_ufl_element",
    "persistent_fixed_trace_hcurl_ufl_element",
    "regionwise_interior_p_dof_budget",
    "reduced_trace_hcurl_ufl_element",
]
