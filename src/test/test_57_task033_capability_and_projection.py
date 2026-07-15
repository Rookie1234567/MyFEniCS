from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.run_task033_one_tib_projection import main as one_tib_main
from benchmarks.run_task033_variable_p_audit import main as variable_p_main
from benchmarks.task033_one_tib_projection import (
    HIGH_RISK_MAX_ROWS,
    PREFERRED_MAX_ROWS,
    CANDIDATE_MAX_ROWS,
    build_one_tib_projection,
    classify_local_fe_rows,
)
from benchmarks.task033_variable_p_capability import (
    RepositorySourceState,
    build_variable_p_capability_audit,
    qualify_formal_source,
)


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"
BASELINE_ROWS = 923_346_000.0
SOURCE_SHA = "a" * 40


def _formal_source(sha: str = SOURCE_SHA) -> dict:
    return {
        "commit_sha": sha,
        "tracked_source_clean": True,
        "head_before_sha": sha,
        "head_after_sha": sha,
        "source_stable_during_run": True,
        "nonignored_untracked_clean": True,
        "complete_worktree_clean": True,
    }


def _adaptive_evidence(compression: float, sha: str = SOURCE_SHA) -> dict:
    return {
        "schema_version": 1,
        "task_id": "Task033",
        "record_type": "p2_periodic_graded_mesh_plan",
        "status": "measured_same_accuracy_qualification_attached",
        "formal_source": _formal_source(sha),
        "identity": {"is_adaptive_compression_measurement": True},
        "plan": {"degree": 2, "reference_h_nm": 3.0},
        "same_accuracy_qualification": {
            "status": "same_accuracy_strong_gate_pass",
            "data_identity": "derived_from_clean_measured_reference_and_candidate",
            "mandatory_gate_pass": True,
            "strong_gate_pass": True,
            "compression": compression,
            "compression_unit": "dimensionless_local_fe_row_ratio",
            "compression_baseline": "uniform_p2_h3",
            "compression_denominator": "candidate_local_fe_rows",
        },
    }


