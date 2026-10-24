from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import h100_anchor
from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    PERTURBATION_LIMITS,
    R13_MODE_KEYS,
    R14_MODE_KEYS,
    compare_field_sample_bundles,
    compare_r13_modal_outputs,
    compare_r13_r14_modal_outputs,
    task43_v2_physical_configuration_identity,
)
from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from benchmarks.task43_hp_adaptivity.sample_v2_legacy_r10_fields import (
    _restoration_config_comparison,
)
from src.common.modes_3d import outgoing_port_modes_3d

_SAME_ENDPOINT_IDENTITIES = {
    "r13_physical_configuration_sha256": "a" * 64,
    "r14_physical_configuration_sha256": "a" * 64,
    "r13_discretization_sha256": "b" * 64,
    "r14_discretization_sha256": "b" * 64,
}


def _refresh_metrics(payload):
    rows = payload["orders"]
    r00_s = sum(
        row["R"]
        for row in rows
        if row["side"] == "top"
        and row["m"] == 0
        and row["n"] == 0
        and row["polarization"] == "s"
    )
    r00_p = sum(
        row["R"]
        for row in rows
        if row["side"] == "top"
        and row["m"] == 0
        and row["n"] == 0
        and row["polarization"] == "p"
    )
    payload["metrics"] = {
        "R_total": sum(row["R"] for row in rows),
        "T_total": sum(row["T"] for row in rows),
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_s + r00_p,
        "dtn_port_mode_count": len(rows),
    }


def _mode_payload(
    max_m: int, max_n: int, *, tail_amplitude: float = 0.0, tail_power: float = 0.0
):
    rows = []
    r13_keys = set(R13_MODE_KEYS)
    for side in ("top", "bottom"):
        for m in range(-max_m, max_m + 1):
            for n in range(-max_n, max_n + 1):
                for polarization in ("s", "p"):
                    key = (side, m, n, polarization)
                    is_tail = key not in r13_keys
                    power = tail_power if is_tail else 0.0
                    amplitude = tail_amplitude if is_tail else 0.0
                    rows.append(
                        {
                            "side": side,
                            "m": m,
                            "n": n,
                            "polarization": polarization,
                            "outgoing_amplitude_at_boundary": [amplitude, 0.0],
                            "power_ratio": power,
                            "power_carrying": True,
                            "R": power if side == "top" else 0.0,
                            "T": power if side == "bottom" else 0.0,
                        }
                    )
    payload = {"orders": rows}
    _refresh_metrics(payload)
    return payload


def test_r13_r14_common_modes_and_tail_are_separate_and_pass_when_small():
    r13 = _mode_payload(4, 8)
    r14 = _mode_payload(5, 9, tail_amplitude=1.0e-8, tail_power=1.0e-10)
    r14["orders"].reverse()

    result = compare_r13_r14_modal_outputs(
        r13,
        r14,
        r13_a_volume=0.4,
        r14_a_volume=0.4,
        **_SAME_ENDPOINT_IDENTITIES,
    )

    assert len(R13_MODE_KEYS) == result["common_inventory"]["mode_count"] == 612
    assert (
        len(R14_MODE_KEYS - R13_MODE_KEYS)
        == result["tail_inventory"]["mode_count"]
        == 224
    )
    assert result["pass_10_percent_perturbation_gate"]
    assert len(result["common_612"]["per_channel_power_ratio"]["all_rows"]) == 612
    tail_rows = result["r14_tail_224"]["all_rows"]
    assert len(tail_rows) == 224
    assert all(row["R13_amplitude"] is None for row in tail_rows)
    assert all(row["R13_power_ratio"] is None for row in tail_rows)
    assert all(row["delta"] is None for row in tail_rows)
    assert result["r14_tail_224"]["aggregate_power_by_outgoing_side"]["top"]["pass"]
    assert all(
        group["pass"]
        for group in result["common_612"][
            "full_inventory_extension_diagnostic_groups"
        ].values()
    )


