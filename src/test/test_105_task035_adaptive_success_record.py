from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json"
)


class Task035AdaptiveSuccessRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_watchdog_source_resource_and_reference_gates_pass(self) -> None:
        record = self.record
        self.assertEqual(record["status"], "actual_r5_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(
            record["source"]["commit_sha"],
            "9ee77e2bd90dafe1623942221ff75793ac38d5cb",
        )
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 2
        )
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        reference = record["fixed_observable_reference"]
        self.assertEqual(reference["key"], "p4_h5")
        self.assertFalse(reference["continuum_reference"])
        self.assertEqual(
            reference["record_sha256"],
            "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111",
        )

    def test_two_actual_cycles_reduce_both_fixed_reference_errors(self) -> None:
        cycles = self.record["cycles"]
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in cycles],
            [180, 1308, 8785],
        )
        self.assertEqual(
            [cycle["coarse"]["num_nedelec_dofs"] for cycle in cycles],
            [1470, 9504, 60330],
        )
        self.assertEqual(
            [cycle["enriched"]["num_nedelec_dofs"] for cycle in cycles],
            [4011, 26730, 172257],
        )
        coarse_errors = [cycle["coarse_fixed_reference_error_l2"] for cycle in cycles]
        enriched_errors = [
            cycle["enriched_fixed_reference_error_l2"] for cycle in cycles
        ]
        self.assertGreater(coarse_errors[0], coarse_errors[1])
        self.assertGreater(coarse_errors[1], coarse_errors[2])
        self.assertGreater(enriched_errors[0], enriched_errors[1])
        self.assertGreater(enriched_errors[1], enriched_errors[2])
        self.assertLess(enriched_errors[-1], 1.0e-2)
        for cycle in cycles:
            self.assertTrue(cycle["mesh_audit"]["pass"])
            self.assertLess(cycle["coarse"]["linear_system_relative_residual"], 1.0e-9)
            self.assertLess(
                cycle["enriched"]["linear_system_relative_residual"], 1.0e-9
            )
            self.assertGreaterEqual(cycle["R5"]["marking"]["captured_fraction"], 0.5)
            self.assertLess(
                cycle["R5"]["correction_energy"]["relative_closure_error"],
                1.0e-10,
            )

    def test_multilevel_refinement_is_deterministic_and_periodic(self) -> None:
        self.assertEqual(len(self.record["refinements"]), 2)
        for refinement in self.record["refinements"]:
            self.assertTrue(refinement["pass"])
            self.assertEqual(
                refinement["refinement_execution"],
                "replicated_comm_self_then_distribute",
            )
            edge = refinement["periodic_edge_closure"]
            self.assertTrue(edge["full_periodic_boundary_synchronization"])
            audit = refinement["refined_mesh_audit"]
            self.assertEqual(audit["orientation"]["nonpositive_count"], 0)
            self.assertTrue(audit["periodic_x"]["pass"])
            self.assertTrue(audit["periodic_y"]["pass"])


if __name__ == "__main__":
    unittest.main()
