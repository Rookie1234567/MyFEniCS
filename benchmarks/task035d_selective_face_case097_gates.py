"""Frozen launch and solver Gates for the Task035d selective-face candidate."""

from __future__ import annotations

import math
from typing import Any, Mapping

from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_LOCAL_H_BASE_CONFIG_SHA256,
    TASK035D_LOCAL_H_BOX_CATALOG_SHA256,
    TASK035D_LOCAL_H_CARRIER_SHA256,
    TASK035D_LOCAL_H_DTN_ROWS,
    TASK035D_LOCAL_H_HANGING_CATALOG_SHA256,
    TASK035D_LOCAL_H_HANGING_PATCHES,
    TASK035D_LOCAL_H_HANGING_SLAVE_ROWS,
    TASK035D_LOCAL_H_LEAF_CATALOG_SHA256,
    TASK035D_LOCAL_H_LEAF_CELLS,
    TASK035D_LOCAL_H_MATERIAL_SHA256,
    TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS,
    TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256,
    TASK035D_LOCAL_H_ROOT_CELLS,
)


TASK035D_SELECTIVE_FACE_PLAN_NAME = "h15_grating_top_selective_p6_faces_v1"
TASK035D_SELECTIVE_FACE_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "h15_grating_top_selective_p6_faces_plan_v1.json"
)
TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256 = (
    "8691695f7bac96c1ab8094637e8bb1d0adfe5e2d4770427f126857e7909a1e60"
)
TASK035D_SELECTIVE_FACE_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "selective_p6_face_mpi_identity_v1.json"
)
TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256 = (
    "d55bcfad3a9dc9e58ac8229a51e74e27b0a3c76b439a9cc5695914ef0cd5eeb1"
)
TASK035D_SELECTIVE_FACE_COMPONENT_SOURCE_SHA = (
    "478379329d60e379f7b62e22f3979175fd15da60"
)
TASK035D_SELECTIVE_FACE_CHECKER_SOURCE_SHA = "478379329d60e379f7b62e22f3979175fd15da60"
TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256 = (
    "cf525a98007dd9930dd8f40b50e44e14e87e6e3db6c6d704a7dc0f8efbf789d7"
)
TASK035D_SELECTIVE_FACE_FLATTENED_GRAPH_SHA256 = (
    "0c6ddad703585a8ebf84243b3faee9335dc57233781472ee03d3990f6c06ba08"
)
TASK035D_SELECTIVE_FACE_ENTITY_CATALOG_SHA256 = (
    "3321186e54c1fd0ef9c71418338f957cf3ae86bfb24ccf6a64dca1e627115b9e"
)
TASK035D_SELECTIVE_FACE_CELL_GRAPH_SHA256 = (
    "f4efbd2a866878cb920144a9d288ba9ce695974835293115af4df2017b15f0ff"
)
TASK035D_SELECTIVE_FACE_CELL_DEGREE_PLAN_SHA256 = (
    "433b4e88368ae95672e66ec203fdf1988d6e284409f43a99f507cdac3eff1e64"
)
TASK035D_SELECTIVE_FACE_ENTITY_DEGREE_SHA256 = (
    "99dc671f60f7f04e8b2b43b3c1fd24b69f065c5f5727a1066f1023f0e5bb6b73"
)
TASK035D_SELECTIVE_FACE_RAW_ACTIVE_FE_DOFS = 84_375
TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS = 24_075
TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS = 83_125
TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS = 18_590
TASK035D_SELECTIVE_FACE_SOLVE_ROWS = 18_670
TASK035D_SELECTIVE_FACE_SELECTED_COUNT = 10
TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS = (
    (2, 92857142857, 0, 5892857143, 0, 8928571429),
    (2, 92857142857, 0, 5892857143, 8928571429, 17857142857),
    (2, 92857142857, 11785714286, 17857142857, 0, 8928571429),
    (
        2,
        92857142857,
        11785714286,
        17857142857,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 17857142857, 23928571429, 0, 8928571429),
    (
        2,
        92857142857,
        17857142857,
        23928571429,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 23928571429, 29821428571, 0, 8928571429),
    (
        2,
        92857142857,
        23928571429,
        29821428571,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 29821428571, 35714285714, 0, 8928571429),
    (
        2,
        92857142857,
        29821428571,
        35714285714,
        8928571429,
        17857142857,
    ),
)


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_nonnegative_le(value: Any, limit: float) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= float(limit)
    )


