from __future__ import annotations

import numpy as np
import pytest

from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    magnetic_field_from_electric_curl,
    scattered_field_samples,
    weighted_vector_field_metrics,
)


def test_common_quadrature_uses_union_of_reference_and_candidate_breakpoints() -> None:
    reference_axes = ([0.0, 1.0], [0.0, 3.75, 7.5, 11.25, 20.0], [0.0, 2.0])
    candidate_axes = ([0.0, 0.5, 1.0], [0.0, 2.5, 5.0, 10.0, 15.0, 20.0], [0.0, 1.0, 2.0])
    rule = build_common_volume_quadrature([reference_axes, candidate_axes], gauss_order=8)

    assert rule.axis_breakpoints_nm[0].tolist() == [0.0, 0.5, 1.0]
    assert rule.axis_breakpoints_nm[1].tolist() == [0.0, 2.5, 3.75, 5.0, 7.5, 10.0, 11.25, 15.0, 20.0]
    assert rule.axis_breakpoints_nm[2].tolist() == [0.0, 1.0, 2.0]
    assert rule.partition_box_count == 2 * 8 * 2

    # Degree 15 in each coordinate is integrated exactly by 8-point Gauss on
    # every box; this also checks the tensor-product nm^3 weights.
    integrand = rule.points_nm[:, 0] ** 15 * rule.points_nm[:, 1] ** 9 * rule.points_nm[:, 2] ** 7
    expected = (1.0 / 16.0) * (20.0**10 / 10.0) * (2.0**8 / 8.0)
    assert float(np.dot(rule.weights_nm3, integrand)) == pytest.approx(expected, rel=2e-13, abs=1e-12)
    assert float(rule.weights_nm3.sum()) == pytest.approx(40.0, rel=2e-14)


def test_common_quadrature_identity_is_stable_and_bound_to_resolved_rule() -> None:
    axes = ([0.0, 1.0], [0.0, 2.0], [0.0, 3.0])
    first = build_common_volume_quadrature([axes], gauss_order=8)
    repeat = build_common_volume_quadrature([axes], gauss_order=8)
    changed_order = build_common_volume_quadrature([axes], gauss_order=7)
    changed_partition = build_common_volume_quadrature(
        [axes, ([0.0, 0.5, 1.0], axes[1], axes[2])], gauss_order=8
    )

    assert first.rule_sha256 == repeat.rule_sha256
    assert first.rule_sha256 != changed_order.rule_sha256
    assert first.rule_sha256 != changed_partition.rule_sha256


def test_field_metrics_keep_phase_and_subtract_only_the_fixed_background() -> None:
    weights = np.array([0.25, 0.75], dtype=np.float64)
    reference = np.array([[1.0 + 0.0j, 0.0j], [1.0 + 0.0j, 0.0j]])
    candidate = 1j * reference
    metrics = weighted_vector_field_metrics(reference, candidate, weights)
    assert metrics["reference_l2"] == pytest.approx(1.0)
    assert metrics["candidate_l2"] == pytest.approx(1.0)
    assert metrics["difference_l2"] == pytest.approx(np.sqrt(2.0))
    assert metrics["relative_to_reference"] == pytest.approx(np.sqrt(2.0))
    assert metrics["relative_to_reference_defined"] is True

    zero_reference = weighted_vector_field_metrics(
        np.zeros_like(reference), reference, weights, reference_norm_floor=2.0
    )
    assert zero_reference["relative_to_reference"] is None
    assert zero_reference["relative_to_reference_defined"] is False
    assert zero_reference["relative_to_reference_or_floor"] == pytest.approx(0.5)

    total = reference + np.array([[0.0, 0.0], [0.0, 1.0j]])
    background = np.array([[0.5, 0.0], [0.5, 0.0]])
    assert np.array_equal(scattered_field_samples(total, background), total - background)
    with pytest.raises(ValueError, match="identical shapes"):
        scattered_field_samples(total, background[:1])


def test_magnetic_field_conversion_uses_solver_curl_convention() -> None:
    curl_values = np.array([[1.0 + 2.0j, -3.0j, 0.5]], dtype=np.complex128)
    scale = 1.0 / 377.0
    k0 = 2.0
    mu_r = 1.5 + 0.25j
    actual = magnetic_field_from_electric_curl(
        curl_values,
        magnetic_field_scale_A_per_m=scale,
        k0_per_nm=k0,
        mu_r=mu_r,
    )
    expected = (scale / (1j * k0 * mu_r)) * curl_values
    assert np.array_equal(actual, expected)
