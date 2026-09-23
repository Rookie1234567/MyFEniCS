"""Opt-in workstation sizes and budgets; the numerical method is V5 BAL_H."""

NATIVE_CASES = {
    # User-authorized continuation of the previously stopped 13.5 nm run.
    # The 128-iteration screen remains fixed in balanced_profile_facts.  The
    # 5 nm user-authorized run has no wall/solve deadline; None is an explicit
    # contract value, not a large numeric substitute.
    'balanced_h6_p4_native_13p5': (13.5, (10.0,), 7200, 43200, 64800),
    'balanced_h6_p4_native_5nm': (5.0, (4.0, 3.0), None, None, None),
    'balanced_h6_p4_native_3nm': (3.0, (2.5, 2.0), 21600, 172800, 259200),
    'balanced_h6_p4_native_2nm': (2.0, (1.5, 2.0), None, None, None),
    'balanced_h6_p4_native_2nm_measured': (2.0, (1.5,), None, None, None),
    # Review V3 opt-in route.  This is the only profile using the measured
    # tree-RSS policy; all historical native identities retain their old
    # swap/prediction/resource contracts.
    'dual_condensed_balh_native_5nm_v3': (5.0, (4.0,), None, None, None),
}
V5_NATIVE_CASES = {
    'dual_condensed_balh_native_13p5_q4_v5': (13.5, (7.5,), 4),
    'dual_condensed_balh_native_13p5_q3_v5': (13.5, (7.5,), 3),
    'dual_condensed_balh_native_5nm_v5': (5.0, (4.0,), 4),
    'dual_condensed_balh_native_2nm_v5': (2.0, (1.5,), 4),
}
V5_EXPECTED_MODE_COUNTS = {
    'dual_condensed_balh_native_13p5_q4_v5': 80,
    'dual_condensed_balh_native_13p5_q3_v5': 80,
    'dual_condensed_balh_native_5nm_v5': 600,
    'dual_condensed_balh_native_2nm_v5': 3904,
}
NATIVE_CASES.update(
    {
        identity: (wavelength, meshes, None, None, None)
        for identity, (wavelength, meshes, _) in V5_NATIVE_CASES.items()
    }
)
NATIVE_PROFILES = tuple(NATIVE_CASES)
RETAINED_CONDENSED_PROFILE = 'dual_condensed_balh_native_5nm_v3'
V5_NATIVE_PROFILES = frozenset(V5_NATIVE_CASES)
V5_R13_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_13p5_q4_v5',
        'dual_condensed_balh_native_13p5_q3_v5',
    }
)
RETAINED_CONDENSED_PROFILES = frozenset(
    {RETAINED_CONDENSED_PROFILE, *V5_NATIVE_PROFILES}
)
NATIVE_TIME_LIMIT_MODES = {
    'balanced_h6_p4_native_13p5': 'bounded',
    'balanced_h6_p4_native_5nm': 'none',
    'balanced_h6_p4_native_3nm': 'bounded',
    'balanced_h6_p4_native_2nm': 'none',
    'balanced_h6_p4_native_2nm_measured': 'none',
    'dual_condensed_balh_native_5nm_v3': 'none',
}
NATIVE_TIME_LIMIT_MODES.update(
    {identity: 'none' for identity in V5_NATIVE_PROFILES}
)
NATIVE_NONE_TIME_PROFILES = frozenset(
    identity for identity, mode in NATIVE_TIME_LIMIT_MODES.items() if mode == 'none'
)
MATERIALS = {
    13.5: (0.999002304859, 0.00182649365),
    5.0: (0.99396854453, 0.00435380777),
    3.0: (0.99735217495, 0.000883207249),
    2.0: (0.99880148307, 0.000213688647),
}

USER_MATERIAL_METADATA = {
    2.0: {
        'material': 'Si / silicon',
        'density_g_cm3': 2.33,
        'delta': 0.00119851693,
        'beta': 0.000213688647,
        'authority': 'user-provided for this execution; not independently database-verified',
        'interpretation': 'complex refractive index n=1-delta+i*beta; epsilon=n*n',
    },
    5.0: {
        'material': 'Si / silicon',
        'density_g_cm3': 2.33,
        'delta': 0.00603145547,
        'beta': 0.00435380777,
        'authority': 'user-provided for this execution; not independently database-verified',
        'interpretation': 'complex refractive index n=1-delta+i*beta; epsilon=n*n',
    },
}


