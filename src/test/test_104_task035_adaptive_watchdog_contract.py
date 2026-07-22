from __future__ import annotations

from argparse import Namespace
import inspect
import json
import math
from pathlib import Path
import unittest

from benchmarks.run_task035_actual_r5 import _qualify_adaptive
from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5
from src.adaptivity.target_r5_adaptive_cycles import (
    task034_best_available_observable_reference,
)
from src.solvers.common_3d_case_flow import run_prepared_3d_case_flow
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


ROOT = Path(__file__).resolve().parents[2]
INITIAL_RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_r5_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json"
)
SECOND_STOP_RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_r5_adaptive_tetra_p2_p3_h50_cycle2_reference_gate_mpi2.json"
)


def _adaptive_result() -> dict:
    summary = {
        "official_result": True,
        "linear_system_relative_residual": 1.0e-12,
        "mesh_cell_type_actual": "tetrahedron",
    }
    estimate = {
        "correction_energy": {"relative_closure_error": 1.0e-14},
        "marking": {"captured_fraction": 0.51},
    }
    return {
        "status": "actual_r5_adaptive_cycles_pass",
        "pass": True,
        "ordinary_default_changed": False,
        "marked_cycles_completed": 1,
        "fixed_observable_reference": {
            "identity": "best_available_discrete_reference_for_case093",
            "record_sha256": "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111",
        },
        "all_fixed_reference_error_reductions_positive": True,
        "cycles": [
            {
                "mesh_audit": {"pass": True},
                "actual_r5": {
                    "coarse": {"summary": summary},
                    "enriched": {"summary": summary},
                    "R5": estimate,
                },
            }
            for _ in range(2)
        ],
        "refinements": [{"pass": True}],
    }


class Task035AdaptiveWatchdogContractTests(unittest.TestCase):
    @staticmethod
    def _norm(vector: dict[str, float], reference: dict[str, float]) -> float:
        return math.sqrt(sum((vector[key] - reference[key]) ** 2 for key in reference))

    def test_mesh_override_is_explicit_and_default_off(self) -> None:
        for function in (
            run_prepared_3d_case_flow,
            run_stage4b_block_grating_3d_case,
            run_target_global_two_level_r5,
        ):
            parameter = inspect.signature(function).parameters[
                "mesh_data_override"
            ]
            self.assertIsNone(parameter.default)

    def test_adaptive_qualification_requires_measured_reduction(self) -> None:
        args = Namespace(
            mpi_size=2,
            theta=0.5,
            adaptive_marked_cycles=1,
        )
        sampler = {
            "max_observed_worker_rank_count": 2,
            "max_process_tree_swap_mb": 0.0,
        }
        result = _adaptive_result()
        qualified = _qualify_adaptive(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualified["pass"])
        result["all_fixed_reference_error_reductions_positive"] = False
        failed = _qualify_adaptive(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn(
            "all_fixed_reference_error_reductions_positive",
            failed["failures"],
        )

    def test_initial_moving_gap_failure_has_positive_fixed_reference_signal(self) -> None:
        reference = task034_best_available_observable_reference()
        self.assertEqual(reference["key"], "p4_h5")
        self.assertFalse(reference["continuum_reference"])
        record = json.loads(INITIAL_RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "formal_not_pass")
        cycle0, cycle1 = record["cycles"]
        coarse0 = self._norm(
            cycle0["coarse_observables"], reference["observables"]
        )
        coarse1 = self._norm(
            cycle1["coarse_observables"], reference["observables"]
        )
        enriched0 = self._norm(
            cycle0["enriched_observables"], reference["observables"]
        )
        enriched1 = self._norm(
            cycle1["enriched_observables"], reference["observables"]
        )
        self.assertLess(coarse1, coarse0)
        self.assertLess(enriched1, enriched0)
        self.assertGreater(
            cycle1["official_observable_delta_l2"],
            cycle0["official_observable_delta_l2"],
        )
        self.assertEqual(
            record["qualification"]["failures"],
            [
                "result_status",
                "result_pass",
                "all_observable_error_reductions_positive",
            ],
        )

    def test_second_refinement_periodic_propagation_stop_is_preserved(self) -> None:
        record = json.loads(SECOND_STOP_RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "formal_not_pass")
        self.assertTrue(record["all_fixed_reference_error_reductions_positive"])
        self.assertEqual(len(record["cycles"]), 2)
        self.assertEqual(len(record["refinements"]), 2)
        failed = record["refinements"][1]
        audit = failed["refined_mesh_audit"]
        self.assertFalse(failed["pass"])
        self.assertEqual(audit["orientation"]["nonpositive_count"], 0)
        self.assertGreater(audit["shape_quality"]["quantiles"]["minimum"], 0.0)
        self.assertFalse(audit["periodic_x"]["pass"])
        self.assertFalse(audit["periodic_y"]["pass"])
        self.assertEqual(failed["parent_global_cells"], 1142)
        self.assertEqual(failed["refined_global_cells"], 6560)
        self.assertIn(
            "all_refinement_audits_pass",
            record["qualification"]["failures"],
        )


if __name__ == "__main__":
    unittest.main()
