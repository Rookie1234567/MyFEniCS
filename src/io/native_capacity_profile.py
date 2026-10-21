"""Opt-in workstation sizes and Task40 direct-route identities."""

import math

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
V7_D_ANISO_N0_P6_DIRECT_PROFILE = (
    'dual_condensed_balh_native_0p7nm_aniso_n0_p6_direct_grid_d_v1'
)
V7_ANISO_N0_P6_DIRECT_PROFILES = frozenset(
    {V7_ANISO_N0_P6_DIRECT_PROFILE, V7_D_ANISO_N0_P6_DIRECT_PROFILE}
)
V6_F5_P6_DIRECT_FULL600_PROFILE = (
    'task39extra_v6_f5_p6_condensed_direct_full600_v1'
)
V6_F5_P6_DIRECT_N0_PROFILE = 'task39extra_v6_f5_p6_condensed_direct_n0_v1'
V6_F5_P6_DIRECT_PROFILES = frozenset(
    {V6_F5_P6_DIRECT_FULL600_PROFILE, V6_F5_P6_DIRECT_N0_PROFILE}
)
DISPERSION_FLAT_P6_PROFILE = "task39extra_dispersion_flat_0p7_p6_v1"
DISPERSION_FLAT_P6_RAISED_RSS_PROFILE = (
    "task39extra_dispersion_flat_0p7_p6_raised_rss_v2"
)
DISPERSION_FLAT_P6_PROFILES = frozenset(
    {DISPERSION_FLAT_P6_PROFILE, DISPERSION_FLAT_P6_RAISED_RSS_PROFILE}
)
DISPERSION_FLAT_RSS_HARD_LIMIT_BYTES = 32 * 1024**3
DISPERSION_FLAT_RSS_PLANNING_LIMIT_BYTES = 24 * 1024**3
DISPERSION_FLAT_RAISED_RSS_HARD_LIMIT_BYTES = 512 * 1024**3
DISPERSION_FLAT_RAISED_RSS_PLANNING_LIMIT_BYTES = 448 * 1024**3
TASK40_PHI90_D13_B_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_B_p6_direct_v1"
)
TASK40_PHI90_D13_X_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_X_p6_direct_v1"
)
TASK40_PHI90_D13_Y_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_Y_p6_direct_v1"
)
TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_Y2_p6_direct_v1"
)
TASK40_PHI90_D13_Y3_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_Y3_p6_direct_v1"
)
TASK40_PHI90_D13_X2_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_X2_from_Y2_p6_direct_v1"
)
TASK40_PHI90_D13_Z_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_Z_p6_direct_v1"
)
TASK40_PHI90_D13_Z2_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_Z2_from_Y2_p6_direct_v1"
)
TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_D13_R14_from_Y2_p6_direct_v1"
)
TASK40_PHI90_D5_B_P6_DIRECT_PROFILE = (
    "task40para_phi90_5_D5_B_p6_direct_v1"
)
TASK40_PHI90_D5_X_P6_DIRECT_PROFILE = (
    "task40para_phi90_5_D5_X_p6_direct_v1"
)
TASK40_PHI90_D5_Y_P6_DIRECT_PROFILE = (
    "task40para_phi90_5_D5_Y_p6_direct_v1"
)
TASK40_PHI90_D5_Z_P6_DIRECT_PROFILE = (
    "task40para_phi90_5_D5_Z_p6_direct_v1"
)
TASK40_PHI90_D5_PROFILES = frozenset(
    {
        TASK40_PHI90_D5_B_P6_DIRECT_PROFILE,
        TASK40_PHI90_D5_X_P6_DIRECT_PROFILE,
        TASK40_PHI90_D5_Y_P6_DIRECT_PROFILE,
        TASK40_PHI90_D5_Z_P6_DIRECT_PROFILE,
    }
)
TASK40_PHI90_H15_B_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_H15_B_p6_direct_v1"
)
TASK40_PHI90_H15_X_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_H15_X_p6_direct_v1"
)
TASK40_PHI90_H15_Y_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_H15_Y_p6_direct_v1"
)
TASK40_PHI90_H15_Z_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_H15_Z_p6_direct_v1"
)
TASK40_PHI90_H15_YZ480_P6_DIRECT_PROFILE = (
    "task40para_phi90_13p5_H15_YZ480_p6_direct_v1"
)
TASK40_PHI90_H15_PROFILES = {
    TASK40_PHI90_H15_B_P6_DIRECT_PROFILE: "B",
    TASK40_PHI90_H15_X_P6_DIRECT_PROFILE: "X",
    TASK40_PHI90_H15_Y_P6_DIRECT_PROFILE: "Y",
    TASK40_PHI90_H15_Z_P6_DIRECT_PROFILE: "Z",
    TASK40_PHI90_H15_YZ480_P6_DIRECT_PROFILE: "YZ480",
}
# D15 is a distinct 13.5 nm study. D15-Z2 is deliberately omitted because it
# is an identity-based reuse alias to the completed H15-B result.
TASK40_PHI90_D15_PROFILES = {
    f"task40para_phi90_13p5_D15_{case}_p6_direct_v1": case
    for case in (
        "B", "X1", "X2", "X3", "Y1", "Y2", "Y3", "Y3_2",
        "Y3_3", "Y3_4", "Y4_4_4", "Z1", "Z3"
    )
}
TASK40_PHI90_D13_BASE_AXIS_SHA256 = {
    "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
    "y": "ade66521c0b91557472bc44e87928403e2331bb5211d39406ed3fcb35a1780ef",
    "z": "1b914feb6c2eba6bf20142a3a24e9918947b90be497ded96778e1e1ee3457ce6",
}
TASK40_PHI90_D13_CASES = {
    TASK40_PHI90_D13_B_P6_DIRECT_PROFILE: {
        "case": "B",
        "changed_axis": None,
        "axis_cell_counts": (6, 6, 14),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (2, 2, 2), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 504,
        "expected_material_tag_counts": {"1": 420, "2": 36, "3": 48},
        "explicit_axis_counts_in_input": False,
    },
    TASK40_PHI90_D13_X_P6_DIRECT_PROFILE: {
        "case": "X",
        "changed_axis": "x",
        "axis_cell_counts": (12, 6, 14),
        "segment_cell_counts": {
            "x": (4, 4, 4), "y": (2, 2, 2), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 1008,
        "expected_material_tag_counts": {"1": 840, "2": 72, "3": 96},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_Y_P6_DIRECT_PROFILE: {
        "case": "Y",
        "changed_axis": "y",
        "axis_cell_counts": (6, 12, 14),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (4, 4, 4), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 1008,
        "expected_material_tag_counts": {"1": 840, "2": 72, "3": 96},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE: {
        "case": "Y2",
        "parent_case": "Y",
        "changed_axis": "y",
        "axis_cell_counts": (6, 24, 14),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (8, 8, 8), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 2016,
        "expected_material_tag_counts": {"1": 1680, "2": 144, "3": 192},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_Y3_P6_DIRECT_PROFILE: {
        "case": "Y3",
        "parent_case": "Y2",
        "changed_axis": "y",
        "axis_cell_counts": (6, 48, 14),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (16, 16, 16), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 4032,
        "expected_material_tag_counts": {"1": 3360, "2": 288, "3": 384},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_X2_P6_DIRECT_PROFILE: {
        "case": "X2",
        "parent_case": "Y2",
        "axis_comparison_parent": "Y2",
        "changed_axis": "x",
        "axis_cell_counts": (12, 24, 14),
        "segment_cell_counts": {
            "x": (4, 4, 4), "y": (8, 8, 8), "z": (1, 12, 1),
        },
        "expected_global_cell_count": 4032,
        "expected_material_tag_counts": {"1": 3360, "2": 288, "3": 384},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_Z_P6_DIRECT_PROFILE: {
        "case": "Z",
        "changed_axis": "z",
        "axis_cell_counts": (6, 6, 28),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (2, 2, 2), "z": (2, 24, 2),
        },
        "expected_global_cell_count": 1008,
        "expected_material_tag_counts": {"1": 840, "2": 72, "3": 96},
        "explicit_axis_counts_in_input": True,
    },
    TASK40_PHI90_D13_Z2_P6_DIRECT_PROFILE: {
        "case": "Z2",
        "parent_case": "Y2",
        "axis_comparison_parent": "Y2",
        "changed_axis": "z",
        "axis_cell_counts": (6, 24, 28),
        "segment_cell_counts": {
            "x": (2, 2, 2), "y": (8, 8, 8), "z": (2, 24, 2),
        },
        "expected_global_cell_count": 4032,
        "expected_material_tag_counts": {"1": 3360, "2": 288, "3": 384},
        "explicit_axis_counts_in_input": True,
    },
}
TASK40_PHI90_P6_DIRECT_PROFILES = frozenset(
    {
        *TASK40_PHI90_D13_CASES,
        TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE,
        *TASK40_PHI90_D5_PROFILES,
        *TASK40_PHI90_H15_PROFILES,
        *TASK40_PHI90_D15_PROFILES,
    }
)
P6_CONDENSED_DIRECT_PROFILES = (
    V7_ANISO_N0_P6_DIRECT_PROFILES
    | V6_F5_P6_DIRECT_PROFILES
    | DISPERSION_FLAT_P6_PROFILES
    | TASK40_PHI90_P6_DIRECT_PROFILES
)
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
NATIVE_CASES[V7_D_ANISO_N0_P6_DIRECT_PROFILE] = (0.7, (0.25,), None, None, None)
NATIVE_CASES[DISPERSION_FLAT_P6_PROFILE] = (
    0.7, (0.5, 0.25, 0.125), None, None, None
)
NATIVE_CASES[DISPERSION_FLAT_P6_RAISED_RSS_PROFILE] = (
    0.7, (0.5, 0.25, 0.125), None, None, None
)
for _task40_profile in TASK40_PHI90_D13_CASES:
    NATIVE_CASES[_task40_profile] = (13.5, (10.0,), None, None, None)
for _task40_profile in TASK40_PHI90_H15_PROFILES:
    NATIVE_CASES[_task40_profile] = (13.5, (15.0,), None, None, None)
for _task40_profile in TASK40_PHI90_D5_PROFILES:
    NATIVE_CASES[_task40_profile] = (5.0, (4.0,), None, None, None)
for _task40_profile in TASK40_PHI90_D15_PROFILES:
    NATIVE_CASES[_task40_profile] = (13.5, (15.0,), None, None, None)
NATIVE_CASES[TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE] = (
    13.5, (10.0,), None, None, None
)
for _f5_direct_profile in V6_F5_P6_DIRECT_PROFILES:
    NATIVE_CASES[_f5_direct_profile] = (5.0, (4.0,), None, None, None)
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
            *V6_F5_P6_DIRECT_PROFILES,
            *DISPERSION_FLAT_P6_PROFILES,
            *TASK40_PHI90_P6_DIRECT_PROFILES,
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


def _dispersion_flat_p6_profile_facts(identity):
    """Return the isolated small-flat P6 direct study contract."""

    from src.geometry.dispersion_flat_axis_plan import (
        AXIS_PLAN_ID,
        Z_AXIS_SHA256_LE_F64,
    )

    facts = native_profile_facts(V7_ANISO_N0_P6_DIRECT_PROFILE)
    if identity == DISPERSION_FLAT_P6_PROFILE:
        hard = DISPERSION_FLAT_RSS_HARD_LIMIT_BYTES
        planning = DISPERSION_FLAT_RSS_PLANNING_LIMIT_BYTES
        resource_version = "v1"
    elif identity == DISPERSION_FLAT_P6_RAISED_RSS_PROFILE:
        hard = DISPERSION_FLAT_RAISED_RSS_HARD_LIMIT_BYTES
        planning = DISPERSION_FLAT_RAISED_RSS_PLANNING_LIMIT_BYTES
        resource_version = "raised_v2"
    else:
        raise ValueError(f"unsupported dispersion-flat P6 profile: {identity}")
    facts.update(
        identity=identity,
        execution_mode="full_solve",
        wavelength_nm=0.7,
        allowed_mesh_targets_nm=[0.5, 0.25, 0.125],
        formal_runner="src.runners.p6_condensed_direct",
        route="DISPERSION_FLAT_P6_CONDENSED_DIRECT",
        operator_scope="all_auto_propagating_orders_for_flat_1nm_period",
        full_dtn_status=(
            "AUTO_PROPAGATING_PORT_OPERATOR_BUILT; evanescent orders excluded"
        ),
    )
    # The direct flat study must not inherit V7's P4/H6/FGMRES resource and
    # qualification language.  Keep the common profile schema, but replace
    # those branches with explicit NOT_BUILT facts for this route.
    facts["reference_only"] = True
    facts["fine_physical_operator_modified"] = False
    facts["official_recovery_requires_full_explicit_true_residual"] = True
    facts.pop("release_auxiliary_before_recovery", None)
    facts.pop("additional_fine_vectors_limit", None)
    facts["fine_auxiliary"] = {
        "identity": "NOT_BUILT_DIRECT_P6",
        "constructed": False,
    }
    facts["intermediate"] = {
        "operator": "NOT_BUILT_DIRECT_P6",
        "reason": "direct P6 condensed solve has no P4/coarse correction",
    }
    facts["auxiliary"] = {
        "role": "appended_modal_unknowns_in_the_augmented_direct_matrix",
        "independent_auxiliary_operator": False,
    }
    facts["balanced"] = {
        "operator": "NOT_BUILT_DIRECT_P6",
        "outer_balanced_projection": False,
    }
    facts["inner"] = {
        "route": "NOT_BUILT_DIRECT_P6",
        "iterations": 0,
        "ksp_created": False,
    }
    facts["structural_calls"] = {
        "matrix_assembly_contract": 1,
        "factor_symbolic_contract": 1,
        "factor_numeric_contract": 1,
        "factor_solve_contract": 1,
        "outer_ksp_contract": 0,
    }
    facts["p4_p6_curl_implementation"] = "P6_NATIVE_FFCX_ONLY; P4_NOT_BUILT"
    facts["p4_assembly_implementation"] = "NOT_BUILT_DIRECT_P6"
    facts["functional_store_policy"] = {
        "enabled": False,
        "configuration": "not_used",
        "cross_mesh_fe_reuse": False,
    }
    facts["outer"] = {
        "route": "P6_CONDENSED_DIRECT",
        "initial_guess": "not_applicable_direct_solve",
        "screen": {"enabled": False, "policy": "not_applicable"},
    }
    facts["resources"].update(
        absolute_cap_bytes=hard,
        planning_cap_bytes=planning,
        startup_headroom_bytes=hard - planning,
        # memory_envelope() requires this floor for native profiles; the
        # effective reserve remains max(4 GiB, 15% of effective total RAM).
        reserve_min_bytes=4 * 1024**3,
        rss_hard_limit_bytes=hard,
        rss_warning_bytes=planning,
        resource_stop_policy="measured_tree_rss_only_v3",
        swap_policy="require_zero_swap",
        global_swap_delta_policy="require_zero_swap",
        stop_on_global_swap=True,
        prediction_admission_policy="record_only",
        memavailable_runtime_policy="record_at_fresh_admission",
        require_zero_swap=True,
        pss_sampling_policy="disabled_by_profile",
        pss_interval_seconds=None,
        uss_sampling_policy="disabled_by_profile",
        uss_interval_seconds=None,
        concurrent_neighbor_authorized=False,
    )
    for key in (
        "reserve_fraction",
        "warning_fraction",
        "job_swap_max_bytes",
        "performance_grace_seconds",
        "p1_max_rows_each",
        "p1_matrix_factor_max_bytes_each",
        "independent_p1_factors",
        "reference_p4_factors",
        "reference_factor_budget",
        "batch_limit_seconds",
        "E1_setup_tests_seconds",
        "E1_PC_limit",
        "E1_C_limit",
        "E1_MatSolve_limit",
        "p4_budget_policy",
        "reference_memory_admission",
    ):
        facts["resources"].pop(key, None)
    facts["native_execution"].update(
        supervisor_cpu=9,
        worker_cpu=24,
        worker_cpus=[24],
        mpi_size=1,
        math_threads=1,
        memory_policy="interleave_nodes0_1",
        native_memory_policy="interleave_nodes0_1",
    )
    facts["component_options"] = {
        "functional_store_policy": "disabled_no_functional_store_config",
        "cross_mesh_fe_reuse": False,
        "direct_p6_route": True,
        "flat_component": True,
        "axis_plan_id": AXIS_PLAN_ID,
        "z_axis_sha256_le_f64": Z_AXIS_SHA256_LE_F64,
        "nx_cases": [2, 4, 8],
        "axis_cell_counts": [[2, 2, 234], [4, 2, 234], [8, 2, 234]],
        "mode_policy": "all_auto_propagating_orders_per_flat_period",
        "no_n0_filter": True,
        "volume_quadrature": {
            "degree": 15,
            "rule": "default",
            "points_per_hexahedron": 512,
            "points_weights_sha256": (
                "e3cf565f440b60b083a065f4655124926e98b047edea40d869cdfa5c66df9175"
            ),
        },
        "surface_quadrature": {
            "degree": 160,
            "rule": "default",
            "mode_inventory": "all_auto_propagating_orders",
        },
        "surface_quadrature_witness": {
            "degree": 192,
            "case": "nx2_only",
            "scope": "same_mesh_rhs_and_action_diagnostic_no_gate",
        },
        "surface_assembly_backend_by_degree": {"p6": "native_ffcx"},
        "worker_tree_rss_hard_limit_bytes": hard,
        "worker_tree_rss_planning_limit_bytes": planning,
    }
    facts["backend"] = {
        "p6": "exact_p6_local_static_condensation_materialized_AIJ",
        "global_matrix": "one_exact_[S_V,Bhat;-Dhat,Hhat]_matrix",
        "factor": "one_MUMPS_symbolic_then_numeric_on_the_same_matrix",
        "rhs": "production_incident_top_traction_plus_DtN_modal_rhs_via_finalized_MPC",
        "recovery": "P6CellCondensedAction.recover_storage",
        "independent_residual": "original_full_p6_A6_active_flat_auto_port_operator",
        "p4_operator": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "outer_ksp": "NOT_BUILT",
        "operator_scope": facts["operator_scope"],
        "full_dtn_status": facts["full_dtn_status"],
    }
    facts.pop("coarse_operator", None)
    facts.pop("retained_condensed_v20", None)
    facts["condensed_route"] = {
        "name": "dispersion_flat_p6_exact_local_condensation_direct_v1",
        "degree": 6,
        "matrix_blocks": "[S_V,Bhat;-Dhat,Hhat]",
        "local_elimination": "exact_existing_per_cell_interior_factorization",
        "parent_modes": "dynamic_all_auto_propagating_orders",
        "active_modes": "same_as_parent_no_filter",
        "parent_quadrature_degree": 160,
        "matrix_lifecycle": "one_materialized_PETSc_AIJ_through_symbolic_numeric_solve",
        "cross_mesh_reuse": False,
        "functional_store": False,
        "no_p4_factor_or_outer_ksp": True,
    }
    facts["campaign_authorization"].update(
        source="user-authorized 0.7 nm flat P6 direct dispersion calibration",
        execution_mode="full_solve",
        resource_policy={
            "name": (
                f"dispersion_flat_{hard // 2**30}GiB_tree_rss_zero_swap_{resource_version}"
            ),
            "rss_hard_limit_bytes": hard,
            "rss_planning_limit_bytes": planning,
            "zero_swap": True,
            "pss_uss_sampling": "disabled",
            "prediction": "record_only",
        },
        memory_override={
            "source": "user-authorized bounded dispersion flat calibration",
            "whole_process_tree_rss_cap_bytes": hard,
            "planning_cap_bytes": planning,
            "startup_headroom_bytes": hard - planning,
            "require_zero_swap": True,
            "pss_uss_sampling": "disabled",
        },
        direct_route={
            "degree": 6,
            "mode_policy": "all_auto_propagating_orders_per_flat_period",
            "surface_quadrature_degree": 160,
            "volume_quadrature_degree": 15,
            "same_factor_lifecycle": ["symbolic", "numeric", "solve"],
            "p4_and_outer_ksp": "not_built",
        },
    )
    for key in (
        "restart",
        "max_iterations",
        "initial_guess",
        "screen",
        "low_memory_p4_inverse_trials",
    ):
        facts["campaign_authorization"].pop(key, None)
    facts["campaign_authorization"].pop("fresh_n0_inventory_directory", None)
    facts["comparison_reference"] = {
        "reference_kind": "three_same_physics_flat_meshes",
        "comparison_cases": [2, 4, 8],
        "only_mesh_change": "x cell count; x period and y/z axes remain fixed",
        "old_grating_reference": "not_a_same_mesh_or_same_geometry_comparison",
        "physical_plane_wave_reference": "analytic plane-interface reference recomputed in outcome",
        "qualification_scope": "bounded flat component; not full grating qualification",
    }
    return facts


def _task40_phi90_d13_profile_facts(identity):
    """Return one frozen Task40 P6-direct D13 directional mesh contract."""

    if identity not in TASK40_PHI90_D13_CASES:
        raise ValueError(f"unsupported Task40 P6-direct profile: {identity}")
    case = TASK40_PHI90_D13_CASES[identity]
    case_name = case["case"]
    surface_quadrature_degree = 28
    operator_scope = f"task40_phi90_D13_{case_name}_R13_finite_rectangle"
    from src.geometry.task40_phi90_d13_axis_plan import (
        D13_AXIS_PLANS,
        D13_B_AXIS_SHA256_LE_F64,
    )

    axis_plan = D13_AXIS_PLANS[case_name]
    if tuple(axis_plan["axis_cell_counts"]) != tuple(case["axis_cell_counts"]):
        raise ValueError(f"Task40 D13 {case_name} profile and frozen axis plan differ")
    if D13_B_AXIS_SHA256_LE_F64 != TASK40_PHI90_D13_BASE_AXIS_SHA256:
        raise ValueError("Task40 D13 B axis hashes differ between profile and axis plan")
    facts = native_profile_facts("dual_condensed_balh_native_13p5_q4_v5")
    for legacy_key in (
        "fine_auxiliary", "intermediate", "auxiliary", "balanced",
        "additional_fine_vectors_limit", "inner", "structural_calls",
        "fine_physical_operator_modified",
        "official_recovery_requires_full_explicit_true_residual",
        "release_auxiliary_before_recovery", "reference_only",
    ):
        facts.pop(legacy_key, None)
    mode_selection = {
        "schema": "task40.dtn-mode-selection.v1",
        "policy": "explicit_symmetric_rectangle_v1",
        "parent_rectangle_max_abs_m_n": [4, 8],
        "active_rectangle_max_abs_m_n": [4, 8],
        "parent_inventory_scope": "R13_finite_rectangle_including_evanescent",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
    }
    facts.update(
        identity=identity,
        model_id="si_block_phi90_50x50_17x20_h120",
        execution_mode="full_solve",
        wavelength_nm=13.5,
        allowed_mesh_targets_nm=[10.0],
        formal_runner="src.runners.p6_condensed_direct",
        route=f"TASK40_PHI90_D13_{case_name}_P6_CONDENSED_DIRECT_R13",
        operator_scope=operator_scope,
        full_dtn_status="FULL_DTN_NOT_VERIFIED",
    )
    facts["task40_material_identity"] = {
        "model_id": "si_block_phi90_50x50_17x20_h120",
        "material_label": "Si / silicon",
        "index_values": list(MATERIALS[13.5]),
        "value_authority": "inherited_13p5_nm_input_values_exact",
        "shared_material_tables_modified": False,
    }
    facts["outer"] = {
        "route": "P6_CONDENSED_DIRECT",
        "initial_guess": "not_applicable_direct_solve",
        "screen": {"enabled": False, "policy": "not_applicable"},
    }
    # No user-fixed RSS ceiling applies to D13.  The watchdog uses a separate
    # explicit available-memory floor and never falls back to legacy caps.
    facts["resources"] = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "rss_warning_bytes": None,
        "startup_headroom_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "global_swap_delta_policy": "observe_only",
        "stop_on_global_swap": False,
        "prediction_admission_policy": "record_only",
        "memavailable_runtime_policy": "stop_below_explicit_64_gib_floor",
        "pss_sampling_policy": "disabled_by_profile",
        "pss_interval_seconds": None,
        "uss_sampling_policy": "disabled_by_profile",
        "uss_interval_seconds": None,
        "concurrent_neighbor_authorized": False,
        "workflow_seconds": None,
        "solve_seconds": None,
        "time_limit_mode": "none",
    }
    facts["native_execution"] = {
        "supervisor_cpu": 9,
        "worker_cpu": 24,
        "worker_cpus": [24],
        "mpi_size": 1,
        "math_threads": 1,
        "memory_policy": "interleave_nodes0_1",
        "native_memory_policy": "interleave_nodes0_1",
    }
    facts["component_options"] = {
        "functional_store_policy": "disabled_no_functional_store_config",
        "cross_mesh_fe_reuse": False,
        "direct_p6_route": True,
        "dtn_sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "dtn_sparse_cutoff_relative_tolerance": 1.0e-13,
        "direct_factor_evidence": {
            "schema": "task40.p6-direct-factor-evidence.v1",
            "mode_keys": [
                ["top", -4, 0, "p"],
                ["top", 0, 0, "s"],
                ["top", 4, 0, "p"],
                ["bottom", -4, 0, "p"],
                ["bottom", 0, 0, "s"],
                ["bottom", 4, 0, "p"],
            ],
            "pre_release": True,
            "saves_full_p6_storage_and_augmented_solution": True,
            "saves_independent_port_residuals": True,
            "full_primal_projection_quadrature_degree": int(
                surface_quadrature_degree
            ),
        },
        "task_family": "task40_phi90_mesh_modes_direct",
        "mesh_target_nm": 10.0,
        "expected_axis_cell_counts": list(case["axis_cell_counts"]),
        "expected_global_cell_count": case["expected_global_cell_count"],
        "directional_mesh_comparison": {
            "case": case_name,
            "parent_case": case.get("parent_case", "B"),
            "changed_axis": case["changed_axis"],
            "axis_cell_counts": list(case["axis_cell_counts"]),
            "segment_cell_counts": {
                axis: list(counts)
                for axis, counts in case["segment_cell_counts"].items()
            },
            "base_axis_sha256_le_f64": dict(
                axis_plan["parent_axis_sha256_le_f64"]
                if case.get("axis_comparison_parent") is not None
                else TASK40_PHI90_D13_BASE_AXIS_SHA256
            ),
            "expected_material_tag_counts": dict(
                case["expected_material_tag_counts"]
            ),
            "mesh_plan_id": axis_plan["plan_id"] if case_name != "B" else None,
            "mesh_plan_sha256": (
                axis_plan["mesh_plan_sha256"] if case_name != "B" else None
            ),
            "expected_axis_sha256_le_f64": dict(
                axis_plan["actual_axis_sha256_le_f64"]
            ),
            "explicit_axis_counts_in_input": case[
                "explicit_axis_counts_in_input"
            ],
            "only_axis_changes_from_B": (
                case["changed_axis"]
                if case.get("axis_comparison_parent") is None
                else None
            ),
        },
        "mode_selection": mode_selection,
        "volume_quadrature": {
            "degree": 15,
            "rule": "default",
            "authority": "live_fine_volume_quadrature_metadata",
        },
        "surface_quadrature": {
            "degree": surface_quadrature_degree,
            "rule": "default",
            "fixed_comparison_envelope": {"max_abs_m": 6, "max_abs_n": 10},
            "authority": "R_plus_two_envelope_fixed_before_D13_B",
            "formula": "max(10, 2*p + max_abs_order + 6)",
        },
        "surface_assembly_backend_by_degree": {"p6": "native_ffcx"},
        "field_output_evidence": {
            "complete_field": "cellwise_DG6_E_and_H_with_domain_tags",
            "periodic_reference_sample_counts_min_x_y": [40, 64],
            "pillar_interior_and_exterior": "both_required_in_periodic_center_grid",
            "x_normal_interface_tangential_components": ["y", "z"],
            "y_normal_interface_tangential_components": ["x", "z"],
            "interface_observation_source": (
                "unaveraged_cellwise_DG6_traces_in_complete_field_export"
            ),
        },
    }
    if case.get("axis_comparison_parent") is not None:
        facts["component_options"]["directional_mesh_comparison"].update(
            axis_comparison_parent=case["axis_comparison_parent"],
            only_axis_changes_from_parent=case["changed_axis"],
        )
    facts["backend"] = {
        "p6": "exact_p6_local_static_condensation_materialized_AIJ",
        "global_matrix": "one_exact_[S_V,Bhat;-Dhat,Hhat]_matrix",
        "factor": "one_MUMPS_symbolic_then_numeric_on_the_same_matrix_with_at_most_two_correction_solves",
        "rhs": "P6CellCondensedAction.reduce_rhs",
        "recovery": "P6CellCondensedAction.recover_storage",
        "independent_residual": "original_full_p6_A6_active_R13_rectangle_action",
        "p4_operator": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "outer_ksp": "NOT_BUILT",
        "operator_scope": facts["operator_scope"],
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
    }
    facts.pop("coarse_operator", None)
    facts.pop("retained_condensed_v20", None)
    facts.pop("p4_assembly_implementation", None)
    facts.pop("p4_p6_curl_implementation", None)
    facts["condensed_route"] = {
        "name": "task40_phi90_p6_exact_local_condensation_direct_v1",
        "degree": 6,
        "matrix_blocks": "[S_V,Bhat;-Dhat,Hhat]",
        "local_elimination": "exact_existing_per_cell_interior_factorization",
        "parent_mode_inventory": "explicit_R13_rectangle_including_evanescent",
        "active_mode_inventory": "same_as_parent",
        "parent_quadrature_degree": 28,
        "surface_quadrature_envelope_max_abs_m_n": [6, 10],
        "same_matrix_lifecycle": (
            "one_materialized_PETSc_AIJ_one_symbolic_one_numeric_initial_solve_"
            "and_at_most_two_same_factor_correction_solves"
        ),
        "condensed_residual_relative_gate": 1.0e-9,
        "max_same_factor_correction_solves": 2,
        "total_factor_solve_calls_max": 3,
        "release_after": (
            "independent_native_A6_and_complete_p6_storage_recovery"
        ),
        "release_before": "field_and_absorption_output_postprocessing",
        "materialized_matrix_owner": "AssemblyTimeCondensedSystem",
        "borrowed_action_owns_matrix": False,
        "cross_mesh_reuse": False,
        "functional_store": False,
        "no_p4_factor_or_outer_ksp": True,
    }
    facts["campaign_authorization"] = {
        "source": "Task40 user-authorized N1 then D13 sequence",
        "execution_mode": "full_solve",
        "time_limit_mode": "none",
        "formal_mpi": 1,
        "math_threads": 1,
        "supervisor_cpu": 9,
        "worker_cpu": 24,
        "numa_policy": "interleave_nodes0_1",
        "resource_policy": {
            "name": "host_available_floor_v1",
            "rss_user_cap": None,
            "minimum_available_bytes": 64 * 1024**3,
            "swap": "observe_only",
            "pss_uss_sampling": "disabled",
            "prediction": "record_only",
        },
        "direct_route": {
            "degree": 6,
            "parent_mode_rectangle_max_abs_m_n": [4, 8],
            "active_mode_rectangle_max_abs_m_n": [4, 8],
            "parent_mode_count": "live_inventory_expected_612",
            "parent_mode_sha256": "live_inventory_authority",
            "volume_quadrature": "live_degree15_default_rule",
            "surface_quadrature": "fixed_R_plus_two_envelope_degree28",
            "same_factor_lifecycle": {
                "symbolic_calls": 1,
                "numeric_calls": 1,
                "initial_solve_calls": 1,
                "same_factor_correction_solve_calls_max": 2,
                "total_solve_calls_max": 3,
            },
            "condensed_residual_relative_gate": 1.0e-9,
            "max_same_factor_correction_solves": 2,
            "p4_and_outer_ksp": "not_built",
        },
    }
    facts["operator_scope"] = operator_scope
    facts["full_dtn_status"] = "FULL_DTN_NOT_VERIFIED"
    return facts


def _task40_phi90_d5_profile_facts(identity):
    """Freeze one fixed-budget 5 nm D5 R5 mesh case and its integrals."""
    from copy import deepcopy

    from src.geometry.task40_phi90_d5_axis_plan import (
        D5_AXIS_PLANS,
    )

    if identity not in TASK40_PHI90_D5_PROFILES:
        raise ValueError(f"unsupported Task40 D5 profile: {identity}")
    case_by_profile = {
        TASK40_PHI90_D5_B_P6_DIRECT_PROFILE: "B",
        TASK40_PHI90_D5_X_P6_DIRECT_PROFILE: "X",
        TASK40_PHI90_D5_Y_P6_DIRECT_PROFILE: "Y",
        TASK40_PHI90_D5_Z_P6_DIRECT_PROFILE: "Z",
    }
    case_name = case_by_profile[identity]
    plan = D5_AXIS_PLANS[case_name]
    counts = tuple(int(value) for value in plan["axis_cell_counts"])
    nx, ny, _nz = counts
    segment_counts = plan["segment_cell_counts"]
    total_cells = math.prod(counts)
    substrate = nx * ny * int(segment_counts["z"][0])
    grating = (
        int(segment_counts["x"][1])
        * int(segment_counts["y"][1])
        * int(segment_counts["z"][1])
    )
    tags = {
        "1": total_cells - substrate - grating,
        "2": substrate,
        "3": grating,
    }
    if case_name == "B" and tags != {"1": 5188, "2": 920, "3": 792}:
        raise ValueError(f"Task40 D5 B tag arithmetic changed: {tags}")
    if case_name != "B" and tags != {
        "1": 10376, "2": 1840, "3": 1584
    }:
        raise ValueError(f"Task40 D5 {case_name} tag arithmetic changed: {tags}")
    base = deepcopy(
        _task40_phi90_d13_profile_facts(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    )
    operator_scope = f"task40_phi90_D5_{case_name}_R5_finite_rectangle"
    mode = {
        "schema": "task40.dtn-mode-selection.v1",
        "policy": "explicit_symmetric_rectangle_v1",
        "reference_mode_label": "R5",
        "parent_rectangle_max_abs_m_n": [11, 20],
        "active_rectangle_max_abs_m_n": [11, 20],
        "parent_inventory_scope": "R5_finite_rectangle_including_evanescent",
        "expected_mode_count": 3772,
        "boundary_amplitude_scale_policy": "boundary_magnitude_scaled_r5_v1",
        "expected_mode_sha256": (
            "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
        ),
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
    }
    base.update(
        identity=identity,
        model_id="si_block_phi90_50x50_17x20_h120",
        execution_mode="full_solve",
        wavelength_nm=5.0,
        allowed_mesh_targets_nm=[4.0],
        route=f"TASK40_PHI90_D5_{case_name}_P6_CONDENSED_DIRECT_R5",
        operator_scope=operator_scope,
        full_dtn_status="FULL_DTN_NOT_VERIFIED",
    )
    base["task40_material_identity"] = {
        "model_id": "si_block_phi90_50x50_17x20_h120",
        "material_label": "Si / silicon",
        "index_values": list(MATERIALS[5.0]),
        "value_authority": "inherited_5_nm_input_values_exact",
        "shared_material_tables_modified": False,
    }
    options = base["component_options"]
    options.update(
        task_family="task40_phi90_d5_mesh_modes_direct",
        mesh_target_nm=4.0,
        expected_axis_cell_counts=list(counts),
        expected_global_cell_count=total_cells,
        nominal_isotropic_4nm_cell_budget=7020,
        actual_budgeted_cell_count=total_cells,
        budgeted_mesh_reason=(
            "D13 same-policy evidence shows larger y sensitivity than x/z; "
            "the 5 nm baseline allocates more intervals to y while retaining "
            "material planes and a graded z mesh. This is a candidate baseline, "
            "not a convergence claim."
        ),
        directional_mesh_comparison={
            "mesh_plan_family": "d5",
            "case": case_name,
            "parent_case": "B",
            "changed_axis": plan["changed_axis"],
            "axis_cell_counts": list(counts),
            "segment_cell_counts": segment_counts,
            "base_axis_sha256_le_f64": dict(
                plan["parent_axis_sha256_le_f64"]
            ),
            "expected_material_tag_counts": tags,
            "mesh_plan_id": plan["plan_id"],
            "mesh_plan_sha256": plan["mesh_plan_sha256"],
            "expected_axis_sha256_le_f64": dict(
                plan["actual_axis_sha256_le_f64"]
            ),
            "explicit_axis_counts_in_input": True,
            "only_axis_changes_from_B": plan["changed_axis"],
        },
        mode_selection=mode,
    )
    options["direct_factor_evidence"][
        "full_primal_projection_quadrature_degree"
    ] = 39
    options["surface_quadrature"] = {
        "degree": 39,
        "rule": "default",
        "fixed_comparison_envelope": {"max_abs_m": 12, "max_abs_n": 21},
        "authority": "fixed_R5_plus_one_envelope_before_D5_B",
        "formula": "max(10, 2*p + max_abs_order + 6)",
    }
    options["volume_quadrature"] = {
        "degree": 15,
        "rule": "default",
        "authority": "live_fine_volume_quadrature_metadata",
    }
    base["backend"].update(
        independent_residual="original_full_p6_A6_active_R5_rectangle_action",
        operator_scope=operator_scope,
    )
    base["condensed_route"].update(
        operator_family="D5_R5_finite_rectangle",
        parent_mode_inventory="explicit_R5_rectangle_including_evanescent",
        parent_mode_count=3772,
        parent_quadrature_degree=39,
        surface_quadrature_envelope_max_abs_m_n=[12, 21],
        operator_scope=operator_scope,
    )
    direct_route = base["campaign_authorization"]["direct_route"]
    direct_route.update(
        mesh_target_nm=4.0,
        parent_mode_rectangle_max_abs_m_n=[11, 20],
        active_mode_rectangle_max_abs_m_n=[11, 20],
        parent_mode_count=3772,
        parent_mode_sha256=(
            "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
        ),
        port_boundary_amplitude_scale_policy="boundary_magnitude_scaled_r5_v1",
        surface_quadrature=(
            "fixed_R5_plus_one_m12_n21_envelope_degree39"
        ),
    )
    base["campaign_authorization"]["source"] = (
        "Task40 user-authorized D5 5 nm direction study with a fixed nominal "
        "7020-cell budget and D13-informed y prioritization"
    )
    base["operator_scope"] = operator_scope
    base["full_dtn_status"] = "FULL_DTN_NOT_VERIFIED"
    return base


def _task40_phi90_r14_profile_facts(identity):
    """Freeze an R14 rectangle on the existing same-policy D13-Y2 mesh."""
    from copy import deepcopy

    facts = deepcopy(
        _task40_phi90_d13_profile_facts(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    )
    mode = facts["component_options"]["mode_selection"]
    mode.update(
        reference_mode_label="R14",
        expected_mode_count=836,
        expected_mode_sha256=(
            "deefaa839044a2542560b60b68a457c4f127eee2221d6dd8477c3d49fb1a860e"
        ),
        parent_rectangle_max_abs_m_n=[5, 9],
        active_rectangle_max_abs_m_n=[5, 9],
        parent_inventory_scope="R14_finite_rectangle_including_evanescent",
    )
    operator_scope = "task40_phi90_D13_R14_on_Y2_finite_rectangle"
    facts.update(
        identity=identity,
        route="TASK40_PHI90_D13_R14_ON_Y2_P6_CONDENSED_DIRECT",
        operator_scope=operator_scope,
    )
    options = facts["component_options"]
    options["mode_selection"] = mode
    options["reference_mode_expansion"] = {
        "parent_case": "same_policy_D13_Y2",
        "only_operator_change": "R13_to_R14_rectangle",
        "parent_rectangle_max_abs_m_n": [5, 9],
        "expected_mode_count": 836,
        "expected_mode_sha256": (
            "deefaa839044a2542560b60b68a457c4f127eee2221d6dd8477c3d49fb1a860e"
        ),
        "contains_evanescent_modes": True,
        "surface_quadrature_degree": 28,
        "surface_quadrature_authority": "fixed_R_plus_two_m6_n10_envelope",
    }
    facts["condensed_route"].update(
        parent_mode_inventory="explicit_R14_rectangle_including_evanescent",
        active_mode_inventory="same_as_R14_parent",
        operator_scope=operator_scope,
    )
    facts["backend"].update(
        independent_residual="original_full_p6_A6_active_R14_rectangle",
        operator_scope=operator_scope,
    )
    facts["campaign_authorization"]["direct_route"].update(
        parent_mode_rectangle_max_abs_m_n=[5, 9],
        active_mode_rectangle_max_abs_m_n=[5, 9],
        parent_mode_count="live_inventory_expected_836",
        reference_mode_label="R14",
        surface_quadrature=(
            "fixed_Rplus2_m6_n10_envelope_degree28; R14 is contained"
        ),
    )
    facts["full_dtn_status"] = "FULL_DTN_NOT_VERIFIED"
    return facts


def _task40_phi90_h15_profile_facts(identity):
    """Return one frozen Task40 H15 or approved fixed-budget mesh profile."""
    from copy import deepcopy

    from src.geometry.task40_phi90_h15_axis_plan import (
        H15_AXIS_PLANS,
        H15_BASE_AXIS_SHA256_LE_F64,
    )

    try:
        case_name = TASK40_PHI90_H15_PROFILES[identity]
    except KeyError as exc:
        raise ValueError(f"unsupported Task40 h15 profile: {identity}") from exc
    plan = H15_AXIS_PLANS[case_name]
    counts = tuple(int(value) for value in plan["axis_cell_counts"])
    nx, ny, nz = counts
    segment_counts = plan["segment_cell_counts"]
    expected_cells = nx * ny * nz
    x_center_cells = int(segment_counts["x"][1])
    y_center_cells = int(segment_counts["y"][1])
    z_substrate_cells = int(segment_counts["z"][0])
    z_grating_cells = int(segment_counts["z"][1])
    substrate_cells = nx * ny * z_substrate_cells
    grating_cells = x_center_cells * y_center_cells * z_grating_cells
    expected_tags = {
        "1": expected_cells - substrate_cells - grating_cells,
        "2": substrate_cells,
        "3": grating_cells,
    }
    base = deepcopy(
        _task40_phi90_d13_profile_facts(TASK40_PHI90_D13_B_P6_DIRECT_PROFILE)
    )
    operator_scope = f"task40_phi90_H15_{case_name}_R13_finite_rectangle"
    base.update(
        identity=identity,
        allowed_mesh_targets_nm=[15.0],
        route=f"TASK40_PHI90_H15_{case_name}_P6_CONDENSED_DIRECT_R13",
        operator_scope=operator_scope,
    )
    base["component_options"].update(
        task_family="task40_phi90_h15_mesh_modes_direct",
        mesh_target_nm=15.0,
        expected_axis_cell_counts=list(counts),
        expected_global_cell_count=expected_cells,
    )
    base["component_options"]["surface_quadrature"].update(
        authority="fixed_R_plus_two_envelope_before_H15_B"
    )
    directional_comparison = {
        "mesh_plan_family": "task40_phi90_h15",
        "case": case_name,
        "parent_case": plan["parent_case"],
        "changed_axis": plan["changed_axis"],
        "axis_cell_counts": list(counts),
        "segment_cell_counts": {
            axis: list(values) for axis, values in segment_counts.items()
        },
        "base_axis_sha256_le_f64": dict(H15_BASE_AXIS_SHA256_LE_F64),
        "expected_material_tag_counts": expected_tags,
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["mesh_plan_sha256"],
        "expected_axis_sha256_le_f64": dict(plan["actual_axis_sha256_le_f64"]),
        "explicit_axis_counts_in_input": True,
        "only_axis_changes_from_B": plan["changed_axis"],
    }
    if case_name == "YZ480":
        directional_comparison.pop("only_axis_changes_from_B")
        directional_comparison.update(
            changed_axes=list(plan["changed_axes"]),
            parent_axis_sha256_le_f64=dict(plan["parent_axis_sha256_le_f64"]),
            only_axis_changes_from_parent=list(plan["changed_axes"]),
        )
    base["component_options"]["directional_mesh_comparison"] = directional_comparison
    base["backend"]["operator_scope"] = operator_scope
    if case_name == "YZ480":
        base["campaign_authorization"]["source"] = (
            "Task40 user-authorized H15 baseline, one-axis refinements, and one "
            "480-cell y-refined/z-coarsened candidate"
        )
    else:
        base["campaign_authorization"]["source"] = (
            "Task40 user-authorized H15 baseline and one-axis refinements"
        )
    base["campaign_authorization"]["direct_route"]["mesh_target_nm"] = 15.0
    base["condensed_route"]["name"] = (
        "task40_phi90_h15_p6_exact_local_condensation_direct_v1"
    )
    base["condensed_route"]["operator_family"] = "H15_R13_finite_rectangle"
    base["condensed_route"]["expected_global_cell_count"] = expected_cells
    base["resources"]["rss_hard_limit_bytes"] = None
    return base


def _task40_phi90_d15_profile_facts(identity):
    """Freeze one launchable D15 axis case without relabeling historical H15 runs."""
    from copy import deepcopy

    from src.geometry.task40_phi90_d15_axis_plan import (
        D15_CASES,
        D15_Z2_HISTORICAL_REUSE,
        d15_axis_plan,
    )

    try:
        case_name = TASK40_PHI90_D15_PROFILES[identity]
    except KeyError as exc:
        raise ValueError(f"unsupported Task40 D15 profile: {identity}") from exc
    case = D15_CASES[case_name]
    plan = d15_axis_plan(case_name)
    counts = tuple(int(value) for value in plan["axis_cell_counts"])
    expected_cells = int(plan["expected_global_cell_count"])
    tags = dict(plan["static_midpoint_tags"])
    tag_counts = {"1": tags["air"], "2": tags["substrate"], "3": tags["grating"]}
    operator_scope = f"task40_phi90_D15_{case_name}_R13_finite_rectangle"
    base = deepcopy(
        _task40_phi90_d13_profile_facts(TASK40_PHI90_D13_B_P6_DIRECT_PROFILE)
    )
    base.update(
        identity=identity,
        model_id="si_block_phi90_50x50_17x20_h120",
        execution_mode="full_solve",
        wavelength_nm=13.5,
        allowed_mesh_targets_nm=[15.0],
        formal_runner="src.runners.p6_condensed_direct",
        route=f"TASK40_PHI90_D15_{case_name}_P6_CONDENSED_DIRECT_R13",
        operator_scope=operator_scope,
        full_dtn_status="FULL_DTN_NOT_VERIFIED",
    )
    options = base["component_options"]
    # Bind the D15 finite rectangle explicitly; the copied D13-B facts provide
    # the numerical policy, but the D15 manifest must carry its own mode identity.
    options["mode_selection"].update(
        reference_mode_label="R13",
        expected_mode_count=612,
        expected_mode_sha256=(
            "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
        ),
    )
    options.update(
        task_family="task40_phi90_d15_mesh_modes_direct",
        mesh_target_nm=15.0,
        expected_axis_cell_counts=list(counts),
        expected_global_cell_count=expected_cells,
        directional_mesh_comparison={
            "mesh_plan_family": "d15",
            "case": case_name,
            "parent_case": case["parent_case"],
            "changed_axis": case["changed_axis"],
            "axis_cell_counts": list(counts),
            "segment_cell_counts": {
                axis: list(values)
                for axis, values in plan["segment_cell_counts"].items()
            },
            "base_axis_sha256_le_f64": dict(plan["base_axis_sha256_le_f64"]),
            "expected_material_tag_counts": tag_counts,
            "mesh_plan_id": plan["plan_id"],
            "mesh_plan_sha256": plan["mesh_plan_sha256"],
            "expected_axis_sha256_le_f64": dict(plan["axis_sha256_le_f64"]),
            "explicit_axis_counts_in_input": True,
            "only_axis_changes_from_B": case["changed_axis"],
            "previous_case": plan["previous_case"],
            "nestedness_from_B": bool(plan["nestedness_from_B"]),
            "nestedness_from_previous_level": bool(
                plan["nestedness_from_previous_level"]
            ),
            "static_plan_record": (
                plan["static_plan_record"]
            ),
            "static_plan_sha256": plan["static_plan_sha256"],
            "historical_D15_Z2_role_reuse": (
                dict(D15_Z2_HISTORICAL_REUSE) if case_name == "B" else None
            ),
            "acceptance_thresholds": {
                "total_R_T_A_balance_A_volume_abs": 1.0e-5,
                "each_channel_R_T_abs_all_active_and_power_carrying": 1.0e-6,
                "boundary_complex_amplitude_relative_l2_no_phase_fit": 1.0e-4,
                "same_coordinate_complex_E_H_relative_l2_no_phase_fit": 1.0e-4,
                "horizontal_Et_Ht_scope": "reported_as_existing_horizontal_diagnostic",
                "canonical_sidewall_Et_Ht": "NOT_MEASURED",
                "all_612_common_channels_required": True,
                "lossy_power_carrying_included_even_if_not_propagating": True,
            },
        },
    )
    options["surface_quadrature"].update(
        authority="fixed_R13_plus_two_m6_n10_envelope_before_D15_B"
    )
    base["backend"]["operator_scope"] = operator_scope
    base["condensed_route"].update(
        name="task40_phi90_d15_p6_exact_local_condensation_direct_v1",
        operator_family=f"D15_{case_name}_R13_finite_rectangle",
        expected_global_cell_count=expected_cells,
        operator_scope=operator_scope,
    )
    base["campaign_authorization"]["source"] = (
        "user-authorized D15 13.5 nm coarse baseline and bounded one-axis "
        "direction study; D15-Z2 maps to the completed H15-B result"
    )
    base["campaign_authorization"]["direct_route"]["mesh_target_nm"] = 15.0
    base["campaign_authorization"]["direct_route"]["d15_axis_case"] = case_name
    base["campaign_authorization"]["direct_route"]["d15_static_plan_sha256"] = (
        plan["static_plan_sha256"]
    )
    base["campaign_authorization"]["direct_route"]["reuse_D15_Z2_without_new_run"] = True
    base["resources"]["rss_hard_limit_bytes"] = None
    return base


def native_profile_facts(identity):
    from .physical_balanced_profile import balanced_profile_facts
    if identity in TASK40_PHI90_P6_DIRECT_PROFILES:
        if identity in TASK40_PHI90_D5_PROFILES:
            return _task40_phi90_d5_profile_facts(identity)
        if identity in TASK40_PHI90_D15_PROFILES:
            return _task40_phi90_d15_profile_facts(identity)
        if identity in TASK40_PHI90_H15_PROFILES:
            return _task40_phi90_h15_profile_facts(identity)
        if identity == TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE:
            return _task40_phi90_r14_profile_facts(identity)
        return _task40_phi90_d13_profile_facts(identity)
    if identity in DISPERSION_FLAT_P6_PROFILES:
        return _dispersion_flat_p6_profile_facts(identity)
    if identity in V6_F5_P6_DIRECT_PROFILES:
        from src.geometry.task39extra_v6_f5_mesh_plan import (
            F5_AXIS_SHA256,
            F5_Y2_PLAN_ID,
            f5_axis_plan_sha256,
        )

        facts = native_profile_facts('dual_condensed_balh_native_5nm_v5')
        truncated = identity == V6_F5_P6_DIRECT_N0_PROFILE
        active_count = 80 if truncated else 600
        active_sha = (
            '36337e70f52f959b4f8b7e1727ee8babccd3e84d2e25d70bd32e87c79040e012'
            if truncated
            else 'dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645'
        )
        parent_sha = 'dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645'
        rss_cap = V7_RSS_HARD_LIMIT_BYTES
        facts.update(
            identity=identity,
            execution_mode='full_solve',
            wavelength_nm=5.0,
            allowed_mesh_targets_nm=[4.0],
            formal_runner='src.runners.p6_condensed_direct',
            route=(
                'V6_F5_P6_CONDENSED_DIRECT_N0'
                if truncated
                else 'V6_F5_P6_CONDENSED_DIRECT_FULL600'
            ),
            operator_scope=(
                'n0_filtered_dtn_not_full_dtn'
                if truncated
                else 'full_600_mode_dtn'
            ),
        )
        facts['outer'] = {
            'route': 'P6_CONDENSED_DIRECT',
            'initial_guess': 'not_applicable_direct_solve',
            'screen': {'enabled': False, 'policy': 'not_applicable'},
        }
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
        facts['native_execution'].update(
            supervisor_cpu=9,
            worker_cpu=24,
            worker_cpus=[24],
            mpi_size=1,
            math_threads=1,
            memory_policy='interleave_nodes0_1',
            native_memory_policy='interleave_nodes0_1',
        )
        facts['component_options'] = {
            'functional_store_policy': 'disabled_no_functional_store_config',
            'cross_mesh_fe_reuse': False,
            'direct_p6_route': True,
            'mode_policy': 'n_equals_zero_from_full600_parent' if truncated else 'full600_parent',
            'parent_mode_count': 600,
            'parent_mode_sha256': parent_sha,
            'active_mode_count': active_count,
            'active_mode_sha256': active_sha,
            'volume_quadrature': {
                'degree': 15,
                'rule': 'default',
                'points_per_hexahedron': 512,
                'points_weights_sha256': (
                    'e3cf565f440b60b083a065f4655124926e98b047edea40d869cdfa5c66df9175'
                ),
            },
            'surface_quadrature': {
                'degree': 37,
                'rule': 'default',
                'authority': 'full600_parent_inventory_even_for_n0_subset',
            },
            'surface_assembly_backend_by_degree': {'p6': 'native_ffcx'},
            'mesh_plan_id': F5_Y2_PLAN_ID,
            'mesh_plan_sha256': f5_axis_plan_sha256(F5_Y2_PLAN_ID),
            'mesh_axis_cell_counts': [15, 2, 36],
            'mesh_axis_y_values_nm': [0.0, 12.5, 25.0],
            'mesh_axis_sha256_le_f64': dict(F5_AXIS_SHA256),
        }
        facts['backend'] = {
            'p6': 'exact_p6_local_static_condensation_materialized_AIJ',
            'global_matrix': 'one_exact_[S_V,Bhat;-Dhat,Hhat]_matrix',
            'factor': 'one_MUMPS_symbolic_then_numeric_on_the_same_matrix',
            'rhs': 'P6CellCondensedAction.reduce_rhs',
            'recovery': 'P6CellCondensedAction.recover_storage',
            'independent_residual': (
                'original_full_p6_A6_n0_action'
                if truncated
                else 'original_full_p6_A6_action'
            ),
            'p4_operator': 'NOT_BUILT',
            'p4_factor': 'NOT_BUILT',
            'outer_ksp': 'NOT_BUILT',
            'operator_scope': facts['operator_scope'],
        }
        facts.pop('coarse_operator', None)
        facts.pop('retained_condensed_v20', None)
        facts['condensed_route'] = {
            'name': 'v6_f5_p6_exact_local_condensation_direct',
            'degree': 6,
            'matrix_blocks': '[S_V,Bhat;-Dhat,Hhat]',
            'local_elimination': 'exact_existing_per_cell_interior_factorization',
            'parent_modes': 600,
            'active_modes': active_count,
            'active_mode_sha256': active_sha,
            'same_matrix_lifecycle': 'one_materialized_PETSc_AIJ_through_symbolic_numeric_solve',
            'cross_mesh_reuse': False,
            'functional_store': False,
            'no_p4_factor_or_outer_ksp': True,
        }
        facts['campaign_authorization']['source'] = (
            'user-authorized 5 nm full600 then n0 p6 direct comparison'
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
        }
        facts['campaign_authorization']['memory_override'] = {
            'source': 'user_authorized_f5_p6_direct_full_solve',
            'whole_process_tree_rss_cap_bytes': rss_cap,
            'parent_and_worker_cap_bytes': rss_cap,
            'pss_uss_sampling': 'disabled',
            'swap_prediction_eta': 'observe_only',
            'time_limit_mode': 'none',
        }
        facts['campaign_authorization'].pop('two_nm_material', None)
        facts['campaign_authorization']['five_nm_material'] = dict(
            facts['campaign_authorization']['user_material']
        )
        facts['campaign_authorization']['direct_route'] = {
            'degree': 6,
            'parent_mode_count': 600,
            'parent_mode_sha256': parent_sha,
            'active_mode_count': active_count,
            'active_mode_sha256': active_sha,
            'volume_quadrature_degree': 15,
            'surface_quadrature_degree': 37,
            'same_factor_lifecycle': ['symbolic', 'numeric', 'solve'],
            'p4_and_outer_ksp': 'not_built',
        }
        facts['comparison_reference'] = {
            'run_id': '20261002T153058.967208Z',
            'source_commit': '1828bc675f2862025e0eaed0beccf15982eb09e6',
            'actual_cells': 3780,
            'parent_mode_count': 600,
            'parent_mode_sha256': parent_sha,
            'baseline_p6_residual': 8.704501286501755e-7,
            'baseline_R': 0.7331835097833246,
            'baseline_T': 0.0002224396245329203,
            'baseline_A_balance': 0.2665940505921425,
            'baseline_A_volume': 0.26659403493314143,
            'baseline_peak_tree_rss_bytes': 38082981888,
            'baseline_workflow_wall_seconds': 12534.1825,
            'comparison_boundary': [
                'new runs use two y layers while the old iterative run used seven',
                'new runs use direct condensation instead of iterative P4/FGMRES',
            ],
        }
        return facts
    if identity in V7_ANISO_N0_P6_DIRECT_PROFILES:
        # Reuse only the immutable V7 physical/material/output and resource
        # facts.  This is a separate direct p6 route: no p4 operator or outer
        # Krylov/PC identity is exposed by these facts.
        facts = native_profile_facts(V7_ANISO_N0_P4_PROFILE)
        facts.update(
            identity=identity,
            execution_mode='full_solve',
            formal_runner='src.runners.p6_condensed_direct',
            route=(
                'V7_P6_CONDENSED_DIRECT_N0_GRID_D'
                if identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE
                else 'V7_P6_CONDENSED_DIRECT_N0'
            ),
        )
        if identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE:
            from src.geometry.v7_d_aniso_n0_p6_axis_plan import d_axis_plan

            plan = d_axis_plan()
            facts['allowed_mesh_targets_nm'] = [0.25]
            facts['component_options'].update(
                mesh_plan_id=plan['plan_id'],
                mesh_plan_sha256=plan['plan_sha256'],
                mesh_axis_cell_counts=plan['axis_cell_counts'],
                mesh_axis_sha256_le_f64=plan['axis_sha256_le_f64'],
                mesh_axis_segment_cell_counts=plan['segment_cell_counts'],
                grid_comparison_scope='CROSS_CHANGED_GRID_DIAGNOSTIC',
                no_cross_mesh_fe_reuse=True,
            )
            facts['component_options']['parent_mode_selection'] = dict(
                facts['component_options']['dtn_mode_selection']
            )
            facts['component_options']['volume_quadrature'] = {
                'degree': 15,
                'rule': 'default',
                'points_per_hexahedron': 512,
                'points_weights_sha256': (
                    'e3cf565f440b60b083a065f4655124926e98b047edea40d869cdfa5c66df9175'
                ),
            }
            facts['component_options']['surface_quadrature'] = {
                'degree': 160,
                'rule': 'default',
                'authority': 'full_32060_parent_inventory',
            }
            facts['condensed_route'].update(
                name='v7_d_p6_exact_local_condensation_direct_n0',
                mesh_plan_id=plan['plan_id'],
                mesh_plan_sha256=plan['plan_sha256'],
                mesh_axis_cell_counts=plan['axis_cell_counts'],
                grid_comparison_scope='CROSS_CHANGED_GRID_DIAGNOSTIC',
                mumps_out_of_core='forbidden_icntl23_must_read_back_zero',
            )
            facts['condensed_route'].pop('rows', None)
            facts['condensed_route']['rows_source'] = (
                'actual D mesh and MPC dof maps recorded before matrix assembly'
            )
            facts['campaign_authorization']['source'] = (
                'user-authorized single V7 candidate-D full grating diagnostic'
            )
            facts['campaign_authorization']['candidate_grid'] = {
                'scope': 'CROSS_CHANGED_GRID_DIAGNOSTIC',
                'mesh_plan_id': plan['plan_id'],
                'mesh_plan_sha256': plan['plan_sha256'],
                'axis_cell_counts': plan['axis_cell_counts'],
                'cell_count': 47_200,
                'x_segment_cell_counts': [66, 68, 66],
                'y_segment_cell_counts': [2],
                'z_segment_cell_counts': [9, 100, 9],
            }
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
        if identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE:
            from src.geometry.v7_d_aniso_n0_p6_axis_plan import d_axis_plan

            plan = d_axis_plan()
            facts['condensed_route'].pop('rows', None)
            facts['condensed_route'].update(
                name='v7_d_p6_exact_local_condensation_direct_n0',
                rows_source=(
                    'actual D mesh and MPC dof maps recorded before matrix assembly'
                ),
                mesh_plan_id=plan['plan_id'],
                mesh_plan_sha256=plan['plan_sha256'],
                mesh_axis_cell_counts=plan['axis_cell_counts'],
                grid_comparison_scope='CROSS_CHANGED_GRID_DIAGNOSTIC',
                mumps_out_of_core='forbidden_icntl23_must_read_back_zero',
            )
        facts['campaign_authorization']['source'] = (
            'user-authorized single V7 candidate-D full grating diagnostic'
            if identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE
            else 'user-authorized V7 p6 condensed direct full solve'
        )
        facts['campaign_authorization']['execution_mode'] = 'full_solve'
        facts['campaign_authorization']['direct_route'] = {
            'degree': 6,
            'active_mode_count': V7_N0_ACTIVE_MODE_COUNT,
            'parent_mode_count': V7_N0_PARENT_MODE_COUNT,
            'quadrature_inventory': 'parent_q160',
            'surface_quadrature_degree': 160,
            'volume_quadrature_degree': 15,
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
    """Return the explicit native profile for iterative or p6-direct routes."""

    solver = solver or {}
    if (
        str(method) == 'full3d_direct'
        and solver.get('native_capacity_profile')
        in P6_CONDENSED_DIRECT_PROFILES
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


def _validate_v6_f5_p6_direct_case(config, identity: str) -> None:
    """Lock the two new 5 nm direct runs to the old F5 physics and frozen axes."""

    from .input_loader import InputError
    from src.geometry.task39extra_v6_f5_mesh_plan import (
        F5_Y2_PLAN_ID,
        validate_frozen_f5_axes,
    )

    def require(section: str, key: str, expected: object) -> None:
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f'{identity} fixes {section}.{key}={expected!r}; got {actual!r}'
            )

    require('method', 'kind', 'full3d_direct')
    solver = config.get('solver', {})
    if solver.get('native_capacity_profile') != identity:
        raise InputError(f'{identity} is not selected as the direct profile')
    if solver.get('linear_solver') != 'direct':
        raise InputError(f'{identity} requires solver.linear_solver=direct')
    if solver.get('direct_solver_profile', 'default') != 'default':
        raise InputError(f'{identity} requires the default qualified MUMPS controls')
    forbidden_solver_fields = {
        'preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree'
    }.intersection(solver)
    if forbidden_solver_fields:
        raise InputError(
            f'{identity} forbids iterative/P4 fields: '
            + ', '.join(sorted(forbidden_solver_fields))
        )

    geometry = {
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
    for key, expected in geometry.items():
        require('geometry', key, expected)
    materials = config.get('materials', {})
    for key, expected in {
        'n_air': (1.0, 0.0),
        'mu_r': (1.0, 0.0),
        'n_substrate': (0.99396854453, 0.00435380777),
        'n_grating': (0.99396854453, 0.00435380777),
    }.items():
        actual = tuple(materials.get(key, ()))
        if actual != expected:
            raise InputError(
                f'{identity} fixes materials.{key}={expected!r}; got {actual!r}'
            )

    for key, expected in {
        'wavelength_nm': 5.0,
        'grazing_angle_deg': 1.0,
        'azimuth_deg': 0.0,
        'polarization': 's',
        'electric_amplitude': 1.0,
    }.items():
        require('incidence', key, expected)
    for key, expected in {
        'nedelec_degree': 6,
        'visualization_degree': 6,
        'mesh_target_nm': 4.0,
        'mesh_cell_type': 'hexahedron',
        'mesh_spacing_mode': 'boundary_fitted',
        'assembly_backend': 'standard_full',
        'floquet_constraint_mode': 'auto',
    }.items():
        require('discretization', key, expected)
    if config.get('discretization', {}).get('mesh_plan_id') != F5_Y2_PLAN_ID:
        raise InputError(f'{identity} requires the exact frozen F5 y2 axis plan')
    try:
        validate_frozen_f5_axes(config['discretization'])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f'{identity} has invalid frozen F5 axes: {exc}') from exc

    for key, expected in {
        'use_floquet_x': True,
        'use_floquet_y': True,
        'vertical_boundary': 'dtn_port',
        'scattering_background': 'layered',
        'dtn_order_policy': 'auto_propagating',
        'dtn_assembly': 'auxiliary',
        'use_pml': False,
    }.items():
        require('boundary', key, expected)
    execution = config.get('execution', {})
    if execution.get('mpi_size') != 1 or execution.get('time_limit_mode') != 'none':
        raise InputError(f'{identity} requires MPI1 and no workflow deadline')
    required_rss_gib = V7_RSS_HARD_LIMIT_BYTES / 2**30
    if execution.get('native_memory_policy') != 'interleave_nodes0_1':
        raise InputError(f'{identity} requires interleave_nodes0_1')
    if execution.get('require_zero_swap') is not False:
        raise InputError(f'{identity} observes swap without a zero-swap stop')
    if execution.get('warning_memory_gib') != 1_170_000_000_000 / 2**30:
        raise InputError(f'{identity} fixes the existing RSS warning level')
    for key in ('terminate_memory_gib', 'memory_limit_gb'):
        if execution.get(key) != required_rss_gib:
            raise InputError(f'{identity} fixes {key} to the 1.8e12-byte tree RSS cap')
    if config.get('output', {}).get('export_fields') is not True:
        raise InputError(f'{identity} requires full field output')
    if config.get('geometry', {}).get('cell_notch') is not None:
        raise InputError(f'{identity} does not permit a geometry notch')


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


def _validate_v7_d_p6_direct_case(config) -> None:
    """Validate candidate D as the one frozen x+z changed-grid direct route."""

    from copy import deepcopy

    from .input_loader import InputError
    from src.geometry.v7_d_aniso_n0_p6_axis_plan import (
        D_AXIS_COUNTS,
        D_AXIS_PLAN_ID,
        D_Z_PROFILE,
        validate_frozen_d_axes,
    )

    identity = V7_D_ANISO_N0_P6_DIRECT_PROFILE
    solver = config.get('solver', {})
    if config.get('method', {}).get('kind') != 'full3d_direct':
        raise InputError(f'{identity} is restricted to full3d_direct')
    if solver.get('native_capacity_profile') != identity:
        raise InputError(f'{identity} is not selected as the native direct profile')
    if solver.get('linear_solver') != 'direct':
        raise InputError(f'{identity} requires solver.linear_solver=direct')
    if solver.get('direct_solver_profile', 'default') != 'default':
        raise InputError(f'{identity} uses the qualified default MUMPS controls')
    forbidden_solver_fields = {
        'preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree'
    }.intersection(solver)
    if forbidden_solver_fields:
        raise InputError(
            f'{identity} forbids P4/iterative solver fields: '
            + ', '.join(sorted(forbidden_solver_fields))
        )

    discretization = config.get('discretization', {})
    if tuple(discretization.get('mesh_axis_cell_counts') or ()) != D_AXIS_COUNTS:
        raise InputError(f'{identity} fixes mesh_axis_cell_counts={D_AXIS_COUNTS}')
    if discretization.get('mesh_plan_id') != D_AXIS_PLAN_ID:
        raise InputError(f'{identity} requires its frozen candidate-D mesh plan')
    if discretization.get('mesh_axis_z_profile') != D_Z_PROFILE:
        raise InputError(f'{identity} has the wrong z segment profile identity')
    if discretization.get('mesh_target_nm') != 0.25:
        raise InputError(f'{identity} fixes the nominal x target to 0.25 nm')
    try:
        validate_frozen_d_axes(discretization)
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f'{identity} has invalid frozen axes: {exc}') from exc

    # Reuse the previously checked immutable V7 material, incidence, boundary,
    # output and resource requirements, while removing only the old grid and
    # solver identities from this validation copy.  The live D config remains
    # untouched and is bound to its own direct profile and mesh plan above.
    baseline = deepcopy(config)
    baseline['method']['kind'] = 'full3d_iterative'
    baseline_solver = baseline['solver']
    baseline_solver.pop('native_capacity_profile', None)
    baseline_solver.update(
        linear_solver='iterative',
        ksp_type='fgmres',
        preconditioner=V7_ANISO_N0_P4_PROFILE,
        restart=32,
        max_iterations=2048,
        coarse_degree=4,
    )
    baseline_discretization = baseline['discretization']
    baseline_discretization.update(
        mesh_target_nm=0.5,
        mesh_axis_cell_counts=[100, 2, 234],
    )
    for key in (
        'mesh_axis_x_values', 'mesh_axis_y_values', 'mesh_axis_z_values',
        'mesh_axis_z_profile', 'mesh_plan_id', 'mesh_plan_sha256',
    ):
        baseline_discretization.pop(key, None)
    _validate_v7_aniso_n0_p4_case(baseline)


def _validate_dispersion_flat_p6_case(config, identity: str) -> None:
    """Fail closed on approved same-material flat P6 direct cases."""

    from src.geometry.dispersion_flat_axis_plan import (
        flat_axis_plan,
        validate_frozen_dispersion_flat_axes,
    )

    from .input_loader import InputError

    if identity == DISPERSION_FLAT_P6_PROFILE:
        hard = DISPERSION_FLAT_RSS_HARD_LIMIT_BYTES
        planning = DISPERSION_FLAT_RSS_PLANNING_LIMIT_BYTES
    elif identity == DISPERSION_FLAT_P6_RAISED_RSS_PROFILE:
        hard = DISPERSION_FLAT_RAISED_RSS_HARD_LIMIT_BYTES
        planning = DISPERSION_FLAT_RAISED_RSS_PLANNING_LIMIT_BYTES
    else:
        raise InputError(f'{identity} is not an approved dispersion-flat P6 profile')

    def require(section: str, key: str, expected: object) -> None:
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f'{identity} fixes {section}.{key}={expected!r}; got {actual!r}'
            )

    require('method', 'kind', 'full3d_direct')
    solver = config.get('solver', {})
    if solver.get('native_capacity_profile') != identity:
        raise InputError(f'{identity} is not selected as the direct profile')
    if solver.get('linear_solver') != 'direct' or solver.get(
        'direct_solver_profile', 'default'
    ) != 'default':
        raise InputError(f'{identity} requires the qualified default direct solver')
    forbidden_solver_fields = {
        'preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree'
    }.intersection(solver)
    if forbidden_solver_fields:
        raise InputError(
            f'{identity} forbids a P4/iterative route: '
            + ', '.join(sorted(forbidden_solver_fields))
        )

    for key, expected in {
        'geometry_kind': 'flat_layer',
        'period_x_nm': 1.0,
        'period_y_nm': 25.0,
        'z_min_nm': -10.0,
        'z_max_nm': 130.0,
        'interface_z_nm': 0.0,
        'air_height_nm': 130.0,
        'substrate_thickness_nm': 10.0,
        'grating_width_x_nm': 0.0,
        'grating_width_y_nm': 0.0,
        'grating_height_nm': 0.0,
    }.items():
        require('geometry', key, expected)
    for key, expected in {
        'n_air': (1.0, 0.0),
        'mu_r': (1.0, 0.0),
        'n_substrate': MATERIALS[0.7],
        'n_grating': MATERIALS[0.7],
    }.items():
        actual = tuple(config.get('materials', {}).get(key, ()))
        if actual != tuple(expected):
            raise InputError(f'{identity} fixes materials.{key}={expected!r}')
    for key in ('substrate_name', 'grating_name'):
        if config.get('materials', {}).get(key) != USER_MATERIAL_METADATA[0.7]['material']:
            raise InputError(f'{identity} fixes materials.{key} to the recorded Si label')

    for key, expected in {
        'wavelength_nm': 0.7,
        'tilt_from_downward_z_deg': 89.0,
        'azimuth_deg': 0.0,
        'polarization': 's',
        'electric_amplitude': 1.0,
    }.items():
        require('incidence', key, expected)
    for key, expected in {
        'nedelec_degree': 6,
        'visualization_degree': 6,
        'mesh_cell_type': 'hexahedron',
        'mesh_spacing_mode': 'boundary_fitted',
        'assembly_backend': 'standard_full',
        'floquet_constraint_mode': 'auto',
    }.items():
        require('discretization', key, expected)
    target = float(config.get('discretization', {}).get('mesh_target_nm', -1.0))
    if target not in (0.5, 0.25, 0.125):
        raise InputError(f'{identity} allows mesh_target_nm in (0.5, 0.25, 0.125)')
    nx = round(1.0 / target)
    if nx not in (2, 4, 8) or target != 1.0 / nx:
        raise InputError(f'{identity} requires one of the exact x meshes 2/4/8')
    try:
        axes = validate_frozen_dispersion_flat_axes(config['discretization'])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f'{identity} has invalid flat mesh axes: {exc}') from exc
    plan = flat_axis_plan(nx)
    if tuple(config['discretization']['mesh_axis_cell_counts']) != tuple(
        plan['axis_cell_counts']
    ):
        raise InputError(f'{identity} mesh-axis counts differ from nx={nx}')
    if (axes['x'][0], axes['x'][-1], axes['y'][0], axes['y'][-1]) != (
        0.0, 1.0, 0.0, 25.0
    ) or (axes['z'][0], axes['z'][-1]) != (-10.0, 130.0):
        raise InputError(f'{identity} flat axes do not span the exact physical bounds')

    for key, expected in {
        'use_floquet_x': True,
        'use_floquet_y': True,
        'vertical_boundary': 'dtn_port',
        'scattering_background': 'layered',
        'dtn_order_policy': 'auto_propagating',
        'dtn_assembly': 'auxiliary',
        'use_pml': False,
    }.items():
        require('boundary', key, expected)
    execution = config.get('execution', {})
    if execution.get('mpi_size') != 1 or execution.get('time_limit_mode') != 'none':
        raise InputError(f'{identity} requires MPI1 and no workflow deadline')
    if execution.get('timeout_seconds') is not None:
        raise InputError(f'{identity} requires timeout_seconds=None')
    if execution.get('native_memory_policy') != 'interleave_nodes0_1':
        raise InputError(f'{identity} requires interleave_nodes0_1')
    if execution.get('require_zero_swap') is not True:
        raise InputError(f'{identity} requires zero swap')
    for key, expected in {
        'warning_memory_gib': planning / 2**30,
        'terminate_memory_gib': hard / 2**30,
        'memory_limit_gb': hard / 2**30,
    }.items():
        require('execution', key, expected)
    output = config.get('output', {})
    for key in (
        'export_fields', 'export_diffraction_orders', 'export_modal_amplitudes',
        'export_reference_planes',
    ):
        if output.get(key) is not True:
            raise InputError(f'{identity} requires output.{key}=true')
    if output.get('export_canonical_vectors') is not False:
        raise InputError(f'{identity} keeps large canonical-vector exports disabled')
    if tuple(output.get('reference_plane_z_nm') or ()) != (
        10.0, 30.0, 60.0, 90.0, 110.0
    ) or int(output.get('sample_count_y', 0)) < 4:
        raise InputError(f'{identity} requires the five planes and at least four y samples')


def _validate_task40_phi90_d13_case(config: dict, identity: str) -> None:
    """Validate one finite-R13 Task40 P6-direct directional mesh input."""
    from .input_loader import InputError

    case = TASK40_PHI90_D13_CASES[identity]

    def require(section: str, key: str, expected: object) -> None:
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f'{identity} fixes {section}.{key}={expected!r}; got {actual!r}'
            )

    require('method', 'kind', 'full3d_direct')
    solver = config.get('solver', {})
    require('solver', 'native_capacity_profile', identity)
    require('solver', 'linear_solver', 'direct')
    require('solver', 'direct_solver_profile', 'default')
    forbidden = {'preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree'} & set(solver)
    if forbidden:
        raise InputError(f'{identity} forbids iterative/P4 fields: {sorted(forbidden)}')
    for key, expected in {
        'model_id': 'si_block_phi90_50x50_17x20_h120',
    }.items():
        actual = config.get(key)
        if actual != expected:
            raise InputError(f'{identity} fixes {key}={expected!r}; got {actual!r}')
    for key, expected in {
        'geometry_kind': 'rectangular_block_grating',
        'period_x_nm': 50.0, 'period_y_nm': 50.0,
        'z_min_nm': -10.0, 'z_max_nm': 130.0,
        'interface_z_nm': 0.0, 'air_height_nm': 130.0,
        'substrate_thickness_nm': 10.0,
        'grating_width_x_nm': 17.0, 'grating_width_y_nm': 20.0,
        'grating_height_nm': 120.0,
    }.items():
        require('geometry', key, expected)
    materials = config.get('materials', {})
    expected_n = tuple(MATERIALS[13.5])
    for key, expected in {
        'n_air': (1.0, 0.0), 'mu_r': (1.0, 0.0),
        'n_substrate': expected_n, 'n_grating': expected_n,
    }.items():
        actual = tuple(materials.get(key, ()))
        if actual != expected:
            raise InputError(f'{identity} fixes materials.{key}={expected!r}')
    for key in ('substrate_name', 'grating_name'):
        if materials.get(key) != 'Si / silicon':
            raise InputError(f'{identity} fixes materials.{key} to the inherited Si label')
    for key, expected in {
        'wavelength_nm': 13.5, 'grazing_angle_deg': 1.0,
        'azimuth_deg': 90.0, 'polarization': 's', 'electric_amplitude': 1.0,
    }.items():
        require('incidence', key, expected)
    discretization = config.get('discretization', {})
    for key, expected in {
        'nedelec_degree': 6, 'visualization_degree': 6,
        'mesh_target_nm': 10.0, 'mesh_cell_type': 'hexahedron',
        'mesh_spacing_mode': 'boundary_fitted',
        'assembly_backend': 'standard_full', 'floquet_constraint_mode': 'auto',
    }.items():
        require('discretization', key, expected)
    actual_axis_counts = discretization.get('mesh_axis_cell_counts')
    if case["case"] == "B":
        for key in (
            'mesh_axis_cell_counts', 'mesh_axis_x_values', 'mesh_axis_y_values',
            'mesh_axis_z_values', 'mesh_axis_z_profile', 'mesh_plan_id',
            'mesh_plan_sha256',
        ):
            if discretization.get(key) is not None:
                raise InputError(
                    f'{identity} derives its h10 baseline mesh; {key} must be omitted'
                )
    else:
        from src.geometry.task40_phi90_d13_axis_plan import (
            validate_frozen_d13_axes,
        )

        frozen_payload = {
            'mesh_plan_id': discretization.get('mesh_plan_id'),
            'mesh_plan_sha256': discretization.get('mesh_plan_sha256'),
            'mesh_axis_cell_counts': actual_axis_counts,
            'mesh_axis_x_values': discretization.get('mesh_axis_x_values'),
            'mesh_axis_y_values': discretization.get('mesh_axis_y_values'),
            'mesh_axis_z_values': discretization.get('mesh_axis_z_values'),
        }
        try:
            validate_frozen_d13_axes(frozen_payload)
        except ValueError as exc:
            raise InputError(f'{identity} has an invalid frozen D13 mesh: {exc}') from exc
        if tuple(actual_axis_counts or ()) != tuple(case["axis_cell_counts"]):
            raise InputError(
                f'{identity} fixes mesh_axis_cell_counts='
                f'{case["axis_cell_counts"]}; got {actual_axis_counts!r}'
            )
        if discretization.get('mesh_axis_z_profile') is not None:
            raise InputError(f'{identity} does not use a z-profile alias')
    for key, expected in {
        'use_floquet_x': True, 'use_floquet_y': True,
        'vertical_boundary': 'dtn_port', 'scattering_background': 'layered',
        'dtn_order_policy': 'auto_propagating', 'dtn_assembly': 'auxiliary',
        'use_pml': False,
    }.items():
        require('boundary', key, expected)
    execution = config.get('execution', {})
    for key, expected in {
        'mpi_size': 1, 'time_limit_mode': 'none', 'timeout_seconds': None,
        'require_zero_swap': False, 'native_memory_policy': 'interleave_nodes0_1',
    }.items():
        require('execution', key, expected)
    if not (0 < float(execution.get('warning_memory_gib', 0))
            < float(execution.get('terminate_memory_gib', 0))):
        raise InputError(f'{identity} requires positive ordered legacy diagnostic fields')
    output = config.get('output', {})
    for key in ('export_fields', 'export_diffraction_orders', 'export_modal_amplitudes',
                'export_reference_planes'):
        if output.get(key) is not True:
            raise InputError(f'{identity} requires output.{key}=true')
    if output.get('export_canonical_vectors') is not False:
        raise InputError(f'{identity} keeps large canonical-vector export disabled')
    if tuple(output.get('reference_plane_z_nm') or ()) != (10.0, 30.0, 60.0, 90.0, 110.0):
        raise InputError(f'{identity} fixes the five reference planes')
    if int(output.get('sample_count_y', 0)) < 64:
        raise InputError(f'{identity} requires at least 64 full-3D y samples for phase resolution')


def _validate_task40_phi90_d15_case(config: dict, identity: str) -> None:
    """Validate D15 axes, then reuse the D13 baseline's unchanged physics contract."""
    from copy import deepcopy

    from src.geometry.task40_phi90_d15_axis_plan import validate_frozen_d15_axes
    from .input_loader import InputError

    facts = _task40_phi90_d15_profile_facts(identity)
    comparison = facts["component_options"]["directional_mesh_comparison"]
    discretization = config.get("discretization", {})
    if discretization.get("mesh_target_nm") != 15.0:
        raise InputError(f"{identity} fixes discretization.mesh_target_nm=15.0")
    payload = {
        "mesh_plan_id": discretization.get("mesh_plan_id"),
        "mesh_plan_sha256": discretization.get("mesh_plan_sha256"),
        "mesh_axis_cell_counts": discretization.get("mesh_axis_cell_counts"),
        "mesh_axis_x_values": discretization.get("mesh_axis_x_values"),
        "mesh_axis_y_values": discretization.get("mesh_axis_y_values"),
        "mesh_axis_z_values": discretization.get("mesh_axis_z_values"),
    }
    try:
        validate_frozen_d15_axes(payload)
    except ValueError as exc:
        raise InputError(f"{identity} has invalid frozen D15 axes: {exc}") from exc
    if tuple(payload["mesh_axis_cell_counts"] or ()) != tuple(
        comparison["axis_cell_counts"]
    ):
        raise InputError(f"{identity} D15 counts differ from profile facts")
    if discretization.get("mesh_axis_z_profile") is not None:
        raise InputError(f"{identity} does not use a z-profile alias")

    # All non-axis fields are frozen by the already tested D13-B physical,
    # mode, integration, output, and direct-solver contract.
    inherited = deepcopy(config)
    inherited.setdefault("solver", {})[
        "native_capacity_profile"
    ] = TASK40_PHI90_D13_B_P6_DIRECT_PROFILE
    inherited_discretization = inherited["discretization"]
    inherited_discretization["mesh_target_nm"] = 10.0
    for key in (
        "mesh_axis_cell_counts",
        "mesh_axis_x_values",
        "mesh_axis_y_values",
        "mesh_axis_z_values",
        "mesh_axis_z_profile",
        "mesh_plan_id",
        "mesh_plan_sha256",
    ):
        inherited_discretization.pop(key, None)
    _validate_task40_phi90_d13_case(
        inherited, TASK40_PHI90_D13_B_P6_DIRECT_PROFILE
    )


def _validate_task40_phi90_h15_case(config: dict, identity: str) -> None:
    """Validate one explicit H15 base/refinement input without D13 aliases."""
    from src.geometry.task40_phi90_h15_axis_plan import validate_frozen_h15_axes
    from .input_loader import InputError

    facts = _task40_phi90_h15_profile_facts(identity)
    comparison = facts["component_options"]["directional_mesh_comparison"]

    def require(section: str, key: str, expected: object) -> None:
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f'{identity} fixes {section}.{key}={expected!r}; got {actual!r}'
            )

    require('method', 'kind', 'full3d_direct')
    solver = config.get('solver', {})
    require('solver', 'native_capacity_profile', identity)
    require('solver', 'linear_solver', 'direct')
    require('solver', 'direct_solver_profile', 'default')
    forbidden = {'preconditioner', 'ksp_type', 'restart', 'max_iterations', 'coarse_degree'} & set(solver)
    if forbidden:
        raise InputError(f'{identity} forbids iterative/P4 fields: {sorted(forbidden)}')
    if config.get('model_id') != 'si_block_phi90_50x50_17x20_h120':
        raise InputError(f'{identity} fixes model_id=si_block_phi90_50x50_17x20_h120')
    for key, expected in {
        'geometry_kind': 'rectangular_block_grating',
        'period_x_nm': 50.0, 'period_y_nm': 50.0,
        'z_min_nm': -10.0, 'z_max_nm': 130.0,
        'interface_z_nm': 0.0, 'air_height_nm': 130.0,
        'substrate_thickness_nm': 10.0,
        'grating_width_x_nm': 17.0, 'grating_width_y_nm': 20.0,
        'grating_height_nm': 120.0,
    }.items():
        require('geometry', key, expected)
    materials = config.get('materials', {})
    expected_n = tuple(MATERIALS[13.5])
    for key, expected in {
        'n_air': (1.0, 0.0), 'mu_r': (1.0, 0.0),
        'n_substrate': expected_n, 'n_grating': expected_n,
    }.items():
        if tuple(materials.get(key, ())) != expected:
            raise InputError(f'{identity} fixes materials.{key}={expected!r}')
    for key in ('substrate_name', 'grating_name'):
        if materials.get(key) != 'Si / silicon':
            raise InputError(f'{identity} fixes materials.{key} to the inherited Si label')
    for key, expected in {
        'wavelength_nm': 13.5, 'grazing_angle_deg': 1.0,
        'azimuth_deg': 90.0, 'polarization': 's', 'electric_amplitude': 1.0,
    }.items():
        require('incidence', key, expected)
    discretization = config.get('discretization', {})
    for key, expected in {
        'nedelec_degree': 6, 'visualization_degree': 6,
        'mesh_target_nm': 15.0, 'mesh_cell_type': 'hexahedron',
        'mesh_spacing_mode': 'boundary_fitted',
        'assembly_backend': 'standard_full', 'floquet_constraint_mode': 'auto',
    }.items():
        require('discretization', key, expected)
    payload = {
        'mesh_plan_id': discretization.get('mesh_plan_id'),
        'mesh_plan_sha256': discretization.get('mesh_plan_sha256'),
        'mesh_axis_cell_counts': discretization.get('mesh_axis_cell_counts'),
        'mesh_axis_x_values': discretization.get('mesh_axis_x_values'),
        'mesh_axis_y_values': discretization.get('mesh_axis_y_values'),
        'mesh_axis_z_values': discretization.get('mesh_axis_z_values'),
    }
    try:
        validate_frozen_h15_axes(payload)
    except ValueError as exc:
        raise InputError(f'{identity} has an invalid frozen H15 mesh: {exc}') from exc
    if tuple(payload['mesh_axis_cell_counts'] or ()) != tuple(
        comparison['axis_cell_counts']
    ):
        raise InputError(f'{identity} H15 axis cell counts differ from profile facts')
    if discretization.get('mesh_axis_z_profile') is not None:
        raise InputError(f'{identity} does not use a z-profile alias')
    for key, expected in {
        'use_floquet_x': True, 'use_floquet_y': True,
        'vertical_boundary': 'dtn_port', 'scattering_background': 'layered',
        'dtn_order_policy': 'auto_propagating', 'dtn_assembly': 'auxiliary',
        'use_pml': False,
    }.items():
        require('boundary', key, expected)
    execution = config.get('execution', {})
    for key, expected in {
        'mpi_size': 1, 'time_limit_mode': 'none', 'timeout_seconds': None,
        'require_zero_swap': False, 'native_memory_policy': 'interleave_nodes0_1',
    }.items():
        require('execution', key, expected)
    if not (0 < float(execution.get('warning_memory_gib', 0))
            < float(execution.get('terminate_memory_gib', 0))):
        raise InputError(f'{identity} requires positive ordered diagnostic memory fields')
    output = config.get('output', {})
    for key in ('export_fields', 'export_diffraction_orders', 'export_modal_amplitudes',
                'export_reference_planes'):
        if output.get(key) is not True:
            raise InputError(f'{identity} requires output.{key}=true')
    if output.get('export_canonical_vectors') is not False:
        raise InputError(f'{identity} keeps large canonical-vector exports disabled')
    if tuple(output.get('reference_plane_z_nm') or ()) != (
        10.0, 30.0, 60.0, 90.0, 110.0
    ):
        raise InputError(f'{identity} fixes the five reference planes')
    if int(output.get('sample_count_y', 0)) < 64:
        raise InputError(f'{identity} requires at least 64 full-3D y samples')


def _validate_task40_phi90_d5_case(config: dict, identity: str) -> None:
    """Validate one fixed-budget 5 nm direct D5 input and exact frozen axes."""
    from src.geometry.task40_phi90_d5_axis_plan import validate_frozen_d5_axes
    from .input_loader import InputError

    facts = _task40_phi90_d5_profile_facts(identity)
    comparison = facts["component_options"]["directional_mesh_comparison"]

    def require(section: str, key: str, expected: object) -> None:
        actual = config.get(section, {}).get(key)
        if actual != expected:
            raise InputError(
                f"{identity} fixes {section}.{key}={expected!r}; got {actual!r}"
            )

    require("method", "kind", "full3d_direct")
    solver = config.get("solver", {})
    require("solver", "native_capacity_profile", identity)
    require("solver", "linear_solver", "direct")
    require("solver", "direct_solver_profile", "default")
    forbidden = {
        "preconditioner", "ksp_type", "restart", "max_iterations", "coarse_degree"
    } & set(solver)
    if forbidden:
        raise InputError(f"{identity} forbids iterative/P4 fields: {sorted(forbidden)}")
    if config.get("model_id") != "si_block_phi90_50x50_17x20_h120":
        raise InputError(f"{identity} fixes model_id=si_block_phi90_50x50_17x20_h120")
    for key, expected in {
        "geometry_kind": "rectangular_block_grating",
        "period_x_nm": 50.0, "period_y_nm": 50.0,
        "z_min_nm": -10.0, "z_max_nm": 130.0,
        "interface_z_nm": 0.0, "air_height_nm": 130.0,
        "substrate_thickness_nm": 10.0,
        "grating_width_x_nm": 17.0, "grating_width_y_nm": 20.0,
        "grating_height_nm": 120.0,
    }.items():
        require("geometry", key, expected)
    expected_n = tuple(MATERIALS[5.0])
    materials = config.get("materials", {})
    for key, expected in {
        "n_air": (1.0, 0.0), "mu_r": (1.0, 0.0),
        "n_substrate": expected_n, "n_grating": expected_n,
    }.items():
        if tuple(materials.get(key, ())) != expected:
            raise InputError(f"{identity} fixes materials.{key}={expected!r}")
    for key in ("substrate_name", "grating_name"):
        if materials.get(key) != "Si / silicon":
            raise InputError(f"{identity} fixes materials.{key} to the Si label")
    for key, expected in {
        "wavelength_nm": 5.0, "grazing_angle_deg": 1.0,
        "azimuth_deg": 90.0, "polarization": "s", "electric_amplitude": 1.0,
    }.items():
        require("incidence", key, expected)
    discretization = config.get("discretization", {})
    for key, expected in {
        "nedelec_degree": 6, "visualization_degree": 6,
        "mesh_target_nm": 4.0, "mesh_cell_type": "hexahedron",
        "mesh_spacing_mode": "boundary_fitted",
        "assembly_backend": "standard_full", "floquet_constraint_mode": "auto",
    }.items():
        require("discretization", key, expected)
    frozen = {
        "mesh_plan_id": discretization.get("mesh_plan_id"),
        "mesh_plan_sha256": discretization.get("mesh_plan_sha256"),
        "mesh_axis_cell_counts": discretization.get("mesh_axis_cell_counts"),
        "mesh_axis_x_values": discretization.get("mesh_axis_x_values"),
        "mesh_axis_y_values": discretization.get("mesh_axis_y_values"),
        "mesh_axis_z_values": discretization.get("mesh_axis_z_values"),
    }
    try:
        validate_frozen_d5_axes(frozen)
    except ValueError as exc:
        raise InputError(f"{identity} has invalid frozen D5 axes: {exc}") from exc
    if tuple(frozen["mesh_axis_cell_counts"] or ()) != tuple(
        comparison["axis_cell_counts"]
    ):
        raise InputError(f"{identity} D5 axis counts differ from profile facts")
    if discretization.get("mesh_axis_z_profile") is not None:
        raise InputError(f"{identity} uses explicit D5 axes, not a z-profile alias")
    for key, expected in {
        "use_floquet_x": True, "use_floquet_y": True,
        "vertical_boundary": "dtn_port", "scattering_background": "layered",
        "dtn_order_policy": "auto_propagating", "dtn_assembly": "auxiliary",
        "use_pml": False,
    }.items():
        require("boundary", key, expected)
    execution = config.get("execution", {})
    for key, expected in {
        "mpi_size": 1, "time_limit_mode": "none", "timeout_seconds": None,
        "require_zero_swap": False, "native_memory_policy": "interleave_nodes0_1",
    }.items():
        require("execution", key, expected)
    if not (0 < float(execution.get("warning_memory_gib", 0))
            < float(execution.get("terminate_memory_gib", 0))):
        raise InputError(f"{identity} requires positive ordered diagnostic memory fields")
    output = config.get("output", {})
    for key in (
        "export_fields", "export_diffraction_orders", "export_modal_amplitudes",
        "export_reference_planes",
    ):
        if output.get(key) is not True:
            raise InputError(f"{identity} requires output.{key}=true")
    if output.get("export_canonical_vectors") is not False:
        raise InputError(f"{identity} keeps canonical-vector export disabled")
    if tuple(output.get("reference_plane_z_nm") or ()) != (
        10.0, 30.0, 60.0, 90.0, 110.0
    ):
        raise InputError(f"{identity} fixes the five reference planes")
    if int(output.get("sample_count_y", 0)) < 64:
        raise InputError(f"{identity} requires at least 64 phase-resolving y samples")
    if output.get("diffraction_order_max_m") != 11 or output.get(
        "diffraction_order_max_n"
    ) != 20:
        raise InputError(f"{identity} requires R5 output envelope m11/n20")


def _validate_task40_phi90_r14_case(config: dict, identity: str) -> None:
    """Validate the unchanged Y2 physics/mesh plus the distinct R14 output range."""
    from copy import deepcopy

    from .input_loader import InputError

    comparison_config = deepcopy(config)
    comparison_config.setdefault('solver', {})[
        'native_capacity_profile'
    ] = TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE
    _validate_task40_phi90_d13_case(
        comparison_config, TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE
    )
    output = config.get('output', {})
    if output.get('diffraction_order_max_m') != 5:
        raise InputError(f'{identity} requires output.diffraction_order_max_m=5')
    if output.get('diffraction_order_max_n') != 9:
        raise InputError(f'{identity} requires output.diffraction_order_max_n=9')


def validate_native_case(config):
    """Validate only the campaign's frozen physical and numerical choices."""
    from .input_loader import InputError
    identity = native_capacity_profile_identity(
        config.get('method', {}).get('kind'), config['solver']
    )
    if identity in TASK40_PHI90_P6_DIRECT_PROFILES:
        if identity in TASK40_PHI90_D5_PROFILES:
            _validate_task40_phi90_d5_case(config, identity)
        elif identity in TASK40_PHI90_D15_PROFILES:
            _validate_task40_phi90_d15_case(config, identity)
        elif identity in TASK40_PHI90_H15_PROFILES:
            _validate_task40_phi90_h15_case(config, identity)
        elif identity == TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE:
            _validate_task40_phi90_r14_case(config, identity)
        else:
            _validate_task40_phi90_d13_case(config, identity)
        return
    if identity in DISPERSION_FLAT_P6_PROFILES:
        _validate_dispersion_flat_p6_case(config, identity)
        return
    if identity in V6_F5_P6_DIRECT_PROFILES:
        _validate_v6_f5_p6_direct_case(config, identity)
        return
    if identity in V7_ANISO_N0_P6_DIRECT_PROFILES:
        if identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE:
            _validate_v7_d_p6_direct_case(config)
            return
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
