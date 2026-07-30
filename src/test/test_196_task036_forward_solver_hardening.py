from __future__ import annotations

from unittest import mock
import unittest

import numpy as np

from benchmarks.task032_final_gates import _all_formal_true
from src.solvers.common_3d_utils import (
    _complete_rank_max,
    _complete_rank_sum,
    _gather_optional_rank_floats,
    _log_solver_summary,
    _trim_process_heap,
)
from src.solvers.dtn_port_3d import _dof_row_semantics
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedDirectSolution,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    HybridModalSchurDirectSystem,
)


class Task036ForwardSolverHardeningTests(unittest.TestCase):
    def test_diagnostic_gate_cannot_veto_or_qualify_formal_result(self) -> None:
        self.assertTrue(
            _all_formal_true(
                {
                    "formal_exact_dual": True,
                    "diagnostic_sampled_proxy": False,
                }
            )
        )
        self.assertFalse(
            _all_formal_true(
                {
                    "formal_exact_dual": False,
                    "diagnostic_sampled_proxy": True,
                }
            )
        )

    def test_optional_rank_rss_collection_never_branches_on_local_none(
        self,
    ) -> None:
        comm = mock.Mock()
        comm.allgather.return_value = [10.0, None, 30.0]
        values = _gather_optional_rank_floats(comm, 10.0)
        self.assertEqual(values, [10.0, None, 30.0])
        comm.allgather.assert_called_once_with(10.0)
        self.assertIsNone(_complete_rank_max(values))
        self.assertIsNone(_complete_rank_sum(values))
        self.assertEqual(_complete_rank_max([10.0, 30.0]), 30.0)
        self.assertEqual(_complete_rank_sum([10.0, 30.0]), 40.0)

    def test_dof_row_semantics_separate_space_and_matrix_counts(self) -> None:
        fields = _dof_row_semantics(
            active_exact_sequence_fe_dofs=80,
            storage_carrier_fe_dofs=120,
            independent_trace_rows=50,
            augmented_rows=62,
            auxiliary_rows=12,
        )
        self.assertEqual(fields["num_active_exact_sequence_fe_dofs"], 80)
        self.assertEqual(fields["num_storage_carrier_fe_dofs"], 120)
        self.assertEqual(fields["num_independent_trace_rows"], 50)
        self.assertEqual(fields["num_augmented_rows"], 62)
        with self.assertRaisesRegex(ValueError, "storage carrier"):
            _dof_row_semantics(
                active_exact_sequence_fe_dofs=121,
                storage_carrier_fe_dofs=120,
                independent_trace_rows=50,
                augmented_rows=62,
                auxiliary_rows=12,
            )
        with self.assertRaisesRegex(ValueError, "must equal"):
            _dof_row_semantics(
                active_exact_sequence_fe_dofs=80,
                storage_carrier_fe_dofs=120,
                independent_trace_rows=50,
                augmented_rows=63,
                auxiliary_rows=12,
            )

    def test_malloc_trim_zero_is_completed_without_pages_returned(self) -> None:
        class FakeTrim:
            argtypes = None
            restype = None

            def __call__(self, _padding):
                return 0

        library = mock.Mock()
        library.malloc_trim = FakeTrim()
        with (
            mock.patch("ctypes.CDLL", return_value=library),
            mock.patch(
                "src.solvers.common_3d_utils._current_rss_mb",
                side_effect=(100.0, 100.0),
            ),
        ):
            audit = _trim_process_heap()
        self.assertTrue(audit["supported"])
        self.assertTrue(audit["succeeded"])
        self.assertTrue(audit["call_completed"])
        self.assertFalse(audit["allocator_reported_pages_released"])
        self.assertEqual(audit["return_code"], 0)

    def test_solver_log_calls_historical_upper_bound_by_its_scope(self) -> None:
        lines: list[str] = []
        _log_solver_summary(
            {
                "stage4_full3d_assembly_backend_requested": "standard_full",
                "linear_solve_method": "direct_lu",
                "actual_ksp_type": "preonly",
                "actual_pc_type": "lu",
                "actual_pc_factor_solver_type": "mumps",
                "ksp_converged": True,
                "ksp_converged_reason": 4,
                "ksp_converged_reason_name": "CONVERGED",
                "ksp_iterations": 1,
                "solver_residual_norm": 1.0e-12,
                "max_rss_mb": 100.0,
                "total_peak_rss_mb": 999.0,
                "sum_rank_historical_peaks_mb_upper_bound": 200.0,
                "official_result": True,
                "diagnostic_only": False,
                "case_status": "completed",
            },
            lines.append,
        )
        text = "\n".join(lines)
        self.assertIn("max rank historical RSS", text)
        self.assertIn("sum rank historical peaks upper bound = 200.0 MB", text)
        self.assertNotIn("total peak RSS", text)

    def test_augmented_solution_factor_release_is_idempotent(self) -> None:
        x = mock.Mock()
        ksp = mock.Mock()
        bottom = mock.Mock()
        top = mock.Mock()
        solution = HybridAugmentedDirectSolution(
            x=x,
            ksp=ksp,
            bottom=bottom,
            top=top,
            modal_amplitudes=np.zeros(2, dtype=np.complex128),
            relative_residual=0.0,
            setup_seconds=0.0,
            solve_seconds=0.0,
            converged_reason=1,
        )
        first = solution.release_factorization()
        second = solution.release_factorization()
        self.assertTrue(first["released"])
        self.assertTrue(second["already_released"])
        x.destroy.assert_called_once()
        ksp.destroy.assert_called_once()
        self.assertIsNone(solution.x)
        self.assertIsNone(solution.ksp)
        self.assertIs(solution.bottom, bottom)
        self.assertIs(solution.top, top)
        np.testing.assert_array_equal(
            solution.modal_amplitudes,
            np.zeros(2, dtype=np.complex128),
        )
        solution.destroy()
        solution.destroy()
        bottom.destroy.assert_called_once()
        top.destroy.assert_called_once()

    def test_modal_schur_destroy_clears_factor_handles(self) -> None:
        bottom_factor = mock.Mock()
        top_factor = mock.Mock()
        system = HybridModalSchurDirectSystem(
            modal_schur=np.eye(2, dtype=np.complex128),
            modal_rhs=np.zeros(2, dtype=np.complex128),
            modal_constraint=np.eye(2, dtype=np.complex128),
            bottom_contribution=np.eye(2, dtype=np.complex128),
            top_contribution=np.eye(2, dtype=np.complex128),
            bottom_factor=bottom_factor,
            top_factor=top_factor,
            factor_setup_seconds={},
            multi_rhs_solve_seconds={},
            multi_rhs_count=1,
            transient_dense_rhs_solution_bytes={},
            factor_inventory={},
            modal_schur_condition=1.0,
        )
        system.destroy()
        system.destroy()
        bottom_factor.destroy.assert_called_once()
        top_factor.destroy.assert_called_once()
        self.assertIsNone(system.bottom_factor)
        self.assertIsNone(system.top_factor)


if __name__ == "__main__":
    unittest.main()
