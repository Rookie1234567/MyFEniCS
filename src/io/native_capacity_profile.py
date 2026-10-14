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
V7_ANISO_N0_P4_PROFILE = 'dual_condensed_balh_native_0p7nm_aniso_n0_p4_full_v7'
V7_ANISO_N0_P4_PROFILES = frozenset({V7_ANISO_N0_P4_PROFILE})
V7_ANISO_N0_P6_DIRECT_PROFILE = (
    'dual_condensed_balh_native_0p7nm_aniso_n0_p6_direct_full_v1'
)
V7_ANISO_N0_P6_DIRECT_PROFILES = frozenset({V7_ANISO_N0_P6_DIRECT_PROFILE})
V7_ANISO_N0_PROFILES = (
    V7_ANISO_N0_P4_PROFILES | V7_ANISO_N0_P6_DIRECT_PROFILES
)
V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY = (
    'v7_p64_T_transpose_reference_v1'
)
V7_N0_PARENT_MODE_COUNT = 32060
V7_N0_PARENT_MODE_SHA256 = (
    '7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb'
)
V7_N0_ACTIVE_MODE_COUNT = 572
V7_N0_ACTIVE_MODE_SHA256 = (
    '946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b'
)
V7_RSS_HARD_LIMIT_BYTES = 1_800_000_000_000
# Separate identities keep all V5 inputs and policies immutable.
V6_BASE_PROFILES = {
    'dual_condensed_balh_native_13p5_p3_v6': 'dual_condensed_balh_native_13p5_q3_v5',
    'dual_condensed_balh_native_5nm_v6': 'dual_condensed_balh_native_5nm_v5',
    'dual_condensed_balh_native_2nm_h6_only_v6': 'dual_condensed_balh_native_2nm_v5',
    'dual_condensed_balh_native_2nm_pilot16_v6': 'dual_condensed_balh_native_2nm_v5',
    # Explicit opt-in p3 experiments retain the same V6 physical/material
    # contracts while selecting a degree-3 coarse operator.
    'dual_condensed_balh_native_5nm_p3_v6': 'dual_condensed_balh_native_5nm_v5',
    'dual_condensed_balh_native_2nm_p3_pilot16_v6': 'dual_condensed_balh_native_2nm_v5',
    'dual_condensed_balh_native_0p7nm_p3_pilot16_v6': 'dual_condensed_balh_native_2nm_v5',
    # This separately named route keeps the full 0.7 nm parent inventory for
    # q=160 while exposing only its n=0 operator rows.  It is not a full-DtN
    # profile and must never inherit the old 3904-mode 2 nm checker contract.
    'dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6': 'dual_condensed_balh_native_2nm_v5',
    # Full-solve V7 anisotropic N0 route, using the existing exact p4 operator.
    V7_ANISO_N0_P4_PROFILE: 'dual_condensed_balh_native_2nm_v5',
}
V6_0P7_N0_P3_PROFILES = frozenset(
    {'dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6'}
)
V6_0P7_P3_HP_OPTIN_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_0p7nm_p3_pilot16_v6',
        *V6_0P7_N0_P3_PROFILES,
    }
)
V6_NATIVE_PROFILES = frozenset(V6_BASE_PROFILES)
V6_P3_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_13p5_p3_v6',
        'dual_condensed_balh_native_5nm_p3_v6',
        'dual_condensed_balh_native_2nm_p3_pilot16_v6',
        'dual_condensed_balh_native_0p7nm_p3_pilot16_v6',
        *V6_0P7_N0_P3_PROFILES,
    }
)
V6_R13_ANCHOR_PROFILES = frozenset({'dual_condensed_balh_native_13p5_p3_v6'})
V6_PILOT16_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_2nm_pilot16_v6',
        'dual_condensed_balh_native_2nm_p3_pilot16_v6',
        'dual_condensed_balh_native_0p7nm_p3_pilot16_v6',
        *V6_0P7_N0_P3_PROFILES,
    }
)
V6_COARSE_DEGREES = {
    identity: 3 if identity in V6_P3_PROFILES else 4
    for identity in V6_NATIVE_PROFILES
}
V6_MATH_THREADS = 1  # Updated only after the bounded E3 comparison and clean freeze.
NATIVE_CASES.update(
    {
        identity: (wavelength, meshes, None, None, None)
        for identity, (wavelength, meshes, _) in V5_NATIVE_CASES.items()
    }
)
NATIVE_CASES.update({identity: NATIVE_CASES[base] for identity, base in V6_BASE_PROFILES.items()})
NATIVE_CASES['dual_condensed_balh_native_0p7nm_p3_pilot16_v6'] = (
    0.7, (0.7,), None, None, None
)
NATIVE_CASES['dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6'] = (
    0.7, (0.7,), None, None, None
)
NATIVE_CASES[V7_ANISO_N0_P4_PROFILE] = (0.7, (0.5,), None, None, None)
NATIVE_CASES[V7_ANISO_N0_P6_DIRECT_PROFILE] = (0.7, (0.5,), None, None, None)
NATIVE_PROFILES = tuple(NATIVE_CASES)
RETAINED_CONDENSED_PROFILE = 'dual_condensed_balh_native_5nm_v3'
V5_NATIVE_PROFILES = frozenset(V5_NATIVE_CASES)
SETUP_ONLY_5NM_PROFILE = 'dual_condensed_balh_native_5nm_v5'
SETUP_ONLY_5NM_INPUT_SHA256 = (
    '03a9992d576612335135fa22f25192f97754feb4a281e6c06ce29534e4095d36'
)
SETUP_ONLY_5NM_PHYSICAL_SHA256 = (
    '96b548e4cd7fbec7f5397d6be7fa22cf5f9e0faaaeb2f70ff95cf01f0f8af88d'
)


