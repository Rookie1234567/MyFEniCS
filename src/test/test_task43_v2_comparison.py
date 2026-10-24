from __future__ import annotations

import copy

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    PERTURBATION_LIMITS,
    R13_MODE_KEYS,
    R14_MODE_KEYS,
    compare_field_sample_bundles,
    compare_r13_r14_modal_outputs,
)


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
    )

    assert not result["r14_tail_224"]["per_channel_power_ratio_maximum"]["pass"]
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
