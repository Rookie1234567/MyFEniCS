"""Frozen V5 identities, shared by E1 evidence and the planned run_case route.

Public schema/launcher registration is a separate reviewed wiring step.
"""

BALANCED_ROUTES = {
    'balanced_h6_p4_v5': 'BAL_H',
    'balanced_s6_p4_v5': 'BAL_S',
    'projected_krylov6_h6_p4_v5': 'PROJ_K6',
}
BALANCED_PROFILES = tuple(BALANCED_ROUTES)

# V7 is intentionally a separate opt-in family.  Keeping it out of the V5
# tuple prevents the old one-of-three batch ledger from silently accepting a
# bounded inexact coarse inverse as one of its historical runs.
BOUNDED_ENTITY_PROFILE = 'bounded_entity16_v7'
BOUNDED_PROJECTED_PROFILE = 'bounded_projected_seq2_16_v7'
BOUNDED_ENTITY_GCROT8_PROFILE = 'balanced_h6_entity_gcrot8_v8'
BOUNDED_ENTITY_GCROT8_NEW16_PROFILE = 'balanced_h6_entity_gcrot8_new16_v9'
BOUNDED_ROUTES = {
    BOUNDED_ENTITY_PROFILE: 'ENTITY16',
    BOUNDED_PROJECTED_PROFILE: 'PROJECTED_SEQ2_16',
    BOUNDED_ENTITY_GCROT8_PROFILE: 'ENTITY_GCROT8',
    BOUNDED_ENTITY_GCROT8_NEW16_PROFILE: 'ENTITY_GCROT8_NEW16',
}
BOUNDED_PROFILES = tuple(BOUNDED_ROUTES)


def balanced_profile_facts(identity):
    from .physical_intermediate_profile import profile_facts, REFERENCE_PROFILE
    route = BALANCED_ROUTES[identity]
    facts = profile_facts(REFERENCE_PROFILE)
    facts.update(identity=identity, route=route, reference_only=True,
        balanced=dict(C='P A4^-1 PH', primal_projection='I-CA', dual_projection='I-AC',
                      complement='ker(PH A); not M0 projection', stage_MR=False, terminal_MR=False),
        fine_auxiliary=dict(identity='S6_upper_cycle' if route=='BAL_S' else 'H6_degree3',
                            calls_per_PC_max=6 if route=='PROJ_K6' else 1),
        additional_fine_vectors_limit=32,
        inner=dict(max_steps=6 if route=='PROJ_K6' else 0, restart=False, zero_start=True,
                   true_relative_target=.25, non_target_finite_return_allowed=True),
        structural_calls=dict(C_max=7 if route=='PROJ_K6' else 2,
                              A6_max=13 if route=='PROJ_K6' else 2,
                              extra_inner_true_A6_max=6 if route=='PROJ_K6' else 0))
    facts['outer'].update(max_iterations=2048, checkpoint_interval=32, safe_snapshot_interval=32,
        safe_snapshot_seconds=120, safe_snapshot_purpose='every32 and120s safe snapshots; terminal vec_sol', live_KSP=True, KSP_create_count=1, KSP_solve_count=1,
        screen=dict(iterations=128, solve_seconds=1800, absolute_true_limit=1e-2,
                    three_checkpoint_geometric_ratio=.65, nonseparable_enabled=False))
    facts['intermediate'].update(max_refinements=2, success_formal_packets='scalar_only',
        failure_packets='complete_current_rhs_before_rejection', replay_old_failure=False)
    facts['resources'].update(workflow_seconds=10800, solve_seconds=7200,
        independent_p1_factors=1 if route=='BAL_S' else 0,
        batch_limit_seconds=43200, performance_grace_seconds=60,
        E1_setup_tests_seconds=5400, E1_PC_limit=15, E1_C_limit=55, E1_MatSolve_limit=165)
    return facts


