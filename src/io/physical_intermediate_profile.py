"""Frozen, explicit input identity for the development physical middle solver."""

PROFILE = "physical_intermediate_p4_shifted_aux_v1"
REFERENCE_PROFILE = "physical_intermediate_p4_reference_v1"
FAST_PROFILE = "a2r_equivalent_fast_v1"
LIGHT_PROFILE = "p6smooth_p4ref_p6smooth_v1"
PACKED_PROFILE = "a2r_packed_equivalent_v2"
JOINT_PROFILE = "light_p4ref_jointmr3_v2"
from .physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
from .physical_recursive_profile import RECURSIVE_PROFILES

PROFILES = (PROFILE, REFERENCE_PROFILE, FAST_PROFILE, LIGHT_PROFILE, PACKED_PROFILE, JOINT_PROFILE) + BALANCED_PROFILES + RECURSIVE_PROFILES + BOUNDED_PROFILES


def profile_facts(identity=PROFILE) -> dict:
    if identity in RECURSIVE_PROFILES:
        from .physical_recursive_profile import recursive_profile_facts
        return recursive_profile_facts(identity)
    if identity in BALANCED_PROFILES:
        from .physical_balanced_profile import balanced_profile_facts
        return balanced_profile_facts(identity)
    if identity in BOUNDED_PROFILES:
        from .physical_balanced_profile import bounded_profile_facts
        return bounded_profile_facts(identity)
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
