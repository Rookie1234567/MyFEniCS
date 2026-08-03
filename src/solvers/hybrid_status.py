"""Small status contract for non-production Hybrid-P results."""

from __future__ import annotations


def hybrid_p_disposition(
    polarization_kind: str,
    *,
    full3d_physical_solution_exists: bool,
    modal_rank_sufficient: bool | None,
    interface_closure_pass: bool,
    diagnostic_projection_bug: bool,
) -> dict[str, object]:
    """Classify Hybrid-P evidence without upgrading it to production."""

    if str(polarization_kind).lower() != "p":
        return {
            "applicable": False,
            "primary_status": "not_applicable_s_polarization",
            "hybrid_p_production_qualified": False,
            "full3d_fallback_is_hybrid_success": False,
        }

    rank_insufficient = modal_rank_sufficient is False
    rank_pending = modal_rank_sufficient is None
    interface_failed = not bool(interface_closure_pass)
    if diagnostic_projection_bug:
        primary_status = "diagnostic_projection_bug"
    elif rank_insufficient:
        primary_status = "hybrid_modal_rank_insufficient"
    elif interface_failed:
        primary_status = "hybrid_interface_closure_failed"
    elif rank_pending:
        primary_status = "hybrid_modal_rank_pending_actual_M_convergence"
    else:
        primary_status = "hybrid_p_research_observables_pass_production_quarantined"

    return {
        "applicable": True,
        "primary_status": primary_status,
        "full3d_physical_solution_exists": bool(full3d_physical_solution_exists),
        "hybrid_modal_rank_insufficient": rank_insufficient,
        "hybrid_modal_rank_pending_actual_M_convergence": rank_pending,
        "hybrid_interface_closure_failed": interface_failed,
        "diagnostic_projection_bug": bool(diagnostic_projection_bug),
        "hybrid_p_production_qualified": False,
        "full3d_fallback_is_hybrid_success": False,
    }


__all__ = ["hybrid_p_disposition"]
