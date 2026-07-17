from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from benchmarks.run_task033_resource_matrix import flatten_entry
from benchmarks.task033_resource_gates import (
    BASE_GATE_GIB,
    DEFAULT_DOCKER_LIMIT_GIB,
    build_reduced_equal_accuracy_resource_matrix,
    build_resource_matrix,
    matrix_key,
    nedelec_hex_local_dimension,
    project_resources,
    scaled_gate_limits,
)


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"


class Task033ResourceGateTests(unittest.TestCase):
    def _matrix(self) -> dict:
        return build_resource_matrix()

    @staticmethod
    def _entry(record: dict, key: str) -> dict:
        return next(item for item in record["entries"] if item["matrix_key"] == key)

    def test_default_matrix_has_all_twenty_policy_and_decision_entries(self) -> None:
        record = self._matrix()
        self.assertEqual(record["matrix_shape"]["entries"], 20)
        self.assertEqual(len(record["entries"]), 20)
        self.assertEqual(
            record["decision_counts"],
            {
                "planning": {
                    "planning_eligible_by_resource_prediction": 8,
                    "reuse_task032_clean_anchor": 1,
                    "not_run_by_memory_gate": 11,
                },
                "launch": {
                    "not_launch_eligible_runtime_contract": 7,
                    "reuse_task032_clean_anchor": 1,
                    "not_run_by_memory_gate": 11,
                    "not_run_pending_high_order_qualification": 1,
                },
            },
        )
        policy_counts: dict[str, int] = {}
        for entry in record["entries"]:
            policy = entry["policy_class"]
            policy_counts[policy] = policy_counts.get(policy, 0) + 1
        self.assertEqual(
            policy_counts,
            {"required": 10, "conditional": 4, "locked_by_default": 6},
        )

    def test_top_level_identity_is_complete_and_prediction_only(self) -> None:
        record = self._matrix()
        self.assertEqual(record["benchmark_id"], "task033_case091_resource_matrix")
        self.assertEqual(record["case_id"], "091_hybrid_hp_adaptivity_feasibility")
        self.assertEqual(record["task_id"], "Task033")
        self.assertEqual(
            record["record_type"],
            "task033_resource_prediction_and_launch_decision",
        )
        self.assertEqual(
            record["data_identity"],
            "prediction_with_measured_task032_calibration_and_anchor",
        )
        identity = record["identity"]
        for field in (
            "is_pde_run",
            "is_solver_pass",
            "is_memory_measurement",
            "is_adaptive_compression_measurement",
            "ordinary_default_changed",
            "runtime_preflight_performed",
            "proves_0p7nm_feasible",
        ):
            self.assertFalse(identity[field], field)

    def test_default_runtime_contract_is_unknown_and_fail_closed(self) -> None:
        record = self._matrix()
        runtime = record["runtime_launch_contract"]
        for field in (
            "source_clean",
            "swap_activity_detected",
            "watchdog_enabled",
            "one_large_case_at_a_time",
        ):
            self.assertIsNone(runtime[field], field)
        self.assertFalse(runtime["runtime_contract_verified"])
        self.assertEqual(len(runtime["contract_failures"]), 4)

        p2_h5 = self._entry(record, "p2_h5")
        self.assertTrue(p2_h5["planning_eligible"])
        self.assertFalse(p2_h5["launch_eligible"])
        self.assertEqual(
            p2_h5["launch_decision"], "not_launch_eligible_runtime_contract"
        )

    def test_verified_runtime_and_high_order_gates_are_separate(self) -> None:
        runtime = {
            "source_clean": True,
            "swap_activity_detected": False,
            "watchdog_enabled": True,
            "one_large_case_at_a_time": True,
        }
        record = build_resource_matrix(**runtime)
        self.assertTrue(self._entry(record, "p2_h5")["launch_eligible"])
        p3_h5 = self._entry(record, "p3_h5")
        self.assertTrue(p3_h5["planning_eligible"])
        self.assertFalse(p3_h5["launch_eligible"])
        self.assertEqual(
            p3_h5["launch_decision"],
            "not_run_pending_high_order_qualification",
        )

        qualified = build_resource_matrix(**runtime, qualified_high_order_degrees=(3,))
        self.assertTrue(self._entry(qualified, "p3_h5")["launch_eligible"])
        self.assertEqual(
            self._entry(qualified, "p3_h5")["launch_decision"],
            "launch_eligible",
        )

    def test_factor_center_uses_each_cases_own_predicted_nnz_and_fill(self) -> None:
        p2_h2p5 = project_resources(2, 2.5)
        p4_h5 = project_resources(4, 5.0)
        factor_key = "factor_nnz_fill_payload_affine"
        factor_p2 = p2_h2p5["predictions"][factor_key]
        factor_p4 = p4_h5["predictions"][factor_key]
        self.assertNotEqual(
            p2_h2p5["projected_assembled_nnz"],
            p4_h5["projected_assembled_nnz"],
        )
        self.assertNotEqual(
            factor_p2["projected_factor_payload_gib"],
            factor_p4["projected_factor_payload_gib"],
        )
        self.assertGreater(factor_p4["projected_fill_ratio"], 0.0)
        self.assertGreaterEqual(factor_p2["projected_fill_ratio"], 1.0)
        self.assertEqual(factor_p4["minimum_fill_ratio"], 1.0)
        self.assertEqual(
            factor_p4["independent_variable"],
            "projected assembled NNZ and factor fill",
        )
        p4_entry = self._entry(self._matrix(), "p4_h5")
        self.assertFalse(p4_entry["prediction_gate_pass"])
        self.assertFalse(p4_entry["launch_eligible"])
        self.assertEqual(p4_entry["launch_decision"], "not_run_by_memory_gate")

    def test_p2_h5_nnz_anchor_has_no_ceil_drift(self) -> None:
        projection = project_resources(2, 5.0)
        self.assertEqual(projection["projected_local_fe_rows"], 13_652)
        self.assertEqual(projection["projected_assembled_nnz"], 2_000_624)

    def test_review_v5_reduced_equal_accuracy_matrix_is_separate(self) -> None:
        record = build_reduced_equal_accuracy_resource_matrix()
        self.assertEqual(record["matrix_shape"]["entries"], 2)
        self.assertEqual(
            [entry["matrix_key"] for entry in record["entries"]],
            ["p3_h10", "p3_h7p5"],
        )
        self.assertEqual(
            record["resolved_config"]["execution_order"],
            ["p3_h10", "p3_h7p5_if_needed"],
        )
        for entry in record["entries"]:
            self.assertTrue(entry["prediction_gate_pass"])
            self.assertFalse(entry["launch_eligible"])
            self.assertEqual(
                entry["launch_decision"],
                "not_launch_eligible_runtime_contract",
            )
        self.assertLess(
            record["entries"][0]["conservative_upper_gib"],
            record["entries"][1]["conservative_upper_gib"],
        )

    def test_measured_p2_h3_anchor_is_not_mixed_with_predicted_fields(self) -> None:
        entry = self._entry(self._matrix(), "p2_h3")
        self.assertEqual(entry["launch_decision"], "reuse_task032_clean_anchor")
        self.assertEqual(entry["data_identity"]["projected_rows_nnz"], "predicted")
        self.assertEqual(entry["data_identity"]["pde_execution"], "not_run")
        measured = entry["measured_anchor"]
        self.assertEqual(measured["data_identity"], "measured")
        self.assertEqual(measured["local_fe_rows"], 68_396)
        self.assertEqual(measured["total_rows"], 68_796)
        self.assertEqual(measured["assembled_nnz"], 8_594_673)
        self.assertEqual(measured["modes_per_direction"], 160)

    def test_default_uses_measured_docker_limit_and_injected_limits_scale(self) -> None:
        limits = scaled_gate_limits()
        self.assertEqual(limits["container_limit_gib"], DEFAULT_DOCKER_LIMIT_GIB)
        self.assertEqual(limits["effective_hard_budget_gib"], 13.6485)
        self.assertEqual(
            limits["container_limit_identity"],
            "measured_phase0_docker_engine_memtotal",
        )

        half = scaled_gate_limits(7.0)
        self.assertEqual(half["scale_from_14_gib"], 0.5)
        self.assertEqual(
            half["two_center_limit_gib"], BASE_GATE_GIB["two_center_limit"] / 2
        )
        self.assertEqual(
            half["controlled_termination_gib"],
            BASE_GATE_GIB["controlled_termination"] / 2,
        )
        capped = scaled_gate_limits(64.0)
        self.assertEqual(capped["effective_hard_budget_gib"], 14.0)

    def test_explicit_failed_runtime_contracts_remain_fail_closed(self) -> None:
        variants = (
            ({"source_clean": False}, "tracked_source_not_clean"),
            ({"swap_activity_detected": True}, "swap_activity_detected"),
            ({"watchdog_enabled": False}, "watchdog_not_enabled"),
            (
                {"one_large_case_at_a_time": False},
                "one_large_case_contract_not_met",
            ),
        )
        for kwargs, reason in variants:
            with self.subTest(reason=reason):
                runtime = {
                    "source_clean": True,
                    "swap_activity_detected": False,
                    "watchdog_enabled": True,
                    "one_large_case_at_a_time": True,
                }
                runtime.update(kwargs)
                record = build_resource_matrix(**runtime)
                p2_h5 = self._entry(record, "p2_h5")
                self.assertFalse(p2_h5["launch_eligible"])
                self.assertIn(reason, p2_h5["launch_reasons"])

    def test_conditional_and_locked_cases_keep_explicit_fail_closed_reasons(
        self,
    ) -> None:
        entries = {item["matrix_key"]: item for item in self._matrix()["entries"]}
        self.assertIn(
            "conditional_predecessor_clean_record_missing",
            entries["p3_h3"]["planning_reasons"],
        )
        self.assertIn(
            "locked_by_default_without_independent_unlock",
            entries["p4_h2p5"]["planning_reasons"],
        )

    def test_checked_in_json_and_csv_match_every_entry_leaf(self) -> None:
        checked = json.loads(
            (CASE / "records" / "resource_matrix.json").read_text(encoding="utf-8")
        )
        self.assertEqual(checked, self._matrix())
        with (CASE / "records" / "resource_matrix.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 20)
        all_fields = set(rows[0])
        for csv_row, json_entry in zip(rows, checked["entries"], strict=True):
            expected = flatten_entry(json_entry)
            self.assertEqual(
                csv_row, {field: expected.get(field, "") for field in all_fields}
            )
            self.assertEqual(
                {field: json.loads(value) for field, value in csv_row.items() if value},
                {field: json.loads(value) for field, value in expected.items()},
            )

        config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
        expected = json.loads((CASE / "expected.json").read_text(encoding="utf-8"))
        self.assertEqual(config["task032_anchor"]["degree"], 2)
        self.assertEqual(config["task032_anchor"]["h_nm"], 3.0)
        self.assertEqual(
            expected["default_decision_counts"], checked["decision_counts"]
        )
        self.assertFalse(expected["claims"]["pde_run_performed"])
        self.assertFalse(expected["claims"]["proves_0p7nm_feasible"])

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            scaled_gate_limits(0.0)
        with self.assertRaises(ValueError):
            project_resources(5, 3.0)
        with self.assertRaises(ValueError):
            project_resources(2, 0.0)
        with self.assertRaises(ValueError):
            build_resource_matrix(conditional_clean_records=("p9_h9",))
        with self.assertRaises(ValueError):
            build_resource_matrix(qualified_high_order_degrees=(2,))
        self.assertEqual(nedelec_hex_local_dimension(2), 54)
        self.assertEqual(
            {
                matrix_key(degree, h_nm)
                for degree in (1, 2, 3, 4)
                for h_nm in (5.0, 3.0, 2.5, 2.0, 1.5)
            },
            {entry["matrix_key"] for entry in self._matrix()["entries"]},
        )


if __name__ == "__main__":
    unittest.main()
