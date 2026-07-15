from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from benchmarks.check_task033 import main
from benchmarks.task033_evidence_checker import (
    DEFAULT_FORMAL_MANIFEST,
    FORMAL_SCHEMA,
    REQUIRED_FORMAL_ROLES,
    ROLE_SPECS,
    ROOT,
    check_formal_evidence,
    check_task033,
)


class Task033EvidenceCheckerTests(unittest.TestCase):
    def test_default_planning_bundle_is_verified_without_physical_claim(self) -> None:
        report = check_task033(root=ROOT)

        self.assertTrue(report["verified"], report["problems"])
        self.assertEqual(report["mode"], "planning")
        self.assertEqual(report["status"], "evidence_verified")
        self.assertFalse(report["identity"]["is_pde_run"])
        self.assertFalse(report["identity"]["is_solver_pass"])
        self.assertFalse(report["identity"]["claims_task033_complete"])
        self.assertEqual(len(report["checks"]), 9)

    def test_committed_manifest_is_schema_valid_and_explicitly_not_run(self) -> None:
        schema = json.loads((ROOT / FORMAL_SCHEMA).read_text(encoding="utf-8"))
        manifest = json.loads(
            (ROOT / DEFAULT_FORMAL_MANIFEST).read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
        self.assertEqual(manifest["status"], "not_run")
        self.assertIsNone(manifest["clean_source_sha"])
        self.assertEqual(manifest["entries"], [])
        self.assertFalse(manifest["identity"]["is_solver_pass"])

    def test_require_formal_fails_closed_on_committed_not_run_manifest(self) -> None:
        report = check_task033(root=ROOT, require_formal=True)

        self.assertFalse(report["verified"])
        self.assertEqual(report["mode"], "formal")
        self.assertEqual(report["status"], "fail_closed")
        rendered = "\n".join(report["problems"])
        self.assertIn("submitted_for_verification", rendered)
        self.assertIn("missing roles", rendered)

    def test_role_inventory_includes_required_negative_evidence(self) -> None:
        self.assertEqual(len(REQUIRED_FORMAL_ROLES), 16)
        self.assertEqual(set(REQUIRED_FORMAL_ROLES), set(ROLE_SPECS))
        self.assertEqual(
            ROLE_SPECS["qep_mpi_timeout_negative"].accepted_statuses,
            ("formal_not_pass",),
        )
        self.assertEqual(
            ROLE_SPECS["variable_p_capability_audit"].accepted_statuses,
            ("not_qualified_fail_closed",),
        )

    def test_complete_inventory_with_wrong_hashes_fails_before_acceptance(self) -> None:
        committed = json.loads(
            (ROOT / DEFAULT_FORMAL_MANIFEST).read_text(encoding="utf-8")
        )
        manifest = copy.deepcopy(committed)
        manifest["status"] = "submitted_for_verification"
        manifest["identity"]["is_formal_evidence_submission"] = True
        manifest["clean_source_sha"] = "a" * 40
        available_paths = [
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / "benchmarks").rglob("*.json"))
            if path != ROOT / DEFAULT_FORMAL_MANIFEST
        ]
        self.assertGreaterEqual(len(available_paths), len(REQUIRED_FORMAL_ROLES))
        role_paths: dict[str, str] = {}
        next_path = 0
        for role in REQUIRED_FORMAL_ROLES:
            if role == "case090_mpi_memory":
                role_paths[role] = role_paths["case090_clean_core"]
            else:
                role_paths[role] = available_paths[next_path]
                next_path += 1
        manifest["entries"] = [
            {
                "role": role,
                "path": role_paths[role],
                "sha256": "0" * 64,
                "schema_ref": ROLE_SPECS[role].schema_ref,
                "source_sha_pointer": "/formal_source/commit_sha",
                "source_clean_pointer": "/formal_source/tracked_source_clean",
                "source_clean_expected": True,
            }
            for role in REQUIRED_FORMAL_ROLES
        ]
        with tempfile.TemporaryDirectory(prefix="task033_manifest_") as temporary:
            path = Path(temporary) / "formal_manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            checks = check_formal_evidence(path, root=ROOT)

        problems = [
            problem
            for check in checks
            for problem in check.get("problems", [])
        ]
        self.assertTrue(any("SHA256 mismatch" in problem for problem in problems))
        self.assertFalse(any(check["status"] == "verified" for check in checks[2:]))

    def test_cli_exit_codes_distinguish_planning_and_formal_modes(self) -> None:
        with redirect_stdout(io.StringIO()):
            planning_code = main(["--repo-root", str(ROOT)])
            formal_code = main(["--repo-root", str(ROOT), "--require-formal"])

        self.assertEqual(planning_code, 0)
        self.assertEqual(formal_code, 2)


if __name__ == "__main__":
    unittest.main()
