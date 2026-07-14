from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
TASK = DOCS / "task031_compact_physical_slab_memory_optimization"
OUTCOMES = TASK / "outcomes"
CASE = ROOT / "benchmarks" / "cases" / "070_compact_physical_slab_memory_optimization"


class Task031ContractTests(unittest.TestCase):
    def test_task_book_is_present_and_outcomes_are_complete(self) -> None:
        self.assertTrue((TASK / "task.md").is_file())
        self.assertTrue((TASK / "review_report_v1.md").is_file())
        self.assertTrue((TASK / "response_v1.md").is_file())
        required = (
            "README.md",
            "summary.md",
            "run_log.txt",
            "test_summary.md",
            "environment.json",
            "memory_breakdown.csv",
            "krylov_comparison.csv",
            "krylov_comparison.md",
            "matrix_free_validation.md",
            "factor_dedup.md",
            "overlap_funnel.csv",
            "overlap_funnel.md",
            "selective_solver_funnel.csv",
            "selective_solver_funnel.md",
            "h2_memory_prediction.md",
            "h2_launch_decision.md",
            "negative_results.md",
            "merge_recommendation.md",
            "next_decision.md",
            "changed_files.md",
        )
        for name in required:
            with self.subTest(name=name):
                self.assertTrue((OUTCOMES / name).is_file())

    def test_summary_and_progress_use_retrospective_contract(self) -> None:
        summary = (OUTCOMES / "summary.md").read_text(encoding="utf-8")
        for value in (
            "strong_memory_success_slow_but_memory_efficient",
            "ordinary_default_changed = false",
            "任务目标与非目标",
            "基线、冻结配置和环境",
            "实验/运行矩阵",
            "关键结果表",
            "根因解释",
            "失败、负结果与未运行项",
            "最终合并建议",
            "下一步决定",
            "证据索引",
        ):
            with self.subTest(value=value):
                self.assertIn(value, summary)

        progress = (DOCS / "development_progress.md").read_text(encoding="utf-8")
        match = re.search(
            r"^# 44\. Task031：compact physical-slab 内存优先结构优化\s*$"
            r"(?P<section>.*?)^# 45\.",
            progress,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        section = "" if match is None else match.group("section")
        self.assertGreater(len(section), 5000)
        for value in (
            "为什么启动",
            "冻结问题与 baseline",
            "采用的方法",
            "实验漏斗与负结果",
            "h5/h3/h2 正式结果",
            "h2 预测与条件解锁",
            "结果解释",
            "最终决策与合并边界",
            "局限与下一步因果关系",
            "证据入口",
        ):
            with self.subTest(value=value):
                self.assertIn(value, section)

    def test_case070_records_are_parseable_and_frozen(self) -> None:
        required = (
            "config.json",
            "expected.json",
            "expected/gates.json",
            "records/baseline_h5.json",
            "records/baseline_h3.json",
            "records/baseline_h2.json",
            "records/object_lifecycle.json",
            "records/pc_linearity.json",
            "records/candidate_screen.json",
            "records/memory_components.json",
            "records/h2_prediction.json",
            "records/best_h5.json",
            "records/best_h3.json",
            "records/best_h2.json",
        )
        for relative in required:
            with self.subTest(relative=relative):
                payload = json.loads((CASE / relative).read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)

        config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["ordinary_default_changed"])
        self.assertEqual(config["solver"]["n_aux"], 80)
        self.assertEqual(config["solver"]["ksp_type"], "fgmres")
        self.assertTrue(config["solver"]["matrix_free_fine"])
        self.assertTrue(config["solver"]["compact_lifecycle"])

    def test_clean_best_records_pass_core_numeric_and_memory_contract(self) -> None:
        expected = {
            "h5": (44698, 1.619598388671875),
            "h3": (198438, 3.474346160888672),
            "h2": (615108, 7.897674560546875),
        }
        for label, (n_fe, peak) in expected.items():
            record = json.loads(
                (CASE / "records" / f"best_{label}.json").read_text(
                    encoding="utf-8"
                )
            )
            with self.subTest(label=label):
                self.assertEqual(record["n_fe"], n_fe)
                self.assertEqual(record["n_aux"], 80)
                self.assertEqual(record["ksp_type"], "fgmres")
                self.assertGreater(record["ksp_reason"], 0)
                self.assertLessEqual(record["reported_relative_residual"], 1.0e-6)
                self.assertLessEqual(record["condensed_true_residual"], 1.0e-6)
                self.assertLessEqual(record["full_augmented_true_residual"], 1.0e-6)
                self.assertLessEqual(record["fine_action_relative_error"], 1.0e-11)
                self.assertAlmostEqual(record["simultaneous_worker_peak_gib"], peak)
                self.assertEqual(record["swap_in_delta_pages"], 0)
                self.assertEqual(record["swap_out_delta_pages"], 0)
                self.assertFalse(record["ordinary_default_changed"])
                self.assertTrue(record["matrix_free_fine"])
                self.assertFalse(record["fine_matrix_present_during_solve"])
                metadata = record["metadata"]
                self.assertFalse(metadata["tracked_source_dirty"])
                self.assertEqual(metadata["commit_sha"], metadata["verified_clean_sha"])
                self.assertRegex(metadata["source_artifact_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(metadata["memory_sampler_sha256"], r"^[0-9a-f]{64}$")

    def test_h2_prediction_and_classification(self) -> None:
        prediction = json.loads(
            (CASE / "records" / "h2_prediction.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(prediction["affine_dof_central_gib"], 8.8)
        self.assertLessEqual(prediction["task030_ratio_transfer_central_gib"], 8.8)
        self.assertLessEqual(prediction["conservative_upper_gib"], 10.0)
        self.assertTrue(prediction["launch_allowed"])
        h2 = json.loads(
            (CASE / "records" / "best_h2.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(h2["simultaneous_worker_peak_gib"], 8.0)
        self.assertEqual(
            h2["classification"],
            "strong_memory_success_slow_but_memory_efficient",
        )

    def test_csv_and_repository_indexes_include_case070(self) -> None:
        for name in (
            "memory_breakdown.csv",
            "krylov_comparison.csv",
            "overlap_funnel.csv",
            "selective_solver_funnel.csv",
        ):
            with self.subTest(name=name):
                with (OUTCOMES / name).open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(rows)

        self.assertIn(
            "070_compact_physical_slab_memory_optimization",
            (CASE.parent / "README.md").read_text(encoding="utf-8"),
        )
        self.assertIn("Task031", (DOCS / "README.md").read_text(encoding="utf-8"))
        manifest = (ROOT / "benchmarks" / "benchmark_manifest.csv").read_text(
            encoding="utf-8"
        )
        for benchmark_id in (
            "task031_compact_h5",
            "task031_compact_h3",
            "task031_compact_h2",
        ):
            self.assertIn(benchmark_id, manifest)

    def test_task031_features_remain_explicit_opt_in(self) -> None:
        runner = (ROOT / "benchmarks" / "run_workstation_iterative.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('parser.add_argument("--matrix-free-fine", action="store_true")', runner)
        self.assertIn('parser.add_argument("--compact-lifecycle", action="store_true")', runner)
        self.assertIn("matrix_free_fine=True, expected False", runner)
        self.assertIn("compact_lifecycle=True, expected False", runner)
        self.assertIn('os.environ.get("TASK031_IMAGE_DIGEST", "unknown")', runner)

    def test_iterative_port_document_separates_interface_and_qualification(self) -> None:
        ports = (DOCS / "iterative_solver_ports.md").read_text(encoding="utf-8")
        for value in (
            "argparse port exists != solver is currently usable",
            "Task27 canonical workstation profile",
            "compact_physical_slab_low_memory_experimental_opt_in",
            "task031_matrix_free_compact_physical_slab_opt_in",
            "port_implemented_but_incompatible_with_current_adaptive_pc",
            "interface_exposed_not_target_qualified",
            "linear_research_port_numeric_negative",
            "assembled-F-free public MPC form-action path",
            "8.0–8.2 GiB",
            "1–10° grazing + S/P",
        ):
            with self.subTest(value=value):
                self.assertIn(value, ports)
        for flag in (
            "--matrix-free-fine",
            "--compact-lifecycle",
            "--certify-pc",
            "--subdomain-local-shift",
            "--factor-only-storage",
            "--post-smooth",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, ports)
        linked_docs = (
            DOCS / "README.md",
            DOCS / "solver_guide.md",
            DOCS / "capability_matrix.md",
            ROOT / "notes" / "quick_start" / "40_3d_workstation_iterative.md",
        )
        for path in linked_docs:
            with self.subTest(path=path.name):
                self.assertIn(
                    "iterative_solver_ports.md", path.read_text(encoding="utf-8")
                )

    def test_task031_wrapper_certifies_non_fgmres_but_not_flexible_default(self) -> None:
        wrapper = (
            ROOT / "benchmarks" / "run_task031_memory_forensics.py"
        ).read_text(encoding="utf-8")
        worker = (ROOT / "benchmarks" / "run_workstation_iterative.py").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            wrapper,
            r'"--certify-pc",\s+action=argparse\.BooleanOptionalAction,\s+'
            r'default=False',
        )
        self.assertIn('args.ksp_type != "fgmres"', worker)
        self.assertIn("fixed-PC linearity gate failed", worker)
        for label in ("h5", "h3", "h2"):
            record = json.loads(
                (CASE / "records" / f"best_{label}.json").read_text(
                    encoding="utf-8"
                )
            )
            with self.subTest(label=label):
                self.assertNotIn("--certify-pc", record["metadata"]["command"])

    def test_review_v1_hardening_terms_are_synchronized(self) -> None:
        summary = (OUTCOMES / "summary.md").read_text(encoding="utf-8")
        response = (TASK / "response_v1.md").read_text(encoding="utf-8")
        case = (CASE / "README.md").read_text(encoding="utf-8")
        for text in (summary, response, case):
            self.assertIn("external simultaneous", text)
            self.assertIn("legacy internal", text)
            self.assertIn("8.0–8.2 GiB", text)
        self.assertIn("release_f()", response)
        self.assertIn("4.74x", response)
        self.assertIn("origin/master", response)
        self.assertIn("project_service_requirements_phase1_scope.md", response)


if __name__ == "__main__":
    unittest.main()
