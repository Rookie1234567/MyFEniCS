from __future__ import annotations

import copy
import json
import unittest

from benchmarks.task035_case094 import DEFAULT_MANIFEST, ROOT, validate_base_manifest
from src.test.test_26_documentation_contract import (
    ACTIVE_RESEARCH_CASES,
    QUALIFIED_OR_FROZEN_CASES,
    STAGING_OR_IN_PROGRESS_CASES,
)



def _manifest() -> dict:
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))


class Task035PhaseATests(unittest.TestCase):
    def test_tracked_phase_a_manifest_is_hermetic(self) -> None:
        result = validate_base_manifest(_manifest(), repo_root=ROOT)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["status"], "phase_a_gate_pass")
        self.assertEqual(
            result["successor_binding_results"][0]["status"],
            "approved_successor_hash_match",
        )
        self.assertTrue(
            all(row["status"] == "descriptor_only" for row in result["artifact_results"])
        )

    def test_tracked_hash_mismatch_is_recomputed(self) -> None:
        manifest = copy.deepcopy(_manifest())
        manifest["tracked_bindings"]["case093_compact_records"][0]["sha256"] = "0" * 64
        result = validate_base_manifest(manifest, repo_root=ROOT)
        self.assertIn(
            "case093_compact_records[0]:tracked_hash_mismatch",
            result["failures"],
        )

    def test_artifact_descriptor_cannot_claim_a_different_observed_hash(self) -> None:
        manifest = copy.deepcopy(_manifest())
        manifest["baseline_artifacts"][0]["observed_sha256"] = "f" * 64
        result = validate_base_manifest(manifest, repo_root=ROOT)
        self.assertIn(
            "p4_h5_full3d:descriptor_hash_binding",
            result["failures"],
        )

    def test_all_six_baseline_roles_are_required(self) -> None:
        manifest = copy.deepcopy(_manifest())
        manifest["baseline_artifacts"].pop()
        result = validate_base_manifest(manifest, repo_root=ROOT)
        self.assertIn("baseline_artifact_roles", result["failures"])

    def test_staging_case_cannot_claim_canonical_or_production(self) -> None:
        case_dir = ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity"
        for name in ("config.json", "expected.json"):
            record = json.loads((case_dir / name).read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "phase_a_in_progress")
            self.assertFalse(record["canonical"])
            self.assertFalse(record["production_qualified"])
            self.assertFalse(record["pde_run"])
            self.assertEqual(record["phase_b_or_later_results"], "not_available")

    def test_base_manifest_records_final_phase_a_pass(self) -> None:
        manifest = _manifest()
        self.assertEqual(manifest["status"], "phase_a_gate_pass")
        self.assertTrue(manifest["gates"]["full_regression"])
        self.assertTrue(manifest["decision"]["phase_a_gate_pass"])
        self.assertTrue(
            manifest["decision"]["phase_b_fixture_work_authorized_after_phase_a_review"]
        )

    def test_ordinary_checker_does_not_read_ignored_artifacts(self) -> None:
        manifest = copy.deepcopy(_manifest())
        manifest["environment_qualification"]["raw_json_path"] = (
            "benchmarks/artifacts/not_materialized/environment.json"
        )
        for index, artifact in enumerate(manifest["baseline_artifacts"]):
            artifact["path"] = f"benchmarks/artifacts/not_materialized/{index}.json"
        result = validate_base_manifest(manifest, repo_root=ROOT)
        self.assertEqual(result["failures"], [])
        self.assertTrue(
            all(row["status"] == "descriptor_only" for row in result["artifact_results"])
        )

    def test_case_directory_set_is_formal_union_staging(self) -> None:
        cases_root = ROOT / "benchmarks/cases"
        observed = {path.name for path in cases_root.iterdir() if path.is_dir()}
        self.assertEqual(
            observed,
            QUALIFIED_OR_FROZEN_CASES
            | STAGING_OR_IN_PROGRESS_CASES
            | ACTIVE_RESEARCH_CASES,
        )

    def test_initial_regression_failure_history_is_preserved(self) -> None:
        path = (
            ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
            / "phase_a_regression_failure.json"
        )
        failure = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(failure["status"], "controlled_stop")
        self.assertEqual(failure["result"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