_EXPECTED_STABLE_IDENTITY = {
    "actual_full3d_equivalent_active_fe_dofs": (TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS),
    "base_config_identity_sha256": TASK035D_LOCAL_H_BASE_CONFIG_SHA256,
    "canonical_cell_graph_sha256": (TASK035D_SELECTIVE_FACE_CELL_GRAPH_SHA256),
    "carrier_connectivity_sha256": TASK035D_LOCAL_H_CARRIER_SHA256,
    "cell_degree_counts": {"p4": 0, "p5": 0, "p6": 134},
    "cell_degree_plan_sha256": (TASK035D_SELECTIVE_FACE_CELL_DEGREE_PLAN_SHA256),
    "flattened_graph_sha256": (TASK035D_SELECTIVE_FACE_FLATTENED_GRAPH_SHA256),
    "geometry_canonical_entity_degree_sha256": (
        TASK035D_SELECTIVE_FACE_ENTITY_DEGREE_SHA256
    ),
    "hanging_face_catalog_sha256": (TASK035D_LOCAL_H_HANGING_CATALOG_SHA256),
    "hanging_patch_count": TASK035D_LOCAL_H_HANGING_PATCHES,
    "hanging_slave_rows": TASK035D_LOCAL_H_HANGING_SLAVE_ROWS,
    "independent_trace_rows": (TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS),
    "leaf_catalog_sha256": TASK035D_LOCAL_H_LEAF_CATALOG_SHA256,
    "leaf_cell_count": TASK035D_LOCAL_H_LEAF_CELLS,
    "local_variable_trace_implemented": True,
    "material_catalog_sha256": TASK035D_LOCAL_H_MATERIAL_SHA256,
    "mesh_cell_box_catalog_sha256": TASK035D_LOCAL_H_BOX_CATALOG_SHA256,
    "periodic_slave_rows": TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS,
    "physical_authority_sha256": (TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256),
    "physical_facet_catalog_sha256": (TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256),
    "plan_file_sha256": TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
    "predicted_direct_solve_rows": TASK035D_SELECTIVE_FACE_SOLVE_ROWS,
    "raw_broken_active_fe_dofs": (TASK035D_SELECTIVE_FACE_RAW_ACTIVE_FE_DOFS),
    "raw_broken_trace_rows": TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS,
    "root_cell_count": TASK035D_LOCAL_H_ROOT_CELLS,
    "selected_p6_face_count": TASK035D_SELECTIVE_FACE_SELECTED_COUNT,
    "selected_p6_face_geometry_keys": [
        list(key) for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS
    ],
    "selected_p6_periodic_orbit_count": 0,
    "selective_trace_full3d_dof_delta": 200,
    "trace_degree_values": [5, 6],
}

_EXPECTED_COMPONENT_RECORDS = [
    {
        "mpi_size": 1,
        "path": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "selective_p6_face_mpi1_v1.json"
        ),
        "sha256": ("e4e8d22916213adc8b0d4e8b0d9fb5910b75ba5158faa36344c8e4bb61258a7f"),
    },
    {
        "mpi_size": 2,
        "path": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "selective_p6_face_mpi2_v1.json"
        ),
        "sha256": ("34b8a5df103d090353181fb99466c88217e5626f14b7f24816188a83680add51"),
    },
    {
        "mpi_size": 8,
        "path": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "selective_p6_face_mpi8_v1.json"
        ),
        "sha256": ("0d680ec981b47039084b104234493436a5553394d58506f24ae935f399080d8c"),
    },
]


