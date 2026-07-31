from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mpi4py import MPI

from src import main as main_module
from src.common import output_paths
from src.common.config_3d import (
    NUMERICAL_SANITY_ONLY,
    oblique_incidence_airbox_config,
    require_material_wavelength_consistency,
    target_stage4_config,
)
from src.common.output_paths import shared_unique_run_dir, unique_run_dir


class MainPresetContractTests(unittest.TestCase):
    def test_unique_run_directory_is_atomically_claimed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("src.common.output_paths.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 31, 12, 0, 0)
                first = unique_run_dir(root, "case")
                second = unique_run_dir(root, "case")
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    @unittest.skipUnless(MPI.COMM_WORLD.size == 2, "requires MPI2")
    def test_shared_unique_run_directory_broadcasts_failure_and_success(self):
        comm = MPI.COMM_WORLD
        directory = TemporaryDirectory() if comm.rank == 0 else None
        root = Path(
            comm.bcast(directory.name if directory is not None else None, root=0)
        )
        try:
            failure_context = (
                patch.object(
                    output_paths,
                    "unique_run_dir",
                    side_effect=OSError("injected rank0 mkdir failure"),
                )
                if comm.rank == 0
                else nullcontext()
            )
            failure: tuple[str, str] | None = None
            with failure_context:
                try:
                    shared_unique_run_dir(comm, root / "failure", "case")
                except Exception as error:
                    failure = (type(error).__name__, str(error))
            failures = comm.allgather(failure)
            expected_failure = (
                "RuntimeError",
                "rank 0 failed to claim shared run directory: "
                "OSError: injected rank0 mkdir failure",
            )
            self.assertEqual(failures, [expected_failure, expected_failure])

            chosen = shared_unique_run_dir(comm, root / "success", "case")
            successes = comm.allgather((str(chosen), chosen.is_dir()))
            self.assertEqual({path for path, _exists in successes}, {str(chosen)})
            self.assertTrue(all(exists for _path, exists in successes))

            explicit_shared = root / "explicit-shared"
            shared = shared_unique_run_dir(
                comm,
                explicit_shared,
                "unused",
                enabled=False,
            )
            shared_states = comm.allgather((str(shared), shared.exists()))
            self.assertEqual(
                shared_states,
                [(str(explicit_shared), False), (str(explicit_shared), False)],
            )
        finally:
            comm.barrier()
            if directory is not None:
                directory.cleanup()

    def test_known_13p5_material_contract_passes_canonical_target(self):
        cfg = target_stage4_config(degree=5, h_nm=10.0)
        audit = require_material_wavelength_consistency(cfg)
        self.assertEqual(audit["status"], "known_material_consistent")
        self.assertEqual(audit["active_regions"], ["substrate", "grating"])

    def test_known_13p5_material_is_rejected_at_another_wavelength(self):
        cfg = target_stage4_config(degree=5, h_nm=10.0)
        cfg.lambda0 = 0.7
        data = cfg.as_jsonable()
        self.assertNotIn("material_wavelength_consistency", data)
        with self.assertRaisesRegex(ValueError, "13.5 nm"):
            require_material_wavelength_consistency(cfg)

    def test_known_13p5_label_and_index_must_match_bidirectionally(self):
        for field, value in (
            ("n_substrate", 0.9 + 0.01j),
            ("substrate_material_label", "custom substrate"),
        ):
            cfg = target_stage4_config(degree=5, h_nm=10.0)
            setattr(cfg, field, value)
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "must pair"
            ):
                require_material_wavelength_consistency(cfg)

    def test_inactive_grating_material_is_not_checked(self):
        cfg = target_stage4_config(degree=5, h_nm=10.0)
        cfg.grating_width_x = 0.0
        cfg.n_grating = 0.8 + 0.1j
        audit = require_material_wavelength_consistency(cfg)
        self.assertEqual(audit["status"], "known_material_consistent")
        self.assertEqual(audit["active_regions"], ["substrate"])

    def test_airbox_without_active_material_regions_is_not_applicable(self):
        cfg = oblique_incidence_airbox_config()
        cfg.validation_role = "physical_benchmark_candidate"
        audit = require_material_wavelength_consistency(cfg)
        self.assertEqual(audit["status"], "not_applicable")
        self.assertEqual(audit["active_regions"], [])
        self.assertEqual(audit["known_material_regions"], [])

    def test_custom_0p7_material_serializes_only_as_unverified_diagnostic(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cfg.lambda0 = 0.7
        cfg.n_substrate = 0.8 + 0.02j
        cfg.n_grating = 0.7 + 0.03j
        cfg.substrate_material_label = "custom 0.7 nm substrate"
        cfg.grating_material_label = "custom 0.7 nm grating"
        data = cfg.as_jsonable()
        self.assertNotIn("material_wavelength_consistency", data)
        json.dumps(data)
        audit = require_material_wavelength_consistency(cfg)
        self.assertEqual(audit["status"], "custom_material_unverified")

        cfg.validation_role = "physical_benchmark_candidate"
        with self.assertRaisesRegex(ValueError, NUMERICAL_SANITY_ONLY):
            require_material_wavelength_consistency(cfg)

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
