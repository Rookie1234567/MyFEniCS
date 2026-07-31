from __future__ import annotations

import unittest
from dataclasses import replace
from unittest import mock

import numpy as np

from src.common.config_3d import target_stage4_config
from src.postprocessing import full3d_reference
from src.postprocessing.full3d_reference import (
    MAX_REPLICATED_SAMPLE_BYTES,
    periodic_plane_sample_grid,
    reference_plane_sides,
)


class Full3dReferenceExportTests(unittest.TestCase):
    def test_default_is_disabled(self):
        cfg = target_stage4_config(degree=2, h_nm=5.0)
        self.assertFalse(cfg.full3d_reference_export)
        self.assertEqual(cfg.full3d_reference_plane_z, ())

    def test_periodic_grid_excludes_duplicate_boundaries_and_preserves_planes(self):
        cfg = replace(
            target_stage4_config(degree=2, h_nm=5.0),
            full3d_reference_export=True,
            full3d_reference_plane_z=(10.0, 30.0, 60.0, 90.0, 110.0),
            full3d_reference_sample_count_x=10,
            full3d_reference_sample_count_y=5,
        )
        x_nm, y_nm, z_nm, points_nm = periodic_plane_sample_grid(cfg)
        self.assertEqual(points_nm.shape, (250, 3))
        np.testing.assert_allclose(z_nm, (10.0, 30.0, 60.0, 90.0, 110.0))
        self.assertGreater(x_nm.min(), cfg.x_min)
        self.assertLess(x_nm.max(), cfg.x_max)
        self.assertGreater(y_nm.min(), cfg.y_min)
        self.assertLess(y_nm.max(), cfg.y_max)
        np.testing.assert_allclose(points_nm[:50, 2], 10.0)
        np.testing.assert_allclose(points_nm[-50:, 2], 110.0)

    def test_replicated_payload_guard_is_bounded(self):
        requested = 5 * 20 * 40 * 3 * np.dtype(np.complex128).itemsize * 2
        self.assertLess(requested, MAX_REPLICATED_SAMPLE_BYTES)

    def test_replicated_payload_guard_precedes_coordinate_allocation(self):
        cfg = replace(
            target_stage4_config(degree=2, h_nm=5.0),
            full3d_reference_export=True,
            full3d_reference_plane_z=(10.0, 110.0),
            full3d_reference_sample_count_x=100_000,
            full3d_reference_sample_count_y=100_000,
        )
        with (
            mock.patch.object(
                full3d_reference.np,
                "arange",
                side_effect=AssertionError("coordinate allocation attempted"),
            ) as arange,
            mock.patch.object(
                full3d_reference.np,
                "meshgrid",
                side_effect=AssertionError("mesh allocation attempted"),
            ) as meshgrid,
            self.assertRaisesRegex(ValueError, r"64 MiB.*requested [0-9]+ bytes"),
        ):
            periodic_plane_sample_grid(cfg)
        arange.assert_not_called()
        meshgrid.assert_not_called()

    def test_interface_traces_are_selected_from_inside_middle_region(self):
        sides = reference_plane_sides(5, 4).reshape((5, 4))
        np.testing.assert_array_equal(sides[0], 1)
        np.testing.assert_array_equal(sides[-1], -1)
        np.testing.assert_array_equal(sides[1:-1], 1)

    def test_invalid_or_duplicate_planes_fail_closed(self):
        base = target_stage4_config(degree=2, h_nm=5.0)
        for planes in ((), (10.0, 10.0), (30.0, 10.0), (-20.0,)):
            cfg = replace(
                base,
                full3d_reference_export=True,
                full3d_reference_plane_z=planes,
            )
            with self.subTest(planes=planes), self.assertRaises(ValueError):
                periodic_plane_sample_grid(cfg)


if __name__ == "__main__":
    unittest.main()
