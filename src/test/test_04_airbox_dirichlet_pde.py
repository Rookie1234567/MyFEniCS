from __future__ import annotations

import math
import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, run_small_3d_case, stage1_smoke_config


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D PDE smoke tests.")
class TestAirboxDirichletPDE(unittest.TestCase):
    def test_stage1_airbox_dirichlet_smoke(self):
        summary = run_small_3d_case(stage1_smoke_config(), "level04_stage1")
        self.assertTrue(math.isfinite(float(summary["relative_max_abs_E_error"])))
        self.assertGreater(summary["num_nedelec_dofs"], 0)
        self.assertEqual(summary["stage_case"], "stage1_airbox")


if __name__ == "__main__":
    unittest.main()
