"""Opt-in workstation sizes and budgets; the numerical method is V5 BAL_H."""

NATIVE_CASES = {
    'balanced_h6_p4_native_13p5': (13.5, (10.0,), 1800, 14400, 21600),
    'balanced_h6_p4_native_5nm': (5.0, (4.0, 3.0), 10800, 86400, 129600),
    'balanced_h6_p4_native_3nm': (3.0, (2.5, 2.0), 21600, 172800, 259200),
    'balanced_h6_p4_native_2nm': (2.0, (1.5, 1.0), 21600, 259200, 345600),
}
NATIVE_PROFILES = tuple(NATIVE_CASES)
MATERIALS = {
    13.5: (0.999002304859, 0.00182649365),
    5.0: (0.99396854453, 0.00435380777),
    3.0: (0.99735217495, 0.000883207249),
    2.0: (0.99880148307, 0.000213688647),
}


def native_profile_facts(identity):
    from .physical_balanced_profile import balanced_profile_facts
    wavelength, meshes, screen, solve, workflow = NATIVE_CASES[identity]
    facts = balanced_profile_facts('balanced_h6_p4_v5')
    facts.update(identity=identity, native_capacity=True,
                 wavelength_nm=wavelength, allowed_mesh_targets_nm=list(meshes))
    facts['outer']['screen']['solve_seconds'] = screen
    facts['resources'].update(
        solve_seconds=solve, workflow_seconds=workflow, batch_limit_seconds=864000,
        absolute_cap_bytes=32*1024**3 if wavelength == 13.5 else int(1.60*1024**4),
        reserve_min_bytes=256*1024**3,
        planning_cap_bytes=24*1024**3 if wavelength == 13.5 else int(1.50*1024**4),
        concurrent_neighbor_authorized=True,
    )
    return facts


def validate_native_case(config):
    """Validate only the campaign's frozen physical and numerical choices."""
    from .input_loader import InputError
    identity = config['solver']['preconditioner']
    wavelength, meshes, _, _, workflow = NATIVE_CASES[identity]
    expected = {
        'solver': {'restart': 32, 'max_iterations': 2048},
        'execution': {'mpi_size': 1, 'timeout_seconds': workflow, 'require_zero_swap': True},
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
    if config['discretization']['mesh_target_nm'] not in meshes:
        raise InputError(f'{identity} permits mesh_target_nm in {meshes}')
    for key in ('n_substrate', 'n_grating'):
        if tuple(config['materials'][key]) != MATERIALS[wavelength]:
            raise InputError(f'{identity} fixes materials.{key}')
    if wavelength != 13.5 and config['geometry'].get('cell_notch'):
        raise InputError('shortwave notch is outside this campaign')
