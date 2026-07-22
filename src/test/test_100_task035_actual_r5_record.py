from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_global_r5_p2_p3_h10_mpi8.json"
)


class Task035ActualR5RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_clean_sha_and_watchdog_gates_are_bound(self) -> None:
        self.assertEqual(self.record["status"], "actual_global_r5_pass")
        self.assertTrue(self.record["source"]["stable_and_clean_after"])
        self.assertEqual(len(self.record["source"]["commit_sha"]), 40)
        self.assertTrue(self.record["qualification"]["pass"])
        self.assertEqual(self.record["qualification"]["failures"], [])
        self.assertEqual(self.record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        self.assertEqual(self.record["resource_authority"]["max_observed_worker_rank_count"], 8)

    def test_actual_p2_p3_target_solves_and_cell_estimator_pass(self) -> None:
        self.assertEqual(self.record["coarse"]["degree"], 2)
        self.assertEqual(self.record["enriched"]["degree"], 3)
        self.assertEqual(self.record["coarse"]["num_mesh_cells"], 252)
        self.assertEqual(self.record["enriched"]["num_mesh_cells"], 252)
        self.assertLess(self.record["coarse"]["linear_system_relative_residual"], 1.0e-9)
        self.assertLess(self.record["enriched"]["linear_system_relative_residual"], 1.0e-9)
        r5 = self.record["R5"]
        self.assertTrue(r5["formal_hierarchical_fe_r5"])
        self.assertTrue(r5["finite_cell_contributions"])
        self.assertTrue(r5["nonnegative_cell_contributions"])
        self.assertEqual(r5["owned_cell_contribution_count"], 252)
        self.assertLess(r5["correction_energy"]["relative_closure_error"], 1.0e-10)
        self.assertGreaterEqual(r5["marking"]["captured_fraction"], 0.5)
        self.assertEqual(len(r5["marking"]["global_cell_ids_sha256"]), 64)

    def test_evidence_remains_research_only_and_hash_bound(self) -> None:
        self.assertTrue(
            self.record["qualification"]["checks"]["ordinary_default_unchanged"]
        )
        for name in (
            "actual_r5_result_sha256",
            "memory_timeline_sha256",
            "progress_sha256",
            "stdout_sha256",
        ):
            self.assertEqual(len(self.record["raw_evidence"][name]), 64)


if __name__ == "__main__":
    unittest.main()
