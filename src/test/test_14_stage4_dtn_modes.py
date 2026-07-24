from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from mpi4py import MPI
import numpy as np

from src.common.config_3d import (
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    target_stage4_config,
)
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
    _write_port_outputs,
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


def _grazing_fixture_b_cfg(**updates):
    values = {
        "stage_case": "stage4_flat_layer_sanity",
        "stage4_dtn_order_policy": "zero_order",
        "period_x": 10.0,
        "period_y": 10.0,
        "air_height": 5.0,
        "substrate_thickness": 5.0,
        "z_min": -5.0,
        "z_max": 5.0,
        "grating_width_x": 0.0,
        "grating_width_y": 0.0,
        "grating_height": 0.0,
        "incident_theta_deg": 89.0,
    }
    values.update(updates)
    return _dtn_cfg(**values)


class Stage4DtnModeTests(unittest.TestCase):
    def _single_bottom_s_power(self, cfg):
        modes = outgoing_port_modes_3d(cfg)
        bottom_index = next(
            idx
            for idx, mode in enumerate(modes)
            if mode.side == "bottom" and mode.m == 0 and mode.n == 0 and mode.polarization == "s"
        )
        incident_projections = [
            _incident_projection_onto_top_mode(mode, cfg) if mode.side == "top" else 0.0 + 0.0j
            for mode in modes
        ]
        aux_values = np.asarray(incident_projections, dtype=np.complex128)
        aux_values[bottom_index] = 1.0 + 0.0j
        metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
        return modes, bottom_index, incident_projections, aux_values, metrics

    def test_auto_dtn_orders_ignore_probe_zero_order_flag(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating", diffraction_zero_order_only=True)
        modes = outgoing_port_modes_3d(cfg)
        propagating_orders = {(mode.m, mode.n) for mode in modes if mode.propagating}
        self.assertIn((0, 0), propagating_orders)
        self.assertTrue(any(order != (0, 0) for order in propagating_orders))
        self.assertGreater(len(modes), 4)

    def test_opt_in_evanescent_buffer_expands_operator_without_changing_default(self):
        default_cfg = target_stage4_config(degree=6, h_nm=15.0)
        buffered_cfg = target_stage4_config(degree=6, h_nm=15.0)
        buffered_cfg.stage4_dtn_evanescent_buffer = 1
        default_modes = outgoing_port_modes_3d(default_cfg)
        buffered_modes = outgoing_port_modes_3d(buffered_cfg)
        self.assertTrue(all(mode.propagating for mode in default_modes))
        self.assertGreater(len(buffered_modes), len(default_modes))
        self.assertTrue(any(not mode.propagating for mode in buffered_modes))
        default_ids = {
            (mode.side, mode.m, mode.n, mode.polarization)
            for mode in default_modes
        }
        buffered_ids = {
            (mode.side, mode.m, mode.n, mode.polarization)
            for mode in buffered_modes
        }
        self.assertLess(default_ids, buffered_ids)
        extra_modes = [
            mode
            for mode in buffered_modes
            if (
                mode.side,
                mode.m,
                mode.n,
                mode.polarization,
            )
            not in default_ids
        ]
        self.assertEqual(len(default_modes), 80)
        self.assertEqual(len(extra_modes), 260)
        self.assertTrue(
            all(not mode.propagating for mode in extra_modes)
        )
        self.assertEqual(
            sum(
                mode.side == "top"
                and mode.power_per_unit_amplitude > 0.0
                for mode in extra_modes
            ),
            0,
        )
        self.assertEqual(
            sum(
                mode.side == "bottom"
                and mode.power_per_unit_amplitude > 0.0
                for mode in extra_modes
            ),
            130,
        )
        ordered_ids = [
            (mode.side, mode.m, mode.n, mode.polarization)
            for mode in buffered_modes
        ]
        digest = hashlib.sha256(
            json.dumps(
                ordered_ids,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            digest,
            "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629",
        )
        self.assertTrue(
            math.isclose(
            min(
                abs(_mode_boundary_phase(mode, buffered_cfg))
                for mode in buffered_modes
            ),
            4.698738560873268e-84,
                rel_tol=1.0e-12,
                abs_tol=0.0,
            )
        )
        self.assertTrue(
            math.isclose(
            min(
                _mode_projection_denominator(mode, buffered_cfg)
                for mode in buffered_modes
            ),
            1.314525165643265e-164,
                rel_tol=1.0e-12,
                abs_tol=0.0,
            )
        )

    def test_task034_target_default_mode_identity_is_frozen(self):
        cfg = target_stage4_config(degree=6, h_nm=15.0)
        modes = outgoing_port_modes_3d(cfg)
        ordered_ids = [
            (mode.side, mode.m, mode.n, mode.polarization)
            for mode in modes
        ]
        digest = hashlib.sha256(
            json.dumps(
                ordered_ids,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(len(ordered_ids), 80)
        self.assertEqual(
            digest,
            "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21",
        )
        self.assertEqual(cfg.stage4_dtn_evanescent_buffer, 0)
        self.assertIsNone(cfg.stage4_dtn_quadrature_degree)
        self.assertFalse(cfg.stage4_retain_dual_recovery_context)

    def test_evanescent_buffer_rejects_incompatible_policy(self):
        cfg = _dtn_cfg(
            stage4_dtn_order_policy="zero_order",
            stage4_dtn_evanescent_buffer=1,
        )
        with self.assertRaisesRegex(ValueError, "qualified only"):
            outgoing_port_modes_3d(cfg)

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

    def test_lossy_below_critical_mode_counts_finite_port_transmission(self):
        cfg = _grazing_fixture_b_cfg()
        modes, bottom_index, incident_projections, aux_values, metrics = self._single_bottom_s_power(cfg)
        mode = modes[bottom_index]
        expected = _mode_power_at_boundary(mode, cfg, 1.0 + 0.0j) / incident_power_3d(cfg)

        self.assertFalse(mode.propagating)
        self.assertGreater(mode.power_per_unit_amplitude, 0.0)
        self.assertGreater(expected, 0.0)
        self.assertAlmostEqual(metrics["T_total"], expected, places=12)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, metrics, MPI.COMM_SELF)
            payload = json.loads((out_dir / "dtn_port_diffraction_orders_3d.json").read_text(encoding="utf-8"))
        row = payload["orders"][bottom_index]
        self.assertFalse(row["propagating"])
        self.assertTrue(row["power_carrying"])
        self.assertAlmostEqual(row["T"], expected, places=12)

    def test_lossless_evanescent_mode_carries_zero_finite_port_transmission(self):
        lossless_index = complex(SI_SUBSTRATE_INDEX_EUV_13P5_NM.real, 0.0)
        cfg = _grazing_fixture_b_cfg(n_substrate=lossless_index)
        modes, bottom_index, incident_projections, aux_values, metrics = self._single_bottom_s_power(cfg)
        mode = modes[bottom_index]

        self.assertFalse(mode.propagating)
        self.assertEqual(mode.power_per_unit_amplitude, 0.0)
        self.assertEqual(metrics["T_total"], 0.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, metrics, MPI.COMM_SELF)
            payload = json.loads((out_dir / "dtn_port_diffraction_orders_3d.json").read_text(encoding="utf-8"))
        row = payload["orders"][bottom_index]
        self.assertFalse(row["propagating"])
        self.assertFalse(row["power_carrying"])
        self.assertEqual(row["T"], 0.0)


if __name__ == "__main__":
    unittest.main()
