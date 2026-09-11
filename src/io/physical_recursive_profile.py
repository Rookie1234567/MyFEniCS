"""Explicit opt-in V6 recursive physical coarse profiles; HI requires qualification."""
RECURSIVE_LO = 'balanced_h6_recursive_p4_lo_v6'
RECURSIVE_HI = 'balanced_h6_recursive_p4_hi_v6'
RECURSIVE_PROFILES = (RECURSIVE_LO, RECURSIVE_HI)

# Review V10 is an explicit control/runner profile.  It is kept separate
# from the V6 production-dispatch tuple until its M1/M2 qualification closes.
MACRO_V10_PROFILE = 'physical_macro_dd4_v10'
MACRO_V10_PROFILES = (MACRO_V10_PROFILE,)
MACRO_V11_PROFILE = 'physical_macro_dd4_v11'
MACRO_V11_PROFILES = (MACRO_V11_PROFILE,)
MACRO_V12_PROFILE = 'physical_macro_dd4_v12'
MACRO_V12_PROFILES = (MACRO_V12_PROFILE,)


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


def macro_v11_profile_facts():
    """Return the V11 opt-in contract with the symbolic-sized local policy.

    V11 changes only the local MUMPS work-package policy.  The block topology,
    physical operator, I4 limits, and the old V10 profile remain separate so
    selecting this identity is the only way to activate the new allocation
    controls.
    """
    facts = macro_v10_profile_facts()
    facts.update(
        identity=MACRO_V11_PROFILE,
        scope='N0_N5_symbolic_sized_local_mumps_validation',
        memory_policy='SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
        dat_contract={
            'solver_preconditioner': MACRO_V11_PROFILE,
            'solver_memory_policy': 'SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
            'dispatch': 'profile-selected macro V11 M1/N2 controls',
        },
        resources={
            **facts['resources'],
            'n0_n2_seconds': 7200,
            'n1_calibration_seconds': 900,
            'n2_local_build_seconds': 3600,
            'n2_controls_seconds': 1200,
            'cumulative_seconds': 43200,
        },
        stage_budgets={
            'N1_CALIBRATION': {'workflow_seconds': 900, 'solve_seconds': 900},
            'N2_M1_CONTROLS': {
                'cumulative_n0_n2_seconds': 7200,
                'build_seconds': 3600,
                'controls_seconds': 1200,
            },
            'N3_RESTART_PROBE': {'workflow_seconds': 3600, 'solve_seconds': 2400},
            'N4_ORIGINAL': {'workflow_seconds': 14400, 'solve_seconds': 10800},
            'N4_NOTCH': {'workflow_seconds': 14400, 'solve_seconds': 10800},
        },
        qualification='opt_in; V11 symbolic-sized local MUMPS policy; no old-default change',
    )
    facts['M1'] = {
        **facts['M1'],
        'calibration_blocks_max': 3,
        'calibration_numeric_max': 6,
        'calibration_solves_per_factor_max': 16,
        'calibration_residual_limit': 1e-10,
        'calibration_solution_difference_limit': 1e-10,
    }
    facts['memory_policy_contract'] = {
        'estimate': '1e6*(1+max(INFOG16,INFOG17))',
        'request': '1e6*ceil(max(32MiB,2*E+8MiB)/1e6)',
        'icntl23': 'set and read back before numeric',
        'icntl49': 'request 1 only when public getter/setter supports it',
        'unsupported_49': 'COMPACTION_UNSUPPORTED; continue if all other gates pass',
        'no_used_min_or_rss_offset': True,
    }
    return facts


