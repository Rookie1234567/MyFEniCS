from __future__ import annotations

from collections import Counter
import math
from typing import Any


TASK035D_CASE097_BACKEND = "assembly_time_variable_p_condensed"
TASK035D_CASE097_PLAN_SCHEMA = (
    "task035d.variable-p-cell-degree-plan.v1"
)
TASK035D_CASE097_AUTHORITY_SCHEMA = (
    "task035d.legacy-seeded-plan-authority.v1"
)
TASK035D_T30_PLAN_NAME = "t30"
TASK035D_T30_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "t30_h10_cell_degree_plan_v1.json"
)
TASK035D_T30_PLAN_FILE_SHA256 = (
    "4f580a06f4c1774316ecbdce950828b3cda143f0807145d9d40de2cd64df5c3a"
)
TASK035D_T30_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "legacy_seeded_plan_authority_mpi8_v1.json"
)
TASK035D_T30_AUTHORITY_FILE_SHA256 = (
    "97e8ddaab151cfc985c43c66256c036f3809ee216c47f67710a1f01679de0961"
)
TASK035D_T30_PLAN_CONTENT_SHA256 = (
    "862a0347792c356858b405d27f9874cfb9a28b3d75034d73f75c594c5c43c26d"
)
TASK035D_T30_GEOMETRY_CATALOG_SHA256 = (
    "e33ae0611cfe3d9d380ec04af0b86efec7f7f751cdb2dd90a9bd936d71dbcf64"
)
TASK035D_T30_SEED_GEOMETRY_SHA256 = (
    "b68a588e99032c9972740621bf01f15807d92d6025919bb097a53e92e75852a7"
)
TASK035D_T30_SEED_PAYLOAD_SHA256 = (
    "b3420dbdfce689cfa14e9b87e51910943d81b160dbd8a4b9e3c5798526f4b68c"
)
TASK035D_T30_CELL_DEGREE_COUNTS = {"p4": 144, "p5": 56, "p6": 52}
TASK035D_T30_ACTIVE_FE_DOFS = 87_600
TASK035D_T30_ACTIVE_TRACE_ROWS = 35_208
TASK035D_T30_PERIODIC_TRACE_ROWS = 28_910
TASK035D_T30_DTN_ROWS = 80
TASK035D_T30_SOLVE_ROWS = 28_990
TASK035D_H10_MESH_SHA256 = (
    "f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857"
)
TASK035D_H10_CELL_TAG_SHA256 = (
    "42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131"
)
TASK035D_H10_FACET_TAG_SHA256 = (
    "0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd"
)


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _t30_authority_entry(authority: dict[str, Any]) -> dict[str, Any]:
    plans = authority.get("plans")
    if not isinstance(plans, list):
        return {}
    matches = [
        plan
        for plan in plans
        if isinstance(plan, dict)
        and plan.get("name") == TASK035D_T30_PLAN_NAME
    ]
    return matches[0] if len(matches) == 1 else {}


