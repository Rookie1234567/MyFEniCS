from __future__ import annotations

import unittest

from src.validation.task035_target_artifact_bakeoff import run_target_artifact_bakeoff


class Task035TargetArtifactBakeoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_target_artifact_bakeoff()

    def test_target_identity_and_required_points(self) -> None:
        self.assertEqual(
            [row["point"] for row in self.record["points"]],
            ["p2_h5", "p2_h3", "p3_h10"],
        )
        for row in self.record["points"]:
            identity = row["target_identity"]
            self.assertEqual(identity["grazing_angle_deg"], 10.0)
            self.assertEqual(identity["polarization"], "S")
            self.assertIn("Task034 fixed", identity["geometry"])

    def test_R1_R5_DtN_and_R2_policy_are_explicit(self) -> None:
        for row in self.record["points"]:
            self.assertGreater(row["R1_sampled_strong_residual_proxy"]["norm"], 0.0)
            self.assertGreater(row["R5_discrete_two_level_proxy"]["norm"], 0.0)
            self.assertFalse(row["R5_discrete_two_level_proxy"]["formal_hierarchical_FE_R5"])
            self.assertEqual(
                row["R2_kh_over_p"]["policy"],
                "diagnostic_only_excluded_from_marking",
            )
            self.assertGreater(row["external_DtN_sample_split"]["top_sample_plane_l2"], 0.0)

    def test_required_metrics_and_negative_scope_are_preserved(self) -> None:
        for row in self.record["points"]:
            self.assertTrue(row["observable_error"]["positive_reduction"])
            self.assertIn("pearson", row["R1_sampled_strong_residual_proxy"]["local_error_correlation"])
            self.assertEqual(len(row["R1_sampled_strong_residual_proxy"]["marked_set"]["global_sample_ids_sha256"]), 64)
            self.assertGreaterEqual(row["R1_R5_marked_set_jaccard"], 0.0)
            self.assertLessEqual(row["R1_R5_marked_set_jaccard"], 1.0)
        self.assertEqual(self.record["status"], "controlled_negative_provisional_R1")
        self.assertFalse(self.record["production_estimator_selected"])
        self.assertTrue(self.record["phase_d_low_cost_unlocked"])
        self.assertFalse(self.record["actual_refinement_evidence"]["estimator_marked_refinement"])
        self.assertLess(
            self.record["actual_refinement_evidence"]["observable_error_reduction_fraction"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