def native_profile_facts(identity):
    from .physical_balanced_profile import balanced_profile_facts
    wavelength, meshes, screen, solve, workflow = NATIVE_CASES[identity]
    time_limit_mode = NATIVE_TIME_LIMIT_MODES[identity]
    user_material = USER_MATERIAL_METADATA.get(wavelength)
    facts = balanced_profile_facts('balanced_h6_p4_v5')
    facts.update(identity=identity, native_capacity=True,
                 wavelength_nm=wavelength, allowed_mesh_targets_nm=list(meshes))
    facts['p4_p6_curl_implementation'] = 'native_curl_fused_avx512_strict_v1'
    facts['resources']['pss_interval_seconds'] = 5.0
    facts['p4_assembly_implementation'] = 'native_p4_row_loop_avx512_v1'
    facts['outer']['screen']['solve_seconds'] = screen
    facts['resources'].update(
        solve_seconds=solve, workflow_seconds=workflow,
        batch_limit_seconds=None if time_limit_mode == 'none' else 864000,
        absolute_cap_bytes=32*1024**3 if wavelength == 13.5 else int(1.60*1024**4),
        reserve_min_bytes=256*1024**3,
        planning_cap_bytes=24*1024**3 if wavelength == 13.5 else int(1.50*1024**4),
        concurrent_neighbor_authorized=True,
    )
    if identity == 'dual_condensed_balh_native_5nm_v3':
        # This route deliberately overrides the inherited V5 screen/backend
        # labels below.  The old balanced profile remains byte-for-byte
        # described for every other identity.
        facts['outer'].update(
            route='RETAINED_BAL_H_V20',
            ksp_type='fgmres',
            restart=32,
            max_iterations=2048,
            initial_guess='zero',
            screen=dict(
                iterations=128,
                solve_seconds=None,
                absolute_true_limit=None,
                progress_only=True,
                stop_on_screen=False,
                policy='progress_only_observed_not_a_stop_gate',
            ),
        )
        facts['p4_p6_curl_implementation'] = (
            'FFCx_original_split_curl_mass_retained_v20'
        )
        facts['p4_assembly_implementation'] = (
            'assembly_time_condensed_v20_exact_MPC_p4'
        )
        facts['formal_runner'] = 'src.runners.physical_retained_condensed_v20'
        facts['backend'] = {
            'p6': 'retained_local_schur_matrix_free',
            'p4': 'assembly_time_condensed_exact_inverse',
            'h6': 'physical_light_setup_original_window_then_packed_action',
            'outer': 'run_retained_fgmres',
            'not_old_fullspace_intermediate_solver': True,
        }
        facts['resources'].update(
            absolute_cap_bytes=1_300_000_000_000,
            planning_cap_bytes=1_300_000_000_000,
            startup_headroom_bytes=128*1024**3,
            resource_stop_policy='measured_tree_rss_only_v3',
            rss_hard_limit_bytes=1_300_000_000_000,
            rss_warning_bytes=1_170_000_000_000,
            swap_policy='observe_only',
            global_swap_delta_policy='observe_only',
            prediction_admission_policy='record_only',
            memavailable_runtime_policy='observe_and_warn_only',
            stop_on_global_swap=False,
            icntl23=0,
            require_zero_swap=False,
            p4_budget_policy='measured_rss_only_record_prediction',
            reference_memory_admission='measured_rss',
        )
        facts['condensed_route'] = {
            'name': 'v20_selective_dual_condensed',
            'p6': 'retained_local_schur_matrix_free',
            'p4': 'assembly_time_condensed_exact_inverse',
            'bridge': 'retained_J_inverse_original_BAL_H',
            'geometry_identity_policy': 'raw_unrounded',
            'shared_identity_cache': 'read_only_by_local_interior_dimension',
            'p4_max_refinements': 2,
            'p4_relative_residual_limit': 1.0e-10,
            'matrix_lifecycle': 'MATRIX_RETAINED_BACKEND_DEPENDENCY',
            'mode_inventory': 'dynamic_current_input',
        }
    facts['campaign_authorization'] = {
        'source': 'user_execution_instruction_2026-09-09',
        'formal_mpi': 1,
        'threads_per_process': 1,
        'restart': 32,
        'max_iterations': 2048,
        'initial_guess': 'zero',
        'screen': {
            'iterations': facts['outer']['screen']['iterations'],
            'solve_seconds': screen,
            'time_limit_mode': time_limit_mode,
            'enabled_for_notch': False,
        },
        'time_limit_mode': time_limit_mode,
        'solve_seconds': solve,
        'workflow_seconds': workflow,
    }
    if identity == 'dual_condensed_balh_native_5nm_v3':
        facts['campaign_authorization']['screen'].update(
            progress_only=True,
            stop_on_screen=False,
        )
        facts['campaign_authorization']['resource_policy'] = {
            'name': 'measured_tree_rss_only_v3',
            'rss_hard_limit_bytes': 1_300_000_000_000,
            'rss_warning_bytes': 1_170_000_000_000,
            'startup_headroom_bytes': 128*1024**3,
            'swap': 'observe_only',
            'faults': 'observe_only',
            'prediction': 'record_only',
            'elapsed': 'observe_only',
            'memavailable': 'observe_and_warn_only',
            'icntl23': 0,
        }
    if identity in V5_NATIVE_PROFILES:
        coarse_degree = V5_NATIVE_CASES[identity][2]
        facts['outer'].update(
            route='RETAINED_BAL_H_V20_V5',
            ksp_type='fgmres', restart=32, max_iterations=2048,
            initial_guess='zero',
            screen={
                'iterations': 128, 'solve_seconds': None,
                'absolute_true_limit': None, 'progress_only': True,
                'stop_on_screen': False,
                'policy': 'progress_only_observed_not_a_stop_gate',
            },
        )
        facts['p4_p6_curl_implementation'] = (
            'V20 retained p6 action; input-selected Vq/Aq coarse degree; '
            'sum-factorized fast-path qualification pending M-b'
        )
        facts['p4_assembly_implementation'] = (
            'assembly_time_condensed_v20_exact_MPC_at_coarse_degree_q'
        )
        facts['formal_runner'] = 'src.runners.physical_retained_condensed_v20'
        facts['backend'] = {
            'p6': 'retained_local_schur_matrix_free',
            'coarse': 'assembly_time_condensed_exact_inverse_at_solver.coarse_degree',
            'p4': 'internal compatibility alias for the selected Vq coarse system',
            'h6': 'V20 H6/Aq path pending M-b actual-factory qualification',
            'outer': 'run_retained_fgmres',
            'not_old_fullspace_intermediate_solver': True,
        }
        facts['resources'].update(
            absolute_cap_bytes=1_300_000_000_000,
            planning_cap_bytes=1_300_000_000_000,
            startup_headroom_bytes=128*1024**3,
            resource_stop_policy='measured_tree_rss_only_v3',
            rss_hard_limit_bytes=1_300_000_000_000,
            rss_warning_bytes=1_170_000_000_000,
            swap_policy='observe_only',
            global_swap_delta_policy='observe_only',
            prediction_admission_policy='record_only',
            memavailable_runtime_policy='observe_and_warn_only',
            stop_on_global_swap=False,
            icntl23=0,
            require_zero_swap=False,
            p4_budget_policy='measured_rss_only_record_prediction',
            reference_memory_admission='measured_rss',
        )
        facts['native_execution'] = {
            'supervisor_cpu': 9,
            'worker_cpu': 24,
            'mpi_size': 1,
            'math_threads': 1,
            'native_memory_policy': 'preferred_node1',
        }
        facts['retained_condensed_v20'] = {
            'coarse_degree': coarse_degree,
            'fixed_serial_owner_route': True,
            'optimized_owner_apply': True,
            'native_Aq_projection_check': True,
            'screen_is_progress_only': True,
            'factory_qualification': (
                'components_passed_990cell_q3_q4_Aq_and_18cell_q3_q4_setup; '
                'formal_R13_pair_and_path_release_pending'
                if identity in V5_R13_PROFILES else
                'selected_material_action_and_Aq_p4_components_passed; '
                'full_case_mode_inventory_and_formal_run_pending'
            ),
        }
        facts['p4_p6_curl_implementation'] = (
            'V5_opt_in_4bf2_sum_factorized_p6_A6_H6'
        )
        facts['p4_assembly_implementation'] = (
            'V5_assembly_time_condensed_coarse_Aq_exact_inverse'
        )
        facts['campaign_authorization'] = {
            'source': 'Review V5 user-authorized execution sequence',
            'formal_mpi': 1,
            'threads_per_process': 1,
            'restart': 32,
            'max_iterations': 2048,
            'initial_guess': 'zero',
            'screen': {
                'iterations': 128, 'solve_seconds': None,
                'time_limit_mode': 'none', 'enabled_for_notch': False,
                'progress_only': True, 'stop_on_screen': False,
            },
            'time_limit_mode': 'none',
            'solve_seconds': None,
            'workflow_seconds': None,
            'resource_policy': {
                'name': 'measured_tree_rss_only_v3',
                'rss_hard_limit_bytes': 1_300_000_000_000,
                'rss_warning_bytes': 1_170_000_000_000,
                'startup_headroom_bytes': 128*1024**3,
                'swap': 'observe_only', 'faults': 'observe_only',
                'prediction': 'record_only', 'elapsed': 'observe_only',
                'memavailable': 'observe_and_warn_only', 'icntl23': 0,
            },
        }
        facts['condensed_route'] = {
            'name': 'v20_selective_dual_condensed_v5',
            'p6': 'retained_local_schur_matrix_free',
            'p4': 'assembly_time_condensed_exact_inverse',
            'bridge': 'retained_J_inverse_original_BAL_H',
            'geometry_identity_policy': 'raw_unrounded',
            'shared_identity_cache': 'read_only_by_local_interior_dimension',
            'p4_max_refinements': 2,
            'p4_relative_residual_limit': 1.0e-10,
            'matrix_lifecycle': 'MATRIX_RETAINED_BACKEND_DEPENDENCY',
            'mode_inventory': 'dynamic_current_input',
        }
    if identity == 'balanced_h6_p4_native_2nm_measured':
        # User instruction 2026-09-18: measure the whole job, do not stop on
        # a predicted factor/workspace peak. GB here means 10**9 bytes.
        facts['resources'].update(
            absolute_cap_bytes=1_537_500_000_000,
            reference_memory_admission='measured_rss',
        )
        facts['campaign_authorization']['memory_override'] = {
            'source': 'user_execution_instruction_2026-09-18',
            'whole_process_tree_rss_cap_bytes': 1_537_500_000_000,
            'predicted_peak_is_diagnostic_only': True,
            'system_reserve_and_zero_swap_retained': True,
        }
    if user_material is not None:
        facts['campaign_authorization']['user_material'] = user_material
        if wavelength == 5.0:
            facts['campaign_authorization']['five_nm_material'] = user_material
        if wavelength == 2.0:
            facts['campaign_authorization']['two_nm_material'] = user_material
    return facts


