from __future__ import annotations

import unittest

import numpy as np

from src.postprocessing.diffraction_3d import (
    E_FOURIER_DIAGNOSTIC_NOTE,
    OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE,
    OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE,
    SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE,
    _eh_fourier_order_powers,
    _e_fourier_order_powers,
    _incident_power,
    enumerate_diffraction_orders_3d,
    fit_diffraction_amplitudes_from_samples,
    mode_eh_vectors,
    polarization_basis_3d,
    _sampled_flux_code_units,
    _probe_z_locations,
)
from src.postprocessing.flat_layer_reference_3d import (
    analytic_volume_absorption_between_z,
    compute_flat_layer_reference_3d,
)
from src.common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values, fresnel_reference
from src.test.stage2_test_utils import stage4_block_config


def _sample_plane(cfg, z: float, nx: int = 6, ny: int = 5) -> np.ndarray:
    xs = cfg.x_min + (np.arange(nx, dtype=np.float64) + 0.5) * (cfg.x_max - cfg.x_min) / nx
    ys = cfg.y_min + (np.arange(ny, dtype=np.float64) + 0.5) * (cfg.y_max - cfg.y_min) / ny
    return np.asarray([[x, y, z] for y in ys for x in xs], dtype=np.float64)


def _mode_samples(points, kvec, e_vec, h_vec, amplitude: complex) -> tuple[np.ndarray, np.ndarray]:
    phase = np.exp(1j * (kvec[0] * points[:, 0] + kvec[1] * points[:, 1] + kvec[2] * points[:, 2]))
    return amplitude * phase[:, None] * e_vec[None, :], amplitude * phase[:, None] * h_vec[None, :]


