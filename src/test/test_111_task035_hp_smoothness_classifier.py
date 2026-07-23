from __future__ import annotations

import unittest

import numpy as np

from src.adaptivity.hp_smoothness_classifier import (
    classify_hp_correction_decay,
)


class Task035HpSmoothnessClassifierTests(unittest.TestCase):
    def test_consecutive_correction_decay_classifies_h_p_and_floor(self) -> None:
        report = classify_hp_correction_decay(
            np.array([7, 2, 5, 9]),
            np.array([10.0, 8.0, 1.0e-14, 4.0]),
            np.array([2.0, 6.0, 2.0e-14, 2.0]),
            [9, 7, 5, 2],
            p_decay_ratio_threshold=0.5,
            significance_floor_fraction=1.0e-12,
        )
        self.assertTrue(report["pass"])
        self.assertFalse(report["ordinary_default_changed"])
        self.assertEqual(
            report["counts"],
            {
                "h_candidate": 1,
                "p_candidate": 2,
                "undetermined": 1,
            },
        )
        self.assertEqual(
            [
                (entry["canonical_cell_id"], entry["decision"])
                for entry in report["decisions"]
            ],
            [
                (2, "h_candidate"),
                (5, "undetermined"),
                (7, "p_candidate"),
                (9, "p_candidate"),
            ],
        )
        self.assertEqual(report["classified_cell_count"], 3)
        self.assertAlmostEqual(report["p_candidate_fraction_of_classified"], 2.0 / 3.0)

    def test_classifier_rejects_invalid_or_unaligned_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "aligned"):
            classify_hp_correction_decay(
                np.array([1, 1]),
                np.array([1.0, 2.0]),
                np.array([0.5, 1.0]),
                [1],
            )
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([-1.0]),
                np.array([0.5]),
                [1],
            )
        with self.assertRaisesRegex(ValueError, "subset"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [2],
            )
        with self.assertRaisesRegex(ValueError, "consecutive"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [1],
                degrees=(3, 5, 6),
            )
        with self.assertRaisesRegex(ValueError, "threshold"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [1],
                p_decay_ratio_threshold=1.0,
            )


if __name__ == "__main__":
    unittest.main()
