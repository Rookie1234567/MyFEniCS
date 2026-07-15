"""Explicit polynomial quadrature policy for Task033 high-order paths."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HighOrderQuadraturePolicy:
    """Recorded inputs and selected/elevated quadrature degrees."""

    field_degree: int
    geometry_degree: int
    coefficient_degree: int
    selected_degree: int
    raised_comparison_degree: int
    policy: str = "2p_plus_2g_plus_c_plus_2"


def high_order_quadrature_policy(
    *,
    field_degree: int,
    geometry_degree: int,
    coefficient_degree: int,
) -> HighOrderQuadraturePolicy:
    """Build the conservative policy used by planar Task033 fixtures.

    The rule preserves quadrature degree eight for the reviewed p=2,
    linear-geometry, piecewise-constant-material path.  A comparison two
    degrees higher is part of qualification.  Curved production geometry is
    outside Task033 and requires a separate mapping-aware study.
    """

    if field_degree < 1:
        raise ValueError("field_degree must be at least one.")
    if geometry_degree < 1:
        raise ValueError("geometry_degree must be at least one.")
    if coefficient_degree < 0:
        raise ValueError("coefficient_degree must be non-negative.")
    selected = int(
        2 * field_degree
        + 2 * geometry_degree
        + coefficient_degree
        + 2
    )
    return HighOrderQuadraturePolicy(
        field_degree=int(field_degree),
        geometry_degree=int(geometry_degree),
        coefficient_degree=int(coefficient_degree),
        selected_degree=selected,
        raised_comparison_degree=selected + 2,
    )
