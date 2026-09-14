"""Frozen, explicit input identity for the development physical middle solver."""

PROFILE = "physical_intermediate_p4_shifted_aux_v1"
REFERENCE_PROFILE = "physical_intermediate_p4_reference_v1"
FAST_PROFILE = "a2r_equivalent_fast_v1"
LIGHT_PROFILE = "p6smooth_p4ref_p6smooth_v1"
PACKED_PROFILE = "a2r_packed_equivalent_v2"
JOINT_PROFILE = "light_p4ref_jointmr3_v2"
from .physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
from .physical_recursive_profile import (
    MACRO_V12_PROFILES,
    P4_DIRECTION_DIAGNOSIS_PROFILES,
    MACRO_V11_PROFILES,
    MACRO_V10_PROFILES,
    macro_v12_profile_facts,
    p4_direction_diagnosis_profile_facts,
    RECURSIVE_PROFILES,
    macro_v11_profile_facts,
    macro_v10_profile_facts,
)

SCHUR_PROFILE = "physical_p4_schur_v14"
P4_BLR_PROFILE = "physical_p4_blr_bal_h_v16"
P4_BLR_TRADEOFF_PROFILE = "physical_p4_blr_tradeoff_v17"
CELL_CONDENSED_EXACT_PROFILE = "physical_p4_cell_condensed_exact_v18"
CELL_CONDENSED_BLR_PROFILE = "physical_p4_cell_condensed_blr_v18"
P4_BLR_TRADEOFF_THRESHOLDS = {
    "T1_BLR_CONTROL": 1.0e-3,
    "T2_BLR_CONTROL": 1.0e-4,
}

PROFILES = (PROFILE, REFERENCE_PROFILE, FAST_PROFILE, LIGHT_PROFILE, PACKED_PROFILE, JOINT_PROFILE, SCHUR_PROFILE, P4_BLR_PROFILE, P4_BLR_TRADEOFF_PROFILE, CELL_CONDENSED_EXACT_PROFILE, CELL_CONDENSED_BLR_PROFILE) + BALANCED_PROFILES + RECURSIVE_PROFILES + BOUNDED_PROFILES + MACRO_V10_PROFILES + MACRO_V11_PROFILES + MACRO_V12_PROFILES + P4_DIRECTION_DIAGNOSIS_PROFILES


def p4_blr_tradeoff_threshold(stage: str) -> float:
    """Return the one frozen V17 threshold represented by ``stage``."""

    try:
        return float(P4_BLR_TRADEOFF_THRESHOLDS[str(stage)])
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "physical_p4_blr_tradeoff_v17 requires T1_BLR_CONTROL or T2_BLR_CONTROL"
        ) from exc


