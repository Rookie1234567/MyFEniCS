from __future__ import annotations

import unittest

from src.validation.task035_mesh_backend_bakeoff import run_mesh_backend_bakeoff


class Task035MeshBackendBakeoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = run_mesh_backend_bakeoff()

    def test_three_required_backends_are_compared(self) -> None:
        self.assertEqual(self.record["strip_tensor_negative_control"]["status"], "controlled_negative")
        self.assertEqual(self.record["multi_block_conforming_hexa"]["status"], "hexa_backend_blocker")
        self.assertEqual(self.record["tetra_marked_refinement_control"]["status"], "control_pass")

    def test_tetra_control_is_real_local_and_improves_proxy(self) -> None:
        tetra = self.record["tetra_marked_refinement_control"]
        self.assertTrue(tetra["real_dolfinx_refine"])
        self.assertGreater(tetra["refined_cells"], tetra["coarse_cells"])
        self.assertGreater(tetra["minimum_signed_volume_proxy"], 0.0)
        self.assertTrue(tetra["locality_pass"])
        self.assertGreater(tetra["observable_proxy_reduction_fraction"], 0.0)

    def test_no_production_or_phase_E_promotion(self) -> None:
        self.assertEqual(self.record["phase_d_internal_gate"], "complete")
        self.assertFalse(self.record["production_backend_selected"])
        self.assertFalse(self.record["ordinary_default_changed"])
        self.assertFalse(self.record["phase_e_unlocked"])


if __name__ == "__main__":
    unittest.main()
