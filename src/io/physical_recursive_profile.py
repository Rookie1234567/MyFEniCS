"""Explicit opt-in V6 recursive physical coarse profiles; HI requires qualification."""
RECURSIVE_LO = 'balanced_h6_recursive_p4_lo_v6'
RECURSIVE_HI = 'balanced_h6_recursive_p4_hi_v6'
RECURSIVE_PROFILES = (RECURSIVE_LO, RECURSIVE_HI)


def recursive_profile_facts(identity):
    if identity not in RECURSIVE_PROFILES:
        raise ValueError('unknown recursive profile')
    from .physical_balanced_profile import balanced_profile_facts
    facts = balanced_profile_facts('balanced_h6_p4_v5')
    facts.update(identity=identity, reference_only=False,
        physical_levels=[6,4,2], inner=dict(projected_krylov_steps=0),
        intermediate=dict(degree=4, ksp_type='right_fgmres', restart=16,
            max_iterations=64, relative_tolerance=1e-4 if identity==RECURSIVE_LO else 1e-6,
            initial_guess='zero', seconds=60, explicit_interval=16,
            finite_inexact_return=True, success_formal_packets='scalar_only',
            retained_array_packets='slowest_input_and_failures'),
        auxiliary=dict(levels=[4,2], physical=True,
            B4='C42+(I-C42 A4)H4(I-A4 C42)', H4_degree=3, H4_power_steps=10),
        inexact_balance=dict(identity='PH(q-A6z)=eps1-eps2', closure_limit=1e-8,
            scale='sum of rhs and applied norms for both I4 calls', first=True,
            every_PC=32, exit=True, exit_recompute_I4=False),
        storage=dict(levels=[6,4,2],p6_global_aij=0,p4_global_aij=0,
            p6_global_factor=0,p4_global_factor=0,bottom='bounded_physical_p2'),
        qualification='LO first; HI requires realized component accuracy contrast')
    facts['balanced'].update(C='P I4(PH q)', complement='inexact coarse balance; not exact projection')
    facts['resources'].update(workflow_seconds=14400,solve_seconds=10800,
        reference_p4_factors=0,independent_p1_factors=0,
        physical_p2_max_rows=8192,physical_p2_budget_bytes=512*1024**2,
        physical_p2_true_tolerance=1e-10,physical_p2_max_refinements=2,
        global_swap_increment_stop=True,G0_G1_seconds=5400)
    facts['resources'].pop('reference_factor_budget',None)
    for key in ('E1_setup_tests_seconds','E1_PC_limit','E1_C_limit','E1_MatSolve_limit'):
        facts['resources'].pop(key,None)
    return facts
