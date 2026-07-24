"""Structural audit for inverse H(curl) trace/interior budget exchange.

Task035b's qualified reduced-trace construction keeps a lower shared trace
while enriching cell-interior modes.  Reversing that exchange--keeping a p6
trace while lowering cell interiors--is tempting as a way to spend matrix
rows on trace accuracy without exceeding a Full3D-equivalent DoF budget.

This module checks the local polynomial de Rham prerequisite of that idea
using the *same* mixed trace/interior Basix construction as the qualified
regionwise-p path.  A failed local exact-sequence audit is sufficient to stop
the proposed space before mesh construction, form compilation, or a PDE run.
"""

from __future__ import annotations

from typing import Any

from .hcurl_regionwise_p import (
    _create_trace_interior_element,
    _standard_hexa_hcurl,
    audit_tensor_product_exact_sequence,
)


def audit_trace_interior_pair(
    trace_degree: int,
    cell_interior_degree: int,
) -> dict[str, Any]:
    """Audit one mixed trace/interior space made by the current construction."""

    trace_degree = int(trace_degree)
    cell_interior_degree = int(cell_interior_degree)
    if not 1 <= trace_degree <= 6:
        raise ValueError("trace_degree must lie in [1, 6]")
    if not 1 <= cell_interior_degree <= 6:
        raise ValueError("cell_interior_degree must lie in [1, 6]")

    element, construction = _create_trace_interior_element(
        trace_degree,
        cell_interior_degree,
    )
    exact_sequence = audit_tensor_product_exact_sequence(
        element,
        trace_degree=trace_degree,
        interior_degree=cell_interior_degree,
    )
    trace_dofs = sum(
        len(entity)
        for dimension in element.entity_dofs[:3]
        for entity in dimension
    )
    interior_dofs = len(element.entity_dofs[3][0])
    if trace_dofs + interior_dofs != int(element.dim):
        raise RuntimeError("mixed trace/interior entity dimensions do not close")

    standard_trace = _standard_hexa_hcurl(trace_degree)
    standard_interior = _standard_hexa_hcurl(cell_interior_degree)
    full_trace_degree_interior_dofs = len(
        standard_trace.entity_dofs[3][0]
    )
    return {
        "schema_version": "task035b.trace-interior-pair-audit.v1",
        "status": "trace_interior_pair_structurally_audited",
        "audit_completed": True,
        "pass": bool(exact_sequence["pass"]),
        "cell_type": "hexahedron",
        "trace_degree": trace_degree,
        "cell_interior_degree": cell_interior_degree,
        "inverse_budget_exchange": (
            trace_degree > cell_interior_degree
        ),
        "mixed_vector_space_dimension": int(element.dim),
        "trace_dimension": int(trace_dofs),
        "cell_interior_dimension": int(interior_dofs),
        "standard_trace_degree_space_dimension": int(
            standard_trace.dim
        ),
        "standard_cell_interior_degree_space_dimension": int(
            standard_interior.dim
        ),
        "full_trace_degree_cell_interior_dimension": int(
            full_trace_degree_interior_dofs
        ),
        "cell_interior_modes_removed_from_full_trace_degree_space": int(
            full_trace_degree_interior_dofs - interior_dofs
        ),
        "construction": {
            "method": (
                "current Task035b mixed trace/interior Basix construction"
            ),
            "custom_element": bool(construction["custom"]),
            "polynomial_subspace_rank": int(
                construction["polynomial_subspace_rank"]
            ),
            "coefficient_matrix_condition_number": float(
                construction["coefficient_matrix_condition_number"]
            ),
            "shared_entity_policy": (
                "edge and face moments come from trace_degree; cell moments "
                "come from cell_interior_degree"
            ),
        },
        "exact_sequence": exact_sequence,
        "exact_sequence_pass": bool(exact_sequence["pass"]),
        "pde_authorized": bool(exact_sequence["pass"]),
    }


def audit_inverse_trace_interior_budget_exchange() -> dict[str, Any]:
    """Classify p6-trace/p5-or-p4-interior exchanges and valid controls."""

    inverse_pairs = {
        "p6_trace_p5_cell_interior": audit_trace_interior_pair(6, 5),
        "p6_trace_p4_cell_interior": audit_trace_interior_pair(6, 4),
    }
    qualified_controls = {
        "p5_trace_p5_cell_interior": audit_trace_interior_pair(5, 5),
        "p5_trace_p6_cell_interior": audit_trace_interior_pair(5, 6),
    }

    inverse_failures = {
        name: not bool(pair["exact_sequence_pass"])
        and int(
            pair["exact_sequence"]["missing_gradient_mode_count"]
        )
        > 0
        for name, pair in inverse_pairs.items()
    }
    control_passes = {
        name: bool(pair["exact_sequence_pass"])
        and int(
            pair["exact_sequence"]["missing_gradient_mode_count"]
        )
        == 0
        for name, pair in qualified_controls.items()
    }
    audit_pass = all(inverse_failures.values()) and all(
        control_passes.values()
    )
    if not audit_pass:
        raise RuntimeError(
            "inverse budget-exchange audit did not reproduce the expected "
            "invalid-inverse / valid-control split"
        )

    classified_inverse_pairs = {
        name: {
            **pair,
            "classification": (
                "controlled_negative_non_exact_sequence_space"
            ),
            "candidate_authorized": False,
            "pde_authorized": False,
            "not_run_reason": (
                "local tensor exact-sequence prerequisite fails before "
                "mesh, matrix, or PDE construction"
            ),
        }
        for name, pair in inverse_pairs.items()
    }
    return {
        "schema_version": (
            "task035b.inverse-trace-interior-budget-exchange-audit.v1"
        ),
        "status": (
            "inverse_budget_exchange_controlled_negative_preflight"
        ),
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "controlled_negative": True,
        "ordinary_default_changed": False,
        "geometry_scope": (
            "geometry-independent local hexahedral polynomial prerequisite"
        ),
        "inverse_budget_exchange_pairs": classified_inverse_pairs,
        "qualified_p5_trace_controls": qualified_controls,
        "candidate_count": 0,
        "candidate_authorized": False,
        "pde_run_count": 0,
        "pde_authorized": False,
        "mesh_built": False,
        "form_compiled": False,
        "matrix_assembled": False,
        "solver_started": False,
        "decision": (
            "do not exchange global p6 trace modes for p5 or p4 cell "
            "interiors with the current mixed construction; both inverse "
            "spaces omit required gradient modes"
        ),
        "control_interpretation": (
            "standard p5 trace/interior and qualified p5-trace/p6-interior "
            "both close the same local exact-sequence prerequisite"
        ),
        "thresholds_relaxed": False,
    }


__all__ = [
    "audit_inverse_trace_interior_budget_exchange",
    "audit_trace_interior_pair",
]
