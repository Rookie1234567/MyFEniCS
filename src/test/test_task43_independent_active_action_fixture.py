from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.variable_p_degree_plan import (
    cell_box_catalog,
    variable_p_cell_degree_plan_payload,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.dtn_port_3d import compute_stage4_independent_active_action
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


class Task43IndependentActiveActionFixture(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MYFENICS_RUN_TASK43_A6_SMALL_FIXTURE") == "1",
        "explicit opt-in Task43 A6 small physical fixture",
    )
    def test_phi90_h100_p3_r13_active_action(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size != 1:
            self.skipTest("this component fixture qualifies one direct MPI rank")

        root = Path(
            os.environ.get(
                "TASK43_A6_FIXTURE_ROOT",
                "/tmp/task43_a6_phi90_h100_p3_r13_fixture_mpi1",
            )
        )
        if comm.rank == 0:
            root.mkdir(parents=True, exist_ok=True)
            print(f"[TASK43-A6] fixture_root={root}", flush=True)
        comm.Barrier()
        cfg = task43_initial_profile(case_name="task43_a6_small_component_fixture")
        # This fixture qualifies the Task43 physics and residual path on the
        # standard boundary-fitted h=100 nm interface mesh.  It deliberately
        # does not reuse the frozen 3x10x6 Task43 starting axes.
        cfg.mesh_plan_id = None
        cfg.mesh_plan_sha256 = None
        cfg.mesh_axis_cell_counts = None
        cfg.mesh_axis_x_values = None
        cfg.mesh_axis_y_values = None
        cfg.mesh_axis_z_values = None
        cfg.mesh_axis_z_profile = None
        cfg.mesh_spacing_mode = "boundary_fitted"
        cfg.mesh_target_size = 100.0

        if comm.rank == 0:
            print("[TASK43-A6] stage=mesh_build begin", flush=True)
        mesh_data = build_airbox_mesh_3d(cfg, root / "mesh")
        if comm.rank == 0:
            print(
                "[TASK43-A6] stage=mesh_build end "
                f"cells={mesh_data.mesh.topology.index_map(3).size_global} "
                f"axes={mesh_data.mesh_cells_resolved}",
                flush=True,
            )
        boxes = cell_box_catalog(mesh_data.mesh)
        plan = variable_p_cell_degree_plan_payload(
            mesh_data.mesh,
            {box: 3 for box in boxes},
            provenance={
                "purpose": "Task43 independent active action component fixture",
                "physics_profile": "phi90_si_13p5nm_r13_q15_q28",
                "mesh_role": "boundary-fitted h100 small component qualification",
                "active_degree": 3,
                "formal_candidate": False,
            },
        )
        plan_path = root / "uniform_p3_degree_plan.json"
        if comm.rank == 0:
            root.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        comm.Barrier()
        cfg.stage4_variable_p_cell_degree_plan = str(plan_path)
        captured: dict[str, object] = {}
        if comm.rank == 0:
            print("[TASK43-A6] stage=solve_and_independent_action begin", flush=True)

        def observer(view) -> None:
            captured["a6"] = compute_stage4_independent_active_action(view)
            captured["mode_count"] = len(view.goal_context["modes"])
            captured["condensed_residual"] = {
                key: float(view.full_active_residual[key])
                for key in (
                    "linear_system_residual_norm",
                    "linear_system_relative_residual",
                    "reduced_trace_dtn_residual_norm",
                    "eliminated_cell_interior_residual_norm",
                )
                if view.full_active_residual.get(key) is not None
            }

        summary = run_stage4b_block_grating_3d_case(
            cfg,
            root / "solve",
            variable_p_live_observer=observer,
            mesh_data_override=mesh_data,
        )
        if comm.rank == 0:
            print(
                "[TASK43-A6] stage=solve_and_independent_action end "
                f"status={summary['case_status']}",
                flush=True,
            )
        a6 = captured["a6"]
        record = {
            "classification": "component_qualification_not_task43_start_or_accuracy_claim",
            "case_name": cfg.case_name,
            "physics_profile": "Task43 phi90 SI 13.5 nm, R13, q15 volume, q28 ports",
            "mesh_role": "boundary-fitted h100 interface mesh, not frozen 3x10x6 start",
            "axis_cell_counts_xyz": list(mesh_data.mesh_cells_resolved),
            "mesh_spacing_mode_resolved": mesh_data.mesh_spacing_mode_resolved,
            "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
            "active_degree_plan": "uniform p3 on p6 storage carrier",
            "mode_count": captured["mode_count"],
            "solver_status": summary["case_status"],
            "condensed_residual": captured["condensed_residual"],
            "independent_active_action": a6,
        }
        if comm.rank == 0:
            (root / "independent_active_action_record.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        self.assertEqual(summary["case_status"], "completed")
        self.assertEqual(captured["mode_count"], 612)
        self.assertEqual(a6["rows"]["modal_lower"], 612)
        self.assertTrue(
            a6["full_solver_gauge_residual"]["task_gate_pass"],
            json.dumps(a6["full_solver_gauge_residual"], sort_keys=True),
        )
        self.assertTrue(
            a6["full_solver_gauge_residual"]["small_direct_target_pass"],
            json.dumps(a6["full_solver_gauge_residual"], sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
