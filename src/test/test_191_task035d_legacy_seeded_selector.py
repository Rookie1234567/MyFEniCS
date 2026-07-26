from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from mpi4py import MPI

from src.adaptivity.legacy_seeded_variable_p import (
    build_legacy_seeded_variable_p_plan,
    load_legacy_multigoal_cell_seed,
    periodic_cell_components,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


_CASE097 = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
_SEED = _CASE097 / "records" / "legacy_multigoal_seed_v1.json"

_EXPECTED = {
    0.30: {
        "captured": 0.3128451732112291,
        "counts": {"p4": 144, "p5": 56, "p6": 52},
        "active_rows": 87_600,
        "trace_before": 35_208,
        "trace_independent": 28_910,
        "solve_rows": 28_990,
        "plan_sha": (
            "862a0347792c356858b405d27f9874cfb9a28b3d75034d73f75c594c5c43c26d"
        ),
    },
    0.25: {
        "captured": 0.25807889894175046,
        "counts": {"p4": 159, "p5": 51, "p6": 42},
        "active_rows": 82_052,
        "trace_before": 33_740,
        "trace_independent": 27_789,
        "solve_rows": 27_869,
        "plan_sha": (
            "666a20fa5ed4354e380b8286c3b6321b8e6b243e5b89df56ec35a0a869d0f9ad"
        ),
    },
    0.15: {
        "captured": 0.15823083322507697,
        "counts": {"p4": 178, "p5": 46, "p6": 28},
        "active_rows": 74_522,
        "trace_before": 31_658,
        "trace_independent": 25_972,
        "solve_rows": 26_052,
        "plan_sha": (
            "a940c09f208c03fcbb4c07cd8527313ace3a5c63945eb68e8fe66bfc9860b669"
        ),
    },
}


class Task035dLegacySeededSelectorTests(unittest.TestCase):
    def test_periodic_cell_components_close_double_periodic_corners(
        self,
    ) -> None:
        boxes = tuple(
            (
                float(x),
                float(y),
                0.0,
                float(x + 1),
                float(y + 1),
                1.0,
            )
            for x in range(3)
            for y in range(3)
        )
        components = periodic_cell_components(boxes)
        self.assertEqual(
            components,
            (
                (0, 2, 6, 8),
                (1, 7),
                (3, 5),
                (4,),
            ),
        )

    def test_h10_t30_t25_t15_plans_reproduce_hash_bound_authority(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        if comm.size not in {1, 2, 8}:
            self.skipTest("Case097 selector qualifies serial/MPI2/MPI8")
        with tempfile.TemporaryDirectory(
            prefix=f"task035d-selector-mpi{comm.size}-",
        ) as directory:
            cfg = replace(
                target_stage4_config(degree=6, h_nm=10.0),
                case_name=(
                    f"task035d_selector_identity_mpi{comm.size}"
                ),
                unique_output=False,
            )
            mesh_data = build_airbox_mesh_3d(
                cfg,
                Path(directory) / "mesh",
            )
            seed = load_legacy_multigoal_cell_seed(
                mesh_data.mesh,
                _SEED,
            )
            self.assertFalse(seed.audit["production_qualified"])
            self.assertFalse(seed.audit["formal_selector_authority"])
            self.assertTrue(seed.audit["fresh_12_channel_pde_required"])
            for target, expected in _EXPECTED.items():
                plan = build_legacy_seeded_variable_p_plan(
                    mesh_data.mesh,
                    seed,
                    target_score_mass=target,
                )
                audit = plan.audit
                self.assertAlmostEqual(
                    audit["captured_score_mass"],
                    expected["captured"],
                    places=15,
                )
                self.assertEqual(
                    audit["cell_degree_counts"],
                    expected["counts"],
                )
                self.assertEqual(
                    audit["actual_conforming_active_fe_dofs"],
                    expected["active_rows"],
                )
                self.assertEqual(
                    audit[
                        "active_trace_rows_before_periodic_elimination"
                    ],
                    expected["trace_before"],
                )
                self.assertEqual(
                    audit["periodic_independent_trace_rows"],
                    expected["trace_independent"],
                )
                self.assertEqual(
                    audit["predicted_direct_solve_rows"],
                    expected["solve_rows"],
                )
                self.assertEqual(
                    audit["cycle2_plan_sha256"],
                    expected["plan_sha"],
                )
                self.assertTrue(audit["active_fe_dof_gate_pass"])
                self.assertTrue(
                    audit["periodic_constraint_audit"]["pass"]
                )
                self.assertTrue(audit["fresh_12_channel_pde_required"])
                self.assertFalse(
                    audit["seed_audit"]["production_qualified"]
                )


if __name__ == "__main__":
    unittest.main()
