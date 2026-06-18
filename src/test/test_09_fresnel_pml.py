from __future__ import annotations

import math
import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, fresnel_smoke_config, run_small_3d_case


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D Fresnel+PML PDE tests.")
class TestFresnelPML(unittest.TestCase):
    def test_fresnel_with_floquet_and_pml_smoke(self):
        summary = run_small_3d_case(fresnel_smoke_config(), "level09_fresnel_pml")
        self.assertTrue(summary["use_floquet_xy"])
        self.assertTrue(summary["use_pml"])
        self.assertTrue(math.isfinite(float(summary["R_total"])))
        self.assertTrue(math.isfinite(float(summary["T_total"])))


if __name__ == "__main__":
    unittest.main()
