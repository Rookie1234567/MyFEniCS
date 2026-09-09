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
BOUNDED_ROUTES = {
    BOUNDED_ENTITY_PROFILE: 'ENTITY16',
    BOUNDED_PROJECTED_PROFILE: 'PROJECTED_SEQ2_16',
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
    """Return the V7 outer contract without importing the formal builder."""
    if identity not in BOUNDED_ROUTES:
        raise ValueError('unknown bounded V7 profile')
    route = BOUNDED_ROUTES[identity]
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
        route_b=dict(status='registered_not_implemented' if route != 'ENTITY16' else 'conditional'))
    facts['outer'].update(max_iterations=2048, restart=32,
        checkpoint_interval=32, safe_snapshot_interval=8,
        safe_snapshot_seconds=120, live_KSP=True, KSP_create_count=1,
        KSP_solve_count=1, screen=dict(iterations=128, solve_seconds=1800,
        absolute_true_limit=1e-2, last8_interval_ratio=.80,
        three_checkpoint_geometric_ratio=.80,
        mid_budget_seconds=5400, mid_budget_residual_limit=1e-3))
    facts['resources'].update(workflow_seconds=14400, solve_seconds=10800,
        batch_limit_seconds=43200, performance_grace_seconds=60,
        independent_p1_factors=0, reference_p4_factors=0,
        local_trace_payload_cap_bytes=256*1024**2,
        physical_p2_max_rows=8192, physical_p2_budget_bytes=512*1024**2)
    facts['resources'].pop('reference_factor_budget', None)
    return facts