def setup_only_5nm_identity_errors(
    *, profile: str, method: str, input_sha256: str, physical_model_sha256: str
) -> list[str]:
    """Fail closed unless setup-only is bound to the reviewed 5 nm V5 input."""

    errors = []
    if profile != SETUP_ONLY_5NM_PROFILE:
        errors.append("setup-only is restricted to the V5 5 nm profile")
    if method != "full3d_iterative":
        errors.append("setup-only requires the full3d_iterative worker")
    if input_sha256 != SETUP_ONLY_5NM_INPUT_SHA256:
        errors.append("setup-only input SHA does not match the reviewed 5 nm input")
    if physical_model_sha256 != SETUP_ONLY_5NM_PHYSICAL_SHA256:
        errors.append("setup-only physical SHA does not match the reviewed model")
    return errors


V5_R13_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_13p5_q4_v5',
        'dual_condensed_balh_native_13p5_q3_v5',
    }
)
V5_ROUNDED_TENSOR_REPRESENTATIVE_PROFILES = frozenset(
    {
        'dual_condensed_balh_native_5nm_v5',
        'dual_condensed_balh_native_2nm_v5',
    }
)
RETAINED_CONDENSED_PROFILES = frozenset(
    {RETAINED_CONDENSED_PROFILE, *V5_NATIVE_PROFILES, *V6_NATIVE_PROFILES}
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
    {
        identity: 'none'
        for identity in (
            *V5_NATIVE_PROFILES,
            *V6_NATIVE_PROFILES,
            *V7_ANISO_N0_P6_DIRECT_PROFILES,
        )
    }
)
NATIVE_NONE_TIME_PROFILES = frozenset(
    identity for identity, mode in NATIVE_TIME_LIMIT_MODES.items() if mode == 'none'
)
MATERIALS = {
    13.5: (0.999002304859, 0.00182649365),
    5.0: (0.99396854453, 0.00435380777),
    3.0: (0.99735217495, 0.000883207249),
    2.0: (0.99880148307, 0.000213688647),
    0.7: (0.9998851259969171, 4.325285938225562e-06),
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
    0.7: {
        'material': 'Si / silicon',
        'density_g_cm3': 2.33,
        'delta': 0.00011487400308289077,
        'beta': 4.325285938225562e-06,
        'authority': (
            'derived by linear interpolation of the task R48 Henke table '
            'and the recorded project wavelength conversion; material accuracy unqualified'
        ),
        'source_sha256': '3e947de11141efbba8b0df1ece4d75f56c72075d060cc2b457cf21be1400d884',
        'interpretation': 'complex refractive index n=1-delta+i*beta; epsilon=n*n',
    },
}


