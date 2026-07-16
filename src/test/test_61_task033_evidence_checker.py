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
    FINAL_OUTCOME_INPUT_ROLE_MAP,
    FORMAL_SCHEMA,
    REQUIRED_FORMAL_ROLES,
    ROLE_SPECS,
    ROOT,
    _manifest_structure_problems,
    _semantic_problems,
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
        schema_check = next(
            check
            for check in report["checks"]
            if check["name"] == "all_task033_schemas_parse"
        )
        for schema_path in schema_check["details"]["schemas"]:
            self.assertNotIn("\\", schema_path)
            self.assertFalse(Path(schema_path).is_absolute())

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

    def test_manifest_schema_rejects_nonportable_paths(self) -> None:
        schema = json.loads((ROOT / FORMAL_SCHEMA).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        manifest = json.loads(
            (ROOT / DEFAULT_FORMAL_MANIFEST).read_text(encoding="utf-8")
        )
        manifest["status"] = "submitted_for_verification"
        manifest["identity"]["is_formal_evidence_submission"] = True
        manifest["clean_source_sha"] = "a" * 40
        manifest["entries"] = [
            {
                "role": role,
                "path": f"benchmarks/artifacts/{role}.json",
                "sha256": "0" * 64,
                "schema_ref": ROLE_SPECS[role].schema_ref,
                "source_sha_pointer": "/formal_source/commit_sha",
                "source_clean_pointer": "/formal_source/tracked_source_clean",
                "source_clean_expected": True,
            }
            for role in REQUIRED_FORMAL_ROLES
        ]
        validator.validate(manifest)
        for bad_path in (
            "/absolute.json",
            "C:/absolute.json",
            "nested\\record.json",
            "../escape.json",
            "nested/../escape.json",
            "./record.json",
            "nested/./record.json",
            "nested//record.json",
            "nested/",
        ):
            with self.subTest(path=bad_path):
                forged = copy.deepcopy(manifest)
                forged["entries"][0]["path"] = bad_path
                self.assertTrue(list(validator.iter_errors(forged)))

    def test_manifest_structure_resolves_aliases_before_reuse_check(self) -> None:
        entries = [
            {
                "role": role,
                "path": (
                    "case090.json"
                    if role in {"case090_clean_core", "case090_mpi_memory"}
                    else f"evidence/{role}.json"
                ),
            }
            for role in REQUIRED_FORMAL_ROLES
        ]
        entries[2]["path"] = "evidence/shared.json"
        entries[3]["path"] = "evidence/alias/../shared.json"
        manifest = {
            "status": "submitted_for_verification",
            "required_roles": list(REQUIRED_FORMAL_ROLES),
            "entries": entries,
        }

        with tempfile.TemporaryDirectory() as tmp:
            problems = _manifest_structure_problems(
                manifest, root=Path(tmp)
            )

        rendered = "\n".join(problems)
        self.assertIn("is not canonical repository-relative POSIX", rendered)
        self.assertIn("reuses evidence path", rendered)

    def test_require_formal_fails_closed_on_committed_not_run_manifest(self) -> None:
        report = check_task033(root=ROOT, require_formal=True)

        self.assertFalse(report["verified"])
        self.assertEqual(report["mode"], "formal")
        self.assertEqual(report["status"], "fail_closed")
        rendered = "\n".join(report["problems"])
        self.assertIn("submitted_for_verification", rendered)
        self.assertIn("missing roles", rendered)

    def test_role_inventory_includes_required_negative_evidence(self) -> None:
        self.assertEqual(len(REQUIRED_FORMAL_ROLES), 21)
        self.assertEqual(set(REQUIRED_FORMAL_ROLES), set(ROLE_SPECS))
        for role in (
            "qep_mpi2_timeout_negative",
            "qep_mpi4_timeout_negative",
        ):
            self.assertEqual(
                ROLE_SPECS[role].accepted_statuses,
                ("formal_not_pass",),
            )
        self.assertEqual(len(FINAL_OUTCOME_INPUT_ROLE_MAP), 13)
        self.assertNotIn("formal_verification", REQUIRED_FORMAL_ROLES)
        self.assertEqual(
            ROLE_SPECS["qep_order_study"].accepted_statuses,
            (
                "qep_component_aggregate_qualified",
                "qep_component_aggregate_not_qualified",
            ),
        )
        self.assertEqual(
            ROLE_SPECS["variable_p_capability_audit"].accepted_statuses,
            ("not_qualified_fail_closed",),
        )

    def test_timeout_and_anchor_roles_enforce_exact_identity(self) -> None:
        source_gate = {"pass": True, "checks": {"clean": True}}
        common = {
            "schema_version": "task033.memory-watchdog.v2",
            "benchmark_id": "task033_external_memory_watchdog",
            "resource_authority": {"gate": {"pass": True}},
            "source_gate": source_gate,
            "launch_gate": {"pass": True},
            "memory_authority_pass": True,
            "no_swap": True,
            "terminated_for_memory": False,
            "terminated_for_authority_unreadable": False,
        }
        timeout = {
            **common,
            "target": "qep",
            "status": "formal_not_pass",
            "formal_pass": False,
            "numeric_pass": False,
            "return_code": -15,
            "terminated_for_timeout": True,
            "command": ["mpiexec", "-n", "2", "python", "qep"],
        }
        self.assertEqual(
            _semantic_problems("qep_mpi2_timeout_negative", timeout), []
        )
        self.assertTrue(
            _semantic_problems("qep_mpi4_timeout_negative", timeout)
        )

        anchor = {
            **common,
            "target": "hybrid",
            "status": "measured_shard_pass",
            "formal_pass": True,
            "numeric_pass": True,
            "terminated_for_timeout": False,
            "requested_modes": 160,
            "candidate_modes": 160,
            "command": ["mpiexec", "-n", "4", "python", "hybrid"],
            "measurements": {
                "case": {"degree": 1, "h_nm": 5.0},
                "hybrid_system": {"primary_solver_path": "augmented"},
                "modal_schur_comparison": {
                    "status": "pass",
                    "comparison_solver_path": "modal-schur-memory-minimal",
                    "comparison_solver_path_argument": "minimal",
                    "dense_interface_square_formed": False,
                    "gates": {"solution": True},
                },
            },
        }
        self.assertEqual(
            _semantic_problems("augmented_vs_minimal_p1", anchor), []
        )
        forged = copy.deepcopy(anchor)
        forged["measurements"]["modal_schur_comparison"][
            "dense_interface_square_formed"
        ] = True
        self.assertTrue(
            _semantic_problems("augmented_vs_minimal_p1", forged)
        )

    def test_checker_rejects_generic_not_qualified_qep_as_partial(self) -> None:
        payload = {
            "status": "qep_component_aggregate_not_qualified",
            "qualification_classification": "not_qualified",
            "identity": {
                "is_qep_component_qualified": False,
                "is_qep_p3_only_partial": False,
            },
        }
        problems = _semantic_problems("qep_order_study", payload)
        self.assertTrue(problems)
        self.assertIn("narrow p4-only partial", problems[0])

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