def test_same_r13_comparison_requires_shared_physics_and_discretization():
    r13 = _mode_payload(4, 8)
    result = compare_r13_modal_outputs(
        r13,
        copy.deepcopy(r13),
        reference_a_volume=0.4,
        candidate_a_volume=0.4,
        reference_physical_configuration_sha256="a" * 64,
        candidate_physical_configuration_sha256="a" * 64,
        reference_discretization_sha256="b" * 64,
        candidate_discretization_sha256="b" * 64,
    )
    assert result["pass_10_percent_perturbation_gate"]
    assert len(result["per_channel_power_ratio"]["all_rows"]) == 612
    assert len(result["boundary_amplitude_all_rows"]) == 612

    with pytest.raises(ValueError, match="different discretization"):
        compare_r13_modal_outputs(
            r13,
            copy.deepcopy(r13),
            reference_a_volume=0.4,
            candidate_a_volume=0.4,
            reference_physical_configuration_sha256="a" * 64,
            candidate_physical_configuration_sha256="a" * 64,
            reference_discretization_sha256="b" * 64,
            candidate_discretization_sha256="c" * 64,
        )


def test_same_r14_inventory_comparison_supports_all_836_same_lu_modes():
    r14 = _mode_payload(5, 9)
    result = compare_r13_modal_outputs(
        r14,
        copy.deepcopy(r14),
        reference_a_volume=0.4,
        candidate_a_volume=0.4,
        reference_physical_configuration_sha256="a" * 64,
        candidate_physical_configuration_sha256="a" * 64,
        reference_discretization_sha256="b" * 64,
        candidate_discretization_sha256="b" * 64,
        expected_keys=R14_MODE_KEYS,
    )

    assert result["schema"] == "task43.v2_r14_same_space_modal_comparison.v1"
    assert result["reference_inventory"]["mode_count"] == 836
    assert result["candidate_inventory"]["mode_count"] == 836
    assert len(result["per_channel_power_ratio"]["all_rows"]) == 836
    assert (
        sum(
            group["mode_count"]
            for group in result["boundary_amplitude_groups"].values()
        )
        == 836
    )
    assert result["pass_10_percent_perturbation_gate"]


