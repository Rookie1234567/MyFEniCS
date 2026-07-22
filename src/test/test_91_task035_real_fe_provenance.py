from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
)


class Task035RealFiniteElementProvenanceTests(unittest.TestCase):
    def test_real_records_bind_linux_abi_and_exact_fixture_sources(self) -> None:
        for filename in ("real_fe_mpi1.json", "real_fe_mpi2.json"):
            record = json.loads((RECORDS / filename).read_text(encoding="utf-8"))
            provenance = record["provenance"]
            self.assertEqual(
                provenance["python_executable"],
                "/home/Projects/MyFEniCS/.venv/bin/python",
            )
            self.assertEqual(provenance["qualified_activation"], "1")
            self.assertEqual(provenance["petsc_scalar_dtype"], "complex128")
            self.assertEqual(provenance["petsc_int_dtype"], "int32")
            self.assertEqual(len(provenance["git_head_at_run"]), 40)
            for relative, expected in provenance[
                "tracked_content_bindings"
            ].items():
                actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
