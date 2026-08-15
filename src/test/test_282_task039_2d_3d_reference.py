from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.task039_2d_3d_reference as checker


def _fixture() -> dict[str, object]:
    x = np.arange(4, dtype=np.float64)
    z2 = np.asarray([-5.0, 5.0, 30.0, 60.0, 90.0, 115.0, 125.0])
    z3 = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0])
    e2 = np.ones((7, 4), dtype=np.complex128)
    hx2 = np.full((7, 4), 2.0 + 0.0j)
    hz2 = np.full((7, 4), 3.0 + 0.0j)
    e3 = np.zeros((5, 2, 4, 3), dtype=np.complex128)
    h3 = np.zeros_like(e3)
    e3[:, :, :, 1] = 1.0
    h3[:, :, :, 0] = 2.0
    h3[:, :, :, 2] = 3.0
    rows2 = {
        -1: {
            "R_order": 0.001,
            "T_order": 0.1,
            "top_propagating": True,
            "bottom_propagating": True,
            "reflected_Ez_real": 0.0,
            "reflected_Ez_imag": 0.0,
            "transmitted_Ez_real": 0.0,
            "transmitted_Ez_imag": 0.0,
        },
        0: {
            "R_order": 0.099,
            "T_order": 0.7,
            "top_propagating": True,
            "bottom_propagating": True,
            "reflected_Ez_real": 0.0,
            "reflected_Ez_imag": 0.0,
            "transmitted_Ez_real": 0.0,
            "transmitted_Ez_imag": 0.0,
        },
    }
    rows3 = {
        (side, m, 0, "s"): {"power_ratio": value, "outgoing_amplitude": 1.0 + 0.0j}
        for side, values in (
            ("top", {-1: 0.001, 0: 0.099}),
            ("bottom", {-1: 0.1, 0: 0.7}),
        )
        for m, value in values.items()
    }
    two_d = {
        "root": "2d",
        "model_id": "task039_5nm_v3_1deg_s5",
        "source_sha": "a" * 40,
        "power": {"R_total": 0.1, "T_total": 0.8, "A_balance": 0.1, "A_volume": 0.1},
        "fields": {
            "x_nm": x,
            "z_nm": z2,
            "electric_y_V_per_m": e2,
            "magnetic_x_A_per_m": hx2,
            "magnetic_z_A_per_m": hz2,
        },
        "orders": rows2,
    }
    three_d = {
        "root": "3d",
        "manifest": {
            "model_id": "task039_5nm_v3_1deg_s5_full3d",
            "source_sha": "b" * 40,
        },
        "numeric": {
            "R_total_dtn_port_modal": 0.1,
            "T_total_dtn_port_modal": 0.8,
            "A_balance_dtn_port_modal": 0.1,
            "A_volume_total": 0.1,
        },
        "reference": {
            "arrays": {
                "x_nm": x,
                "y_nm": np.arange(2),
                "z_nm": z3,
                "E_V_per_m": e3,
                "H_A_per_m": h3,
            }
        },
        "orders": {"rows": rows3},
    }
    cfg2 = SimpleNamespace(
        lambda0=5.0,
        period_x=50.0,
        grating_width=17.0,
        grating_height=120.0,
        n_air=1.0 + 0j,
        n_substrate=1.4 + 0.0j,
        n_grating=1.4 + 0.0j,
        k0=1.0,
        kx=0.5 + 0j,
        ky=-np.sqrt(0.75) + 0j,
        incident_angle_deg=89.0,
    )
    wave = np.asarray([0.5, 0.0, -np.sqrt(0.75)], dtype=np.complex128)
    cfg3 = SimpleNamespace(
        lambda0=5.0,
        period_x=50.0,
        period_y=25.0,
        grating_width_x=17.0,
        grating_height=120.0,
        n_air=1.0 + 0j,
        n_substrate=1.4 + 0.0j,
        n_grating=1.4 + 0.0j,
        k0=1.0,
        kx=0.5 + 0j,
        wavevector=wave,
        s_polarization_vector=np.asarray([0.0, 1.0, 0.0]),
        incident_theta_deg=89.0,
        incident_phi_deg=0.0,
        incident_amplitude=1.0 + 0j,
        polarization_vector=np.asarray([0.0, 1.0, 0.0]),
        mu_r=1.0 + 0j,
        x_min=0.0,
        x_max=50.0,
        y_min=0.0,
        y_max=25.0,
    )
    return {"two_d": two_d, "three_d": three_d, "cfg2": cfg2, "cfg3": cfg3}


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    data = _fixture()
    monkeypatch.setattr(checker, "_load_formal_run", lambda *_args: data["two_d"])
    monkeypatch.setattr(checker, "_load_run", lambda *_args, **_kwargs: data["three_d"])
    monkeypatch.setattr(
        checker, "_load_configs", lambda *_args: (data["cfg2"], data["cfg3"])
    )
    return data