def profile_facts(identity=PROFILE) -> dict:
    if identity in {CELL_CONDENSED_EXACT_PROFILE, CELL_CONDENSED_BLR_PROFILE}:
        stages = {
            "U0_PREFLIGHT": {"workflow_seconds": 600, "solve_seconds": 600},
            "U1_CONTROL_BRIDGE": {"workflow_seconds": 1800, "solve_seconds": 1800},
            "U2_EXACT_CONTROL": {"workflow_seconds": 43200, "solve_seconds": 43200},
            "U3_BLR_CONTROL": {"workflow_seconds": 43200, "solve_seconds": 43200},
            "U4_ORIGINAL": {"workflow_seconds": 43200, "solve_seconds": 43200},
            "U4_EXACT_FALLBACK": {"workflow_seconds": 43200, "solve_seconds": 43200},
            "U5_NOTCH": {"workflow_seconds": 43200, "solve_seconds": 43200},
            "U6_FINALIZE": {"workflow_seconds": 43200, "solve_seconds": 43200},
        }
        backend = (
            "blr" if identity == CELL_CONDENSED_BLR_PROFILE else "exact"
        )
        return {
            "identity": identity,
            "scope": "review_v18_p4_cell_condensed",
            "backend": backend,
            "physical_levels": [6, 4],
            "common_core": {
                "active_matrix": "assembly-time p4 independent trace plus 80 carrier rows",
                "interface_matrix": "[S_V Bhat; -Dhat Hhat] from complete cell-local elimination",
                "cell_operator": "complete curl-plus-complex-material volume tensor before Schur",
                "interior_factor": "one LAPACK complex128 LU per verified cell class",
                "global_factor": "one condensed sparse MUMPS factor retained through postprocess",
                "mpi_size": 1,
                "ordinary_default_changed": False,
                "old_macro_objects": False,
                "old_full_p4_matrix": False,
            },
            "assembly": {
                "dense_appended_block": True,
                "sum_duplicate_cell_integrals": True,
                "strict_local_checks": True,
                "quadrature_changed": False,
                "trace_order_changed": False,
                "cache_key_dependencies": [
                    "material_tag", "cell_widths", "jacobian", "orientation",
                    "degree_and_basis_hash", "ufcx_integral_ids", "kernel_counts",
                ],
            },
            "outer": {
                "ksp_type": "right_fgmres",
                "restart": 32,
                "max_iterations": 2048,
                "zero_start": True,
                "live_KSP": True,
                "explicit_true_residual_limit": 1.0e-6,
                "balanced_route": "existing_InterfaceBalancedCoupling_BAL_H",
            },
            "direct_controls": {
                "rhs_count": 3,
                "additional_rhs_count": 3 if backend == "exact" else 0,
                "global_factor_count": 1,
                "one_mat_solve_per_nonzero_rhs": True,
                "full_reference": "native p4 matrix-free action plus carrier",
                "icntl": {"10": 0, "35": 0 if backend == "exact" else 2},
                "cntl": {"7": None if backend == "exact" else 1.0e-5},
            },
            "memory_policy": "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            "resources": {
                "workflow_seconds": 43200,
                "solve_seconds": 43200,
                "pc_soft_seconds": 0,
                "pc_hard_seconds": 0,
                "mpi_size": 1,
                "require_zero_swap": True,
                "time_policy": "observe_only",
                "require_observe_only": True,
                "inventory_memory_cap_bytes_by_stage": {
                    stage: 6 * 1024**3 for stage in stages
                },
                "shared_temp_workspace_cap_bytes": 1 * 1024**3,
                "local_factor_matrix_and_allocated_cap_bytes": 6 * 1024**3,
                "interface_matrix_factor_solve_cap_bytes": 6 * 1024**3,
                "interface_workspace_cap_bytes": 1 * 1024**3,
                "tree_cap_bytes": 8 * 1024**3,
                "dynamic_launch_cap_formula": "min(8GiB, effective_available_bytes-reserve_bytes)",
                "reserve_formula": "max(4GiB, 0.15*effective_total_bytes)",
                "warning_fraction": 0.85,
                "stage_budgets": stages,
            },
            "gates": {
                "native_A4_relative_residual": 1.0e-10 if backend == "exact" else 0.5,
                "native_identity_relative": 1.0e-10,
                "field_l2_and_scaled_curl": 1.0e-8 if backend == "exact" else 0.25,
                "solve_call_delta": 1,
                "rhs_input_unchanged": True,
                "linearity_repeat": "reported_from_three_additional_exact_calls"
                if backend == "exact" else "not_applicable_in_U3",
                "zero_action": 1.0e-12,
                "strict_slave_zero": True,
                "p6_interface_is_conditional": True,
            },
            "qualification": (
                "opt_in; U0 then matched U1/U2, optional single tau=1e-5 U3, "
                "then selected U4/U5; observe_only"
            ),
        }
    if identity == P4_BLR_PROFILE:
        stage_budgets = {
            "S0_PREFLIGHT": {"workflow_seconds": 600, "solve_seconds": 600},
            "S1_CONTROL": {"workflow_seconds": 1800, "solve_seconds": 1800},
            "S2_BLR_CONTROL": {"workflow_seconds": 14400, "solve_seconds": 14400},
            "S3_ORIGINAL": {"workflow_seconds": 14400, "solve_seconds": 10800},
            "S4_NOTCH": {"workflow_seconds": 14400, "solve_seconds": 10800},
            "S5_FINALIZE": {"workflow_seconds": 43200, "solve_seconds": 43200},
        }
        return {
            "identity": P4_BLR_PROFILE,
            "scope": "review_v16_p4_blr",
            "physical_levels": [6, 4],
            "common_core": {
                "active_matrix": "native p4 MPC augmented A4 with 80 carrier rows",
                "interface_matrix": "[V B; -D H]",
                "rhs_source": "three hash-bound reviewed V14 Q1 RHS records",
                "factor_lifetime": "one global BLR factor and matrix retained through all three evaluations",
                "reference_in_factor_or_initial_guess": False,
                "old_macro_objects": False,
                "old_p2_p1_levels": False,
            },
            "outer": {
                "ksp_type": "right_fgmres",
                "restart": 32,
                "max_iterations": 2048,
                "zero_start": True,
                "live_KSP": True,
                "explicit_true_residual_limit": 1.0e-6,
            },
            "direct_controls": {
                "rhs_count": 3,
                "global_factor_count": 1,
                "solve_order": "sequential",
                "one_mat_solve_per_rhs": True,
                "full_reference": "native p4 A4 with 80 port rows",
                "immediate_packet_fields": [
                    "full_augmented_solution",
                    "native_A4_residual",
                    "native_residual_identity",
                    "rho",
                    "field_l2",
                    "scaled_curl",
                    "solve_counters",
                    "timings",
                ],
            },
            "memory_policy": "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            "resources": {
                "workflow_seconds": 43200,
                "solve_seconds": 43200,
                "pc_soft_seconds": 0,
                "pc_hard_seconds": 0,
                "mpi_size": 1,
                "require_zero_swap": True,
                "time_policy": "observe_only",
                "require_observe_only": True,
                "inventory_memory_cap_bytes_by_stage": {
                    stage: 6 * 1024**3 for stage in stage_budgets
                },
                "shared_temp_workspace_cap_bytes": 1 * 1024**3,
                "local_factor_matrix_and_allocated_cap_bytes": 6 * 1024**3,
                "interface_matrix_factor_solve_cap_bytes": 6 * 1024**3,
                "interface_workspace_cap_bytes": 1 * 1024**3,
                "tree_cap_bytes": 8 * 1024**3,
                "dynamic_launch_cap_formula": "min(8GiB, effective_available_bytes-reserve_bytes)",
                "reserve_formula": "max(4GiB, 0.15*effective_total_bytes)",
                "warning_fraction": 0.85,
                "stage_budgets": stage_budgets,
            },
            "gates": {
                "native_A4_relative_residual": 0.5,
                "field_l2_and_scaled_curl": 0.25,
                "solve_call_delta": 1,
                "rhs_input_unchanged": True,
                "linearity_repeat": 1.0e-12,
                "zero_action": 1.0e-12,
                "p6_interface_is_conditional": True,
            },
            "qualification": "opt_in; S1 bridge and S2 BLR control evidence precede S3 original p6 and S4 notch stages",
        }
    if identity == P4_BLR_TRADEOFF_PROFILE:
        facts = profile_facts(P4_BLR_PROFILE)
        stage_budgets = {
            "T1_BLR_CONTROL": {"workflow_seconds": 14400, "solve_seconds": 14400},
            "T2_BLR_CONTROL": {"workflow_seconds": 14400, "solve_seconds": 14400},
            "T3_ORIGINAL": {"workflow_seconds": 14400, "solve_seconds": 10800},
            "T4_NOTCH": {"workflow_seconds": 14400, "solve_seconds": 10800},
            "T5_FINALIZE": {"workflow_seconds": 43200, "solve_seconds": 43200},
        }
        facts["identity"] = P4_BLR_TRADEOFF_PROFILE
        facts["scope"] = "review_v17_p4_blr_tradeoff"
        facts["direct_controls"] = {
            **facts["direct_controls"],
            "allowed_blr_thresholds": dict(P4_BLR_TRADEOFF_THRESHOLDS),
            "coverage_statistics": {
                "stdout_enabled": True,
                "icntl": {"2": 0, "3": 6, "4": 2},
                "meaning": "MUMPS BLR front coverage lines are read from bounded standard output",
            },
        }
        facts["resources"] = {
            **facts["resources"],
            "stage_budgets": stage_budgets,
            "inventory_memory_cap_bytes_by_stage": {
                stage: 6 * 1024**3 for stage in stage_budgets
            },
        }
        facts["qualification"] = (
            "opt_in; T1=1e-3, conditional T2=1e-4, then at most one selected T3/T4 pair"
        )
        return facts
    if identity == SCHUR_PROFILE:
        return {
            'identity': SCHUR_PROFILE,
            'scope': 'review_v14_Q0_to_Q6_physical_p4_schur',
            'physical_levels': [6, 4],
            'common_core': {
                'active_matrix': 'A_IiIi from native p4 MPC active indices',
                'interface_matrix': '[S_V B; -D H]',
                'gamma_support': 'shared cell owners plus both nonzero B/D supports',
                'internal_blocks': 42,
                'internal_rows_expected': 35868,
                'gamma_rows_expected': 13092,
                'active_rows_expected': 48960,
                'max_internal_rows': 2048,
                'batch_columns': 32,
                'old_macro_objects': False,
                'old_p2_p1_levels': False,
                'global_dense_schur': False,
            },
            'outer': {
                'ksp_type': 'right_fgmres', 'restart': 32, 'max_iterations': 2048,
                'zero_start': True, 'live_KSP': True, 'KSP_create_count': 1,
                'KSP_solve_count': 1, 'explicit_true_residual_limit': 1e-6,
            },
            'direct_controls': {
                'rhs_count': 3, 'global_factor_count': 1,
                'internal_factor_count': 42, 'solve_order': 'sequential',
                'full_reference': 'native p4 A4 with 80 port rows',
                'schur_reference': 'explicit sparse S_V plus 80 port rows',
            },
            'memory_policy': 'SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
            'resources': {
                'workflow_seconds': 14400, 'solve_seconds': 10800,
                'pc_soft_seconds': 25, 'pc_hard_seconds': 30,
                'mpi_size': 1, 'require_zero_swap': True,
                'inventory_memory_cap_bytes_by_stage': {
                    'Q1_FULL_DIRECT': 6 * 1024**3,
                    'Q2_SCHUR_DIRECT': 6 * 1024**3,
                    'Q3_INTERFACE_CONTROL': 3 * 1024**3,
                    'Q4_ORIGINAL': 3 * 1024**3,
                    'Q5_NOTCH': 3 * 1024**3,
                },
                'shared_temp_workspace_cap_bytes': 1 * 1024**3,
                'local_factor_matrix_and_allocated_cap_bytes': 512 * 1024**2,
                'interface_matrix_factor_solve_cap_bytes': 64 * 1024**2,
                'interface_workspace_cap_bytes': 64 * 1024**2,
                'tree_cap_bytes': 8 * 1024**3,
                'dynamic_launch_cap_formula':
                    'min(8GiB, effective_available_bytes-reserve_bytes)',
                'reserve_formula': 'max(4GiB, 0.15*effective_total_bytes)',
                'warning_fraction': 0.85,
                'stage_budgets': {
                    'Q0_CORE': {'workflow_seconds': 600, 'solve_seconds': 600},
                    'Q1_FULL_DIRECT': {'workflow_seconds': 1800, 'solve_seconds': 1800},
                    'Q2_SCHUR_DIRECT': {'workflow_seconds': 3600, 'solve_seconds': 3600},
                    'Q3_INTERFACE_CONTROL': {'workflow_seconds': 3600, 'solve_seconds': 3600},
                    'Q4_ORIGINAL': {'workflow_seconds': 14400, 'solve_seconds': 10800},
                    'Q5_NOTCH': {'workflow_seconds': 14400, 'solve_seconds': 10800},
                    'Q6_FINALIZE': {'workflow_seconds': 43200, 'solve_seconds': 43200},
                },
            },
            'gates': {
                'direct_relative_residual': 1e-10,
                'field_l2_and_scaled_curl': 1e-8,
                'interface_rcond': 1e-12,
                'interface_workspace_bytes': 64 * 1024**2,
            },
            'qualification': 'opt_in; Q1/Q2 direct comparison precedes Q3-Q5',
        }
    if identity in RECURSIVE_PROFILES:
        from .physical_recursive_profile import recursive_profile_facts
        return recursive_profile_facts(identity)
    if identity in BALANCED_PROFILES:
        from .physical_balanced_profile import balanced_profile_facts
        return balanced_profile_facts(identity)
    if identity in BOUNDED_PROFILES:
        from .physical_balanced_profile import bounded_profile_facts
        return bounded_profile_facts(identity)
    if identity in MACRO_V10_PROFILES:
        return macro_v10_profile_facts()
    if identity in MACRO_V11_PROFILES:
        return macro_v11_profile_facts()
    if identity in MACRO_V12_PROFILES:
        return macro_v12_profile_facts()
    if identity in P4_DIRECTION_DIAGNOSIS_PROFILES:
        return p4_direction_diagnosis_profile_facts()
    if identity == JOINT_PROFILE:
        facts = profile_facts(LIGHT_PROFILE)
        facts['identity'] = identity
        facts['fine_auxiliary']['direction_acceptance'] = 'old_sequential_MR_generation_then_joint_QR_small_SVD'
        facts['joint_mr3'] = dict(relative_singular_cutoff=1e-12,
            explicit_residual_safeguard=1e-10, maximum_extra_A6=1,
            additional_fine_vector_limit=16, additional_workspace_bytes_limit=64*1024**2,
            direction_generator=LIGHT_PROFILE, physical_A6='original_split_form')
        return facts
    if identity == PACKED_PROFILE:
        facts = profile_facts(FAST_PROFILE)
        facts.update(identity=identity, backend=dict(B6='exact_partial_assembly_batch8_contiguous',
            pc_A6_volume='exact_partial_assembly_batch8_contiguous', outer_A6='original_split_form',
            installation='after_original_setup_and_window', shared_dtn='borrowed'))
        facts['diagnostic_profile'] = dict(complete_pc_limit=14, per_path_limit=7,
            setup_inclusive_seconds=2400, outer_execution_enabled=False, paired_shared_setup=True)
        facts['resources'].update(performance_grace_seconds=60, batch_limit_seconds=36000)
        return facts
    if identity == LIGHT_PROFILE:
        facts = profile_facts(REFERENCE_PROFILE)
        facts.update(identity=identity, positive_identity='H6',
            backend=dict(B6='exact_partial_assembly_batch8_contiguous', A6='original_split_form'),
            fine_auxiliary=dict(identity='fixed_degree3_H6', pre_cycles=1, post_cycles=1,
                direction_acceptance='fine_physical_modified_residual', physical_middle_directions=1,
                calls_per_PC=dict(H6=2, S6=0, B6=4, positive_p3=0, positive_p1=0)))
        facts['outer'].update(max_iterations=2048, safe_snapshot_interval=8, safe_snapshot_seconds=120,
            reported_iteration_interval=1)
        facts['resources'].update(workflow_seconds=10800, solve_seconds=7200, independent_p1_factors=0,
                                  performance_grace_seconds=60, batch_limit_seconds=36000)
        return facts
    if identity == FAST_PROFILE:
        facts = profile_facts(REFERENCE_PROFILE)
        facts.update(identity=identity, backend=dict(B6='exact_partial_assembly_batch8',
            pc_A6_volume='exact_partial_assembly_batch8', outer_A6='original_split_form',
            installation='after_original_setup_and_window', shared_dtn='borrowed'))
        facts['outer'].update(max_iterations=2048)
        facts['resources'].update(workflow_seconds=10800, solve_seconds=7200)
        facts['diagnostic_profile'] = dict(complete_pc_limit=7, setup_inclusive_seconds=1800,
            outer_execution_enabled=False)
        return facts
    if identity == REFERENCE_PROFILE:
        facts = profile_facts()
        facts.update(identity=identity, reference_only=True,
            intermediate=dict(degree=4, solver='exact_augmented_A4_reference', relative_tolerance=1e-10),
            auxiliary=dict(constructed=False, reason='replaced by diagnostic A4 reference'))
        facts['resources'].update(independent_p1_factors=1, reference_p4_factors=1,
            reference_factor_budget='dynamic whole-workflow cap; not bounded p1 cap')
        return facts
    if identity != PROFILE:
        raise ValueError('unknown physical middle profile')
    return {
        "identity": PROFILE,
        "outer": {"ksp_type": "right_fgmres", "restart": 32, "max_iterations": 512,
                  "relative_tolerance": 1e-6, "cycle_ledger_interval": 32,
                  "checkpoint_interval": 128, "final_safe_checkpoint": True,
                  "safe_snapshot_interval": 32,
                  "safe_snapshot_purpose": "last completed state survives interruption between regular128 checkpoints",
                  "initial_guess": "zero"},
        "fine_auxiliary": {"identity": "existing_positive_same_mesh_6_3_1",
                           "pre_cycles": 1, "post_cycles": 1,
                           "direction_acceptance": "fine_physical_modified_residual",
                           "physical_middle_directions": 1},
        "intermediate": {"degree": 4, "ksp_type": "right_fgmres", "restart": 12,
                         "max_iterations": 36, "relative_tolerance": 1e-2,
                         "initial_guess": "zero"},
        "auxiliary": {"levels": [4, 2, 1], "shift_sigma": 0.5,
                      "shift_weight": "max(abs(epsilon_r),1e-12)",
                      "smoother": "right_fgmres_positive_diagonal_jacobi",
                      "pre_steps": 3, "post_steps": 3},
        "resources": {"workflow_seconds": 7200, "solve_seconds": 3600,
                      "absolute_cap_bytes": 12_000_000_000,
                      "reserve_min_bytes": 4*1024**3, "reserve_fraction": 0.15,
                      "warning_fraction": 0.85, "job_swap_max_bytes": 0,
                      "p1_max_rows_each": 4096, "p1_matrix_factor_max_bytes_each": 512*1024**2,
                      "independent_p1_factors": 2},
        "fine_physical_operator_modified": False,
        "official_recovery_requires_full_explicit_true_residual": True,
        "release_auxiliary_before_recovery": True,
    }
