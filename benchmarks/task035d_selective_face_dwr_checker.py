"""Independent fail-closed checker for Task035d selective-face DWR."""

from __future__ import annotations

import math
from typing import Any, Mapping


COARSE_CANDIDATE_ID = "h15_top_air_local_h_v1"
ENRICHED_CANDIDATE_ID = "h15_grating_top_selective_p6_faces_v1"
COARSE_FULL3D_EQUIVALENT_DOFS = 82_925
ENRICHED_FULL3D_EQUIVALENT_DOFS = 83_125
COARSE_SOLVE_ROWS = 18_470
ENRICHED_SOLVE_ROWS = 18_670
SELECTED_FACE_COUNT = 10


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def task035d_selective_face_dwr_report_gate(
    report: Mapping[str, Any] | None,
    *,
    expected_source_sha: str,
    expected_coarse_plan_sha256: str,
    expected_enriched_plan_sha256: str,
    expected_significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Recompute the formal cross-trace DWR verdict from raw report fields."""

    report = report if isinstance(report, Mapping) else {}
    coarse = report.get("coarse_snapshot")
    coarse = coarse if isinstance(coarse, Mapping) else {}
    coarse_candidate = coarse.get("candidate")
    coarse_candidate = (
        coarse_candidate
        if isinstance(coarse_candidate, Mapping)
        else {}
    )
    enriched = report.get("enriched_candidate")
    enriched = enriched if isinstance(enriched, Mapping) else {}
    identity = report.get("identity_checks")
    identity = identity if isinstance(identity, Mapping) else {}
    transfer = report.get("root_transfer")
    transfer = transfer if isinstance(transfer, Mapping) else {}
    transfer_checks = transfer.get("checks")
    transfer_checks = (
        transfer_checks if isinstance(transfer_checks, Mapping) else {}
    )
    galerkin = report.get("galerkin_audit")
    galerkin = galerkin if isinstance(galerkin, Mapping) else {}
    galerkin_checks = galerkin.get("checks")
    galerkin_checks = (
        galerkin_checks
        if isinstance(galerkin_checks, Mapping)
        else {}
    )
    probes = galerkin.get("operator_probes")
    probes = probes if isinstance(probes, list) else []
    primal = report.get("primal_endpoints")
    primal = primal if isinstance(primal, Mapping) else {}
    basis = report.get("unit_channel_adjoint_basis")
    basis = basis if isinstance(basis, Mapping) else {}
    goals = report.get("goal_dwr")
    goals = goals if isinstance(goals, Mapping) else {}
    goal_rows = goals.get("goals")
    goal_rows = goal_rows if isinstance(goal_rows, Mapping) else {}
    marking = report.get("selected_face_multigoal_marking")
    marking = marking if isinstance(marking, Mapping) else {}
    ranked = marking.get("ranked_faces")
    ranked = ranked if isinstance(ranked, list) else []
    authority = report.get("significant_channel_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    boundary = report.get("formal_boundary")
    boundary = boundary if isinstance(boundary, Mapping) else {}

    endpoint_rows = list(goal_rows.values())
    face_keys = {
        tuple(map(int, row.get("geometry_key", ())))
        for row in ranked
        if isinstance(row, Mapping)
    }
    checks = {
        "report_schema_and_status": (
            report.get("schema_version")
            == "task035d.selective-face-cross-trace-dwr.v1"
            and report.get("status")
            == "selective_face_cross_trace_live_dwr_pass"
            and report.get("pass") is True
            and report.get("controlled_negative") is not True
        ),
        "source_sha_is_frozen_and_shared": (
            _valid_hex(expected_source_sha, 40)
            and coarse_candidate.get("source_sha")
            == expected_source_sha
            and enriched.get("source_sha") == expected_source_sha
        ),
        "endpoint_candidates_are_exact": (
            coarse_candidate.get("candidate_id")
            == COARSE_CANDIDATE_ID
            and enriched.get("candidate_id") == ENRICHED_CANDIDATE_ID
            and coarse_candidate.get("plan_file_sha256")
            == expected_coarse_plan_sha256
            and enriched.get("plan_file_sha256")
            == expected_enriched_plan_sha256
            and coarse_candidate.get(
                "actual_full3d_equivalent_active_fe_dofs"
            )
            == COARSE_FULL3D_EQUIVALENT_DOFS
            and enriched.get(
                "actual_full3d_equivalent_active_fe_dofs"
            )
            == ENRICHED_FULL3D_EQUIVALENT_DOFS
            and coarse_candidate.get("cell_interior_degree_sha256")
            == enriched.get("cell_interior_degree_sha256")
        ),
        "significant_channel_authority": (
            _valid_hex(
                expected_significant_channel_authority_sha256,
                64,
            )
            and authority.get("sha256")
            == expected_significant_channel_authority_sha256
            and authority.get("physical_channel_count") == 12
            and authority.get("real_goal_count") == 36
        ),
        "all_endpoint_identities": (
            bool(identity)
            and all(value is True for value in identity.values())
        ),
        "actual_cross_trace_transfer": (
            report.get("same_trace_only") is False
            and report.get(
                "actual_cross_trace_primal_prolongation_used"
            )
            is True
            and transfer.get("pass") is True
            and transfer.get("selected_p6_face_count")
            == SELECTED_FACE_COUNT
            and transfer.get("trace_dimension_delta") == 200
            and transfer.get("coarse_independent_trace_rows")
            == COARSE_SOLVE_ROWS - 80
            and transfer.get("enriched_independent_trace_rows")
            == ENRICHED_SOLVE_ROWS - 80
            and _valid_hex(
                transfer.get("trace_injection_sha256"),
                64,
            )
            and _valid_hex(
                transfer.get("trace_complement_projector_sha256"),
                64,
            )
            and transfer.get("complement_basis_is_identity_authority")
            is False
            and bool(transfer_checks)
            and all(
                value is True for value in transfer_checks.values()
            )
        ),
        "galerkin_and_complement_gate": (
            galerkin.get("pass") is True
            and bool(galerkin_checks)
            and all(
                value is True for value in galerkin_checks.values()
            )
            and len(probes) == 3
            and all(
                isinstance(row, Mapping) and row.get("pass") is True
                for row in probes
            )
            and galerkin.get("full_matrix_equality_claimed") is False
            and galerkin.get("actual_endpoint_dwr_closure_is_mandatory")
            is True
        ),
        "both_primal_residual_gates": (
            isinstance(primal.get("coarse_residual_gate"), Mapping)
            and primal["coarse_residual_gate"].get("pass") is True
            and isinstance(primal.get("enriched_residual_gate"), Mapping)
            and primal["enriched_residual_gate"].get("pass") is True
        ),
        "twelve_actual_unit_adjoints": (
            basis.get("pass") is True
            and basis.get("unit_adjoint_solve_count") == 12
            and isinstance(basis.get("channels"), Mapping)
            and len(basis["channels"]) == 12
            and all(
                isinstance(row, Mapping) and row.get("pass") is True
                for row in basis["channels"].values()
            )
        ),
        "all_36_goal_closures": (
            goals.get("pass") is True
            and goals.get("requested_real_goal_count") == 36
            and goals.get("passed_real_goal_count") == 36
            and goals.get("power_goal_count") == 12
            and goals.get("power_goal_pass_count") == 12
            and goals.get("complex_amplitude_component_goal_count") == 24
            and goals.get(
                "complex_amplitude_component_goal_pass_count"
            )
            == 24
            and len(endpoint_rows) == 36
            and all(
                isinstance(row, Mapping)
                and row.get("pass") is True
                and row.get(
                    "endpoint_closure_does_not_use_partition_error"
                )
                is True
                and row.get("selected_face_pairing_closure_pass") is True
                and isinstance(
                    row.get("signed_goal_closure_error"),
                    (int, float),
                )
                and math.isfinite(
                    float(row["signed_goal_closure_error"])
                )
                and abs(float(row["signed_goal_closure_error"]))
                <= float(row.get("goal_closure_limit", -1.0))
                and len(row.get("face_contributions") or ())
                == SELECTED_FACE_COUNT
                for row in endpoint_rows
            )
        ),
        "ten_face_multigoal_partition": (
            marking.get("face_count") == SELECTED_FACE_COUNT
            and len(ranked) == SELECTED_FACE_COUNT
            and len(face_keys) == SELECTED_FACE_COUNT
            and marking.get(
                "signed_contributions_used_for_goal_closure"
            )
            is True
            and marking.get(
                "absolute_contributions_used_for_marking_only"
            )
            is True
        ),
        "formal_boundary_preserved": (
            boundary.get(
                "this_report_qualifies_the_actual_selected_face_action"
            )
            is True
            and boundary.get("this_report_does_not_select_unrun_faces")
            is True
            and boundary.get("full_case095_physics_gate_still_independent")
            is True
            and boundary.get("hybrid_credit_locked_until_full_full3d_gate")
            is True
        ),
        "ordinary_default_unchanged": (
            report.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "task035d.selective-face-cross-trace-dwr-checker.v1"
        ),
        "status": (
            "selective_face_cross_trace_dwr_checker_pass"
            if not failures
            else "selective_face_cross_trace_dwr_checker_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "goal_oriented_selection_credit": not failures,
        "full_case095_physics_gate_still_independent": True,
        "ordinary_default_changed": False,
    }


__all__ = ["task035d_selective_face_dwr_report_gate"]
