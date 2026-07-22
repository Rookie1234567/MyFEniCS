from __future__ import annotations

from pathlib import Path
import unittest

from mpi4py import MPI

from src.adaptivity.goal_weighted_two_level import (
    run_target_goal_weighted_two_level,
)


ROOT = Path(__file__).resolve().parents[2]


class Task035GoalWeightedTwoLevelTests(unittest.TestCase):
    def test_actual_midpoint_dwr_and_physical_marking_are_mpi_stable(self) -> None:
        out_dir = (
            ROOT
            / "benchmarks/artifacts/task035/actual_dtn_adjoint"
            / f"goal_weighted_fixture_mpi{MPI.COMM_WORLD.size}"
        )
        result = run_target_goal_weighted_two_level(out_dir)
        self.assertTrue(result["pass"], result["DWR"])
        self.assertEqual(
            result["status"], "target_goal_weighted_two_level_pass"
        )
        dwr = result["DWR"]
        self.assertTrue(dwr["adjoint_qualification"]["pass"])
        self.assertEqual(
            dwr["rejected_localization"]["decision"],
            "controlled_negative_partition_dependent",
        )
        expected = {
            "R_total": (
                46,
                "8fae8171771a02ed262dd51a3304ba85cd187719f0394ec92bd1333bc5cbd9e5",
            ),
            "T_total": (
                46,
                "460acbaffc35cecce28be0c4ee8ed59291efab3265029e7e0755c748f44900e8",
            ),
        }
        for goal, (count, geometry_hash) in expected.items():
            report = dwr["goals"][goal]
            self.assertEqual(
                report["estimator"],
                "physical_adjoint_weighted_two_level_Hcurl_pairing",
            )
            self.assertAlmostEqual(report["absolute_effectivity"], 1.0, places=8)
            self.assertLess(abs(report["signed_goal_change_closure"]), 1.0e-9)
            self.assertEqual(report["marking"]["count"], count)
            self.assertEqual(report["marked_geometry_sha256"], geometry_hash)
            self.assertGreaterEqual(report["marking"]["captured_fraction"], 0.5)
            self.assertLess(
                report["adjoint_solve"]["adjoint_residual"][
                    "relative_residual"
                ],
                1.0e-9,
            )
        combined = dwr["combined_relative_R_T"]["marking"]
        self.assertEqual(combined["count"], 49)
        self.assertEqual(
            combined["global_cell_ids_sha256"],
            "ad59503356833a4e139962684369ae82f91e8bdaf48d9230bfb8e61a65a7b54b",
        )


if __name__ == "__main__":
    unittest.main()
