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
}
NATIVE_PROFILES = tuple(NATIVE_CASES)
NATIVE_TIME_LIMIT_MODES = {
    'balanced_h6_p4_native_13p5': 'bounded',
    'balanced_h6_p4_native_5nm': 'none',
    'balanced_h6_p4_native_3nm': 'bounded',
    'balanced_h6_p4_native_2nm': 'none',
}
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
    wavelength, meshes, _, _, workflow = NATIVE_CASES[identity]
    time_limit_mode = NATIVE_TIME_LIMIT_MODES[identity]
    expected = {
        'solver': {'restart': 32, 'max_iterations': 2048},
        'execution': {'mpi_size': 1, 'require_zero_swap': True,
                      'time_limit_mode': time_limit_mode},
        'discretization': {'nedelec_degree': 6, 'assembly_backend': 'standard_full',
                               'mesh_cell_type': 'hexahedron', 'mesh_spacing_mode': 'boundary_fitted'},
        'incidence': {'wavelength_nm': wavelength, 'grazing_angle_deg': 1.0,
                          'azimuth_deg': 0.0, 'polarization': 's', 'electric_amplitude': 1.0},
        'boundary': {'use_floquet_x': True, 'use_floquet_y': True,
                         'dtn_order_policy': 'auto_propagating', 'use_pml': False},
    }
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