class Task033CapabilityAndProjectionTests(unittest.TestCase):
    @staticmethod
    def _synthetic_mixed_api_probe() -> dict:
        empty_symbol = {
            "module": "synthetic",
            "symbol": "absent",
            "available": False,
            "error_type": None,
            "signature": None,
        }
        symbols = {
            "basix_ufl_mixed_element": {
                **empty_symbol,
                "symbol": "mixed_element",
                "available": True,
            },
            "ufl_mixed_function_space": {**empty_symbol},
            "dolfinx_mixed_topology_form": {
                **empty_symbol,
                "symbol": "mixed_topology_form",
                "available": True,
            },
        }
        return {
            "data_identity": "synthetic_public_symbol_probe_for_unit_test",
            "packages": {},
            "symbols": symbols,
        }

    def test_mixed_fields_and_mixed_topology_do_not_qualify_cellwise_p(self) -> None:
        audit = build_variable_p_capability_audit(
            runtime_probe=self._synthetic_mixed_api_probe()
        )
        interpretation = audit["api_interpretation"]
        self.assertTrue(interpretation["mixed_fields"]["public_symbol_observed"])
        self.assertTrue(interpretation["mixed_topology"]["public_symbol_observed"])
        self.assertFalse(
            interpretation["mixed_fields"][
                "counts_as_cellwise_variable_p_evidence"
            ]
        )
        self.assertFalse(
            interpretation["mixed_topology"]
            ["counts_as_cellwise_variable_p_evidence"]
        )
        self.assertFalse(
            audit["decision"]["native_cellwise_variable_p_hcurl_qualified"]
        )
        self.assertEqual(audit["status"], "not_qualified_fail_closed")

    def test_every_variable_p_semantic_requirement_is_fail_closed(self) -> None:
        audit = build_variable_p_capability_audit(
            runtime_probe=self._synthetic_mixed_api_probe()
        )
        self.assertEqual(len(audit["semantic_requirements"]), 6)
        self.assertTrue(
            all(not item["qualified"] for item in audit["semantic_requirements"])
        )
        self.assertFalse(
            audit["decision"]["implement_bespoke_arbitrary_variable_p_constraints"]
        )
        self.assertFalse(audit["identity"]["proves_native_cellwise_variable_p"])

    def test_one_tib_projection_defaults_to_not_qualified(self) -> None:
        projection = build_one_tib_projection()
        self.assertEqual(projection["status"], "not_qualified")
        self.assertIsNone(projection["result"]["projected_local_fe_rows"])
        self.assertIsNone(projection["result"]["classification"])
        self.assertIn(
            "measured_same_accuracy_evidence_missing",
            projection["input"]["qualification_failures"],
        )
        self.assertNotIn("formal_source", projection)

    def test_unsourced_or_nonmeasured_compression_is_not_classified(self) -> None:
        unsourced = build_one_tib_projection(
            measured_compression=5.0,
            measurement_identity="measured",
        )
        self.assertEqual(unsourced["status"], "not_qualified")
        self.assertIsNone(unsourced["result"]["classification"])

        predicted = build_one_tib_projection(
            measured_compression=5.0,
            measurement_identity="predicted",
            evidence_record="records/predicted.json",
        )
        self.assertEqual(predicted["status"], "not_qualified")
        self.assertIsNone(predicted["result"]["classification"])

        wrong_sha = build_one_tib_projection(
            compression_evidence=_adaptive_evidence(5.0, "b" * 40),
            evidence_record="records/measured.json",
            formal_source=_formal_source(),
        )
        self.assertEqual(wrong_sha["status"], "not_qualified")
        self.assertIn(
            "adaptive_evidence_source_sha_mismatch",
            wrong_sha["input"]["qualification_failures"],
        )
        wrong_unit_evidence = _adaptive_evidence(5.0)
        wrong_unit_evidence["same_accuracy_qualification"][
            "compression_unit"
        ] = "dimensionless_ratio"
        wrong_unit = build_one_tib_projection(
            compression_evidence=wrong_unit_evidence,
            evidence_record="records/measured.json",
            formal_source=_formal_source(),
        )
        self.assertEqual(wrong_unit["status"], "not_qualified")
        self.assertIn(
            "compression_unit_not_local_fe_row_ratio",
            wrong_unit["input"]["qualification_failures"],
        )

        unqualified_evidence = _adaptive_evidence(5.0)
        unqualified_evidence["same_accuracy_qualification"][
            "mandatory_gate_pass"
        ] = False
        unqualified = build_one_tib_projection(
            compression_evidence=unqualified_evidence,
            evidence_record="records/measured.json",
            formal_source=_formal_source(),
        )
        self.assertEqual(unqualified["status"], "not_qualified")
        self.assertIn(
            "physical_equal_accuracy_gate_not_passed",
            unqualified["input"]["qualification_failures"],
        )

    def test_projection_classification_boundaries_are_disjoint(self) -> None:
        self.assertEqual(classify_local_fe_rows(PREFERRED_MAX_ROWS), "preferred")
        self.assertEqual(
            classify_local_fe_rows(math.nextafter(PREFERRED_MAX_ROWS, math.inf)),
            "candidate",
        )
        self.assertEqual(classify_local_fe_rows(CANDIDATE_MAX_ROWS), "candidate")
        self.assertEqual(
            classify_local_fe_rows(math.nextafter(CANDIDATE_MAX_ROWS, math.inf)),
            "high-risk",
        )
        self.assertEqual(classify_local_fe_rows(HIGH_RISK_MAX_ROWS), "high-risk")
        self.assertEqual(
            classify_local_fe_rows(math.nextafter(HIGH_RISK_MAX_ROWS, math.inf)),
            "infeasible",
        )

    def test_measured_compression_maps_to_all_four_row_zones(self) -> None:
        samples = {
            "preferred": (BASELINE_ROWS / 200_000_000.0, 200_000_000.0),
            "candidate": (BASELINE_ROWS / 300_000_000.0, 300_000_000.0),
            "high-risk": (BASELINE_ROWS / 400_000_000.0, 400_000_000.0),
            "infeasible": (BASELINE_ROWS / 600_000_000.0, 600_000_000.0),
        }
        for expected, (compression, target_rows) in samples.items():
            with self.subTest(expected=expected):
                projection = build_one_tib_projection(
                    compression_evidence=_adaptive_evidence(compression),
                    evidence_record="records/measured_compression.json",
                    formal_source=_formal_source(),
                )
                self.assertEqual(projection["status"], "classified")
                self.assertEqual(projection["result"]["classification"], expected)
                self.assertEqual(
                    projection["result"]["projected_local_fe_rows"], target_rows
                )

    def test_invalid_numeric_inputs_fail_closed(self) -> None:
        for value in (0.0, -1.0, math.inf, math.nan):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_one_tib_projection(
                        measured_compression=value,
                        measurement_identity="measured",
                        evidence_record="records/measured.json",
                    )
        with self.assertRaises(ValueError):
            classify_local_fe_rows(0.0)

    def test_formal_source_requires_full_clean_stable_git_state(self) -> None:
        clean = RepositorySourceState(SOURCE_SHA, ())
        source = qualify_formal_source(clean, clean)
        self.assertEqual(source["commit_sha"], SOURCE_SHA)
        self.assertTrue(source["nonignored_untracked_clean"])

        dirty = RepositorySourceState(SOURCE_SHA, ("?? new_nonignored.json",))
        with self.assertRaisesRegex(RuntimeError, "not_completely_clean"):
            qualify_formal_source(clean, dirty)
        changed = RepositorySourceState("b" * 40, ())
        with self.assertRaisesRegex(RuntimeError, "head_changed"):
            qualify_formal_source(clean, changed)

    def test_formal_variable_p_record_has_approved_source_binding(self) -> None:
        audit = build_variable_p_capability_audit(
            runtime_probe=self._synthetic_mixed_api_probe(),
            formal_source=_formal_source(),
        )
        self.assertTrue(audit["identity"]["is_formal_record"])
        self.assertEqual(audit["formal_source"]["commit_sha"], SOURCE_SHA)

    def test_formal_runners_attach_source_and_projection_consumes_evidence(self) -> None:
        clean = RepositorySourceState(SOURCE_SHA, ())
        stream = io.StringIO()
        with (
            patch(
                "benchmarks.run_task033_variable_p_audit.inspect_repository_source",
                return_value=clean,
            ),
            redirect_stdout(stream),
        ):
            self.assertEqual(variable_p_main(["--formal"]), 0)
        self.assertEqual(
            json.loads(stream.getvalue())["formal_source"]["commit_sha"],
            SOURCE_SHA,
        )

        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "adaptive.json"
            evidence_path.write_text(
                json.dumps(_adaptive_evidence(2.0)), encoding="utf-8"
            )
            stream = io.StringIO()
            with (
                patch(
                    "benchmarks.run_task033_one_tib_projection.inspect_repository_source",
                    return_value=clean,
                ),
                redirect_stdout(stream),
            ):
                self.assertEqual(
                    one_tib_main(
                        [
                            "--formal",
                            "--compression-evidence",
                            str(evidence_path),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stream.getvalue())["status"], "classified")

    def test_checked_plan_records_preserve_identity_and_units(self) -> None:
        variable_p = json.loads(
            (CASE / "records" / "variable_p_capability_audit.json").read_text(
                encoding="utf-8"
            )
        )
        projection = json.loads(
            (CASE / "records" / "one_tib_projection_plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(variable_p["status"], "not_qualified_fail_closed")
        self.assertFalse(variable_p["identity"]["proves_0p7nm_feasible"])
        self.assertEqual(projection["status"], "not_qualified")
        self.assertEqual(projection["baseline"]["value"], 923_346_000)
        self.assertEqual(projection["baseline"]["unit"], "local_fe_rows")
        self.assertEqual(projection["input"]["unit"], "dimensionless_ratio")
        self.assertEqual(projection["result"]["unit"], "local_fe_rows")
        self.assertFalse(projection["identity"]["is_0p7nm_feasibility_proof"])

    def test_json_schemas_reject_exaggerated_claims(self) -> None:
        try:
            import jsonschema
        except ModuleNotFoundError:
            self.skipTest("optional jsonschema package is unavailable")

        pairs = (
            (
                "variable_p_capability_schema.json",
                "variable_p_capability_audit.json",
            ),
            ("one_tib_projection_schema.json", "one_tib_projection_plan.json"),
        )
        for schema_name, record_name in pairs:
            schema = json.loads((CASE / schema_name).read_text(encoding="utf-8"))
            record = json.loads(
                (CASE / "records" / record_name).read_text(encoding="utf-8")
            )
            jsonschema.validate(record, schema)

        variable_schema = json.loads(
            (CASE / "variable_p_capability_schema.json").read_text(encoding="utf-8")
        )
        exaggerated = build_variable_p_capability_audit(
            runtime_probe=self._synthetic_mixed_api_probe()
        )
        exaggerated["identity"]["proves_native_cellwise_variable_p"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(exaggerated, variable_schema)
        jsonschema.validate(
            build_variable_p_capability_audit(
                runtime_probe=self._synthetic_mixed_api_probe(),
                formal_source=_formal_source(),
            ),
            variable_schema,
        )

        projection_schema = json.loads(
            (CASE / "one_tib_projection_schema.json").read_text(encoding="utf-8")
        )
        exaggerated_projection = build_one_tib_projection()
        exaggerated_projection["identity"]["is_0p7nm_feasibility_proof"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(exaggerated_projection, projection_schema)
        jsonschema.validate(
            build_one_tib_projection(
                compression_evidence=_adaptive_evidence(2.0),
                evidence_record="records/adaptive_h3.json",
                formal_source=_formal_source(),
            ),
            projection_schema,
        )


if __name__ == "__main__":
    unittest.main()
