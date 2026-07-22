from __future__ import annotations

import unittest

from src.validation.task035_real_fe_fixtures import run_real_fe_fixture_suite


class Task035RealFiniteElementFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_real_fe_fixture_suite()

    def test_b1_real_periodic_nedelec_fixture(self) -> None:
        fixture = self.record["b1"]
        self.assertEqual(fixture["status"], "real_fe_fixture_pass")
        self.assertTrue(fixture["real_fe"])
        self.assertFalse(fixture["pde_run"])
        self.assertEqual([point["degree"] for point in fixture["points"]], [1, 2])
        for point in fixture["points"]:
            self.assertTrue(point["cell_identity"]["pass"])
            self.assertLess(point["floquet_pair_residual"], 1.0e-9)
            self.assertGreater(point["orientation_fault_residual"], 1.0e-2)
            self.assertGreater(point["phase_fault_residual"], 1.0e-3)

    def test_b2_real_flat_lossy_layer_and_official_goal_fixture(self) -> None:
        fixture = self.record["b2"]
        self.assertEqual(
            fixture["status"], "real_fe_official_goal_fixture_pass"
        )
        self.assertTrue(fixture["real_fe"])
        self.assertEqual(
            fixture["r2_policy"],
            "diagnostic_only_kh_over_p_never_rescales_R1",
        )
        self.assertEqual(len(fixture["points"]), 3)
        coarse, _, fine = fixture["points"]
        self.assertLess(
            fine["relative_l2_field_error"], coarse["relative_l2_field_error"]
        )
        self.assertTrue(all(
            point["official_fixture_r00_error"] < 1.0e-10
            for point in fixture["points"]
        ))
        self.assertLess(fine["r1_indicator"], coarse["r1_indicator"])
        for point in fixture["points"]:
            self.assertLess(point["goal_derivative_absolute_error"], 1.0e-8)
            self.assertGreater(point["dtn_operator_perturbation_norm"], 1.0e-3)

    def test_minimum_gate_metadata_is_nonproduction(self) -> None:
        self.assertEqual(
            self.record["status"], "real_fe_fixture_minimum_pass"
        )
        self.assertFalse(self.record["canonical"])
        self.assertFalse(self.record["production_qualified"])
        self.assertFalse(self.record["target_grating_run"])


if __name__ == "__main__":
    unittest.main()