class Stage4DiffractionModeTests(unittest.TestCase):
    def test_stage4_probe_power_source_is_diagnostic_eh_fourier(self):
        self.assertEqual(OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE, "diagnostic_eh_fourier_probe")
        self.assertIn("Diagnostic only", OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE)
        self.assertIn("DtN port modal amplitudes", OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE)
        self.assertIn("Diagnostic only", E_FOURIER_DIAGNOSTIC_NOTE)
        self.assertIn("DtN port modal amplitudes", SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE)
        self.assertNotIn("Official Stage-4 R/T uses E-Fourier", SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE)

    def test_zero_order_only_catalog(self):
        cfg = stage4_block_config(diffraction_zero_order_only=True)
        orders = enumerate_diffraction_orders_3d(cfg)
        self.assertEqual([(order.m, order.n) for order in orders], [(0, 0)])
        self.assertTrue(orders[0].top_propagating)
        self.assertTrue(orders[0].bottom_propagating)
        self.assertNotAlmostEqual(orders[0].beta_bottom.imag, 0.0, places=12)

    def test_auto_catalog_finds_higher_orders_for_large_period(self):
        cfg = stage4_block_config(
            diffraction_zero_order_only=False,
        )
        orders = enumerate_diffraction_orders_3d(cfg)
        propagating = [(order.m, order.n) for order in orders if order.top_propagating or order.bottom_propagating]
        self.assertIn((0, 0), propagating)
        self.assertTrue(any((m, n) != (0, 0) for m, n in propagating))

    def test_polarization_basis_is_transverse(self):
        cfg = stage4_block_config(diffraction_zero_order_only=False)
        alpha = cfg.kx + 2.0 * np.pi / cfg.period_x
        gamma = cfg.ky + 2.0 * np.pi / cfg.period_y
        beta = np.sqrt((cfg.k0 * cfg.n_air) ** 2 - alpha**2 - gamma**2 + 0.0j)
        for _, pol in polarization_basis_3d(alpha, gamma, beta, cfg.n_air, 1, cfg):
            kvec = np.asarray((alpha, gamma, beta), dtype=np.complex128)
            self.assertLess(abs(np.dot(kvec, pol)), 1.0e-12)

    def test_analytic_sample_fit_recovers_zero_order_amplitudes(self):
        cfg = stage4_block_config(diffraction_zero_order_only=True)
        order = enumerate_diffraction_orders_3d(cfg)[0]
        points = _sample_plane(cfg, z=250.0)
        top_basis = dict(polarization_basis_3d(order.alpha, order.gamma, order.beta_top, cfg.n_air, -1, cfg))
        pol = top_basis["x"]
        k_down, e_down, h_down = mode_eh_vectors(order.alpha, order.gamma, order.beta_top, pol, -1, cfg)
        k_up, e_up, h_up = mode_eh_vectors(order.alpha, order.gamma, order.beta_top, pol, 1, cfg)
        e_inc, h_inc = _mode_samples(points, k_down, e_down, h_down, 1.0 + 0.0j)
        e_ref, h_ref = _mode_samples(points, k_up, e_up, h_up, 0.25 - 0.1j)
        amplitudes, residual = fit_diffraction_amplitudes_from_samples(
            cfg,
            [order],
            points,
            e_inc + e_ref,
            h_inc + h_ref,
            side="top",
        )
        self.assertLess(residual, 1.0e-12)
        self.assertAlmostEqual(amplitudes[(0, 0, "x", "down")].real, 1.0, places=10)
        self.assertAlmostEqual(amplitudes[(0, 0, "x", "up")].real, 0.25, places=10)
        self.assertAlmostEqual(amplitudes[(0, 0, "x", "up")].imag, -0.1, places=10)
        self.assertLess(abs(amplitudes[(0, 0, "y", "down")]), 1.0e-12)

    def test_default_probe_planes_place_top_above_block(self):
        cfg = stage4_block_config(
            diffraction_zero_order_only=False,
            z_min=-50.0,
            z_max=100.0,
            interface_z=0.0,
            grating_height=50.0,
            diffraction_probe_fraction=0.75,
        )
        top_z, bottom_z = _probe_z_locations(cfg)
        expected_top = cfg.grating_z_max + 0.75 * (cfg.physical_z_max - cfg.grating_z_max)
        self.assertAlmostEqual(top_z, expected_top, places=12)
        self.assertAlmostEqual(bottom_z, 0.75 * cfg.physical_z_min, places=12)
        self.assertGreater(top_z, cfg.grating_z_max)
        self.assertLess(bottom_z, cfg.interface_z)

    def test_reduced_height_probe_planes_fit_between_block_and_boundary(self):
        cfg = stage4_block_config(
            diffraction_zero_order_only=False,
            z_min=-10.0,
            z_max=60.0,
            interface_z=0.0,
            grating_height=50.0,
            diffraction_probe_fraction=0.75,
        )
        top_z, bottom_z = _probe_z_locations(cfg)
        self.assertAlmostEqual(top_z, 57.5, places=12)
        self.assertAlmostEqual(bottom_z, -7.5, places=12)
        self.assertGreater(top_z, cfg.grating_z_max)
        self.assertLess(top_z, cfg.physical_z_max)

    def test_flat_layer_fresnel_field_e_fourier_power_sanity(self):
        cfg = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_substrate=1.45 + 0.0j,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=False,
            diffraction_order_max_m=2,
            diffraction_order_max_n=2,
            diffraction_sample_count_x=32,
            diffraction_sample_count_y=32,
        )
        orders = enumerate_diffraction_orders_3d(cfg)
        top_z, bottom_z = _probe_z_locations(cfg)
        top_points = _sample_plane(
            cfg,
            z=top_z,
            nx=cfg.diffraction_sample_count_x,
            ny=cfg.diffraction_sample_count_y,
        )
        bottom_points = _sample_plane(
            cfg,
            z=bottom_z,
            nx=cfg.diffraction_sample_count_x,
            ny=cfg.diffraction_sample_count_y,
        )
        _, metrics = _e_fourier_order_powers(
            cfg,
            orders,
            top_points,
            electric_field_code_values(cfg, top_points),
            bottom_points,
            electric_field_code_values(cfg, bottom_points),
            _incident_power(cfg),
        )
        ref = fresnel_reference(cfg)
        self.assertAlmostEqual(metrics["R_total_from_e_fourier"], ref["R"], places=11)
        self.assertAlmostEqual(metrics["T_total_from_e_fourier"], ref["T"], places=11)
        self.assertAlmostEqual(metrics["R_plus_T_from_e_fourier"], ref["R_plus_T"], places=11)

        _, eh_metrics = _eh_fourier_order_powers(
            cfg,
            orders,
            top_points,
            electric_field_code_values(cfg, top_points),
            magnetic_field_code_values(cfg, top_points),
            bottom_points,
            electric_field_code_values(cfg, bottom_points),
            magnetic_field_code_values(cfg, bottom_points),
            _incident_power(cfg),
        )
        self.assertAlmostEqual(eh_metrics["R_total_from_eh_fourier"], ref["R"], places=11)
        self.assertAlmostEqual(eh_metrics["T_total_from_eh_fourier"], ref["T"], places=11)
        self.assertAlmostEqual(eh_metrics["R_plus_T_from_eh_fourier"], ref["R_plus_T"], places=11)

    def test_lossy_flat_layer_keeps_transmitted_zero_order(self):
        cfg = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=True,
            diffraction_sample_count_x=16,
            diffraction_sample_count_y=16,
        )
        order = enumerate_diffraction_orders_3d(cfg)[0]
        self.assertTrue(order.bottom_propagating)
        top_z, bottom_z = _probe_z_locations(cfg)
        top_points = _sample_plane(
            cfg,
            z=top_z,
            nx=cfg.diffraction_sample_count_x,
            ny=cfg.diffraction_sample_count_y,
        )
        bottom_points = _sample_plane(
            cfg,
            z=bottom_z,
            nx=cfg.diffraction_sample_count_x,
            ny=cfg.diffraction_sample_count_y,
        )
        _, eh_metrics = _eh_fourier_order_powers(
            cfg,
            [order],
            top_points,
            electric_field_code_values(cfg, top_points),
            magnetic_field_code_values(cfg, top_points),
            bottom_points,
            electric_field_code_values(cfg, bottom_points),
            magnetic_field_code_values(cfg, bottom_points),
            _incident_power(cfg),
        )
        self.assertGreater(eh_metrics["T_total_from_eh_fourier"], 0.0)

    def test_lossy_flat_layer_reference_includes_probe_plane_attenuation(self):
        cfg = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=True,
            diffraction_sample_count_x=16,
            diffraction_sample_count_y=16,
        )
        reference = compute_flat_layer_reference_3d(cfg)
        fresnel = fresnel_reference(cfg)
        self.assertAlmostEqual(reference["R_ref"], fresnel["R"], places=12)
        self.assertLess(reference["T_ref_at_bottom_reference_plane"], fresnel["T"])
        self.assertGreater(reference["A_ref_between_reference_planes"], 0.0)
        self.assertGreater(
            reference["A_ref_between_port_planes"],
            reference["A_ref_between_reference_planes"],
        )

    def test_analytic_eh_probe_and_net_flux_match_lossy_flat_reference(self):
        cfg = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=True,
            diffraction_sample_count_x=24,
            diffraction_sample_count_y=24,
        )
        order = enumerate_diffraction_orders_3d(cfg)[0]
        top_z, bottom_z = _probe_z_locations(cfg)
        top_points = _sample_plane(cfg, z=top_z, nx=24, ny=24)
        bottom_points = _sample_plane(cfg, z=bottom_z, nx=24, ny=24)
        top_e = electric_field_code_values(cfg, top_points)
        top_h = magnetic_field_code_values(cfg, top_points)
        bottom_e = electric_field_code_values(cfg, bottom_points)
        bottom_h = magnetic_field_code_values(cfg, bottom_points)
        incident_power = _incident_power(cfg)
        reference = compute_flat_layer_reference_3d(cfg)

        _, eh_metrics = _eh_fourier_order_powers(
            cfg,
            [order],
            top_points,
            top_e,
            top_h,
            bottom_points,
            bottom_e,
            bottom_h,
            incident_power,
        )
        self.assertAlmostEqual(eh_metrics["R_total_from_eh_fourier"], reference["R_ref"], places=11)
        self.assertAlmostEqual(
            eh_metrics["T_total_from_eh_fourier"],
            reference["T_ref_at_bottom_reference_plane"],
            places=11,
        )
        self.assertAlmostEqual(
            eh_metrics["A_balance_from_eh_fourier"],
            reference["A_ref_between_reference_planes"],
            places=11,
        )

        top_flux = _sampled_flux_code_units(top_e, top_h, np.asarray((0.0, 0.0, 1.0)), cfg)
        bottom_flux = _sampled_flux_code_units(bottom_e, bottom_h, np.asarray((0.0, 0.0, -1.0)), cfg)
        R_flux = 1.0 + top_flux / incident_power
        T_flux = bottom_flux / incident_power
        A_flux = 1.0 - R_flux - T_flux
        self.assertAlmostEqual(R_flux, reference["R_ref"], places=11)
        self.assertAlmostEqual(T_flux, reference["T_ref_at_bottom_reference_plane"], places=11)
        self.assertAlmostEqual(A_flux, reference["A_ref_between_reference_planes"], places=11)
        self.assertGreater(T_flux, 0.0)

    def test_analytic_volume_absorption_matches_lossy_flat_flux_loss(self):
        cfg = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=True,
        )
        reference = compute_flat_layer_reference_3d(cfg)
        volume = analytic_volume_absorption_between_z(cfg, bottom_z=cfg.physical_z_min)
        self.assertEqual(volume["status"], "ok")
        self.assertAlmostEqual(volume["A_volume_ref"], reference["A_ref_between_port_planes"], places=11)

        lossless = stage4_block_config(
            stage_case="stage4_flat_layer_sanity",
            grating_width_x=0.0,
            grating_width_y=0.0,
            grating_height=0.0,
            n_substrate=1.45 + 0.0j,
            n_grating=1.0 + 0.0j,
            diffraction_zero_order_only=True,
        )
        lossless_volume = analytic_volume_absorption_between_z(lossless, bottom_z=lossless.physical_z_min)
        self.assertEqual(lossless_volume["status"], "lossless")
        self.assertAlmostEqual(lossless_volume["A_volume_ref"], 0.0, places=14)

    def test_eh_fourier_separates_same_order_up_down_waves(self):
        cfg = stage4_block_config(diffraction_zero_order_only=True)
        order = enumerate_diffraction_orders_3d(cfg)[0]
        points = _sample_plane(cfg, z=-25.0, nx=16, ny=16)
        basis = dict(polarization_basis_3d(order.alpha, order.gamma, order.beta_bottom, cfg.substrate_index, -1, cfg))
        pol = basis["y"]
        k_down, e_down, h_down = mode_eh_vectors(order.alpha, order.gamma, order.beta_bottom, pol, -1, cfg)
        k_up, e_up, h_up = mode_eh_vectors(order.alpha, order.gamma, order.beta_bottom, pol, 1, cfg)
        down_amp = 0.8 + 0.2j
        up_amp = 0.3 - 0.1j
        e_down_values, h_down_values = _mode_samples(points, k_down, e_down, h_down, down_amp)
        e_up_values, h_up_values = _mode_samples(points, k_up, e_up, h_up, up_amp)

        rows, _ = _eh_fourier_order_powers(
            cfg,
            [order],
            points,
            np.zeros_like(e_down_values),
            np.zeros_like(h_down_values),
            points,
            e_down_values + e_up_values,
            h_down_values + h_up_values,
            _incident_power(cfg),
        )
        recovered = rows[(0, 0, "y")]["transmitted_amplitude_eh_fourier"]
        self.assertLess(abs(recovered - down_amp), 1.0e-12)


if __name__ == "__main__":
    unittest.main()
