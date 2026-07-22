from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
UNIFORM_RECORD = RECORDS / "actual_uniform_tetra_level2_p2_p3_mpi2.json"
ADAPTIVE_RECORD = (
    RECORDS / "actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json"
)


class Task035UniformControlRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uniform = json.loads(UNIFORM_RECORD.read_text(encoding="utf-8"))
        cls.adaptive = json.loads(ADAPTIVE_RECORD.read_text(encoding="utf-8"))

    def test_uniform_watchdog_and_numerical_gates_pass(self) -> None:
        record = self.uniform
        self.assertEqual(record["status"], "actual_uniform_tetra_control_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "e1743b632aeda845e151efaef7bdf2c81e347f36",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 2
        )
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        self.assertLess(record["coarse"]["linear_system_relative_residual"], 1.0e-9)
        self.assertLess(record["enriched"]["linear_system_relative_residual"], 1.0e-9)

    def test_two_uniform_levels_and_hashes_are_bound(self) -> None:
        refinements = self.uniform["refinements"]
        self.assertEqual(
            [entry["parent_global_cells"] for entry in refinements], [180, 1440]
        )
        self.assertEqual(
            [entry["refined_global_cells"] for entry in refinements], [1440, 11520]
        )
        self.assertEqual(
            [
                entry["refined_mesh_audit"]["partition_independent_mesh_sha256"]
                for entry in refinements
            ],
            [
                "22204e1bdaef3321585f54d111ea1f8d070c0c202931817eb6d5b245a21891af",
                "37d4f643572e77154af28b6c8dd69b8d31ceb40ee1a1ea5528ee9782199f28a8",
            ],
        )
        for entry in refinements:
            self.assertTrue(entry["uniform_all_parent_cells_marked"])
            self.assertEqual(
                entry["periodic_edge_closure"]["boundary_sleeve_edges_added"],
                0,
            )

    def test_uniform_is_more_accurate_at_comparable_cost(self) -> None:
        uniform = self.uniform
        adaptive = self.adaptive
        adaptive_final = adaptive["cycles"][-1]
        cell_ratio = (
            adaptive_final["mesh_audit"]["global_cell_count"]
            / uniform["final_mesh_audit"]["global_cell_count"]
        )
        memory_ratio = (
            adaptive["resource_authority"]["memory_authority_gib"]
            / uniform["resource_authority"]["memory_authority_gib"]
        )
        time_ratio = adaptive["elapsed_seconds"] / uniform["elapsed_seconds"]
        p2_error_ratio = (
            adaptive_final["coarse_fixed_reference_error_l2"]
            / uniform["coarse_fixed_reference_error_l2"]
        )
        p3_error_ratio = (
            adaptive_final["enriched_fixed_reference_error_l2"]
            / uniform["enriched_fixed_reference_error_l2"]
        )
        self.assertLess(cell_ratio, 0.8)
        self.assertLess(memory_ratio, 0.8)
        self.assertLess(time_ratio, 0.6)
        self.assertGreater(p2_error_ratio, 18.0)
        self.assertGreater(p3_error_ratio, 5.0)


if __name__ == "__main__":
    unittest.main()
