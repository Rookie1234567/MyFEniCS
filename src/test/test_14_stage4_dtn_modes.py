from __future__ import annotations

import unittest

import numpy as np

from src.common.modes_3d import (
    incident_power_3d,
    outgoing_port_modes_3d,
)
from src.solvers.dtn_port_3d import (
    DTN_PORT_MODAL_POWER_SOURCE,
    _incident_projection_onto_top_mode,
    _mode_boundary_phase,
    _mode_power_at_boundary,
    _mode_projection_denominator,
    _port_power_metrics,
    _traction_vector,
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

    def test_lossy_bottom_port_power_is_evaluated_at_boundary_plane(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        bottom_y = [
            mode
            for mode in outgoing_port_modes_3d(cfg)
            if mode.side == "bottom" and mode.m == 0 and mode.n == 0 and mode.polarization == "y"
        ][0]
        phase = _mode_boundary_phase(bottom_y, cfg)
        self.assertLess(abs(phase), 1.0)
        self.assertAlmostEqual(
            _mode_power_at_boundary(bottom_y, cfg, 1.0 + 0.0j),
            bottom_y.power_per_unit_amplitude * abs(phase) ** 2,
            places=10,
        )
        area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
        self.assertAlmostEqual(
            _mode_projection_denominator(bottom_y, cfg),
            area * bottom_y.electric_tangential_norm_sq * abs(phase) ** 2,
            places=10,
        )

    def test_auxiliary_traction_uses_curl_cross_outward_normal_sign(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        y_modes = [
            mode
            for mode in outgoing_port_modes_3d(cfg)
            if mode.m == 0 and mode.n == 0 and mode.polarization == "y"
        ]
        self.assertEqual({mode.side for mode in y_modes}, {"top", "bottom"})
        for mode in y_modes:
            traction = _traction_vector(mode, cfg)
            self.assertAlmostEqual(traction[1].real, (-mode.beta.imag), places=12)
            self.assertAlmostEqual(traction[1].imag, mode.beta.real, places=12)

    def test_port_power_metrics_expose_dtn_modal_official_aliases(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        modes = outgoing_port_modes_3d(cfg)
        incident_projections = [
            _incident_projection_onto_top_mode(mode, cfg) if mode.side == "top" else 0.0 + 0.0j
            for mode in modes
        ]
        aux_values = np.asarray(incident_projections, dtype=np.complex128)
        metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
        self.assertEqual(metrics["power_source"], DTN_PORT_MODAL_POWER_SOURCE)
        self.assertEqual(metrics["diffraction_total_power_source"], DTN_PORT_MODAL_POWER_SOURCE)
        self.assertEqual(metrics["R_total"], metrics["R_total_dtn_port_modal"])
        self.assertEqual(metrics["T_total"], metrics["T_total_dtn_port_modal"])
        self.assertEqual(metrics["R_plus_T"], metrics["R_plus_T_dtn_port_modal"])
        self.assertIn("top outgoing amplitude", metrics["dtn_port_modal_amplitude_convention"])


if __name__ == "__main__":
    unittest.main()
