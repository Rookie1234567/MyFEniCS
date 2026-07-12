from __future__ import annotations

import unittest

import numpy as np

from src.common.config import SimulationConfig
from src.postprocessing.power_metrics import (
    _is_propagating,
    _modal_admittance,
    _modal_power_on_plane,
    _modal_power_factor,
    _positive_sqrt,
)
from src.solvers.solve_port_maxwell import _select_dtn_port_modes


class LossyPortModeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = SimulationConfig(
            period_x=100.0,
            lambda0=13.5,
            incident_angle_deg=0.0,
            n_air=1.0,
            n_substrate=0.999002304859 + 0.00182649365j,
            port_use_diffraction_orders=True,
        )

    def test_lossy_zero_order_carries_transmitted_power(self):
        k_sub = self.cfg.k0 * self.cfg.n_substrate
        beta = _positive_sqrt(k_sub**2)
        self.assertGreater(beta.imag, 0.0)
        self.assertTrue(_is_propagating(beta, k_sub**2))
        power_factor = _modal_power_factor(_modal_admittance(k_sub, beta))
        self.assertGreater(
            _modal_power_on_plane(
                self.cfg.period_x, power_factor, 1.0, power_carrying=True
            ),
            0.0,
        )

    def test_below_cutoff_lossy_order_is_not_mislabeled(self):
        k_sub = self.cfg.k0 * self.cfg.n_substrate
        alpha = 2.0 * 3.141592653589793 * 8 / self.cfg.period_x
        dispersion = k_sub**2 - alpha**2
        beta = _positive_sqrt(dispersion)
        self.assertLess(dispersion.real, 0.0)
        self.assertFalse(_is_propagating(beta, dispersion))
        power_factor = _modal_power_factor(_modal_admittance(k_sub, beta))
        self.assertEqual(
            _modal_power_on_plane(
                self.cfg.period_x, power_factor, 1.0, power_carrying=False
            ),
            0.0,
        )

    def test_auto_dtn_selection_keeps_lossy_power_carrying_orders(self):
        selection = _select_dtn_port_modes(self.cfg, lambda _message: None)
        bottom = selection["orders_by_side"]["bottom"]
        self.assertIn(0, bottom)
        self.assertIn(-7, bottom)
        self.assertIn(7, bottom)
        self.assertNotIn(-8, bottom)
        self.assertNotIn(8, bottom)

    def test_power_uses_attenuated_coefficient_on_the_actual_plane(self):
        beta = 0.46 + 0.01j
        distance = 50.0
        boundary_coefficient = complex(np.exp(1j * beta * distance))
        at_reference = _modal_power_on_plane(100.0, 0.5, 1.0, True)
        at_bottom_port = _modal_power_on_plane(100.0, 0.5, boundary_coefficient, True)
        self.assertLess(at_bottom_port, at_reference)
        self.assertEqual(
            _modal_power_on_plane(100.0, 0.5, boundary_coefficient, False), 0.0
        )


if __name__ == "__main__":
    unittest.main()