def bounded_profile_facts(identity):
    """Return the bounded outer contract without importing the formal builder."""
    if identity not in BOUNDED_ROUTES:
        raise ValueError('unknown bounded profile')
    route = BOUNDED_ROUTES[identity]
    recycled = route in ('ENTITY_GCROT8', 'ENTITY_GCROT8_NEW16')
    from .physical_intermediate_profile import profile_facts, REFERENCE_PROFILE
    facts = profile_facts(REFERENCE_PROFILE)
    facts.update(identity=identity, route=route, reference_only=False,
        physical_levels=[6, 4, 2],
        balanced=dict(C='P64 I4(P64H q)', primal_projection='I-C A6',
                      dual_projection='I-A6 C',
                      complement='inexact coarse balance; eps1-eps2 ledger',
                      stage_MR=False, terminal_MR=False),
        fine_auxiliary=dict(identity='H6_degree3', calls_per_PC=dict(I4=2, H6=1)),
        intermediate=dict(degree=4, ksp_type='right_fgmres', restart=16,
                          max_iterations=16, relative_tolerance=1e-4,
                          initial_guess='zero', seconds=30,
                          safe_return_seconds=25, explicit_residual='native_A4',
                          finite_inexact_return=True),
        auxiliary=dict(levels=[4, 2], physical=True,
                       bottom='bounded_physical_p2', global_p4_factor=0,
                       global_p4_matrix=0),
        additional_fine_vectors_limit=32,
        inner=dict(method='right_fgmres', restart=16, max_iterations=16,
                   zero_start=True, true_relative_target=1e-4,
                   non_target_finite_return_allowed=True,
                   safe_return_seconds=25, hard_seconds=30,
                   separate_native_residual_action=True,
                   no_direction_consecutive_limit=2,
                   timeout_consecutive_limit=3),
        inexact_balance=dict(identity='P64H(q-A6z)=eps1-eps2',
                             closure_limit=1e-8, first=True, every_PC=32,
                             exit=True, RHS_scale='sum(rhs+applied) for both I4 calls'),
        storage=dict(levels=[6, 4, 2], p6_global_aij=0, p4_global_aij=0,
                     p6_global_factor=0, p4_global_factor=0,
                     bottom='bounded_physical_p2',
                     owner_route='792 edge + 774 face entities'),
        route_a=dict(source_sha='9dbf12355e6e6c7eac23d055c12da4e7eda2a7d8',
                     cached_exact_volume_and_dtn=True,
                     formal_lifecycle_unbounded_entity_pilot_caps=dict(E_volume=263, HT=65),
                     mpi_owner_route='MPI1-only qualification; safe callback in formal'),
        route_b=dict(
            status='conditional' if route != 'ENTITY16' else 'conditional',
            implementation='projected_full252_seq2',
            source_sha='dcca0f5ea6b7ba9221b23dd210a3c06839cc47be',
            patch_count=252, patch_dimension=144,
            grouping='structured_cell_coordinate_parity_(i+j+k)%2',
            formula='M0 + M1 - M1*T*M0',
            no_saved_entity_lu_overlap=True))
    facts['outer'].update(max_iterations=2048, restart=32,
        checkpoint_interval=32, safe_snapshot_interval=8,
        safe_snapshot_seconds=120, live_KSP=True, KSP_create_count=1,
        KSP_solve_count=1, screen=dict(iterations=128, solve_seconds=1800,
        absolute_true_limit=1e-2, last8_interval_ratio=.80,
        three_checkpoint_geometric_ratio=.80,
        mid_budget_seconds=5400, mid_budget_residual_limit=1e-3))
    facts['resources'].update(workflow_seconds=14400, solve_seconds=10800,
        batch_limit_seconds=36000 if recycled else 43200,
        performance_grace_seconds=60,
        independent_p1_factors=0, reference_p4_factors=0,
        local_trace_payload_cap_bytes=256*1024**2,
        physical_p2_max_rows=8192, physical_p2_budget_bytes=512*1024**2)
    facts['resources'].pop('reference_factor_budget', None)
    if route in ('ENTITY_GCROT8', 'ENTITY_GCROT8_NEW16'):
        fixed_policy = route == 'ENTITY_GCROT8_NEW16'
        facts['intermediate'].update(
            ksp_type='gcrotmk', restart=8, max_iterations=1,
            relative_tolerance=1e-4, initial_guess='zero',
            scipy_backend='scipy.sparse.linalg.gcrotmk',
            scipy_fixed=dict(m=('derived_from_effective_rank' if fixed_policy else 8),
                             k=8, maxiter=1, truncate='smallest',
                             discard_C=False, tol=1e-4, atol=0.0))
        facts['inner'].update(
            method='gcrotmk', restart=8, max_iterations=1,
            true_relative_target=1e-4, fixed_round=True,
            max_new_B4=16, max_new_arnoldi_directions=16)
        facts['recycling'] = dict(
            enabled=True, pool_pair_order='(U,Q)', max_pool_pairs=8,
            relation='A4 U = Q', orthogonality='Q^H Q = I',
            backend='scipy.sparse.linalg.gcrotmk', m=8, k=8, maxiter=1,
            truncate='smallest', discard_C=False, tol=1e-4, atol=0.0,
            max_new_B4=16, max_new_arnoldi_directions=16,
            orthogonality_limit=1e-10, closure_limit=1e-10,
            rank_threshold=1e-12, safe_return_seconds=25,
            hard_seconds=30,
            native_spot='first_nonempty_then_absolute_calls_32_64_...',
            extra_bytes_limit=(128*1024**2 if fixed_policy else 64*1024**2),
            p4_independent_rows=48960,
            pool_numeric_bytes_p4_derived=12_533_760,
            transaction='private_CU_copy_commit_after_final_native_checks',
            initial_projection=dict(
                formula='c0 = U (Q^H g)',
                source='current_model_outer_rhs_and_current_initial_pool_only',
                uses_reference_or_previous_solution=False,
                zero_outer_initial_guess=True, zero_initial_pool=True),
            native_spot_schedule='first_nonempty_then_absolute_calls_32_64_...',
            native_spot_recommendation='first plus absolute calls 32/64/...')
        if fixed_policy:
            facts['inner'].update(policy='FIXED_NEW16_RECYCLE8')
            facts['outer']['screen'].update(
                iterations_role='observation_only',
                decision='first_safe_true_residual_check_at_or_after_1800_seconds',
                absolute_true_limit=0.10)
            facts['recycling'].update(
                policy='FIXED_NEW16_RECYCLE8',
                m_call_formula='16-max(8-effective_rank,0)',
                new_work_upper_bound=16,
                payload_cap_bytes=128*1024**2,
                payload_scope=(
                    'full_I4_search_vectors_persistent_transaction_pool_QR_SVD_'
                    'truncation_temporaries_adapter_vectors_and_indices'))
        facts['inexact_balance'].update(
            recycling_identity='A4 U=Q; cached-transform closure plus native spot checks')
        facts['route_b'] = dict(
            status='not_applicable', candidate=False,
            reason=('V8 admits only the entity GCROT8 route; no projected B candidate'
                    if not fixed_policy else
                    'V9 fixed-new16 route admits only the entity GCROT8 route'))
        facts['preparation_ledger'] = dict(
            schema=('task39extra.review-v9-equal-new-work-budget.v1'
                    if fixed_policy else
                    'task39extra.review-v8-k0-k1-budget.v1'),
            total_seconds=3600, finite_control_seconds=900,
            old_v7_ledger='not_used_or_merged')
    return facts
