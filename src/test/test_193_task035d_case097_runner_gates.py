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
    TASK035D_COMBINED_HP_ACTIVE_FE_DOFS,
    TASK035D_COMBINED_HP_AUTHORITY_PATH,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_COMBINED_HP_PLAN_PATH,
    TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS,
    TASK035D_COMBINED_HP_SOLVE_ROWS,
    TASK035D_H10_CELL_TAG_SHA256,
    TASK035D_H10_FACET_TAG_SHA256,
    TASK035D_H10_MESH_SHA256,
    TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
    TASK035D_LOCAL_H_AUTHORITY_PATH,
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_PATH,
    TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS,
    TASK035D_LOCAL_H_SOLVE_ROWS,
    TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
    TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS,
    TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS,
    TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS,
    TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256,
    TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
    TASK035D_T30_ACTIVE_FE_DOFS,
    TASK035D_T30_ACTIVE_TRACE_ROWS,
    TASK035D_T30_PERIODIC_TRACE_ROWS,
    TASK035D_T30_PLAN_CONTENT_SHA256,
    TASK035D_T30_SOLVE_ROWS,
    task035d_case097_local_h_solver_gate,
    task035d_case097_combined_hp_solver_gate,
    task035d_case097_plan_authority_gate,
    task035d_case097_sidewall_guard_plan_authority_gate,
    task035d_case097_sidewall_guard_solver_gate,
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
SIDEWALL_PLAN = RECORDS / "sidewall_z0_guard_h10_cell_degree_plan_v1.json"
SIDEWALL_AUTHORITY = RECORDS / "physics_guard_plan_authority_mpi8_v1.json"
SIDEWALL_PLAN_SHA256 = hashlib.sha256(SIDEWALL_PLAN.read_bytes()).hexdigest()
SIDEWALL_AUTHORITY_SHA256 = hashlib.sha256(
    SIDEWALL_AUTHORITY.read_bytes()
).hexdigest()
LOCAL_H_PLAN = ROOT / TASK035D_LOCAL_H_PLAN_PATH
LOCAL_H_AUTHORITY = ROOT / TASK035D_LOCAL_H_AUTHORITY_PATH
LOCAL_H_PLAN_SHA256 = hashlib.sha256(LOCAL_H_PLAN.read_bytes()).hexdigest()
LOCAL_H_AUTHORITY_SHA256 = hashlib.sha256(
    LOCAL_H_AUTHORITY.read_bytes()
).hexdigest()
LOCAL_H_COMPONENT = RECORDS / "local_h_production_mpi8_v3_owner_gate_fix1.json"
COMBINED_HP_PLAN = ROOT / TASK035D_COMBINED_HP_PLAN_PATH
COMBINED_HP_AUTHORITY = ROOT / TASK035D_COMBINED_HP_AUTHORITY_PATH
COMBINED_HP_PLAN_SHA256 = hashlib.sha256(
    COMBINED_HP_PLAN.read_bytes()
).hexdigest()
COMBINED_HP_AUTHORITY_SHA256 = hashlib.sha256(
    COMBINED_HP_AUTHORITY.read_bytes()
).hexdigest()
COMBINED_HP_COMPONENT = RECORDS / "combined_hp_interior_mpi8_v2.json"
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


def _sidewall_cli() -> list[str]:
    cli = _task035d_cli()
    cli.extend(("--task035d-candidate-id", "sidewall_z0_guard_v1"))
    cli[cli.index("--stage4-variable-p-cell-degree-plan") + 1] = str(
        SIDEWALL_PLAN
    )
    cli[
        cli.index("--stage4-variable-p-cell-degree-plan-sha256") + 1
    ] = SIDEWALL_PLAN_SHA256
    cli[cli.index("--task035d-plan-authority") + 1] = str(
        SIDEWALL_AUTHORITY
    )
    cli[cli.index("--task035d-plan-authority-sha256") + 1] = (
        SIDEWALL_AUTHORITY_SHA256
    )
    return cli


