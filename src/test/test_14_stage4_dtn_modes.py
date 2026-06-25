from __future__ import annotations

import unittest

import numpy as np

from src.common.modes_3d import (
    incident_power_3d,
    outgoing_port_modes_3d,
)
from src.test.stage2_test_utils import stage4_block_config


def _dtn_cfg(**updates):
    values = {
        "stage_case": "stage4_block_grating",
        "stage4_boundary_model": "dtn_port",
        "stage4_dtn_order_policy": "auto_propagating",
        "stage4_dtn_assembly": "auxiliary",
        "use_pml": False,
        "pml_top_thickness": 0.0,
        "pml_bottom_thickness": 0.0,
        "diffraction_zero_order_only": True,
    }
    values.update(updates)
    return stage4_block_config(**values)


class Stage4DtnModeTests(unittest.TestCase):
    def test_auto_dtn_orders_ignore_probe_zero_order_flag(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating", diffraction_zero_order_only=True)
        modes = outgoing_port_modes_3d(cfg)
        propagating_orders = {(mode.m, mode.n) for mode in modes if mode.propagating}
        self.assertIn((0, 0), propagating_orders)
        self.assertTrue(any(order != (0, 0) for order in propagating_orders))
        self.assertGreater(len(modes), 4)

    def test_zero_order_policy_keeps_only_zero_order_ports(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order", diffraction_zero_order_only=False)
        modes = outgoing_port_modes_3d(cfg)
        self.assertEqual({(mode.side, mode.m, mode.n) for mode in modes}, {("top", 0, 0), ("bottom", 0, 0)})
        self.assertEqual(len(modes), 4)

    def test_port_polarizations_are_transverse_and_power_positive(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating")
        for mode in outgoing_port_modes_3d(cfg):
            if not mode.propagating:
                continue
            self.assertLess(abs(np.dot(mode.k_vector, mode.e_vector)), 1.0e-10)
            self.assertGreater(mode.electric_tangential_norm_sq, 0.0)
            self.assertGreater(mode.power_per_unit_amplitude, 0.0)
            self.assertEqual(mode.vertical_sign, 1 if mode.side == "top" else -1)

    def test_zero_order_top_basis_projects_unit_incident_polarization(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        top_zero_modes = [
            mode for mode in outgoing_port_modes_3d(cfg) if mode.side == "top" and mode.m == 0 and mode.n == 0
        ]
        incident_e = np.asarray(cfg.polarization_vector, dtype=np.complex128)
        projections = [
            abs(np.vdot(mode.e_vector[:2], incident_e[:2])) ** 2 / mode.electric_tangential_norm_sq
            for mode in top_zero_modes
        ]
        self.assertAlmostEqual(float(sum(projections)), abs(complex(cfg.incident_amplitude)) ** 2, places=12)
        self.assertGreater(incident_power_3d(cfg), 0.0)


if __name__ == "__main__":
    unittest.main()
