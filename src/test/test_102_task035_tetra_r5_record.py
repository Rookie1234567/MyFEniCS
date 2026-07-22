from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_global_r5_tetra_p2_p3_h50_mpi2.json"
)


class Task035TetraR5RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_periodic_tetra_target_pde_and_watchdog_pass(self) -> None:
        self.assertEqual(self.record["status"], "actual_global_r5_pass")
        self.assertTrue(self.record["qualification"]["pass"])
        self.assertEqual(self.record["qualification"]["failures"], [])
        self.assertTrue(self.record["source"]["stable_and_clean_after"])
        self.assertEqual(self.record["resource_authority"]["max_observed_worker_rank_count"], 2)
        self.assertEqual(self.record["resource_authority"]["max_process_tree_swap_mb"], 0.0)

    def test_actual_tetra_p2_p3_and_r5_metrics_are_bound(self) -> None:
        for solve, degree in ((self.record["coarse"], 2), (self.record["enriched"], 3)):
            self.assertEqual(solve["degree"], degree)
            self.assertEqual(solve["mesh_cell_type_actual"], "tetrahedron")
            self.assertEqual(solve["num_mesh_cells"], 180)
            self.assertTrue(solve["official_result"])
            self.assertLess(solve["linear_system_relative_residual"], 1.0e-9)
        r5 = self.record["R5"]
        self.assertTrue(r5["formal_hierarchical_fe_r5"])
        self.assertEqual(r5["owned_cell_contribution_count"], 180)
        self.assertLess(r5["correction_energy"]["relative_closure_error"], 1.0e-10)
        self.assertEqual(
            r5["marking"]["global_cell_ids_sha256"],
            "2153dfe45d360b395b1de4669a277d08f5d73b9b5ca85f193e988f98add4f731",
        )
        self.assertGreaterEqual(r5["marking"]["captured_fraction"], 0.5)


if __name__ == "__main__":
    unittest.main()
