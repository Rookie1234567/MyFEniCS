from __future__ import annotations

import unittest

from benchmarks.task035_phase_cd import run_phase_cd_suite


class Task035PhaseCDCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_phase_cd_suite()

    def test_phase_C_D_and_components_close_without_promotion(self) -> None:
        self.assertEqual(self.record["status"], "phase_cd_complete_controlled_negative")
        self.assertEqual(self.record["phase_c"]["phase_c_internal_gate"], "complete_controlled_negative")
        self.assertEqual(self.record["B3_B4"]["status"], "B3_B4_pass")
        self.assertEqual(self.record["phase_d"]["phase_d_internal_gate"], "complete")
        self.assertFalse(self.record["production_estimator_selected"])
        self.assertFalse(self.record["production_backend_selected"])
        self.assertFalse(self.record["ordinary_default_changed"])
        self.assertFalse(self.record["phase_e_unlocked"])

    def test_clean_source_or_content_hash_contract_is_present(self) -> None:
        provenance = self.record["provenance"]
        self.assertEqual(provenance["petsc_scalar_dtype"], "complex128")
        self.assertGreaterEqual(len(provenance["tracked_content_bindings"]), 4)
        self.assertTrue(all(len(value) == 64 for value in provenance["tracked_content_bindings"].values()))


if __name__ == "__main__":
    unittest.main()
