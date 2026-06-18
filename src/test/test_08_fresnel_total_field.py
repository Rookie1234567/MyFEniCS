from __future__ import annotations

import math
import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, fresnel_smoke_config, run_small_3d_case


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D Fresnel PDE tests.")
class TestFresnelTotalField(unittest.TestCase):
    def test_fresnel_total_field_smoke_without_pml(self):
        cfg = fresnel_smoke_config(use_floquet_xy=False, use_pml=False, mesh_target_size=700.0)
        summary = run_small_3d_case(cfg, "level08_fresnel_total")
        self.assertTrue(math.isfinite(float(summary["R_total"])))
        self.assertTrue(math.isfinite(float(summary["T_total"])))
        self.assertTrue(math.isfinite(float(summary["fresnel_R_error"])))


if __name__ == "__main__":
    unittest.main()