@pytest.mark.parametrize(
    ("phase", "expected_keys", "expected_count"),
    [
        ("A1_q", R13_MODE_KEYS, 612),
        ("A1_R", R14_MODE_KEYS, 836),
    ],
)
def test_v2_a1_config_resolves_the_frozen_complete_mode_inventory(
    phase, expected_keys, expected_count
):
    contract_path = (
        h100_anchor._REPOSITORY_ROOT
        / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
    )
    contract = h100_anchor._load_v2_diagnostic_contract(
        contract_path, h100_anchor._V2_CONTRACT_SHA256
    )
    cfg = task43_initial_profile(case_name="task43_v2_mode_configuration_test")
    configuration = h100_anchor._configure_v2_a1_endpoint(cfg, phase, contract)
    modes = outgoing_port_modes_3d(cfg)
    actual_keys = {
        (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        for mode in modes
    }

    assert configuration["modal_rectangle"]["mode_count"] == expected_count
    assert len(modes) == expected_count
    assert actual_keys == expected_keys

    endpoint_identity = h100_anchor._v2_endpoint_identity(
        cfg,
        modes,
        axes_nm={
            "x": cfg.mesh_axis_x_values,
            "y": cfg.mesh_axis_y_values,
            "z": cfg.mesh_axis_z_values,
        },
        candidate_plan_sha256="a" * 64,
        active_degree_plan_sha256="b" * 64,
        phase=phase,
        contract_sha256=h100_anchor._V2_CONTRACT_SHA256,
    )
    assert (
        endpoint_identity["numerical_controls"]["modal_rectangle"]["mode_count"]
        == expected_count
    )

    with pytest.raises(ValueError, match="resolved mode inventory"):
        h100_anchor._v2_endpoint_identity(
            cfg,
            [*modes, modes[-1]],
            axes_nm={
                "x": cfg.mesh_axis_x_values,
                "y": cfg.mesh_axis_y_values,
                "z": cfg.mesh_axis_z_values,
            },
            candidate_plan_sha256="a" * 64,
            active_degree_plan_sha256="b" * 64,
            phase=phase,
            contract_sha256=h100_anchor._V2_CONTRACT_SHA256,
        )


def test_r14_tail_individual_power_is_a_real_gate():
    r13 = _mode_payload(4, 8)
    r14 = _mode_payload(5, 9, tail_amplitude=1.0e-8, tail_power=0.0)
    tail_key = next(iter(R14_MODE_KEYS - R13_MODE_KEYS))
    row = next(
        row
        for row in r14["orders"]
        if (row["side"], row["m"], row["n"], row["polarization"]) == tail_key
    )
    row["power_ratio"] = 2.0 * PERTURBATION_LIMITS["R14_tail_channel_power_ratio"]
    row["R"] = row["power_ratio"] if row["side"] == "top" else 0.0
    row["T"] = row["power_ratio"] if row["side"] == "bottom" else 0.0
    _refresh_metrics(r14)

    result = compare_r13_r14_modal_outputs(
        r13,
        r14,
        r13_a_volume=0.4,
        r14_a_volume=0.4,
        **_SAME_ENDPOINT_IDENTITIES,
    )

    assert not result["r14_tail_224"]["per_channel_power_ratio_maximum"]["pass"]
    assert not result["pass_10_percent_perturbation_gate"]


def test_r14_tail_amplitude_floor_gate_is_not_hidden_by_large_reference_norm():
    r13 = _mode_payload(4, 8)
    r14 = _mode_payload(5, 9)
    for row in r13["orders"]:
        if row["side"] == "top" and row["polarization"] == "s":
            row["outgoing_amplitude_at_boundary"] = [10.0, 0.0]
    tail_key = next(
        key
        for key in R14_MODE_KEYS - R13_MODE_KEYS
        if key[0] == "top" and key[3] == "s"
    )
    tail_row = next(
        row
        for row in r14["orders"]
        if (row["side"], row["m"], row["n"], row["polarization"]) == tail_key
    )
    tail_row["outgoing_amplitude_at_boundary"] = [2.0e-5, 0.0]

    result = compare_r13_r14_modal_outputs(
        r13,
        r14,
        r13_a_volume=0.4,
        r14_a_volume=0.4,
        **_SAME_ENDPOINT_IDENTITIES,
    )

    assert (
        result["r14_tail_224"]["boundary_amplitude_groups"]["top_s"][
            "relative_with_incident_floor"
        ]
        > 1.0e-5
    )
    assert not result["r14_tail_224"]["boundary_amplitude_groups"]["top_s"][
        "within_10_percent_final_tolerance"
    ]
    assert not result["pass_10_percent_perturbation_gate"]


def test_joint_common_and_tail_amplitude_envelope_is_a_gate():
    r13 = _mode_payload(4, 8)
    r14 = _mode_payload(5, 9)
    common_key = next(key for key in R13_MODE_KEYS if key[0] == "top" and key[3] == "s")
    tail_key = next(
        key
        for key in R14_MODE_KEYS - R13_MODE_KEYS
        if key[0] == "top" and key[3] == "s"
    )
    for row in r14["orders"]:
        key = (row["side"], row["m"], row["n"], row["polarization"])
        if key in {common_key, tail_key}:
            row["outgoing_amplitude_at_boundary"] = [0.8e-5, 0.0]

    result = compare_r13_r14_modal_outputs(
        r13,
        r14,
        r13_a_volume=0.4,
        r14_a_volume=0.4,
        **_SAME_ENDPOINT_IDENTITIES,
    )

    group = result["common_612"]["full_inventory_extension_diagnostic_groups"]["top_s"]
    assert (
        result["common_612"]["boundary_amplitude_groups"]["top_s"][
            "relative_with_unit_incident_modal_floor"
        ]
        < 1.0e-5
    )
    assert (
        result["r14_tail_224"]["boundary_amplitude_groups"]["top_s"][
            "relative_with_incident_floor"
        ]
        < 1.0e-5
    )
    assert group["relative_extension_diagnostic_envelope"] > 1.0e-5
    assert not group["pass"]
    assert not result["pass_10_percent_perturbation_gate"]


def test_physical_configuration_identity_excludes_only_numerical_controls():
    config = {
        "geometry_kind": "rectangular_block_grating",
        "scattering_background": "layered",
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
        "lambda0": 13.5,
        "period_x": 50.0,
        "period_y": 50.0,
        "physical_z_min": -10.0,
        "physical_z_max": 130.0,
        "domain_z_min": -10.0,
        "domain_z_max": 130.0,
        "air_height": 130.0,
        "grating_bounds": {"x_min": 16.5, "x_max": 33.5},
        "grating_width_x": 17.0,
        "grating_width_y": 20.0,
        "grating_height": 120.0,
        "interface_z": 0.0,
        "substrate_thickness": 10.0,
        "incident_theta_deg": 89.0,
        "incident_phi_deg": 90.0,
        "incident_amplitude": [1.0, 0.0],
        "incident_e0_v_per_m": 1.0,
        "polarization_kind": "s",
        "polarization": [[-1.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        "propagation_direction": [0.0, 1.0, 0.0],
        "wavevector": [[0.0, 0.0], [0.4, 0.0], [0.0, 0.0]],
        "floquet_phase_x": [1.0, 0.0],
        "floquet_phase_y": [0.8, 0.6],
        "n_air": [1.0, 0.0],
        "mu_r": [1.0, 0.0],
        "n_substrate": [0.9, 0.01],
        "n_grating": [0.9, 0.01],
        "eps_air": [1.0, 0.0],
        "eps_substrate": [0.8, 0.02],
        "eps_grating": [0.8, 0.02],
        "eps_r": [1.0, 0.0],
        "grating_background_eps": [1.0, 0.0],
        "grating_index": [0.9, 0.01],
        "k0": 0.4,
        "magnetic_field_scale_A_per_m": 0.002,
        "use_floquet_xy": True,
        "use_pml": False,
        "pml_alpha": 5.0,
        "pml_bottom_thickness": 0.0,
        "pml_top_thickness": 0.0,
        "stage4_boundary_model": "dtn_port",
        "stage4_pml_outer_bc": "natural",
        "stage4_floquet_slave_elimination": True,
        "mesh_cell_type_resolved": "hexahedron",
        "stage4_dtn_quadrature_degree": 28,
        "stage4_dtn_rectangle_max_n": 8,
    }
    axes = {axis: [0.0, 1.0] for axis in ("x", "y", "z")}
    kwargs = {
        "axis_values_nm": axes,
        "candidate_plan_sha256": "a" * 64,
        "active_degree_plan_sha256": "b" * 64,
    }
    baseline = task43_v2_physical_configuration_identity(config, **kwargs)
    changed_numerics = dict(
        config, stage4_dtn_quadrature_degree=32, stage4_dtn_rectangle_max_n=9
    )
    assert (
        task43_v2_physical_configuration_identity(changed_numerics, **kwargs)["sha256"]
        == baseline["sha256"]
    )
    changed_physics = dict(config, incident_theta_deg=88.0)
    assert (
        task43_v2_physical_configuration_identity(changed_physics, **kwargs)["sha256"]
        != baseline["sha256"]
    )
    changed_discretization = task43_v2_physical_configuration_identity(
        config,
        axis_values_nm={"x": [0.0, 0.5, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]},
        candidate_plan_sha256="c" * 64,
        active_degree_plan_sha256="d" * 64,
    )
    assert changed_discretization["sha256"] == baseline["sha256"]
    assert (
        changed_discretization["discretization_identity"]["sha256"]
        != baseline["discretization_identity"]["sha256"]
    )


def test_restoration_config_records_floquet_setting_outside_physics_identity():
    solve_config = {
        "incident_theta_deg": 89.0,
        "stage4_floquet_slave_elimination": True,
        "stage4_cell_static_condensation": True,
    }
    restored_config = {
        "incident_theta_deg": 89.0,
        "stage4_floquet_slave_elimination": False,
        "stage4_cell_static_condensation": False,
    }
    comparison = _restoration_config_comparison(solve_config, restored_config)

    assert comparison["all_physical_fields_match"]
    assert comparison["floquet_slave_elimination"]["solve_record"] is True
    assert (
        comparison["floquet_slave_elimination"]["restored_carrier_config_default"]
        is False
    )
    differences = {
        item["field"]: item
        for item in comparison["solver_and_reconstruction_setting_differences"]
    }
    assert differences["stage4_floquet_slave_elimination"]["solve_record_value"]
    assert not differences["stage4_floquet_slave_elimination"][
        "restored_carrier_config_value"
    ]
    assert (
        "stage4_floquet_slave_elimination"
        not in comparison["physical_field_names_checked"]
    )


def test_restoration_config_rejects_changed_physical_field():
    solve_config = {
        "incident_theta_deg": 89.0,
        "stage4_floquet_slave_elimination": True,
    }
    restored_config = {
        "incident_theta_deg": 88.0,
        "stage4_floquet_slave_elimination": False,
    }
    with pytest.raises(ValueError, match="physical fields differ"):
        _restoration_config_comparison(solve_config, restored_config)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "fractional_index", "aggregate"]
)
def test_r13_inventory_must_be_complete_and_unique(mutation: str):
    r13 = _mode_payload(4, 8)
    r14 = _mode_payload(5, 9)
    if mutation == "missing":
        r13["orders"].pop()
        expected = ValueError
    elif mutation == "duplicate":
        r13["orders"][0] = copy.deepcopy(r13["orders"][1])
        expected = ValueError
    elif mutation == "fractional_index":
        r13["orders"][0]["m"] = 1.5
        expected = TypeError
    else:
        r13["metrics"]["R_total"] = 1.0
        expected = ValueError

    with pytest.raises(expected):
        compare_r13_r14_modal_outputs(
            r13,
            r14,
            r13_a_volume=0.4,
            r14_a_volume=0.4,
            **_SAME_ENDPOINT_IDENTITIES,
        )


def _field_bundle(offset: float = 0.0, background_offset: float = 0.0):
    points = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    base = np.ones((2, 3), dtype=np.complex128)
    curl = 0.5 * base
    magnetic = curl / (1j * 0.4)
    background_e = np.full((2, 3), background_offset, dtype=np.complex128)
    background_h = np.full((2, 3), background_offset, dtype=np.complex128)
    return {
        "points_nm": points,
        "weights_nm3": np.ones(2, dtype=np.float64),
        "physical_configuration_identity_sha256": "a" * 64,
        "E_total_code": base + offset,
        "curl_E_total_code": curl,
        "H_total_A_per_m": magnetic,
        "incident_background_E_code": background_e,
        "incident_background_H_A_per_m": background_h,
        "E_scattered_code": base + offset - background_e,
        "H_scattered_A_per_m": magnetic - background_h,
    }


def test_field_comparison_requires_same_actual_samples_and_gates_full_vector():
    reference = _field_bundle()
    candidate = _field_bundle()
    scales = {
        "k0_per_nm": 0.4,
        "magnetic_field_scale_A_per_m": 1.0,
        "mu_r": 1.0 + 0.0j,
        "incident_e_norm_floor": 1.0,
        "incident_h_norm_floor": 1.0,
        "incident_g_norm_floor": 1.0,
    }

    same = compare_field_sample_bundles(reference, candidate, **scales)
    assert same["same_points_and_weights"]
    assert same["same_incident_background_arrays"]
    assert same["pass_10_percent_perturbation_gate"]
    assert set(same["component_relative_values"]) == {
        "E_total_code",
        "H_total_A_per_m",
        "E_scattered_code",
        "H_scattered_A_per_m",
        "G",
    }

    changed = compare_field_sample_bundles(
        reference, _field_bundle(offset=1.0e-4), **scales
    )
    assert not changed["pass_10_percent_perturbation_gate"]

    wrong_points = _field_bundle()
    wrong_points["points_nm"][0, 0] = 1.0e-9
    with pytest.raises(ValueError, match="identical physical points"):
        compare_field_sample_bundles(reference, wrong_points, **scales)

    different_background = _field_bundle(background_offset=1.0e-9)
    with pytest.raises(ValueError, match="same incident background arrays"):
        compare_field_sample_bundles(reference, different_background, **scales)


def test_field_comparison_rejects_nonfinite_curl_wrong_h_and_wrong_scattered_field():
    reference = _field_bundle()
    scales = {
        "k0_per_nm": 0.4,
        "magnetic_field_scale_A_per_m": 1.0,
        "mu_r": 1.0 + 0.0j,
        "incident_e_norm_floor": 1.0,
        "incident_h_norm_floor": 1.0,
        "incident_g_norm_floor": 1.0,
    }

    nonfinite_curl = _field_bundle()
    nonfinite_curl["curl_E_total_code"][0, 0] = np.nan
    with pytest.raises(ValueError, match="must be finite"):
        compare_field_sample_bundles(reference, nonfinite_curl, **scales)

    wrong_h = _field_bundle()
    wrong_h["H_total_A_per_m"][0, 0] += 1.0
    with pytest.raises(ValueError, match="do not match its recovered curl"):
        compare_field_sample_bundles(reference, wrong_h, **scales)

    wrong_scattered = _field_bundle()
    wrong_scattered["E_scattered_code"][0, 0] += 1.0
    with pytest.raises(ValueError, match="scattered E does not match saved background"):
        compare_field_sample_bundles(reference, wrong_scattered, **scales)


@pytest.mark.parametrize("writer_schema", ["current_writer", "legacy_resampler"])
def test_v2_field_npz_reader_accepts_both_saved_sample_schemas(
    tmp_path, monkeypatch, writer_schema
):
    points = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    weights = np.asarray([0.25, 0.75])
    total_e = np.full((2, 3), 1.0 + 2.0j, dtype=np.complex128)
    curl_e = np.full((2, 3), -0.5 + 0.25j, dtype=np.complex128)
    total_h = np.full((2, 3), 0.75 - 0.5j, dtype=np.complex128)
    path = tmp_path / f"{writer_schema}.npz"
    if writer_schema == "current_writer":
        h100_anchor._write_samples(
            path,
            {
                "q8": {
                    "points_nm": points,
                    "weights_nm3": weights,
                    "E_total": total_e,
                    "curl_E_total": curl_e,
                    "H_total_A_per_m": total_h,
                }
            },
            (np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0])),
        )
    else:
        np.savez_compressed(
            path,
            q8_points_nm=points,
            q8_weights_nm3=weights,
            q8_E_total_code=total_e,
            q8_curl_E_total_code=curl_e,
            q8_H_total_A_per_m=total_h,
        )

    monkeypatch.setattr(
        h100_anchor,
        "electric_field_code_values",
        lambda _cfg, actual_points: np.zeros_like(actual_points, dtype=np.complex128),
    )
    monkeypatch.setattr(
        h100_anchor,
        "magnetic_field_code_values",
        lambda _cfg, actual_points: np.zeros_like(actual_points, dtype=np.complex128),
    )
    result = h100_anchor._v2_field_bundle_from_npz(
        path, 8, SimpleNamespace(magnetic_field_scale_A_per_m=1.0), "a" * 64
    )

    np.testing.assert_array_equal(result["points_nm"], points)
    np.testing.assert_array_equal(result["weights_nm3"], weights)
    np.testing.assert_array_equal(result["E_total_code"], total_e)
    np.testing.assert_array_equal(result["curl_E_total_code"], curl_e)
    np.testing.assert_array_equal(result["H_total_A_per_m"], total_h)
    assert result["physical_configuration_identity_sha256"] == "a" * 64


