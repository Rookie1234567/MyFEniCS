"""Frozen V5 identities, shared by E1 evidence and the planned run_case route.

Public schema/launcher registration is a separate reviewed wiring step.
"""

BALANCED_ROUTES = {
    'balanced_h6_p4_v5': 'BAL_H',
    'balanced_s6_p4_v5': 'BAL_S',
    'projected_krylov6_h6_p4_v5': 'PROJ_K6',
}
BALANCED_PROFILES = tuple(BALANCED_ROUTES)
from .native_capacity_profile import NATIVE_PROFILES
BALANCED_ROUTES.update({name: 'BAL_H' for name in NATIVE_PROFILES})


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
