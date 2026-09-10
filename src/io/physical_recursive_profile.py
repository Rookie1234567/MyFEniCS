"""Explicit opt-in V6 recursive physical coarse profiles; HI requires qualification."""
RECURSIVE_LO = 'balanced_h6_recursive_p4_lo_v6'
RECURSIVE_HI = 'balanced_h6_recursive_p4_hi_v6'
RECURSIVE_PROFILES = (RECURSIVE_LO, RECURSIVE_HI)

# Review V10 is an explicit control/runner profile.  It is kept separate
# from the V6 production-dispatch tuple until its M1/M2 qualification closes.
MACRO_V10_PROFILE = 'physical_macro_dd4_v10'
MACRO_V10_PROFILES = (MACRO_V10_PROFILE,)


def macro_v10_profile_facts():
    """Return the fixed M1 contract without changing old V6 profiles."""
    return {
        'identity': MACRO_V10_PROFILE,
        'scope': 'M0_M1_controls_only',
        'physical_levels': [6, 4, 2],
        'macro_blocks': {
            'seed_groups': 'floor(cell_coordinate/2)', 'expected_count': 42,
            'local_rows_cap': 2600, 'resident_cap_bytes': 2 * 1024**3,
            'temporary_workspace_reserve_bytes': 1 * 1024**3,
            'input_weighting': 'none', 'output_weighting': '1/multiplicity',
        },
        'B4': 'C_U+(I-C_U A4)M_D(I-A4 C_U)',
        'I4': {
            'method': 'right_FGMRES', 'zero_start': True, 'target': 1e-4,
            'restart': 4, 'max_iterations': 4, 'safe_return_seconds': 25,
            'hard_seconds': 30, 'native_residual': True,
        },
        'outer_execution_enabled': False,
        'outer_pc_calls': 0,
        'final_physical_true_residual_target': 1e-6,
        'dat_contract': {
            'solver_restart_and_max_iterations': 'I4 control only',
            'dispatch': 'profile-selected macro M1 controls',
        },
        'resources': {
            'workflow_seconds': 5400, 'build_seconds': 3600,
            'controls_seconds': 1200,
            'budget_relation': 'build_and_controls_are_inclusive',
            'mpi_size': 1, 'require_zero_swap': True,
        },
        'M1': {'bare_calibration_rhs': 6, 'shared_inputs': 3,
               'shared_I4_max': 6, 'outer_pc_calls': 0},
        'inexact_balance': {
            'BAL_H': 'eps1-eps2', 'ONE_C': 'eps1-g2', 'closure_limit': 1e-8,
        },
        'storage': {
            'p6_global_aij': 0, 'p4_global_aij': 0, 'p4_global_factor': 0,
            'global_column_probes': 0, 'pseudoinverse': 0, 'shift': 0,
        },
        'qualification': 'opt_in; M1 only until M2 selects a fixed framework/restart',
    }


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
