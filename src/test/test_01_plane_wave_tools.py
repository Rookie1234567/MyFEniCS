from __future__ import annotations

import unittest

import numpy as np

from src.common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values
from src.common.config_3d import oblique_incidence_airbox_config


class TestPlaneWaveTools(unittest.TestCase):
    def test_direction_and_te_tm_basis_are_orthonormal(self):
        cfg = oblique_incidence_airbox_config()
        s_hat = cfg.direction_vector
        e_s = cfg.s_polarization_vector
        e_p = cfg.p_polarization_vector
        self.assertAlmostEqual(float(np.linalg.norm(s_hat)), 1.0, places=14)
        self.assertLess(abs(np.dot(e_s, s_hat)), 1.0e-14)
        self.assertLess(abs(np.dot(e_p, s_hat)), 1.0e-14)
        self.assertLess(abs(np.dot(e_s, e_p)), 1.0e-14)
        self.assertAlmostEqual(float(np.linalg.norm(e_s)), 1.0, places=14)
        self.assertAlmostEqual(float(np.linalg.norm(e_p)), 1.0, places=14)

    def test_plane_wave_is_transverse_for_te_and_tm(self):
        for kind in ("s", "p"):
            cfg = oblique_incidence_airbox_config(polarization_kind=kind, custom_polarization=None)
            self.assertLess(abs(np.dot(cfg.wavevector, cfg.polarization_vector)), 1.0e-12)

    def test_h_field_and_poynting_follow_propagation_direction(self):
        cfg = oblique_incidence_airbox_config(polarization_kind="s", custom_polarization=None)
        point = np.asarray([[113.0, 77.0, -25.0]], dtype=np.float64)
        E = electric_field_code_values(cfg, point)[0]
        H = magnetic_field_code_values(cfg, point)[0]
        poynting = 0.5 * np.real(np.cross(E, np.conj(H)))
        cosine = float(np.dot(poynting, cfg.direction_vector) / np.linalg.norm(poynting))
        self.assertGreater(cosine, 1.0 - 1.0e-12)
        self.assertLess(abs(np.dot(H, cfg.wavevector)), 1.0e-12)
        self.assertLess(abs(np.dot(E, H)), 1.0e-12)


if __name__ == "__main__":
    unittest.main()
