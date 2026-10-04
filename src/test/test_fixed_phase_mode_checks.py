"""Complete per-key channel checks on small pure arrays; no FE/solver."""

import numpy as np
import pytest
from benchmarks.fixed_phase_checker import (
    align_physical_modes,
    complex_mode_differences,
    compare_from_arrays,
)
from src.test.test_fixed_phase_contract import _saved_physics_fixture


def observables():
    z = _saved_physics_fixture()
    for k in (
        "selected_total_E",
        "selected_total_H",
        "selected_scattered_E",
        "selected_scattered_H",
    ):
        z[k] = np.ones((6, 3), complex)
    for k in ("total_projection", "scattered_projection", "outgoing_origin"):
        z[k] = np.ones(340, complex)
    return z


def test_full_physical_key_alignment_accepts_permutation_and_rejects_bad_plane():
    z = observables()
    order = np.roll(np.arange(340), 13)
    other = dict(z)
    for name in (
        "mode_keys",
        "mode_k",
        "mode_e",
        "mode_boundary_z",
        "total_projection",
        "scattered_projection",
        "outgoing_origin",
        "outgoing_boundary",
        "per_level_power",
    ):
        other[name] = z[name][order]
    inverse = align_physical_modes(z, other)
    assert np.array_equal(other["mode_keys"][inverse], z["mode_keys"])
    other["mode_boundary_z"] = other["mode_boundary_z"] + 0.1
    with pytest.raises(ValueError, match="PHYSICAL_IDENTITY"):
        align_physical_modes(z, other)


def test_near_zero_channel_keeps_absolute_difference_and_registered_floor():
    z = observables()
    zero = np.zeros(340, complex)
    c = zero.copy()
    c[8] = 1e-14j
    r = complex_mode_differences(c, zero, z["mode_keys"])
    assert r["count"] == 340 and r["near_zero_count"] == 340
    assert r["max_relative"] == 0.01 and r["worst_absolute"] == 1e-14
    assert r["worst_denominator"] == 1e-12


def test_one_bad_complex_channel_cannot_hide_in_aggregate_norm():
    right = observables()
    left = dict(right)
    a = right["total_projection"].copy()
    a[17] += 0.002j
    left["total_projection"] = a
    assert np.linalg.norm(a - right["total_projection"]) / np.linalg.norm(a) < 1e-3
    eq = dict.fromkeys(
        (
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "independent_physical_weak",
            "recovery",
        ),
        0.0,
    )
    eq.update(channels=340, full_FE_recovered=True)
    raw = np.zeros((6, 4, 3))
    raw[:, :, 1:] = 1
    r = compare_from_arrays(
        {"E3_vs_E4_q15": raw, "E3_vs_E4_q30": raw.copy()},
        {"E3": left, "E4": right},
        {"E3": eq, "E4": eq},
    )
    assert not r["comparisons"]["E3_vs_E4"]["field_passed"]
    assert (
        r["comparisons"]["E3_vs_E4"]["per_mode_complex"]["total_projection"][
            "max_relative"
        ]
        == 0.002
    )
    assert not r["comparisons"]["E3_vs_E4"]["qualified"]
