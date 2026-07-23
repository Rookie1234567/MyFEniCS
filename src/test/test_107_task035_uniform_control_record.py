from __future__ import annotations

import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
CASE093_CONVERGENCE = (
    ROOT
    / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json"
)
UNIFORM_RECORD = RECORDS / "actual_uniform_tetra_level2_p2_p3_mpi2.json"
UNIFORM_LEVEL1_RECORD = RECORDS / "actual_uniform_tetra_level1_p2_p3_mpi2.json"
ADAPTIVE_RECORD = (
    RECORDS / "actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json"
)
DWR_R_RECORD = RECORDS / "actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json"
DWR_R_CYCLE2_CANONICAL_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle2_canonical_contiguous_mpi8.json"
)
DWR_COMBINED_CYCLE2_CANONICAL_RECORD = RECORDS / (
    "actual_dwr_combined_adaptive_tetra_p2_p3_h50_cycle2_canonical_contiguous_mpi8.json"
)
DWR_COMBINED_CYCLE3_MEMORY_STOP_RECORD = RECORDS / (
    "actual_dwr_combined_adaptive_tetra_p2_p3_h50_theta0p5_0p5_0p15_cycle3_mpi8.json"
)
P3_P4_LEVEL1_RECORD = RECORDS / "actual_uniform_tetra_level1_p3_p4_mpi2.json"
P3_P4_LEVEL1_MPI8_RECORD = RECORDS / "actual_uniform_tetra_level1_p3_p4_mpi8.json"
P3_P4_DWR_R_MPI8_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_mpi8.json"
)
P3_P4_DWR_R_CYCLE2_PRE_TIE_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_mpi8.json"
)
P3_P4_DWR_R_CYCLE2_TIE_V1_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_tie_stable_mpi8.json"
)
P3_P4_DWR_R_THETA03_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p3_cycle1_mpi8.json"
)
P3_P4_DWR_R_THETA_SCHEDULE_RECORD = (
    RECORDS / "actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p5_0p15_cycle2_mpi8.json"
)
P3_P4_DWR_R_CANONICAL_CONNECTIVITY_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_connectivity_mpi8.json"
)
P3_P4_DWR_R_CANONICAL_CONNECTIVITY_REPEAT_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_"
    "canonical_connectivity_repeat_mpi8.json"
)
P3_P4_DWR_R_BALANCED_CONTIGUOUS_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_"
    "canonical_contiguous_balanced_mpi8.json"
)
P3_P4_DWR_R_BALANCED_CONTIGUOUS_REPEAT_RECORD = RECORDS / (
    "actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_"
    "canonical_contiguous_balanced_repeat_mpi8.json"
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
        cls.dwr_r_cycle2_canonical = json.loads(
            DWR_R_CYCLE2_CANONICAL_RECORD.read_text(encoding="utf-8")
        )
        cls.dwr_combined_cycle2_canonical = json.loads(
            DWR_COMBINED_CYCLE2_CANONICAL_RECORD.read_text(encoding="utf-8")
        )
        cls.dwr_combined_cycle3_memory_stop = json.loads(
            DWR_COMBINED_CYCLE3_MEMORY_STOP_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_level1 = json.loads(P3_P4_LEVEL1_RECORD.read_text(encoding="utf-8"))
        cls.p3_p4_level1_mpi8 = json.loads(
            P3_P4_LEVEL1_MPI8_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_mpi8 = json.loads(
            P3_P4_DWR_R_MPI8_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_cycle2_pre_tie = json.loads(
            P3_P4_DWR_R_CYCLE2_PRE_TIE_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_cycle2_tie_v1 = json.loads(
            P3_P4_DWR_R_CYCLE2_TIE_V1_RECORD.read_text(encoding="utf-8")
        )
        cls.case093 = json.loads(CASE093_CONVERGENCE.read_text(encoding="utf-8"))
        cls.p3_p4_dwr_r_theta03 = json.loads(
            P3_P4_DWR_R_THETA03_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_theta_schedule = json.loads(
            P3_P4_DWR_R_THETA_SCHEDULE_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_canonical_connectivity = json.loads(
            P3_P4_DWR_R_CANONICAL_CONNECTIVITY_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_canonical_connectivity_repeat = json.loads(
            P3_P4_DWR_R_CANONICAL_CONNECTIVITY_REPEAT_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_balanced_contiguous = json.loads(
            P3_P4_DWR_R_BALANCED_CONTIGUOUS_RECORD.read_text(encoding="utf-8")
        )
        cls.p3_p4_dwr_r_balanced_contiguous_repeat = json.loads(
            P3_P4_DWR_R_BALANCED_CONTIGUOUS_REPEAT_RECORD.read_text(encoding="utf-8")
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
                self.assertAlmostEqual(dwr["goals"][goal]["absolute_effectivity"], 1.0)
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

    def test_p2_p3_cycle2_is_time_positive_but_dof_efficiency_negative(self) -> None:
        record = self.dwr_r_cycle2_canonical
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "375cfac622ce8e76611bb5b09e5ce7af190856e1",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1276, 7662],
        )
        self.assertEqual(
            [cycle["marker"]["marked_count"] for cycle in record["cycles"]],
            [46, 260, 987],
        )
        self.assertEqual(
            [cycle["enriched_fixed_reference_error_l2"] for cycle in record["cycles"]],
            [
                1.1473425924493463,
                0.17165330581451946,
                0.014373484111754159,
            ],
        )
        self.assertTrue(record["all_fixed_reference_error_reductions_positive"])
        final = record["cycles"][-1]
        self.assertEqual(final["enriched"]["num_nedelec_dofs"], 151518)
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertLess(authority["memory_authority_gib"], 7.4)
        self.assertLess(
            record["elapsed_seconds"],
            0.3 * self.uniform["elapsed_seconds"],
        )
        self.assertLess(
            authority["memory_authority_gib"],
            self.uniform["resource_authority"]["memory_authority_gib"],
        )

        level1_dofs = self.uniform_level1["enriched"]["num_nedelec_dofs"]
        level2_dofs = self.uniform["enriched"]["num_nedelec_dofs"]
        level1_error = self.uniform_level1["enriched_fixed_reference_error_l2"]
        level2_error = self.uniform["enriched_fixed_reference_error_l2"]
        convergence_slope = math.log(level1_error / level2_error) / math.log(
            level2_dofs / level1_dofs
        )
        interpolated_uniform_error = level1_error * (
            final["enriched"]["num_nedelec_dofs"] / level1_dofs
        ) ** (-convergence_slope)
        self.assertGreater(convergence_slope, 1.9)
        self.assertGreater(
            final["enriched_fixed_reference_error_l2"],
            5.0 * interpolated_uniform_error,
        )

    def test_p2_p3_combined_cycle2_is_current_strongest_but_not_dof_win(self) -> None:
        record = self.dwr_combined_cycle2_canonical
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "755f8037ab246df8b3673b818c46f74c9b738637",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["dwr_marker_policy"], "combined_relative_R_T")
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1316, 8842],
        )
        self.assertEqual(
            [cycle["marker"]["marked_count"] for cycle in record["cycles"]],
            [50, 376, 1561],
        )
        self.assertEqual(
            [cycle["enriched_fixed_reference_error_l2"] for cycle in record["cycles"]],
            [1.1473425924493446, 0.130301000462057, 0.004984756092733831],
        )
        self.assertTrue(record["all_fixed_reference_error_reductions_positive"])
        final = record["cycles"][-1]
        r_only_final = self.dwr_r_cycle2_canonical["cycles"][-1]
        self.assertEqual(final["enriched"]["num_nedelec_dofs"], 173325)
        self.assertLess(
            final["enriched_fixed_reference_error_l2"],
            0.35 * r_only_final["enriched_fixed_reference_error_l2"],
        )
        self.assertLess(
            final["enriched"]["num_nedelec_dofs"],
            1.15 * r_only_final["enriched"]["num_nedelec_dofs"],
        )
        level1_dofs = self.uniform_level1["enriched"]["num_nedelec_dofs"]
        level2_dofs = self.uniform["enriched"]["num_nedelec_dofs"]
        level1_error = self.uniform_level1["enriched_fixed_reference_error_l2"]
        level2_error = self.uniform["enriched_fixed_reference_error_l2"]
        slope = math.log(level1_error / level2_error) / math.log(
            level2_dofs / level1_dofs
        )
        interpolated_uniform_error = level1_error * (
            final["enriched"]["num_nedelec_dofs"] / level1_dofs
        ) ** (-slope)
        self.assertGreater(
            final["enriched_fixed_reference_error_l2"],
            2.0 * interpolated_uniform_error,
        )
        self.assertLess(record["elapsed_seconds"], self.uniform["elapsed_seconds"])
        self.assertLess(record["resource_authority"]["memory_authority_gib"], 8.8)

    def test_combined_cycle3_is_a_controlled_memory_stop(self) -> None:
        record = self.dwr_combined_cycle3_memory_stop
        self.assertEqual(record["status"], "formal_not_pass")
        self.assertFalse(record["qualification"]["pass"])
        self.assertIn(
            "not_terminated_for_memory",
            record["qualification"]["failures"],
        )
        self.assertNotIn(
            "not_terminated_for_timeout",
            record["qualification"]["failures"],
        )
        self.assertEqual(
            record["source"]["commit_sha"],
            "4482beb71bfb7e5f57ef5e9c3828294b3999a409",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertTrue(record["warning_triggered"])
        self.assertTrue(record["terminated_for_memory"])
        self.assertFalse(record["terminated_for_timeout"])
        policy = record["resource_policy"]
        self.assertTrue(policy["one_heavy_case_at_a_time"])
        self.assertEqual(policy["termination_gib"], 32.0)
        self.assertEqual(policy["timeout_seconds"], 1800.0)
        self.assertFalse(policy["swap_allowed"])
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertGreaterEqual(authority["memory_authority_gib"], 32.0)
        self.assertLess(authority["memory_authority_gib"], 32.1)
        self.assertEqual(
            authority["stage_peaks"][-1]["stage"],
            "dwr_adaptive_cycle_3_goal_dwr_enriched_solve_and_adjoint",
        )
        self.assertIsNone(record["raw_evidence"]["actual_r5_result_sha256"])
        self.assertEqual(len(record["raw_evidence"]["memory_timeline_sha256"]), 64)
        self.assertEqual(len(record["raw_evidence"]["progress_sha256"]), 64)
        self.assertEqual(len(record["raw_evidence"]["stdout_sha256"]), 64)

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
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)

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
            self.assertLess(mpi8[level]["linear_system_relative_residual"], 1.0e-9)
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
            cycle["enriched_fixed_reference_error_l2"] for cycle in record["cycles"]
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
        self.assertEqual(final["mesh_audit"]["orientation"]["nonpositive_count"], 0)
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
            record["cycles"][1]["DWR"]["goals"]["R_total"]["marked_canonical_cell_ids"]
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
            self.assertEqual(cycle["mesh_audit"]["orientation"]["nonpositive_count"], 0)
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertGreater(authority["memory_authority_gib"], 16.0)
        self.assertLess(authority["memory_authority_gib"], 20.0)

    def test_tie_policy_v1_cycle2_is_positive_with_repeat_overlap_gate(self) -> None:
        record = self.p3_p4_dwr_r_cycle2_tie_v1
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "a7ecab0f54ceee14214ccf63d16b09299665dd18",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1268, 7348],
        )
        final = record["cycles"][-1]
        self.assertAlmostEqual(
            final["enriched_fixed_reference_error_l2"],
            0.0005363453435066528,
        )
        self.assertEqual(final["enriched"]["num_nedelec_dofs"], 315444)
        self.assertEqual(final["mesh_audit"]["orientation"]["nonpositive_count"], 0)
        self.assertEqual(
            final["mesh_audit"]["partition_independent_mesh_sha256"],
            "f64e68fb2e683d212f373e1cf2c91cb5b7cab2a996e586193f714fd5e19675af",
        )
        marker_reports = [
            source["cycles"][1]["DWR"]["goals"]["R_total"]
            for source in (
                self.p3_p4_dwr_r_mpi8,
                self.p3_p4_dwr_r_cycle2_pre_tie,
                record,
            )
        ]
        for report in marker_reports:
            self.assertEqual(report["marking"]["count"], 215)
        for left_index in range(len(marker_reports)):
            for right_index in range(left_index + 1, len(marker_reports)):
                left = set(marker_reports[left_index]["marked_canonical_cell_ids"])
                right = set(marker_reports[right_index]["marked_canonical_cell_ids"])
                overlap = len(left & right) / len(left | right)
                self.assertGreaterEqual(overlap, 0.99)
                self.assertNotEqual(
                    marker_reports[left_index]["marked_geometry_sha256"],
                    marker_reports[right_index]["marked_geometry_sha256"],
                )
        tie_report = marker_reports[-1]["marking"]
        self.assertEqual(tie_report["minimal_count_before_tie_expansion"], 215)
        self.assertEqual(tie_report["cutoff_tie_expansion_count"], 0)
        self.assertEqual(
            tie_report["tie_policy"],
            "include_all_cutoff_contributions_within_relative_1e-10",
        )
        old_final = self.p3_p4_dwr_r_cycle2_pre_tie["cycles"][-1]
        self.assertLess(
            abs(
                final["enriched_fixed_reference_error_l2"]
                - old_final["enriched_fixed_reference_error_l2"]
            ),
            5.0e-9,
        )
        authority = record["resource_authority"]
        self.assertEqual(authority["max_observed_worker_rank_count"], 8)
        self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
        self.assertLess(authority["memory_authority_gib"], 19.0)

    def test_one_dwr_cycle_is_engineering_positive_but_cycle2_is_dominated(
        self,
    ) -> None:
        points = {entry["key"]: entry for entry in self.case093["points"]}
        reference = points["p4_h5"]["full3d"]["official_values"]

        def observable_error(key: str) -> float:
            values = points[key]["full3d"]["official_values"]
            return math.sqrt(
                sum(
                    (values[name] - reference[name]) ** 2
                    for name in ("R_total", "T_total", "A_volume_total")
                )
            )

        cycle1 = self.p3_p4_dwr_r_mpi8["cycles"][-1]
        p4_h10 = points["p4_h10"]["full3d"]
        self.assertLess(
            cycle1["enriched_fixed_reference_error_l2"],
            observable_error("p4_h10"),
        )
        self.assertLess(
            cycle1["enriched"]["num_nedelec_dofs"],
            1.06 * p4_h10["resource"]["dofs"],
        )
        self.assertLess(
            self.p3_p4_dwr_r_mpi8["resource_authority"]["memory_authority_gib"],
            p4_h10["resource"]["peak_memory_gib"],
        )

        cycle2_record = self.p3_p4_dwr_r_cycle2_tie_v1
        cycle2 = cycle2_record["cycles"][-1]
        p4_h7p5 = points["p4_h7p5"]["full3d"]
        self.assertGreater(
            cycle2["enriched_fixed_reference_error_l2"],
            observable_error("p4_h7p5"),
        )
        self.assertGreater(
            cycle2["enriched"]["num_nedelec_dofs"],
            2.0 * p4_h7p5["resource"]["dofs"],
        )
        self.assertGreater(
            cycle2_record["resource_authority"]["memory_authority_gib"],
            1.4 * p4_h7p5["resource"]["peak_memory_gib"],
        )

    def test_theta03_is_a_controlled_negative_cost_screen(self) -> None:
        theta03 = self.p3_p4_dwr_r_theta03
        theta05 = self.p3_p4_dwr_r_mpi8
        self.assertEqual(theta03["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(theta03["qualification"]["pass"])
        self.assertEqual(theta03["qualification"]["failures"], [])
        self.assertEqual(
            theta03["source"]["commit_sha"],
            "6c4b2aee9d7ef2673a66996540c5022defd270a9",
        )
        self.assertTrue(theta03["source"]["stable_and_clean_after"])
        self.assertEqual(theta03["cycles"][0]["marker"]["marked_count"], 23)
        final03 = theta03["cycles"][-1]
        final05 = theta05["cycles"][-1]
        self.assertEqual(final03["mesh_audit"]["global_cell_count"], 1200)
        self.assertEqual(final03["enriched"]["num_nedelec_dofs"], 53128)
        self.assertAlmostEqual(
            final03["enriched_fixed_reference_error_l2"],
            0.010596993391412929,
        )
        self.assertGreater(
            final03["enriched_fixed_reference_error_l2"],
            2.2 * final05["enriched_fixed_reference_error_l2"],
        )
        self.assertGreater(
            final03["enriched"]["num_nedelec_dofs"],
            0.95 * final05["enriched"]["num_nedelec_dofs"],
        )
        points = {entry["key"]: entry for entry in self.case093["points"]}
        reference = points["p4_h5"]["full3d"]["official_values"]
        p4_h10 = points["p4_h10"]["full3d"]
        p4_h10_error = math.sqrt(
            sum(
                (p4_h10["official_values"][name] - reference[name]) ** 2
                for name in ("R_total", "T_total", "A_volume_total")
            )
        )
        self.assertGreater(final03["enriched_fixed_reference_error_l2"], p4_h10_error)
        self.assertLess(
            final03["enriched"]["num_nedelec_dofs"],
            1.01 * p4_h10["resource"]["dofs"],
        )
        self.assertEqual(final03["mesh_audit"]["orientation"]["nonpositive_count"], 0)

    def test_theta015_second_cycle_is_cost_negative_and_exposes_repeat_drift(
        self,
    ) -> None:
        record = self.p3_p4_dwr_r_theta_schedule
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "8c4c62ae5c3047718bd0733a1a3083e3cc99e446",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["theta_schedule"], [0.5, 0.15])
        self.assertEqual(
            [cycle["theta"] for cycle in record["cycles"]],
            [0.5, 0.15, 0.15],
        )
        self.assertEqual(
            [cycle["mesh_audit"]["global_cell_count"] for cycle in record["cycles"]],
            [180, 1268, 6110],
        )
        self.assertEqual(record["cycles"][1]["marker"]["marked_count"], 35)
        final = record["cycles"][-1]
        self.assertEqual(final["enriched"]["num_nedelec_dofs"], 265152)
        self.assertAlmostEqual(
            final["enriched_fixed_reference_error_l2"],
            0.002045169163347349,
        )
        theta05 = self.p3_p4_dwr_r_cycle2_tie_v1
        self.assertLess(
            final["enriched"]["num_nedelec_dofs"],
            theta05["cycles"][-1]["enriched"]["num_nedelec_dofs"],
        )
        self.assertGreater(
            final["enriched_fixed_reference_error_l2"],
            3.5 * theta05["cycles"][-1]["enriched_fixed_reference_error_l2"],
        )
        points = {entry["key"]: entry for entry in self.case093["points"]}
        p4_h7p5 = points["p4_h7p5"]["full3d"]
        reference = points["p4_h5"]["full3d"]["official_values"]
        structured_error = math.sqrt(
            sum(
                (p4_h7p5["official_values"][name] - reference[name]) ** 2
                for name in ("R_total", "T_total", "A_volume_total")
            )
        )
        self.assertGreater(final["enriched_fixed_reference_error_l2"], structured_error)
        self.assertGreater(
            final["enriched"]["num_nedelec_dofs"],
            p4_h7p5["resource"]["dofs"],
        )
        self.assertGreater(
            record["resource_authority"]["memory_authority_gib"],
            p4_h7p5["resource"]["peak_memory_gib"],
        )
        old_cycle1 = self.p3_p4_dwr_r_mpi8["cycles"][-1]
        new_cycle1 = record["cycles"][1]
        self.assertEqual(
            new_cycle1["mesh_audit"]["partition_independent_mesh_sha256"],
            old_cycle1["mesh_audit"]["partition_independent_mesh_sha256"],
        )
        self.assertGreater(
            new_cycle1["enriched_fixed_reference_error_l2"],
            6.0 * old_cycle1["enriched_fixed_reference_error_l2"],
        )

    def test_canonical_tetra_connectivity_recovers_stable_p4_anchor(self) -> None:
        record = self.p3_p4_dwr_r_canonical_connectivity
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "8671bf60f81e606385d129dcc6599ba823ac2aa3",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["marked_cycles_completed"], 1)
        refinement = record["refinements"][0]
        for rebuild_name in ("serial_rebuild", "orientation_rebuild"):
            rebuild = refinement[rebuild_name]
            self.assertTrue(rebuild["canonical_positive_vertex_ordering"])
            self.assertEqual(len(rebuild["canonical_connectivity_sha256"]), 64)
        final = record["cycles"][-1]
        self.assertEqual(
            final["mesh_audit"]["partition_independent_mesh_sha256"],
            "68c06aaad8855926afe82989d89faef32420406693d3b29d8836d7b90aace2e8",
        )
        self.assertEqual(final["coarse"]["matrix_stats"]["matrix_nnz_used"], 2391697.0)
        self.assertEqual(
            final["enriched"]["matrix_stats"]["matrix_nnz_used"], 8572192.0
        )
        self.assertAlmostEqual(
            final["enriched_fixed_reference_error_l2"],
            0.004600195243301677,
        )
        old_stable = self.p3_p4_dwr_r_mpi8["cycles"][-1]
        self.assertLess(
            abs(
                final["enriched_fixed_reference_error_l2"]
                - old_stable["enriched_fixed_reference_error_l2"]
            ),
            1.0e-12,
        )

    def test_canonical_connectivity_alone_leaves_partition_nnz_drift(self) -> None:
        first = self.p3_p4_dwr_r_canonical_connectivity
        repeat = self.p3_p4_dwr_r_canonical_connectivity_repeat
        self.assertEqual(repeat["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(repeat["qualification"]["pass"])
        self.assertEqual(repeat["qualification"]["failures"], [])
        self.assertEqual(
            repeat["source"]["commit_sha"],
            "42642cbcbf3bd4922bdbdff61aaba13db5085d1a",
        )
        self.assertTrue(repeat["source"]["stable_and_clean_after"])
        for rebuild_name in ("serial_rebuild", "orientation_rebuild"):
            first_hash = first["refinements"][0][rebuild_name][
                "canonical_connectivity_sha256"
            ]
            repeat_hash = repeat["refinements"][0][rebuild_name][
                "canonical_connectivity_sha256"
            ]
            self.assertEqual(first_hash, repeat_hash)
        first_final = first["cycles"][-1]
        repeat_final = repeat["cycles"][-1]
        self.assertEqual(
            first_final["mesh_audit"]["partition_independent_mesh_sha256"],
            repeat_final["mesh_audit"]["partition_independent_mesh_sha256"],
        )
        for field in ("coarse", "enriched"):
            self.assertNotEqual(
                first_final[field]["matrix_stats"]["matrix_nnz_used"],
                repeat_final[field]["matrix_stats"]["matrix_nnz_used"],
            )
        self.assertLess(
            abs(
                first_final["enriched_fixed_reference_error_l2"]
                - repeat_final["enriched_fixed_reference_error_l2"]
            ),
            1.0e-12,
        )

    def test_balanced_contiguous_mpi8_repeats_exact_structure(self) -> None:
        first = self.p3_p4_dwr_r_balanced_contiguous
        repeat = self.p3_p4_dwr_r_balanced_contiguous_repeat
        for record, source_sha in (
            (first, "0c81f688c5c4a8e8bcdea8c4ad67f9633bf8bcc2"),
            (repeat, "96b45267eae3df801fad9dda960a59a4639ca1d1"),
        ):
            self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
            self.assertTrue(record["qualification"]["pass"])
            self.assertEqual(record["qualification"]["failures"], [])
            self.assertEqual(record["source"]["commit_sha"], source_sha)
            self.assertTrue(record["source"]["stable_and_clean_after"])
            authority = record["resource_authority"]
            self.assertEqual(authority["max_observed_worker_rank_count"], 8)
            self.assertEqual(authority["max_process_tree_swap_mb"], 0.0)
            self.assertLess(authority["memory_authority_gib"], 4.2)

        first_refinement = first["refinements"][0]["orientation_rebuild"]
        repeat_refinement = repeat["refinements"][0]["orientation_rebuild"]
        for field in (
            "canonical_connectivity_sha256",
            "owned_cell_counts_by_rank",
            "ghost_cell_counts_by_rank",
        ):
            self.assertEqual(first_refinement[field], repeat_refinement[field])
        self.assertEqual(
            first_refinement["owned_cell_counts_by_rank"],
            [158, 159, 158, 159, 158, 159, 158, 159],
        )
        self.assertEqual(
            first_refinement["ghost_cell_counts_by_rank"],
            [71, 127, 149, 136, 142, 139, 134, 70],
        )
        for first_cycle, repeat_cycle in zip(
            first["cycles"], repeat["cycles"], strict=True
        ):
            self.assertEqual(
                first_cycle["mesh_audit"]["partition_independent_mesh_sha256"],
                repeat_cycle["mesh_audit"]["partition_independent_mesh_sha256"],
            )
            for field in ("coarse", "enriched"):
                self.assertEqual(
                    first_cycle[field]["num_nedelec_dofs"],
                    repeat_cycle[field]["num_nedelec_dofs"],
                )
                self.assertEqual(
                    first_cycle[field]["matrix_stats"]["matrix_nnz_used"],
                    repeat_cycle[field]["matrix_stats"]["matrix_nnz_used"],
                )
        first_final = first["cycles"][-1]
        repeat_final = repeat["cycles"][-1]
        self.assertEqual(
            first_final["coarse"]["matrix_stats"]["matrix_nnz_used"], 2391617.0
        )
        self.assertEqual(
            first_final["enriched"]["matrix_stats"]["matrix_nnz_used"], 8571936.0
        )
        self.assertLess(
            abs(
                first_final["enriched_fixed_reference_error_l2"]
                - repeat_final["enriched_fixed_reference_error_l2"]
            ),
            1.0e-12,
        )
        self.assertEqual(
            first["cycles"][0]["marker"]["marked_geometry_sha256"],
            repeat["cycles"][0]["marker"]["marked_geometry_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
