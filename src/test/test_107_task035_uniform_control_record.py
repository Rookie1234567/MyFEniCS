from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
UNIFORM_RECORD = RECORDS / "actual_uniform_tetra_level2_p2_p3_mpi2.json"
UNIFORM_LEVEL1_RECORD = RECORDS / "actual_uniform_tetra_level1_p2_p3_mpi2.json"
ADAPTIVE_RECORD = (
    RECORDS / "actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json"
)
DWR_R_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json"
)
P3_P4_LEVEL1_RECORD = (
    RECORDS / "actual_uniform_tetra_level1_p3_p4_mpi2.json"
)



class Task035UniformControlRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uniform = json.loads(UNIFORM_RECORD.read_text(encoding="utf-8"))
        cls.uniform_level1 = json.loads(
            UNIFORM_LEVEL1_RECORD.read_text(encoding="utf-8")
        )
        cls.adaptive = json.loads(ADAPTIVE_RECORD.read_text(encoding="utf-8"))
        cls.dwr_r = json.loads(DWR_R_RECORD.read_text(encoding="utf-8"))
        cls.p3_p4_level1 = json.loads(
            P3_P4_LEVEL1_RECORD.read_text(encoding="utf-8")
        )

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

    def test_level1_cost_matched_anchor_is_clean_sha_mpi2(self) -> None:
        record = self.uniform_level1
        self.assertEqual(record["status"], "actual_uniform_tetra_control_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "75781dda90afad40cba0a7861538d733581a9e53",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["final_mesh_audit"]["global_cell_count"], 1440)
        self.assertEqual(
            record["final_mesh_audit"]["partition_independent_mesh_sha256"],
            "22204e1bdaef3321585f54d111ea1f8d070c0c202931817eb6d5b245a21891af",
        )
        self.assertAlmostEqual(
            record["coarse_fixed_reference_error_l2"],
            1.0250853958921506,
        )
        self.assertAlmostEqual(
            record["enriched_fixed_reference_error_l2"],
            0.06761458409703112,
        )
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 2
        )
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        self.assertLess(record["resource_authority"]["memory_authority_gib"], 1.1)

    def test_dwr_r_watchdog_and_discrete_adjoint_gates_pass(self) -> None:
        record = self.dwr_r
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "dfb219f00466dd5ca56c51baea127273c23aaf0a",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["dwr_marker_policy"], "R_total")
        self.assertEqual(record["marked_cycles_completed"], 1)
        self.assertEqual(len(record["cycles"]), 2)
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1276],
        )
        self.assertEqual(
            [cycle["marker"]["marked_count"] for cycle in record["cycles"]],
            [46, 260],
        )
        self.assertEqual(
            record["cycles"][0]["marker"]["marked_geometry_sha256"],
            "8fae8171771a02ed262dd51a3304ba85cd187719f0394ec92bd1333bc5cbd9e5",
        )
        for cycle in record["cycles"]:
            dwr = cycle["DWR"]
            self.assertTrue(dwr["adjoint_qualification"]["pass"])
            for goal in ("R_total", "T_total"):
                self.assertAlmostEqual(
                    dwr["goals"][goal]["absolute_effectivity"], 1.0
                )
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 2)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertLess(authority["memory_authority_gib"], 1.1)

    def test_dwr_r_is_a_mixed_not_production_signal(self) -> None:
        dwr_final = self.dwr_r["cycles"][-1]
        uniform = self.uniform_level1
        r5_final = self.adaptive["cycles"][1]
        self.assertAlmostEqual(
            dwr_final["coarse_fixed_reference_error_l2"], 1.0234845059305149
        )
        self.assertAlmostEqual(
            dwr_final["enriched_fixed_reference_error_l2"], 0.17165330581454807
        )
        self.assertLess(
            dwr_final["coarse_fixed_reference_error_l2"],
            uniform["coarse_fixed_reference_error_l2"],
        )
        self.assertLess(
            dwr_final["coarse_fixed_reference_error_l2"],
            r5_final["coarse_fixed_reference_error_l2"],
        )
        self.assertGreater(
            dwr_final["enriched_fixed_reference_error_l2"],
            2.5 * uniform["enriched_fixed_reference_error_l2"],
        )
        self.assertGreater(
            dwr_final["enriched_fixed_reference_error_l2"],
            r5_final["enriched_fixed_reference_error_l2"],
        )

    def test_p3_p4_uniform1_is_a_strong_global_p_signal(self) -> None:
        record = self.p3_p4_level1
        self.assertEqual(record["status"], "actual_uniform_tetra_control_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "1f05c380861dd286510d069a8739927bc97dc5fa",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["final_mesh_audit"]["global_cell_count"], 1440)
        self.assertEqual(
            record["final_mesh_audit"]["partition_independent_mesh_sha256"],
            self.uniform_level1["final_mesh_audit"][
                "partition_independent_mesh_sha256"
            ],
        )
        self.assertAlmostEqual(
            record["coarse_fixed_reference_error_l2"],
            self.uniform_level1["enriched_fixed_reference_error_l2"],
            places=12,
        )
        self.assertAlmostEqual(
            record["enriched_fixed_reference_error_l2"],
            0.0059771134455638905,
        )
        self.assertLess(
            record["enriched_fixed_reference_error_l2"],
            0.09 * record["coarse_fixed_reference_error_l2"],
        )
        p4_dofs = record["enriched"]["num_nedelec_dofs"]
        uniform2_p2_dofs = self.uniform["coarse"]["num_nedelec_dofs"]
        self.assertLess(p4_dofs, uniform2_p2_dofs)
        self.assertLess(
            record["enriched_fixed_reference_error_l2"],
            self.uniform["coarse_fixed_reference_error_l2"],
        )
        self.assertLess(
            record["resource_authority"]["memory_authority_gib"],
            0.31 * self.uniform["resource_authority"]["memory_authority_gib"],
        )
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 2
        )
        self.assertEqual(
            record["resource_authority"]["max_process_tree_swap_mb"], 0.0
        )


if __name__ == "__main__":
    unittest.main()
