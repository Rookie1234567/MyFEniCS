import numpy as np
import pytest

from benchmarks.task039_review_v1_contracts import (
    _identity_sha256,
    compare_full3d_grid_views_v2,
)


def _v2_view(physical_sha: str) -> dict[str, object]:
    identity = {
        "geometry": {"domain": "task039"},
        "materials": {"epsilon": 12.0},
        "incidence": {"theta_deg": 10.0},
        "boundary": {"ports": "dtn"},
        "discretization": {"degree": 6},
    }
    keys = [("bottom", index, 0, "s") for index in range(300)] + [
        ("top", index, 0, "s") for index in range(304)
    ]
    orders = {}
    for index, key in enumerate(keys):
        orders[key] = {
            "power_ratio": 1.0e-7 if index == 0 else 1.0e-2,
            "outgoing_amplitude": 1.0e-6 + 0j if index == 0 else 1.0 + 0j,
        }
    coordinates = {
        "x_nm": np.asarray([0.0, 1.0]),
        "y_nm": np.asarray([0.0, 1.0]),
        "z_nm": np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]),
    }
    return {
        "mesh_target_nm": 6.0 if physical_sha == "h6" else 5.0,
        "physical_model_sha256": physical_sha,
        "physics_except_mesh_identity": identity,
        "physics_except_mesh_sha256": _identity_sha256(identity),
        "mode_keys": keys,
        "orders": orders,
        "observables": {
            "R_total": 0.9,
            "T_total": 0.01,
            "A_balance": 0.09,
            "A_volume": 0.09,
        },
        "closure": 1.0e-8,
        "coordinates": coordinates,
        "fields": {
            "E_V_per_m": np.ones((5, 2, 2, 3), dtype=np.complex128),
            "H_A_per_m": np.ones((5, 2, 2, 3), dtype=np.complex128) * 2.0,
        },
        "source": f"{physical_sha}-run",
    }


def test_v2_identical_data_passes_primary_and_full_channel() -> None:
    result = compare_full3d_grid_views_v2(_v2_view("h6"), _v2_view("h5"))
    assert result["pass"] is True
    assert result["classification"] == (
        "FULL3D_DIRECT_5NM_PRIMARY_REFERENCE_ESTABLISHED_AT_P6H5"
    )
    assert (
        "FULL3D_DIRECT_5NM_FULL_CHANNEL_REFERENCE_ESTABLISHED_AT_P6H5"
        in result["classification_flags"]
    )
    assert result["mode_keys"]["exact"] is True
    assert result["below_1e-8_count"] == 0


def test_v2_weak_relative_error_does_not_deny_primary() -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    weak_key = left["mode_keys"][0]
    right["orders"][weak_key]["outgoing_amplitude"] = 0j
    result = compare_full3d_grid_views_v2(left, right)
    assert result["primary_pass"] is True
    assert result["full_channel_order_gate"]["pass"] is False
    assert (
        "FULL_CHANNEL_WEAK_ORDER_CONVERGENCE_PENDING" in result["classification_flags"]
    )
    assert len(result["weak_orders"]["rows"]) == 1
    assert result["weak_orders"]["rows"][0]["amplitude_relative_delta"] == 1.0


def test_v2_primary_failure_does_not_establish_full_channel() -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    right["observables"]["R_total"] += 2.0e-5
    result = compare_full3d_grid_views_v2(left, right)
    assert result["primary_pass"] is False
    assert result["h5_role"] == "best_available_discrete_authority_only"
    assert result["full_channel_order_gate"]["pass"] is True
    assert (
        "FULL3D_DIRECT_5NM_FULL_CHANNEL_REFERENCE_ESTABLISHED_AT_P6H5"
        not in result["classification_flags"]
    )


@pytest.mark.parametrize("gate", ("observable", "field", "order", "aggregate"))
def test_v2_primary_gates_fail_independently(gate: str) -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    if gate == "observable":
        right["observables"]["R_total"] += 2.0e-5
    elif gate == "field":
        right["fields"]["E_V_per_m"] *= 1.003
    elif gate == "order":
        right["orders"][left["mode_keys"][1]]["power_ratio"] *= 1.002
    else:
        for row in right["orders"].values():
            row["power_ratio"] *= 1.0002
    result = compare_full3d_grid_views_v2(left, right)
    assert result["primary_pass"] is False
    if gate == "observable":
        assert result["gates"]["primary_observables"] is False
    elif gate == "field":
        assert result["gates"]["selected_fields"] is False
    elif gate == "order":
        assert result["gates"]["primary_orders"] is False
    else:
        assert result["gates"]["all_604_aggregate"] is False


@pytest.mark.parametrize("mutation", ("identity", "keys"))
def test_v2_identity_and_inventory_are_fail_closed(mutation: str) -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    if mutation == "identity":
        right["physics_except_mesh_identity"]["materials"]["epsilon"] = 13.0
    else:
        right["mode_keys"] = right["mode_keys"][:-1]
    with pytest.raises(ValueError):
        compare_full3d_grid_views_v2(left, right)


def test_v2_zero_amplitude_has_finite_wrapped_phase_delta() -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    key = left["mode_keys"][0]
    left["orders"][key]["outgoing_amplitude"] = 0j
    right["orders"][key]["outgoing_amplitude"] = 0j
    result = compare_full3d_grid_views_v2(left, right)
    phase = result["weak_orders"]["rows"][0]["wrapped_phase_delta_rad"]
    assert np.isfinite(phase)
    assert np.isfinite(result["weak_orders"]["rows"][0]["amplitude_relative_delta"])
    assert np.isfinite(result["weak_orders"]["rows"][0]["amplitude_denominator"])
    assert phase == 0.0


def test_v2_phase_delta_wraps_across_pi() -> None:
    left = _v2_view("h6")
    right = _v2_view("h5")
    key = left["mode_keys"][0]
    left["orders"][key]["outgoing_amplitude"] = np.exp(1j * (np.pi - 0.01))
    right["orders"][key]["outgoing_amplitude"] = np.exp(1j * (-np.pi + 0.01))
    result = compare_full3d_grid_views_v2(left, right)
    phase = result["weak_orders"]["rows"][0]["wrapped_phase_delta_rad"]
    assert abs(phase) == pytest.approx(0.02, abs=1.0e-12)