def task035d_case097_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    *,
    expected_plan_file_sha256: str | None,
    observed_plan_file_sha256: str | None,
    expected_authority_sha256: str | None,
    observed_authority_sha256: str | None,
    plan_is_tracked: bool,
    authority_is_tracked: bool,
    plan_path_from_root: str | None,
    authority_path_from_root: str | None,
) -> dict[str, Any]:
    """Validate the tracked MPI8 T30 launch authority without accuracy credit."""

    plan = plan if isinstance(plan, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    closure = plan.get("closure_audit")
    closure = closure if isinstance(closure, dict) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    selector = provenance.get("selector_audit")
    selector = selector if isinstance(selector, dict) else {}
    periodic = selector.get("periodic_constraint_audit")
    periodic = periodic if isinstance(periodic, dict) else {}
    periodic_checks = periodic.get("checks")
    periodic_checks = (
        periodic_checks if isinstance(periodic_checks, dict) else {}
    )
    seed = selector.get("seed_audit")
    seed = seed if isinstance(seed, dict) else {}
    authority_entry = _t30_authority_entry(authority)
    environment = authority.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    cells = plan.get("cells")
    cell_degrees = (
        Counter(int(row.get("degree", -1)) for row in cells)
        if isinstance(cells, list)
        and all(isinstance(row, dict) for row in cells)
        else Counter()
    )
    observed_degree_counts = {
        f"p{degree}": int(cell_degrees[degree])
        for degree in (4, 5, 6)
    }

    checks = {
        "plan_is_tracked": plan_is_tracked,
        "authority_is_tracked": authority_is_tracked,
        "plan_expected_sha_is_valid": _valid_hex(
            expected_plan_file_sha256,
            64,
        ),
        "authority_expected_sha_is_valid": _valid_hex(
            expected_authority_sha256,
            64,
        ),
        "plan_file_hash_matches_expected": (
            observed_plan_file_sha256 == expected_plan_file_sha256
        ),
        "plan_file_hash_matches_frozen_t30": (
            observed_plan_file_sha256 == TASK035D_T30_PLAN_FILE_SHA256
            and expected_plan_file_sha256 == TASK035D_T30_PLAN_FILE_SHA256
        ),
        "authority_file_hash_matches_expected": (
            observed_authority_sha256 == expected_authority_sha256
        ),
        "authority_file_hash_matches_frozen_mpi8": (
            observed_authority_sha256
            == TASK035D_T30_AUTHORITY_FILE_SHA256
            and expected_authority_sha256
            == TASK035D_T30_AUTHORITY_FILE_SHA256
        ),
        "plan_schema": (
            plan.get("schema_version") == TASK035D_CASE097_PLAN_SCHEMA
        ),
        "plan_status": plan.get("status") == "geometry_bound_cell_degree_plan",
        "plan_path_identity": plan_path_from_root == TASK035D_T30_PLAN_PATH,
        "authority_path_identity": (
            authority_path_from_root == TASK035D_T30_AUTHORITY_PATH
        ),
        "plan_content_sha": (
            plan.get("cell_degree_plan_sha256")
            == TASK035D_T30_PLAN_CONTENT_SHA256
        ),
        "plan_geometry_catalog_sha": (
            plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_T30_GEOMETRY_CATALOG_SHA256
        ),
        "plan_cell_count": isinstance(cells, list) and len(cells) == 252,
        "plan_cell_degree_counts": (
            observed_degree_counts == TASK035D_T30_CELL_DEGREE_COUNTS
        ),
        "plan_closure_pass": closure.get("pass") is True,
        "plan_active_fe_dofs": (
            closure.get("active_rows") == TASK035D_T30_ACTIVE_FE_DOFS
        ),
        "plan_active_trace_rows": (
            closure.get("active_trace_rows")
            == TASK035D_T30_ACTIVE_TRACE_ROWS
        ),
        "plan_inactive_rows_absent": (
            closure.get("inactive_p6_rows") == 86_202
            and closure.get("inactive_p6_trace_rows") == 25_194
        ),
        "plan_adjacent_degree_jump": (
            closure.get("maximum_adjacent_cell_degree_jump") == 1
        ),
        "plan_ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and closure.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
        ),
        "historical_seed_is_not_accuracy_authority": (
            provenance.get("formal_accuracy_credit") is False
            and provenance.get("fresh_12_channel_pde_required") is True
            and selector.get("historical_seed_only") is True
            and seed.get("production_qualified") is False
        ),
        "seed_payload_identity": (
            provenance.get("seed_payload_sha256")
            == TASK035D_T30_SEED_PAYLOAD_SHA256
            and seed.get("payload_sha256")
            == TASK035D_T30_SEED_PAYLOAD_SHA256
            and seed.get("mesh_geometry_sha256")
            == TASK035D_T30_SEED_GEOMETRY_SHA256
        ),
        "selector_pass": selector.get("pass") is True,
        "selector_active_fe_gate": (
            selector.get("actual_conforming_active_fe_dofs")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and selector.get("active_fe_dof_gate_pass") is True
        ),
        "selector_periodic_trace_rows": (
            selector.get("periodic_independent_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
        ),
        "selector_solve_rows": (
            selector.get("predicted_direct_solve_rows")
            == TASK035D_T30_SOLVE_ROWS
            and selector.get("appended_dtn_rows") == TASK035D_T30_DTN_ROWS
        ),
        "periodic_constraint_pass": (
            periodic.get("pass") is True
            and periodic.get("independent_periodic_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
            and periodic_checks.get(
                "slave_rows_eliminated_before_insertion"
            )
            is True
            and periodic.get("inactive_p6_rows_globally_numbered") is False
        ),
        "authority_schema": (
            authority.get("schema_version")
            == TASK035D_CASE097_AUTHORITY_SCHEMA
        ),
        "authority_status": (
            authority.get("status")
            == "legacy_seeded_plan_authority_mpi8_pass"
            and authority.get("pass") is True
        ),
        "authority_environment": (
            environment.get("mpi_size") == 8
            and environment.get("petsc_scalar_type") == "complex128"
            and environment.get("petsc_int_type") == "int32"
        ),
        "authority_fixed_case": (
            authority.get("actual_axis_counts") == [6, 3, 14]
            and authority.get("cell_count") == 252
            and authority.get("degree_container") == 6
            and authority.get("h_nm") == 10.0
            and authority.get("geometry")
            == "Task034 fixed rectangular block grating"
        ),
        "authority_is_pre_pde_only": (
            authority.get("formal_accuracy_credit") is False
            and authority.get("fresh_12_channel_pde_required") is True
            and authority.get("seed_production_qualified") is False
            and authority.get("heavy_pde_started") is False
        ),
        "authority_entry_plan_path": (
            authority_entry.get("plan_file") == TASK035D_T30_PLAN_PATH
        ),
        "authority_entry_file_hash": (
            authority_entry.get("plan_file_sha256")
            == observed_plan_file_sha256
        ),
        "authority_entry_plan_content": (
            authority_entry.get("cell_degree_plan_sha256")
            == TASK035D_T30_PLAN_CONTENT_SHA256
            and authority_entry.get("cell_degree_counts")
            == TASK035D_T30_CELL_DEGREE_COUNTS
        ),
        "authority_entry_dimensions": (
            authority_entry.get("actual_conforming_active_fe_dofs")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and authority_entry.get("periodic_independent_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
            and authority_entry.get("predicted_direct_solve_rows")
            == TASK035D_T30_SOLVE_ROWS
        ),
        "authority_ordinary_default_unchanged": (
            authority.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.case097-t30-launch-gate.v1",
        "status": (
            "task035d_t30_launch_authority_pass"
            if not failures
            else "task035d_t30_launch_authority_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "plan_identity": {
            "name": TASK035D_T30_PLAN_NAME,
            "path": plan_path_from_root,
            "file_sha256": observed_plan_file_sha256,
            "cell_degree_plan_sha256": plan.get(
                "cell_degree_plan_sha256"
            ),
            "mesh_cell_box_catalog_sha256": plan.get(
                "mesh_cell_box_catalog_sha256"
            ),
            "cell_degree_counts": observed_degree_counts,
            "actual_conforming_active_fe_dofs": closure.get("active_rows"),
            "periodic_independent_trace_rows": selector.get(
                "periodic_independent_trace_rows"
            ),
            "predicted_direct_solve_rows": selector.get(
                "predicted_direct_solve_rows"
            ),
        },
        "accuracy_credit": (
            "none_until_fresh_12_channel_checker_passes"
        ),
        "ordinary_default_changed": False,
    }


def task035d_case097_t30_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the exact variable-p reduction identity before physics comparison."""

    summary = solver_summary if isinstance(solver_summary, dict) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, dict) else {}
    config = summary.get("config")
    config = config if isinstance(config, dict) else {}
    audit = summary.get("cell_static_condensation")
    audit = audit if isinstance(audit, dict) else {}
    degree_plan = audit.get("degree_plan")
    degree_plan = degree_plan if isinstance(degree_plan, dict) else {}
    periodic = audit.get("periodic_constraints")
    periodic = periodic if isinstance(periodic, dict) else {}
    recovery = audit.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    full_residual = audit.get("full_explicit_true_residual")
    full_residual = (
        full_residual if isinstance(full_residual, dict) else {}
    )
    backend_qualification = summary.get(
        "stage4_full3d_assembly_backend_qualification"
    )
    backend_audit = summary.get("stage4_full3d_assembly_backend_audit")
    backend_audit = (
        backend_audit if isinstance(backend_audit, dict) else {}
    )
    backend_qualification = (
        backend_qualification
        if isinstance(backend_qualification, dict)
        else {}
    )
    factor_inventory = summary.get("stage4_dtn_factor_inventory")
    factor_inventory = (
        factor_inventory if isinstance(factor_inventory, dict) else {}
    )
    factor_matrix = factor_inventory.get("matrix_stats")
    factor_matrix = (
        factor_matrix if isinstance(factor_matrix, dict) else {}
    )
    solver_release = summary.get("solver_release_audit")
    solver_release = (
        solver_release if isinstance(solver_release, dict) else {}
    )
    heap_trim = solver_release.get("process_heap_trim")
    heap_trim = heap_trim if isinstance(heap_trim, dict) else {}
    global_transfer = audit.get("global_transfer")
    global_transfer = (
        global_transfer if isinstance(global_transfer, dict) else {}
    )
    condensed_system = audit.get("condensed_system")
    condensed_system = (
        condensed_system if isinstance(condensed_system, dict) else {}
    )
    mesh_identity = summary.get("variable_p_mesh_identity")
    mesh_identity = (
        mesh_identity if isinstance(mesh_identity, dict) else {}
    )
    orientation = summary.get("nedelec_orientation_factor_stats")
    orientation = orientation if isinstance(orientation, dict) else {}
    domain_volumes = summary.get("domain_tag_volumes")
    domain_volumes = (
        domain_volumes if isinstance(domain_volumes, dict) else {}
    )
    periodic_mismatch_fields = (
        "floquet_max_face_transform_fit_residual",
        "floquet_max_edge_midpoint_pairing_error",
        "floquet_max_face_midpoint_pairing_error",
        "floquet_edge_corner_constraint_phase_mismatch",
        "floquet_x_face_mismatch",
        "floquet_y_face_mismatch",
        "floquet_edge_corner_mismatch",
    )
    periodic_mismatches = [
        summary.get(name) for name in periodic_mismatch_fields
    ]
    backend_contract = backend_qualification.get("contract")
    backend_contract = (
        set(backend_contract) if isinstance(backend_contract, list) else set()
    )

    checks = {
        "fixed_rectangular_stage4_config": (
            config.get("stage_case") == "stage4_block_grating"
            and config.get("geometry_kind") == "rectangular_block_grating"
            and config.get("mesh_cell_type_resolved") == "hexahedron"
            and config.get("nedelec_degree") == 6
            and config.get("mesh_target_size") == 10.0
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
        ),
        "fixed_task034_physics": (
            config.get("lambda0") == 13.5
            and config.get("incident_theta_deg") == 80.0
            and config.get("incident_phi_deg") == 0.0
            and config.get("period_x") == 50.0
            and config.get("period_y") == 25.0
            and config.get("z_min") == -10.0
            and config.get("z_max") == 130.0
            and config.get("grating_height") == 120.0
            and config.get("grating_width_x") == 17.0
            and config.get("grating_width_y") == 25.0
            and config.get("scattering_background") == "layered"
            and config.get("polarization_kind") == "s"
        ),
        "mesh_and_tag_identity": (
            mesh_identity.get("partition_independent_mesh_sha256")
            == TASK035D_H10_MESH_SHA256
            and mesh_identity.get("cell_tag_sha256")
            == TASK035D_H10_CELL_TAG_SHA256
            and mesh_identity.get("facet_tag_sha256")
            == TASK035D_H10_FACET_TAG_SHA256
            and mesh_identity.get("global_cell_count") == 252
            and mesh_identity.get("mesh_cells_resolved") == [6, 3, 14]
            and summary.get("mesh_cells_resolved") == [6, 3, 14]
            and (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
        ),
        "material_volume_identity": (
            math.isclose(
                float(domain_volumes.get("air", math.nan)),
                111_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("substrate", math.nan)),
                12_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("grating", math.nan)),
                51_000.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
        ),
        "uniform_container_periodic_orientation": (
            summary.get("use_floquet_xy") is True
            and summary.get("floquet_num_slave_edges")
            == summary.get("floquet_num_matched_master_edges")
            and summary.get("floquet_num_slave_faces")
            == summary.get("floquet_num_matched_master_faces")
            and all(
                isinstance(value, (int, float))
                and abs(float(value)) <= 1.0e-12
                for value in periodic_mismatches
            )
            and orientation.get("uses_exact_basix_entity_transforms")
            is True
            and orientation.get("uses_local_moment_fit") is False
            and orientation.get("used_full_boundary_gather") is False
            and orientation.get("created_dense_boundary_square") is False
        ),
        "variable_p_backend_actual": (
            summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035D_CASE097_BACKEND
            and summary.get("stage4_variable_p_active") is True
            and backend_qualification.get("status") == "qualified"
            and backend_qualification.get("qualified_scope") is True
            and backend_qualification.get("element_contract")
            == "exact_sequence_variable_p4_p5_p6_in_p6_container"
            and {
                "geometry_bound_inactive_row_free_variable_p",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            }.issubset(backend_contract)
        ),
        "active_fe_dof_gate": (
            summary.get("num_actual_conforming_active_fe_dofs")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and summary.get("num_actual_conforming_active_fe_dofs") <= 90_000
        ),
        "active_periodic_trace_rows": (
            summary.get("num_active_trace_dofs")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
        ),
        "active_solve_rows": (
            summary.get("num_active_condensed_dofs")
            == TASK035D_T30_SOLVE_ROWS
            and matrix.get("matrix_rows") == TASK035D_T30_SOLVE_ROWS
        ),
        "dtn_rows": (
            summary.get("stage4_dtn_num_auxiliary_dofs")
            == TASK035D_T30_DTN_ROWS
        ),
        "matrix_nonzero_and_no_dynamic_reallocation": (
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and matrix.get("matrix_mallocs") == 0.0
        ),
        "direct_factor_inventory": (
            factor_inventory.get("available") is True
            and factor_inventory.get("factor_solver_type") == "mumps"
            and factor_matrix.get("matrix_rows")
            == TASK035D_T30_SOLVE_ROWS
            and isinstance(
                factor_matrix.get("matrix_nnz_used"),
                (int, float),
            )
            and float(factor_matrix["matrix_nnz_used"]) > 0.0
        ),
        "degree_plan_identity": (
            degree_plan.get("cell_degree_plan_sha256")
            == TASK035D_T30_PLAN_CONTENT_SHA256
            and degree_plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_T30_GEOMETRY_CATALOG_SHA256
            and degree_plan.get("cell_degree_counts")
            == TASK035D_T30_CELL_DEGREE_COUNTS
        ),
        "degree_plan_active_dimensions": (
            degree_plan.get("active_rows")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and degree_plan.get("active_trace_rows")
            == TASK035D_T30_ACTIVE_TRACE_ROWS
        ),
        "periodic_identity": (
            periodic.get("pass") is True
            and periodic.get("mpi_size") == 8
            and periodic.get("independent_periodic_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
            and periodic.get("inactive_p6_rows_globally_numbered") is False
        ),
        "inactive_rows_absent": (
            audit.get("full_p6_global_matrix_allocated") is False
            and audit.get("inactive_p6_rows_globally_numbered") is False
            and audit.get("active_fe_dof_gate_pass") is True
        ),
        "variable_p_audit_chain": (
            audit.get("schema_version")
            == "task035d.variable-p-assembly-reduction.v1"
            and audit.get("status")
            == "variable_p_assembly_time_reduction_built"
            and audit.get("pass") is True
            and degree_plan.get("pass") is True
            and periodic.get("pass") is True
            and global_transfer.get("pass") is True
            and condensed_system.get("pass") is True
            and condensed_system.get("status")
            == "variable_p_condensed_trace_matrix_pass"
            and degree_plan.get("mpi_size") == 8
            and periodic.get("mpi_size") == 8
            and global_transfer.get("mpi_size") == 8
            and condensed_system.get("mpi_size") == 8
        ),
        "trace_only_gate": (
            summary.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            )
            is False
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
            )
            == 0
            and summary.get(
                "stage4_dtn_variable_p_trace_functional_count"
            )
            == 81
            and isinstance(
                summary.get(
                    "stage4_dtn_variable_p_removed_interior_max_abs"
                ),
                (int, float),
            )
            and math.isfinite(
                float(
                    summary[
                        "stage4_dtn_variable_p_removed_interior_max_abs"
                    ]
                )
            )
            and summary[
                "stage4_dtn_variable_p_removed_interior_max_abs"
            ]
            >= 0.0
        ),
        "full_field_recovery": (
            recovery.get("status") == "variable_p_full_field_recovery_pass"
            and recovery.get("pass") is True
        ),
        "full_explicit_true_residual": (
            isinstance(
                full_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(
                full_residual["linear_system_relative_residual"]
            )
            <= 1.0e-9
            and full_residual.get("linear_system_relative_residual")
            == summary.get("linear_system_relative_residual")
        ),
        "eliminated_interior_residual": (
            isinstance(
                full_residual.get(
                    "eliminated_cell_interior_residual_norm"
                ),
                (int, float),
            )
            and float(
                full_residual[
                    "eliminated_cell_interior_residual_norm"
                ]
            )
            <= 1.0e-9
        ),
        "ordinary_default_unchanged": (
            audit.get("ordinary_default_changed") is False
            and config.get("stage4_full3d_assembly_backend")
            == TASK035D_CASE097_BACKEND
            and backend_audit.get("ordinary_default_unchanged") is True
            and backend_audit.get("selection_source") == "public_port"
        ),
        "solver_lifecycle_release": (
            summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess")
            is True
            and solver_release.get("petsc_garbage_cleanup_called") is True
            and heap_trim.get("supported_on_all_ranks") is True
            and heap_trim.get("succeeded_on_all_ranks") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.case097-t30-solver-gate.v1",
        "status": (
            "task035d_t30_solver_identity_pass"
            if not failures
            else "task035d_t30_solver_identity_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "accuracy_credit": "structural_and_residual_only",
    }


__all__ = [
    "TASK035D_CASE097_BACKEND",
    "TASK035D_H10_CELL_TAG_SHA256",
    "TASK035D_H10_FACET_TAG_SHA256",
    "TASK035D_H10_MESH_SHA256",
    "TASK035D_T30_ACTIVE_FE_DOFS",
    "TASK035D_T30_ACTIVE_TRACE_ROWS",
    "TASK035D_T30_AUTHORITY_FILE_SHA256",
    "TASK035D_T30_AUTHORITY_PATH",
    "TASK035D_T30_DTN_ROWS",
    "TASK035D_T30_PERIODIC_TRACE_ROWS",
    "TASK035D_T30_PLAN_CONTENT_SHA256",
    "TASK035D_T30_PLAN_FILE_SHA256",
    "TASK035D_T30_PLAN_PATH",
    "TASK035D_T30_SOLVE_ROWS",
    "task035d_case097_plan_authority_gate",
    "task035d_case097_t30_solver_gate",
]