def _apply_v7_aniso_n0_p4_facts(facts: dict) -> None:
    """Apply the explicit full-solve V7 route without inheriting N0 pilot/store policy."""

    rss_cap = V7_RSS_HARD_LIMIT_BYTES
    mode_selection = {
        'schema': 'task39extra.dtn-mode-selection.v1',
        'policy': 'n_equals_zero_both_ports_both_polarizations',
        'parent_mode_count': V7_N0_PARENT_MODE_COUNT,
        'parent_mode_sha256': V7_N0_PARENT_MODE_SHA256,
        'active_mode_count': V7_N0_ACTIVE_MODE_COUNT,
        'expected_active_mode_sha256': V7_N0_ACTIVE_MODE_SHA256,
        'm_range_in_each_side_polarization': [-142, 0],
        'quadrature_inventory': 'full_parent_modes',
        'operator_scope': 'n0_filtered_dtn_not_full_dtn',
    }
    facts.update(
        identity=V7_ANISO_N0_P4_PROFILE,
        execution_mode='full_solve',
        wavelength_nm=0.7,
        allowed_mesh_targets_nm=[0.5],
        operator_scope='n0_filtered_dtn_not_full_dtn',
        functional_store_policy={
            'enabled': False,
            'parent_import': False,
            'cross_mesh_fe_reuse': 'forbidden',
            'configuration': 'not_used',
            'fresh_n0_inventory_directory': 'runtime_artifact_directory',
        },
    )
    facts['outer'].update(
        ksp_type='fgmres', restart=32, max_iterations=2048,
        initial_guess='zero', planned_stop_iteration=None,
    )
    facts['outer']['screen']['enabled'] = False
    facts['resources'].update(
        absolute_cap_bytes=rss_cap,
        planning_cap_bytes=rss_cap,
        rss_hard_limit_bytes=rss_cap,
        rss_warning_bytes=1_170_000_000_000,
        resource_stop_policy='measured_tree_rss_only_v3',
        swap_policy='observe_only',
        global_swap_delta_policy='observe_only',
        stop_on_global_swap=False,
        prediction_admission_policy='record_only',
        memavailable_runtime_policy='observe_and_warn_only',
        require_zero_swap=False,
        pss_sampling_policy='disabled_by_profile',
        pss_interval_seconds=None,
        uss_sampling_policy='disabled_by_profile',
        uss_interval_seconds=None,
        concurrent_neighbor_authorized=False,
    )
    facts['campaign_authorization']['source'] = (
        'Review V7 urgent anisotropic full-solve N0 p4 route'
    )
    facts['campaign_authorization']['execution_mode'] = 'full_solve'
    facts['campaign_authorization']['resource_policy'] = {
        'name': 'measured_tree_rss_only_v3',
        'rss_hard_limit_bytes': rss_cap,
        'rss_warning_bytes': 1_170_000_000_000,
        'swap': 'observe_only',
        'prediction': 'record_only',
        'memavailable': 'observe_and_warn_only',
        'pss_uss_sampling': 'disabled',
        'icntl23': 0,
    }
    facts['campaign_authorization']['memory_override'] = {
        'source': 'Review_V7_user_authorized_0p7nm_full_solve',
        'whole_process_tree_rss_cap_bytes': rss_cap,
        'parent_and_worker_cap_bytes': rss_cap,
        'pss_uss_sampling': 'disabled',
        'swap_prediction_eta': 'observe_only',
        'time_limit_mode': 'none',
    }
    facts['campaign_authorization']['user_material'] = dict(
        USER_MATERIAL_METADATA[0.7]
    )
    facts['campaign_authorization'].pop('two_nm_material', None)
    facts['campaign_authorization'].pop('five_nm_material', None)
    facts['native_execution'].update(
        supervisor_cpu=9,
        worker_cpu=24,
        worker_cpus=[24],
        mpi_size=1,
        math_threads=1,
        memory_policy='interleave_nodes0_1',
        native_memory_policy='interleave_nodes0_1',
    )
    facts['component_options'].update(
        reuse_dtn_surface_vector=True,
        reuse_dtn_surface_geometry_cache=True,
        dtn_surface_geometry_cache_limit_bytes=4 * 1024**3,
        dtn_surface_weighted_moment_contraction=(
            'q160_weighted_moment_x_then_y_v1'
        ),
        dtn_surface_prepare_trace_contraction=True,
        dtn_component_cache_last_use_release=True,
        dtn_mode_progress_interval=1024,
        dtn_surface_assembly_backend_by_degree={
            'p6': 'q160_affine_hex_pointwise_weighted_legendre_component_pair_v1',
            'p4': 'native_ffcx',
        },
        dtn_mode_selection=mode_selection,
        same_mesh_coefficient_map_policy=(
            V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
        ),
    )
    facts['component_options'].pop('dtn_surface_assembly_backend', None)
    coarse_operator = {
        'degree': 4,
        'name': 'A4_n0',
        'matrix': 'exact_per_cell_static_condensation_plus_selected_ports',
        'inverse': 'one_exact_global_MUMPS_factor',
        'relative_residual_limit': 1.0e-10,
        'maximum_extra_same_factor_refinements': 2,
        'operator_scope': 'n0_filtered_dtn_not_full_dtn',
        'same_mesh_coefficient_map_policy': (
            V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
        ),
    }
    facts['coarse_operator'] = dict(coarse_operator)
    facts['backend']['coarse_operator'] = dict(coarse_operator)
    facts['backend'].update(
        original_a4='fused_original_volume_plus_complete_N0_DtN',
        coarse_operator=dict(coarse_operator),
        same_mesh_coefficient_map_policy=(
            V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
        ),
    )
    facts['backend'].pop('original_a3', None)
    facts['backend'].pop('p4_compatibility_alias', None)
    facts['retained_condensed_v20'].update(
        coarse_degree=4,
        coarse_operator=dict(coarse_operator),
        same_mesh_trace_map_policy='basix_full_cell_interpolation_v1',
        same_mesh_coefficient_map_policy=(
            V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
        ),
        p4_internal_names_are_compatibility_aliases=False,
        functional_store_policy='disabled_no_functional_store_config',
        fresh_n0_inventory_directory='runtime_artifact_directory',
        cross_mesh_fe_reuse=False,
    )
    facts['condensed_route'].update(
        coarse_degree=4,
        coarse_operator='A4_n0',
        coarse='assembly_time_condensed_exact_A4_inverse',
        p4='one exact global MUMPS factor on the selected N0 operator',
        coarse_factor='one_exact_global_MUMPS_factor',
        coarse_relative_residual_limit=1.0e-10,
        coarse_max_refinements=2,
        operator_scope='n0_filtered_dtn_not_full_dtn',
        cross_mesh_fe_reuse=False,
        same_mesh_coefficient_map_policy=(
            V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
        ),
    )


