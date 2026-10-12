"""Scope/authority negative checks without a new PDE or factor."""

from copy import deepcopy

import pytest

from benchmarks.v7_anisotropic_n0_checker import v7_contract_errors
from src.io.native_capacity_profile import V7_ANISO_N0_P4_PROFILE, native_profile_facts


def record():
    profile = native_profile_facts(V7_ANISO_N0_P4_PROFILE)
    selection = dict(profile["component_options"]["dtn_mode_selection"])
    selection["active_mode_sha256"] = selection["expected_active_mode_sha256"]
    return {
        "experiment": "V7_ANISOTROPIC_N0_P4_FULL",
        "execution_mode": "full_solve",
        "complete_solve": True,
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
        "profile": profile,
        "operator_selection": selection,
        "retained_runtime": {
            "mode_count": 572,
            "mode_sha256": selection["active_mode_sha256"],
            "coarse_operator": {
                "degree": 4,
                "name": "A4",
                "residual_scope": "A4_n0",
                "relative_residual_limit": 1e-10,
                "maximum_extra_same_factor_refinements": 2,
            },
        },
        "v7_mesh_qa": {
            "status": "PASS",
            "actual_global_cell_count": 46800,
            "actual_axis_cell_counts": [100, 2, 234],
            "jacobian": {"all_positive": True, "minimum": 3.6},
            "cell_tag_y_invariance": {"tags_constant_for_each_xz_column": True},
        },
        "n0_functional_preparation": {
            str(degree): {"dtn_quadrature_degree": 160} for degree in (6, 4)
        },
        "pre_release_a6": {"operator_scope": "A6_n0"},
        "post_release_a6": {"operator_scope": "A6_n0"},
        "residual_arrays": {"operator_scope": "A6_n0"},
        "solve": {"physical_residual_key": "A6_n0_relative"},
        "full_dtn_endpoint_check": {
            "status": "FULL_DTN_NOT_VERIFIED",
            "A6_full_relative": None,
        },
        "v7_output_audit": {
            "authority": "AUTHORITY_LIMITED",
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "omitted_channel_values": "NOT_COMPUTED",
            "same_field_truncation": {
                "status": "OBSERVED_NOT_A84_SOLUTION",
                "omitted_mode_count": 488,
                "retained_A84_count": 84,
                "new_factor_calls": 0,
                "new_PDE_calls": 0,
                "delta20": 0.5,
                "b572_minus_A84_u572_relative": 0.51,
            },
            "power_groups": {"tail20_power": 0.1},
            "y_diagnostics": {
                "y_nm": [1, 5, 10, 20],
                "phase_fitting": False,
                "threshold_role": "diagnostic_warning_only",
            },
            "future_A84_screen_is_current_solve_gate": False,
        },
    }


def test_future_truncation_failure_does_not_veto_current_572_solution():
    # This fixture checks added scope conditions only; shared full numerical and
    # physical gates are exercised by the same retained checker at runtime.
    assert not v7_contract_errors(record())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("execution_mode",), "pilot_16"),
        (("complete_solve",), False),
        (("v7_mesh_qa", "actual_global_cell_count"), 530856),
        (("v7_mesh_qa", "jacobian", "minimum"), -1.0),
        (("n0_functional_preparation", "4", "dtn_quadrature_degree"), 40),
        (("residual_arrays", "operator_scope"), "A6_full"),
        (("retained_runtime", "coarse_operator", "degree"), 3),
        (("profile", "outer", "planned_stop_iteration"), 16),
        (("profile", "resources", "rss_hard_limit_bytes"), 1300000000000),
        (("solve", "physical_residual_key"), "original_A6_relative"),
        (("full_dtn_endpoint_check", "A6_full_relative"), 0.0),
        (("v7_output_audit", "omitted_channel_values"), "MEASURED_ZERO"),
        (("v7_output_audit", "same_field_truncation", "delta20"), float("nan")),
        (("v7_output_audit", "same_field_truncation", "new_factor_calls"), 1),
    ],
)
def test_scope_or_gate_changes_are_rejected(path, value):
    data = deepcopy(record())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert v7_contract_errors(data)