def task035d_case097_selective_face_plan_authority_gate(
    plan: Mapping[str, Any] | None,
    authority: Mapping[str, Any] | None,
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
    """Validate the immutable component authority before an MPI8 PDE."""

    plan = plan if isinstance(plan, Mapping) else {}
    authority = authority if isinstance(authority, Mapping) else {}
    base = plan.get("base_config")
    base = base if isinstance(base, Mapping) else {}
    forest = plan.get("expected_forest")
    forest = forest if isinstance(forest, Mapping) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    checker = authority.get("checker_identity")
    checker = checker if isinstance(checker, Mapping) else {}
    cross = authority.get("cross_checks")
    cross = cross if isinstance(cross, Mapping) else {}
    selected = plan.get("selected_p6_face_geometry_keys")
    expected_selected = [list(key) for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS]
    checks = {
        "tracked_inputs": plan_is_tracked and authority_is_tracked,
        "hash_bound_inputs": (
            _valid_hex(expected_plan_file_sha256, 64)
            and observed_plan_file_sha256
            == expected_plan_file_sha256
            == TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256
            and _valid_hex(expected_authority_sha256, 64)
            and observed_authority_sha256
            == expected_authority_sha256
            == TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256
        ),
        "path_identity": (
            plan_path_from_root == TASK035D_SELECTIVE_FACE_PLAN_PATH
            and authority_path_from_root == TASK035D_SELECTIVE_FACE_AUTHORITY_PATH
        ),
        "fixed_rectangular_h15_plan": (
            plan.get("schema_version") == "task035d.stage4-local-h-refinement-plan.v1"
            and plan.get("status") == "stage4_balanced_local_h_plan"
            and base.get("identity_sha256") == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and base.get("geometry_kind") == "rectangular_block_grating"
            and base.get("mesh_target_size") == 15.0
            and base.get("mesh_cells_resolved") == [6, 2, 10]
            and plan.get("maximum_level") == 1
            and plan.get("trace_degree") == 5
            and plan.get("cell_interior_degree") == 6
        ),
        "same_one_sided_local_h_forest": (
            plan.get("marked_root_boxes")
            == [
                {
                    "lower": [8.25, 0.0, 120.0],
                    "upper": [16.5, 12.5, 130.0],
                }
            ]
            and forest.get("root_cell_count") == TASK035D_LOCAL_H_ROOT_CELLS
            and forest.get("leaf_cell_count") == TASK035D_LOCAL_H_LEAF_CELLS
            and forest.get("hanging_patch_count") == TASK035D_LOCAL_H_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_LOCAL_H_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_LOCAL_H_HANGING_CATALOG_SHA256
        ),
        "exact_ten_face_seed": (
            selected == expected_selected
            and provenance.get("candidate_id") == TASK035D_SELECTIVE_FACE_PLAN_NAME
            and provenance.get("accuracy_credit") is False
            and provenance.get("goal_oriented_selection_credit_before_run") is False
            and "no pre-run DWR credit" in str(provenance.get("selection_evidence", ""))
        ),
        "authority_schema_and_source": (
            authority.get("schema_version")
            == "case097.selective-p6-face-mpi-identity.v1"
            and authority.get("status") == "selective_p6_face_mpi_identity_pass"
            and authority.get("pass") is True
            and authority.get("candidate_id") == TASK035D_SELECTIVE_FACE_PLAN_NAME
            and authority.get("source_sha")
            == TASK035D_SELECTIVE_FACE_COMPONENT_SOURCE_SHA
            and authority.get("live_head") == TASK035D_SELECTIVE_FACE_CHECKER_SOURCE_SHA
            and checker.get("source_sha") == TASK035D_SELECTIVE_FACE_CHECKER_SOURCE_SHA
            and checker.get("verified_clean_checker") is True
            and checker.get("status_lines") == []
        ),
        "authority_inputs_and_cross_checks": (
            authority.get("input_records") == _EXPECTED_COMPONENT_RECORDS
            and bool(cross)
            and all(value is True for value in cross.values())
        ),
        "authority_stable_identity": (
            authority.get("stable_identity") == _EXPECTED_STABLE_IDENTITY
        ),
        "authority_plan_identity": (
            authority.get("plan")
            == {
                "path": TASK035D_SELECTIVE_FACE_PLAN_PATH,
                "sha256": TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
            }
        ),
        "pre_pde_scope_and_dof_budget": (
            authority.get("pde_launch_gate") is True
            and authority.get("pde_accuracy_credit") is False
            and authority.get("failures") == []
            and TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS <= 90_000
        ),
        "ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
            and authority.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": ("task035d.case097-selective-p6-face-launch-gate.v1"),
        "status": (
            "task035d_selective_p6_face_launch_authority_pass"
            if not failures
            else "task035d_selective_p6_face_launch_authority_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "candidate": TASK035D_SELECTIVE_FACE_PLAN_NAME,
        "accuracy_credit": ("none_until_fresh_12_channel_checker_passes"),
        "plan_identity": {
            "path": TASK035D_SELECTIVE_FACE_PLAN_PATH,
            "file_sha256": TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
            "actual_conforming_active_fe_dofs": (
                TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS
            ),
            "predicted_direct_solve_rows": (TASK035D_SELECTIVE_FACE_SOLVE_ROWS),
        },
        "selection_credit": {
            "structural_resource_anchor": True,
            "actual_channel_dwr": False,
            "goal_oriented_selection_credit": False,
            "posthoc_actual_action_attribution": False,
            "complete_combined_hp_credit": False,
        },
        "actual_full3d_equivalent_active_fe_dofs": (
            TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS
        ),
        "predicted_direct_solve_rows": TASK035D_SELECTIVE_FACE_SOLVE_ROWS,
        "goal_oriented_selection_credit_before_live_dwr": False,
        "ordinary_default_changed": False,
    }


def task035d_case097_selective_face_solver_gate(
    solver_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the actual inactive-row-free selective-face PDE system."""

    summary = solver_summary if isinstance(solver_summary, Mapping) else {}
    config = summary.get("config")
    config = config if isinstance(config, Mapping) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    audit = summary.get("cell_static_condensation")
    audit = audit if isinstance(audit, Mapping) else {}
    local_h = audit.get("local_h")
    local_h = local_h if isinstance(local_h, Mapping) else {}
    mesh = local_h.get("mesh")
    mesh = mesh if isinstance(mesh, Mapping) else {}
    forest = mesh.get("forest")
    forest = forest if isinstance(forest, Mapping) else {}
    carrier = mesh.get("carrier")
    carrier = carrier if isinstance(carrier, Mapping) else {}
    physical = local_h.get("physical_trace")
    physical = physical if isinstance(physical, Mapping) else {}
    physical_checks = physical.get("checks")
    physical_checks = physical_checks if isinstance(physical_checks, Mapping) else {}
    trace = audit.get("trace_constraints")
    trace = trace if isinstance(trace, Mapping) else {}
    degree = audit.get("degree_plan")
    degree = degree if isinstance(degree, Mapping) else {}
    condensed = audit.get("condensed_system")
    condensed = condensed if isinstance(condensed, Mapping) else {}
    recovery = audit.get("recovery")
    recovery = recovery if isinstance(recovery, Mapping) else {}
    trace_recovery = recovery.get("trace_constraint_recovery")
    trace_recovery = trace_recovery if isinstance(trace_recovery, Mapping) else {}
    residual = audit.get("full_explicit_true_residual")
    residual = residual if isinstance(residual, Mapping) else {}
    qualification = summary.get("stage4_full3d_assembly_backend_qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    backend_contract = qualification.get("contract")
    backend_contract = (
        set(backend_contract) if isinstance(backend_contract, list) else set()
    )
    factor = summary.get("stage4_dtn_factor_inventory")
    factor = factor if isinstance(factor, Mapping) else {}
    factor_matrix = factor.get("matrix_stats")
    factor_matrix = factor_matrix if isinstance(factor_matrix, Mapping) else {}
    release = summary.get("solver_release_audit")
    release = release if isinstance(release, Mapping) else {}
    heap_trim = release.get("process_heap_trim")
    heap_trim = heap_trim if isinstance(heap_trim, Mapping) else {}
    expected_selected = [list(key) for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS]
    checks = {
        "fixed_rectangular_h15_config": (
            config.get("stage_case") == "stage4_block_grating"
            and config.get("geometry_kind") == "rectangular_block_grating"
            and config.get("mesh_cell_type_resolved") == "hexahedron"
            and config.get("nedelec_degree") == 6
            and config.get("mesh_target_size") == 15.0
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("stage4_variable_p_cell_degree_plan") is None
            and isinstance(
                config.get("stage4_local_h_refinement_plan"),
                str,
            )
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
        "qualified_opt_in_backend": (
            summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035D_CASE097_BACKEND
            and summary.get("stage4_variable_p_active") is True
            and summary.get("stage4_local_h_active") is True
            and qualification.get("status") == "qualified"
            and qualification.get("qualified_scope") is True
            and {
                "geometry_bound_balanced_local_h_hanging_trace_elimination",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            }.issubset(backend_contract)
        ),
        "shared_local_h_mesh_identity": (
            mesh.get("pass") is True
            and mesh.get("plan_file_sha256") == TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256
            and mesh.get("base_config_identity_sha256")
            == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and mesh.get("root_cell_count") == TASK035D_LOCAL_H_ROOT_CELLS
            and mesh.get("leaf_cell_count") == TASK035D_LOCAL_H_LEAF_CELLS
            and mesh.get("hanging_patch_count") == TASK035D_LOCAL_H_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_LOCAL_H_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_LOCAL_H_HANGING_CATALOG_SHA256
            and carrier.get("canonical_connectivity_sha256")
            == TASK035D_LOCAL_H_CARRIER_SHA256
            and carrier.get("physical_facet_catalog_sha256")
            == TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256
            and carrier.get("material_catalog_sha256")
            == TASK035D_LOCAL_H_MATERIAL_SHA256
        ),
        "selective_face_physical_authority": (
            physical.get("pass") is True
            and physical.get("mpi_size") == 8
            and physical.get("degree") == 5
            and physical.get("trace_degree_values") == [5, 6]
            and physical.get("selected_p6_face_count")
            == TASK035D_SELECTIVE_FACE_SELECTED_COUNT
            and physical.get("selected_p6_face_geometry_keys") == expected_selected
            and physical.get("selected_p6_periodic_orbit_count") == 0
            and physical_checks.get("selected_p6_faces_are_not_hanging") is True
            and physical_checks.get("selected_p6_faces_close_periodic_orbits") is True
            and physical.get("selective_trace_full3d_dof_delta") == 200
            and physical.get("physical_authority_sha256")
            == TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256
        ),
        "inactive_row_free_reduction_dimensions": (
            local_h.get("pass") is True
            and local_h.get("raw_broken_active_fe_dofs")
            == TASK035D_SELECTIVE_FACE_RAW_ACTIVE_FE_DOFS
            and local_h.get("raw_broken_trace_rows")
            == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and local_h.get("hanging_slave_rows") == TASK035D_LOCAL_H_HANGING_SLAVE_ROWS
            and local_h.get("periodic_slave_rows")
            == TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS
            and local_h.get("actual_full3d_equivalent_active_fe_dofs")
            == TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS
            and local_h.get("independent_trace_rows")
            == TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS
            and local_h.get("active_fe_dof_gate_pass") is True
            and summary.get("num_actual_conforming_active_fe_dofs")
            == TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS
            and summary.get("num_active_trace_dofs")
            == TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS
            and summary.get("num_active_condensed_dofs")
            == TASK035D_SELECTIVE_FACE_SOLVE_ROWS
        ),
        "combined_constraint_identity": (
            trace.get("pass") is True
            and trace.get("mpi_size") == 8
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("raw_trace_rows") == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and trace.get("independent_trace_rows")
            == TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS
            and trace.get("flattened_graph_sha256")
            == TASK035D_SELECTIVE_FACE_FLATTENED_GRAPH_SHA256
            and trace.get("canonical_cell_graph_sha256")
            == TASK035D_SELECTIVE_FACE_CELL_GRAPH_SHA256
            and trace.get("local_variable_trace_implemented") is True
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get("hanging_or_floquet_slave_rows_globally_numbered") is False
        ),
        "degree_plan_identity": (
            degree.get("pass") is True
            and degree.get("cell_degree_counts") == {"p4": 0, "p5": 0, "p6": 134}
            and degree.get("trace_degree_values") == [5, 6]
            and degree.get("selected_p6_face_count") == 10
            and degree.get("local_variable_trace_implemented") is True
            and degree.get("cell_degree_plan_sha256")
            == TASK035D_SELECTIVE_FACE_CELL_DEGREE_PLAN_SHA256
            and degree.get("geometry_canonical_entity_degree_sha256")
            == TASK035D_SELECTIVE_FACE_ENTITY_DEGREE_SHA256
            and degree.get("active_rows") == TASK035D_SELECTIVE_FACE_RAW_ACTIVE_FE_DOFS
            and degree.get("active_trace_rows")
            == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and degree.get("mesh_cell_box_catalog_sha256")
            == TASK035D_LOCAL_H_BOX_CATALOG_SHA256
        ),
        "matrix_and_factor_rows": (
            matrix.get("matrix_rows") == TASK035D_SELECTIVE_FACE_SOLVE_ROWS
            and isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and matrix.get("matrix_mallocs") == 0.0
            and factor.get("available") is True
            and factor.get("factor_solver_type") == "mumps"
            and factor_matrix.get("matrix_rows") == TASK035D_SELECTIVE_FACE_SOLVE_ROWS
        ),
        "no_hidden_p6_or_numbered_inactive_rows": (
            audit.get("pass") is True
            and condensed.get("pass") is True
            and condensed.get("active_full3d_rows_before_condensation")
            == TASK035D_SELECTIVE_FACE_RAW_ACTIVE_FE_DOFS
            and condensed.get("active_trace_rows_before_constraint_elimination")
            == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and condensed.get("active_trace_rows")
            == TASK035D_SELECTIVE_FACE_INDEPENDENT_TRACE_ROWS
            and condensed.get("appended_rows") == TASK035D_LOCAL_H_DTN_ROWS
            and audit.get("full_p6_global_matrix_allocated") is False
            and audit.get("inactive_p6_rows_globally_numbered") is False
            and condensed.get("hanging_or_floquet_slave_rows_globally_numbered")
            is False
        ),
        "full_field_recovery": (
            recovery.get("pass") is True
            and trace_recovery.get("pass") is True
            and trace_recovery.get("covered_raw_trace_rows")
            == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and trace_recovery.get("expected_raw_trace_rows")
            == TASK035D_SELECTIVE_FACE_RAW_TRACE_ROWS
            and float(trace_recovery.get("maximum_abs_error", math.inf)) <= 5.0e-11
            and float(trace_recovery.get("relative_l2_error", math.inf)) <= 5.0e-11
        ),
        "full_explicit_true_residual": (
            _finite_nonnegative_le(
                residual.get("linear_system_relative_residual"),
                1.0e-9,
            )
            and residual.get("linear_system_relative_residual")
            == summary.get("linear_system_relative_residual")
            and _finite_nonnegative_le(
                residual.get("eliminated_cell_interior_residual_norm"),
                1.0e-9,
            )
        ),
        "trace_only_dtn": (
            summary.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            )
            is False
            and summary.get("stage4_dtn_num_auxiliary_dofs")
            == TASK035D_LOCAL_H_DTN_ROWS
        ),
        "ordinary_default_and_lifecycle": (
            audit.get("ordinary_default_changed") is False
            and config.get("stage4_full3d_assembly_backend") == TASK035D_CASE097_BACKEND
            and summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess") is True
            and release.get("petsc_garbage_cleanup_called") is True
            and heap_trim.get("supported_on_all_ranks") is True
            and heap_trim.get("succeeded_on_all_ranks") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": ("task035d.case097-selective-p6-face-solver-gate.v1"),
        "status": (
            "task035d_selective_p6_face_solver_identity_pass"
            if not failures
            else "task035d_selective_p6_face_solver_identity_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "candidate": TASK035D_SELECTIVE_FACE_PLAN_NAME,
        "accuracy_credit": "structural_and_residual_only",
        "full_case095_physics_gate_still_independent": True,
    }


__all__ = [
    "TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS",
    "TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256",
    "TASK035D_SELECTIVE_FACE_AUTHORITY_PATH",
    "TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256",
    "TASK035D_SELECTIVE_FACE_PLAN_NAME",
    "TASK035D_SELECTIVE_FACE_PLAN_PATH",
    "TASK035D_SELECTIVE_FACE_SOLVE_ROWS",
    "task035d_case097_selective_face_plan_authority_gate",
    "task035d_case097_selective_face_solver_gate",
]
