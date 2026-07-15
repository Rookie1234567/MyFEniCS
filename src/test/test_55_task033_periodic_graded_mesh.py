from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.geometry.task033_periodic_graded_mesh import (
    AdaptiveMeshBudgetError,
    AdaptiveMeshContractError,
    Task033Stage4Geometry,
    axis_neighbor_ratio,
    build_adaptive_planning_record,
    build_physics_informed_graded_plan,
    compression_classification,
    dorfler_mark,
    qualify_same_accuracy_candidate,
    rebuild_from_cell_indicators,
    synchronize_periodic_cell_marks,
    uniform_reference_mesh_cells,
)


class Task033PeriodicGradedMeshTests(unittest.TestCase):
    def test_periodic_mark_union_includes_opposite_faces_and_corners(self):
        marks = np.zeros((4, 3, 2), dtype=bool)
        marks[0, 1, 0] = True
        marks[2, 0, 1] = True
        marks[0, 0, 0] = True
        synced = synchronize_periodic_cell_marks(marks)
        self.assertTrue(synced[-1, 1, 0])
        self.assertTrue(synced[2, -1, 1])
        self.assertTrue(synced[-1, -1, 0])
        np.testing.assert_array_equal(synced[0, :, :], synced[-1, :, :])
        np.testing.assert_array_equal(synced[:, 0, :], synced[:, -1, :])

    def test_h5_and_h3_plans_are_conforming_fitted_and_smaller_by_cell_count(self):
        for reference_h in (5.0, 3.0):
            with self.subTest(reference_h=reference_h):
                plan = build_physics_informed_graded_plan(reference_h_nm=reference_h)
                certificate = plan.certificate()
                self.assertTrue(certificate["eligible_for_mesh_smoke"])
                self.assertTrue(certificate["checks"]["degree_is_fixed_p2"])
                self.assertTrue(certificate["checks"]["conforming_tensor_product"])
                self.assertFalse(
                    certificate["checks"]["custom_hanging_node_constraints_used"]
                )
                self.assertTrue(
                    certificate["checks"]["bottom_top_modal_trace_xy_exact_match"]
                )
                self.assertFalse(
                    certificate["checks"]["ordinary_default_changed"]
                )
                self.assertLessEqual(
                    axis_neighbor_ratio(plan.x_values, periodic=True),
                    2.0 * (1.0 + 1.0e-12),
                )
                self.assertLessEqual(
                    axis_neighbor_ratio(plan.y_values, periodic=True),
                    2.0 * (1.0 + 1.0e-12),
                )
                self.assertLess(
                    plan.mesh_cells["total"],
                    uniform_reference_mesh_cells(reference_h),
                )
                for value in (16.5, 33.5):
                    self.assertTrue(np.any(np.isclose(plan.x_values, value)))
                for value in (0.0, 10.0):
                    self.assertTrue(np.any(np.isclose(plan.bottom_z_values, value)))
                for value in (110.0, 120.0):
                    self.assertTrue(np.any(np.isclose(plan.top_z_values, value)))

    def test_dorfler_indicator_rebuild_is_deterministic_and_budgeted(self):
        plan = build_physics_informed_graded_plan(reference_h_nm=5.0)
        nx = len(plan.x_values) - 1
        ny = len(plan.y_values) - 1
        bottom = np.zeros((nx, ny, len(plan.bottom_z_values) - 1))
        top = np.zeros((nx, ny, len(plan.top_z_values) - 1))
        bottom[0, 1, 0] = 10.0
        top[-1, 1, -1] = 5.0
        marked = dorfler_mark(bottom, theta=0.5)
        self.assertEqual(int(np.count_nonzero(marked)), 1)
        rebuilt_a = rebuild_from_cell_indicators(
            plan,
            bottom_indicator=bottom,
            top_indicator=top,
            max_total_cells=100_000,
        )
        rebuilt_b = rebuild_from_cell_indicators(
            plan,
            bottom_indicator=bottom,
            top_indicator=top,
            max_total_cells=100_000,
        )
        self.assertEqual(rebuilt_a.plan_hash, rebuilt_b.plan_hash)
        self.assertEqual(rebuilt_a.parent_plan_hash, plan.plan_hash)
        self.assertGreater(rebuilt_a.mesh_cells["total"], plan.mesh_cells["total"])
        self.assertTrue(rebuilt_a.certificate()["eligible_for_mesh_smoke"])
        with self.assertRaises(AdaptiveMeshBudgetError):
            rebuild_from_cell_indicators(
                plan,
                bottom_indicator=bottom,
                top_indicator=top,
                max_total_cells=1,
            )

    def test_accuracy_contract_fails_closed_then_accepts_clean_measured_gate(self):
        plan = build_physics_informed_graded_plan(reference_h_nm=3.0)
        missing = qualify_same_accuracy_candidate(
            plan=plan,
            reference=None,
            candidate=None,
        )
        self.assertEqual(missing["status"], "not_qualified_missing_evidence")
        reference = {
            "data_identity": "measured",
            "source_clean": True,
            "degree": 2,
            "h_nm": 3.0,
            "local_fe_rows": 68_396,
            "full_field_available": True,
            "source_commit": "a" * 40,
            "physics_signature": "task033_13p5nm_si_10deg_s_m160",
        }
        candidate = {
            "data_identity": "measured",
            "source_clean": True,
            "degree": 2,
            "local_fe_rows": 30_000,
            "true_residual": 1.0e-11,
            "max_abs_rta_delta": 5.0e-7,
            "max_significant_order_amplitude_relative_delta": 5.0e-5,
            "sampled_interface_e_relative_error": 1.0e-3,
            "sampled_interface_h_relative_error": 2.0e-3,
            "modal_truncation_gate_pass": True,
            "source_commit": "b" * 40,
            "physics_signature": "task033_13p5nm_si_10deg_s_m160",
            "mesh_plan_hash": plan.plan_hash,
        }
        passed = qualify_same_accuracy_candidate(
            plan=plan,
            reference=reference,
            candidate=candidate,
        )
        self.assertEqual(passed["status"], "same_accuracy_strong_gate_pass")
        self.assertAlmostEqual(passed["compression"], 68_396 / 30_000)
        self.assertEqual(passed["compression_classification"], "clear_success")
        candidate["source_clean"] = False
        dirty = qualify_same_accuracy_candidate(
            plan=plan,
            reference=reference,
            candidate=candidate,
        )
        self.assertFalse(dirty["mandatory_gate_pass"])
        self.assertIn(
            "both_records_must_come_from_tracked_source_clean_commits",
            dirty["reasons"],
        )

    def test_contract_rejects_wrong_reference_and_preserves_task_classes(self):
        with self.assertRaises(AdaptiveMeshContractError):
            build_physics_informed_graded_plan(reference_h_nm=2.0)
        expected = {
            1.2: "weak_signal",
            1.3: "useful_engineering_positive",
            2.0: "clear_success",
            3.0: "combined_engineering_target",
            5.0: "strong_preferred_target",
        }
        for value, label in expected.items():
            self.assertEqual(compression_classification(value), label)

    def test_planning_record_never_claims_pde_or_accuracy_without_evidence(self):
        plan = build_physics_informed_graded_plan(reference_h_nm=5.0)
        record = build_adaptive_planning_record(plan)
        self.assertEqual(record["status"], "plan_only_no_pde_run")
        self.assertFalse(record["identity"]["is_pde_run"])
        self.assertFalse(record["identity"]["is_solver_pass"])
        self.assertFalse(record["identity"]["ordinary_default_changed"])
        self.assertFalse(
            record["derived_mesh_cell_comparison"]["accuracy_qualified"]
        )
        self.assertEqual(
            record["same_accuracy_qualification"]["status"],
            "not_qualified_missing_evidence",
        )
        self.assertEqual(
            record["algorithm_boundaries"]["generic_y_material"],
            "not_qualified_fail_closed",
        )

    def test_runner_writes_parseable_fail_closed_record(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "adaptive_h5.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "benchmarks.run_task033_adaptive_mesh",
                    "--reference-h",
                    "5",
                    "--output-json",
                    str(output),
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["record_type"], "p2_periodic_graded_mesh_plan")
            self.assertEqual(payload["status"], "plan_only_no_pde_run")

    @unittest.skipUnless(
        importlib.util.find_spec("dolfinx") is not None,
        "DOLFINx runtime is required for the materialization smoke test.",
    )
    def test_dolfinx_materialization_keeps_matching_trace_and_floquet(self):
        from basix.ufl import element
        from dolfinx import default_real_type, fem

        from src.common.config_3d import target_stage4_config
        from src.constraints.floquet_3d import build_double_floquet_mpc
        from src.geometry.task033_periodic_graded_mesh import (
            build_task033_graded_local_mesh_pair,
        )

        cfg = target_stage4_config(degree=2, h_nm=5.0)
        plan = build_physics_informed_graded_plan(
            reference_h_nm=5.0,
            geometry=Task033Stage4Geometry.from_config(cfg),
        )
        bottom, top = build_task033_graded_local_mesh_pair(cfg, plan)
        self.assertEqual(bottom.mesh_cells[:2], top.mesh_cells[:2])
        self.assertEqual(
            bottom.global_interface_facet_count,
            top.global_interface_facet_count,
        )
        self.assertEqual(bottom.local_interface_outward_normal_sign, +1)
        self.assertEqual(top.local_interface_outward_normal_sign, -1)
        for local in (bottom, top):
            space = fem.functionspace(
                local.mesh,
                element(
                    "N1curl",
                    local.mesh.basix_cell(),
                    2,
                    dtype=default_real_type,
                ),
            )
            floquet = build_double_floquet_mpc(space, local.mesh_data, cfg)
            self.assertGreater(floquet.num_constraints, 0)
            self.assertLessEqual(floquet.max_masters_per_slave, 1)


if __name__ == "__main__":
    unittest.main()
