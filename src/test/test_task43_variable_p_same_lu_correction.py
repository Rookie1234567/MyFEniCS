from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.variable_p_degree_plan import (
    cell_box_catalog,
    variable_p_cell_degree_plan_payload,
)
from src.common.config_3d import ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers import dtn_port_3d
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


class Task43VariablePSameLUMicroFixture(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MYFENICS_RUN_TASK43_SAME_LU_CORRECTION_PDE") == "1",
        "explicit opt-in small mixed-p variable-p PDE correction fixture",
    )
    def test_mixed_p4_p5_correction_precedes_recovery_and_live_gate(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size != 1:
            self.skipTest("same-LU variable-p correction is qualified only for MPI1")

        fixture_root = Path(
            os.environ.get(
                "TASK43_SAME_LU_CORRECTION_FIXTURE_ROOT",
                tempfile.mkdtemp(prefix="task43_same_lu_correction_mpi1_"),
            )
        ).resolve()
        fixture_root.mkdir(parents=True, exist_ok=True)
        print(
            "[TASK43-SAME-LU] component fixture only; not Task43 accuracy evidence "
            f"root={fixture_root}",
            flush=True,
        )

        cfg = task43_initial_profile(
            case_name="task43_same_lu_correction_mixed_p4_p5_component"
        )
        cfg.mesh_plan_id = None
        cfg.mesh_plan_sha256 = None
        cfg.mesh_axis_cell_counts = None
        cfg.mesh_axis_x_values = None
        cfg.mesh_axis_y_values = None
        cfg.mesh_axis_z_values = None
        cfg.mesh_axis_z_profile = None
        cfg.mesh_spacing_mode = "boundary_fitted"
        cfg.mesh_target_size = 180.0
        cfg.stage4_dtn_order_policy = "zero_order"
        cfg.diffraction_zero_order_only = False
        # Restrict only generic probe reporting here. The DtN solve itself
        # still uses its unchanged four-channel zero-order inventory.
        cfg.reporting_diffraction_order_max_m = 0
        cfg.reporting_diffraction_order_max_n = 0
        cfg.stage4_full3d_assembly_backend = (
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        )
        cfg.stage4_variable_p_cell_degree_plan = None
        cfg.matrix_diagnostics_assemble_only = False
        cfg.matrix_diagnostics_factorization_only = False
        cfg.unique_output = False

        mesh_data = build_airbox_mesh_3d(cfg, fixture_root / "mesh")
        boxes = cell_box_catalog(mesh_data.mesh)
        z_midpoint = 0.5 * (cfg.z_min + cfg.z_max)
        degree_by_box = {
            box: 4 if 0.5 * (box[2] + box[5]) < z_midpoint else 5
            for box in boxes
        }
        degree_histogram = Counter(degree_by_box.values())
        if set(degree_histogram) != {4, 5}:
            self.skipTest(
                "boundary-fitted component mesh did not resolve both mixed degrees: "
                f"{dict(degree_histogram)}"
            )
        plan = variable_p_cell_degree_plan_payload(
            mesh_data.mesh,
            degree_by_box,
            provenance={
                "purpose": "Task43 same-LU correction call-order component fixture",
                "physics_profile": "phi90 SI 13.5 nm, zero-order ports",
                "mesh_role": "small boundary-fitted component mesh",
                "active_degree_histogram": dict(sorted(degree_histogram.items())),
                "degree_split_axis": "z (non-periodic)",
                "formal_candidate": False,
            },
        )
        plan_path = fixture_root / "mixed_p4_p5_degree_plan.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        cfg.stage4_variable_p_cell_degree_plan = str(plan_path)

        injected_solution: dict[str, np.ndarray] = {}
        original_solve = dtn_port_3d._solve_augmented_system

        def solve_then_perturb(*args, **kwargs):
            x, ksp, telemetry = original_solve(*args, **kwargs)
            values = x.getArray()
            if values.size == 0:
                raise AssertionError("MPI1 augmented vector unexpectedly has no rows")
            values[0] += PETSc.ScalarType(1.0e-6 - 0.5e-6j)
            injected_solution["values"] = values.copy()
            return x, ksp, telemetry

        captured: dict[str, object] = {}

        def observer(view) -> None:
            captured["view_solution"] = view.x.getArray(readonly=True).copy()
            captured["full_active_residual"] = dict(view.full_active_residual)
            captured["mode_count"] = len(view.goal_context["modes"])
            captured["independent_active_action"] = (
                dtn_port_3d.compute_stage4_independent_active_action(view)
            )
            self.assertGreater(view.primal_solver_telemetry["converged_reason"], 0)
            self.assertLessEqual(
                float(view.full_active_residual["linear_system_relative_residual"]),
                1.0e-9,
            )
            self.assertTrue(view.port_operator_audit["pass"])

        with patch.object(
            dtn_port_3d, "_solve_augmented_system", side_effect=solve_then_perturb
        ):
            summary = run_stage4b_block_grating_3d_case(
                cfg,
                fixture_root / "solve",
                variable_p_live_observer=observer,
                variable_p_single_lu_residual_correction=True,
                mesh_data_override=mesh_data,
            )

        report = summary["variable_p_same_lu_residual_correction"]
        self.assertEqual(summary["case_status"], "completed")
        self.assertTrue(summary["variable_p_live_observer_invoked"])
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["solution_updated"])
        self.assertGreater(report["initial_condensed_relative_to_rhs"], 1.0e-9)
        self.assertLessEqual(
            report["corrected_condensed_relative_to_rhs"], 1.0e-9
        )
        self.assertGreater(report["original_primal_ksp"]["converged_reason"], 0)
        self.assertGreater(report["correction_ksp"]["converged_reason"], 0)
        self.assertGreater(report["elapsed_seconds"], 0.0)
        self.assertFalse(
            np.array_equal(
                injected_solution["values"], captured["view_solution"]
            )
        )
        self.assertEqual(captured["mode_count"], 4)
        a6 = captured["independent_active_action"]
        self.assertTrue(a6["full_solver_gauge_residual"]["finite"])
        self.assertLessEqual(
            a6["full_solver_gauge_residual"]["relative_to_independent_rhs"],
            1.0e-6,
        )
        self.assertTrue((fixture_root / "solve" / "dtn_port_power_metrics_3d.json").is_file())


if __name__ == "__main__":
    unittest.main()