def native_profile_facts(identity):
    from .physical_balanced_profile import balanced_profile_facts
    if identity in V7_ANISO_N0_P6_DIRECT_PROFILES:
        # Reuse only the immutable V7 physical/material/output and resource
        # facts.  This is a separate direct p6 route: no p4 operator or outer
        # Krylov/PC identity is exposed by these facts.
        facts = native_profile_facts(V7_ANISO_N0_P4_PROFILE)
        facts.update(
            identity=identity,
            execution_mode='full_solve',
            formal_runner='src.runners.p6_condensed_direct',
            route='V7_P6_CONDENSED_DIRECT_N0',
        )
        facts['outer'].pop('ksp_type', None)
        facts['outer'].pop('restart', None)
        facts['outer'].pop('max_iterations', None)
        facts['outer'].pop('planned_stop_iteration', None)
        facts['outer'].update(
            route='P6_CONDENSED_DIRECT',
            initial_guess='not_applicable_direct_solve',
            screen={'enabled': False, 'policy': 'not_applicable'},
        )
        facts['component_options'].pop('same_mesh_coefficient_map_policy', None)
        facts['component_options'].update(
            functional_store_policy='disabled_no_functional_store_config',
            cross_mesh_fe_reuse=False,
        )
        facts['component_options']['dtn_surface_assembly_backend_by_degree'] = {
            'p6': (
                'q160_affine_hex_pointwise_weighted_legendre_component_pair_v1'
            )
        }
        facts['backend'] = {
            'p6': 'exact_p6_local_static_condensation_materialized_AIJ',
            'global_matrix': 'one_exact_[S_V,Bhat;-Dhat,Hhat]_matrix',
            'factor': 'one_MUMPS_symbolic_then_numeric_on_the_same_matrix',
            'rhs': 'P6CellCondensedAction.reduce_rhs',
            'recovery': 'P6CellCondensedAction.recover_storage',
            'independent_residual': 'original_full_p6_A6_n0_action',
            'p4_operator': 'NOT_BUILT',
            'p4_factor': 'NOT_BUILT',
            'outer_ksp': 'NOT_BUILT',
            'full_dtn_status': 'FULL_DTN_NOT_VERIFIED',
        }
        facts.pop('coarse_operator', None)
        facts.pop('retained_condensed_v20', None)
        facts['condensed_route'] = {
            'name': 'v7_p6_exact_local_condensation_direct_n0',
            'degree': 6,
            'rows': 9_281_372,
            'matrix_blocks': '[S_V,Bhat;-Dhat,Hhat]',
            'local_elimination': 'exact_existing_per_cell_interior_factorization',
            'ports': V7_N0_ACTIVE_MODE_COUNT,
            'matrix_lifecycle': (
                'one_materialized_PETSc_AIJ_through_symbolic_numeric_solve'
            ),
            'cross_mesh_reuse': False,
            'functional_store': False,
        }
        facts['campaign_authorization']['source'] = (
            'user-authorized V7 p6 condensed direct full solve'
        )
        facts['campaign_authorization']['execution_mode'] = 'full_solve'
        facts['campaign_authorization']['direct_route'] = {
            'degree': 6,
            'active_mode_count': V7_N0_ACTIVE_MODE_COUNT,
            'parent_mode_count': V7_N0_PARENT_MODE_COUNT,
            'quadrature_inventory': 'parent_q160',
            'same_factor_lifecycle': ['symbolic', 'numeric', 'solve'],
            'p4_and_outer_ksp': 'not_built',
        }
        return facts
    if identity in V6_NATIVE_PROFILES:
        facts = native_profile_facts(V6_BASE_PROFILES[identity])
        h6_only = identity == 'dual_condensed_balh_native_2nm_h6_only_v6'
        pilot = identity in V6_PILOT16_PROFILES
        coarse_degree = V6_COARSE_DEGREES[identity]
        threads = 1 if h6_only else V6_MATH_THREADS
        facts.update(identity=identity, execution_mode=('h6_only' if h6_only else
                     'pilot_16' if pilot else 'full_solve'))
        facts['resources'].update(pss_sampling_policy='disabled_by_profile',
            pss_interval_seconds=None, uss_sampling_policy='disabled_by_profile',
            concurrent_neighbor_authorized=False)
        facts['native_execution'].update(math_threads=threads,
            worker_cpus=list(range(24, 24+threads)), memory_policy='interleave_nodes0_1',
            native_memory_policy='interleave_nodes0_1')
        facts['component_options'] = dict(reference_metric_diagonal=True,
            direct_h6_backend=True, h6_natural_order=True,
            fused_a6=True, fast_complete_a4=True, blocked_gram=True,
            shared_readonly_geometry=True, shared_contractions=False,
            combine_real_imag_transforms=False, continuous_projection_matmul=False,
            reuse_projection_work=False)
        if identity in V6_0P7_P3_HP_OPTIN_PROFILES:
            facts['wavelength_nm'] = 0.7
            facts['allowed_mesh_targets_nm'] = [0.7]
            rss_hard_limit_bytes = 1_950_000_000_000
            facts['resources'].update(
                absolute_cap_bytes=rss_hard_limit_bytes,
                planning_cap_bytes=rss_hard_limit_bytes,
                rss_hard_limit_bytes=rss_hard_limit_bytes,
            )
            facts['campaign_authorization']['resource_policy'].update(
                rss_hard_limit_bytes=rss_hard_limit_bytes,
            )
            facts['campaign_authorization']['memory_override'] = {
                'source': 'user_authorized_h0p7_followup_resource_policy',
                'whole_process_tree_rss_cap_bytes': rss_hard_limit_bytes,
                'parent_and_worker_cap_bytes': rss_hard_limit_bytes,
                'pss_uss_sampling': 'disabled',
                'swap_prediction_eta': 'observe_only',
                'time_limit_mode': 'none',
            }
            facts['component_options'].update(
                exact_carrier_diagonal_hp=True,
                omit_structural_zero_hlocal=True,
                reuse_dtn_surface_vector=True,
                reuse_dtn_surface_geometry_cache=True,
                dtn_surface_geometry_cache_limit_bytes=4 * 1024**3,
                dtn_surface_weighted_moment_contraction=(
                    'q160_weighted_moment_x_then_y_v1'
                ),
                dtn_surface_prepare_trace_contraction=True,
                dtn_component_cache_last_use_release=True,
                dtn_mode_progress_interval=1024,
                dtn_surface_assembly_backend_by_degree={
                    'p6': (
                        'q160_affine_hex_pointwise_weighted_legendre_component_pair_v1'
                    ),
                    'p3': 'native_ffcx',
                },
            )
            facts['component_options'].pop('dtn_surface_assembly_backend', None)
            facts['condensed_route'] = dict(
                facts['condensed_route'],
                hp_storage_policy='exact_carrier_diagonal',
                hlocal_omission_policy='only_omitted_H_is_structural_zero',
            )
            if identity in V6_0P7_N0_P3_PROFILES:
                facts['component_options']['dtn_mode_selection'] = {
                    'schema': 'task39extra.dtn-mode-selection.v1',
                    'policy': 'n_equals_zero_both_ports_both_polarizations',
                    'parent_mode_count': 32060,
                    'parent_mode_sha256': (
                        '7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb'
                    ),
                    'active_mode_count': 572,
                    'expected_active_mode_sha256': (
                        '946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b'
                    ),
                    'm_range_in_each_side_polarization': [-142, 0],
                    'quadrature_inventory': 'full_parent_modes',
                    'operator_scope': 'n0_filtered_dtn_not_full_dtn',
                }
            material_facts = USER_MATERIAL_METADATA[0.7]
            facts['campaign_authorization']['user_material'] = dict(material_facts)
            facts['campaign_authorization'].pop('two_nm_material', None)
            facts['campaign_authorization'].pop('five_nm_material', None)
        facts['outer']['planned_stop_iteration'] = 16 if pilot else None
        facts['outer']['screen']['enabled'] = False
        facts['campaign_authorization'].update(source=(
            'user-authorized p6/p3 intermediate coarse exploration'
            if coarse_degree == 3 else 'Review V6 exact p4 speed batch'),
            threads_per_process=threads, execution_mode=facts['execution_mode'],
            exclusive_heavy_window_required=True, low_memory_p4_inverse_trials=0)
        facts['backend'].update(
            h6='reference_metric_direct_sum_factorized_natural',
            original_a4='fused_original_volume_plus_complete_DtN',
            local_tensor='blocked_gram_original_FFCx_rules',
        )
        if identity in V7_ANISO_N0_P4_PROFILES:
            _apply_v7_aniso_n0_p4_facts(facts)
        if identity in V6_P3_PROFILES:
            coarse_operator = {
                'degree': coarse_degree,
                'name': f'A{coarse_degree}',
                'same_mesh_trace_map_policy': (
                    'v6_p3_canonical_shared_trace_v1'
                ),
                'matrix': 'exact_per_cell_static_condensation_plus_ports',
                'inverse': 'one_exact_global_MUMPS_factor',
                'relative_residual_limit': 1.0e-10,
                'maximum_extra_same_factor_refinements': 2,
            }
            facts['coarse_operator'] = dict(coarse_operator)
            facts['backend']['coarse_operator'] = dict(coarse_operator)
            facts['retained_condensed_v20'] = dict(
                facts['retained_condensed_v20'],
                coarse_degree=coarse_degree,
                coarse_operator=dict(coarse_operator),
                same_mesh_trace_map_policy=(
                    'v6_p3_canonical_shared_trace_v1'
                ),
                p4_internal_names_are_compatibility_aliases=True,
                factory_qualification=(
                    'p3 profile opt-in; bounded FE/MPC component qualification required'
                ),
            )
            facts['backend']['original_a3'] = (
                'fused_original_volume_plus_complete_DtN'
            )
            facts['backend']['coarse_transfer'] = (
                'canonical_shared_edge_and_quadrilateral_face_trace_rows; '
                'Basix cell-interior rows retained; V6 P3 profile opt-in'
            )
            facts['backend'].pop('original_a4')
            facts['backend']['p4_compatibility_alias'] = (
                'legacy p4_* storage/helper names only; actual operator is A3'
            )
            facts['condensed_route'].update(
                coarse_degree=coarse_degree,
                coarse_operator=f'A{coarse_degree}',
                same_mesh_trace_map_policy=(
                    'v6_p3_canonical_shared_trace_v1'
                ),
                coarse='assembly_time_condensed_exact_A3_inverse',
                p4='compatibility alias to the selected exact A3 inverse',
                coarse_factor='one_exact_global_MUMPS_factor',
                coarse_relative_residual_limit=1.0e-10,
                coarse_max_refinements=2,
                p4_internal_names_are_compatibility_aliases=True,
            )
            facts['component_options']['same_mesh_trace_map_policy'] = (
                'v6_p3_canonical_shared_trace_v1'
            )
        if identity in V6_R13_ANCHOR_PROFILES:
            facts['condensed_route']['geometry_identity_policy'] = (
                'rounded_12_representative'
            )
        return facts
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
            'geometry_identity_policy': (
                'rounded_12_representative'
                if identity in V5_ROUNDED_TENSOR_REPRESENTATIVE_PROFILES
                else 'raw_unrounded'
            ),
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


