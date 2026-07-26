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
        summary = run_stage4b_block_grating_3d_case(
            cfg,
            root / "solve",
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


if __name__ == "__main__":
    unittest.main()
