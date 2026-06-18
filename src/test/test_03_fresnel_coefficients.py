from __future__ import annotations

import unittest

import numpy as np

from src.common.analytic_fields_3d import fresnel_reference
from src.common.config_3d import oblique_incidence_airbox_config


class TestFresnelCoefficients(unittest.TestCase):
    def test_beta_identity_for_air_and_substrate(self):
        cfg = oblique_incidence_airbox_config(
            geometry_kind="fresnel_interface",
            n_substrate=1.45 + 0.0j,
            polarization_kind="s",
            custom_polarization=None,
        )
        k_parallel2 = cfg.kx**2 + cfg.ky**2
        for n_medium in (cfg.n_air, cfg.substrate_index):
            beta = np.sqrt((cfg.k0 * n_medium) ** 2 - k_parallel2)
            if beta.imag < 0.0:
                beta = -beta
            self.assertLess(abs(beta**2 + k_parallel2 - (cfg.k0 * n_medium) ** 2), 1.0e-14)

    def test_n_substrate_one_removes_interface_for_te_and_tm(self):
        for kind in ("s", "p"):
            cfg = oblique_incidence_airbox_config(
                geometry_kind="fresnel_interface",
                n_substrate=1.0 + 0.0j,
                polarization_kind=kind,
                custom_polarization=None,
            )
            ref = fresnel_reference(cfg)
            self.assertLess(abs(ref["r"]), 1.0e-14)
            self.assertLess(abs(ref["t"] - 1.0), 1.0e-14)
            self.assertLess(abs(ref["R"]), 1.0e-14)
            self.assertLess(abs(ref["T"] - 1.0), 1.0e-14)

    def test_lossless_fresnel_conserves_power(self):
        for kind in ("s", "p"):
            cfg = oblique_incidence_airbox_config(
                geometry_kind="fresnel_interface",
                n_substrate=1.45 + 0.0j,
                polarization_kind=kind,
                custom_polarization=None,
            )
            ref = fresnel_reference(cfg)
            self.assertLess(abs(ref["R_plus_T"] - 1.0), 1.0e-13)


if __name__ == "__main__":
    unittest.main()
