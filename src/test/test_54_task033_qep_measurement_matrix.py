from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from benchmarks.task033_qep_measurement import (
    QepCandidate,
    build_qep_plan,
    mixed_quad_local_dimension,
    not_run_measurement_record,
    qep_candidates,
    qep_memory_prediction,
    qep_runtime_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"


class Task033QepMeasurementMatrixTests(unittest.TestCase):
    def test_matrix_axes_are_complete_and_unique(self) -> None:
        candidates = qep_candidates()
        self.assertEqual(len(candidates), 180)
        self.assertEqual(len(set(candidates)), 180)
        self.assertEqual(len({candidate.matrix_key for candidate in candidates}), 180)
        self.assertEqual({candidate.degree for candidate in candidates}, {1, 2, 3, 4})
        self.assertEqual(
            {candidate.h_nm for candidate in candidates},
            {5.0, 3.0, 2.5, 2.0, 1.5},
        )
        self.assertEqual({candidate.mpi_size for candidate in candidates}, {1, 2, 4})
        self.assertEqual(
            {candidate.material_kind for candidate in candidates},
            {"air", "lossy_homogeneous", "stage4_xy"},
        )

    def test_qep_prediction_is_component_scoped_and_memory_gated(self) -> None:
        candidate = QepCandidate("air", 4, 1.5, 4)
        prediction = qep_memory_prediction(candidate)
        self.assertEqual(prediction["data_identity"], "predicted_not_measured")
        self.assertEqual(prediction["scope"], "cross_section_qep_component_only")
        self.assertGreater(prediction["full_dof_upper_bound"], 0)
        self.assertGreater(prediction["four_matrix_nnz_upper_bound"], 0)
        self.assertEqual(mixed_quad_local_dimension(4), 65)
        self.assertTrue(prediction["prediction_gate_pass"])

        tiny_limit = qep_memory_prediction(candidate, container_limit_gib=0.1)
        self.assertFalse(tiny_limit["prediction_gate_pass"])
        self.assertTrue(
            (not tiny_limit["two_centers_pass"])
            or (not tiny_limit["conservative_upper_pass"])
        )

    def test_runtime_contract_defaults_fail_closed_and_p3_requires_evidence(self) -> None:
        candidate = QepCandidate("lossy_homogeneous", 3, 5.0, 2)
        prediction = qep_memory_prediction(candidate)
        default = qep_runtime_preflight(candidate, prediction=prediction)
        self.assertFalse(default["launch_eligible"])
        self.assertIn("tracked_source_clean_unknown", default["failures"])
        self.assertIn("swap_activity_state_unknown", default["failures"])
        self.assertIn("watchdog_state_unknown", default["failures"])
        self.assertIn(
            "case090_high_order_core_evidence_missing_or_invalid",
            default["failures"],
        )

        verified = qep_runtime_preflight(
            candidate,
            prediction=prediction,
            source_clean_verified=True,
            verified_clean_sha="a" * 40,
            swap_activity_detected=False,
            watchdog_enabled=True,
            one_large_case_at_a_time=True,
            high_order_core_evidence_sha256="b" * 64,
        )
        self.assertTrue(verified["runtime_contract_verified"])
        self.assertTrue(verified["launch_eligible"])
        self.assertEqual(verified["failures"], [])

    def test_not_run_record_has_no_numerical_or_pass_identity(self) -> None:
        candidate = QepCandidate("stage4_xy", 2, 3.0, 1)
        prediction = qep_memory_prediction(candidate)
        preflight = qep_runtime_preflight(candidate, prediction=prediction)
        record = not_run_measurement_record(
            candidate,
            prediction=prediction,
            preflight=preflight,
            provenance={"commit_sha": None},
        )
        self.assertEqual(record["status"], "not_run_runtime_contract")
        self.assertFalse(record["identity"]["is_pde_run"])
        self.assertFalse(record["identity"]["is_solver_pass"])
        self.assertIsNone(record["numerical_results"])
        self.assertIsNone(record["resource_measurements"])
        self.assertFalse(record["gates"]["all_required_numerical_gates_pass"])

    def test_checked_in_plan_is_exact_and_never_counts_not_run_as_pass(self) -> None:
        checked = json.loads(
            (CASE / "records" / "qep_matrix_plan.json").read_text(encoding="utf-8")
        )
        self.assertEqual(checked, build_qep_plan())
        self.assertEqual(checked["status"], "not_run")
        self.assertEqual(checked["summary"]["entries"], 180)
        self.assertEqual(checked["summary"]["measured_entries"], 0)
        self.assertEqual(checked["summary"]["solver_pass_entries"], 0)
        self.assertTrue(
            all(entry["result_identity"] == "not_run" for entry in checked["entries"])
        )
        self.assertTrue(
            all(not entry["is_solver_pass"] for entry in checked["entries"])
        )
        self.assertTrue(
            all(entry["numerical_results"] is None for entry in checked["entries"])
        )

    def test_json_schema_rejects_a_not_run_entry_relabelled_as_pass(self) -> None:
        try:
            import jsonschema
        except ImportError:  # pragma: no cover - optional host dependency
            self.skipTest("jsonschema is not installed")
        schema = json.loads(
            (CASE / "qep_measurement_schema.json").read_text(encoding="utf-8")
        )
        plan = build_qep_plan()
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(plan)

        candidate = QepCandidate("air", 2, 5.0, 1)
        prediction = qep_memory_prediction(candidate)
        validator.validate(
            not_run_measurement_record(
                candidate,
                prediction=prediction,
                preflight=qep_runtime_preflight(candidate, prediction=prediction),
                provenance={"commit_sha": None},
            )
        )

        invalid = copy.deepcopy(plan)
        invalid["entries"][0]["is_solver_pass"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(invalid)

    def test_invalid_candidate_and_mode_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            QepCandidate("air", 5, 5.0, 1)
        with self.assertRaises(ValueError):
            QepCandidate("air", 2, 4.0, 1)
        with self.assertRaises(ValueError):
            QepCandidate("air", 2, 5.0, 3)
        with self.assertRaises(ValueError):
            qep_memory_prediction(QepCandidate("air", 2, 5.0, 1), requested_modes=1)


if __name__ == "__main__":
    unittest.main()
