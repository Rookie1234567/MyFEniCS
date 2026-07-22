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
P3_P4_LEVEL1_MPI8_RECORD = (
    RECORDS / "actual_uniform_tetra_level1_p3_p4_mpi8.json"
)
P3_P4_DWR_R_MPI8_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_mpi8.json"
)
P3_P4_DWR_R_CYCLE2_PRE_TIE_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_mpi8.json"
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
        cls.p3_p4_level1_mpi8 = json.loads(
            P3_P4_LEVEL1_MPI8_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_mpi8 = json.loads(
            P3_P4_DWR_R_MPI8_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_cycle2_pre_tie = json.loads(
            P3_P4_DWR_R_CYCLE2_PRE_TIE_RECORD.read_text(encoding="utf-8")
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

    def test_p3_p4_mpi8_identity_and_resource_tradeoff(self) -> None:
        mpi2 = self.p3_p4_level1
        mpi8 = self.p3_p4_level1_mpi8
        self.assertEqual(mpi8["status"], "actual_uniform_tetra_control_pass")
        self.assertTrue(mpi8["qualification"]["pass"])
        self.assertEqual(mpi8["qualification"]["failures"], [])
        self.assertEqual(
            mpi8["source"]["commit_sha"],
            "73c494d4113430df4744e4566afa3495ddf419ab",
        )
        self.assertTrue(mpi8["source"]["stable_and_clean_after"])
        self.assertEqual(
            mpi8["final_mesh_audit"]["partition_independent_mesh_sha256"],
            mpi2["final_mesh_audit"]["partition_independent_mesh_sha256"],
        )
        for level in ("coarse", "enriched"):
            self.assertEqual(
                mpi8[level]["num_nedelec_dofs"],
                mpi2[level]["num_nedelec_dofs"],
            )
            self.assertLess(
                mpi8[level]["linear_system_relative_residual"], 1.0e-9
            )
            for observable in ("R_total", "T_total", "A_volume_total"):
                self.assertAlmostEqual(
                    mpi8[level][observable], mpi2[level][observable], places=12
                )
        self.assertAlmostEqual(
            mpi8["coarse_fixed_reference_error_l2"],
            mpi2["coarse_fixed_reference_error_l2"],
            places=12,
        )
        self.assertAlmostEqual(
            mpi8["enriched_fixed_reference_error_l2"],
            mpi2["enriched_fixed_reference_error_l2"],
            places=12,
        )
        authority = mpi8["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertLess(mpi8["elapsed_seconds"], 0.5 * mpi2["elapsed_seconds"])
        self.assertGreater(
            authority["memory_authority_gib"],
            mpi2["resource_authority"]["memory_authority_gib"],
        )
        self.assertLess(authority["memory_authority_gib"], 5.0)

    def test_p3_p4_dwr_cycle1_beats_uniform_for_p4_only(self) -> None:
        adaptive = self.p3_p4_dwr_r_mpi8
        uniform = self.p3_p4_level1_mpi8
        self.assertEqual(adaptive["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(adaptive["qualification"]["pass"])
        self.assertEqual(adaptive["qualification"]["failures"], [])
        self.assertEqual(
            adaptive["source"]["commit_sha"],
            "891fd579bf5128fb6a6c861fb9c03b2db2e470c0",
        )
        self.assertTrue(adaptive["source"]["stable_and_clean_after"])
        self.assertEqual(adaptive["dwr_marker_policy"], "R_total")
        self.assertEqual(adaptive["marked_cycles_completed"], 1)
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in adaptive["cycles"]],
            [180, 1268],
        )
        final = adaptive["cycles"][-1]
        self.assertEqual(final["marker"]["marked_count"], 215)
        self.assertEqual(
            final["marker"]["marked_geometry_sha256"],
            "94e60338ecb73ec69e1ad481b684ce8549a8f93fb45c7d00c95ec02b263985a7",
        )
        self.assertAlmostEqual(
            final["coarse_fixed_reference_error_l2"], 0.1572607696270727
        )
        self.assertAlmostEqual(
            final["enriched_fixed_reference_error_l2"], 0.004600195243332768
        )
        self.assertLess(
            final["enriched_fixed_reference_error_l2"],
            0.78 * uniform["enriched_fixed_reference_error_l2"],
        )
        self.assertLess(
            final["mesh_audit"]["global_cell_count"],
            0.89 * uniform["final_mesh_audit"]["global_cell_count"],
        )
        self.assertLess(
            final["enriched"]["num_nedelec_dofs"],
            0.89 * uniform["enriched"]["num_nedelec_dofs"],
        )
        self.assertGreater(
            final["coarse_fixed_reference_error_l2"],
            2.0 * uniform["coarse_fixed_reference_error_l2"],
        )
        for cycle in adaptive["cycles"]:
            self.assertTrue(cycle["DWR"]["adjoint_qualification"]["pass"])
            for goal in ("R_total", "T_total"):
                self.assertAlmostEqual(
                    cycle["DWR"]["goals"][goal]["absolute_effectivity"],
                    1.0,
                )
        authority = adaptive["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertLess(
            authority["memory_authority_gib"],
            uniform["resource_authority"]["memory_authority_gib"],
        )

    def test_pre_tie_policy_cycle2_preserves_positive_and_drift_evidence(self) -> None:
        record = self.p3_p4_dwr_r_cycle2_pre_tie
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "9e0483b18d593d644d790d2f4d8d0a7f1009daf0",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["marked_cycles_completed"], 2)
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1268, 7356],
        )
        coarse_errors = [
            cycle["coarse_fixed_reference_error_l2"] for cycle in record["cycles"]
        ]
        enriched_errors = [
            cycle["enriched_fixed_reference_error_l2"]
            for cycle in record["cycles"]
        ]
        self.assertTrue(
            all(right < left for left, right in zip(coarse_errors, coarse_errors[1:]))
        )
        self.assertTrue(
            all(
                right < left
                for left, right in zip(enriched_errors, enriched_errors[1:])
            )
        )
        self.assertAlmostEqual(enriched_errors[-1], 0.0005363437843649089)
        self.assertLess(
            enriched_errors[-1],
            self.uniform["enriched_fixed_reference_error_l2"],
        )
        final = record["cycles"][-1]
        self.assertEqual(final["enriched"]["num_nedelec_dofs"], 315768)
        self.assertEqual(
            final["mesh_audit"]["orientation"]["nonpositive_count"], 0
        )
        self.assertEqual(
            final["mesh_audit"]["partition_independent_mesh_sha256"],
            "5414a0fcf8e3f2186fcf4aa3dff133bf2546b16b68e6e8c7751eb6f03c93f635",
        )
        previous_marker = set(
            self.p3_p4_dwr_r_mpi8["cycles"][1]["DWR"]["goals"]["R_total"][
                "marked_canonical_cell_ids"
            ]
        )
        repeated_marker = set(
            record["cycles"][1]["DWR"]["goals"]["R_total"][
                "marked_canonical_cell_ids"
            ]
        )
        self.assertEqual(len(previous_marker), 215)
        self.assertEqual(len(repeated_marker), 215)
        self.assertEqual(len(previous_marker & repeated_marker), 214)
        self.assertEqual(len(previous_marker ^ repeated_marker), 2)
        self.assertAlmostEqual(
            len(previous_marker & repeated_marker)
            / len(previous_marker | repeated_marker),
            214 / 216,
        )
        for cycle in record["cycles"]:
            self.assertTrue(cycle["DWR"]["adjoint_qualification"]["pass"])
            self.assertEqual(
                cycle["mesh_audit"]["orientation"]["nonpositive_count"], 0
            )
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertGreater(authority["memory_authority_gib"], 16.0)
        self.assertLess(authority["memory_authority_gib"], 20.0)


if __name__ == "__main__":
    unittest.main()