def _local_h_cli() -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        "15",
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
        "--stage4-local-h-refinement-plan",
        str(LOCAL_H_PLAN),
        "--stage4-local-h-refinement-plan-sha256",
        LOCAL_H_PLAN_SHA256,
        "--task035d-case097-gate",
        "--task035d-candidate-id",
        TASK035D_LOCAL_H_PLAN_NAME,
        "--task035d-plan-authority",
        str(LOCAL_H_AUTHORITY),
        "--task035d-plan-authority-sha256",
        LOCAL_H_AUTHORITY_SHA256,
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _combined_hp_cli() -> list[str]:
    cli = _local_h_cli()
    cli[cli.index("--task035d-candidate-id") + 1] = (
        TASK035D_COMBINED_HP_PLAN_NAME
    )
    cli[cli.index("--stage4-local-h-refinement-plan") + 1] = str(
        COMBINED_HP_PLAN
    )
    cli[
        cli.index("--stage4-local-h-refinement-plan-sha256") + 1
    ] = COMBINED_HP_PLAN_SHA256
    cli[cli.index("--task035d-plan-authority") + 1] = str(
        COMBINED_HP_AUTHORITY
    )
    cli[cli.index("--task035d-plan-authority-sha256") + 1] = (
        COMBINED_HP_AUTHORITY_SHA256
    )
    return cli


