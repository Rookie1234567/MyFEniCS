from __future__ import annotations

import csv
import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]

CORE_QUICK_START = (
    "00_environment_and_pycharm.md",
    "01_main_py_parameter_map.md",
    "02_results_and_paraview.md",
    "10_2d_pml_floquet.md",
    "11_2d_dtn_floquet.md",
    "12_2d_te_tm_and_complex_material.md",
    "13_2d_diffraction_and_rta_methods.md",
    "20_3d_stage1_airbox.md",
    "21_3d_stage2a_floquet.md",
    "22_3d_stage2b_pml.md",
    "23_3d_stage2c_fresnel.md",
    "30_3d_stage4a_flat_layer.md",
    "31_3d_stage4b_grating_direct.md",
    "32_3d_direct_ooc_blr.md",
    "40_3d_workstation_iterative.md",
)

CORE_WALKTHROUGH = (
    "01_main_and_runner_dispatch.md",
    "11_2d_floquet_pml_port_forms.md",
    "12_2d_dtn_and_rta_postprocess.md",
    "20_3d_staged_architecture.md",
    "21_3d_floquet_and_pml.md",
    "22_3d_dtn_augmented_system.md",
    "23_3d_rta_and_field_reconstruction.md",
    "30_direct_solver_profiles.md",
    "31_exact_condensation.md",
    "32_physical_slab_two_level_pc.md",
    "33_workstation_fgmres_runtime.md",
)

QUALIFIED_OR_FROZEN_CASES = {
    "001_2d_tm_pml_floquet",
    "002_2d_tm_dtn_equivalence",
    "003_2d_te_tm_complex_absorption",
    "010_3d_stage1_airbox",
    "011_3d_stage2a_floquet",
    "012_3d_stage2b_pml",
    "013_3d_stage2c_fresnel",
    "020_3d_stage4a_flat_dtn",
    "021_3d_stage4b_direct",
    "022_dtn_condensation_equivalence",
    "030_mumps_ooc_blr",
    "031_workstation_iterative",
    "040_mpi_p_algebra_regression",
    "050_stage4_direct_memory_forensics",
    "060_multilevel_hcurl_iterative_solver",
    "070_compact_physical_slab_memory_optimization",
    "080_hybrid_fem_modal_direct_baseline",
    "090_high_order_3d_floquet_hcurl",
    "091_hybrid_hp_adaptivity_feasibility",
    "092_workstation_wsl_adaptive_scalability",
    "093_fixed_geometry_ph_convergence_mpi",
}
STAGING_OR_IN_PROGRESS_CASES: set[str] = set()
ACTIVE_RESEARCH_CASES = {
    "094_hcurl_goal_oriented_adaptivity",
    "095_high_order_local_hp_resource_envelope",
    "096_hybrid_channel_memory_closure",
}
SURROGATE_TASK_CASES = {
    "110_surrogate_two_parameter_pilot",
    "111_task001_illumination_robustness",
    "112_s_continuous_illumination_multifidelity_surrogate",
    "113_task002_m2a_low_grazing_diagnostics",
    "114_task002_solver_domain_robustness",
    "115_task002_full3d_hierarchy_qualification",
    "116_task002_single_fidelity_design",
}