def test_2d_3d_identity_and_all_y_reduction_pass(patched):
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is True
    assert result["identity"]["incident_power"]["pass"] is True
    assert result["fields"]["pass"] is True
    assert result["fields"]["normal_flux_diagnostic"]["relative_l2"] == 0.0
    assert result["fields"]["normal_flux_diagnostic"]["denominator"] == pytest.approx(
        np.sqrt(12.0)
    )
    assert result["orders"]["primary_pass"] is True


def test_incident_power_uses_relative_identity_gate(patched, monkeypatch):
    patched["cfg2"].period_x = 1.0e-10
    patched["cfg3"].period_x = 1.0e-10
    small_period_x = np.asarray([0.0, 2.5e-11, 5.0e-11, 7.5e-11])
    patched["two_d"]["fields"]["x_nm"] = small_period_x
    patched["three_d"]["reference"]["arrays"]["x_nm"] = small_period_x.copy()
    expected = 0.5 * np.sqrt(0.75) * patched["cfg2"].period_x
    absolute_delta = 5.0e-13
    monkeypatch.setattr(
        checker,
        "incident_power_3d",
        lambda _cfg: (
            (expected + absolute_delta) * patched["cfg3"].period_y / patched["cfg2"].k0
        ),
    )
    result = checker.compare_2d_3d_reference("2d", "3d")
    power = result["identity"]["incident_power"]
    assert power["absolute_delta"] < 1.0e-12
    assert power["relative_delta"] > 1.0e-12
    assert not power["pass"]
    assert result["pass"] is False
    assert result["orders"]["leakage"]["aggregate"]["pass"] is True


