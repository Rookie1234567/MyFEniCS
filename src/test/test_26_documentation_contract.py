from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]


class DocumentationContractTests(unittest.TestCase):
    def test_required_document_layers_exist(self):
        required = (
            "notes/quick_start/README.md",
            "notes/quick_start/00_environment_and_pycharm.md",
            "notes/quick_start/01_main_py_parameter_map.md",
            "notes/quick_start/40_3d_workstation_iterative.md",
            "notes/theory/README.md",
            "notes/theory/maxwell_strong_weak_and_fem.md",
            "notes/theory/dtn_modal_ports_and_condensation.md",
            "notes/theory/official_and_diagnostic_rta_methods.md",
            "notes/theory/iterative_solver_and_preconditioner.md",
            "notes/reference/code_walkthrough.md",
            "notes/reference/code_walkthrough/00_repository_architecture.md",
            "notes/reference/code_walkthrough/50_tests_and_benchmark_contract.md",
            "benchmarks/cases/README.md",
        )
        missing = [name for name in required if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_numbered_benchmark_cases_use_the_full_contract(self):
        expected = {
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
        }
        cases_root = ROOT / "benchmarks" / "cases"
        observed = {path.name for path in cases_root.iterdir() if path.is_dir()}
        self.assertEqual(observed, expected)
        for case in sorted(expected):
            text = (cases_root / case / "README.md").read_text(encoding="utf-8")
            with self.subTest(case=case):
                for number in range(1, 23):
                    self.assertIn(f"| {number}.", text)

    def test_local_links_in_new_indexes_and_layers_resolve(self):
        roots = (
            ROOT / "notes" / "quick_start",
            ROOT / "notes" / "theory",
            ROOT / "notes" / "reference" / "code_walkthrough",
            ROOT / "benchmarks" / "cases",
        )
        markdown = [ROOT / "notes" / "reference" / "code_walkthrough.md"]
        for folder in roots:
            markdown.extend(folder.rglob("*.md"))
        broken: list[str] = []
        for source in markdown:
            for raw in re.findall(r"\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
                target = raw.split("#", 1)[0].strip().strip("<>")
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (source.parent / unquote(target)).resolve()
                if not resolved.exists():
                    broken.append(f"{source.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_capability_status_does_not_overstate_stage2(self):
        text = (ROOT / "docs" / "capability_matrix.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"Stage2B PML \| experimental")
        self.assertRegex(text, r"Stage2C Fresnel \| experimental")


if __name__ == "__main__":
    unittest.main()
