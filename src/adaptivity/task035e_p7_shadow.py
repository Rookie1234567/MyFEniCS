"""Cell-interior-only p7 shadow enrichment for Task035e.

This module is deliberately a low-level, shadow-only component.  It embeds
the ordinary hexahedral p6 N1curl/Q pair into p7 with Basix interpolation and
adds the *complete* coefficient-Riesz complement carried by p7 cell-interior
degrees of freedom.  Edge and face traces therefore remain exactly p6.

The component is useful for a conservative interior-error lower bound.  It is
not a production p7 space, it cannot create a next production degree plan, and
it cannot by itself satisfy the Task035e F1 p-shadow stopping condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping

import basix
import basix.ufl
import numpy as np
from scipy.linalg import qr, solve_triangular


_P6 = 6
_P7 = 7
_FORMAL_GOAL_COUNT = 59
_ROUND_OFF_LIMIT = 2.0e-10
_HCURL = "hcurl"
_H1 = "h1"


def _readonly(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values)
    result.setflags(write=False)
    return result


def _maximum_absolute(values: np.ndarray) -> float:
    return float(np.max(np.abs(values), initial=0.0))


def _standard_element(
    family: str,
    degree: int,
) -> basix.finite_element.FiniteElement:
    if family == _HCURL:
        return basix.ufl.element(
            "N1curl",
            "hexahedron",
            int(degree),
        ).basix_element
    if family == _H1:
        return basix.ufl.element(
            "Lagrange",
            "hexahedron",
            int(degree),
            lagrange_variant=basix.LagrangeVariant.gll_warped,
        ).basix_element
    raise ValueError(f"unsupported de Rham family {family!r}")


def _entity_dofs(
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


def _rank_from_pivoted_qr(matrix: np.ndarray) -> tuple[int, float]:
    values = np.asarray(matrix)
    if min(values.shape, default=0) == 0:
        return 0, 0.0
    _orthogonal, upper, _pivots = qr(
        values,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(upper))
    tolerance = (
        0.0
        if len(diagonal) == 0
        else float(
            diagonal[0]
            * max(values.shape)
            * np.finfo(np.float64).eps
        )
    )
    return int(np.count_nonzero(diagonal > tolerance)), tolerance


def _canonicalize_columns(matrix: np.ndarray) -> np.ndarray:
    result = np.asarray(matrix, dtype=np.float64).copy()
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        if result[pivot, column] < 0.0:
            result[:, column] *= -1.0
    return np.ascontiguousarray(result)


def _discrete_gradient(
    scalar_element: basix.finite_element.FiniteElement,
    hcurl_element: basix.finite_element.FiniteElement,
) -> np.ndarray:
    points = np.asarray(hcurl_element.points)
    scalar_table = np.asarray(scalar_element.tabulate(1, points))
    if scalar_table.shape[:2] != (4, len(points)):
        raise RuntimeError(
            "unexpected scalar derivative tabulation for a hexahedron"
        )
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
    ).reshape(3 * len(points), int(scalar_element.dim))
    return np.ascontiguousarray(
        np.asarray(hcurl_element.interpolation_matrix) @ flattened
    )


@dataclass(frozen=True)
class _FamilyComplement:
    """Construction data for one p6-plus-p7-interior family."""

    p6_element: basix.finite_element.FiniteElement
    p7_element: basix.finite_element.FiniteElement
    p6_to_p7: np.ndarray
    p7_to_p6: np.ndarray
    expansion: np.ndarray
    complement: np.ndarray
    p6_trace_dofs: np.ndarray
    p6_interior_dofs: np.ndarray
    p7_trace_dofs: np.ndarray
    p7_interior_dofs: np.ndarray
    trace_q: np.ndarray
    trace_r: np.ndarray
    interior_q1: np.ndarray
    interior_r: np.ndarray
    interior_complement: np.ndarray
    metrics: Mapping[str, Any]


def _build_family_complement(family: str) -> _FamilyComplement:
    p6_element = _standard_element(family, _P6)
    p7_element = _standard_element(family, _P7)
    p6_to_p7 = np.asarray(
        basix.compute_interpolation_operator(p6_element, p7_element),
        dtype=np.float64,
    )
    p7_to_p6 = np.asarray(
        basix.compute_interpolation_operator(p7_element, p6_element),
        dtype=np.float64,
    )
    p6_trace = _entity_dofs(p6_element, range(3))
    p6_interior = _entity_dofs(p6_element, range(3, 4))
    p7_trace = _entity_dofs(p7_element, range(3))
    p7_interior = _entity_dofs(p7_element, range(3, 4))

    interior_embedding = np.ascontiguousarray(
        p6_to_p7[np.ix_(p7_interior, p6_interior)]
    )
    interior_q, interior_r_full = np.linalg.qr(
        interior_embedding,
        mode="complete",
    )
    interior_r = np.ascontiguousarray(
        interior_r_full[: len(p6_interior)]
    )
    interior_q1 = np.ascontiguousarray(
        interior_q[:, : len(p6_interior)]
    )
    interior_complement = _canonicalize_columns(
        interior_q[:, len(p6_interior) :]
    )
    complement = np.zeros(
        (int(p7_element.dim), interior_complement.shape[1]),
        dtype=np.float64,
    )
    complement[p7_interior] = interior_complement
    expansion = np.ascontiguousarray(
        np.concatenate((p6_to_p7, complement), axis=1)
    )

    trace_embedding = np.ascontiguousarray(
        p6_to_p7[np.ix_(p7_trace, p6_trace)]
    )
    trace_q, trace_r = np.linalg.qr(trace_embedding, mode="reduced")
    trace_rank, trace_rank_tolerance = _rank_from_pivoted_qr(
        trace_embedding
    )
    interior_rank, interior_rank_tolerance = _rank_from_pivoted_qr(
        interior_embedding
    )
    reverse_error = _maximum_absolute(
        p7_to_p6 @ p6_to_p7 - np.eye(int(p6_element.dim))
    )
    p6_interior_trace_error = _maximum_absolute(
        p6_to_p7[np.ix_(p7_trace, p6_interior)]
    )
    complement_trace_error = _maximum_absolute(complement[p7_trace])
    complement_gram_error = _maximum_absolute(
        interior_complement.T @ interior_complement
        - np.eye(interior_complement.shape[1])
    )
    orthogonality_error = _maximum_absolute(
        interior_embedding.T @ interior_complement
    )
    naive_prefix = np.eye(int(p7_element.dim), int(p6_element.dim))
    naive_prefix_error = _maximum_absolute(p6_to_p7 - naive_prefix)
    active_rank = (
        trace_rank + interior_rank + interior_complement.shape[1]
    )
    metrics = MappingProxyType(
        {
            "family": family,
            "p6_dimension": int(p6_element.dim),
            "p7_dimension": int(p7_element.dim),
            "p6_trace_dimension": len(p6_trace),
            "p6_interior_dimension": len(p6_interior),
            "p7_trace_dimension": len(p7_trace),
            "p7_interior_dimension": len(p7_interior),
            "interior_complement_dimension": (
                interior_complement.shape[1]
            ),
            "active_dimension": expansion.shape[1],
            "active_rank": active_rank,
            "trace_embedding_rank": trace_rank,
            "trace_embedding_rank_tolerance": trace_rank_tolerance,
            "interior_embedding_rank": interior_rank,
            "interior_embedding_rank_tolerance": (
                interior_rank_tolerance
            ),
            "p7_to_p6_left_inverse_error_max": reverse_error,
            "p6_interior_p7_trace_support_max": (
                p6_interior_trace_error
            ),
            "complement_p7_trace_support_max": complement_trace_error,
            "complement_coefficient_gram_error_max": (
                complement_gram_error
            ),
            "p6_interior_complement_orthogonality_error_max": (
                orthogonality_error
            ),
            "naive_prefix_error_max": naive_prefix_error,
            "prefix_assumption_used": False,
            "orthogonality_metric": (
                "canonical_p7_cell_interpolation_coefficient_inner_product"
            ),
            "complement_span_is_metric_independent": True,
            "affine_physical_riesz_credit_claimed": False,
        }
    )
    checks = (
        trace_rank == len(p6_trace),
        interior_rank == len(p6_interior),
        active_rank == expansion.shape[1],
        reverse_error <= _ROUND_OFF_LIMIT,
        p6_interior_trace_error <= _ROUND_OFF_LIMIT,
        complement_trace_error <= _ROUND_OFF_LIMIT,
        complement_gram_error <= _ROUND_OFF_LIMIT,
        orthogonality_error <= _ROUND_OFF_LIMIT,
        naive_prefix_error > 1.0e-3,
    )
    if not all(checks):
        raise RuntimeError(
            f"{family} p7 cell-interior complement audit failed"
        )

    arrays = (
        p6_to_p7,
        p7_to_p6,
        expansion,
        complement,
        p6_trace,
        p6_interior,
        p7_trace,
        p7_interior,
        trace_q,
        trace_r,
        interior_q1,
        interior_r,
        interior_complement,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return _FamilyComplement(
        p6_element=p6_element,
        p7_element=p7_element,
        p6_to_p7=readonly[0],
        p7_to_p6=readonly[1],
        expansion=readonly[2],
        complement=readonly[3],
        p6_trace_dofs=readonly[4],
        p6_interior_dofs=readonly[5],
        p7_trace_dofs=readonly[6],
        p7_interior_dofs=readonly[7],
        trace_q=readonly[8],
        trace_r=readonly[9],
        interior_q1=readonly[10],
        interior_r=readonly[11],
        interior_complement=readonly[12],
        metrics=metrics,
    )


def _coordinates_in_shadow(
    family: _FamilyComplement,
    values: np.ndarray,
) -> np.ndarray:
    """Express known shadow-space columns without a dense pseudoinverse."""

    rhs = np.asarray(values)
    vector_input = rhs.ndim == 1
    if vector_input:
        rhs = rhs[:, None]
    if rhs.ndim != 2 or rhs.shape[0] != int(family.p7_element.dim):
        raise ValueError("p7 shadow coordinate input has the wrong shape")

    trace_rhs = rhs[family.p7_trace_dofs]
    trace_values = solve_triangular(
        family.trace_r,
        family.trace_q.T @ trace_rhs,
        lower=False,
        check_finite=False,
    )
    interior_rhs = (
        rhs[family.p7_interior_dofs]
        - family.p6_to_p7[
            np.ix_(family.p7_interior_dofs, family.p6_trace_dofs)
        ]
        @ trace_values
    )
    p6_interior_values = solve_triangular(
        family.interior_r,
        family.interior_q1.T @ interior_rhs,
        lower=False,
        check_finite=False,
    )
    complement_values = family.interior_complement.T @ interior_rhs

    coordinates = np.zeros(
        (family.expansion.shape[1], rhs.shape[1]),
        dtype=np.result_type(rhs, np.float64),
    )
    coordinates[family.p6_trace_dofs] = trace_values
    coordinates[family.p6_interior_dofs] = p6_interior_values
    coordinates[int(family.p6_element.dim) :] = complement_values
    if vector_input:
        return np.ascontiguousarray(coordinates[:, 0])
    return np.ascontiguousarray(coordinates)


def _d4_cell_interior_audit(
    family: _FamilyComplement,
) -> tuple[float, float, int]:
    maximum_invariance_error = 0.0
    maximum_trace_support = 0.0
    action_count = 0
    block_size = family.complement.shape[1]
    for face in range(6):
        for reflected in (0, 1):
            for rotations in range(4):
                cell_info = (
                    (reflected << (3 * face))
                    | (rotations << (3 * face + 1))
                )
                oriented = np.ascontiguousarray(family.complement.copy())
                family.p7_element.T_apply(
                    oriented.ravel(),
                    block_size,
                    int(cell_info),
                )
                maximum_invariance_error = max(
                    maximum_invariance_error,
                    _maximum_absolute(oriented - family.complement),
                )
                maximum_trace_support = max(
                    maximum_trace_support,
                    _maximum_absolute(oriented[family.p7_trace_dofs]),
                )
                action_count += 1
    return maximum_invariance_error, maximum_trace_support, action_count


@dataclass(frozen=True)
class P7InteriorShadowSpace:
    """Immutable p6 trace plus p7 cell-interior shadow pair."""

    hcurl_p6_element: basix.finite_element.FiniteElement
    hcurl_p7_element: basix.finite_element.FiniteElement
    h1_p6_element: basix.finite_element.FiniteElement
    h1_p7_element: basix.finite_element.FiniteElement
    hcurl_p6_to_p7: np.ndarray
    h1_p6_to_p7: np.ndarray
    hcurl_interior_complement: np.ndarray
    h1_interior_complement: np.ndarray
    hcurl_expansion: np.ndarray
    h1_expansion: np.ndarray
    discrete_gradient: np.ndarray
    hcurl_trace_dofs: np.ndarray
    hcurl_interior_dofs: np.ndarray
    audit: Mapping[str, Any]
    production_degrees_unchanged: frozenset[int]
    shadow_only: bool = True
    selectable_as_production: bool = False
    next_production_plan: None = None
    coverage_credit: str = "interior_lower_bound_only"

    @property
    def hcurl_dimension(self) -> int:
        return int(self.hcurl_expansion.shape[1])

    @property
    def h1_dimension(self) -> int:
        return int(self.h1_expansion.shape[1])


@lru_cache(maxsize=1)
def build_p7_interior_shadow_space() -> P7InteriorShadowSpace:
    """Build and audit the shadow-only p7 cell-interior exact sequence."""

    hcurl = _build_family_complement(_HCURL)
    h1 = _build_family_complement(_H1)
    p6_gradient = _discrete_gradient(
        h1.p6_element,
        hcurl.p6_element,
    )
    p7_gradient = _discrete_gradient(
        h1.p7_element,
        hcurl.p7_element,
    )
    p6_commuting_error = _maximum_absolute(
        p7_gradient @ h1.p6_to_p7
        - hcurl.p6_to_p7 @ p6_gradient
    )
    expanded_gradient = np.ascontiguousarray(
        p7_gradient @ h1.expansion
    )
    shadow_gradient = _coordinates_in_shadow(
        hcurl,
        expanded_gradient,
    )
    gradient_range_error = _maximum_absolute(
        hcurl.expansion @ shadow_gradient - expanded_gradient
    )
    gradient_rank, gradient_rank_tolerance = _rank_from_pivoted_qr(
        shadow_gradient
    )
    h1_extra_start = int(h1.p6_element.dim)
    extra_gradient_trace_error = _maximum_absolute(
        expanded_gradient[
            np.ix_(
                hcurl.p7_trace_dofs,
                np.arange(h1_extra_start, h1.expansion.shape[1]),
            )
        ]
    )
    hcurl_d4_error, hcurl_d4_trace, hcurl_d4_actions = (
        _d4_cell_interior_audit(hcurl)
    )
    h1_d4_error, h1_d4_trace, h1_d4_actions = (
        _d4_cell_interior_audit(h1)
    )

    hcurl_trace_active = np.asarray(hcurl.p6_trace_dofs, dtype=np.int32)
    hcurl_interior_active = np.concatenate(
        (
            np.asarray(hcurl.p6_interior_dofs, dtype=np.int32),
            np.arange(
                int(hcurl.p6_element.dim),
                hcurl.expansion.shape[1],
                dtype=np.int32,
            ),
        )
    )
    checks = {
        "p6_hcurl_dimension_882": int(hcurl.p6_element.dim) == 882,
        "p7_hcurl_dimension_1344": int(hcurl.p7_element.dim) == 1344,
        "extra_hcurl_interior_dimension_306": (
            hcurl.complement.shape[1] == 306
        ),
        "p6_h1_dimension_343": int(h1.p6_element.dim) == 343,
        "p7_h1_dimension_512": int(h1.p7_element.dim) == 512,
        "extra_h1_interior_dimension_91": (
            h1.complement.shape[1] == 91
        ),
        "hcurl_active_rank_complete": (
            int(hcurl.metrics["active_rank"])
            == hcurl.expansion.shape[1]
        ),
        "h1_active_rank_complete": (
            int(h1.metrics["active_rank"]) == h1.expansion.shape[1]
        ),
        "p6_discrete_gradient_injection_commutes": (
            p6_commuting_error <= _ROUND_OFF_LIMIT
        ),
        "shadow_discrete_gradient_range_closes": (
            gradient_range_error <= _ROUND_OFF_LIMIT
        ),
        "shadow_gradient_kernel_is_constant_only": (
            gradient_rank == h1.expansion.shape[1] - 1
        ),
        "extra_h1_gradient_has_zero_p7_trace": (
            extra_gradient_trace_error <= _ROUND_OFF_LIMIT
        ),
        "all_hcurl_face_d4_actions_leave_cell_interior_unchanged": (
            hcurl_d4_actions == 48
            and hcurl_d4_error <= _ROUND_OFF_LIMIT
            and hcurl_d4_trace <= _ROUND_OFF_LIMIT
        ),
        "all_h1_face_d4_actions_leave_cell_interior_unchanged": (
            h1_d4_actions == 48
            and h1_d4_error <= _ROUND_OFF_LIMIT
            and h1_d4_trace <= _ROUND_OFF_LIMIT
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "p7 cell-interior shadow exact-sequence audit failed: "
            + ", ".join(failures)
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035e.p7-interior-shadow-space.v1",
            "status": "p7_interior_shadow_component_pass",
            "pass": True,
            "hcurl_p6_dimension": int(hcurl.p6_element.dim),
            "hcurl_p7_dimension": int(hcurl.p7_element.dim),
            "hcurl_p6_trace_dimension": len(hcurl.p6_trace_dofs),
            "hcurl_p6_interior_dimension": len(
                hcurl.p6_interior_dofs
            ),
            "hcurl_p7_interior_dimension": len(
                hcurl.p7_interior_dofs
            ),
            "hcurl_extra_interior_dimension": (
                hcurl.complement.shape[1]
            ),
            "hcurl_shadow_dimension": hcurl.expansion.shape[1],
            "h1_p6_dimension": int(h1.p6_element.dim),
            "h1_p7_dimension": int(h1.p7_element.dim),
            "h1_extra_interior_dimension": h1.complement.shape[1],
            "h1_shadow_dimension": h1.expansion.shape[1],
            "hcurl_p6_injection_left_inverse_error_max": (
                hcurl.metrics["p7_to_p6_left_inverse_error_max"]
            ),
            "h1_p6_injection_left_inverse_error_max": (
                h1.metrics["p7_to_p6_left_inverse_error_max"]
            ),
            "hcurl_complement_p7_trace_support_max": (
                hcurl.metrics["complement_p7_trace_support_max"]
            ),
            "h1_complement_p7_trace_support_max": (
                h1.metrics["complement_p7_trace_support_max"]
            ),
            "hcurl_complement_gram_error_max": (
                hcurl.metrics["complement_coefficient_gram_error_max"]
            ),
            "h1_complement_gram_error_max": (
                h1.metrics["complement_coefficient_gram_error_max"]
            ),
            "hcurl_p6_interior_orthogonality_error_max": (
                hcurl.metrics[
                    "p6_interior_complement_orthogonality_error_max"
                ]
            ),
            "h1_p6_interior_orthogonality_error_max": (
                h1.metrics[
                    "p6_interior_complement_orthogonality_error_max"
                ]
            ),
            "hcurl_naive_prefix_error_max": (
                hcurl.metrics["naive_prefix_error_max"]
            ),
            "h1_naive_prefix_error_max": (
                h1.metrics["naive_prefix_error_max"]
            ),
            "prefix_assumption_used": False,
            "p6_gradient_commuting_error_max": p6_commuting_error,
            "shadow_gradient_range_error_max": gradient_range_error,
            "shadow_gradient_rank": gradient_rank,
            "shadow_gradient_rank_tolerance": gradient_rank_tolerance,
            "extra_h1_gradient_p7_trace_support_max": (
                extra_gradient_trace_error
            ),
            "hcurl_face_d4_action_count": hcurl_d4_actions,
            "hcurl_face_d4_invariance_error_max": hcurl_d4_error,
            "hcurl_face_d4_trace_support_max": hcurl_d4_trace,
            "h1_face_d4_action_count": h1_d4_actions,
            "h1_face_d4_invariance_error_max": h1_d4_error,
            "h1_face_d4_trace_support_max": h1_d4_trace,
            "orthogonality_metric": (
                "canonical_p7_cell_interpolation_coefficient_inner_product"
            ),
            "complement_span_is_metric_independent": True,
            "affine_physical_riesz_credit_claimed": False,
            "projection_convention": "E^H A E",
            "production_degrees_unchanged": (4, 5, 6),
            "shadow_only": True,
            "selectable_as_production": False,
            "next_production_plan": None,
            "coverage_credit": "interior_lower_bound_only",
            "can_satisfy_f1_alone": False,
            "p6_saturation_status": "not_measured",
            "p6_saturation_measured_pass": False,
            "p7_trace_shadow_covered": False,
            "h_shadow_covered": False,
            "ordinary_default_changed": False,
            "checks": MappingProxyType(checks),
        }
    )
    arrays = (
        hcurl.p6_to_p7,
        h1.p6_to_p7,
        hcurl.complement,
        h1.complement,
        hcurl.expansion,
        h1.expansion,
        shadow_gradient,
        hcurl_trace_active,
        hcurl_interior_active,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return P7InteriorShadowSpace(
        hcurl_p6_element=hcurl.p6_element,
        hcurl_p7_element=hcurl.p7_element,
        h1_p6_element=h1.p6_element,
        h1_p7_element=h1.p7_element,
        hcurl_p6_to_p7=readonly[0],
        h1_p6_to_p7=readonly[1],
        hcurl_interior_complement=readonly[2],
        h1_interior_complement=readonly[3],
        hcurl_expansion=readonly[4],
        h1_expansion=readonly[5],
        discrete_gradient=readonly[6],
        hcurl_trace_dofs=readonly[7],
        hcurl_interior_dofs=readonly[8],
        audit=audit,
        production_degrees_unchanged=frozenset({4, 5, 6}),
    )


@dataclass(frozen=True)
class P7InteriorShadowSchur:
    """Cell-local p7 shadow projection and exact interior elimination."""

    space: P7InteriorShadowSpace
    active_tensor: np.ndarray
    active_rhs: np.ndarray
    schur_tensor: np.ndarray
    schur_rhs: np.ndarray
    interior_from_trace: np.ndarray
    interior_load: np.ndarray
    audit: Mapping[str, Any]

    def recover_shadow_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        trace = np.asarray(trace_coefficients)
        if trace.shape != (len(self.space.hcurl_trace_dofs),):
            raise ValueError("p7 shadow trace coefficients have wrong shape")
        interior = self.interior_load - self.interior_from_trace @ trace
        active = np.zeros(
            self.space.hcurl_dimension,
            dtype=np.result_type(trace, self.active_rhs),
        )
        active[self.space.hcurl_trace_dofs] = trace
        active[self.space.hcurl_interior_dofs] = interior
        return np.ascontiguousarray(active)

    def recover_p7_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        return np.ascontiguousarray(
            self.space.hcurl_expansion
            @ self.recover_shadow_coefficients(trace_coefficients)
        )


def condense_p7_interior_shadow_tensor(
    p7_tensor: np.ndarray,
    p7_rhs: np.ndarray | None = None,
) -> P7InteriorShadowSchur:
    """Project one cell-local p7 tensor and eliminate all interior modes.

    The input is a single cell tensor.  The result never retains that p7
    tensor and never constructs or numbers a global p7 matrix.
    """

    space = build_p7_interior_shadow_space()
    tensor = np.asarray(p7_tensor)
    p7_dimension = int(space.hcurl_p7_element.dim)
    if tensor.shape != (p7_dimension, p7_dimension):
        raise ValueError("p7 local tensor has the wrong shape")
    if not np.all(np.isfinite(tensor)):
        raise ValueError("p7 local tensor contains non-finite entries")
    if p7_rhs is None:
        rhs = np.zeros(p7_dimension, dtype=tensor.dtype)
    else:
        rhs = np.asarray(p7_rhs)
        if rhs.shape != (p7_dimension,):
            raise ValueError("p7 local right-hand side has the wrong shape")
        if not np.all(np.isfinite(rhs)):
            raise ValueError(
                "p7 local right-hand side contains non-finite entries"
            )

    expansion = np.asarray(space.hcurl_expansion)
    active_tensor = np.ascontiguousarray(
        expansion.conj().T @ tensor @ expansion
    )
    active_rhs = np.ascontiguousarray(expansion.conj().T @ rhs)
    trace = np.asarray(space.hcurl_trace_dofs, dtype=np.int32)
    interior = np.asarray(space.hcurl_interior_dofs, dtype=np.int32)
    a_tt = np.asarray(active_tensor[np.ix_(trace, trace)])
    a_ti = np.asarray(active_tensor[np.ix_(trace, interior)])
    a_it = np.asarray(active_tensor[np.ix_(interior, trace)])
    a_ii = np.asarray(active_tensor[np.ix_(interior, interior)])
    b_t = np.asarray(active_rhs[trace])
    b_i = np.asarray(active_rhs[interior])
    try:
        interior_from_trace = np.linalg.solve(a_ii, a_it)
        interior_load = np.linalg.solve(a_ii, b_i)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "p7 shadow cell-interior block is singular"
        ) from exc
    schur_tensor = np.ascontiguousarray(
        a_tt - a_ti @ interior_from_trace
    )
    schur_rhs = np.ascontiguousarray(b_t - a_ti @ interior_load)
    itemsize = int(active_tensor.dtype.itemsize)
    audit = MappingProxyType(
        {
            "schema_version": "task035e.p7-interior-shadow-schur.v1",
            "status": "p7_interior_shadow_static_condensation_pass",
            "pass": True,
            "p7_cell_local_rows": p7_dimension,
            "active_local_rows": space.hcurl_dimension,
            "active_trace_rows": len(trace),
            "active_cell_interior_rows": len(interior),
            "p7_extra_cell_interior_rows": 306,
            "schur_rows": len(trace),
            "projection_convention": "E^H A E",
            "input_is_one_cell_local_tensor": True,
            "input_p7_tensor_retained": False,
            "global_p7_matrix_constructed": False,
            "global_p7_rows_numbered": False,
            "active_tensor_bytes": (
                space.hcurl_dimension**2 * itemsize
            ),
            "interior_block_bytes": len(interior) ** 2 * itemsize,
            "schur_tensor_bytes": len(trace) ** 2 * itemsize,
            "cell_local_p7_input_bytes": p7_dimension**2 * itemsize,
            "shadow_only": True,
            "selectable_as_production": False,
            "next_production_plan": None,
            "coverage_credit": "interior_lower_bound_only",
            "can_satisfy_f1_alone": False,
            "p6_saturation_status": "not_measured",
            "p6_saturation_measured_pass": False,
            "ordinary_default_changed": False,
        }
    )
    arrays = (
        active_tensor,
        active_rhs,
        schur_tensor,
        schur_rhs,
        interior_from_trace,
        interior_load,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return P7InteriorShadowSchur(
        space=space,
        active_tensor=readonly[0],
        active_rhs=readonly[1],
        schur_tensor=readonly[2],
        schur_rhs=readonly[3],
        interior_from_trace=readonly[4],
        interior_load=readonly[5],
        audit=audit,
    )


@dataclass(frozen=True)
class P7InteriorShadowDWR:
    """Dense cell-local residual/adjoint evidence for all 59 goals."""

    projected_residual: np.ndarray
    projected_goal_gradients: np.ndarray
    adjoints: np.ndarray
    correction: np.ndarray
    signed_contributions: np.ndarray
    direct_goal_deltas: np.ndarray
    audit: Mapping[str, Any]


def evaluate_p7_interior_shadow_dwr(
    p7_tensor: np.ndarray,
    p7_rhs: np.ndarray,
    current_p6_coefficients: np.ndarray,
    p7_goal_gradients: np.ndarray,
) -> P7InteriorShadowDWR:
    """Return the p7-interior residual and signed 59-goal DWR component."""

    space = build_p7_interior_shadow_space()
    tensor = np.asarray(p7_tensor)
    rhs = np.asarray(p7_rhs)
    current = np.asarray(current_p6_coefficients)
    gradients = np.asarray(p7_goal_gradients)
    p7_dimension = int(space.hcurl_p7_element.dim)
    if tensor.shape != (p7_dimension, p7_dimension):
        raise ValueError("p7 local tensor has the wrong shape")
    if rhs.shape != (p7_dimension,):
        raise ValueError("p7 local right-hand side has the wrong shape")
    if current.shape != (int(space.hcurl_p6_element.dim),):
        raise ValueError("current p6 local coefficients have the wrong shape")
    if gradients.shape != (_FORMAL_GOAL_COUNT, p7_dimension):
        raise ValueError(
            "p7 goal gradients must contain exactly 59 full local rows"
        )
    for name, values in (
        ("p7 local tensor", tensor),
        ("p7 local right-hand side", rhs),
        ("current p6 local coefficients", current),
        ("p7 goal gradients", gradients),
    ):
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} contains non-finite entries")

    complement = np.asarray(space.hcurl_interior_complement)
    current_p7 = np.asarray(space.hcurl_p6_to_p7) @ current
    full_residual = rhs - tensor @ current_p7
    projected_residual = np.ascontiguousarray(
        complement.conj().T @ full_residual
    )
    projected_goals = np.ascontiguousarray(
        gradients @ complement.conj()
    )
    complement_tensor = np.ascontiguousarray(
        complement.conj().T @ tensor @ complement
    )
    try:
        correction = np.linalg.solve(
            complement_tensor,
            projected_residual,
        )
        adjoints = np.linalg.solve(
            complement_tensor.conj().T,
            projected_goals.T,
        ).T
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "p7 interior shadow complement block is singular"
        ) from exc
    signed_contributions = np.ascontiguousarray(
        np.real(np.einsum("gi,i->g", adjoints.conj(), projected_residual))
    )
    direct_goal_deltas = np.ascontiguousarray(
        np.real(np.einsum("gi,i->g", projected_goals.conj(), correction))
    )
    dwr_closure_error = _maximum_absolute(
        signed_contributions - direct_goal_deltas
    )
    residual_solve_error = _maximum_absolute(
        complement_tensor @ correction - projected_residual
    )
    adjoint_solve_error = _maximum_absolute(
        complement_tensor.conj().T @ adjoints.T - projected_goals.T
    )
    scale = max(
        _maximum_absolute(signed_contributions),
        _maximum_absolute(direct_goal_deltas),
        1.0,
    )
    if (
        dwr_closure_error > 5.0e-10 * scale
        or residual_solve_error > 5.0e-10
        * max(_maximum_absolute(projected_residual), 1.0)
        or adjoint_solve_error > 5.0e-10
        * max(_maximum_absolute(projected_goals), 1.0)
    ):
        raise RuntimeError("p7 interior shadow residual/DWR closure failed")
    audit = MappingProxyType(
        {
            "schema_version": "task035e.p7-interior-shadow-dwr.v1",
            "status": "p7_interior_shadow_dwr_component_pass",
            "pass": True,
            "goal_count": _FORMAL_GOAL_COUNT,
            "p7_cell_local_rows": p7_dimension,
            "current_p6_local_rows": int(space.hcurl_p6_element.dim),
            "interior_shadow_rows": complement.shape[1],
            "projected_residual_norm": float(
                np.linalg.norm(projected_residual)
            ),
            "dwr_direct_closure_error_max": dwr_closure_error,
            "residual_solve_error_max": residual_solve_error,
            "adjoint_solve_error_max": adjoint_solve_error,
            "signed_contribution_convention": (
                "Re(conj(z_goal) dot projected_residual)"
            ),
            "current_p6_input_retained": False,
            "p7_goal_gradient_input_retained": False,
            "global_p7_matrix_constructed": False,
            "shadow_only": True,
            "selectable_as_production": False,
            "next_production_plan": None,
            "coverage_credit": "interior_lower_bound_only",
            "can_satisfy_f1_alone": False,
            "requires_trace_and_h_shadow_for_f1": True,
            "p6_saturation_status": "not_measured",
            "p6_saturation_measured_pass": False,
            "ordinary_default_changed": False,
        }
    )
    arrays = (
        projected_residual,
        projected_goals,
        adjoints,
        correction,
        signed_contributions,
        direct_goal_deltas,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return P7InteriorShadowDWR(
        projected_residual=readonly[0],
        projected_goal_gradients=readonly[1],
        adjoints=readonly[2],
        correction=readonly[3],
        signed_contributions=readonly[4],
        direct_goal_deltas=readonly[5],
        audit=audit,
    )


__all__ = [
    "P7InteriorShadowDWR",
    "P7InteriorShadowSchur",
    "P7InteriorShadowSpace",
    "build_p7_interior_shadow_space",
    "condense_p7_interior_shadow_tensor",
    "evaluate_p7_interior_shadow_dwr",
]
