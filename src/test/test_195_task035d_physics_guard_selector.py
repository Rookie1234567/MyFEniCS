from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
from mpi4py import MPI

from src.adaptivity.high_order_same_error import ProbeSet
from src.adaptivity.physics_guard_variable_p import (
    build_sidewall_z0_guard_plan,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


ROOT = Path(__file__).resolve().parents[2]
CASE097 = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)


class Task035dPhysicsGuardSelectorTests(unittest.TestCase):
    def test_regional_metric_separates_existing_probe_labels(self) -> None:
        import importlib.util

        path = CASE097 / "generate_physics_guard_recovery.py"
        spec = importlib.util.spec_from_file_location(
            "task035d_generate_physics_guard_recovery",
            path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        points = np.zeros((4, 3), dtype=np.float64)
        probes = ProbeSet(
            name="fixture",
            points=points,
            weights=np.asarray([1.0, 1.0, 2.0, 2.0]),
            region_labels=("a", "a", "b", "b"),
            definition={"fixture": True},
            sha256="fixture",
        )
        p6 = np.ones((4, 3), dtype=np.complex128)
        p5 = p6.copy()
        candidate = p6.copy()
        p5[:2, 0] += 0.25
        candidate[:2, 0] += 0.5
        p5[2:, 1] += 0.5
        candidate[2:, 1] += 0.25
        result = module.regional_probe_metrics(
            probes,
            global_p5=p5,
            global_p6=p6,
            candidate=candidate,
        )
        self.assertEqual(set(result["regions"]), {"a", "b"})
        self.assertAlmostEqual(
            result["regions"]["a"][
                "t30_to_p5_band_relative_l2_ratio"
            ],
            2.0,
        )
        self.assertAlmostEqual(
            result["regions"]["b"][
                "t30_to_p5_band_relative_l2_ratio"
            ],
            0.5,
        )

    def test_h10_sidewall_z0_guard_is_exact_sequence_and_mpi_stable(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        if comm.size not in {1, 2, 8}:
            self.skipTest("physics-guard selector qualifies MPI1/2/8")
        with tempfile.TemporaryDirectory(
            prefix=f"task035d-physics-guard-mpi{comm.size}-",
            dir="/tmp",
        ) as directory:
            cfg = replace(
                target_stage4_config(degree=6, h_nm=10.0),
                case_name=f"physics_guard_test_mpi{comm.size}",
                unique_output=False,
            )
            mesh_data = build_airbox_mesh_3d(
                cfg,
                Path(directory) / "mesh",
            )
            proposal = build_sidewall_z0_guard_plan(mesh_data.mesh)

        audit = proposal.audit
        self.assertTrue(audit["pass"])
        self.assertEqual(
            audit["cycle1_cell_degree_counts"],
            {"p4": 0, "p5": 240, "p6": 12},
        )
        self.assertEqual(
            audit["cell_degree_counts"],
            {"p4": 72, "p5": 168, "p6": 12},
        )
        self.assertEqual(
            audit["actual_conforming_active_fe_dofs"],
            89_870,
        )
        self.assertEqual(
            audit["active_trace_rows_before_periodic_elimination"],
            36_374,
        )
        self.assertEqual(
            audit["periodic_independent_trace_rows"],
            30_984,
        )
        self.assertEqual(audit["predicted_direct_solve_rows"], 31_064)
        self.assertEqual(
            audit["active_rows_by_dimension"],
            {"edge": 4_902, "face": 31_472, "cell_interior": 53_496},
        )
        self.assertEqual(
            audit["cycle2_plan_sha256"],
            "8172bcc9ca2e2fcbc23a8ca15524f80b7658ccf0c19d24da4dcff1ed32fee062",
        )
        self.assertEqual(
            audit["maximum_adjacent_cell_degree_jump"],
            1,
        )
        self.assertTrue(audit["active_fe_dof_gate_pass"])
        self.assertTrue(audit["periodic_constraint_audit"]["pass"])
        self.assertFalse(audit["actual_channel_dwr"])
        self.assertFalse(audit["formal_accuracy_credit"])
        self.assertTrue(audit["fresh_12_channel_pde_required"])

        boxes = tuple(proposal.cycle2.cell_degree_by_box)
        for canonical_id in proposal.p6_canonical_cell_ids:
            box = boxes[canonical_id]
            self.assertGreaterEqual(box[0], 16.5)
            self.assertLessEqual(box[3], 33.5)
            self.assertGreaterEqual(box[2], 0.0)
            self.assertLessEqual(box[5], 20.0)
        for canonical_id in proposal.p4_canonical_cell_ids:
            box = boxes[canonical_id]
            self.assertIn((box[0], box[3]), {(0.0, 8.25), (41.75, 50.0)})
            self.assertGreaterEqual(box[2], 0.0)
            self.assertLessEqual(box[5], 120.0)


if __name__ == "__main__":
    unittest.main()
