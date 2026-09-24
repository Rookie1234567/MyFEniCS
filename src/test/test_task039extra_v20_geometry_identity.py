"""Focused raw-geometry cache identity contract for the V20 route."""

from types import SimpleNamespace

import numpy as np

from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _lexicographic_min_coordinates,
)


def _mesh(width: float):
    coordinates = np.asarray([
        [0.0, 0.0, 0.0], [width, 0.0, 0.0],
        [0.0, 2.0, 0.0], [width, 2.0, 0.0],
        [0.0, 0.0, 3.0], [width, 0.0, 3.0],
        [0.0, 2.0, 3.0], [width, 2.0, 3.0],
    ])
    return SimpleNamespace(
        geometry=SimpleNamespace(
            dofmap=np.arange(8, dtype=np.int32).reshape(1, 8),
            x=coordinates,
        )
    )


def test_raw_unrounded_geometry_does_not_merge_near_widths():
    first = _mesh(1.0)
    second = _mesh(1.0000000000004)
    _, rounded_first = _canonical_axis_aligned_coordinates(
        first, 0, tolerance=1.0e-14, geometry_identity_policy="rounded_12"
    )
    _, rounded_second = _canonical_axis_aligned_coordinates(
        second, 0, tolerance=1.0e-14, geometry_identity_policy="rounded_12"
    )
    _, raw_first = _canonical_axis_aligned_coordinates(
        first, 0, tolerance=1.0e-14, geometry_identity_policy="raw_unrounded"
    )
    _, raw_second = _canonical_axis_aligned_coordinates(
        second, 0, tolerance=1.0e-14, geometry_identity_policy="raw_unrounded"
    )
    assert rounded_first == rounded_second
    assert raw_first != raw_second
    assert raw_second[0] - raw_first[0] > 0.0


def test_unrounded_representative_selection_is_order_independent():
    coordinates = []
    for width in (1.0000000000004, 1.0000000000001, 1.0000000000002):
        canonical, raw_widths = _canonical_axis_aligned_coordinates(
            _mesh(width),
            0,
            tolerance=1.0e-14,
            geometry_identity_policy="raw_unrounded",
        )
        assert raw_widths[0] == width
        coordinates.append(canonical)

    forward = coordinates[0]
    for candidate in coordinates[1:]:
        forward = _lexicographic_min_coordinates(forward, candidate)
    reverse = coordinates[-1]
    for candidate in reversed(coordinates[:-1]):
        reverse = _lexicographic_min_coordinates(reverse, candidate)

    np.testing.assert_array_equal(forward, reverse)
    assert any(np.array_equal(forward, candidate) for candidate in coordinates)
    assert float(forward.reshape(8, 3)[:, 0].max()) > 1.0
