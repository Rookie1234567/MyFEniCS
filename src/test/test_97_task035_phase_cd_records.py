from __future__ import annotations

import json
from pathlib import Path
import unittest

from benchmarks.task035_phase_cd import compare_serial_mpi2


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"


class Task035PhaseCDRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.serial = json.loads((RECORDS / "phase_cd_mpi1.json").read_text(encoding="utf-8"))
        cls.mpi2 = json.loads((RECORDS / "phase_cd_mpi2.json").read_text(encoding="utf-8"))
        cls.identity = json.loads(
            (RECORDS / "phase_cd_mpi_identity.json").read_text(encoding="utf-8")
        )

    def test_final_records_are_clean_sha_bound_and_mpi_identical(self) -> None:
        for record, size in ((self.serial, 1), (self.mpi2, 2)):
            self.assertEqual(record["mpi_size"], size)
            self.assertEqual(record["status"], "phase_cd_complete_controlled_negative")
            self.assertTrue(record["provenance"]["tracked_and_nonignored_untracked_clean_at_start"])
            self.assertEqual(
                record["provenance"]["git_head_at_run"],
                "db2d1e7a49f5754de8d0dec6dda3622a9635e6bb",
            )
        self.assertEqual(compare_serial_mpi2(self.serial, self.mpi2), self.identity)
        self.assertTrue(self.identity["pass"])

    def test_required_C_D_results_are_locked_without_promotion(self) -> None:
        self.assertEqual(
            [row["point"] for row in self.serial["phase_c"]["points"]],
            ["p2_h5", "p2_h3", "p3_h10"],
        )
        self.assertEqual(self.serial["B3_B4"]["status"], "B3_B4_pass")
        self.assertEqual(
            self.serial["phase_d"]["multi_block_conforming_hexa"]["status"],
            "hexa_backend_blocker",
        )
        self.assertEqual(
            self.serial["phase_d"]["tetra_marked_refinement_control"]["status"],
            "control_pass",
        )
        self.assertFalse(self.serial["production_estimator_selected"])
        self.assertFalse(self.serial["production_backend_selected"])
        self.assertFalse(self.serial["phase_e_unlocked"])

    def test_first_mpi2_measurement_failure_is_preserved(self) -> None:
        failure = json.loads(
            (RECORDS / "phase_cd_mpi2_initial_volume_measurement_failure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(failure["status"], "phase_cd_fail")
        tetra = failure["phase_d"]["tetra_marked_refinement_control"]
        self.assertEqual(tetra["minimum_signed_volume_proxy"], 0.0)
        self.assertEqual(tetra["status"], "controlled_negative")
        self.assertEqual(
            failure["provenance"]["git_head_at_run"],
            "a1197c9ade526df422adefe1a3b3db240fa2507a",
        )


if __name__ == "__main__":
    unittest.main()
