from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

import numpy as np

from src.common.config_3d import SimulationConfig3D
from src.geometry.mesh_builder_3d import _stage4_axis_plan
from src.geometry.task39extra_v5_r13_mesh_plan import (
    AXIS_CELL_COUNTS,
    FROZEN_AXES_NM,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_loader import InputError
from src.io.input_validation import load_and_resolve, simulation_config_3d_from_normalized
from src.io.native_capacity_profile import (
    V5_EXPECTED_MODE_COUNTS,
    native_profile_facts,
)


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input" / "task39extra_para_workstation_capacity"


class Task39ExtraV5FrozenAxesTests(unittest.TestCase):
    def test_r13_q3_q4_inputs_resolve_the_same_exact_v21_axis_plan(self):
        resolved = []
        for suffix, coarse_degree in (("q4", 4), ("q3", 3)):
            with self.subTest(suffix=suffix):
                specification = load_and_resolve(
                    INPUTS / f"v5_node1_13p5nm_p6h7p5_{suffix}.dat"
                )
                self.assertEqual(
                    specification.solver["coarse_degree"], coarse_degree
                )
                self.assertEqual(
                    specification.discretization["mesh_plan_sha256"],
                    "b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157",
                )
                cfg = simulation_config_3d_from_normalized(
                    specification.as_jsonable()
                )
                self.assertIsInstance(cfg, SimulationConfig3D)
                axis_plan = _stage4_axis_plan(cfg, comm_size=1)
                self.assertEqual(axis_plan.mesh_cells_resolved, AXIS_CELL_COUNTS)
                self.assertEqual(axis_plan.mesh_spacing_mode_resolved, "v21_r13_frozen_axes")
                self.assertTrue(axis_plan.material_plane_alignment["all_aligned"])
                for axis in ("x", "y", "z"):
                    np.testing.assert_array_equal(
                        getattr(axis_plan, f"{axis}_values"),
                        np.asarray(FROZEN_AXES_NM[axis], dtype=np.float64),
                    )
                self.assertEqual(
                    specification.output["diffraction_order_max_m"], 2
                )
                self.assertEqual(
                    specification.output["diffraction_order_max_n"], 2
                )
                resolved.append(specification)
        self.assertEqual(
            resolved[0].physical_model_sha256,
            resolved[1].physical_model_sha256,
        )

    def test_v5_worker_cpu_is_opt_in_and_legacy_native_profile_stays_cpu23(self):
        for identity, coarse_degree in (
            ("dual_condensed_balh_native_13p5_q4_v5", 4),
            ("dual_condensed_balh_native_13p5_q3_v5", 3),
            ("dual_condensed_balh_native_5nm_v5", 4),
            ("dual_condensed_balh_native_2nm_v5", 4),
        ):
            facts = native_profile_facts(identity)
            self.assertEqual(facts["native_execution"]["worker_cpu"], 24)
            self.assertEqual(facts["native_execution"]["supervisor_cpu"], 9)
            self.assertEqual(facts["retained_condensed_v20"]["coarse_degree"], coarse_degree)
            self.assertEqual(facts["resources"]["resource_stop_policy"], "measured_tree_rss_only_v3")
            self.assertEqual(facts["resources"]["rss_hard_limit_bytes"], 1_300_000_000_000)
            self.assertTrue(facts["outer"]["screen"]["progress_only"])
            self.assertFalse(facts["outer"]["screen"]["stop_on_screen"])

        v5_specification = load_and_resolve(
            INPUTS / "v5_node1_13p5nm_p6h7p5_q4.dat"
        )
        v5_argv = build_execution_plan(
            v5_specification,
            ROOT / "results" / "_v5_execution_plan_contract",
            source_sha="a" * 40,
        ).argv
        self.assertEqual(
            v5_argv[:5],
            ("/usr/bin/taskset", "-c", "24", "/usr/bin/numactl", "--preferred=1"),
        )

        legacy = native_profile_facts("dual_condensed_balh_native_5nm_v3")
        self.assertNotIn("native_execution", legacy)
        self.assertEqual(legacy["resources"]["resource_stop_policy"], "measured_tree_rss_only_v3")
        self.assertEqual(legacy["outer"]["screen"]["progress_only"], True)
        legacy_specification = load_and_resolve(
            INPUTS / "original_5nm_si_p6h4_dual_condensed_v3.dat"
        )
        legacy_argv = build_execution_plan(
            legacy_specification,
            ROOT / "results" / "_legacy_execution_plan_contract",
            source_sha="b" * 40,
        ).argv
        self.assertEqual(
            legacy_argv[:5],
            ("/usr/bin/taskset", "-c", "23", "/usr/bin/numactl", "--preferred=1"),
        )

    def test_old_shortwave_inputs_keep_boundary_fitted_mesh_identity(self):
        for name in (
            "original_5nm_si_p6h4_dual_condensed_v3.dat",
            "original_2nm_si_p6h1p5_measured.dat",
        ):
            with self.subTest(name=name):
                specification = load_and_resolve(INPUTS / name)
                self.assertEqual(
                    specification.discretization["mesh_spacing_mode"],
                    "boundary_fitted",
                )
                for field in (
                    "mesh_axis_cell_counts", "mesh_axis_x_values",
                    "mesh_axis_y_values", "mesh_axis_z_values",
                    "mesh_plan_id", "mesh_plan_sha256",
                ):
                    self.assertNotIn(field, specification.discretization)

    def test_coarse_degree_is_v5_only_and_required_explicitly(self):
        v5 = load_and_resolve(INPUTS / "v5_node1_13p5nm_p6h7p5_q3.dat")
        self.assertEqual(v5.solver["coarse_degree"], 3)

        legacy_path = INPUTS / "original_5nm_si_p6h4_dual_condensed_v3.dat"
        legacy = load_and_resolve(legacy_path)
        self.assertNotIn("coarse_degree", legacy.solver)

        with tempfile.TemporaryDirectory(prefix="task39extra-v5-coarse-degree-") as temp:
            bad_input = Path(temp) / legacy_path.name
            bad_input.write_text(
                legacy_path.read_text(encoding="utf-8").replace(
                    "[solver]\n", "[solver]\ncoarse_degree = 4\n", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InputError, "coarse_degree is reserved"):
                load_and_resolve(bad_input)

    def test_shortwave_v5_inputs_preserve_physics_and_bind_measured_rss_contract(self):
        cases = (
            (
                "v5_node1_5nm_p6h4_q4.dat",
                "original_5nm_si_p6h4_native.dat",
                "dual_condensed_balh_native_5nm_v5",
                5.0,
                4.0,
            ),
            (
                "v5_node1_2nm_p6h1p5_q4.dat",
                "original_2nm_si_p6h1p5_native.dat",
                "dual_condensed_balh_native_2nm_v5",
                2.0,
                1.5,
            ),
        )
        for new_name, old_name, profile, wavelength, mesh_nm in cases:
            with self.subTest(new_input=new_name):
                new = load_and_resolve(INPUTS / new_name)
                old = load_and_resolve(INPUTS / old_name)
                self.assertEqual(new.solver["preconditioner"], profile)
                self.assertEqual(new.solver["coarse_degree"], 4)
                self.assertEqual(new.solver["restart"], 32)
                self.assertEqual(new.solver["max_iterations"], 2048)
                self.assertEqual(new.incidence["wavelength_nm"], wavelength)
                self.assertEqual(new.discretization["nedelec_degree"], 6)
                self.assertEqual(new.discretization["mesh_target_nm"], mesh_nm)
                self.assertEqual(
                    new.physical_model_sha256,
                    old.physical_model_sha256,
                    msg=f"{new_name} changed the physical-model identity",
                )
                for section in ("geometry", "materials", "incidence", "discretization", "boundary", "method", "output"):
                    self.assertEqual(
                        dict(getattr(new, section)),
                        dict(getattr(old, section)),
                        msg=f"{new_name} changed the old {section} physical/output contract",
                    )
                self.assertEqual(new.execution["time_limit_mode"], "none")
                self.assertIsNone(new.execution.get("timeout_seconds"))
                self.assertEqual(new.execution["mpi_size"], 1)
                self.assertEqual(new.execution["native_memory_policy"], "preferred_node1")
                self.assertFalse(new.execution["require_zero_swap"])
                self.assertAlmostEqual(
                    new.execution["warning_memory_gib"] * 1024**3,
                    1_170_000_000_000,
                    delta=1,
                )
                self.assertAlmostEqual(
                    new.execution["terminate_memory_gib"] * 1024**3,
                    1_300_000_000_000,
                    delta=1,
                )
                facts = native_profile_facts(profile)
                self.assertEqual(
                    V5_EXPECTED_MODE_COUNTS[profile],
                    600 if wavelength == 5.0 else 3904,
                )
                self.assertEqual(facts["resources"]["rss_hard_limit_bytes"], 1_300_000_000_000)
                self.assertEqual(facts["resources"]["rss_warning_bytes"], 1_170_000_000_000)
                self.assertEqual(facts["resources"]["swap_policy"], "observe_only")
                self.assertEqual(facts["resources"]["prediction_admission_policy"], "record_only")
                self.assertIsNone(facts["campaign_authorization"]["workflow_seconds"])
                argv = build_execution_plan(
                    new,
                    ROOT / "results" / "_v5_shortwave_execution_plan_contract",
                    source_sha="c" * 40,
                ).argv
                self.assertEqual(
                    argv[:5],
                    ("/usr/bin/taskset", "-c", "24", "/usr/bin/numactl", "--preferred=1"),
                )


if __name__ == "__main__":
    unittest.main()
