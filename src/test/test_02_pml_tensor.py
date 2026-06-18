from __future__ import annotations

import unittest

import numpy as np

from src.common.analytic_fields_3d import pml_complex_z
from src.common.config_3d import normal_incidence_airbox_config
from src.common.pml_3d import z_pml_diagonal_values, z_stretch_derivative_value


class TestPMLTensor(unittest.TestCase):
    def setUp(self):
        self.cfg = normal_incidence_airbox_config(
            use_pml=True,
            pml_top_thickness=250.0,
            pml_bottom_thickness=250.0,
            pml_alpha=5.0,
        )

    def test_physical_region_complex_coordinate_is_unchanged(self):
        z = np.asarray([self.cfg.physical_z_min, 0.0, self.cfg.physical_z_max])
        zeta = pml_complex_z(self.cfg, z)
        self.assertLess(float(np.max(np.abs(zeta - z))), 1.0e-14)

    def test_top_and_bottom_outgoing_waves_decay(self):
        top_inner = self.cfg.physical_z_max + 0.05 * self.cfg.pml_top_thickness
        top_outer = self.cfg.domain_z_max - 0.05 * self.cfg.pml_top_thickness
        bottom_inner = self.cfg.physical_z_min - 0.05 * self.cfg.pml_bottom_thickness
        bottom_outer = self.cfg.domain_z_min + 0.05 * self.cfg.pml_bottom_thickness
        q = self.cfg.k0

        top_amp_inner = abs(np.exp(1j * q * pml_complex_z(self.cfg, np.asarray([top_inner]))[0]))
        top_amp_outer = abs(np.exp(1j * q * pml_complex_z(self.cfg, np.asarray([top_outer]))[0]))
        bottom_amp_inner = abs(np.exp(-1j * q * pml_complex_z(self.cfg, np.asarray([bottom_inner]))[0]))
        bottom_amp_outer = abs(np.exp(-1j * q * pml_complex_z(self.cfg, np.asarray([bottom_outer]))[0]))

        self.assertLess(top_amp_outer, top_amp_inner)
        self.assertLess(bottom_amp_outer, bottom_amp_inner)

    def test_pml_tensor_diagonal_structure(self):
        z = self.cfg.physical_z_max + 0.5 * self.cfg.pml_top_thickness
        eps = 2.25 + 0.0j
        s_z = z_stretch_derivative_value(z, self.cfg, "top")
        eps_diag, mu_inv_diag = z_pml_diagonal_values(z, self.cfg, "top", eps)
        self.assertLess(abs(eps_diag[0] - eps * s_z), 1.0e-14)
        self.assertLess(abs(eps_diag[1] - eps * s_z), 1.0e-14)
        self.assertLess(abs(eps_diag[2] - eps / s_z), 1.0e-14)
        self.assertLess(abs(mu_inv_diag[0] - 1.0 / s_z), 1.0e-14)
        self.assertLess(abs(mu_inv_diag[1] - 1.0 / s_z), 1.0e-14)
        self.assertLess(abs(mu_inv_diag[2] - s_z), 1.0e-14)


if __name__ == "__main__":
    unittest.main()
