from __future__ import annotations

from argparse import Namespace
import inspect
import unittest

from benchmarks.run_task035_actual_r5 import _qualify_adaptive
from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5
from src.solvers.common_3d_case_flow import run_prepared_3d_case_flow
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
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
        "all_observable_error_reductions_positive": True,
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
        result["all_observable_error_reductions_positive"] = False
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
            "all_observable_error_reductions_positive", failed["failures"]
        )


if __name__ == "__main__":
    unittest.main()
