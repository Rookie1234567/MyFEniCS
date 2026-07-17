from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from benchmarks.task033_qep_measurement import (
    LEFT_CANDIDATE_POOL_POLICY,
    QepCandidate,
    build_qep_plan,
    mixed_quad_local_dimension,
    not_run_measurement_record,
    qep_candidates,
    qep_memory_prediction,
    qep_runtime_preflight,
    task033_left_candidate_pool_size,
)


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"


def _measured_qep_numerical_results() -> dict:
    pair_errors = [1.0e-10] * 8
    return {
        "full_dof": 120,
        "reduced_dof": 100,
        "four_matrix_nnz": {
            "K0": 1000,
            "K1": 900,
            "K2": 800,
            "electric_mass": 700,
        },
        "four_matrix_nnz_total": 3400,
        "selected_beta_per_nm": [0.08, 0.0],
        "analytic_beta_per_nm": [0.08, 0.0],
        "analytic_beta_relative_error": 1.0e-3,
        "polynomial_relative_residual": 1.0e-12,
        "assembly_seconds_max_rank": 1.0,
        "solve_seconds_max_rank": 2.0,
        "classification_seconds_max_rank": 0.5,
        "retained_eigenvector_bytes": {
            "right_reduced": 12800,
            "right_full": 15360,
            "left_reduced": 12800,
            "left_full": 15360,
            "total": 56320,
            "scalar_bytes": 16,
            "full_vector_gathered_to_root": False,
        },
        "left_right_classification": {
            "right_polynomial_relative_residual_max": 1.0e-12,
            "left_polynomial_relative_residual_max": 1.0e-10,
            "biorthogonality_identity_error": 1.0e-8,
            "biorthogonality_infinity_norm_error": 8.0e-8,
            "left_candidate_pool_policy": "max_requested_plus_8_or_2x",
            "right_requested_modes": 8,
            "left_candidate_requested_modes": 16,
            "left_candidate_converged_modes": 16,
            "left_pair_relative_errors": pair_errors,
            "left_pair_relative_error_max": max(pair_errors),
            "near_degenerate_groups": [
                {
                    "indices": [0],
                    "beta_center_per_nm": [0.08, 0.0],
                    "max_relative_beta_spread": 0.0,
                    "overlap_condition": 1.0,
                    "normalization_method": "diagonal_qprime",
                    "post_normalization_identity_error": 1.0e-12,
                }
            ],
            "directions": ["forward"] * 8,
            "kinds": ["propagating"] * 8,
            "passive_branch_valid": [True] * 8,
            "full_vector_gathered": False,
        },
        "quadrature": {
            "field_degree": 2,
            "geometry_degree": 1,
            "coefficient_degree": 0,
            "selected_degree": 8,
            "policy": "test-policy",
        },
    }


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
        self.assertEqual(task033_left_candidate_pool_size(2), 10)
        self.assertEqual(task033_left_candidate_pool_size(8), 16)
        self.assertEqual(task033_left_candidate_pool_size(12), 24)
        self.assertEqual(prediction["requested_modes"], 8)
        self.assertEqual(prediction["left_candidate_modes"], 16)
        self.assertEqual(
            prediction["left_candidate_pool_policy"],
            LEFT_CANDIDATE_POOL_POLICY,
        )
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

        measured = not_run_measurement_record(
            candidate,
            prediction=prediction,
            preflight=qep_runtime_preflight(candidate, prediction=prediction),
            provenance={"commit_sha": "a" * 40},
        )
        measured["schema_version"] = "task033.case091.qep-measurement.v2"
        measured["status"] = "measured_shard_pass"
        measured["identity"].update(
            {
                "is_pde_run": True,
                "is_solver_pass": True,
                "is_memory_measurement": True,
                "result_identity": "measured_shard",
                "is_physical_qualification_record": False,
                "physical_qualified": False,
            }
        )
        measured["numerical_results"] = _measured_qep_numerical_results()
        measured["resource_measurements"] = {}
        measured["gates"] = {
            "all_required_numerical_gates_pass": True,
            "left_right_beta_pair_relative_error_le_1e-7": True,
        }
        validator.validate(measured)

        missing_raw_pairing = copy.deepcopy(measured)
        del missing_raw_pairing["numerical_results"][
            "left_right_classification"
        ]["left_candidate_pool_policy"]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(missing_raw_pairing)

        missing_infinity_norm = copy.deepcopy(measured)
        del missing_infinity_norm["numerical_results"][
            "left_right_classification"
        ]["biorthogonality_infinity_norm_error"]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(missing_infinity_norm)

        forged_all_pass = copy.deepcopy(measured)
        classification = forged_all_pass["numerical_results"][
            "left_right_classification"
        ]
        classification["left_pair_relative_errors"][-1] = 2.0e-7
        classification["left_pair_relative_error_max"] = 2.0e-7
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(forged_all_pass)

        forged_biorthogonality_pass = copy.deepcopy(measured)
        forged_biorthogonality_pass["numerical_results"][
            "left_right_classification"
        ]["biorthogonality_identity_error"] = 1.000001e-6
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(forged_biorthogonality_pass)

        missing_explicit_gate = copy.deepcopy(measured)
        del missing_explicit_gate["gates"][
            "left_right_beta_pair_relative_error_le_1e-7"
        ]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(missing_explicit_gate)

    def test_invalid_candidate_and_mode_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            QepCandidate("air", 5, 5.0, 1)
        with self.assertRaises(ValueError):
            QepCandidate("air", 2, 4.0, 1)
        with self.assertRaises(ValueError):
            QepCandidate("air", 2, 5.0, 3)
        with self.assertRaises(ValueError):
            qep_memory_prediction(QepCandidate("air", 2, 5.0, 1), requested_modes=1)
        with self.assertRaises(ValueError):
            qep_memory_prediction(
                QepCandidate("air", 2, 5.0, 1),
                requested_modes=8,
                left_candidate_modes=8,
            )


if __name__ == "__main__":
    unittest.main()
