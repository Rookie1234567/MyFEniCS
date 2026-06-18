from __future__ import annotations

import unittest

import numpy as np

from src.common.analytic_fields_3d import electric_field_code_values
from src.test.stage2_test_utils import RUN_PDE_TESTS, floquet_smoke_config, run_small_3d_case


class TestFloquetConstraints(unittest.TestCase):
    def test_exact_field_has_x_y_and_corner_floquet_phases(self):
        cfg = floquet_smoke_config(case="oblique")
        point = np.asarray([[0.0, 0.0, -100.0]], dtype=np.float64)
        x_shift = point + np.asarray([[cfg.x_max - cfg.x_min, 0.0, 0.0]])
        y_shift = point + np.asarray([[0.0, cfg.y_max - cfg.y_min, 0.0]])
        xy_shift = point + np.asarray([[cfg.x_max - cfg.x_min, cfg.y_max - cfg.y_min, 0.0]])
        e0 = electric_field_code_values(cfg, point)[0]
        self.assertLess(np.linalg.norm(electric_field_code_values(cfg, x_shift)[0] - cfg.floquet_phase_x * e0), 1.0e-12)
        self.assertLess(np.linalg.norm(electric_field_code_values(cfg, y_shift)[0] - cfg.floquet_phase_y * e0), 1.0e-12)
        self.assertLess(
            np.linalg.norm(electric_field_code_values(cfg, xy_shift)[0] - cfg.floquet_phase_x * cfg.floquet_phase_y * e0),
            1.0e-12,
        )

    @unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run 3D Floquet PDE tests.")
    def test_floquet_pde_reports_machine_precision_pairing(self):
        summary = run_small_3d_case(floquet_smoke_config(), "level05_floquet")
        self.assertLess(float(summary["floquet_x_face_mismatch"]), 1.0e-9)
        self.assertLess(float(summary["floquet_y_face_mismatch"]), 1.0e-9)
        self.assertLess(float(summary["floquet_edge_corner_mismatch"]), 1.0e-12)


if __name__ == "__main__":
    unittest.main()
