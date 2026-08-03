from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import unittest

from mpi4py import MPI

from src.adaptivity.variable_p_degree_plan import (
    cell_box_catalog,
    variable_p_cell_degree_plan_payload,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


class Task035dVariablePStage4SmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MYFENICS_RUN_TASK035D_PDE_FIXTURE") == "1",
        "explicit opt-in p6 Stage4 variable-p PDE fixture",
    )
    def test_uniform_p6_plan_closes_full_dtn_path(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size not in {1, 2}:
            self.skipTest("Task035d fixture qualifies serial and MPI2")
        root = Path(
            f"/tmp/task035d_variable_p_dtn_smoke_mpi{comm.size}"
        )
        base = replace(
            target_stage4_config(degree=6, h_nm=100.0),
            case_name=(
                f"task035d_variable_p_dtn_smoke_mpi{comm.size}"
            ),
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            direct_release_base_after_augmentation=True,
            direct_release_solver_before_postprocess=True,
            unique_output=False,
        )
        mesh_data = build_airbox_mesh_3d(base, root / "mesh")
        boxes = cell_box_catalog(mesh_data.mesh)
        payload = variable_p_cell_degree_plan_payload(
            mesh_data.mesh,
            {box: 6 for box in boxes},
            provenance={
                "purpose": "Task035d Stage4 component identity",
                "policy": "uniform_p6_degenerate_control",
                "formal_candidate": False,
            },
        )
        plan_path = root / "uniform_p6_degree_plan.json"
        if comm.rank == 0:
            root.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        comm.Barrier()
        cfg = replace(
            base,
            stage4_full3d_assembly_backend=(
                ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
            ),
            stage4_variable_p_cell_degree_plan=str(plan_path),
        )
        captured: dict[str, object] = {}

        def live_observer(view) -> None:
            self.assertGreater(view.A.getSize()[0], 0)
            self.assertEqual(view.A.getSize()[0], view.b.getSize())
            self.assertEqual(view.A.getSize()[1], view.x.getSize())
            self.assertGreater(view.ksp.getConvergedReason(), 0)
            self.assertFalse(view.recovered._destroyed)
            self.assertEqual(
                view.recovered.active_full_solution.getSize(),
                view.reduction.system.entity_map.active_rows,
            )
            self.assertEqual(
                view.recovered.active_full_rhs.getSize(),
                view.reduction.system.entity_map.active_rows,
            )
            self.assertLessEqual(
                view.full_active_residual[
                    "linear_system_relative_residual"
                ],
                1.0e-9,
            )
            self.assertEqual(
                view.goal_context["num_fem_dofs_after_mpc"]
                + len(view.goal_context["modes"]),
                view.A.getSize()[0],
            )
            self.assertTrue(view.port_operator_audit["pass"])
            self.assertTrue(
                view.port_operator_audit["checks"][
                    "removed_interior_is_qualified_roundoff"
                ]
            )
            self.assertLessEqual(
                view.port_operator_audit[
                    "removed_active_interior_over_threshold_max"
                ],
                1.0,
            )
            captured["recovered"] = view.recovered
            captured["port_operator_audit"] = dict(
                view.port_operator_audit
            )
            captured["primal_solver_telemetry"] = dict(
                view.primal_solver_telemetry
            )
            transpose_rhs = view.b.copy()
            transpose_solution = view.x.duplicate()
            try:
                view.ksp.solveTranspose(
                    transpose_rhs,
                    transpose_solution,
                )
                self.assertGreater(view.ksp.getConvergedReason(), 0)
            finally:
                transpose_solution.destroy()
                transpose_rhs.destroy()

        summary = run_stage4b_block_grating_3d_case(
            cfg,
            root / "solve",
            variable_p_live_observer=live_observer,
            mesh_data_override=mesh_data,
        )
        self.assertEqual(summary["case_status"], "completed")
        self.assertEqual(
            summary["stage4_full3d_assembly_backend_actual"],
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        )
        self.assertTrue(summary["stage4_variable_p_active"])
        self.assertTrue(
            summary["stage4_assembly_time_cell_static_condensation"]
        )
        self.assertLessEqual(
            summary["linear_system_relative_residual"],
            1.0e-9,
        )
        audit = summary["cell_static_condensation"]
        self.assertTrue(audit["active_fe_dof_gate_pass"])
        self.assertEqual(
            audit["actual_conforming_active_fe_dofs"],
            summary["num_nedelec_dofs"],
        )
        self.assertEqual(
            audit["actual_conforming_active_fe_dofs"],
            audit["actual_full3d_equivalent_active_fe_dofs"],
        )
        self.assertEqual(
            summary["num_active_exact_sequence_fe_dofs"],
            audit["actual_conforming_active_fe_dofs"],
        )
        self.assertGreaterEqual(
            summary["num_storage_carrier_fe_dofs"],
            summary["num_active_exact_sequence_fe_dofs"],
        )
        self.assertEqual(
            summary["num_augmented_rows"],
            summary["matrix_stats"]["matrix_rows"],
        )
        self.assertEqual(
            summary["num_augmented_rows"],
            summary["num_independent_trace_rows"]
            + summary["stage4_dtn_num_auxiliary_dofs"],
        )
        self.assertFalse(audit["full_p6_global_matrix_allocated"])
        self.assertFalse(audit["inactive_p6_rows_globally_numbered"])
        self.assertFalse(audit["ordinary_default_changed"])
        self.assertEqual(
            summary["matrix_stats"]["matrix_rows"],
            summary["num_active_condensed_dofs"],
        )
        self.assertEqual(
            summary["matrix_stats"]["matrix_mallocs"],
            0.0,
        )
        self.assertTrue(summary["variable_p_live_observer_requested"])
        self.assertTrue(summary["variable_p_live_observer_invoked"])
        self.assertTrue(captured["port_operator_audit"]["pass"])
        self.assertTrue(
            summary["solver_objects_released_before_postprocess"]
        )
        recovered = captured["recovered"]
        self.assertTrue(recovered._destroyed)
        primal = captured["primal_solver_telemetry"]
        self.assertEqual(
            summary["ksp_converged_reason"],
            primal["converged_reason"],
        )
        self.assertEqual(
            summary["ksp_iterations"],
            primal["iterations"],
        )
        self.assertEqual(
            summary["solver_residual_norm"],
            primal["residual_norm"],
        )


if __name__ == "__main__":
    unittest.main()
