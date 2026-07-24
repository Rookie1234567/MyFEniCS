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
from typing import Any

import basix
import basix.ufl
import numpy as np


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


@lru_cache(maxsize=16)
def _create_trace_interior_element(
    trace_degree: int,
    cell_interior_degree: int,
) -> tuple[basix.finite_element.FiniteElement, dict[str, Any]]:
    """Build one H(curl) element with independent trace/interior orders."""

    trace_element = _standard_hexa_hcurl(trace_degree)
    interior_element = _standard_hexa_hcurl(cell_interior_degree)
    if trace_degree == cell_interior_degree:
        return trace_element, {
            "polynomial_subspace_rank": int(trace_element.dim),
            "coefficient_matrix_condition_number": float(
                np.linalg.cond(trace_element.coefficient_matrix)
            ),
            "custom": False,
        }
    polynomial_element = _standard_hexa_hcurl(
        max(trace_degree, cell_interior_degree)
    )
    tdim = 3
    trace_dofs = _flatten_entity_dofs(trace_element, range(tdim))
    interior_dofs = np.asarray(
        interior_element.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    trace_to_polynomial = basix.compute_interpolation_operator(
        trace_element,
        polynomial_element,
    )
    interior_to_polynomial = basix.compute_interpolation_operator(
        interior_element,
        polynomial_element,
    )
    nodal_coefficients = np.vstack(
        (
            trace_to_polynomial[:, trace_dofs].T
            @ polynomial_element.coefficient_matrix,
            interior_to_polynomial[:, interior_dofs].T
            @ polynomial_element.coefficient_matrix,
        )
    )
    expected_dimension = len(trace_dofs) + len(interior_dofs)
    polynomial_rank = int(np.linalg.matrix_rank(nodal_coefficients))
    if polynomial_rank != expected_dimension:
        raise RuntimeError("mixed trace/interior polynomial subspace is rank deficient")
    orthogonal_columns, _ = np.linalg.qr(
        nodal_coefficients.T,
        mode="reduced",
    )
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
    custom = basix.create_custom_element(
        basix.CellType.hexahedron,
        polynomial_element.value_shape,
        np.ascontiguousarray(orthogonal_columns.T),
        interpolation_points,
        interpolation_matrices,
        polynomial_element.interpolation_nderivs,
        polynomial_element.map_type,
        polynomial_element.sobolev_space,
        False,
        min(
            trace_element.embedded_subdegree,
            interior_element.embedded_subdegree,
        ),
        polynomial_element.embedded_superdegree,
        polynomial_element.polyset_type,
    )
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
    return custom, {
        "polynomial_subspace_rank": polynomial_rank,
        "coefficient_matrix_condition_number": float(
            np.linalg.cond(custom.coefficient_matrix)
        ),
        "custom": True,
    }


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
    "create_reduced_trace_hcurl_element",
    "regionwise_interior_p_dof_budget",
    "reduced_trace_hcurl_ufl_element",
]
