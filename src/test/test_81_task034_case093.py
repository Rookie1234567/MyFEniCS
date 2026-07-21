from __future__ import annotations

import unittest

from benchmarks.task034_case093 import (
    Case093Error,
    PHYSICAL_KEYS,
    VECTOR_KEYS,
    _degree_decision,
    _physical_identity,
    _validate_compact_convergence,
    _validate_compact_mpi,
)


def _method(method: str, degree: int, h_nm: float) -> dict:
    return {
        "method": method,
        "degree": degree,
        "h_nm": h_nm,
        "polarization_kind": "s",
        "mpi_size": 8,
        "status": "measured_pass",
        "qualified": True,
        "source": {"commit_sha": "a" * 40, "clean": True, "stable": True},
        "true_relative_residual": 1.0e-11,
        "official_values": {
            "R_total": 0.01,
            "T_total": 0.59,
            "A_balance": 0.4,
            "A_volume_total": 0.4,
        },
        "resource": {"no_swap": True},
        "evidence": {"path": "ignored.json", "sha256": "b" * 64},
    }


def _convergence_record() -> dict:
    points = []
    decisions = []
    meshes = {2: (5.0, 3.0, 2.0), 3: (7.5, 5.0, 3.0), 4: (10.0, 7.5, 5.0)}
    for degree, h_values in meshes.items():
        keys = []
        for h_nm in h_values:
            suffix = str(h_nm).replace(".", "p")
            key = f"p{degree}_h{suffix}"
            keys.append(key)
            points.append(
                {
                    "key": key,
                    "full3d": _method("full3d", degree, h_nm),
                    "hybrid": _method("hybrid", degree, h_nm),
                    "same_degree_closure": {
                        "status": "same_degree_closure_pass",
                        "pass": True,
                        "observable_vector": {name: 1.0e-6 for name in VECTOR_KEYS},
                    },
                }
            )
        decisions.append(
            {
                "degree": degree,
                "successful_same_degree_points": keys,
                "successful_count": 3,
                "measured_sequence_decision": True,
                "observed_convergence_order_status": "convergence_order_not_established",
                "coarse_to_middle_delta": {name: 2.0 for name in VECTOR_KEYS},
                "middle_to_fine_delta": {name: 1.0 for name in VECTOR_KEYS},
                "componentwise_delta_reduction": {name: True for name in VECTOR_KEYS},
                "all_twelve_components_reduce": True,
            }
        )
    identity = {key: f"value-{key}" for key in PHYSICAL_KEYS}
    identity["polarization_kind"] = "s"
    return {
        "schema_version": "task034.case093.convergence.v1",
        "record_type": "fixed_geometry_ph_convergence_and_same_degree_closure",
        "status": "measured_decisions_complete",
        "physical_identity": identity,
        "points": points,
        "degree_decisions": decisions,
        "selected_discrete_reference": {
            "key": "p4_h5",
            "continuum_reference": False,
        },
    }


def _mpi_record() -> dict:
    methods = {}
    for method in ("full3d", "hybrid"):
        methods[method] = {
            "status": "qualified",
            "checks": {
                "required_mpi_sizes_present_once": True,
                "no_oversubscription": True,
                "all_numerical_identity_rows_pass": True,
            },
            "comparisons": [
                {
                    "mpi_size": size,
                    "checks": {
                        "official_result_identity": True,
                        "true_residual_le_1e-9": True,
                        "rta_and_a_volume_absolute_drift_le_1e-8": True,
                    },
                }
                for size in (1, 8, 16, 32)
            ],
        }
    return {
        "schema_version": "task034.case093.mpi-identity.v1",
        "required_mpi_sizes": [1, 8, 16],
        "exploratory_mpi_sizes": [32],
        "methods": methods,
    }