def _solver_summary(*, sidewall: bool = False) -> dict:
    active_fe_dofs = (
        TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS
        if sidewall
        else TASK035D_T30_ACTIVE_FE_DOFS
    )
    active_trace_rows = (
        TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS
        if sidewall
        else TASK035D_T30_ACTIVE_TRACE_ROWS
    )
    periodic_trace_rows = (
        TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS
        if sidewall
        else TASK035D_T30_PERIODIC_TRACE_ROWS
    )
    solve_rows = (
        TASK035D_SIDEWALL_GUARD_SOLVE_ROWS
        if sidewall
        else TASK035D_T30_SOLVE_ROWS
    )
    plan_content_sha = (
        TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256
        if sidewall
        else TASK035D_T30_PLAN_CONTENT_SHA256
    )
    degree_counts = (
        TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS
        if sidewall
        else {"p4": 144, "p5": 56, "p6": 52}
    )
    residual = {
        "linear_system_rhs_norm": 1.0,
        "linear_system_solution_norm": 2.0,
        "linear_system_residual_norm": 1.0e-12,
        "linear_system_relative_residual": 1.0e-12,
        "eliminated_cell_interior_residual_norm": 1.0e-13,
        "eliminated_cell_interior_max_abs_residual": 1.0e-14,
    }
    matrix = {
        "matrix_rows": solve_rows,
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
            active_fe_dofs
        ),
        "num_active_trace_dofs": periodic_trace_rows,
        "num_active_condensed_dofs": solve_rows,
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
                    plan_content_sha
                ),
                "mesh_cell_box_catalog_sha256": (
                    "e33ae0611cfe3d9d380ec04af0b86efec7f7f751cdb2dd90"
                    "a9bd936d71dbcf64"
                ),
                "cell_degree_counts": degree_counts,
                "active_rows": active_fe_dofs,
                "active_trace_rows": active_trace_rows,
            },
            "periodic_constraints": {
                "pass": True,
                "mpi_size": 8,
                "independent_periodic_trace_rows": (
                    periodic_trace_rows
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


def _local_h_solver_summary() -> dict:
    summary = copy.deepcopy(_solver_summary())
    reduction = json.loads(
        LOCAL_H_COMPONENT.read_text(encoding="utf-8")
    )["reduction_audit"]
    matrix = {
        "matrix_rows": TASK035D_LOCAL_H_SOLVE_ROWS,
        "matrix_nnz_used": 123_456.0,
        "matrix_mallocs": 0.0,
    }
    residual = {
        "linear_system_rhs_norm": 1.0,
        "linear_system_solution_norm": 2.0,
        "linear_system_residual_norm": 1.0e-12,
        "linear_system_relative_residual": 1.0e-12,
        "eliminated_cell_interior_residual_norm": 1.0e-13,
        "eliminated_cell_interior_max_abs_residual": 1.0e-14,
    }
    summary["matrix_stats"] = matrix
    summary["stage4_dtn_factor_inventory"]["matrix_stats"] = matrix
    summary["config"].update(
        {
            "mesh_target_size": 15.0,
            "stage4_variable_p_cell_degree_plan": None,
            "stage4_local_h_refinement_plan": str(LOCAL_H_PLAN),
        }
    )
    summary["stage4_full3d_assembly_backend_qualification"].update(
        {
            "element_contract": (
                "exact_sequence_balanced_local_h_fixed_trace_p6_interior"
            ),
            "contract": [
                "geometry_bound_balanced_local_h_hanging_trace_elimination",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            ],
        }
    )
    summary["stage4_local_h_active"] = True
    summary["stage4_local_h_constraint_audit"] = reduction
    summary["num_raw_broken_active_fe_dofs"] = (
        TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
    )
    summary["num_actual_conforming_active_fe_dofs"] = (
        TASK035D_LOCAL_H_ACTIVE_FE_DOFS
    )
    summary["num_active_trace_dofs"] = (
        reduction["independent_trace_rows"]
    )
    summary["num_active_condensed_dofs"] = TASK035D_LOCAL_H_SOLVE_ROWS
    summary["cell_static_condensation"] = {
        "schema_version": "task035d.variable-p-assembly-reduction.v1",
        "status": "variable_p_assembly_time_reduction_built",
        "pass": True,
        "degree_plan": reduction["degree_plan"],
        "periodic_constraints": None,
        "trace_constraints": reduction["trace_constraints"],
        "local_h": reduction,
        "global_transfer": {
            "status": "matrix_free_active_p6_transfer_built",
            "pass": True,
            "mpi_size": 8,
        },
        "condensed_system": {
            "schema_version": (
                "task035d.variable-p-condensed-trace-system.v1"
            ),
            "status": "variable_p_condensed_trace_matrix_pass",
            "pass": True,
            "mpi_size": 8,
            "active_full3d_rows_before_condensation": (
                TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            ),
            "active_trace_rows_before_constraint_elimination": (
                reduction["raw_broken_trace_rows"]
            ),
            "active_trace_rows": reduction["independent_trace_rows"],
            "appended_rows": 80,
            "floquet_elimination_applied_before_insertion": True,
            "hanging_elimination_applied_before_insertion": True,
            "trace_constraint_elimination_applied_before_insertion": True,
            "trace_constraint_kinds": ["hanging", "floquet"],
            "hanging_or_floquet_slave_rows_globally_numbered": False,
        },
        "recovery": {
            "status": "variable_p_full_field_recovery_pass",
            "pass": True,
            "trace_constraint_recovery": {
                "pass": True,
                "hanging_trace_recovery_explicitly_checked": True,
                "constraint_kinds": ["floquet", "hanging"],
                "covered_raw_trace_rows": reduction[
                    "raw_broken_trace_rows"
                ],
                "expected_raw_trace_rows": reduction[
                    "raw_broken_trace_rows"
                ],
                "maximum_abs_error": 1.0e-13,
                "relative_l2_error": 1.0e-13,
            },
        },
        "full_explicit_true_residual": residual,
        "full_p6_global_matrix_allocated": False,
        "inactive_p6_rows_globally_numbered": False,
        "active_fe_dof_gate_pass": True,
        "ordinary_default_changed": False,
    }
    return summary


def _combined_hp_solver_summary() -> dict:
    summary = copy.deepcopy(_local_h_solver_summary())
    reduction = json.loads(
        COMBINED_HP_COMPONENT.read_text(encoding="utf-8")
    )["reduction_audit"]
    matrix = {
        "matrix_rows": TASK035D_COMBINED_HP_SOLVE_ROWS,
        "matrix_nnz_used": 234_567.0,
        "matrix_mallocs": 0.0,
    }
    summary["matrix_stats"] = matrix
    summary["stage4_dtn_factor_inventory"]["matrix_stats"] = matrix
    summary["config"]["stage4_local_h_refinement_plan"] = str(
        COMBINED_HP_PLAN
    )
    summary["stage4_full3d_assembly_backend_qualification"][
        "element_contract"
    ] = (
        "exact_sequence_balanced_local_h_fixed_trace_"
        "variable_cell_interior"
    )
    summary["stage4_local_h_constraint_audit"] = reduction
    summary["num_raw_broken_active_fe_dofs"] = (
        TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
    )
    summary["num_actual_conforming_active_fe_dofs"] = (
        TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
    )
    summary["num_active_trace_dofs"] = reduction[
        "independent_trace_rows"
    ]
    summary["num_active_condensed_dofs"] = (
        TASK035D_COMBINED_HP_SOLVE_ROWS
    )
    audit = summary["cell_static_condensation"]
    audit["degree_plan"] = reduction["degree_plan"]
    audit["trace_constraints"] = reduction["trace_constraints"]
    audit["local_h"] = reduction
    condensed = audit["condensed_system"]
    condensed["active_full3d_rows_before_condensation"] = (
        TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
    )
    condensed["active_trace_rows_before_constraint_elimination"] = (
        reduction["raw_broken_trace_rows"]
    )
    condensed["active_trace_rows"] = reduction[
        "independent_trace_rows"
    ]
    condensed[
        "interior_rhs_recovery_iterative_refinement_max_steps"
    ] = 2
    audit["recovery"][
        "interior_rhs_recovery_iterative_refinement_max_steps"
    ] = 2
    audit["recovery"]["interior_trace_source"] = (
        "assembled_global_active_trace"
    )
    audit["recovery"][
        "trace_vector_assembled_before_interior_recovery"
    ] = True
    trace_recovery = audit["recovery"]["trace_constraint_recovery"]
    trace_recovery["covered_raw_trace_rows"] = reduction[
        "raw_broken_trace_rows"
    ]
    trace_recovery["expected_raw_trace_rows"] = reduction[
        "raw_broken_trace_rows"
    ]
    return summary


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
    def test_combined_hp_launch_is_hash_bound_and_local_h_scoped(
        self,
    ) -> None:
        args = _parse_args(_combined_hp_cli())
        launch = _validate_task035d_case097_plan(args)
        self.assertTrue(launch["pass"], launch["failures"])
        self.assertEqual(
            launch["plan_identity"]["actual_conforming_active_fe_dofs"],
            TASK035D_COMBINED_HP_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            launch["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_COMBINED_HP_SOLVE_ROWS,
        )
        self.assertFalse(
            launch["selection_credit"]["complete_combined_hp_credit"]
        )
        cfg = _full3d_config(args)
        self.assertEqual(
            cfg.stage4_local_h_refinement_plan,
            str(COMBINED_HP_PLAN.resolve()),
        )
        self.assertIsNone(cfg.stage4_variable_p_cell_degree_plan)
        command = _worker_command(
            args,
            Path("/tmp/task035d-combined-hp"),
        )
        self.assertEqual(command[command.index("--h-nm") + 1], "15.0")
        self.assertEqual(
            command[
                command.index("--stage4-local-h-refinement-plan") + 1
            ],
            str(COMBINED_HP_PLAN.resolve()),
        )
        self.assertNotIn(
            "--stage4-variable-p-cell-degree-plan",
            command,
        )

        solver = _combined_hp_solver_summary()
        solver_gate = task035d_case097_combined_hp_solver_gate(solver)
        self.assertTrue(solver_gate["pass"], solver_gate["failures"])
        qualification = _qualify(
            args=args,
            solver_summary=solver,
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

    def test_h15_local_h_launch_and_solver_identity_are_frozen(self) -> None:
        args = _parse_args(_local_h_cli())
        launch = _validate_task035d_case097_plan(args)
        self.assertTrue(launch["pass"], launch["failures"])
        self.assertEqual(
            launch["plan_identity"]["actual_conforming_active_fe_dofs"],
            TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            launch["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_LOCAL_H_SOLVE_ROWS,
        )
        self.assertFalse(
            launch["selection_credit"]["goal_oriented_selection_credit"]
        )

        cfg = _full3d_config(args)
        self.assertEqual(
            cfg.stage4_local_h_refinement_plan,
            str(LOCAL_H_PLAN.resolve()),
        )
        self.assertIsNone(cfg.stage4_variable_p_cell_degree_plan)
        command = _worker_command(args, Path("/tmp/task035d-local-h"))
        self.assertEqual(
            command[command.index("--h-nm") + 1],
            "15.0",
        )
        self.assertEqual(
            command[
                command.index("--stage4-local-h-refinement-plan") + 1
            ],
            str(LOCAL_H_PLAN.resolve()),
        )
        self.assertNotIn(
            "--stage4-variable-p-cell-degree-plan",
            command,
        )

        solver = _local_h_solver_summary()
        gate = task035d_case097_local_h_solver_gate(solver)
        self.assertTrue(gate["pass"], gate["failures"])
        qualification = _qualify(
            args=args,
            solver_summary=solver,
            events=[{"stage": "after_ksp_solve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary=_resource_summary(),
        )
        self.assertTrue(qualification["pass"], qualification["failures"])

        tampered = copy.deepcopy(solver)
        tampered["cell_static_condensation"]["trace_constraints"][
            "hanging_or_floquet_slave_rows_globally_numbered"
        ] = True
        rejected = task035d_case097_local_h_solver_gate(tampered)
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "combined_constraint_identity",
            rejected["failures"],
        )

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

    def test_sidewall_guard_authority_and_solver_identity_are_frozen(
        self,
    ) -> None:
        plan = json.loads(SIDEWALL_PLAN.read_text(encoding="utf-8"))
        authority = json.loads(
            SIDEWALL_AUTHORITY.read_text(encoding="utf-8")
        )
        gate = task035d_case097_sidewall_guard_plan_authority_gate(
            plan,
            authority,
            expected_plan_file_sha256=SIDEWALL_PLAN_SHA256,
            observed_plan_file_sha256=SIDEWALL_PLAN_SHA256,
            expected_authority_sha256=SIDEWALL_AUTHORITY_SHA256,
            observed_authority_sha256=SIDEWALL_AUTHORITY_SHA256,
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "sidewall_z0_guard_h10_cell_degree_plan_v1.json"
            ),
            authority_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "physics_guard_plan_authority_mpi8_v1.json"
            ),
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(
            gate["plan_identity"]["actual_conforming_active_fe_dofs"],
            TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            gate["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
        )

        tampered = copy.deepcopy(authority)
        tampered["regional_diagnostic"]["actual_channel_dwr"] = True
        rejected = task035d_case097_sidewall_guard_plan_authority_gate(
            plan,
            tampered,
            expected_plan_file_sha256=SIDEWALL_PLAN_SHA256,
            observed_plan_file_sha256=SIDEWALL_PLAN_SHA256,
            expected_authority_sha256=SIDEWALL_AUTHORITY_SHA256,
            observed_authority_sha256=SIDEWALL_AUTHORITY_SHA256,
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "sidewall_z0_guard_h10_cell_degree_plan_v1.json"
            ),
            authority_path_from_root=(
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "physics_guard_plan_authority_mpi8_v1.json"
            ),
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "authority_diagnostic_identity",
            rejected["failures"],
        )

        args = _parse_args(_sidewall_cli())
        self.assertEqual(
            args.task035d_candidate_id,
            "sidewall_z0_guard_v1",
        )
        integrated = _validate_task035d_case097_plan(args)
        self.assertTrue(integrated["pass"], integrated["failures"])
        command = _worker_command(args, Path("/tmp/task035d-sidewall"))
        self.assertEqual(
            command[command.index("--task035d-candidate-id") + 1],
            "sidewall_z0_guard_v1",
        )
        solver_gate = task035d_case097_sidewall_guard_solver_gate(
            _solver_summary(sidewall=True)
        )
        self.assertTrue(solver_gate["pass"], solver_gate["failures"])

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
