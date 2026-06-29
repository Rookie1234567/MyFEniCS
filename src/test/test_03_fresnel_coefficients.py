from __future__ import annotations

import unittest

import numpy as np

from src.common.analytic_fields_3d import fresnel_reference
from src.common.config_3d import normal_incidence_airbox_config, oblique_incidence_airbox_config
from src.solvers.common_3d_fields import _mode_basis
from src.solvers.common_3d_forms import (
    _field_formulation_label,
    _use_incident_scattered_formulation,
    _use_reference_correction_formulation,
)
from src.solvers.common_3d_postprocess import (
    run_fresnel_analytic_postprocess_sanity,
)
from src.test.stage2_test_utils import temp_output_dir


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

    def test_legacy_custom_fresnel_fit_uses_s_basis(self):
        cfg = normal_incidence_airbox_config(
            stage_case="fresnel_interface",
            geometry_kind="fresnel_interface",
            n_substrate=1.45 + 0.0j,
            polarization_kind="custom",
            custom_polarization=(1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
        )
        _, polarization = _mode_basis(cfg, cfg.n_air, vertical_sign=-1)
        self.assertLess(float(np.linalg.norm(polarization - cfg.s_polarization_vector)), 1.0e-14)

    def test_stage2_reference_correction_formulation_labels(self):
        stage1 = normal_incidence_airbox_config(stage_case="stage1_airbox")
        self.assertFalse(_use_reference_correction_formulation(stage1))
        self.assertFalse(_use_incident_scattered_formulation(stage1))
        self.assertEqual(_field_formulation_label(stage1, False, False), "total_field")

        floquet = normal_incidence_airbox_config(stage_case="floquet_airbox")
        self.assertTrue(_use_reference_correction_formulation(floquet))
        self.assertFalse(_use_incident_scattered_formulation(floquet))
        self.assertEqual(_field_formulation_label(floquet, True, False), "incident_correction")

        pml = normal_incidence_airbox_config(stage_case="pml_airbox")
        self.assertTrue(_use_reference_correction_formulation(pml))
        self.assertFalse(_use_incident_scattered_formulation(pml))
        self.assertEqual(_field_formulation_label(pml, True, False), "reference_correction")

        fresnel = normal_incidence_airbox_config(stage_case="fresnel_interface", geometry_kind="fresnel_interface")
        self.assertFalse(_use_reference_correction_formulation(fresnel))
        self.assertTrue(_use_incident_scattered_formulation(fresnel))
        self.assertEqual(_field_formulation_label(fresnel, False, True), "incident_scattered")

    def test_fresnel_analytic_total_field_postprocess_sanity(self):
        cfg = normal_incidence_airbox_config(
            stage_case="fresnel_interface",
            geometry_kind="fresnel_interface",
            use_floquet_xy=True,
            use_pml=True,
            pml_top_thickness=250.0,
            pml_bottom_thickness=250.0,
            n_substrate=1.45 + 0.0j,
            polarization_kind="s",
            custom_polarization=None,
            nedelec_degree=1,
            mesh_target_size=100.0,
        )
        summary = run_fresnel_analytic_postprocess_sanity(cfg, temp_output_dir("fresnel_analytic_postprocess"))
        self.assertTrue(summary["fresnel_postprocess_sanity_pass"])
        self.assertLess(float(summary["fresnel_R_error"]), 1.0e-10)
        self.assertLess(float(summary["fresnel_T_error"]), 1.0e-10)
        self.assertLess(float(summary["fresnel_top_mode_fit_residual"]), 1.0e-1)
        self.assertLess(float(summary["fresnel_bottom_mode_fit_residual"]), 1.0e-1)


if __name__ == "__main__":
    unittest.main()