class Task034Case093Tests(unittest.TestCase):
    def test_compact_checker_recomputes_success_count(self) -> None:
        record = _convergence_record()
        self.assertEqual(_validate_compact_convergence(record), [])
        record["status"] = "forged_status_is_not_authority"
        record["degree_decisions"][0]["successful_count"] = 9
        failures = _validate_compact_convergence(record)
        self.assertIn("p2_successful_count_recompute", failures)

    def test_polarization_identity_cannot_be_mixed(self) -> None:
        record = _convergence_record()
        record["points"][0]["hybrid"]["polarization_kind"] = "p"
        failures = _validate_compact_convergence(record)
        self.assertTrue(any(name.endswith("hybrid_polarization") for name in failures))

    def test_complete_twelve_component_closure_vector_is_required(self) -> None:
        record = _convergence_record()
        del record["points"][0]["same_degree_closure"]["observable_vector"][VECTOR_KEYS[0]]
        failures = _validate_compact_convergence(record)
        self.assertTrue(any(name.endswith("closure_vector") for name in failures))

    def test_nonmonotonic_component_is_preserved_not_deleted(self) -> None:
        record = _convergence_record()
        decision = record["degree_decisions"][0]
        key = VECTOR_KEYS[0]
        decision["middle_to_fine_delta"][key] = 3.0
        decision["componentwise_delta_reduction"][key] = False
        decision["all_twelve_components_reduce"] = False
        self.assertEqual(_validate_compact_convergence(record), [])
        self.assertEqual(decision["successful_count"], 3)

    def test_forged_monotonic_flag_fails_recomputation(self) -> None:
        record = _convergence_record()
        decision = record["degree_decisions"][0]
        decision["middle_to_fine_delta"][VECTOR_KEYS[0]] = 3.0
        failures = _validate_compact_convergence(record)
        self.assertIn("p2_reduction_recompute", failures)

    def test_less_than_three_points_never_reports_observed_order(self) -> None:
        points = [
            {
                "key": f"p2_h{index}",
                "full": {"degree": 2, "h_nm": float(index), "qualified": True},
                "closure": {"pass": True},
            }
            for index in (3, 2)
        ]
        decision = _degree_decision(2, points)
        self.assertEqual(decision["successful_count"], 2)
        self.assertFalse(decision["measured_sequence_decision"])
        self.assertEqual(
            decision["observed_convergence_order_status"],
            "convergence_order_not_established",
        )

    def test_degree_decision_does_not_mix_p_values(self) -> None:
        points = [
            {
                "key": f"p{degree}_h{index}",
                "full": {"degree": degree, "h_nm": float(index), "qualified": True},
                "closure": {"pass": True},
            }
            for degree in (2, 3)
            for index in (3, 2)
        ]
        self.assertEqual(_degree_decision(2, points)["successful_count"], 2)

    def test_mpi16_and_global_oversubscription_gate_are_authoritative(self) -> None:
        record = _mpi_record()
        self.assertEqual(_validate_compact_mpi(record), [])
        record["methods"]["hybrid"]["checks"]["no_oversubscription"] = False
        record["methods"]["full3d"]["comparisons"] = [
            row
            for row in record["methods"]["full3d"]["comparisons"]
            if row["mpi_size"] != 16
        ]
        failures = _validate_compact_mpi(record)
        self.assertIn("hybrid_global_checks", failures)
        self.assertIn("full3d_sizes", failures)

    def test_mpi_numerical_drift_failure_cannot_be_relabelled(self) -> None:
        record = _mpi_record()
        record["methods"]["full3d"]["comparisons"][2]["checks"][
            "rta_and_a_volume_absolute_drift_le_1e-8"
        ] = False
        self.assertIn("full3d_mpi16_identity", _validate_compact_mpi(record))

    def test_fixed_geometry_identity_is_fail_closed(self) -> None:
        config = {key: 1 for key in PHYSICAL_KEYS}
        del config["lambda0"]
        with self.assertRaises(Case093Error):
            _physical_identity(config)


if __name__ == "__main__":
    unittest.main()
