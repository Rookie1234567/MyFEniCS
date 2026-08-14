"""Focused offline contracts for the Review V2 same-grid comparator."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from benchmarks.task039_hybrid_direct_identity import (
    IdentityCheckError,
    _compare_h5_hybrid_full3d_data,
    _v2_physical_model_identity,
)


def _order_keys() -> list[tuple[str, int, int, str]]:
    return [("bottom" if index < 302 else "top", index, 0, "s") for index in range(604)]


def _synthetic_data() -> tuple[dict, dict]:
    keys = _order_keys()
    orders = {}
    for index, key in enumerate(keys):
        power = 1.0e-4 if index < 10 else 5.0e-7 if index < 39 else 1.0e-10
        orders[key] = {
            "power_ratio": power,
            "outgoing_amplitude": complex(np.sqrt(power), 0.0),
        }
    coordinates = {
        "x_nm": np.array([0.0, 1.0], dtype=np.float64),
        "y_nm": np.array([0.0, 1.0], dtype=np.float64),
        "z_nm": np.array([10.0, 30.0, 60.0, 90.0, 110.0], dtype=np.float64),
    }
    fields = {
        "E_V_per_m": np.ones((5, 2, 2, 3), dtype=np.complex128),
        "H_A_per_m": np.full((5, 2, 2, 3), 2.0 + 1.0j, dtype=np.complex128),
    }
    observables = {
        "R_total": 0.1,
        "T_total": 0.2,
        "A_balance": 0.7,
        "A_volume": 0.7,
    }
    hybrid = {
        "inventory": {"keys": keys},
        "observables": observables.copy(),
        "closure": 1.0e-6,
        "orders": orders,
        "payload": {"arrays": {**coordinates, **fields}},
    }
    full = {
        "inventory": {"keys": keys.copy()},
        "observables": observables.copy(),
        "closure": -1.0e-6,
        "orders": deepcopy(orders),
        "fields": {name: value.copy() for name, value in fields.items()},
        "coordinates": {name: value.copy() for name, value in coordinates.items()},
    }
    return hybrid, full


def test_identical_h5_same_grid_data_passes_all_primary_gates():
    hybrid, full = _synthetic_data()
    result = _compare_h5_hybrid_full3d_data(hybrid, full)

    assert result["pass"] is True
    assert result["primary_pass"] is True
    assert result["inventory"]["pass"] is True
    assert result["selected_EH"]["pass"] is True
    assert result["normal_flux"]["pass"] is True
    assert result["orders"]["primary_count"] == 10
    assert result["orders"]["weak_count"] == 29
    assert result["orders"]["below_weak_floor_count"] == 565


def test_weak_amplitude_failure_does_not_veto_primary_but_is_reported():
    hybrid, full = _synthetic_data()
    key = _order_keys()[10]
    full["orders"][key]["outgoing_amplitude"] *= -1.0

    result = _compare_h5_hybrid_full3d_data(hybrid, full)

    assert result["primary_pass"] is True
    assert result["pass"] is True
    assert result["orders"]["weak_pass"] is False
    assert result["orders"]["full_channel_pass"] is False
    assert result["orders"]["weak_rows"][0]["pass"] is False


def test_single_plane_field_failure_vetoes_overall_field_gate():
    hybrid, full = _synthetic_data()
    full["fields"]["E_V_per_m"][0] *= 1.011

    result = _compare_h5_hybrid_full3d_data(hybrid, full)

    field = result["selected_EH"]["fields"]["E_V_per_m"]
    assert field["relative_l2"] <= field["limit"]
    assert field["planes"][0]["relative_l2"] > field["planes"][0]["limit"]
    assert field["planes"][0]["pass"] is False
    assert field["pass"] is False
    assert result["primary_pass"] is False


@pytest.mark.parametrize("shape", ((4, 2, 2, 3), (5, 2, 2, 2)))
def test_selected_field_shape_contract_fails_closed(shape):
    hybrid, full = _synthetic_data()
    invalid = np.ones(shape, dtype=np.complex128)
    hybrid["payload"]["arrays"]["E_V_per_m"] = invalid.copy()
    full["fields"]["E_V_per_m"] = invalid.copy()

    with pytest.raises(IdentityCheckError, match="shape mismatch"):
        _compare_h5_hybrid_full3d_data(hybrid, full)


def test_same_grid_wrapper_requires_equal_physical_model_identity():
    hybrid, full = _synthetic_data()
    hybrid["manifest"] = {"physical_model_sha256": "a" * 64}
    full["physical_model_sha256"] = "b" * 64

    identity = _v2_physical_model_identity(hybrid, full)

    assert (
        identity["hybrid_physical_model_sha256"]
        != identity["full3d_physical_model_sha256"]
    )
    assert identity["pass"] is False


@pytest.mark.parametrize(
    "change",
    ("observable", "field", "primary_order", "aggregate"),
)
def test_each_primary_gate_can_fail(change):
    hybrid, full = _synthetic_data()
    if change == "observable":
        full["observables"]["R_total"] += 2.0e-5
    elif change == "field":
        full["fields"]["E_V_per_m"][0, 0, 0, 0] += 0.2
    elif change == "primary_order":
        key = _order_keys()[0]
        full["orders"][key]["power_ratio"] *= 1.01
        full["orders"][key]["outgoing_amplitude"] *= 1.01
    else:
        for index in range(10):
            key = _order_keys()[index]
            full["orders"][key]["power_ratio"] += 5.0e-8

    result = _compare_h5_hybrid_full3d_data(hybrid, full)

    assert result["pass"] is False
    assert result["primary_pass"] is False
    if change == "observable":
        assert result["observables"]["values"]["R_total"]["pass"] is False
    elif change == "field":
        assert result["selected_EH"]["fields"]["E_V_per_m"]["pass"] is False
    elif change == "primary_order":
        assert result["orders"]["primary_pass"] is False
    else:
        assert result["orders"]["power_weighted_pass"] is False


def test_missing_field_or_inventory_fails_closed():
    hybrid, full = _synthetic_data()
    del full["fields"]["H_A_per_m"]
    with pytest.raises(IdentityCheckError, match="missing H_A_per_m"):
        _compare_h5_hybrid_full3d_data(hybrid, full)

    hybrid, full = _synthetic_data()
    full["inventory"]["keys"] = full["inventory"]["keys"][:-1]
    result = _compare_h5_hybrid_full3d_data(hybrid, full)
    assert result["inventory"]["pass"] is False
    assert result["primary_pass"] is False


def test_threshold_edge_and_phase_wrap_are_finite():
    hybrid, full = _synthetic_data()
    full["observables"]["R_total"] = hybrid["observables"]["R_total"] + 1.0e-5
    edge = _compare_h5_hybrid_full3d_data(hybrid, full)
    assert edge["observables"]["values"]["R_total"]["pass"] is True

    key = _order_keys()[10]
    left = np.exp(1j * (np.pi - 0.01))
    right = np.exp(1j * (-np.pi + 0.01))
    hybrid["orders"][key]["outgoing_amplitude"] = left
    full["orders"][key]["outgoing_amplitude"] = right
    wrapped = _compare_h5_hybrid_full3d_data(hybrid, full)
    phase = wrapped["orders"]["weak_rows"][0]["wrapped_phase_delta_rad"]
    assert abs(phase) == pytest.approx(0.02, abs=1.0e-12)
    zero_hybrid, zero_full = _synthetic_data()
    zero_full["orders"][key]["outgoing_amplitude"] = 0.0j
    zero_hybrid["orders"][key]["outgoing_amplitude"] = 0.0j
    zero = _compare_h5_hybrid_full3d_data(zero_hybrid, zero_full)
    row = zero["orders"]["weak_rows"][0]
    assert np.isfinite(row["amplitude_relative_delta"])
    assert np.isfinite(row["amplitude_denominator"])
