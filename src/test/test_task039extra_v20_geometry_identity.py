"""Focused raw-geometry cache identity contract for the V20 route."""

from types import SimpleNamespace

import numpy as np

from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
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
