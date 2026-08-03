from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import numpy as np

from src.common.config_3d import SimulationConfig3D
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_utils import (
    _complete_rank_max,
    _complete_rank_sum,
    _gather_optional_rank_floats,
    _log_solver_summary,
    _trim_process_heap,
)
from src.solvers.dtn_port_3d import (
    _dof_row_semantics,
    _variable_p_active_fe_dofs,
)
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
)
from src.solvers.hcurl_variable_p_assembly import (
    VariablePCondensedTraceSystem,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedDirectSolution,
)


class Task036ForwardSolverHardeningTests(unittest.TestCase):
    def test_new_projection_and_alias_guards_are_opt_in(self) -> None:
        defaults = {item.name: item.default for item in fields(SimulationConfig3D)}
        self.assertIs(defaults["dtn_y_invariant_n0_alias_preflight"], False)
        self.assertIs(defaults["dtn_auxiliary_direct_projection_audit"], False)

    def test_explicit_axis_counts_cannot_silently_change(self) -> None:
        cfg = SimpleNamespace(
            geometry_kind="airbox",
            mesh_cell_type_resolved="tetrahedron",
            mesh_cells=(3, 3, 3),
            mesh_axis_cell_counts_requested=(4, 3, 3),
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch(
                "src.geometry.mesh_builder_3d._z_alignment_warnings",
                return_value=[],
            ),
            self.assertRaisesRegex(RuntimeError, "requested=.*actual="),
        ):
            build_airbox_mesh_3d(cfg, Path(tmp))

    def test_dof_row_semantics_and_variable_p_legacy_alias(self) -> None:
        fields_out = _dof_row_semantics(
            active_exact_sequence_fe_dofs=80,
            storage_carrier_fe_dofs=120,
            independent_trace_rows=50,
            augmented_rows=62,
            auxiliary_rows=12,
        )
        self.assertEqual(fields_out["num_active_exact_sequence_fe_dofs"], 80)
        self.assertEqual(fields_out["num_storage_carrier_fe_dofs"], 120)
        self.assertEqual(fields_out["num_independent_trace_rows"], 50)
        self.assertEqual(fields_out["num_augmented_rows"], 62)
        self.assertEqual(
            _variable_p_active_fe_dofs({"actual_conforming_active_fe_dofs": 80}),
            80,
        )
        self.assertEqual(
            _variable_p_active_fe_dofs({"actual_full3d_equivalent_active_fe_dofs": 79}),
            79,
        )
        with self.assertRaisesRegex(ValueError, "must equal"):
            _dof_row_semantics(
                active_exact_sequence_fe_dofs=80,
                storage_carrier_fe_dofs=120,
                independent_trace_rows=50,
                augmented_rows=63,
                auxiliary_rows=12,
            )

    def test_malloc_trim_zero_is_a_completed_call(self) -> None:
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
        self.assertTrue(audit["succeeded"])
        self.assertTrue(audit["call_completed"])
        self.assertFalse(audit["allocator_reported_pages_released"])

    def test_optional_rank_memory_values_keep_collectives_aligned(self) -> None:
        comm = mock.Mock()
        comm.allgather.return_value = [10.0, None, 30.0]
        values = _gather_optional_rank_floats(comm, 10.0)
        self.assertEqual(values, [10.0, None, 30.0])
        self.assertIsNone(_complete_rank_max(values))
        self.assertIsNone(_complete_rank_sum(values))
        self.assertEqual(_complete_rank_max([10.0, 30.0]), 30.0)
        self.assertEqual(_complete_rank_sum([10.0, 30.0]), 40.0)

    def test_memory_log_names_historical_upper_bound(self) -> None:
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

    def test_augmented_factor_release_is_idempotent_and_fields_survive(self) -> None:
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
        self.assertIs(solution.bottom_physical, bottom)
        self.assertIs(solution.top_physical, top)
        solution.destroy()
        solution.destroy()
        bottom.destroy.assert_called_once()
        top.destroy.assert_called_once()

    def test_condensed_system_destroy_methods_are_idempotent(self) -> None:
        assembly = object.__new__(AssemblyTimeCondensedSystem)
        assembly.matrix = mock.Mock()
        assembly._destroyed = False
        assembly.destroy()
        assembly.destroy()
        assembly.matrix.destroy.assert_called_once()

        variable = object.__new__(VariablePCondensedTraceSystem)
        variable.matrix = mock.Mock()
        variable._destroyed = False
        variable.release_retained_local_schur = mock.Mock()
        variable.destroy()
        variable.destroy()
        variable.release_retained_local_schur.assert_called_once()
        variable.matrix.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