RECORDED_CASES = {
    "002_2d_tm_dtn_equivalence": (
        "records/explicit.json",
        "records/auxiliary.json",
        "records/comparison.json",
    ),
    "003_2d_te_tm_complex_absorption": (
        "records/tm_complex_absorption.json",
        "records/te_complex_absorption.json",
    ),
    "010_3d_stage1_airbox": ("records/canonical_reference.json",),
    "021_3d_stage4b_direct": (
        "records/h5_reference.json",
        "records/h3_reference.json",
        "records/h2_reviewed_reference.json",
    ),
    "031_workstation_iterative": (
        "records/h5_reference.json",
        "records/h3_reference.json",
        "records/h2_reference.json",
    ),
    "060_multilevel_hcurl_iterative_solver": (
        "records/h5_baseline.json",
        "records/hierarchy_contract.json",
        "records/transfer_contract.json",
        "records/candidate_screen_summary.json",
        "records/best_h5.json",
        "records/best_h3.json",
        "records/best_h2.json",
    ),
    "070_compact_physical_slab_memory_optimization": (
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
    ),
    "080_hybrid_fem_modal_direct_baseline": (
        "records/full3d_h5_reference.json",
        "records/full3d_h3_reference.json",
        "records/hybrid_phase6_m6.json",
        "records/qep_phase2.json",
        "records/modes_phase3.json",
        "records/propagation_phase4.json",
        "records/trace_phase5.json",
        "records/hybrid_h5_m120.json",
        "records/hybrid_h5_m160.json",
        "records/hybrid_h3_m120.json",
        "records/hybrid_h3_m160.json",
        "records/hybrid_h5_funnel.json",
        "records/hybrid_h3_funnel.json",
        "records/parameter_smoke.json",
        "records/memory_h5_augmented.json",
        "records/memory_h5_schur_fast.json",
        "records/memory_h5_schur_minimal.json",
        "records/memory_h3_augmented.json",
        "records/memory_h3_schur_fast.json",
        "records/memory_h3_schur_minimal.json",
        "records/h2_prediction.json",
    ),
    "091_hybrid_hp_adaptivity_feasibility": (
        "records/resource_matrix.json",
        "records/resource_matrix.csv",
    ),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load(path: Path) -> dict:
    return json.loads(_read(path))


class DocumentationContractTests(unittest.TestCase):
    def test_task032_summary_is_table_first_and_traceable(self):
        root = ROOT / "docs" / "task032_hybrid_fem_modal_direct_baseline"
        text = _read(root / "outcomes" / "summary.md")
        table_separators = re.findall(
            r"^\|(?:\s*:?-{3,}:?\s*\|)+$", text, flags=re.MULTILINE
        )
        self.assertGreaterEqual(len(table_separators), 8)
        for heading in (
            "最终状态与适用范围",
            "Phase 0–10 实施矩阵",
            "QEP 与 mode validation",
            "direct path 内存与时间",
            "h2 决策",
            "负结果与停止边界",
            "选择性合并决定",
            "下一步与硬 Gate",
        ):
            self.assertIn(heading, text)
        for identity in ("measured", "derived", "predicted", "not_run"):
            self.assertIn(identity, text)
        for value in ("3.2244 GiB", "M160", "302/302", "not_run_by_gate"):
            self.assertIn(value, text)

    def test_task032_review_closeout_artifacts_are_machine_readable(self):
        root = (
            ROOT
            / "docs"
            / "task032_hybrid_fem_modal_direct_baseline"
            / "outcomes"
        )
        projection = _load(root / "task032_0p7nm_projection.json")
        self.assertEqual(
            projection["record_type"], "analytical_resource_projection"
        )
        self.assertFalse(projection["identity"]["is_pde_run"])
        self.assertFalse(projection["identity"]["is_solver_pass"])
        self.assertNotIn("status", projection)
        for name in (
            "selective_merge_manifest.csv",
            "compact_record_size_inventory.csv",
        ):
            with (root / name).open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertGreater(len(rows), 0, name)
            self.assertTrue(all(None not in row for row in rows), name)

    def test_required_document_layers_exist(self):
        required = (
            "notes/quick_start/README.md",
            "notes/theory/README.md",
            "notes/theory/maxwell_strong_weak_and_fem.md",
            "notes/theory/dtn_modal_ports_and_condensation.md",
            "notes/theory/official_and_diagnostic_rta_methods.md",
            "notes/theory/iterative_solver_and_preconditioner.md",
            "notes/reference/code_walkthrough.md",
            "notes/reference/code_walkthrough/00_repository_architecture.md",
            "notes/reference/code_walkthrough/50_tests_and_benchmark_contract.md",
            "benchmarks/cases/README.md",
            "docs/iterative_solver_ports.md",
            "docs/project_service_requirements_and_forward_model_roadmap.md",
            "docs/project_service_requirements_phase1_scope.md",
        )
        required += tuple(f"notes/quick_start/{name}" for name in CORE_QUICK_START)
        required += tuple(
            f"notes/reference/code_walkthrough/{name}" for name in CORE_WALKTHROUGH
        )
        missing = [name for name in required if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_quick_start_files_are_followable_tutorials(self):
        root = ROOT / "notes" / "quick_start"
        for name in CORE_QUICK_START:
            text = _read(root / name)
            numbered = re.findall(r"^##\s+\d+\.", text, flags=re.MULTILINE)
            with self.subTest(name=name):
                self.assertGreaterEqual(len(text.splitlines()), 100)
                self.assertEqual(len(numbered), 16)
                tutorial_groups = (
                    ("PyCharm",),
                    ("参数",),
                    ("CLI",),
                    ("调用链", "代码路径", "入口"),
                    ("输出", "JSON"),
                    ("Gate",),
                    ("常见错误",),
                    ("链接", "延伸阅读"),
                )
                for choices in tutorial_groups:
                    self.assertTrue(
                        any(choice in text for choice in choices),
                        f"{name} missing one of {choices}",
                    )

    def test_core_walkthroughs_have_source_level_depth(self):
        root = ROOT / "notes" / "reference" / "code_walkthrough"
        concept_groups = (
            ("签名", "入口", "关键函数", "关键类"),
            ("调用顺序", "调用链", "pipeline", "追踪"),
            ("ownership", "所有权", "生命周期", "PETSc/MPI"),
            ("shape", "规模", "尺寸", "DoF", "rows"),
            ("公式", "弱式", "方程", "数学", "$$", "```math"),
            ("测试", "benchmark", "Case"),
            ("限制",),
            ("official", "身份"),
        )
        for name in CORE_WALKTHROUGH:
            text = _read(root / name)
            with self.subTest(name=name):
                self.assertGreaterEqual(len(text.splitlines()), 100)
                for choices in concept_groups:
                    self.assertTrue(
                        any(choice in text for choice in choices),
                        f"{name} missing one of {choices}",
                    )

    def test_numbered_benchmark_cases_use_case_contained_contracts(self):
        cases_root = ROOT / "benchmarks" / "cases"
        observed = {path.name for path in cases_root.iterdir() if path.is_dir()}
        self.assertEqual(
            observed,
            QUALIFIED_OR_FROZEN_CASES
            | STAGING_OR_IN_PROGRESS_CASES
            | ACTIVE_RESEARCH_CASES
            | SURROGATE_TASK_CASES,
        )
        required_sections = (
            "## 物理问题",
            "## 参数说明",
            "## PyCharm",
            "## CLI 或测试",
            "## 代码路径与理论",
            "## 当前证据",
            "## 结果解释",
            "## 限制",
        )
        for case in sorted(QUALIFIED_OR_FROZEN_CASES):
            folder = cases_root / case
            text = _read(folder / "README.md")
            expected = _load(folder / "expected.json")
            with self.subTest(case=case):
                self.assertGreaterEqual(len(text.splitlines()), 60)
                for number in range(1, 23):
                    self.assertIn(f"| {number}.", text)
                for section in required_sections:
                    self.assertIn(section, text)
                self.assertIsInstance(expected.get("status"), str)
                self.assertTrue(expected["status"])

        staging_identity = {
            "status": "phase_a_in_progress",
            "canonical": False,
            "production_qualified": False,
            "pde_run": False,
            "phase_b_or_later_results": "not_available",
        }
        for case in sorted(STAGING_OR_IN_PROGRESS_CASES):
            folder = cases_root / case
            with self.subTest(case=case):
                for name in (
                    "README.md",
                    "config.json",
                    "expected.json",
                    "test_command.txt",
                    "records/base_manifest.json",
                ):
                    self.assertTrue((folder / name).is_file(), name)
                config = _load(folder / "config.json")
                expected = _load(folder / "expected.json")
                for key, value in staging_identity.items():
                    self.assertEqual(config.get(key), value, key)
                    self.assertEqual(expected.get(key), value, key)
                readme = _read(folder / "README.md")
                self.assertIn("## 升级条件", readme)
                self.assertIn("staging", readme)
                command = _read(folder / "test_command.txt").strip()
                self.assertEqual(
                    command,
                    "python -m benchmarks.task035_case094",
                )
                self.assertNotIn("mpiexec", command)
                self.assertNotIn("run_3d", command)

        for case in sorted(ACTIVE_RESEARCH_CASES):
            folder = cases_root / case
            with self.subTest(case=case):
                for name in (
                    "README.md",
                    "config.json",
                    "test_command.txt",
                    "records",
                ):
                    self.assertTrue((folder / name).exists(), name)
                config = _load(folder / "config.json")
                self.assertFalse(config["ordinary_default_changed"])
                if case.startswith("094_"):
                    self.assertTrue(
                        (folder / "expected.json").is_file(),
                        "expected.json",
                    )
                    self.assertEqual(
                        config["status"],
                        (
                            "accepted_research_infrastructure_with_"
                            "controlled_negatives"
                        ),
                    )
                    self.assertFalse(config["canonical"])
                    self.assertFalse(config["production_qualified"])
                    self.assertTrue(config["pde_run"])
                    self.assertIn(
                        "true_discrete_adjoint_and_DWR",
                        config["accepted_capabilities"],
                    )
                    self.assertIn(
                        "automatic_production_hp",
                        config["not_promoted"],
                    )
                elif case.startswith("095_"):
                    self.assertEqual(config["geometry_scope"], "fixed_only")
                    self.assertEqual(config["degrees"], [4, 5, 6])
                    self.assertEqual(config["mpi_size"], 8)
                    irregular = config["irregular_geometry"]
                    self.assertEqual(
                        irregular["status"],
                        "out_of_scope_by_user",
                    )
                    self.assertFalse(irregular["run"])
                    self.assertFalse(irregular["completion_gate"])
                else:
                    self.assertTrue(case.startswith("096_"), case)
                    self.assertEqual(config["geometry_scope"], "fixed_only")
                    self.assertEqual(config["degrees"], [2, 6])
                    self.assertEqual(config["mpi_size"], 8)
                    self.assertEqual(
                        config["formal_model"],
                        {
                            "degree": 6,
                            "h_nm": 10.0,
                            "mpi_size": 8,
                            "hybrid_modes_per_direction": [120, 160],
                        },
                    )
                    self.assertEqual(
                        config["out_of_scope"]["p3_h7p5"],
                        "out_of_scope_by_user_not_run_not_completion_gate",
                    )
                    irregular = config["irregular_geometry"]
                    self.assertEqual(
                        irregular["status"],
                        "out_of_scope_by_user",
                    )
                    self.assertFalse(irregular["run"])
                    self.assertFalse(irregular["completion_gate"])
                records = sorted((folder / "records").glob("*.json"))
                self.assertGreaterEqual(len(records), 2)
                readme = _read(folder / "README.md")
                if case.startswith("095_"):
                    self.assertIn(
                        "fixed rectangular block grating",
                        readme,
                    )
                self.assertIn("MPI8", readme)

        for case in sorted(SURROGATE_TASK_CASES):
            folder = cases_root / case
            with self.subTest(case=case):
                for name in (
                    "README.md",
                    "config.json",
                    "expected.json",
                    "test_command.txt",
                    "records",
                ):
                    self.assertTrue((folder / name).exists(), name)

    def test_recorded_and_test_backed_case_files_are_explicit(self):
        cases_root = ROOT / "benchmarks" / "cases"
        for case, record_names in RECORDED_CASES.items():
            folder = cases_root / case
            with self.subTest(case=case):
                for name in ("README.md", "config.json", "expected.json"):
                    self.assertTrue((folder / name).is_file(), name)
                if case == "091_hybrid_hp_adaptivity_feasibility":
                    self.assertTrue(
                        (
                            ROOT
                            / "benchmarks"
                            / "run_task033_reduced_scope_completion.py"
                        ).is_file()
                    )
                else:
                    self.assertTrue((folder / "run.sh").is_file(), "run.sh")
                for name in record_names:
                    self.assertTrue((folder / name).is_file(), name)

        for case in (
            "001_2d_tm_pml_floquet",
            "011_3d_stage2a_floquet",
            "012_3d_stage2b_pml",
            "013_3d_stage2c_fresnel",
            "020_3d_stage4a_flat_dtn",
        ):
            folder = cases_root / case
            with self.subTest(case=case):
                for name in ("README.md", "config.json", "expected.json", "run.sh"):
                    self.assertTrue((folder / name).is_file(), name)
                expected = _load(folder / "expected.json")
                self.assertNotIn(
                    expected["status"], {"canonical_target", "qualified_target_profile"}
                )

        for case in (
            "022_dtn_condensation_equivalence",
            "040_mpi_p_algebra_regression",
            "090_high_order_3d_floquet_hcurl",
        ):
            folder = cases_root / case
            with self.subTest(case=case):
                for name in (
                    "README.md",
                    "fixture.json",
                    "expected.json",
                    "test_command.txt",
                ):
                    self.assertTrue((folder / name).is_file(), name)
        self.assertTrue(
            (
                cases_root
                / "090_high_order_3d_floquet_hcurl"
                / "records"
                / "analytic_oracles.json"
            ).is_file()
        )
        folder = cases_root / "030_mumps_ooc_blr"
        for name in ("README.md", "config.json", "expected.json", "test_command.txt"):
            self.assertTrue((folder / name).is_file(), name)

        folder = cases_root / "050_stage4_direct_memory_forensics"
        for name in (
            "README.md",
            "config.json",
            "expected.json",
            "run_h5.sh",
            "run_h3.sh",
            "run_h2_guarded.sh",
            "records/README.md",
        ):
            self.assertTrue((folder / name).is_file(), name)

    def test_case002_full_solve_equivalence_record(self):
        root = ROOT / "benchmarks" / "cases" / "002_2d_tm_dtn_equivalence"
        comparison = _load(root / "records" / "comparison.json")
        expected = _load(root / "expected.json")
        self.assertEqual(comparison["status"], "pass")
        self.assertLessEqual(
            comparison["field_relative_difference"],
            expected["field_relative_difference_max"],
        )
        self.assertLessEqual(
            max(abs(value) for value in comparison["absolute_differences"].values()),
            expected["rta_absolute_difference_max"],
        )
        for formulation in ("explicit", "auxiliary"):
            result = comparison[formulation]
            self.assertLessEqual(
                result["linear_true_residual"], expected["linear_residual_max"]
            )
            self.assertIn("matrix_rows", result)
            self.assertIn("matrix_nnz", result)
            self.assertIn("official_rta", result)
        self.assertEqual(comparison["explicit"]["auxiliary_dofs"], 0)
        self.assertGreater(comparison["auxiliary"]["auxiliary_dofs"], 0)

    def test_case003_lossy_records_keep_probe_diagnostic(self):
        root = ROOT / "benchmarks" / "cases" / "003_2d_te_tm_complex_absorption"
        expected = _load(root / "expected.json")
        tolerance = expected["tolerances"]
        for name in ("tm_complex_absorption.json", "te_complex_absorption.json"):
            record = _load(root / "records" / name)
            official = record["official_rta"]
            with self.subTest(name=name):
                for key in (
                    "benchmark_id",
                    "case_id",
                    "polarization",
                    "physical_model",
                    "resolved_config",
                    "metadata",
                    "mesh",
                    "matrix",
                    "solver",
                    "official_rta",
                    "elapsed_seconds",
                    "process_peak_rss_mb_after_run",
                    "artifact_provenance",
                ):
                    self.assertIn(key, record)
                self.assertLessEqual(
                    record["solver"]["linear_true_residual"],
                    tolerance["linear_residual_max"],
                )
                self.assertLessEqual(
                    abs(official["energy_closure_error"]),
                    tolerance["energy_closure_abs_max"],
                )
                self.assertLessEqual(
                    abs(official["A_balance"] - official["A_volume"]),
                    tolerance["absorption_balance_difference_max"],
                )
                for key in expected["nonnegative_quantities"]:
                    self.assertGreaterEqual(official[key], 0.0)
                self.assertEqual(
                    record["diagnostic_probe"]["identity"], "diagnostic_only"
                )
                self.assertTrue(record["diagnostic_probe"]["must_not_replace_official"])

    def test_known_walkthrough_errors_do_not_regress(self):
        root = ROOT / "notes" / "reference" / "code_walkthrough"
        condensation = _read(root / "31_exact_condensation.md")
        two_level = _read(root / "32_physical_slab_two_level_pc.md")
        theory = _read(
            ROOT / "notes" / "theory" / "dtn_modal_ports_and_condensation.md"
        )
        self.assertNotIn("SparseCoarseVector(indices, values, global_size)", two_level)
        self.assertLess(
            two_level.index("smoother.solve(source"),
            two_level.index("rhs_c = Z^H residual"),
        )
        for text in (condensation, theory):
            self.assertIn("np.linalg.inv", text)
            self.assertIn("H=I", text)
            self.assertIn("NotImplementedError", text)

    def test_demo_target_names_and_pycharm_mpi4_are_unambiguous(self):
        roots = (
            ROOT / "src" / "main.py",
            ROOT / "notes" / "quick_start",
            ROOT / "notes" / "reference" / "code_walkthrough",
            ROOT / "benchmarks" / "cases",
        )
        texts: list[str] = []
        for root in roots:
            if root.is_file():
                texts.append(_read(root))
            else:
                texts.extend(_read(path) for path in root.rglob("*.md"))
        combined = "\n".join(texts)
        for ambiguous in (
            "3d_stage4b_grating_direct_h5",
            "3d_stage4b_grating_direct_h3",
            "3d_stage4b_grating_mumps_ooc",
            "3d_stage4b_grating_mumps_blr",
        ):
            self.assertNotIn(ambiguous, combined)
        self.assertIn("3d_target_grating_direct_h5", combined)
        mpi_tutorial = _read(
            ROOT / "notes" / "quick_start" / "40_3d_workstation_iterative.md"
        )
        case031 = _read(
            ROOT / "benchmarks" / "cases" / "031_workstation_iterative" / "README.md"
        )
        for text in (mpi_tutorial, case031):
            self.assertIn("External Tool", text)
            self.assertIn("mpiexec -n 4", text)
            self.assertIn("candidate", text)

    def test_local_links_in_documentation_layers_resolve(self):
        roots = (
            ROOT / "notes" / "quick_start",
            ROOT / "notes" / "theory",
            ROOT / "notes" / "reference" / "code_walkthrough",
            ROOT / "benchmarks" / "cases",
        )
        markdown = [ROOT / "notes" / "reference" / "code_walkthrough.md"]
        markdown.extend(
            ROOT / "docs" / name
            for name in (
                "README.md",
                "solver_guide.md",
                "capability_matrix.md",
                "benchmark.md",
                "iterative_solver_ports.md",
            )
        )
        for folder in roots:
            markdown.extend(folder.rglob("*.md"))
        broken: list[str] = []
        for source in markdown:
            for raw in re.findall(r"\]\(([^)]+)\)", _read(source)):
                target = raw.split("#", 1)[0].strip().strip("<>")
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (source.parent / unquote(target)).resolve()
                if not resolved.exists():
                    broken.append(f"{source.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_task035_planning_markdown_contract(self):
        theory = ROOT / "notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md"
        text = _read(theory)
        self.assertIn(r"\nabla\times", text)
        self.assertNotIn("\nabla\times", text.replace(r"\nabla\times", ""))
        self.assertEqual(text.count("$$") % 2, 0)
        self.assertIn("https://doi.org/", text)
        index = _read(ROOT / "notes/theory/README.md")
        self.assertIn(theory.name, index)
        self.assertTrue((ROOT / "docs/task035_hcurl_goal_oriented_adaptivity/task.md").is_file())

    def test_capability_status_does_not_overstate_stage2(self):
        text = _read(ROOT / "docs" / "capability_matrix.md")
        self.assertRegex(text, r"Stage2B PML \| experimental")
        self.assertRegex(text, r"Stage2C Fresnel \| experimental")


if __name__ == "__main__":
    unittest.main()
