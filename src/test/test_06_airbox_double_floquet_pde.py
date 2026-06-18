from __future__ import annotations

import math
import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, floquet_smoke_config, run_small_3d_case


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D Floquet PDE tests.")
class TestAirboxDoubleFloquetPDE(unittest.TestCase):
    def test_normal_and_oblique_double_floquet_smoke(self):
        for case in ("normal", "oblique"):
            with self.subTest(case=case):
                summary = run_small_3d_case(floquet_smoke_config(case=case), f"level06_{case}")
                self.assertTrue(math.isfinite(float(summary["relative_max_abs_E_error"])))
                self.assertTrue(summary["use_floquet_xy"])


if __name__ == "__main__":
    unittest.main()
