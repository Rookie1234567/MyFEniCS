from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from benchmarks.run_task033_full3d_watchdog import (
    _full3d_config,
    _parse_args,
    _qualify,
    _sampler_summary,
    _validate_task035d_case097_plan,
    _worker_command,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_H10_CELL_TAG_SHA256,
    TASK035D_H10_FACET_TAG_SHA256,
    TASK035D_H10_MESH_SHA256,
    TASK035D_T30_ACTIVE_FE_DOFS,
    TASK035D_T30_ACTIVE_TRACE_ROWS,
    TASK035D_T30_PERIODIC_TRACE_ROWS,
    TASK035D_T30_PLAN_CONTENT_SHA256,
    TASK035D_T30_SOLVE_ROWS,
    task035d_case097_plan_authority_gate,
    task035d_case097_t30_solver_gate,
)


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records"
)
PLAN = RECORDS / "t30_h10_cell_degree_plan_v1.json"
AUTHORITY = RECORDS / "legacy_seeded_plan_authority_mpi8_v1.json"
PLAN_SHA256 = hashlib.sha256(PLAN.read_bytes()).hexdigest()
AUTHORITY_SHA256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
SOURCE_SHA = "a" * 40


def _task035d_cli() -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        TASK035D_CASE097_BACKEND,
        "--stage4-variable-p-cell-degree-plan",
        str(PLAN),
        "--stage4-variable-p-cell-degree-plan-sha256",
        PLAN_SHA256,
        "--task035d-case097-gate",
        "--task035d-plan-authority",
        str(AUTHORITY),
        "--task035d-plan-authority-sha256",
        AUTHORITY_SHA256,
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _solver_summary() -> dict:
    residual = {
        "linear_system_rhs_norm": 1.0,
        "linear_system_solution_norm": 2.0,
        "linear_system_residual_norm": 1.0e-12,
        "linear_system_relative_residual": 1.0e-12,
        "eliminated_cell_interior_residual_norm": 1.0e-13,
        "eliminated_cell_interior_max_abs_residual": 1.0e-14,
    }
    matrix = {
        "matrix_rows": TASK035D_T30_SOLVE_ROWS,
        "matrix_nnz_used": 123_456.0,
        "matrix_mallocs": 0.0,
    }
    return {
        "case_status": "completed",
        "official_result": True,
        "matrix_diagnostics_assemble_only": False,
        "matrix_diagnostics_factorization_only": False,
        "matrix_stats": matrix,
        "ksp_converged": True,
        "linear_system_relative_residual": 1.0e-12,
        "full3d_reference_exported": True,
        "polarization_kind": "s",
        "config": {
            "stage_case": "stage4_block_grating",
            "geometry_kind": "rectangular_block_grating",
            "mesh_cell_type_resolved": "hexahedron",
            "nedelec_degree": 6,
            "mesh_target_size": 10.0,
            "use_floquet_xy": True,
            "stage4_boundary_model": "dtn_port",
            "stage4_dtn_assembly": "auxiliary",
            "stage4_full3d_assembly_backend": TASK035D_CASE097_BACKEND,
            "lambda0": 13.5,
            "incident_theta_deg": 80.0,
            "incident_phi_deg": 0.0,
            "period_x": 50.0,
            "period_y": 25.0,
            "z_min": -10.0,
            "z_max": 130.0,
            "grating_height": 120.0,
            "grating_width_x": 17.0,
            "grating_width_y": 25.0,
            "scattering_background": "layered",
            "polarization_kind": "s",
        },
        "stage4_full3d_assembly_backend_actual": (
            TASK035D_CASE097_BACKEND
        ),
        "stage4_full3d_assembly_backend_qualification": {
            "status": "qualified",
            "qualified_scope": True,
            "actual": TASK035D_CASE097_BACKEND,
            "element_contract": (
                "exact_sequence_variable_p4_p5_p6_in_p6_container"
            ),
            "contract": [
                "geometry_bound_inactive_row_free_variable_p",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            ],
        },
        "stage4_full3d_assembly_backend_audit": {
            "requested": TASK035D_CASE097_BACKEND,
            "actual": TASK035D_CASE097_BACKEND,
            "selection_source": "public_port",
            "ordinary_default_unchanged": True,
        },
        "stage4_variable_p_active": True,
        "variable_p_mesh_identity": {
            "partition_independent_mesh_sha256": TASK035D_H10_MESH_SHA256,
            "cell_tag_sha256": TASK035D_H10_CELL_TAG_SHA256,
            "facet_tag_sha256": TASK035D_H10_FACET_TAG_SHA256,
            "global_cell_count": 252,
            "mesh_cells_resolved": [6, 3, 14],
        },
        "mesh_cells_resolved": [6, 3, 14],
        "mesh_material_plane_alignment": {"all_aligned": True},
        "domain_tag_volumes": {
            "air": 111_500.0,
            "substrate": 12_500.0,
            "grating": 51_000.0,
        },
        "use_floquet_xy": True,
        "floquet_num_slave_edges": 10,
        "floquet_num_matched_master_edges": 10,
        "floquet_num_slave_faces": 5,
        "floquet_num_matched_master_faces": 5,
        "floquet_max_face_transform_fit_residual": 0.0,
        "floquet_max_edge_midpoint_pairing_error": 0.0,
        "floquet_max_face_midpoint_pairing_error": 0.0,
        "floquet_edge_corner_constraint_phase_mismatch": 0.0,
        "floquet_x_face_mismatch": 0.0,
        "floquet_y_face_mismatch": 0.0,
        "floquet_edge_corner_mismatch": 0.0,
        "nedelec_orientation_factor_stats": {
            "uses_exact_basix_entity_transforms": True,
            "uses_local_moment_fit": False,
            "used_full_boundary_gather": False,
            "created_dense_boundary_square": False,
        },
        "num_actual_conforming_active_fe_dofs": (
            TASK035D_T30_ACTIVE_FE_DOFS
        ),
        "num_active_trace_dofs": TASK035D_T30_PERIODIC_TRACE_ROWS,
        "num_active_condensed_dofs": TASK035D_T30_SOLVE_ROWS,
        "stage4_dtn_num_auxiliary_dofs": 80,
        "stage4_dtn_variable_p_trace_only_gate_pass": True,
        "stage4_dtn_variable_p_auxiliary_interior_columns_allocated": False,
        "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max": 0,
        "stage4_dtn_variable_p_trace_functional_count": 81,
        "stage4_dtn_variable_p_removed_interior_max_abs": 2.5e-12,
        "stage4_dtn_factor_inventory": {
            "available": True,
            "factor_solver_type": "mumps",
            "matrix_stats": matrix,
        },
        "direct_release_solver_before_postprocess": True,
        "solver_objects_released_before_postprocess": True,
        "solver_release_audit": {
            "petsc_garbage_cleanup_called": True,
            "process_heap_trim": {
                "supported_on_all_ranks": True,
                "succeeded_on_all_ranks": True,
            },
        },
        "cell_static_condensation": {
            "schema_version": "task035d.variable-p-assembly-reduction.v1",
            "status": "variable_p_assembly_time_reduction_built",
            "pass": True,
            "degree_plan": {
                "pass": True,
                "mpi_size": 8,
                "cell_degree_plan_sha256": (
                    TASK035D_T30_PLAN_CONTENT_SHA256
                ),
                "mesh_cell_box_catalog_sha256": (
                    "e33ae0611cfe3d9d380ec04af0b86efec7f7f751cdb2dd90"
                    "a9bd936d71dbcf64"
                ),
                "cell_degree_counts": {"p4": 144, "p5": 56, "p6": 52},
                "active_rows": TASK035D_T30_ACTIVE_FE_DOFS,
                "active_trace_rows": TASK035D_T30_ACTIVE_TRACE_ROWS,
            },
            "periodic_constraints": {
                "pass": True,
                "mpi_size": 8,
                "independent_periodic_trace_rows": (
                    TASK035D_T30_PERIODIC_TRACE_ROWS
                ),
                "inactive_p6_rows_globally_numbered": False,
            },
            "global_transfer": {
                "status": "matrix_free_active_p6_transfer_built",
                "pass": True,
                "mpi_size": 8,
            },
            "condensed_system": {
                "status": "variable_p_condensed_trace_matrix_pass",
                "pass": True,
                "mpi_size": 8,
            },
            "recovery": {
                "status": "variable_p_full_field_recovery_pass",
                "pass": True,
            },
            "full_explicit_true_residual": residual,
            "full_p6_global_matrix_allocated": False,
            "inactive_p6_rows_globally_numbered": False,
            "active_fe_dof_gate_pass": True,
            "ordinary_default_changed": False,
        },
    }


