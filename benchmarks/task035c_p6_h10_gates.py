from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any


TASK035C_P6_H10_DEGREE = 6
TASK035C_P6_H10_MESH_NM = 10.0
TASK035C_P6_H10_INTERFACES_NM = (10.0, 110.0)
TASK035C_P6_H10_MODE_COUNTS = frozenset({120, 160})
TASK035C_P6_H10_MPI_SIZES = frozenset({1, 2, 4, 8})
TASK035C_P6_H10_BACKENDS = frozenset(
    {"standard_full", "assembly_time_static_condensed"}
)


def valid_hex_digest(value: object, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def task035c_p6_h10_preflight_authority_gate(
    record: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    authority_is_tracked: bool,
) -> dict[str, Any]:
    """Qualify a historical p6/h10 record only as a resource preflight.

    The authority deliberately does not need to share the final Task035c source
    SHA. It proves that the fixed rectangular p6/h10 problem has completed
    safely before. Fresh Full3D/Hybrid physics still has to be generated at the
    exact final source SHA.
    """

    payload = record if isinstance(record, Mapping) else {}
    source = payload.get("source")
    source = source if isinstance(source, Mapping) else {}
    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    qualification_checks = qualification.get("checks")
    qualification_checks = (
        qualification_checks
        if isinstance(qualification_checks, Mapping)
        else {}
    )
    target = payload.get("target_identity")
    target = target if isinstance(target, Mapping) else {}
    enriched = payload.get("enriched")
    enriched = enriched if isinstance(enriched, Mapping) else {}
    matrix = enriched.get("matrix_stats")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}

    residual = enriched.get("linear_system_relative_residual")
    checks = {
        "object_present": bool(payload),
        "schema_identity": bool(
            payload.get("schema_version")
            == "task035.actual-global-r5-watchdog.v1"
            and payload.get("benchmark_id") == "task035_target_actual_global_r5"
        ),
        "record_hash_expected_valid": valid_hex_digest(expected_sha256, 64),
        "record_hash_observed_valid": valid_hex_digest(observed_sha256, 64),
        "record_hash_matches_expected": bool(
            expected_sha256 == observed_sha256
        ),
        "authority_is_git_tracked": authority_is_tracked,
        "historical_run_passed": bool(
            payload.get("status") == "actual_global_r5_pass"
            and qualification.get("pass") is True
            and qualification.get("failures") == []
            and qualification_checks.get("process_completed") is True
            and qualification_checks.get("not_terminated_for_memory") is True
            and qualification_checks.get("not_terminated_for_timeout") is True
            and qualification_checks.get("resource_authority_readable") is True
            and qualification_checks.get("all_expected_mpi_ranks_observed") is True
            and qualification_checks.get("no_process_tree_swap") is True
        ),
        "historical_source_was_clean_and_stable": bool(
            valid_hex_digest(source.get("commit_sha"), 40)
            and source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
        ),
        "fixed_rectangular_identity": bool(
            math.isclose(float(target.get("wavelength_nm", math.nan)), 13.5)
            and math.isclose(
                float(target.get("incidence_theta_deg", math.nan)), 80.0
            )
            and str(target.get("polarization", "")).upper() == "S"
            and target.get("geometry")
            == "Task034 fixed rectangular block grating"
            and target.get("mesh_backend")
            == "boundary-fitted conforming hexahedron"
        ),
        "p6_h10_mpi8_anchor": bool(
            enriched.get("degree") == TASK035C_P6_H10_DEGREE
            and math.isclose(
                float(enriched.get("h_nm", math.nan)),
                TASK035C_P6_H10_MESH_NM,
            )
            and enriched.get("mpi_size") == 8
            and enriched.get("mesh_cell_type_actual") == "hexahedron"
            and enriched.get("case_status") == "completed"
            and enriched.get("official_result") is True
        ),
        "p6_true_residual_le_1e-9": bool(
            isinstance(residual, (int, float)) and float(residual) <= 1.0e-9
        ),
        "positive_measured_matrix_and_memory": bool(
            isinstance(matrix.get("matrix_rows"), (int, float))
            and float(matrix["matrix_rows"]) > 0.0
            and isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and isinstance(resource.get("memory_authority_gib"), (int, float))
            and float(resource["memory_authority_gib"]) > 0.0
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035c.p6-h10-preflight-authority-gate.v1",
        "pass": not failures,
        "role": "historical_resource_preflight_only_not_final_physics_authority",
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "historical_source_sha": source.get("commit_sha"),
        "checks": checks,
        "failures": failures,
    }


def task035c_p6_h10_full3d_reference_gate(
    record: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    current_source_sha: str | None,
    assembly_backend: str,
    mpi_size: int,
    incident_grazing_deg: float = 10.0,
    incident_phi_deg: float = 0.0,
) -> dict[str, Any]:
    """Require a fresh exact-source Full3D reference for Task035c Hybrid."""

    payload = record if isinstance(record, Mapping) else {}
    source = payload.get("source")
    source = source if isinstance(source, Mapping) else {}
    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    qualification_checks = qualification.get("checks")
    qualification_checks = (
        qualification_checks
        if isinstance(qualification_checks, Mapping)
        else {}
    )
    summary = payload.get("solver_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    config = summary.get("config")
    config = config if isinstance(config, Mapping) else {}
    residual = summary.get("linear_system_relative_residual")
    reference_planes = config.get("full3d_reference_plane_z")
    reference_planes = (
        reference_planes if isinstance(reference_planes, list) else []
    )

    checks = {
        "object_present": bool(payload),
        "schema_identity": bool(
            payload.get("schema_version") == "task033.full3d-watchdog.v1"
            and payload.get("benchmark_id") == "task033_target_full3d_watchdog"
        ),
        "record_hash_expected_valid": valid_hex_digest(expected_sha256, 64),
        "record_hash_observed_valid": valid_hex_digest(observed_sha256, 64),
        "record_hash_matches_expected": bool(
            expected_sha256 == observed_sha256
        ),
        "exact_final_source_sha": bool(
            valid_hex_digest(current_source_sha, 40)
            and source.get("commit_sha") == current_source_sha
            and source.get("head_after_sha") == current_source_sha
            and source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
        ),
        "same_p6_h10_mpi_identity": bool(
            payload.get("degree") == TASK035C_P6_H10_DEGREE
            and math.isclose(
                float(payload.get("h_nm", math.nan)),
                TASK035C_P6_H10_MESH_NM,
            )
            and payload.get("mpi_size") == mpi_size
            and payload.get("polarization_kind") == "s"
            and config.get("nedelec_degree") == TASK035C_P6_H10_DEGREE
            and math.isclose(
                float(config.get("mesh_target_size", math.nan)),
                TASK035C_P6_H10_MESH_NM,
            )
        ),
        "matching_backend": bool(
            assembly_backend in TASK035C_P6_H10_BACKENDS
            and payload.get("stage4_full3d_assembly_backend_requested")
            == assembly_backend
            and payload.get("stage4_full3d_assembly_backend_actual")
            == assembly_backend
            and summary.get("stage4_full3d_assembly_backend_actual")
            == assembly_backend
        ),
        "fixed_rectangular_physics": bool(
            summary.get("stage_case") == "stage4_block_grating"
            and summary.get("geometry_kind") == "rectangular_block_grating"
            and math.isclose(float(config.get("lambda0", math.nan)), 13.5)
            and math.isclose(
                float(config.get("incident_theta_deg", math.nan)),
                90.0 - float(incident_grazing_deg),
            )
            and math.isclose(
                float(config.get("incident_phi_deg", math.nan)),
                float(incident_phi_deg),
            )
            and math.isclose(float(config.get("period_x", math.nan)), 50.0)
            and math.isclose(float(config.get("period_y", math.nan)), 25.0)
            and math.isclose(float(config.get("z_min", math.nan)), -10.0)
            and math.isclose(float(config.get("z_max", math.nan)), 130.0)
            and math.isclose(float(config.get("grating_height", math.nan)), 120.0)
            and math.isclose(float(config.get("grating_width_x", math.nan)), 17.0)
            and math.isclose(float(config.get("grating_width_y", math.nan)), 25.0)
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("scattering_background") == "layered"
        ),
        "full_solve_and_reference_export_pass": bool(
            payload.get("run_kind") == "full-solve"
            and payload.get("status") == "full3d_reference_pass"
            and payload.get("return_code") == 0
            and qualification.get("pass") is True
            and qualification.get("failures") == []
            and qualification_checks.get("official_result") is True
            and qualification_checks.get("ksp_converged") is True
            and qualification_checks.get("reference_exported") is True
            and qualification_checks.get("swap_policy_satisfied") is True
            and summary.get("official_result") is True
            and summary.get("full3d_reference_exported") is True
            and any(math.isclose(float(value), 10.0) for value in reference_planes)
            and any(math.isclose(float(value), 110.0) for value in reference_planes)
        ),
        "true_residual_le_1e-9": bool(
            isinstance(residual, (int, float)) and float(residual) <= 1.0e-9
        ),
        "raw_artifact_hashes_present": bool(
            valid_hex_digest(payload.get("solver_summary_sha256"), 64)
            and valid_hex_digest(payload.get("progress_sha256"), 64)
            and valid_hex_digest(payload.get("timeline_sha256"), 64)
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035c.p6-h10-full3d-reference-gate.v1",
        "pass": not failures,
        "assembly_backend": assembly_backend,
        "incident_grazing_deg": float(incident_grazing_deg),
        "incident_phi_deg": float(incident_phi_deg),
        "reference_source_sha": source.get("commit_sha"),
        "current_source_sha": current_source_sha,
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "checks": checks,
        "failures": failures,
    }
