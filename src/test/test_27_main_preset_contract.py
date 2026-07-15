from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import main as main_module
from src.common.config_3d import target_stage4_config


class MainPresetContractTests(unittest.TestCase):
    def test_default_is_safe_stage1_and_names_are_unique(self):
        names = main_module.available_preset_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(main_module.ACTIVE_PYCHARM_PRESET, "3d_stage1_airbox_smoke")
        dimension, args = main_module.preset_cli_args(main_module.ACTIVE_PYCHARM_PRESET)
        self.assertEqual(dimension, "3d")
        self.assertEqual(args[args.index("--stage-case") + 1], "stage1_airbox")
        self.assertEqual(set(names), set(main_module.PRESET_INFO))

    def test_verbose_listing_exposes_resource_and_physical_identity(self):
        listing = main_module.format_preset_listing(verbose=True)
        for name in main_module.available_preset_names():
            with self.subTest(name=name):
                self.assertIn(name, listing)
        for field in ("geometry=", "discretization=", "resource=", "status="):
            self.assertIn(field, listing)

    def test_no_preset_silently_claims_iterative_qualification(self):
        for name in main_module.available_preset_names():
            dimension, args = main_module.preset_cli_args(name)
            joined = " ".join(args).lower()
            with self.subTest(name=name):
                self.assertIn(dimension, {"2d", "3d"})
                self.assertNotIn("iterative", name.lower())
                self.assertNotIn("qualified", joined)
                self.assertNotIn("fgmres", joined)

    def test_main_source_contains_no_invalid_group_values(self):
        text = Path(main_module.__file__).read_text(encoding="utf-8")
        for invalid in ("stage2_all", "stage4_all", "case=both"):
            self.assertNotIn(invalid, text)

    def test_demo_and_target_stage4_presets_are_unambiguous(self):
        names = set(main_module.available_preset_names())
        for ambiguous in (
            "3d_stage4b_grating_direct_h5",
            "3d_stage4b_grating_direct_h3",
            "3d_stage4b_grating_mumps_ooc",
            "3d_stage4b_grating_mumps_blr",
        ):
            self.assertNotIn(ambiguous, names)
        self.assertIn("3d_stage4b_demo_direct_h5", names)
        self.assertIn("3d_target_grating_direct_h5", names)

    def test_flat_stage4_preset_contains_no_grating_block(self):
        settings = main_module.PRESETS_3D["3d_stage4a_flat_layer_direct"]
        self.assertEqual(settings.stage_case, "stage4_flat_layer_sanity")
        self.assertEqual(
            (
                settings.grating_width_x,
                settings.grating_width_y,
                settings.grating_height,
            ),
            (0.0, 0.0, 0.0),
        )

    def test_target_direct_presets_share_the_canonical_physical_config(self):
        physical_fields = (
            "stage_case",
            "lambda0",
            "period_x",
            "period_y",
            "air_height",
            "substrate_thickness",
            "n_substrate",
            "n_grating",
            "grating_width_x",
            "grating_width_y",
            "grating_height",
            "incident_theta_deg",
            "incident_phi_deg",
            "polarization_kind",
            "nedelec_degree",
            "mesh_target_size",
            "stage4_boundary_model",
            "stage4_dtn_order_policy",
        )
        for h_nm in (5.0, 3.0):
            name = f"3d_target_grating_direct_h{int(h_nm)}"
            settings = main_module.PRESETS_3D[name]
            canonical = target_stage4_config(degree=2, h_nm=h_nm)
            with self.subTest(name=name):
                for field in physical_fields:
                    self.assertEqual(
                        getattr(settings, field), getattr(canonical, field)
                    )
                self.assertFalse(settings.matrix_diagnostics_assemble_only)
                self.assertTrue(canonical.matrix_diagnostics_assemble_only)

    def test_every_2d_preset_is_accepted_by_the_real_runner_parser(self):
        from src.runners import run_cases

        def fake_summary(cfg, out_dir, **_kwargs):
            return {
                "case_name": cfg.case_name,
                "config": cfg.as_jsonable(),
                "out_dir": str(out_dir),
                "power_metrics": {},
            }

        with TemporaryDirectory() as tmp:
            with (
                patch.object(run_cases, "run_case", side_effect=fake_summary),
                patch.object(run_cases, "run_port_case", side_effect=fake_summary),
                patch.object(run_cases, "run_te_case", side_effect=fake_summary),
                patch.object(run_cases, "run_te_port_case", side_effect=fake_summary),
            ):
                for name in main_module.PRESETS_2D:
                    _, args = main_module.preset_cli_args(name)
                    with self.subTest(name=name):
                        result = run_cases.main([*args, "--results-root", tmp])
                        self.assertIsNotNone(result)

    def test_every_3d_preset_is_accepted_by_the_real_runner_parser(self):
        from src.runners import run_3d_cases

        def fake_run(cfg, out_dir):
            return {"case_name": cfg.case_name, "out_dir": str(out_dir)}

        with TemporaryDirectory() as tmp:
            with patch.object(run_3d_cases, "_run_stage_config", side_effect=fake_run):
                for name in main_module.PRESETS_3D:
                    _, args = main_module.preset_cli_args(name)
                    with self.subTest(name=name):
                        run_3d_cases.main([*args, "--results-root", tmp])
                self.assertEqual(
                    len(list(Path(tmp).rglob("all_run_summary.json"))),
                    len(main_module.PRESETS_3D),
                )


if __name__ == "__main__":
    unittest.main()