def native_capacity_profile_identity(method, solver):
    """Return the explicit native profile for iterative or direct V7 routes."""

    solver = solver or {}
    if (
        str(method) == 'full3d_direct'
        and solver.get('native_capacity_profile')
        in V7_ANISO_N0_P6_DIRECT_PROFILES
    ):
        return solver['native_capacity_profile']
    return solver.get('preconditioner')


def validate_same_mesh_coefficient_map_profile_binding(
    profile_identity,
    coarse_degree,
    component_options,
):
    """Validate the explicit V7/coarse-P4/profile metadata policy binding."""

    options = dict(component_options or {})
    selected = options.get('same_mesh_coefficient_map_policy')
    if profile_identity not in V7_ANISO_N0_P4_PROFILES:
        if selected is not None:
            raise ValueError(
                'same-mesh coefficient map override is restricted to the explicit V7 profile'
            )
        return None

    if int(coarse_degree) != 4:
        raise ValueError('V7 coefficient map override requires coarse degree 4')
    facts = native_profile_facts(profile_identity)
    expected = V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
    sites = {
        'component_options': facts['component_options'].get(
            'same_mesh_coefficient_map_policy'
        ),
        'coarse_operator': facts['coarse_operator'].get(
            'same_mesh_coefficient_map_policy'
        ),
        'backend': facts['backend'].get('same_mesh_coefficient_map_policy'),
        'backend.coarse_operator': facts['backend']['coarse_operator'].get(
            'same_mesh_coefficient_map_policy'
        ),
        'retained_condensed_v20': facts['retained_condensed_v20'].get(
            'same_mesh_coefficient_map_policy'
        ),
        'condensed_route': facts['condensed_route'].get(
            'same_mesh_coefficient_map_policy'
        ),
    }
    if any(value != expected for value in sites.values()):
        raise RuntimeError(
            'V7 coefficient map metadata is inconsistent: '
            + ', '.join(f'{key}={value!r}' for key, value in sites.items())
        )
    if selected != expected:
        raise ValueError(
            'V7 component_options must explicitly select the resolved '
            'P64 coefficient map policy'
        )
    if facts['retained_condensed_v20'].get('same_mesh_trace_map_policy') != (
        'basix_full_cell_interpolation_v1'
    ):
        raise RuntimeError('V7 coefficient policy must retain the qualified trace map')
    return expected


