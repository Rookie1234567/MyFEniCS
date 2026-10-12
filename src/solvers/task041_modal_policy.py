"""Standard-library-only Task041 modal policy metadata and resolver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TASK041_V12_MODAL_SOLVER_POLICY_ID = "task041_v12_bounded_inexact_modal"
TASK041_V12_MODAL_BACKUP_POLICY_ID = (
    "task041_v12_bounded_inexact_modal_once_backup"
)
TASK041_V12_MODAL_BACKUP_QUALIFICATION_METHOD = (
    "task041_v12_h6_primary_once_physical_backup_with_original_outer_fgmres"
)
TASK041_V13_CONSISTENT_MODAL_POLICY_ID = (
    "task041_v13_consistent_fixed_balh_modal_surrogate"
)

_TASK041_V12_MODAL_SOLVER_POLICY = {
    "policy_id": TASK041_V12_MODAL_SOLVER_POLICY_ID,
    "target_rtol": 1.0e-3,
    "max_it": 32,
    "restart": 32,
    "solver_matmult_limit": 34,
    "total_matmult_limit_including_final": 35,
    "approximate_return_eta_max": 0.1,
    "accepted_normal_return_conditions": (
        "runtime_DIVERGED_ITS_at_max_it_or_positive_reason_with_raw_target_miss"
    ),
    "raw_reason_and_residual_preserved": True,
}
_TASK041_V12_MODAL_BACKUP_POLICY = {
    **_TASK041_V12_MODAL_SOLVER_POLICY,
    "policy_id": TASK041_V12_MODAL_BACKUP_POLICY_ID,
    "primary_method": "fixed_h6_modal_gmres_research",
    "backup_method": "fixed_physical_balh_once_modal_gmres_research",
    "maximum_backup_switches": 1,
    "backup_triggers": [
        "normal_trusted_primary_return_eta_above_0.1",
        "two_consecutive_eight_step_outer_true_residual_windows_each_improve_less_than_10_percent",
    ],
    "backup_safety_boundary": (
        "after_completed_modal_KSP_before_next_modal_KSP_entry"
    ),
    "outer_stagnation_window_steps": 8,
    "outer_stagnation_window_improvement_max": 0.10,
    "outer_stagnation_residual_gate_threshold": 5.0e-9,
    "outer_stagnation_metrics": [
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    ],
    "backup_borrows_existing_side_factors": True,
    "backup_requires_same_fixed_physical_linearity_gate": True,
    "side_restart64_trial": {
        "enabled_by_default": False,
        "status": "registered_once_trial_requires_live_fresh_authority_callback",
        "requires_measured_restart32_stagnation_and_outer_stagnation": True,
        "restart32_stagnation_windows": 2,
        "restart32_window_steps": 32,
        "restart32_window_improvement_max": 0.10,
        "max_it": 128,
        "restart": 64,
        "orthogonalization": "modified_gram_schmidt",
        "maximum_trials": 1,
        "requires_fresh_memory_gate": True,
        "selection_rule": (
            "same_rhs_eta64_at_most_0.9_eta32_and_max_rank_trial_wall_with_one_setup_not_higher"
            "_and_log_residual_reduction_per_wall_not_lower"
        ),
        "restart64_source_workspace": {
            "restart32_ksp_destroyed_before_restart64_gate": True,
            "petsc_vec_offset": 2,
            "gmres_owned_vectors": "offset+2+restart",
            "fgmres_preconditioned_vectors": "gmres_owned_vectors-offset",
            "basis_vec_layout": "operator-local-rows",
            "preconditioned_vec_layout": "operator-local-columns",
            "auxiliary_vec_layout": "per-rank max(operator-local-rows,operator-local-columns)",
            "trial_solution_vectors": 1,
            "simultaneous_true_residual_vectors": {
                "operator_output_row_layout": 1,
                "original_rhs_copy_column_layout": 1,
            },
            "captured_rhs_in_fresh_B": True,
            "additional_scalar_arrays": "Hessenberg/Givens plus conservative SVD arrays and nrs",
            "complex_scalar_bytes": 16,
        },
        "restart32_restore_workspace": {
            "fresh_gate_after_restart64_trial_and_candidate_rhs_are_destroyed": True,
            "restart": 32,
            "basis_vec_layout": "operator-local-rows",
            "preconditioned_vec_layout": "operator-local-columns",
            "auxiliary_vec_layout": "per-rank max(operator-local-rows,operator-local-columns)",
            "future_apply_output_vectors": 1,
            "simultaneous_true_residual_vectors": {
                "operator_output_row_layout": 1,
                "original_rhs_copy_column_layout": 1,
            },
            "captured_rhs_in_fresh_B": False,
            "additional_scalar_arrays": "Hessenberg/Givens plus conservative SVD arrays and nrs",
            "complex_scalar_bytes": 16,
        },
    },
    "post_backup_stop": {
        "enabled": True,
        "requires_one_backup_used": True,
        "requires_side_trial_resolved": True,
        "finite_stagnation_stop_requires_two_complete_post_trial_eight_step_windows": True,
        "restore_workspace_capacity_refusal_is_an_immediate_safe_boundary_stop": True,
        "maximum_unpassed_global_and_block_improvement": 0.10,
        "reason_class": "runtime_supported_non_success_with_separate_policy_stop_reason",
    },
}
_TASK041_V13_CONSISTENT_MODAL_POLICY = {
    "policy_id": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
    "method": "task041_v13_consistent_fixed_balh_modal_surrogate",
    "side_method": "fixed_physical_balh_once",
    "same_side_actions_for_all_ldu_terms_and_modal_schur": True,
    "modal_linear_solver": "owner_local_scipy_lu",
    "sample_columns_required": 8,
    "owner_modal_storage_limit_bytes": 268_435_456,
    "modal_schur_residual_tolerance": 1.0e-10,
    "original_modal_row_residual_tolerance": 1.0e-10,
    "outer_threshold": 5.0e-9,
    "outer_restart_initial": 32,
    "outer_restart_trial": 64,
    "outer_restart_trial_count": 1,
    "outer_restart_trial_requires_completed_window": 48,
    "outer_restart_loss_post_window_steps": 16,
    "outer_restart_loss_minimum_progress_fraction": 0.10,
    "outer_restart_loss_evidence_rule": (
        "compare_equal_16_step_complete_true_residual_windows_16_to_32_and_32_to_48_using_original_rhs_global_norm_and_each_rows_existing_block_component_max_denominator; "
        "require_at_least_10_percent_global_best_improvement_in_16_to_32; "
        "at_iteration_48_require_global_and_each_still_unpassed_block_to_improve_less_than_10_percent_in_32_to_48; "
        "this_is_a_predeclared_progress_loss_heuristic_not_a_convergence_theorem"
    ),
    "outer_finite_stop_window_steps": 16,
    "outer_finite_stop_consecutive_windows": 2,
    "outer_finite_stop_maximum_best_residual_improvement": 0.10,
    "legacy_default_builder_unchanged": True,
}


def resolve_task041_modal_solver_policy(
    value: str | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve one sealed Task041 modal policy without changing legacy defaults."""

    if value is None:
        return None
    policies = {
        TASK041_V12_MODAL_SOLVER_POLICY_ID: _TASK041_V12_MODAL_SOLVER_POLICY,
        TASK041_V12_MODAL_BACKUP_POLICY_ID: _TASK041_V12_MODAL_BACKUP_POLICY,
        TASK041_V13_CONSISTENT_MODAL_POLICY_ID: (
            _TASK041_V13_CONSISTENT_MODAL_POLICY
        ),
    }
    if isinstance(value, str):
        policy = policies.get(value)
        if policy is None:
            raise ValueError("unsupported Task041 modal solver policy")
        return dict(policy)
    if not isinstance(value, Mapping):
        raise TypeError(
            "Task041 modal solver policy must be a registered id or mapping"
        )
    policy_id = value.get("policy_id")
    policy = policies.get(policy_id) if isinstance(policy_id, str) else None
    if policy is None or dict(value) != policy:
        raise ValueError("Task041 modal solver policy does not match its registered contract")
    return dict(policy)


__all__ = (
    "TASK041_V12_MODAL_BACKUP_POLICY_ID",
    "TASK041_V12_MODAL_BACKUP_QUALIFICATION_METHOD",
    "TASK041_V12_MODAL_SOLVER_POLICY_ID",
    "TASK041_V13_CONSISTENT_MODAL_POLICY_ID",
    "_TASK041_V12_MODAL_BACKUP_POLICY",
    "_TASK041_V12_MODAL_SOLVER_POLICY",
    "_TASK041_V13_CONSISTENT_MODAL_POLICY",
    "resolve_task041_modal_solver_policy",
)
