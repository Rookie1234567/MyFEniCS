from __future__ import annotations

import numpy as np
import pytest

from benchmarks.task033_reduced_equal_accuracy import (
    ReducedEqualAccuracyError,
    classify_resource_reduction,
    compare_full3d_to_reference,
)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (1.0, "weak"),
        (1.299999, "weak"),
        (1.3, "useful_positive"),
        (2.0, "clear_success"),
        (3.0, "engineering_target"),
    ],
)
def test_review_v5_resource_reduction_boundaries(ratio: float, expected: str) -> None:
    assert classify_resource_reduction(ratio) == expected


def _full3d(scale: float) -> dict:
    coordinates = {
        "x_nm": np.array([0.0, 1.0]),
        "y_nm": np.array([0.0]),
        "z_nm": np.array([10.0, 30.0]),
        "interface_z_nm": np.array([10.0, 30.0]),
    }
    arrays = {
        **coordinates,
        "E_V_per_m": np.full((2, 1, 2, 3), scale, dtype=np.complex128),
        "H_A_per_m": np.full((2, 1, 2, 3), 2.0 * scale, dtype=np.complex128),
        "E_t_interface_V_per_m": np.full(
            (2, 1, 2, 2), scale, dtype=np.complex128
        ),
        "H_t_interface_A_per_m": np.full(
            (2, 1, 2, 2), 2.0 * scale, dtype=np.complex128
        ),
    }
    order = {
        "power_ratio": 0.2 * scale,
        "outgoing_amplitude_at_boundary": [scale, 0.0],
    }
    return {
        "arrays": arrays,
        "orders": {("top", 0, 0, "s"): order},
        "descriptor": {
            "results": {
                "R_total": 0.1 * scale,
                "T_total": 0.2 * scale,
                "A_balance": 1.0 - 0.3 * scale,
                "A_volume_total": 1.0 - 0.3 * scale,
                "linear_system_true_relative_residual": 1.0e-12,
            }
        },
    }


def test_direct_comparison_computes_planes_interfaces_orders_and_scalars() -> None:
    result = compare_full3d_to_reference(_full3d(1.0), _full3d(1.1))
    assert result["selected_planes"]["max_electric_relative_l2"] == pytest.approx(0.1)
    assert result["selected_planes"]["max_magnetic_relative_l2"] == pytest.approx(0.1)
    assert result["interfaces"]["max_electric_tangential_relative_l2"] == pytest.approx(
        0.1
    )
    assert result["scalar_observables"]["R_total"]["absolute_error"] == pytest.approx(
        0.01
    )
    assert result["diffraction_orders"]["significant_order_count"] == 1
    assert result["full_true_relative_residual"] == pytest.approx(1.0e-12)


def test_direct_comparison_rejects_different_sample_coordinates() -> None:
    reference = _full3d(1.0)
    candidate = _full3d(1.0)
    candidate["arrays"]["x_nm"] = np.array([0.0, 2.0])
    with pytest.raises(ReducedEqualAccuracyError, match="sample coordinates differ"):
        compare_full3d_to_reference(reference, candidate)