def _validate_v7_aniso_n0_p4_case(config) -> None:
    """Fail closed on the one reviewed V7 mesh, N0 operator, and full-solve input."""
    from .input_loader import InputError

    def require(section, key, expected):
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f'{V7_ANISO_N0_P4_PROFILE} fixes {section}.{key}={expected!r}; '
                f'got {actual!r}'
            )

    geometry_expected = {
        'geometry_kind': 'rectangular_block_grating',
        'period_x_nm': 50.0,
        'period_y_nm': 25.0,
        'z_min_nm': -10.0,
        'z_max_nm': 130.0,
        'interface_z_nm': 0.0,
        'air_height_nm': 130.0,
        'substrate_thickness_nm': 10.0,
        'grating_width_x_nm': 17.0,
        'grating_width_y_nm': 25.0,
        'grating_height_nm': 120.0,
    }
    for key, value in geometry_expected.items():
        require('geometry', key, value)
    require('geometry', 'cell_notch', None)

    for section, expected in (
        ('materials', {
            'n_air': (1.0, 0.0),
            'mu_r': (1.0, 0.0),
            'substrate_name': USER_MATERIAL_METADATA[0.7]['material'],
            'grating_name': USER_MATERIAL_METADATA[0.7]['material'],
            'n_substrate': MATERIALS[0.7],
            'n_grating': MATERIALS[0.7],
        }),
        ('incidence', {
            'wavelength_nm': 0.7,
            'grazing_angle_deg': 1.0,
            'azimuth_deg': 0.0,
            'polarization': 's',
            'electric_amplitude': 1.0,
        }),
        ('discretization', {
            'nedelec_degree': 6,
            'visualization_degree': 6,
            'mesh_target_nm': 0.5,
            'mesh_cell_type': 'hexahedron',
            'mesh_spacing_mode': 'boundary_fitted',
            'assembly_backend': 'standard_full',
            'floquet_constraint_mode': 'auto',
        }),
        ('boundary', {
            'use_floquet_x': True,
            'use_floquet_y': True,
            'vertical_boundary': 'dtn_port',
            'scattering_background': 'layered',
            'dtn_order_policy': 'auto_propagating',
            'dtn_assembly': 'auxiliary',
            'use_pml': False,
        }),
        ('method', {'kind': 'full3d_iterative'}),
        ('solver', {
            'linear_solver': 'iterative',
            'ksp_type': 'fgmres',
            'preconditioner': V7_ANISO_N0_P4_PROFILE,
            'restart': 32,
            'max_iterations': 2048,
            'coarse_degree': 4,
        }),
        ('execution', {
            'mpi_size': 1,
            'time_limit_mode': 'none',
            'timeout_seconds': None,
            'require_zero_swap': False,
            'native_memory_policy': 'interleave_nodes0_1',
        }),
    ):
        for key, value in expected.items():
            require(section, key, value)

    discretization = config['discretization']
    if tuple(discretization.get('mesh_axis_cell_counts') or ()) != (100, 2, 234):
        raise InputError(
            f'{V7_ANISO_N0_P4_PROFILE} fixes mesh_axis_cell_counts=[100, 2, 234]'
        )
    for key in (
        'mesh_axis_x_values', 'mesh_axis_y_values', 'mesh_axis_z_values',
        'mesh_axis_z_profile', 'mesh_plan_id', 'mesh_plan_sha256',
    ):
        if discretization.get(key) is not None:
            raise InputError(
                f'{V7_ANISO_N0_P4_PROFILE} derives axes from the exact count plan; '
                f'{key} must be omitted'
            )

    execution = config['execution']
    required_gib = V7_RSS_HARD_LIMIT_BYTES / 2**30
    if execution.get('warning_memory_gib') != 1_170_000_000_000 / 2**30:
        raise InputError(f'{V7_ANISO_N0_P4_PROFILE} fixes the 1.17e12-byte warning level')
    for key in ('terminate_memory_gib', 'memory_limit_gb'):
        if execution.get(key) != required_gib:
            raise InputError(
                f'{V7_ANISO_N0_P4_PROFILE} fixes {key} to the '
                f'{V7_RSS_HARD_LIMIT_BYTES}-byte RSS cap'
            )

    output_expected = {
        'export_fields': True,
        'export_diffraction_orders': True,
        'export_canonical_vectors': True,
        'export_modal_amplitudes': True,
        'export_reference_planes': True,
        'reference_plane_z_nm': (10.0, 30.0, 60.0, 90.0, 110.0),
        'sample_count_x': 40,
        'diffraction_sample_count_x': 24,
        'diffraction_sample_count_y': 24,
        'diffraction_order_max_m': 142,
        'diffraction_order_max_n': 0,
    }
    for key, value in output_expected.items():
        require('output', key, value)
    if config.get('output', {}).get('sample_count_y', 0) < 4:
        raise InputError(
            f'{V7_ANISO_N0_P4_PROFILE} requires at least four full-3D reference y samples'
        )