def macro_v12_profile_facts():
    """Return the V12 full-validation contract.

    V12 deliberately keeps the V11 symbolic-sized MUMPS policy and physical
    operator.  Its only changed local allocation authority is the explicit
    2.5 GiB complete-inventory cap; the old V10/V11 default remains 2 GiB.
    The O0--O4 stages are recorded here so input validation, manifests, and
    runners consume one immutable profile rather than duplicating limits.
    """
    facts = macro_v11_profile_facts()
    facts.update(
        identity=MACRO_V12_PROFILE,
        scope='O0_O4_full_physical_macro_validation',
        memory_policy='SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
        # V12 is the first profile that is permitted to enter the physical
        # outer solve.  Do not inherit V10/V11's control-only switch or their
        # M1-only accounting fields through the profile copy above.
        outer_execution_enabled=True,
        outer_pc_calls=None,
        dat_contract={
            'solver_preconditioner': MACRO_V12_PROFILE,
            'solver_memory_policy': 'SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
            'dispatch': 'profile-selected macro V12 O0/O1/O2/O3/O4 stages',
        },
        qualification='opt_in; complete local inventory cap is 2.5 GiB; old defaults unchanged',
    )
    facts['macro_blocks'] = {
        **facts['macro_blocks'],
        'resident_cap_bytes': 2684354560,
        'resident_cap_gib': 2.5,
        'resident_inventory': 'complete simultaneous local arrays, W/P owner cache, C_U, and cached action',
    }
    facts['stage_budgets'] = {
        'O0_PRECHECK': {'workflow_seconds': 7200, 'build_seconds': 3600, 'controls_seconds': 1200},
        'O1_FULL_PHYSICAL_CONTROLS': {
            'workflow_seconds': 7200, 'build_seconds': 3600, 'controls_seconds': 1200,
        },
        'O2_RESTART_PROBE_32': {'workflow_seconds': 3600, 'solve_seconds': 2400},
        'O2_RESTART_PROBE_64': {'workflow_seconds': 3600, 'solve_seconds': 2400},
        'O3_ORIGINAL': {'workflow_seconds': 14400, 'solve_seconds': 10800},
        'O3_NOTCH': {'workflow_seconds': 14400, 'solve_seconds': 10800},
        'O4_FINALIZE': {'workflow_seconds': 43200},
    }
    facts['O1'] = {
        'bare_calibration_rhs': 6,
        'shared_inputs': 3,
        'new_I4_max': 12,
        'reference_role': 'measurement_only_or_REFERENCE_UNAVAILABLE',
        'one_c_gate': {
            'valid_samples_min': 2,
            'field_geometric_max': 0.80,
            'field_maximum': 1.10,
            'scaled_curl_geometric_max': 1.10,
            'residual_geometric_max': 1.0,
            'time_cumulative_max': 0.80,
        },
    }
    facts['O2'] = {
        'candidate_restarts': [32, 64],
        'zero_start': True,
        'same_rhs_and_A6': True,
        'max_iterations': 64,
        'checkpoint_nodes': [32, 40, 48, 56, 64],
        'endpoint_residual_ratio_max_for_64': 0.50,
        'endpoint_time_ratio_max_for_64': 1.25,
        'both_fail_before_48': 'WHOLE_PC_COST_NOT_VIABLE',
    }
    facts['O3'] = {
        'original_max_iterations': 2048,
        'true_residual_interval': 8,
        'checkpoint_interval': 32,
        'early_stop_rules': {'rho_gt_0_10_seconds': 1800, 'rho_gt_1e-3_seconds': 5400},
        'max_solve_seconds': 10800,
        'conditional_notch': True,
        'notch_geometry': 'existing V5 nonseparable 8-cell gap',
    }
    facts.pop('M1', None)
    facts['resources'] = {
        'workflow_seconds': 43200,
        'cumulative_seconds': 43200,
        'mpi_size': 1,
        'require_zero_swap': True,
        'build_and_controls_are_inclusive': True,
        'o0_o1_shared_seconds': 7200,
        'o2_probe_workflow_seconds': 3600,
        'o2_probe_solve_seconds': 2400,
        'o3_workflow_seconds': 14400,
        'o3_solve_seconds': 10800,
    }
    facts['memory_policy_contract'] = {
        **facts['memory_policy_contract'],
        'complete_inventory_cap_bytes': 2684354560,
        'old_profiles_cap_bytes': 2147483648,
    }
    return facts


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
