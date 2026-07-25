from __future__ import annotations

import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
R_ONLY = (
    RECORDS
    / (
        "actual_dwr_r_adaptive_tetra_p4_p5_h37p5_theta0p7_cycle1_"
        "full_periodic_closure_mpi8.json"
    )
)
MULTI_GOAL = (
    RECORDS
    / (
        "actual_dwr_multigoal_normalized_tetra_p4_p5_h37p5_theta0p7_cycle1_"
        "full_periodic_closure_mpi8.json"
    )
)
REFERENCE = {
    "R_total": 0.0007663133771040101,
    "T_total": 0.602677530502972,
    "A_volume_total": 0.3965561561199801,
}
CONTROL = {
    "R_total": 0.0008024690153384762,
    "T_total": 0.602429772906308,
    "A_volume_total": 0.3967677580783896,
}


class Task035ReviewV5RecordTests(unittest.TestCase):
    def test_h37p5_normalized_multi_goal_record_is_qualified(self) -> None:
        record = json.loads(MULTI_GOAL.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertTrue(all(record["qualification"]["checks"].values()))
        self.assertEqual(
            record["source"]["commit_sha"],
            "4e334a527ad57452ca3b12ab38d3059406f5a4c9",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(
            record["dwr_marker_policy"],
            "tolerance_normalized_R_T",
        )
        self.assertEqual(record["marked_cycles_requested"], 1)
        self.assertEqual(record["marked_cycles_completed"], 1)
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        self.assertLess(record["resource_authority"]["memory_authority_gib"], 16.0)

    def test_one_allowed_refinement_is_identical_to_r_only(self) -> None:
        multi = json.loads(MULTI_GOAL.read_text(encoding="utf-8"))
        r_only = json.loads(R_ONLY.read_text(encoding="utf-8"))
        multi_initial = multi["cycles"][0]
        r_initial = r_only["cycles"][0]
        normalized = multi_initial["DWR"]["tolerance_normalized_R_T"]
        r_goal = multi_initial["DWR"]["goals"]["R_total"]
        self.assertEqual(
            normalized["marked_canonical_cell_ids"],
            r_goal["marked_canonical_cell_ids"],
        )
        self.assertEqual(
            normalized["marked_geometry_sha256"],
            r_goal["marked_geometry_sha256"],
        )
        self.assertEqual(
            multi_initial["marker"]["marked_geometry_sha256"],
            r_initial["marker"]["marked_geometry_sha256"],
        )
        self.assertEqual(
            multi["cycles"][1]["mesh_audit"]["partition_independent_mesh_sha256"],
            r_only["cycles"][1]["mesh_audit"][
                "partition_independent_mesh_sha256"
            ],
        )
        differences = [
            multi["cycles"][1]["enriched"][name]
            - r_only["cycles"][1]["enriched"][name]
            for name in REFERENCE
        ]
        self.assertLess(math.sqrt(sum(value**2 for value in differences)), 1.0e-12)

    def test_post_refinement_markers_differentiate_without_second_h_cycle(self) -> None:
        record = json.loads(MULTI_GOAL.read_text(encoding="utf-8"))
        final_dwr = record["cycles"][1]["DWR"]
        normalized = set(
            final_dwr["tolerance_normalized_R_T"]["marked_canonical_cell_ids"]
        )
        r_only = set(final_dwr["goals"]["R_total"]["marked_canonical_cell_ids"])
        self.assertEqual((len(normalized), len(r_only)), (655, 687))
        self.assertEqual((len(normalized & r_only), len(normalized | r_only)), (517, 825))
        self.assertEqual(record["marked_cycles_completed"], 1)

    def test_vector_gate_passes_but_strict_r_gate_remains_negative(self) -> None:
        record = json.loads(MULTI_GOAL.read_text(encoding="utf-8"))
        final = record["cycles"][1]["enriched"]
        errors = {
            name: float(final[name]) - REFERENCE[name] for name in REFERENCE
        }
        control_errors = {
            name: CONTROL[name] - REFERENCE[name] for name in REFERENCE
        }
        vector_error = math.sqrt(sum(value**2 for value in errors.values()))
        control_vector_error = math.sqrt(
            sum(value**2 for value in control_errors.values())
        )
        self.assertLessEqual(vector_error, control_vector_error)
        self.assertGreater(
            abs(errors["R_total"]),
            abs(control_errors["R_total"]),
        )
        self.assertEqual(final["num_nedelec_dofs"], 129005)


if __name__ == "__main__":
    unittest.main()
