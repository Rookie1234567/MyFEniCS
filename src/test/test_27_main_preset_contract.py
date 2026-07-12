from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import main as main_module


class MainPresetContractTests(unittest.TestCase):
    def test_default_is_safe_stage1_and_names_are_unique(self):
        names = main_module.available_preset_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(main_module.ACTIVE_PYCHARM_PRESET, "3d_stage1_airbox_smoke")
        dimension, args = main_module.preset_cli_args(main_module.ACTIVE_PYCHARM_PRESET)
        self.assertEqual(dimension, "3d")
        self.assertEqual(args[args.index("--stage-case") + 1], "stage1_airbox")

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
