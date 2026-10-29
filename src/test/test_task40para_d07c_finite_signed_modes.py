"""D07C signed-window, q81, frozen-axis, and 0.7 nm direct-input contract."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise, product
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.common.modes_3d import (
    enumerate_diffraction_orders_3d,
)
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d07c_axis_plan import (
    D07C_AXIS_PLANS,
    d07c_axis_plan,
)
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D07C_PROFILE_BY_CASE,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_output_policy,
    _direct_run_contract,
    _task40_d07c_mesh_evidence,
)
from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40para_phi90_mesh_modes_direct"
EXPECTED_MODE_COUNT = 37_700
EXPECTED_MODE_SHA = "fad8f4be8404605d5e75cd6f19506890689e10f7d81367ef44aaadb9437e7873"
EXPECTED_PROPAGATING = 35_784
EXPECTED_POWER_CARRYING = 36_744
EXPECTED_TAGS = {
    "B": {"1": 600, "2": 312, "3": 24},
    "Y1": {"1": 696, "2": 360, "3": 24},
    "Y2": {"1": 680, "2": 360, "3": 40},
}


def _independent_midpoint_tags(plan):
    tags = Counter()
    axes = plan["axes_nm"]
    for x0, x1 in pairwise(axes["x"]):
        xm = (x0 + x1) / 2.0
        for y0, y1 in pairwise(axes["y"]):
            ym = (y0 + y1) / 2.0
            for z0, z1 in pairwise(axes["z"]):
                zm = (z0 + z1) / 2.0
                if zm < 0.0:
                    tag = "2"
                elif zm < 120.0 and 16.5 < xm < 33.5 and 15.0 < ym < 35.0:
                    tag = "3"
                else:
                    tag = "1"
                tags[tag] += 1
    return {key: int(tags[key]) for key in ("1", "2", "3")}


def _resolved_case(case):
    path = INPUT_DIR / f"d07c_{case.lower()}_m32_nminus143_to1_p6_direct.dat"
    specification = load_and_resolve(path)
    return path, specification, specification.as_jsonable()


@pytest.mark.parametrize("case", ("B", "Y1", "Y2"))
def test_d07c_dat_profile_and_real_axis_planner_bind_each_case(case):
    path, _specification, resolved = _resolved_case(case)
    normalized = _validate_sections(_plain(load_dat_input(path).document))
    validate_native_case(normalized)
    profile_id = TASK40_PHI90_D07C_PROFILE_BY_CASE[case]
    assert resolved["solver"]["native_capacity_profile"] == profile_id

    plan = d07c_axis_plan(case)
    facts = native_profile_facts(profile_id)
    route = _direct_run_contract(profile_id)
    cfg = simulation_config_3d_from_normalized(resolved)
    actual = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual, f"{axis}_values"))
        for axis in "xyz"
    }
    assert tuple(actual.mesh_cells_resolved) == tuple(plan["axis_cell_counts"])
    assert actual.mesh_spacing_mode_resolved == "task40_phi90_d07c_frozen_axes"
    assert actual_axes == {
        axis: tuple(plan["axes_nm"][axis]) for axis in "xyz"
    }
    assert _independent_midpoint_tags(plan) == EXPECTED_TAGS[case]
    assert plan["expected_material_tag_counts"] == EXPECTED_TAGS[case]
    assert sum(EXPECTED_TAGS[case].values()) == plan["expected_global_cell_count"]
    assert plan["static_geometry_only"]["axis_aligned_cell_jacobian_determinant_positive"]
    assert plan["static_geometry_only"]["minimum_cell_volume_nm3"] > 0.0

    options = facts["component_options"]
    assert options["mode_selection"]["policy"] == "explicit_signed_rectangle_v1"
    assert options["mode_selection"]["parent_signed_bounds_mn"] == [-32, 32, -143, 1]
    assert options["mode_selection"]["expected_mode_count"] == EXPECTED_MODE_COUNT
    assert options["mode_selection"]["expected_mode_sha256"] == EXPECTED_MODE_SHA
    assert options["mode_selection"]["expected_active_mode_sha256"] == EXPECTED_MODE_SHA
    assert options["mode_selection"]["expected_active_propagating_count"] == EXPECTED_PROPAGATING
    assert options["mode_selection"]["expected_active_power_carrying_count"] == EXPECTED_POWER_CARRYING
    assert options["mode_selection"]["production_auto_inventory_signed_bounds_mn"] == [
        -71, 71, -142, 142
    ]
    assert options["mode_selection"]["auto_rectangle_candidate_key_count"] == 163_020
    assert options["mode_selection"]["production_auto_inventory_mode_count"] == 64_120
    assert options["mode_selection"]["production_auto_inventory_policy"] == "auto_propagating"
    assert options["mode_selection"]["omitted_auto_propagating_mode_count"] == 28_336
    assert options["mode_selection"]["separate_centered_audit_signed_bounds_mn"] == [
        -71, 71, -143, 143
    ]
    assert options["mode_selection"]["separate_centered_audit_mode_count"] == 164_164
    assert options["mode_selection"]["separate_centered_audit_is_production_inventory"] is False
    assert options["surface_quadrature"]["degree"] == 81
    assert options["surface_quadrature"]["reference_degree"] == 161
    assert options["surface_quadrature"]["q161_production_use"] is False
    assert options["volume_quadrature"] == {
        "degree": 15,
        "rule": "default",
        "authority": "live_FFCx_Basix_p6_volume_form_degree_metadata",
    }
    assert route["surface_quadrature_degree"] == 81
    assert route["surface_quadrature_reference_degree"] == 161
    assert route["expected_mode_sha256"] == EXPECTED_MODE_SHA
    assert route["active_sha256"] == EXPECTED_MODE_SHA
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert route["signed_rectangle_bounds_mn"] == [-32, 32, -143, 1]
    assert route["diagnostic_scope"].startswith("TASK40_D07C_")
    assert "0P7NM" in route["diagnostic_scope"]
    output_contract = _direct_output_policy(route)["active_fe_port_output_contract"]
    assert output_contract["active_signed_bounds_mn"] == [-32, 32, -143, 1]
    assert output_contract["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert facts["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["campaign_authorization"]["resource_policy"] == {
        "name": "host_available_floor_v1",
        "rss_user_cap": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap": "observe_only",
        "global_swap": "observe_only",
        "prediction": "record_only",
        "memavailable": "stop_below_explicit_64_gib_floor",
        "pss_uss_sampling": "disabled",
        "time_limit_mode": "none",
    }
    assert facts["resources"]["pss_sampling_policy"] == "disabled_by_profile"
    assert facts["resources"]["swap_policy"] == "observe_only"


def test_d07c_live_mesh_evidence_uses_actual_axes_and_independent_material_tags():
    for case in ("B", "Y1", "Y2"):
        plan = D07C_AXIS_PLANS[case]
        route = _direct_run_contract(TASK40_PHI90_D07C_PROFILE_BY_CASE[case])
        coords = np.asarray(
            list(product(plan["axes_nm"]["x"], plan["axes_nm"]["y"], plan["axes_nm"]["z"])),
            dtype=np.float64,
        )
        cell_tags = []
        for z0, z1 in pairwise(plan["axes_nm"]["z"]):
            zm = (z0 + z1) / 2.0
            for y0, y1 in pairwise(plan["axes_nm"]["y"]):
                ym = (y0 + y1) / 2.0
                for x0, x1 in pairwise(plan["axes_nm"]["x"]):
                    xm = (x0 + x1) / 2.0
                    cell_tags.append(
                        2 if zm < 0.0 else 1 if zm >= 120.0 else
                        3 if 16.5 < xm < 33.5 and 15.0 < ym < 35.0 else 1
                    )
        cell_count = int(plan["expected_global_cell_count"])
        mesh = SimpleNamespace(
            geometry=SimpleNamespace(x=coords),
            topology=SimpleNamespace(
                dim=3,
                index_map=lambda _dim, count=cell_count: SimpleNamespace(size_global=count),
                cell_name=lambda: "hexahedron",
            ),
        )
        levels = {
            "mesh_data": SimpleNamespace(
                mesh=mesh,
                cell_tags=SimpleNamespace(values=np.asarray(cell_tags, dtype=np.int32)),
            )
        }
        cfg = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3))
        evidence = _task40_d07c_mesh_evidence(levels, cfg, route)
        assert evidence["status"] == "PASS"
        assert evidence["material_tag_counts"] == EXPECTED_TAGS[case]


def test_d07c_rejects_wrong_axis_plan_tags_and_resource_values():
    path = INPUT_DIR / "d07c_b_m32_nminus143_to1_p6_direct.dat"
    normalized = _validate_sections(_plain(load_dat_input(path).document))
    wrong_axes = dict(normalized)
    wrong_axes["discretization"] = dict(normalized["discretization"])
    wrong_axes["discretization"]["mesh_axis_y_values"] = list(
        wrong_axes["discretization"]["mesh_axis_y_values"][:-1]
    ) + [50.0 - 0.125]
    with pytest.raises(InputError, match="invalid frozen D07C axes"):
        validate_native_case(wrong_axes)

    wrong_memory = dict(normalized)
    wrong_memory["execution"] = dict(normalized["execution"])
    wrong_memory["execution"]["memory_limit_gb"] = 1676.3806343078613
    with pytest.raises(InputError, match="64 GiB host-available floor"):
        validate_native_case(wrong_memory)

    wrong_material = dict(normalized)
    wrong_material["materials"] = dict(normalized["materials"])
    wrong_material["materials"]["n_grating"] = [0.99396854453, 0.00435380777]
    with pytest.raises(InputError, match="materials.n_grating"):
        validate_native_case(wrong_material)


def test_d07c_signed_window_production_inventory_is_finite_and_uses_q81():
    _path, _specification, resolved = _resolved_case("B")
    profile_id = resolved["solver"]["native_capacity_profile"]
    options = native_profile_facts(profile_id)["component_options"]
    route = _direct_run_contract(profile_id)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["signed_rectangle_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]

    modes, rows, mode_sha = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == EXPECTED_MODE_COUNT
    assert mode_sha == EXPECTED_MODE_SHA
    assert len({(m.side, m.m, m.n, m.polarization) for m in modes}) == EXPECTED_MODE_COUNT
    assert (modes[0].side, modes[0].m, modes[0].n, modes[0].polarization) == (
        "top", -32, -143, "s"
    )
    assert (modes[-1].side, modes[-1].m, modes[-1].n, modes[-1].polarization) == (
        "bottom", 32, 1, "p"
    )
    assert all(-32 <= mode.m <= 32 and -143 <= mode.n <= 1 for mode in modes)
    assert sum(bool(mode.propagating) for mode in modes) == EXPECTED_PROPAGATING
    assert sum(float(mode.power_per_unit_amplitude) > 0.0 for mode in modes) == (
        EXPECTED_POWER_CARRYING
    )
    assert sum(
        not mode.propagating and float(mode.power_per_unit_amplitude) > 0.0
        for mode in modes
    ) == 960
    auto_orders = enumerate_diffraction_orders_3d(cfg)
    auto_port_count = 4 * len(auto_orders)
    auto_propagating_count = 2 * sum(
        bool(order.top_propagating) + bool(order.bottom_propagating)
        for order in auto_orders
    )
    assert auto_port_count == options["mode_selection"]["auto_rectangle_candidate_key_count"]
    assert auto_propagating_count == 64_120
    assert auto_propagating_count - EXPECTED_PROPAGATING == 28_336
    assert all(
        np.isfinite(np.asarray((mode.alpha, mode.gamma, mode.beta), dtype=np.complex128)).all()
        and np.isfinite(mode.e_vector).all()
        and np.isfinite(mode.h_vector).all()
        and np.isfinite(mode.power_per_unit_amplitude)
        and np.isfinite(mode.boundary_amplitude_scale)
        and np.isfinite(mode.boundary_amplitude_log_scale)
        for mode in modes
    )
    assert max(mode.boundary_amplitude_log_scale for mode in modes if mode.side == "top") == pytest.approx(
        557.898104575372
    )
    assert _dtn_surface_quadrature_degree(cfg, list(modes)) == 81

    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    e_inc = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128
    )
    traction = np.cross(
        1j * np.cross(k_inc, e_inc), np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    )
    assert np.isfinite(traction).all()
    assert float(np.linalg.norm(traction)) == pytest.approx(0.1566524338595219)
    assert route["surface_quadrature_reference_degree"] == 161

    with pytest.raises(ValueError, match="signed diffraction bounds must be ordered"):
        enumerate_diffraction_orders_3d(cfg, signed_bounds_override=(1, -1, -2, 2))
    with pytest.raises(ValueError, match="signed bounds cannot be combined"):
        enumerate_diffraction_orders_3d(
            cfg,
            max_m_override=32,
            signed_bounds_override=(-32, 32, -143, 1),
        )
    bad_bounds = (-32, 32, -143, 2)
    bad_orders = enumerate_diffraction_orders_3d(
        cfg, signed_bounds_override=bad_bounds
    )
    assert len(bad_orders) == (32 - (-32) + 1) * (2 - (-143) + 1)
    assert len(bad_orders) * 4 != EXPECTED_MODE_COUNT
