from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "docs" / "para_task001_neural_local_pc_acceleration"
CASE = ROOT / "benchmarks" / "cases" / "090_neural_local_pc_acceleration"


class ParaTask001ContractTests(unittest.TestCase):
    def test_required_outcomes_exist(self):
        required = {
            "summary.md",
            "experiment_matrix.csv",
            "local_action_metrics.csv",
            "runtime_breakdown.csv",
            "memory_report.md",
            "model_and_dataset_provenance.md",
            "merge_recommendation.md",
            "changed_files.md",
        }
        self.assertTrue(required.issubset({path.name for path in (TASK / "outcomes").iterdir()}))

    def test_case_status_is_numeric_pass_engineering_negative(self):
        config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
        expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))
        status = "h5_numeric_pass_engineering_negative"
        self.assertEqual(config["status"], status)
        self.assertEqual(expected["status"], status)
        self.assertTrue(expected["h5_numeric_correctness_passed"])
        self.assertFalse(expected["h5_wall_time_gate_passed"])
        self.assertFalse(expected["h3_allowed"])
        self.assertFalse(expected["h2_allowed"])
        self.assertFalse(expected["ordinary_default_changed"])

    def test_experiment_funnel_stops_after_one_slab_h5(self):
        with (TASK / "outcomes" / "experiment_matrix.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = {row["candidate"]: row for row in csv.DictReader(stream)}
        self.assertEqual(rows["h5_baseline"]["status"], "pass")
        self.assertEqual(rows["h5_one_slab"]["status"], "engineering_negative")
        self.assertEqual(rows["h5_all_slabs"]["status"], "not_run_by_gate")
        self.assertEqual(rows["h3"]["status"], "not_run_by_gate")
        self.assertEqual(rows["h2"]["status"], "not_run_by_gate")

    def test_summary_records_numeric_and_performance_evidence(self):
        summary = (TASK / "outcomes" / "summary.md").read_text(encoding="utf-8")
        for term in (
            "861",
            "854",
            "4.419",
            "2.888",
            "9.903219e-7",
            "0.0890216041/0.4425882733/0.4683901210",
            "ordinary default",
        ):
            self.assertIn(term, summary)

    def test_runtime_features_remain_explicit_opt_in(self):
        runner = (ROOT / "benchmarks" / "run_workstation_iterative.py").read_text(
            encoding="utf-8"
        )
        for flag in (
            "--neural-capture-dir",
            "--neural-checkpoint-root",
            "--neural-enabled-slabs",
            "--neural-lane",
            "--neural-residual-limit",
        ):
            self.assertIn(flag, runner)

    def test_wsl_wrapper_pins_complex_mpc(self):
        wrapper = (ROOT / "scripts" / "wsl_python_complex.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("dolfinx-mpc-0.10.1-complex-petsc3.19-v2", wrapper)
        self.assertIn("x86_64-linux-gnu-complex", wrapper)


if __name__ == "__main__":
    unittest.main()
