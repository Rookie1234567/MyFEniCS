from __future__ import annotations

import pytest

from src.common.modes_3d import outgoing_port_modes_3d
from src.test.stage2_test_utils import stage4_block_config


def _task40_cfg(policy="explicit_rectangle", max_m=2, max_n=2):
    cfg = stage4_block_config(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy=policy,
        stage4_dtn_assembly="auxiliary",
        lambda0=13.5,
        period_x=50.0,
        period_y=50.0,
        z_min=-10.0,
        z_max=130.0,
        n_air=1.0 + 0.0j,
        n_substrate=0.999002304859 + 0.00182649365j,
        n_grating=0.999002304859 + 0.00182649365j,
        incident_theta_deg=89.0,
        incident_phi_deg=90.0,
        polarization_kind="s",
        use_floquet_xy=True,
    )
    cfg.task40_dtn_rectangle_max_m = max_m
    cfg.task40_dtn_rectangle_max_n = max_n
    return cfg


def test_explicit_rectangle_is_exact_and_keeps_evanescent_both_polarizations():
    modes = outgoing_port_modes_3d(_task40_cfg())
    expected_orders = {(m, n) for m in range(-2, 3) for n in range(-2, 3)}
    assert len(modes) == 2 * 25 * 2
    assert {(mode.m, mode.n) for mode in modes} == expected_orders
    assert {mode.side for mode in modes} == {"top", "bottom"}
    assert {mode.polarization for mode in modes} == {"s", "p"}
    assert any(not mode.propagating for mode in modes)
    assert all(mode.beta is not None and mode.e_vector.shape == (3,) for mode in modes)


def test_explicit_rectangle_is_not_legacy_manual_max_user_auto():
    explicit = outgoing_port_modes_3d(_task40_cfg("explicit_rectangle", 2, 2))
    manual_cfg = _task40_cfg("manual", 2, 2)
    manual_cfg.diffraction_order_max_m = 2
    manual_cfg.diffraction_order_max_n = 2
    manual = outgoing_port_modes_3d(manual_cfg)
    assert len(explicit) == 100
    assert len(manual) > len(explicit)
    assert max(abs(mode.m) for mode in explicit) == 2
    assert max(abs(mode.n) for mode in explicit) == 2


@pytest.mark.parametrize(
    ("max_m", "max_n"),
    [(None, 2), (2, None), (-1, 2), (2, -1), (True, 2), (2, 2.0)],
)
def test_explicit_rectangle_requires_explicit_nonnegative_integer_bounds(max_m, max_n):
    with pytest.raises(ValueError, match="explicit_rectangle"):
        outgoing_port_modes_3d(_task40_cfg("explicit_rectangle", max_m, max_n))


def test_task40_d13_input_resolves_only_direct_identity_with_fixed_q28_and_dense_y_samples():
    from src.io import load_and_resolve
    from src.io.native_capacity_profile import (
        TASK40_PHI90_D13_B_P6_DIRECT_PROFILE,
        native_profile_facts,
    )

    specification = load_and_resolve(
        "input/task40para_phi90_mesh_modes_direct/d13_b_r13_p6_direct.dat"
    )
    resolved = specification.as_jsonable()
    facts = native_profile_facts(TASK40_PHI90_D13_B_P6_DIRECT_PROFILE)
    assert resolved["model_id"] == "si_block_phi90_50x50_17x20_h120"
    assert resolved["run_id"] == "task40_phi90_13p5_D13_B_p6_direct_v1"
    assert resolved["materials"]["n_grating"] == [0.999002304859, 0.00182649365]
    assert resolved["incidence"]["azimuth_deg"] == 90.0
    assert resolved["execution"]["timeout_seconds"] is None
    assert resolved["output"]["sample_count_y"] >= 64
    assert facts["component_options"]["surface_quadrature"]["degree"] == 28
    assert facts["component_options"]["surface_quadrature"]["fixed_comparison_envelope"] == {
        "max_abs_m": 6, "max_abs_n": 10,
    }
    assert facts["condensed_route"]["condensed_residual_relative_gate"] == 1.0e-9
    assert facts["condensed_route"]["max_same_factor_correction_solves"] == 2
    assert facts["condensed_route"]["release_after"] == (
        "independent_native_A6_and_complete_p6_storage_recovery"
    )
    assert facts["condensed_route"]["release_before"] == (
        "field_and_absorption_output_postprocessing"
    )
    assert facts["condensed_route"]["materialized_matrix_owner"] == (
        "AssemblyTimeCondensedSystem"
    )
    assert facts["condensed_route"]["borrowed_action_owns_matrix"] is False
    assert facts["campaign_authorization"]["direct_route"]["same_factor_lifecycle"] == {
        "symbolic_calls": 1,
        "numeric_calls": 1,
        "initial_solve_calls": 1,
        "same_factor_correction_solve_calls_max": 2,
        "total_solve_calls_max": 3,
    }
    assert facts["task40_material_identity"]["model_id"] == resolved["model_id"]
    assert facts["task40_material_identity"]["index_values"] == [
        0.999002304859,
        0.00182649365,
    ]
    assert not ({"intermediate", "fine_auxiliary", "balanced", "inner"} & set(facts))