def validate_native_case(config):
    """Validate only the campaign's frozen physical and numerical choices."""
    from .input_loader import InputError
    identity = config['solver']['preconditioner']
    discretization = config['discretization']
    geometry = config['geometry']
    wavelength, meshes, _, _, workflow = NATIVE_CASES[identity]
    time_limit_mode = NATIVE_TIME_LIMIT_MODES[identity]
    expected = {
        'solver': {'restart': 32, 'max_iterations': 2048},
        'execution': {'mpi_size': 1,
                      'time_limit_mode': time_limit_mode},
        'discretization': {'nedelec_degree': 6, 'assembly_backend': 'standard_full',
                               'mesh_cell_type': 'hexahedron', 'mesh_spacing_mode': 'boundary_fitted'},
        'incidence': {'wavelength_nm': wavelength, 'grazing_angle_deg': 1.0,
                          'azimuth_deg': 0.0, 'polarization': 's', 'electric_amplitude': 1.0},
        'boundary': {'use_floquet_x': True, 'use_floquet_y': True,
                         'dtn_order_policy': 'auto_propagating', 'use_pml': False},
    }
    expected['execution']['require_zero_swap'] = (
        False
        if identity == 'dual_condensed_balh_native_5nm_v3'
        or identity in V5_NATIVE_PROFILES
        else True
    )
    if identity in V5_NATIVE_PROFILES:
        expected['execution']['native_memory_policy'] = 'preferred_node1'
        expected['solver']['coarse_degree'] = V5_NATIVE_CASES[identity][2]
    for section, values in expected.items():
        for key, value in values.items():
            if config[section][key] != value:
                raise InputError(f'{identity} fixes {section}.{key}={value}')
    # None is the only unbounded representation; bounded native profiles
    # retain their explicit workflow deadline.
    if config['execution'].get('timeout_seconds') != workflow:
        raise InputError(f'{identity} fixes execution.timeout_seconds={workflow}')
    if config['discretization']['mesh_target_nm'] not in meshes:
        raise InputError(f'{identity} permits mesh_target_nm in {meshes}')
    frozen_mesh_keys = (
        'mesh_axis_cell_counts', 'mesh_axis_x_values', 'mesh_axis_y_values',
        'mesh_axis_z_values', 'mesh_axis_z_profile', 'mesh_plan_id',
        'mesh_plan_sha256',
    )
    if identity in V5_R13_PROFILES:
        from src.geometry.task39extra_v5_r13_mesh_plan import (
            MESH_PLAN_ID,
            MESH_PLAN_SHA256,
            validate_frozen_r13_axes,
        )

        if config['geometry'].get('cell_notch') is not None:
            raise InputError(f'{identity} is original-only; notch geometry is not authorized')
        expected_geometry = {
            'geometry_kind': 'rectangular_block_grating',
            'period_x_nm': 50.0, 'period_y_nm': 25.0,
            'z_min_nm': -10.0, 'z_max_nm': 130.0,
            'interface_z_nm': 0.0, 'air_height_nm': 130.0,
            'substrate_thickness_nm': 10.0,
            'grating_width_x_nm': 17.0, 'grating_width_y_nm': 25.0,
            'grating_height_nm': 120.0,
        }
        for key, value in expected_geometry.items():
            if geometry.get(key) != value:
                raise InputError(f'{identity} fixes geometry.{key}={value}')
        try:
            axes = validate_frozen_r13_axes(discretization)
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(str(exc)) from exc
        if discretization['mesh_plan_id'] != MESH_PLAN_ID or discretization['mesh_plan_sha256'] != MESH_PLAN_SHA256:
            raise InputError(f'{identity} requires the V21 frozen mesh-plan identity')
        if discretization.get('mesh_axis_z_profile') != 'v21_frozen_geometry_mesh_plan':
            raise InputError(f'{identity} requires the V21 frozen z-axis label')
        expected_endpoints = {
            'x': (0.0, config['geometry']['period_x_nm']),
            'y': (0.0, config['geometry']['period_y_nm']),
            'z': (config['geometry']['z_min_nm'], config['geometry']['z_max_nm']),
        }
        for axis, (low, high) in expected_endpoints.items():
            if axes[axis][0] != low or axes[axis][-1] != high:
                raise InputError(f'{identity} frozen {axis} endpoints differ from geometry')
        expected_output = {
            'reference_plane_z_nm': (10.0, 30.0, 60.0, 90.0, 110.0),
            'sample_count_x': 40, 'sample_count_y': 20,
            'diffraction_sample_count_x': 24,
            'diffraction_sample_count_y': 24,
            'top_probe_z_nm': 127.5, 'bottom_probe_z_nm': -7.5,
            'probe_fraction': 0.75,
            'diffraction_order_max_m': 2,
            'diffraction_order_max_n': 2,
        }
        for key, value in expected_output.items():
            actual = config['output'].get(key)
            if key == 'reference_plane_z_nm':
                actual = tuple(actual or ())
            if actual != value:
                raise InputError(f'{identity} fixes output.{key}={value}')
    elif identity in V5_NATIVE_PROFILES and any(
        discretization.get(key) is not None for key in frozen_mesh_keys
    ):
        raise InputError(
            f'{identity} retains ordinary boundary-fitted mesh identity; '
            'frozen R13 axes are not permitted'
        )
    if identity in V5_NATIVE_PROFILES and config['execution'].get('native_memory_policy') != 'preferred_node1':
        raise InputError(f'{identity} fixes native_memory_policy=preferred_node1')
    for key in ('n_substrate', 'n_grating'):
        if tuple(config['materials'][key]) != MATERIALS[wavelength]:
            raise InputError(f'{identity} fixes materials.{key}')
    user_material = USER_MATERIAL_METADATA.get(wavelength)
    if user_material is not None:
        for key in ('substrate_name', 'grating_name'):
            if config['materials'][key] != user_material['material']:
                raise InputError(f'{identity} fixes materials.{key}={user_material["material"]}')
    if wavelength != 13.5 and config['geometry'].get('cell_notch'):
        raise InputError('shortwave notch is outside this campaign')
