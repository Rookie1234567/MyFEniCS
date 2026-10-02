from types import SimpleNamespace

import numpy as np

from benchmarks.postprocess_task40_review_v3_background_attribution import (
    _sample_coordinates,
)
from src.postprocessing.task40_saved_field_h_comparison import (
    _attribution_terms,
    _format_attribution,
    _incident_norm_for_quantity,
)


def test_fixed_sample_axes_expand_in_archived_z_y_x_order() -> None:
    samples = {
        "x_nm": np.arange(40, dtype=np.float64),
        "y_nm": 100.0 + np.arange(20, dtype=np.float64),
        "z_nm": -2.0 + np.arange(5, dtype=np.float64),
    }

    points, hashes = _sample_coordinates(SimpleNamespace(samples=samples))

    assert points.shape == (4000, 3)
    np.testing.assert_array_equal(points[0], [0.0, 100.0, -2.0])
    np.testing.assert_array_equal(points[1], [1.0, 100.0, -2.0])
    np.testing.assert_array_equal(points[40], [0.0, 101.0, -2.0])
    np.testing.assert_array_equal(points[800], [0.0, 100.0, -1.0])
    assert set(hashes) == {"x_nm", "y_nm", "z_nm"}
    assert all(len(value) == 64 for value in hashes.values())


def test_incident_normalizers_follow_quantity_units() -> None:
    incident_e, incident_h, k0 = 2.0, 3.0, 5.0

    assert _incident_norm_for_quantity("E_scattered", incident_e, incident_h, k0) == 2.0
    assert _incident_norm_for_quantity("H_scattered", incident_e, incident_h, k0) == 3.0
    assert _incident_norm_for_quantity("curl_E_total", incident_e, incident_h, k0) == 10.0
    assert _incident_norm_for_quantity(
        "scaled_curl_E_scattered", incident_e, incident_h, k0
    ) == 2.0


def test_complex_attribution_closes_and_raw_curl_scales_from_scaled_curl() -> None:
    d = np.asarray([[1.0 + 2.0j, 3.0 - 1.0j], [0.5 - 1.0j, 2.0j]])
    d_b = np.asarray([[0.25 - 1.0j, 2.0 + 0.5j], [1.5 + 0.5j, -1.0j]])
    weights = np.asarray([2.0, 0.5])
    terms = _attribution_terms(d, d_b, weights)
    scale = 4.0
    k0 = 5.0

    scaled = _format_attribution(
        terms, scale, "V/m", volume_integrated=True
    )
    raw_curl = _format_attribution(
        terms,
        scale,
        "V/m/nm",
        derivative_scale=k0,
        volume_integrated=True,
    )
    expected_inner = np.dot(np.sum(np.conjugate(d) * d_b, axis=1), weights)

    np.testing.assert_allclose(
        scaled["complex_inner_product"],
        [expected_inner.real * scale**2, expected_inner.imag * scale**2],
    )
    assert scaled["two_real_inner_product"] == 2.0 * scaled["complex_inner_product"][0]
    assert scaled["squared_norm_identity_closure_relative"] < 1.0e-14
    assert scaled["l2_norm_unit"] == "V/m·nm^(3/2)"
    assert raw_curl["l2_norm_unit"] == "V/m/nm·nm^(3/2)"
    assert raw_curl["d_l2_norm"] == scaled["d_l2_norm"] * k0
    assert raw_curl["complex_inner_product"][0] == (
        scaled["complex_inner_product"][0] * k0**2
    )
