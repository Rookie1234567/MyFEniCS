from __future__ import annotations

from typing import Any, Mapping


def build_low_cost_bakeoff_entry(
    real_fe_record: Mapping[str, Any],
    mpi_identity: Mapping[str, Any],
) -> dict[str, Any]:
    if real_fe_record.get("status") != "real_fe_fixture_minimum_pass":
        raise ValueError("Phase C-low-cost requires the B1+B2 real FE minimum Gate.")
    if mpi_identity.get("status") != "serial_mpi2_identity_pass":
        raise ValueError("Phase C-low-cost requires serial/MPI2 identity.")
    b1_points = real_fe_record["b1"]["points"]
    b2_points = real_fe_record["b2"]["points"]
    r1_values = [float(point["r1_indicator"]) for point in b2_points]
    field_errors = [float(point["relative_l2_field_error"]) for point in b2_points]
    dtn_values = [
        float(point["external_dtn_boundary_squared"]) ** 0.5
        for point in b2_points
    ]
    r00_errors = [float(point["official_fixture_r00_error"]) for point in b2_points]
    return {
        "schema_version": "task035.phase-c-low-cost-entry.v1",
        "status": "phase_c_low_cost_in_progress",
        "phase_b_real_fixture_minimum_gate": "pass",
        "phase_c_low_cost_unlocked": True,
        "phase_c_formal_completion": "pending_B3_B4",
        "production_estimator_selected": False,
        "heavy_p4_authorized": False,
        "candidate_readiness": {
            "R1_standard_residual": "bakeoff_active_real_FE",
            "R2_kh_over_p": "diagnostic_only_excluded_from_marking",
            "R5_hierarchical_two_level": "pending_real_enriched_fixture",
            "G1_dwr_total_rta": "pending_actual_discrete_residual_and_adjoint",
            "G2_dwr_r00": "real_goal_derivative_pass_adjoint_pending",
            "B1_dtn_split": "bakeoff_active_real_FE_boundary_component",
            "R3_recovery_hcurl": "post_C1_independent_validation",
            "R4_equilibrated_patch": "research_lane_formula_defined",
        },
        "initial_measured_screen": {
            "scope": "B1/B2 real FE fixtures; not the target p2/h5-p2/h3-p3 screen",
            "R1": {
                "indicators": r1_values,
                "field_errors": field_errors,
                "indicator_decreases": all(
                    right < left for left, right in zip(r1_values, r1_values[1:])
                ),
                "field_error_decreases": all(
                    right < left
                    for left, right in zip(field_errors, field_errors[1:])
                ),
                "fine_to_coarse_indicator_ratio": r1_values[-1] / r1_values[0],
                "fine_to_coarse_field_error_ratio": field_errors[-1]
                / field_errors[0],
            },
            "G2": {
                "r00_errors": r00_errors,
                "decision": "controlled_not_rankable_on_machine_precision_fixture_goal",
                "next_gate": "actual_discrete_adjoint_on_nontrivial_low_cost_goal",
            },
            "B1": {
                "external_dtn_norms": dtn_values,
                "component_decreases": all(
                    right < left for left, right in zip(dtn_values, dtn_values[1:])
                ),
                "fault_detection": all(
                    float(point["dtn_operator_perturbation_norm"]) > 1.0e-3
                    for point in b2_points
                ),
            },
            "periodic_R1": {
                "p1": float(b1_points[0]["r1_indicator"]),
                "p2": float(b1_points[1]["r1_indicator"]),
            },
        },
        "next_low_cost_gate": {
            "required_points": ["p2_h5", "p2_h3", "p3_coarse"],
            "required_metrics": [
                "effectivity",
                "local_error_correlation",
                "top_marked_overlap",
                "observable_error_reduction_after_refinement",
                "assembly_time_and_memory",
                "mpi_partition_stability",
            ],
            "B3": "pending_parallel",
            "B4": "pending_parallel",
        },
    }
