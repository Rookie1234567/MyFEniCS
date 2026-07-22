from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.validation.task035_low_cost_bakeoff import build_low_cost_bakeoff_entry


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
)


class Task035LowCostBakeoffEntryTests(unittest.TestCase):
    def test_entry_is_unlocked_but_selects_no_production_estimator(self) -> None:
        real_fe = json.loads(
            (RECORDS / "real_fe_mpi1.json").read_text(encoding="utf-8")
        )
        identity = json.loads(
            (RECORDS / "real_fe_mpi_identity.json").read_text(encoding="utf-8")
        )
        record = build_low_cost_bakeoff_entry(real_fe, identity)
        self.assertEqual(record["status"], "phase_c_low_cost_in_progress")
        self.assertTrue(record["phase_c_low_cost_unlocked"])
        self.assertFalse(record["production_estimator_selected"])
        self.assertFalse(record["heavy_p4_authorized"])
        self.assertEqual(
            record["candidate_readiness"]["R2_kh_over_p"],
            "diagnostic_only_excluded_from_marking",
        )
        self.assertTrue(
            record["initial_measured_screen"]["R1"]["indicator_decreases"]
        )
        self.assertTrue(
            record["initial_measured_screen"]["R1"]["field_error_decreases"]
        )
        self.assertTrue(
            record["initial_measured_screen"]["B1"]["fault_detection"]
        )

    def test_gate_fails_closed_without_mpi_identity(self) -> None:
        real_fe = {"status": "real_fe_fixture_minimum_pass"}
        with self.assertRaisesRegex(ValueError, "serial/MPI2"):
            build_low_cost_bakeoff_entry(
                real_fe, {"status": "serial_mpi2_identity_fail"}
            )


if __name__ == "__main__":
    unittest.main()
