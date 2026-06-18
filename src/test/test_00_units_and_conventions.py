from __future__ import annotations

import math
import unittest

import numpy as np

from src.common.analytic_fields_3d import electric_field_code_values
from src.common.config_3d import SimulationConfig3D, normal_incidence_airbox_config


class TestUnitsAndConventions(unittest.TestCase):
    def test_k0_uses_nm_wavelength(self):
        cfg = SimulationConfig3D(lambda0=20.0)
        self.assertAlmostEqual(cfg.k0, 2.0 * math.pi / 20.0, places=14)
        data = cfg.as_jsonable()
        self.assertEqual(data["length_unit"], "nm")
        self.assertEqual(data["electric_field_unit"], "V/m")
        self.assertEqual(data["magnetic_field_unit"], "A/m")

    def test_phase_advances_along_propagation_direction(self):
        cfg = normal_incidence_airbox_config(lambda0=20.0)
        base = np.asarray([[1.0, 2.0, 3.0]], dtype=np.float64)
        distance_nm = 2.5
        shifted = base + distance_nm * cfg.direction_vector[None, :]
        e_base = electric_field_code_values(cfg, base)[0, 0]
        e_shifted = electric_field_code_values(cfg, shifted)[0, 0]
        expected_ratio = np.exp(1j * cfg.k0 * complex(cfg.n_air) * distance_nm)
        self.assertLess(abs(e_shifted / e_base - expected_ratio), 1.0e-13)


if __name__ == "__main__":
    unittest.main()
