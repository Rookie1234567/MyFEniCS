from __future__ import annotations

import copy
import json
import unittest

from benchmarks.task035_case094 import DEFAULT_MANIFEST, ROOT, validate_base_manifest


def _manifest() -> dict:
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))


class Task035PhaseATests(unittest.TestCase):
    def test_tracked_phase_a_manifest_is_hermetic(self) -> None:
        result = validate_base_manifest(_manifest(), repo_root=ROOT)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["status"], "phase_a_gate_pass")
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


if __name__ == "__main__":
    unittest.main()