def _hard_gate_reference_fixture(explicit_relative=1.0e-10):
    gates = {
        "solver_completed": True,
        "actual_live_and_summary_factor_backend_mumps": True,
        "normal_same_lu_correction_passed": True,
        "exact_complete_modal_inventory": True,
        "explicit_b_minus_Ax_relative_le_1e-8": explicit_relative <= 1.0e-8,
        "independent_A6_relative_le_1e-8": True,
        "condensed_residual_relative_le_1e-9": True,
        "energy_closure_absolute_le_1e-5": True,
        "local_h_closure_pass": True,
        "variable_p_degree_plan_pass": True,
        "trace_constraint_closure_pass": True,
        "active_fe_dof_resource_gate_pass": True,
    }
    record = {
        "solver": {
            "case_status": "completed",
            "actual_direct_factor_backend": "mumps",
            "actual_live_direct_factor_backend": "mumps",
            "normal_same_lu_correction": {
                "status": "passed",
                "solution_updated": True,
                "initial_condensed_residual_norm": 1.0e-3,
                "corrected_condensed_residual_norm": 1.0e-8,
                "initial_condensed_relative_to_rhs": 1.0e-3,
                "corrected_condensed_relative_to_rhs": 1.0e-8,
                "correction_ksp": {"converged_reason": 2},
            },
            "explicit_b_minus_Ax": {
                "linear_system_relative_residual": explicit_relative
            },
            "independent_A6": {
                "full_solver_gauge_residual": {
                    "finite": True,
                    "relative_to_independent_rhs": 1.0e-10,
                }
            },
            "condensed_residual": {"linear_system_relative_residual": 1.0e-10},
            "local_h_audit": {"pass": True},
        },
        "recovered_solution_storage": {
            "degree_plan_pass": True,
            "trace_constraints_pass": True,
            "active_fe_dof_gate_pass": True,
        },
        "modal_outputs": {"inventory": "R13", "mode_count": len(R13_MODE_KEYS)},
        "power": {
            "aggregate": {"R_total": 0.2, "T_total": 0.7},
            "A_volume_total": 0.1,
            "R_plus_T_plus_A_volume": 1.0,
            "energy_closure_error": 0.0,
        },
        "hard_solver_gates": gates,
        "hard_solver_gates_pass": True,
    }
    payload = _mode_payload(4, 8)
    for row in payload["orders"]:
        if row["side"] == "top":
            row["power_ratio"] = 0.2 / 306
            row["R"] = row["power_ratio"]
        else:
            row["power_ratio"] = 0.7 / 306
            row["T"] = row["power_ratio"]
    _refresh_metrics(payload)
    return record, payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("solver", "explicit_b_minus_Ax", "linear_system_relative_residual"),
            1.0e-5,
        ),
        (
            ("solver", "explicit_b_minus_Ax", "linear_system_relative_residual"),
            -1.0e-10,
        ),
        (
            (
                "solver",
                "independent_A6",
                "full_solver_gauge_residual",
                "relative_to_independent_rhs",
            ),
            1.0e-5,
        ),
        (
            ("solver", "condensed_residual", "linear_system_relative_residual"),
            1.0e-3,
        ),
        (("power", "A_volume_total"), 0.2),
    ],
)
def test_a1_reference_hard_gates_recompute_raw_residual_and_power(path, value):
    record, payload = _hard_gate_reference_fixture()
    recomputed = h100_anchor._v2_recompute_reference_hard_gates(
        record, payload, R13_MODE_KEYS
    )
    assert all(recomputed.values())

    # Leave stored status/gate booleans claiming success while changing one of
    # the saved raw solver or power values beyond its frozen gate.
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="disagree with recomputed solver/power"):
        h100_anchor._v2_recompute_reference_hard_gates(record, payload, R13_MODE_KEYS)


def test_a1_reference_normal_correction_rechecks_raw_descent_and_ksp_reason():
    report = {
        "status": "passed",
        "solution_updated": True,
        "initial_condensed_residual_norm": 1.0e-3,
        "corrected_condensed_residual_norm": 1.0e-8,
        "initial_condensed_relative_to_rhs": 1.0e-3,
        "corrected_condensed_relative_to_rhs": 1.0e-8,
        "correction_ksp": {"converged_reason": 2},
    }
    assert h100_anchor._v2_normal_correction_passed(report)
    report["corrected_condensed_residual_norm"] = 1.0e-3
    assert not h100_anchor._v2_normal_correction_passed(report)
    report["corrected_condensed_residual_norm"] = 1.0e-8
    report["correction_ksp"]["converged_reason"] = 0
    assert not h100_anchor._v2_normal_correction_passed(report)


def test_a1_reference_hard_gate_rejects_power_rows_that_disagree_with_metrics():
    record, payload = _hard_gate_reference_fixture()
    payload["orders"][0]["R"] += 0.1
    with pytest.raises(ValueError, match="disagree with recomputed solver/power"):
        h100_anchor._v2_recompute_reference_hard_gates(record, payload, R13_MODE_KEYS)
