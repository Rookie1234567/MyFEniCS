from __future__ import annotations

from src.common.modes_3d import outgoing_port_modes_3d
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.native_capacity_profile import (
    TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE,
    TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import _direct_run_contract
from src.test.stage2_test_utils import stage4_block_config

R14_DAT = "input/task40para_phi90_mesh_modes_direct/d13_r14_from_y2_p6_direct.dat"
Y2_DAT = "input/task40para_phi90_mesh_modes_direct/d13_y2_r13_p6_direct.dat"


def _cfg(max_m: int, max_n: int):
    cfg = stage4_block_config(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="explicit_rectangle",
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


def test_r14_resolves_same_y2_mesh_and_freezes_only_reference_mode_expansion():
    r14 = load_and_resolve(R14_DAT).as_jsonable()
    y2 = load_and_resolve(Y2_DAT).as_jsonable()
    facts = native_profile_facts(TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE)
    y2_facts = native_profile_facts(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    mode = facts["component_options"]["mode_selection"]
    options = facts["component_options"]

    assert r14["model_id"] == y2["model_id"] == "si_block_phi90_50x50_17x20_h120"
    assert r14["geometry"] == y2["geometry"]
    assert r14["materials"] == y2["materials"]
    assert r14["incidence"] == y2["incidence"]
    assert r14["discretization"] == y2["discretization"]
    assert r14["solver"]["native_capacity_profile"] == TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE
    assert r14["run_id"] == "task40_phi90_13p5_D13_R14_from_Y2_p6_direct_v1"
    assert r14["output"]["diffraction_order_max_m"] == 5
    assert r14["output"]["diffraction_order_max_n"] == 9

    assert mode["reference_mode_label"] == "R14"
    assert mode["expected_mode_count"] == 836
    assert mode["expected_mode_sha256"] == (
        "deefaa839044a2542560b60b68a457c4f127eee2221d6dd8477c3d49fb1a860e"
    )
    assert mode["parent_rectangle_max_abs_m_n"] == [5, 9]
    assert mode["active_rectangle_max_abs_m_n"] == [5, 9]
    assert mode["parent_inventory_scope"] == "R14_finite_rectangle_including_evanescent"
    assert options["mode_selection"]["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert options["surface_quadrature"]["degree"] == 28
    assert options["surface_quadrature"]["fixed_comparison_envelope"] == {
        "max_abs_m": 6,
        "max_abs_n": 10,
    }
    assert options["volume_quadrature"] == y2_facts["component_options"]["volume_quadrature"]
    assert options["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert options["dtn_sparse_cutoff_relative_tolerance"] == 1.0e-13


def test_r14_direct_route_uses_836_modes_and_does_not_change_r13_contract():
    route = _direct_run_contract(TASK40_PHI90_D13_R14_P6_DIRECT_PROFILE)
    r13 = _direct_run_contract(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    assert route["parent_count"] == route["active_count"] == 836
    assert route["expected_mode_sha256"] == (
        "deefaa839044a2542560b60b68a457c4f127eee2221d6dd8477c3d49fb1a860e"
    )
    assert route["reference_mode_label"] == "R14"
    assert route["parent_rectangle_max_abs_m_n"] == [5, 9]
    assert route["active_rectangle_max_abs_m_n"] == [5, 9]
    assert route["surface_quadrature_degree"] == 28
    assert route["residual_scope"].endswith("R14_active_rectangle")
    assert route["summary_prefix"].endswith("_R14")
    assert r13["parent_count"] == r13["active_count"] == 612
    assert r13["parent_rectangle_max_abs_m_n"] == [4, 8]
    assert r13["reference_mode_label"] == "R13"
    assert r13["surface_quadrature_degree"] == 28


def test_r14_inventory_contains_exact_836_modes_with_evanescents_and_both_ports():
    modes = outgoing_port_modes_3d(_cfg(5, 9))
    expected = {(m, n) for m in range(-5, 6) for n in range(-9, 10)}
    assert len(modes) == 836
    assert {(mode.m, mode.n) for mode in modes} == expected
    assert {mode.side for mode in modes} == {"top", "bottom"}
    assert {mode.polarization for mode in modes} == {"s", "p"}
    assert any(not mode.propagating for mode in modes)


def test_r14_profile_rejects_a_postprocess_window_that_omits_reference_orders():
    resolved = load_and_resolve(R14_DAT).as_jsonable()
    invalid = dict(resolved)
    invalid["solver"] = dict(resolved["solver"])
    invalid["output"] = dict(resolved["output"])
    invalid["output"]["diffraction_order_max_n"] = 8
    try:
        validate_native_case(invalid)
    except InputError as exc:
        assert "diffraction_order_max_n=9" in str(exc)
    else:
        raise AssertionError("R14 must reject a reporting window that omits n=±9")
