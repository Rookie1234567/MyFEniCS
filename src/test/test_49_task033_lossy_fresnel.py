from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.common.analytic_fields_3d import (
    _fresnel_components,
    fresnel_reference,
)
from src.common.config_3d import (
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    oblique_incidence_airbox_config,
)
from src.validation.task033_high_order_floquet_fixtures import fresnel_oracle


class Task033LossyFresnelTests(unittest.TestCase):
    @staticmethod
    def _config(grazing_deg: float, polarization: str):
        return oblique_incidence_airbox_config(
            geometry_kind="fresnel_interface",
            n_substrate=SI_SUBSTRATE_INDEX_EUV_13P5_NM,
            incident_theta_deg=90.0 - grazing_deg,
            incident_phi_deg=0.0,
            polarization_kind=polarization,
            custom_polarization=None,
        )

    def test_s_and_p_match_oracle_and_close_interface_power(self):
        for grazing_deg in (1.0, 5.0, 10.0):
            for polarization in ("s", "p"):
                with self.subTest(grazing_deg=grazing_deg, polarization=polarization):
                    cfg = self._config(grazing_deg, polarization)
                    reference = fresnel_reference(cfg)
                    oracle = fresnel_oracle(
                        grazing_deg=grazing_deg,
                        polarization=polarization,
                        n_transmitted=SI_SUBSTRATE_INDEX_EUV_13P5_NM,
                    )
                    oracle_r = complex(
                        oracle["r"]["real"], oracle["r"]["imag"]
                    )
                    oracle_t = complex(
                        oracle["t"]["real"], oracle["t"]["imag"]
                    )
                    self.assertLess(abs(reference["r"] - oracle_r), 2.0e-12)
                    self.assertLess(abs(reference["t"] - oracle_t), 2.0e-12)
                    self.assertLess(
                        abs(reference["R_plus_T"] - 1.0), 2.0e-12
                    )
                    self.assertLess(
                        abs(
                            reference["R"]
                            - oracle["R_interface"]
                        ),
                        2.0e-12,
                    )
                    self.assertLess(
                        abs(
                            reference["T"]
                            - oracle["T_into_substrate_at_interface"]
                        ),
                        2.0e-12,
                    )

    def test_complex_p_basis_preserves_maxwell_and_interface_continuity(self):
        for grazing_deg in (1.0, 5.0, 10.0):
            cfg = self._config(grazing_deg, "p")
            k_inc, k_ref, k_trn, e_inc, e_ref, e_trn = _fresnel_components(cfg)
            h_inc = np.cross(k_inc, e_inc) / cfg.k0
            h_ref = np.cross(k_ref, e_ref) / cfg.k0
            h_trn = np.cross(k_trn, e_trn) / cfg.k0
            scale_e = max(float(np.linalg.norm(e_trn)), 1.0)
            scale_h = max(float(np.linalg.norm(h_trn)), 1.0)
            self.assertLess(
                float(np.linalg.norm((e_inc + e_ref - e_trn)[:2])) / scale_e,
                2.0e-12,
            )
            self.assertLess(
                float(np.linalg.norm((h_inc + h_ref - h_trn)[:2])) / scale_h,
                2.0e-12,
            )
            for wavevector, electric in (
                (k_inc, e_inc),
                (k_ref, e_ref),
                (k_trn, e_trn),
            ):
                self.assertLess(
                    abs(np.dot(wavevector, electric))
                    / max(float(np.linalg.norm(wavevector) * np.linalg.norm(electric)), 1.0),
                    2.0e-12,
                )

    def test_lossy_p_analytic_field_postprocess_uses_the_same_basis(self):
        try:
            from src.solvers.common_3d_postprocess import (
                run_fresnel_analytic_postprocess_sanity,
            )
        except ModuleNotFoundError as exc:
            if exc.name in {"dolfinx", "ufl", "petsc4py"}:
                self.skipTest("DOLFINx runtime is provided by the fixed Docker image.")
            raise

        with TemporaryDirectory() as directory:
            for grazing_deg in (1.0, 5.0, 10.0):
                with self.subTest(grazing_deg=grazing_deg):
                    cfg = self._config(grazing_deg, "p")
                    cfg.stage_case = "fresnel_interface"
                    cfg.use_floquet_xy = True
                    cfg.use_pml = True
                    cfg.pml_top_thickness = 250.0
                    cfg.pml_bottom_thickness = 250.0
                    cfg.nedelec_degree = 1
                    cfg.mesh_target_size = 100.0
                    summary = run_fresnel_analytic_postprocess_sanity(
                        cfg,
                        Path(directory) / f"grazing_{grazing_deg:g}",
                    )
                    self.assertTrue(summary["fresnel_postprocess_sanity_pass"])
                    self.assertLess(summary["fresnel_R_error"], 1.0e-8)
                    self.assertLess(summary["fresnel_T_error"], 1.0e-8)


if __name__ == "__main__":
    unittest.main()
