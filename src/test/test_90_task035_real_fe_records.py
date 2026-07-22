from __future__ import annotations

import json
import unittest
from pathlib import Path

from benchmarks.task035_real_fe_fixtures import compare_serial_mpi2


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
)


class Task035RealFiniteElementRecordTests(unittest.TestCase):
    def test_tracked_serial_mpi2_records_are_identical(self) -> None:
        serial = json.loads(
            (RECORDS / "real_fe_mpi1.json").read_text(encoding="utf-8")
        )
        mpi2 = json.loads(
            (RECORDS / "real_fe_mpi2.json").read_text(encoding="utf-8")
        )
        identity = compare_serial_mpi2(serial, mpi2)
        self.assertTrue(identity["pass"], identity["failures"])
        self.assertEqual(identity["status"], "serial_mpi2_identity_pass")
        self.assertEqual(
            identity,
            json.loads(
                (RECORDS / "real_fe_mpi_identity.json").read_text(
                    encoding="utf-8"
                )
            ),
        )

    def test_real_fixture_records_are_explicitly_nonproduction(self) -> None:
        for filename in ("real_fe_mpi1.json", "real_fe_mpi2.json"):
            record = json.loads((RECORDS / filename).read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "real_fe_fixture_minimum_pass")
            self.assertFalse(record["canonical"])
            self.assertFalse(record["production_qualified"])
            self.assertFalse(record["target_grating_run"])
            self.assertTrue(record["b1"]["real_fe"])
            self.assertTrue(record["b2"]["real_fe"])


if __name__ == "__main__":
    unittest.main()
