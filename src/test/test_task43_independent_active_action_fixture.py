from __future__ import annotations

import json
import os
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity import h100_anchor
from benchmarks.task43_hp_adaptivity.compare_initial_to_references import (
    _actual_mesh_identity,
    _modal_comparison,
    _modal_identity,
)
from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.physical_g_error import physical_g_difference_metrics
from src.adaptivity.variable_p_degree_plan import (
    cell_box_catalog,
    variable_p_cell_degree_plan_payload,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.postprocessing.physical_field_comparison import weighted_vector_field_metrics
from src.solvers.dtn_port_3d import compute_stage4_independent_active_action
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


class Task43IndependentActiveActionFixture(unittest.TestCase):
    def test_direct_factor_backend_cli_and_configuration(self) -> None:
        for requested in ("default", "mumps"):
            arguments = ["--case", "native_p3_mpi1", "--run-root", "/tmp/cli-only"]
            if requested != "default":
                arguments.extend(["--direct-factor-backend", requested])
            with patch.object(h100_anchor, "_run", return_value={}) as run:
                self.assertEqual(h100_anchor.main(arguments), 0)
            forwarded = run.call_args.kwargs["direct_factor_backend"]
            self.assertEqual(forwarded, requested)
            cfg = task43_initial_profile()
            before = dict(cfg.petsc_extra_options or {})
            h100_anchor._configure_direct_factor_backend(cfg, forwarded)
            expected = dict(before)
            if requested == "mumps":
                expected["pc_factor_mat_solver_type"] = "mumps"
            self.assertEqual(dict(cfg.petsc_extra_options or {}), expected)

    @unittest.skipUnless(
        os.environ.get("MYFENICS_RUN_TASK43_DIRECT_BACKEND_PAIR") == "1",
        "explicit opt-in physical mixed-p direct backend pair",
    )
    def test_mixed_p4_p5_r13_petsc_mumps_pair(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size != 1:
            self.skipTest("this direct backend component qualifies one MPI rank")
        root = Path(os.environ["TASK43_DIRECT_BACKEND_PAIR_ROOT"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            self.fail(f"refusing to overwrite physical pair evidence: {root}")
        tolerance = 1.0e-8
        started = time.perf_counter()
        cfg = task43_initial_profile(case_name="task43_direct_backend_pair")
        for name in (
            "mesh_plan_id",
            "mesh_plan_sha256",
            "mesh_axis_cell_counts",
            "mesh_axis_x_values",
            "mesh_axis_y_values",
            "mesh_axis_z_values",
            "mesh_axis_z_profile",
        ):
            setattr(cfg, name, None)
        cfg.mesh_spacing_mode = "boundary_fitted"
        cfg.mesh_target_size = 100.0
        mesh_data = build_airbox_mesh_3d(cfg, root / "mesh")
        self.assertEqual(mesh_data.mesh.topology.index_map(3).size_global, 36)
        boxes = cell_box_catalog(mesh_data.mesh)
        midpoint = 0.5 * (cfg.z_min + cfg.z_max)
        degrees = {box: 4 if 0.5 * (box[2] + box[5]) < midpoint else 5 for box in boxes}
        self.assertEqual(set(degrees.values()), {4, 5})
        plan_path = root / "mixed_p4_p5_plan.json"
        plan_path.write_text(
            json.dumps(
                variable_p_cell_degree_plan_payload(
                    mesh_data.mesh,
                    degrees,
                    provenance={
                        "purpose": "direct backend component pair",
                        "formal_candidate": False,
                    },
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        cfg.stage4_variable_p_cell_degree_plan = str(plan_path)
        captures = {}
        records = {}
        for requested, expected in (("default", "petsc"), ("mumps", "mumps")):
            cfg.case_name = f"task43_direct_backend_pair_{expected}"
            h100_anchor._configure_direct_factor_backend(cfg, requested)
            captured = {}
            backend_started = time.perf_counter()
            print(
                f"[TASK43-DIRECT-PAIR] backend={expected} begin root={root}", flush=True
            )

            def observer(view, captured=captured) -> None:
                captured["actual_backend"] = view.ksp.getPC().getFactorSolverType()
                captured["a6"] = compute_stage4_independent_active_action(view)
                captured["condensed"] = dict(view.full_active_residual)
                captured["mode_count"] = len(view.goal_context["modes"])
                captured["fields"] = h100_anchor._field_capture(
                    view.field,
                    view.mesh_data,
                    view.config,
                    comm,
                    None,
                )
                arrays = _actual_mesh_identity(
                    view.field.function_space.mesh, view.field.function_space
                )
                size = view.field.function_space.dofmap.index_map.size_local
                block = view.field.function_space.dofmap.index_map_bs
                arrays["coefficients"] = view.field.x.array[: size * block].copy()
                arrays["rhs"] = view.b.getArray(readonly=True).copy()
                for name, values in zip(
                    ("matrix_indptr", "matrix_indices", "matrix_values"),
                    view.A.getValuesCSR(),
                    strict=True,
                ):
                    arrays[name] = values.copy()
                for order, samples in captured["fields"]["samples"].items():
                    arrays.update(
                        {f"{order}_{name}": values for name, values in samples.items()}
                    )
                captured["arrays"] = arrays

            summary = run_stage4b_block_grating_3d_case(
                cfg,
                root / expected / "solve",
                mesh_data_override=mesh_data,
                variable_p_live_observer=observer,
                variable_p_single_lu_residual_correction=True,
            )
            modal = json.loads(
                (
                    root / expected / "solve" / "dtn_port_diffraction_orders_3d.json"
                ).read_text()
            )
            keys, amplitudes, rows = _modal_identity(modal, expected)
            captured["arrays"]["boundary_amplitudes"] = amplitudes
            captured["arrays"]["channel_power_ratios"] = np.asarray(
                [row["power_ratio"] for row in rows]
            )
            np.savez_compressed(
                root / expected / "raw_pair_arrays.npz", **captured["arrays"]
            )
            record = {
                "requested_backend": requested,
                "actual_live_backend": captured["actual_backend"],
                "actual_summary_backend": summary.get("actual_pc_factor_solver_type"),
                "mode_count": captured["mode_count"],
                "ordered_mode_keys": keys,
                "case_status": summary["case_status"],
                "independent_active_action": captured["a6"],
                "condensed_residual": captured["condensed"],
                "same_lu_correction": summary.get(
                    "variable_p_same_lu_residual_correction"
                ),
                "wall_seconds": time.perf_counter() - backend_started,
                "timings_seconds": summary.get("timings_seconds"),
                "power": {
                    **{
                        key: float(modal["metrics"][key])
                        for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")
                    },
                    "A_volume": float(summary["A_volume_total"]),
                },
                "summary_energy_closure_R_plus_T_plus_A_minus_1": float(
                    summary["energy_closure_error_port_volume"]
                ),
            }
            record["energy_closure_1_minus_R_minus_T_minus_A"] = 1.0 - sum(
                record["power"][key] for key in ("R_total", "T_total", "A_volume")
            )
            record["closure_summary_sign_adjusted_absolute_difference"] = abs(
                record["energy_closure_1_minus_R_minus_T_minus_A"]
                + record["summary_energy_closure_R_plus_T_plus_A_minus_1"]
            )
            (root / expected / "component_record.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n"
            )
            captures[expected] = captured
            records[expected] = record
            captured["modal_case"] = {
                "label": expected,
                "mode_payload": modal,
                "power": record["power"],
            }
            print(
                f"[TASK43-DIRECT-PAIR] backend={expected} end wall={record['wall_seconds']}",
                flush=True,
            )

        reference, candidate = captures["petsc"], captures["mumps"]
        modal_comparison = _modal_comparison(
            reference["modal_case"], candidate["modal_case"]
        )
        gates = {}
        for backend in ("petsc", "mumps"):
            record = records[backend]
            gates[f"{backend}_actual_backend"] = (
                record["actual_live_backend"]
                == record["actual_summary_backend"]
                == backend
            )
            a6_relative = float(
                record["independent_active_action"]["full_solver_gauge_residual"][
                    "relative_to_independent_rhs"
                ]
            )
            gates[f"{backend}_equation"] = bool(
                np.isfinite(a6_relative) and a6_relative <= 1.0e-8
            )
            gates[f"{backend}_condensed"] = (
                float(record["condensed_residual"]["linear_system_relative_residual"])
                <= 1.0e-9
            )
            gates[f"{backend}_closure"] = (
                abs(record["energy_closure_1_minus_R_minus_T_minus_A"]) <= 1.0e-5
            )
            gates[f"{backend}_closure_summary_consistent"] = (
                record["closure_summary_sign_adjusted_absolute_difference"] <= 1.0e-13
            )
            gates[f"{backend}_complete_modes"] = record["mode_count"] == 612
            gates[f"{backend}_completed"] = record["case_status"] == "completed"
        for name, values in reference["arrays"].items():
            if name not in {
                "coefficients",
                "boundary_amplitudes",
                "channel_power_ratios",
            } and not name.startswith(("q8_", "q10_")):
                gates[f"identical_{name}"] = bool(
                    np.array_equal(values, candidate["arrays"][name])
                )
        coeff_ref = reference["arrays"]["coefficients"]
        coeff_cand = candidate["arrays"]["coefficients"]
        coeff_ref_norm = float(np.linalg.norm(coeff_ref))
        coeff_diff_norm = float(np.linalg.norm(coeff_cand - coeff_ref))
        coeff = {
            "reference_norm": coeff_ref_norm,
            "candidate_norm": float(np.linalg.norm(coeff_cand)),
            "difference_norm": coeff_diff_norm,
            "raw_relative": coeff_diff_norm / coeff_ref_norm
            if coeff_ref_norm
            else None,
            "relative_with_algebraic_unit_floor": coeff_diff_norm
            / max(coeff_ref_norm, 1.0),
            "floor": 1.0,
            "floor_active": coeff_ref_norm < 1.0,
            "floor_scope": "one coefficient-unit in this identical code basis; not a physical field scale",
        }
        gates["coefficients"] = coeff["relative_with_algebraic_unit_floor"] <= tolerance
        gates["aggregate_power"] = all(
            value <= tolerance
            for value in modal_comparison["power_absolute_differences"].values()
        )
        gates["channel_power"] = all(
            value <= tolerance
            for value in modal_comparison[
                "individual_channel_power_ratio_absolute_differences"
            ]
        )
        for group, values in modal_comparison["boundary_amplitude_groups"].items():
            ref_norm = values["reference_boundary_amplitude_l2"]
            values["denominator"] = max(ref_norm, 1.0)
            values["floor_active"] = ref_norm < 1.0
            indices = [
                i
                for i, key in enumerate(records["petsc"]["ordered_mode_keys"])
                if f"{key[0]}_{key[3]}" == group
            ]
            values["candidate_boundary_amplitude_l2"] = float(
                np.linalg.norm(candidate["arrays"]["boundary_amplitudes"][indices])
            )
            gates[f"amplitudes_{group}"] = (
                values["relative_with_unit_incident_modal_floor"] <= tolerance
            )
        field_metrics = {}
        for order in ("q8", "q10"):
            ref = reference["fields"]["samples"][order]
            cand = candidate["fields"]["samples"][order]
            gates[f"{order}_points_weights"] = all(
                np.array_equal(ref[key], cand[key])
                for key in ("points_nm", "weights_nm3")
            )
            volume = float(np.sum(ref["weights_nm3"]))
            gates[f"{order}_measured_volume"] = abs(volume - 350000.0) <= 1.0e-7
            metrics = {"measured_volume_nm3": volume}
            for name, ref_values, cand_values, floor in (
                ("E", ref["E_total"], cand["E_total"], np.sqrt(volume)),
                (
                    "curl_E_over_k0",
                    ref["curl_E_total"] / cfg.k0,
                    cand["curl_E_total"] / cfg.k0,
                    np.sqrt(volume),
                ),
                (
                    "H_A_per_m",
                    ref["H_total_A_per_m"],
                    cand["H_total_A_per_m"],
                    np.sqrt(volume) * cfg.magnetic_field_scale_A_per_m,
                ),
            ):
                values = weighted_vector_field_metrics(
                    ref_values,
                    cand_values,
                    ref["weights_nm3"],
                    reference_norm_floor=float(floor),
                )
                values["floor_active"] = bool(values["reference_l2"] < floor)
                metrics[name] = values
                gates[f"{order}_{name}"] = (
                    values["relative_to_reference_or_floor"] <= tolerance
                )
            metrics["G"] = physical_g_difference_metrics(
                ref["E_total"],
                cand["E_total"],
                ref["curl_E_total"],
                cand["curl_E_total"],
                ref["weights_nm3"],
                k0_per_nm=cfg.k0,
                incident_g_norm_floor=float(np.sqrt(2.0 * volume)),
            )
            gates[f"{order}_G"] = (
                metrics["G"]["relative_with_incident_floor"] <= tolerance
            )
            field_metrics[order] = metrics
        # Arrays preserve both full solutions/samples/612 amplitudes and powers;
        # explicit deltas make weak-channel absolute differences auditable.
        np.savez_compressed(
            root / "pair_differences.npz",
            **{
                name: candidate["arrays"][name] - values
                for name, values in reference["arrays"].items()
                if name
                in {"coefficients", "boundary_amplitudes", "channel_power_ratios"}
                or name.startswith(
                    ("q8_E_", "q8_curl_", "q8_H_", "q10_E_", "q10_curl_", "q10_H_")
                )
            },
        )
        comparison = {
            "classification": "36_cell_mixed_p4_p5_full_612_direct_backend_component_only",
            "degree_histogram": dict(Counter(degrees.values())),
            "backend_order": ["petsc", "mumps"],
            "same_lu_correction_both": True,
            "artificial_perturbation": False,
            "phase_fit": False,
            "tolerance": tolerance,
            "weak_quantity_policy": "absolute power; amplitudes and fields divide by max(reference norm, explicit incident floor)",
            "records": records,
            "coefficients": coeff,
            "modal_comparison": modal_comparison,
            "field_metrics": field_metrics,
            "gates": gates,
            "pass": all(gates.values()),
            "wall_seconds": time.perf_counter() - started,
            "timing_scope": "ordered component pair with shared mesh/JIT; not a formal candidate speedup ratio",
        }
        (root / "backend_pair_comparison.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n"
        )
        self.assertTrue(comparison["pass"], json.dumps(gates, sort_keys=True))

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