def test_complex_polarization_is_json_native(patched):
    patched["cfg3"].s_polarization_vector = np.asarray(
        [0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128
    )
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["identity"]["s_polarization_3d"] == [0.0, 1.0, 0.0]
    patched["cfg3"].s_polarization_vector[1] += 1.0e-12j
    with pytest.raises(ValueError, match="not real Ey"):
        checker.compare_2d_3d_reference("2d", "3d")


def test_shape_mismatch_fails_closed(patched):
    patched["three_d"]["reference"]["arrays"]["E_V_per_m"] = np.zeros((5, 2, 4, 2))
    with pytest.raises(ValueError, match="field shape"):
        checker.compare_2d_3d_reference("2d", "3d")


def test_identity_and_union_leakage_failures_are_reported(patched):
    patched["cfg3"].kx = 0.51 + 0j
    with pytest.raises(ValueError, match="kx identity"):
        checker.compare_2d_3d_reference("2d", "3d")
    patched["cfg3"].kx = 0.5 + 0j
    patched["three_d"]["orders"]["rows"][("top", 1, 1, "s")] = {
        "power_ratio": 1.0e-3,
        "outgoing_amplitude": 1.0 + 0j,
    }
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is False
    assert result["gates"]["leakage"] is False


def test_weak_all_m_mismatch_is_diagnostic_only(patched):
    patched["two_d"]["orders"][1] = {
        "R_order": 1.0e-9,
        "T_order": 1.0e-9,
        "top_propagating": False,
        "bottom_propagating": False,
        "reflected_Ez_real": 0.0,
        "reflected_Ez_imag": 0.0,
        "transmitted_Ez_real": 0.0,
        "transmitted_Ez_imag": 0.0,
    }
    patched["three_d"]["orders"]["rows"][("top", 1, 0, "s")] = {
        "power_ratio": 0.2,
        "outgoing_amplitude": 1.0 + 0j,
    }
    patched["three_d"]["orders"]["rows"][("bottom", 1, 0, "s")] = {
        "power_ratio": 0.2,
        "outgoing_amplitude": 1.0 + 0j,
    }
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is True
    assert result["orders"]["weighted_all_m"]["pass"] is False
    assert result["gates"]["primary_m_orders"] is True


def test_missing_weak_order_is_diagnostic_only(patched):
    patched["two_d"]["orders"][1] = {
        "R_order": 1.0e-9,
        "T_order": 1.0e-9,
        "top_propagating": False,
        "bottom_propagating": False,
        "reflected_Ez_real": 0.0,
        "reflected_Ez_imag": 0.0,
        "transmitted_Ez_real": 0.0,
        "transmitted_Ez_imag": 0.0,
    }
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is True
    assert result["orders"]["missing_weak_count"] == 2
    assert result["orders"]["missing_primary_count"] == 0


def test_missing_primary_order_fails_closed(patched):
    del patched["three_d"]["orders"]["rows"][("top", 0, 0, "s")]
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is False
    assert result["orders"]["missing_primary_count"] == 1
    assert result["gates"]["primary_m_orders"] is False


def test_periodic_x_shift_reindexes_fields_and_passes(patched):
    source_x = np.asarray([-1.5, -0.5, 0.5, 1.5])
    target_x = np.asarray([0.5, 1.5, 48.5, 49.5])
    reindex = checker._periodic_coordinate_reindex(source_x, target_x, 50.0)
    assert reindex.tolist() == [2, 3, 0, 1]
    source_values = np.asarray([10.0, 20.0, 30.0, 40.0])
    assert np.array_equal(source_values[reindex], [30.0, 40.0, 10.0, 20.0])
    patched["two_d"]["fields"]["x_nm"] = source_x
    patched["three_d"]["reference"]["arrays"]["x_nm"] = target_x
    e2 = np.tile(source_values, (7, 1)).astype(np.complex128)
    hx2 = np.tile(source_values + 1.0, (7, 1)).astype(np.complex128)
    hz2 = np.tile(source_values + 2.0, (7, 1)).astype(np.complex128)
    patched["two_d"]["fields"]["electric_y_V_per_m"] = e2
    patched["two_d"]["fields"]["magnetic_x_A_per_m"] = hx2
    patched["two_d"]["fields"]["magnetic_z_A_per_m"] = hz2
    e3 = patched["three_d"]["reference"]["arrays"]["E_V_per_m"]
    h3 = patched["three_d"]["reference"]["arrays"]["H_A_per_m"]
    e3[:, :, :, 1] = source_values[reindex]
    h3[:, :, :, 0] = source_values[reindex] + 1.0
    h3[:, :, :, 2] = source_values[reindex] + 2.0
    result = checker.compare_2d_3d_reference("2d", "3d")
    assert result["pass"] is True


def test_non_equivalent_periodic_x_coordinates_fail_closed(patched):
    patched["two_d"]["fields"]["x_nm"] = np.asarray([-1.5, -0.5, 0.5, 1.5])
    patched["three_d"]["reference"]["arrays"]["x_nm"] = np.asarray(
        [0.5, 1.5, 48.5, 49.0]
    )
    with pytest.raises(ValueError, match="periodic-equivalent"):
        checker.compare_2d_3d_reference("2d", "3d")
