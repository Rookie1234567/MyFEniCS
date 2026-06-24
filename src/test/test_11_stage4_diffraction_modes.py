from __future__ import annotations

import unittest

import numpy as np

from src.postprocessing.diffraction_3d import (
    enumerate_diffraction_orders_3d,
    fit_diffraction_amplitudes_from_samples,
    mode_eh_vectors,
    polarization_basis_3d,
    _probe_z_locations,
)
from src.test.stage2_test_utils import stage4_block_config


def _sample_plane(cfg, z: float, nx: int = 6, ny: int = 5) -> np.ndarray:
    xs = cfg.x_min + (np.arange(nx, dtype=np.float64) + 0.5) * (cfg.x_max - cfg.x_min) / nx
    ys = cfg.y_min + (np.arange(ny, dtype=np.float64) + 0.5) * (cfg.y_max - cfg.y_min) / ny
    return np.asarray([[x, y, z] for y in ys for x in xs], dtype=np.float64)


def _mode_samples(points, kvec, e_vec, h_vec, amplitude: complex) -> tuple[np.ndarray, np.ndarray]:
    phase = np.exp(1j * (kvec[0] * points[:, 0] + kvec[1] * points[:, 1] + kvec[2] * points[:, 2]))
    return amplitude * phase[:, None] * e_vec[None, :], amplitude * phase[:, None] * h_vec[None, :]


class Stage4DiffractionModeTests(unittest.TestCase):
    def test_zero_order_only_catalog(self):
        cfg = stage4_block_config(diffraction_zero_order_only=True)
        orders = enumerate_diffraction_orders_3d(cfg)
        self.assertEqual([(order.m, order.n) for order in orders], [(0, 0)])
        self.assertTrue(orders[0].top_propagating)
        self.assertTrue(orders[0].bottom_propagating)

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

    def test_default_probe_planes_use_configured_fraction_of_physical_layers(self):
        cfg = stage4_block_config(
            diffraction_zero_order_only=False,
            z_min=-50.0,
            z_max=100.0,
            interface_z=0.0,
            grating_height=50.0,
            diffraction_probe_fraction=0.75,
        )
        top_z, bottom_z = _probe_z_locations(cfg)
        self.assertAlmostEqual(top_z, 0.75 * cfg.physical_z_max, places=12)
        self.assertAlmostEqual(bottom_z, 0.75 * cfg.physical_z_min, places=12)
        self.assertGreater(top_z, cfg.grating_z_max)
        self.assertLess(bottom_z, cfg.interface_z)


if __name__ == "__main__":
    unittest.main()