def _resource_summary() -> dict:
    per_rank = {
        str(rank): {"pss_mb": 100.0 + rank, "uss_mb": 90.0 + rank}
        for rank in range(8)
    }
    return {
        "max_worker_rank_smaps_readable_count": 8.0,
        "fully_readable_mpi8_smaps_sample_count": 2,
        "per_rank_smaps_rollup_peak_mb": per_rank,
        "max_simultaneous_worker_pss_mb": 800.0,
        "max_simultaneous_worker_uss_mb": 720.0,
        "max_container_cgroup_current_observed_mb": 900.0,
        "max_container_cgroup_peak_mb": 950.0,
    }


class Task035dCase097RunnerGateTests(unittest.TestCase):
    def test_t30_launch_gate_accepts_only_tracked_frozen_authority(self) -> None:
        args = _parse_args(_task035d_cli())
        gate = _validate_task035d_case097_plan(args)
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(
            gate["plan_identity"]["actual_conforming_active_fe_dofs"],
            TASK035D_T30_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            gate["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_T30_SOLVE_ROWS,
        )

        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
        authority["seed_production_qualified"] = True
        rejected = task035d_case097_plan_authority_gate(
            plan,
            authority,
            expected_plan_file_sha256=PLAN_SHA256,
            observed_plan_file_sha256=PLAN_SHA256,
            expected_authority_sha256=AUTHORITY_SHA256,
            observed_authority_sha256=AUTHORITY_SHA256,
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "t30_h10_cell_degree_plan_v1.json"
            ),
            authority_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "legacy_seeded_plan_authority_mpi8_v1.json"
            ),
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "authority_is_pre_pde_only",
            rejected["failures"],
        )
        drifted = task035d_case097_plan_authority_gate(
            plan,
            json.loads(AUTHORITY.read_text(encoding="utf-8")),
            expected_plan_file_sha256="f" * 64,
            observed_plan_file_sha256="f" * 64,
            expected_authority_sha256="e" * 64,
            observed_authority_sha256="e" * 64,
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "t30_h10_cell_degree_plan_v1.json"
            ),
            authority_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "legacy_seeded_plan_authority_mpi8_v1.json"
            ),
        )
        self.assertFalse(drifted["pass"])
        self.assertIn(
            "plan_file_hash_matches_frozen_t30",
            drifted["failures"],
        )
        self.assertIn(
            "authority_file_hash_matches_frozen_mpi8",
            drifted["failures"],
        )

    def test_task035d_parser_is_opt_in_and_scope_locked(self) -> None:
        args = _parse_args(_task035d_cli())
        self.assertTrue(args.task035d_case097_gate)
        self.assertFalse(args.task035c_p6_h10_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(
            args.stage4_full3d_assembly_backend,
            TASK035D_CASE097_BACKEND,
        )
        cfg = _full3d_config(args)
        self.assertEqual(
            cfg.stage4_full3d_assembly_backend,
            TASK035D_CASE097_BACKEND,
        )
        self.assertEqual(
            cfg.stage4_variable_p_cell_degree_plan,
            str(PLAN),
        )
        self.assertTrue(cfg.direct_release_base_after_augmentation)
        self.assertTrue(cfg.direct_release_solver_before_postprocess)
        command = _worker_command(args, Path("/tmp/task035d-worker"))
        self.assertEqual(command[command.index("--mpi-size") + 1], "8")
        self.assertEqual(
            command[
                command.index("--stage4-variable-p-cell-degree-plan") + 1
            ],
            str(PLAN),
        )
        self.assertEqual(
            command[command.index("--task035d-plan-authority") + 1],
            str(AUTHORITY),
        )
        self.assertEqual(
            command[command.index("--verified-clean-sha") + 1],
            SOURCE_SHA,
        )

        for option, value in (
            ("--mpi-size", "4"),
            ("--polarization-kind", "p"),
            ("--profile", "mumps_ooc"),
            ("--stage4-full3d-assembly-backend", "standard_full"),
        ):
            cli = _task035d_cli()
            cli[cli.index(option) + 1] = value
            with self.subTest(option=option, value=value):
                with self.assertRaises(SystemExit):
                    _parse_args(cli)

        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--degree",
                    "6",
                    "--h-nm",
                    "10",
                    "--task035c-p6-h10-gate",
                    *_task035d_cli()[2:],
                ]
            )

        ordinary = _parse_args(
            [
                "--degree",
                "3",
                "--h-nm",
                "5",
            ]
        )
        ordinary_cfg = _full3d_config(ordinary)
        self.assertEqual(
            ordinary_cfg.stage4_full3d_assembly_backend,
            "standard_full",
        )
        self.assertIsNone(ordinary_cfg.stage4_variable_p_cell_degree_plan)
        self.assertFalse(
            ordinary_cfg.direct_release_base_after_augmentation
        )
        self.assertFalse(
            ordinary_cfg.direct_release_solver_before_postprocess
        )

    def test_solver_gate_and_full_qualification_are_fail_closed(self) -> None:
        summary = _solver_summary()
        gate = task035d_case097_t30_solver_gate(summary)
        self.assertTrue(gate["pass"], gate["failures"])

        args = _parse_args(_task035d_cli())
        qualification = _qualify(
            args=args,
            solver_summary=summary,
            events=[{"stage": "after_ksp_solve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary=_resource_summary(),
        )
        self.assertTrue(
            qualification["pass"],
            qualification["failures"],
        )
        self.assertTrue(
            qualification["task035d_case097_solver_gate"]["pass"]
        )

        missing_rank = _resource_summary()
        del missing_rank["per_rank_smaps_rollup_peak_mb"]["7"]
        rejected = _qualify(
            args=args,
            solver_summary=summary,
            events=[{"stage": "after_ksp_solve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary=missing_rank,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "task035d_all_rank_smaps_readable",
            rejected["failures"],
        )

        no_same_frame = _resource_summary()
        no_same_frame["fully_readable_mpi8_smaps_sample_count"] = 0
        rejected = _qualify(
            args=args,
            solver_summary=summary,
            events=[{"stage": "after_ksp_solve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary=no_same_frame,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "task035d_all_rank_smaps_readable",
            rejected["failures"],
        )

        summary["num_actual_conforming_active_fe_dofs"] += 1
        rejected_solver = task035d_case097_t30_solver_gate(summary)
        self.assertFalse(rejected_solver["pass"])
        self.assertIn("active_fe_dof_gate", rejected_solver["failures"])

    def test_sampler_preserves_per_rank_pss_uss_and_cgroup_peak(self) -> None:
        workers = [
            {"rank": rank, "pid": 100 + rank, "rss_mb": 110.0 + rank}
            for rank in range(2)
        ]
        smaps = [
            {
                "rank": rank,
                "pid": 100 + rank,
                "rss_mb": 110.0 + rank,
                "pss_mb": 100.0 + rank,
                "uss_mb": 90.0 + rank,
                "shared_mb": 20.0,
                "anonymous_mb": 80.0,
                "swap_mb": 0.0,
                "swap_pss_mb": 0.0,
            }
            for rank in range(2)
        ]
        row = {
            "stage": "unit_test",
            "worker_rank_rss_sum_mb": 221.0,
            "worker_rank_pss_sum_mb": 201.0,
            "worker_rank_uss_sum_mb": 181.0,
            "worker_rank_shared_sum_mb": 40.0,
            "worker_rank_smaps_swap_sum_mb": 0.0,
            "mpi_process_tree_rss_mb": 230.0,
            "mpi_process_tree_swap_mb": 0.0,
            "worker_rank_rss_mb_json": json.dumps(workers),
            "worker_rank_smaps_rollup_json": json.dumps(smaps),
            "worker_rank_smaps_readable_count": 2,
            "container_cgroup_current_mb": 240.0,
            "container_cgroup_peak_mb": 250.0,
            "job_cgroup_dedicated": False,
            "container_swap_current_mb": 0.0,
            "worker_rank_thread_count_sum": 2,
            "worker_rank_cpu_core_equivalents": 1.0,
        }
        summary = _sampler_summary([row])
        self.assertEqual(summary["max_simultaneous_worker_pss_mb"], 201.0)
        self.assertEqual(summary["max_simultaneous_worker_uss_mb"], 181.0)
        self.assertEqual(
            summary["max_container_cgroup_current_observed_mb"],
            240.0,
        )
        self.assertEqual(
            summary["fully_readable_mpi8_smaps_sample_count"],
            0,
        )
        self.assertIsNone(summary["max_container_cgroup_current_mb"])
        self.assertEqual(summary["max_container_cgroup_peak_mb"], 250.0)
        self.assertEqual(summary["memory_authority_mb"], 230.0)
        self.assertEqual(
            summary["per_rank_smaps_rollup_peak_mb"]["1"]["pss_mb"],
            101.0,
        )

    def test_solver_gate_rejects_independent_identity_drift(self) -> None:
        mutations = {
            "variable_p_backend_actual": lambda row: row[
                "stage4_full3d_assembly_backend_qualification"
            ].update({"contract": []}),
            "mesh_and_tag_identity": lambda row: row[
                "variable_p_mesh_identity"
            ].update({"cell_tag_sha256": "0" * 64}),
            "periodic_identity": lambda row: row[
                "cell_static_condensation"
            ]["periodic_constraints"].update({"mpi_size": 4}),
            "inactive_rows_absent": lambda row: row[
                "cell_static_condensation"
            ].update({"inactive_p6_rows_globally_numbered": True}),
            "trace_only_gate": lambda row: row.update(
                {"stage4_dtn_variable_p_trace_functional_count": 80}
            ),
            "full_explicit_true_residual": lambda row: row[
                "cell_static_condensation"
            ]["full_explicit_true_residual"].update(
                {"linear_system_relative_residual": 1.0e-8}
            ),
            "solver_lifecycle_release": lambda row: row[
                "solver_release_audit"
            ]["process_heap_trim"].update(
                {"succeeded_on_all_ranks": False}
            ),
        }
        for expected_failure, mutate in mutations.items():
            summary = copy.deepcopy(_solver_summary())
            mutate(summary)
            gate = task035d_case097_t30_solver_gate(summary)
            with self.subTest(expected_failure=expected_failure):
                self.assertFalse(gate["pass"])
                self.assertIn(expected_failure, gate["failures"])


if __name__ == "__main__":
    unittest.main()
