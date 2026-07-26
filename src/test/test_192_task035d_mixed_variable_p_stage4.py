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


class Task035dMixedVariablePStage4Tests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MYFENICS_RUN_TASK035D_MIXED_PDE_FIXTURE") == "1",
        "explicit opt-in mixed-p Stage4 PDE fixture",
    )
    def test_periodic_p5_p6_plan_closes_serial_and_mpi2(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size not in {1, 2}:
            self.skipTest("mixed-p Stage4 fixture qualifies serial/MPI2")
        root = Path(
            f"/tmp/task035d_mixed_p5_p6_dtn_smoke_mpi{comm.size}"
        )
        base = replace(
            target_stage4_config(degree=6, h_nm=100.0),
            case_name=(
                f"task035d_mixed_p5_p6_dtn_smoke_mpi{comm.size}"
            ),
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            direct_release_base_after_augmentation=True,
            direct_release_solver_before_postprocess=True,
            unique_output=False,
        )
        mesh_data = build_airbox_mesh_3d(base, root / "mesh")
        boxes = cell_box_catalog(mesh_data.mesh)
        z_midpoint = 0.5 * (
            min(box[2] for box in boxes)
            + max(box[5] for box in boxes)
        )
        degrees = {
            box: 6 if 0.5 * (box[2] + box[5]) >= z_midpoint else 5
            for box in boxes
        }
        self.assertEqual(set(degrees.values()), {5, 6})
        payload = variable_p_cell_degree_plan_payload(
            mesh_data.mesh,
            degrees,
            provenance={
                "purpose": (
                    "Task035d mixed-p Stage4 component qualification"
                ),
                "policy": (
                    "z-layer periodic p5/p6 split; no accuracy credit"
                ),
                "formal_candidate": False,
                "ordinary_default_changed": False,
            },
        )
        plan_path = root / "mixed_p5_p6_degree_plan.json"
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
        self.assertTrue(summary["stage4_variable_p_active"])
        self.assertEqual(
            summary["stage4_full3d_assembly_backend_actual"],
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        )
        self.assertLessEqual(
            summary["linear_system_relative_residual"],
            1.0e-9,
        )
        self.assertTrue(
            summary["stage4_dtn_variable_p_trace_only_gate_pass"]
        )
        self.assertFalse(
            summary[
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            ]
        )
        self.assertEqual(
            summary[
                "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
            ],
            0,
        )
        audit = summary["cell_static_condensation"]
        self.assertEqual(
            audit["degree_plan"]["cell_degree_counts"],
            {
                "p4": 0,
                "p5": sum(degree == 5 for degree in degrees.values()),
                "p6": sum(degree == 6 for degree in degrees.values()),
            },
        )
        self.assertTrue(audit["active_fe_dof_gate_pass"])
        self.assertLess(
            summary["num_actual_conforming_active_fe_dofs"],
            summary["num_nedelec_dofs"],
        )
        self.assertEqual(
            summary["matrix_stats"]["matrix_rows"],
            summary["num_active_condensed_dofs"],
        )
        self.assertEqual(summary["matrix_stats"]["matrix_mallocs"], 0.0)
        self.assertFalse(audit["full_p6_global_matrix_allocated"])
        self.assertFalse(audit["inactive_p6_rows_globally_numbered"])
        self.assertFalse(audit["ordinary_default_changed"])


if __name__ == "__main__":
    unittest.main()
