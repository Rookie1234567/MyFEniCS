from __future__ import annotations

import pytest

from benchmarks.postprocess_task40_p3_mode_staircase import (
    _mode_comparison,
    _mode_key,
    _same_discretization_mode_comparison,
)


def test_mode_key_accepts_manifest_rows_with_only_m_n_fields():
    assert _mode_key({"side": "top", "m": 2, "n": -1, "polarization": "s"}) == (
        "top",
        2,
        -1,
        "s",
    )


def _mode_row(amplitude: complex, power_ratio: float) -> dict:
    return {
        "propagating": True,
        "power_ratio": power_ratio,
        "outgoing_amplitude_at_boundary": [amplitude.real, amplitude.imag],
    }


def test_p3_mode_gate_uses_frozen_significant_set_and_keeps_weak_mode_deltas():
    keys = [
        (side, i // 2, 0, "s" if i % 2 == 0 else "p")
        for side in ("top", "bottom")
        for i in range(40)
    ]
    baseline = {key: _mode_row(0j, 1.0e-7 if i == 0 else 1.0e-12) for i, key in enumerate(keys)}
    first = {key: _mode_row(1.0 + 0.0j if i == 0 else 1.0e-13 + 0.0j, 0.0) for i, key in enumerate(keys)}
    second = {key: _mode_row(1.005 + 0.0j if i == 0 else 2.0e-13 + 0.0j, 0.0) for i, key in enumerate(keys)}

    result = _mode_comparison(first, second, baseline, incident_amplitude=1.0)

    assert result["common_propagating_mode_count"] == 80
    assert result["significant_mode_count"] == 1
    assert result["weak_mode_count"] == 79
    assert result["significant_gate"]["pass"] is True
    significant = next(
        row
        for row in result["all_common_propagating_mode_comparisons"]
        if row["significant_by_frozen_M0_rule"]
    )
    assert significant["incident_normalized_amplitude_difference"] == pytest.approx(0.005)


def test_same_discretization_comparison_keeps_all_modes_and_uses_frozen_significant_set():
    significant = ("top", 0, 0, "s")
    weak = ("bottom", 8, 2, "p")
    first = {
        significant: {**_mode_row(1.0 + 0.0j, 0.0), "propagating": True},
        weak: {**_mode_row(1.0e-24 + 0.0j, 0.0), "propagating": False},
    }
    second = {
        significant: {**_mode_row(1.005 + 0.0j, 0.0), "propagating": True},
        weak: {**_mode_row(2.0e-24 + 0.0j, 0.0), "propagating": False},
    }

    result = _same_discretization_mode_comparison(
        first, second, significant_keys={significant}, incident_amplitude=1.0
    )

    assert result["ordered_mode_count"] == 2
    assert result["propagating_count"] == 1
    assert result["significant_gate"]["pass"] is True
    assert result["all_ordered_mode_comparisons"][1]["absolute_amplitude_difference"] == pytest.approx(1.0e-24)
    assert result["all_ordered_mode_comparisons"][1]["relative_difference_to_first_amplitude"] == pytest.approx(1.0)


def test_same_discretization_comparison_rejects_different_ordered_keys():
    a = ("top", 0, 0, "s")
    b = ("bottom", 0, 0, "s")
    row = {**_mode_row(1.0 + 0.0j, 0.0), "propagating": True}
    with pytest.raises(ValueError, match="keys/order differ"):
        _same_discretization_mode_comparison(
            {a: row, b: row},
            {b: row, a: row},
            significant_keys={a},
            incident_amplitude=1.0,
        )