def validate_native_case(config):
    """Validate only the campaign's frozen physical and numerical choices."""
    from .input_loader import InputError
    identity = native_capacity_profile_identity(
        config.get('method', {}).get('kind'), config['solver']
    )
    if identity in V7_ANISO_N0_P6_DIRECT_PROFILES:
        if config.get('method', {}).get('kind') != 'full3d_direct':
            raise InputError(f'{identity} is restricted to full3d_direct')
        solver = config['solver']
        if solver.get('linear_solver') != 'direct':
            raise InputError(f'{identity} requires solver.linear_solver=direct')
        if solver.get('direct_solver_profile', 'default') != 'default':
            raise InputError(f'{identity} uses the qualified default MUMPS controls')
        if any(
            key in solver
            for key in ('preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree')
        ):
            raise InputError(
                f'{identity} does not accept a P4/iterative/coarse solver route'
            )
        from copy import deepcopy

        v7_physical = deepcopy(config)
        v7_physical['method']['kind'] = 'full3d_iterative'
        v7_solver = v7_physical['solver']
        v7_solver.update(
            linear_solver='iterative',
            ksp_type='fgmres',
            preconditioner=V7_ANISO_N0_P4_PROFILE,
            restart=32,
            max_iterations=2048,
            coarse_degree=4,
        )
        v7_solver.pop('native_capacity_profile', None)
        _validate_v7_aniso_n0_p4_case(v7_physical)
        return
    if identity in V7_ANISO_N0_P4_PROFILES:
        _validate_v7_aniso_n0_p4_case(config)
        return
    if identity in V6_NATIVE_PROFILES:
        from copy import deepcopy
        if config['execution'].get('native_memory_policy') != 'interleave_nodes0_1':
            raise InputError(f'{identity} fixes native_memory_policy=interleave_nodes0_1')
        expected_degree = V6_COARSE_DEGREES[identity]
        if int(config['solver'].get('coarse_degree', -1)) != expected_degree:
            raise InputError(
                f'{identity} fixes solver.coarse_degree={expected_degree}'
            )
        if identity in V6_0P7_P3_HP_OPTIN_PROFILES:
            # Validate the unchanged geometry/runner contract through the
            # qualified 2 nm V5 shape, then check this profile's distinct
            # wavelength, material interpolation, and boundary-fitted target.
            legacy = deepcopy(config)
            legacy['solver']['preconditioner'] = V6_BASE_PROFILES[identity]
            legacy['solver']['coarse_degree'] = V5_NATIVE_CASES[
                V6_BASE_PROFILES[identity]
            ][2]
            legacy['execution']['native_memory_policy'] = 'preferred_node1'
            legacy['incidence']['wavelength_nm'] = 2.0
            legacy['discretization']['mesh_target_nm'] = 1.5
            legacy['materials']['n_substrate'] = list(MATERIALS[2.0])
            legacy['materials']['n_grating'] = list(MATERIALS[2.0])
            validate_native_case(legacy)
            if config['incidence'].get('wavelength_nm') != 0.7:
                raise InputError(f'{identity} fixes wavelength_nm=0.7')
            if config['discretization'].get('mesh_target_nm') != 0.7:
                raise InputError(f'{identity} fixes mesh_target_nm=0.7')
            for key in ('n_substrate', 'n_grating'):
                if tuple(config['materials'][key]) != MATERIALS[0.7]:
                    raise InputError(f'{identity} fixes materials.{key}')
            for key in ('substrate_name', 'grating_name'):
                if config['materials'].get(key) != USER_MATERIAL_METADATA[0.7]['material']:
                    raise InputError(
                        f'{identity} fixes materials.{key}='
                        f"{USER_MATERIAL_METADATA[0.7]['material']}"
                    )
            if config['solver'].get('ksp_type') != 'fgmres':
                raise InputError(f'{identity} fixes solver.ksp_type=fgmres')
            if config['execution'].get('timeout_seconds') is not None:
                raise InputError(f'{identity} fixes execution.timeout_seconds=None')
            if identity in V6_0P7_N0_P3_PROFILES:
                if config['solver'].get('restart') != 32 or config['solver'].get('max_iterations') != 2048:
                    raise InputError(f'{identity} fixes restart=32 and max_iterations=2048')
                if config['output'].get('export_all_port_modes', False):
                    raise InputError(
                        f'{identity} does not claim or export a full-DtN mode result'
                    )
            return
        legacy = deepcopy(config)
        legacy['solver']['preconditioner'] = V6_BASE_PROFILES[identity]
        # Validate the inherited V5 physical campaign independently of the
        # explicit V6 coarse-degree identity.  The base profile is a frozen
        # physical validator and retains its original q4/q3 setting.
        legacy['solver']['coarse_degree'] = V5_NATIVE_CASES[
            V6_BASE_PROFILES[identity]
        ][2]
        legacy['execution']['native_memory_policy'] = 'preferred_node1'
        validate_native_case(legacy)
        return
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
