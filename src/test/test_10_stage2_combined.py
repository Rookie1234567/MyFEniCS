from __future__ import annotations

import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, fresnel_smoke_config, run_small_3d_case


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run combined 3D Stage-2 PDE tests.")
class TestStage2Combined(unittest.TestCase):
    def test_n_substrate_one_is_the_final_flat_interface_sanity_case(self):
        cfg = fresnel_smoke_config(
            n_substrate=1.0 + 0.0j,
            use_floquet_xy=False,
            use_pml=False,
            mesh_target_size=200.0,
        )
        summary = run_small_3d_case(cfg, "level10_nsub1")
        self.assertLess(abs(float(summary["R_total"])), 5.0e-2)
        self.assertLess(abs(float(summary["T_total"]) - 1.0), 5.0e-2)

    def test_n_substrate_one_with_floquet_is_the_periodic_sanity_case(self):
        cfg = fresnel_smoke_config(
            n_substrate=1.0 + 0.0j,
            use_floquet_xy=True,
            use_pml=False,
            mesh_target_size=200.0,
        )
        summary = run_small_3d_case(cfg, "level10_nsub1_floquet")
        self.assertTrue(summary["use_floquet_xy"])
        self.assertFalse(summary["use_pml"])
        self.assertLess(abs(float(summary["floquet_x_face_mismatch"])), 1.0e-10)
        self.assertLess(abs(float(summary["floquet_y_face_mismatch"])), 1.0e-10)
        self.assertLess(abs(float(summary["R_total"])), 5.0e-2)
        self.assertLess(abs(float(summary["T_total"]) - 1.0), 5.0e-2)


if __name__ == "__main__":
    unittest.main()
