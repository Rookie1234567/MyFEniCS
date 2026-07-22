from __future__ import annotations

import unittest

from src.validation.task035_component_fixtures import run_component_fixture_suite


class Task035ComponentFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_component_fixture_suite()

    def test_B3_actual_tags_interface_fault_and_enrichment(self) -> None:
        b3 = self.record["b3"]
        self.assertEqual(b3["status"], "component_fixture_pass")
        self.assertTrue(b3["real_fe"])
        self.assertTrue(b3["material_tag_fault_detected"])
        self.assertGreater(b3["actual_material_interface_facets"], 0)
        self.assertTrue(b3["enriched_proxy_improves"])
        self.assertIn(b3["selected_direction"], ("x", "y", "z"))
        self.assertIn("argmax", b3["selection_rule"])

    def test_B4_actual_Et_Ht_spatial_DtN_M_and_QEP(self) -> None:
        b4 = self.record["b4"]
        self.assertEqual(b4["status"], "component_fixture_pass")
        self.assertTrue(b4["real_target_trace"])
        self.assertFalse(b4["new_pde_run"])
        self.assertGreater(b4["Et_norm"], 0.0)
        self.assertGreater(b4["Ht_impedance_scaled_norm"], 0.0)
        self.assertNotEqual(b4["DtN_trace_residual"], b4["DtN_operator_fault_residual"])
        self.assertGreaterEqual(len(b4["M_perturbations"]), 2)
        self.assertEqual(b4["QEP_diagnostic"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
