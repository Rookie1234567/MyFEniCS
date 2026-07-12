from __future__ import annotations

import json
from pathlib import Path
import unittest

from benchmarks.check_benchmarks import evaluate


ROOT = Path(__file__).resolve().parents[2]


class BenchmarkContractTests(unittest.TestCase):
    def test_canonical_records_pass_automatic_gates(self) -> None:
        gates, summaries = evaluate()
        failed = [gate.name for gate in gates if not gate.passed]
        self.assertFalse(failed, failed)
        self.assertGreaterEqual(len(summaries), 8)

    def test_config_is_single_source_for_qualified_profile(self) -> None:
        config = json.loads(
            (ROOT / "benchmarks/configs/workstation_p2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(config["artifact_root"], "benchmarks/artifacts")
        self.assertEqual(config["qualified_h_nm"], [5.0, 3.0, 2.0])
        runner = (ROOT / "benchmarks/run_workstation_iterative.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('parser.add_argument("--config"', runner)
        self.assertIn('config["artifact_root"]', runner)

    def test_level_scripts_match_manifest_resource_policy(self) -> None:
        level1 = (ROOT / "benchmarks/scripts/run_level1.sh").read_text(encoding="utf-8")
        direct = (ROOT / "benchmarks/scripts/run_level3_direct.sh").read_text(
            encoding="utf-8"
        )
        iterative = (ROOT / "benchmarks/scripts/run_level3_iterative.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("unittest discover", level1)
        self.assertIn("--constraint-backend manual", level1)
        self.assertIn("--stage-case stage1_airbox", level1)
        self.assertIn("--include-resource-heavy-h2", direct)
        self.assertIn("for h in 5 3", direct)
        self.assertIn("for h in 5 3 2", iterative)
        self.assertIn("benchmarks/artifacts", direct)
        self.assertIn("benchmarks/artifacts", iterative)

    def test_ordinary_output_root_default_remains_results(self) -> None:
        for relative in ("src/runners/run_cases.py", "src/runners/run_3d_cases.py"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("default=None", text)
            self.assertIn('root / "results"', text)
            self.assertIn('"--results-root"', text)


if __name__ == "__main__":
    unittest.main()
