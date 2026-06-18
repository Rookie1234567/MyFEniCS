from __future__ import annotations

import math
import unittest

from src.test.stage2_test_utils import RUN_PDE_TESTS, pml_smoke_config, run_small_3d_case


@unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D PML PDE tests.")
class TestPMLAirboxDecay(unittest.TestCase):
    def test_pml_airbox_reports_decay_and_fit_metrics(self):
        summary = run_small_3d_case(pml_smoke_config(), "level07_pml")
        self.assertTrue(math.isfinite(float(summary["pml_reflection_proxy"])))
        self.assertTrue(math.isfinite(float(summary["pml_reference_relative_error"])))
        self.assertLess(float(summary["pml_decay_ratio_bottom"]), 1.0)


if __name__ == "__main__":
    unittest.main()
