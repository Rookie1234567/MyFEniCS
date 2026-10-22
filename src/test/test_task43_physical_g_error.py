from __future__ import annotations

import unittest

import numpy as np

from src.adaptivity.physical_g_error import (
    accumulate_physical_g_cell_contributions,
    attribute_points_to_axis_aligned_cells,
    dorfler_mark_physical_g,
    physical_g_difference_metrics,
)


class Task43PhysicalGErrorTests(unittest.TestCase):
    def test_point_attribution_supports_coarse_leaves_over_union_intervals(self) -> None:
        axes = (
            np.asarray([0.0, 1.0, 2.0]),
            np.asarray([0.0, 1.0, 2.0]),
            np.asarray([0.0, 1.0]),
        )
        bounds = np.asarray(
            [
                [[0.0, 0.0, 0.0], [2.0, 1.0, 1.0]],
                [[0.0, 1.0, 0.0], [2.0, 2.0, 1.0]],
            ],
            dtype=np.float64,
        )
        points = np.asarray(
            [[0.5, 0.5, 0.5], [1.5, 0.5, 0.5], [0.5, 1.5, 0.5]],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(
            attribute_points_to_axis_aligned_cells(points, axes, bounds),
            np.asarray([0, 0, 1], dtype=np.int64),
        )

    def test_point_attribution_rejects_uncovered_or_overlapping_cells(self) -> None:
        axes = (
            np.asarray([0.0, 1.0, 2.0]),
            np.asarray([0.0, 1.0]),
            np.asarray([0.0, 1.0]),
        )
        points = np.asarray([[0.5, 0.5, 0.5]])
        left_cell = np.asarray([[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]])
        with self.assertRaisesRegex(ValueError, "uncovered"):
            attribute_points_to_axis_aligned_cells(points, axes, left_cell)
        overlapping_cells = np.concatenate(
            (
                left_cell,
                np.asarray([[[0.0, 0.0, 0.0], [2.0, 1.0, 1.0]]]),
            ),
            axis=0,
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            attribute_points_to_axis_aligned_cells(points, axes, overlapping_cells)

    def test_cell_contributions_close_to_full_g_difference(self) -> None:
        k0 = 0.5
        weights = np.asarray([0.25, 0.75, 0.5], dtype=np.float64)
        cell_indices = np.asarray([1, 0, 1], dtype=np.int32)
        ref_e = np.zeros((3, 3), dtype=np.complex128)
        ref_curl = np.zeros_like(ref_e)
        candidate_e = np.asarray(
            [[1.0, 0.0j, 0.0j], [0.0j, 2.0, 0.0j], [0.0j, 0.0j, 1j]],
            dtype=np.complex128,
        )
        candidate_curl = np.asarray(
            [[0.0j, 0.5, 0.0j], [1.0, 0.0j, 0.0j], [0.0j, 0.0j, -0.5j]],
            dtype=np.complex128,
        )

        metrics = physical_g_difference_metrics(
            ref_e,
            candidate_e,
            ref_curl,
            candidate_curl,
            weights,
            k0_per_nm=k0,
            incident_g_norm_floor=np.sqrt(7.0),
        )
        contributions = accumulate_physical_g_cell_contributions(
            ref_e,
            candidate_e,
            ref_curl,
            candidate_curl,
            weights,
            cell_indices,
            cell_global_ids=np.asarray([20, 21], dtype=np.int64),
            k0_per_nm=k0,
        )
        self.assertAlmostEqual(
            float(np.sum(contributions)),
            float(metrics["difference_g_norm"]) ** 2,
            places=13,
        )
        self.assertGreater(contributions[0], 0.0)
        self.assertGreater(contributions[0], contributions[1])

    def test_dorfler_marking_is_stable_and_expands_cutoff_ties(self) -> None:
        ids = np.asarray([40, 10, 30, 20], dtype=np.int64)
        contributions = np.asarray([0.5, 0.25 + 5e-13, 0.25 - 5e-13, 0.0])
        marked, report = dorfler_mark_physical_g(
            ids,
            contributions,
            theta=0.75,
        )
        permuted, permuted_report = dorfler_mark_physical_g(
            ids[::-1],
            contributions[::-1],
            theta=0.75,
        )
        self.assertEqual(marked.tolist(), [10, 30, 40])
        self.assertEqual(permuted.tolist(), marked.tolist())
        self.assertEqual(report["minimal_count_before_tie_expansion"], 2)
        self.assertEqual(report["cutoff_tie_expansion_count"], 1)
        self.assertEqual(report["marked_global_cell_ids_sha256"], permuted_report["marked_global_cell_ids_sha256"])
        self.assertGreaterEqual(report["captured_fraction"], 0.75)

    def test_zero_reference_raw_ratio_is_undefined_but_floor_ratio_is_finite(self) -> None:
        zeros = np.zeros((2, 3), dtype=np.complex128)
        candidate = np.ones((2, 3), dtype=np.complex128)
        metrics = physical_g_difference_metrics(
            zeros,
            candidate,
            zeros,
            zeros,
            np.asarray([1.0, 1.0]),
            k0_per_nm=1.0,
            incident_g_norm_floor=4.0,
        )
        self.assertIsNone(metrics["relative_to_reference"])
        self.assertFalse(metrics["relative_to_reference_defined"])
        self.assertAlmostEqual(float(metrics["relative_with_incident_floor"]), np.sqrt(6.0) / 4.0)


if __name__ == "__main__":
    unittest.main()
