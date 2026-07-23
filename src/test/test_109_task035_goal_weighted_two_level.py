from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
from mpi4py import MPI

from src.adaptivity.goal_weighted_two_level import (
    _tolerance_normalized_multi_goal_values,
    run_target_goal_weighted_two_level,
)
from src.adaptivity.target_dwr_adaptive_cycles import (
    _resolve_theta_schedule,
)


ROOT = Path(__file__).resolve().parents[2]


class Task035GoalWeightedTwoLevelTests(unittest.TestCase):
    def test_tolerance_normalized_multi_goal_values_are_fail_closed(self) -> None:
        values = _tolerance_normalized_multi_goal_values(
            {
                "R_total": np.array([2.0, 6.0]),
                "T_total": np.array([3.0, 8.0]),
            },
            {
                "R_total": 2.0,
                "T_total": 1.0,
                "A_volume_total": 4.0,
            },
        )
        np.testing.assert_allclose(
            values,
            np.array([np.sqrt(10.0), np.sqrt(73.0)]),
        )
        with self.assertRaisesRegex(ValueError, "tolerances"):
            _tolerance_normalized_multi_goal_values(
                {
                    "R_total": np.array([1.0]),
                    "T_total": np.array([1.0]),
                },
                {
                    "R_total": 0.0,
                    "T_total": 1.0,
                    "A_volume_total": 1.0,
                },
            )
        with self.assertRaisesRegex(ValueError, "aligned"):
            _tolerance_normalized_multi_goal_values(
                {
                    "R_total": np.array([1.0]),
                    "T_total": np.array([1.0, 2.0]),
                },
                {
                    "R_total": 1.0,
                    "T_total": 1.0,
                    "A_volume_total": 1.0,
                },
            )

    def test_theta_schedule_resolution_is_fail_closed(self) -> None:
        self.assertEqual(_resolve_theta_schedule(2, 0.5, None), (0.5, 0.5))
        self.assertEqual(_resolve_theta_schedule(2, 0.5, (0.5, 0.15)), (0.5, 0.15))
        with self.assertRaises(ValueError):
            _resolve_theta_schedule(2, 0.5, (0.5,))

    def test_actual_midpoint_dwr_and_physical_marking_are_mpi_stable(self) -> None:
        out_dir = (
            ROOT
            / "benchmarks/artifacts/task035/actual_dtn_adjoint"
            / f"goal_weighted_fixture_mpi{MPI.COMM_WORLD.size}"
        )
        result = run_target_goal_weighted_two_level(out_dir)
        self.assertTrue(result["pass"], result["DWR"])
        self.assertEqual(result["coarse"]["h_nm"], 50.0)
        self.assertEqual(result["enriched"]["h_nm"], 50.0)
        self.assertEqual(result["status"], "target_goal_weighted_two_level_pass")
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
                report["adjoint_solve"]["adjoint_residual"]["relative_residual"],
                1.0e-9,
            )
        combined_report = dwr["combined_relative_R_T"]
        combined = combined_report["marking"]
        self.assertEqual(combined["count"], 50)
        self.assertEqual(combined["minimal_count_before_tie_expansion"], 49)
        self.assertEqual(combined["cutoff_tie_expansion_count"], 1)
        self.assertEqual(
            combined["tie_policy"],
            "include_all_cutoff_contributions_within_relative_1e-10",
        )
        self.assertEqual(
            combined["global_cell_ids_sha256"],
            "82e2d5252d209d66f0aed63ca159620ad088a87594d9016cb447ec0195e2bb47",
        )
        self.assertEqual(
            combined_report["marked_geometry_sha256"],
            "2e009aedc501bffb9233f89e0b023209eef54edbe23927a9a88e3d8577e920c2",
        )
        normalized_report = dwr["tolerance_normalized_R_T"]
        self.assertEqual(normalized_report["marking"]["count"], 46)
        self.assertEqual(
            normalized_report["marked_geometry_sha256"],
            "828b0353a44e32d9dbd1baa345143e73c3037818fea5325eb0eb43bed9fed4e1",
        )
        self.assertEqual(
            normalized_report["normalization_authority"][
                "independent_adjoint_goals"
            ],
            ["R_total", "T_total"],
        )
        tolerances = normalized_report["normalization_authority"][
            "absolute_error_tolerances"
        ]
        self.assertAlmostEqual(tolerances["R_total"], 3.61556382344661e-05)
        self.assertAlmostEqual(tolerances["T_total"], 0.0002477575966640666)
        self.assertAlmostEqual(
            tolerances["A_volume_total"],
            0.00021160195840952412,
        )


if __name__ == "__main__":
    unittest.main()
