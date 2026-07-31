from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TASK035C_P6_H10_DEGREE = 6
TASK035C_P6_H10_MESH_NM = 10.0
TASK035C_P6_H10_INTERFACES_NM = (10.0, 110.0)
TASK035C_P6_H10_MODE_COUNTS = frozenset({120, 160})
TASK035C_P6_H10_MPI_SIZES = frozenset({1, 2, 4, 8})
TASK035C_P6_H10_BACKENDS = frozenset(
    {"standard_full", "assembly_time_static_condensed"}
)
_TASK036_REFERENCE_COMPATIBLE_EXACT_PATHS = frozenset(
    {
        "benchmarks/analyze_task036_robustness_scan.py",
        "benchmarks/cases/099_strong_trace_hybrid_fixture/README.md",
        "benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_strong_trace_fixed_channels_v1.csv",
        "benchmarks/cases/099_strong_trace_hybrid_fixture/records/strong_trace_exact_fixture_v1.json",
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/run_task036_one_cell_discrete_bloch.py",
        "benchmarks/run_task036_robustness_scan.py",
        "benchmarks/task035c_p6_h10_gates.py",
        "src/coupling/hybrid_internal_modes.py",
        "src/postprocessing/hybrid_field_reconstruction.py",
        "src/solvers/hybrid_strong_trace_direct.py",
        "src/solvers/one_cell_discrete_bloch.py",
        "src/test/test_181_task035c_p6_h10_runner_gates.py",
        "src/test/test_59_task033_memory_watchdog_contract.py",
        "src/test/test_197_task036_robustness_scan_points.py",
        "src/test/test_198_task036_robustness_analyzer.py",
        "src/test/test_199_task036_strong_trace_hybrid.py",
        "src/test/test_214_task036_one_cell_discrete_bloch.py",
        "src/test/test_40_task032_hybrid_field_reconstruction.py",
        "src/test/test_52_task033_high_order_matched_trace.py",
    }
)
_TASK036_REFERENCE_COMPATIBLE_PREFIXES = (
    "docs/task036_forward_solver_bugfix_hardening/",
)


def task036_strong_trace_anchor_id(
    *,
    incident_grazing_deg: float,
    incident_phi_deg: float,
    polarization_kind: str,
    grating_height_nm: float,
    grating_width_x_nm: float,
) -> str | None:
    """Identify one of the three Review V3 strong-trace anchors."""

    common_geometry = bool(
        math.isclose(grating_height_nm, 120.0)
        and math.isclose(grating_width_x_nm, 17.0)
    )
    if not common_geometry:
        return None
    candidates = (
        ("A004-S", 0.5, 45.0, "s"),
        ("A049-P", 10.0, 90.0, "p"),
        ("A001-P", 0.5, 0.0, "p"),
    )
    for point_id, grazing, azimuth, polarization in candidates:
        if (
            math.isclose(incident_grazing_deg, grazing)
            and math.isclose(incident_phi_deg, azimuth)
            and polarization_kind == polarization
        ):
            return point_id
    return None


def task036_strong_trace_anchor_scope(
    *,
    requested_modes: int,
    incident_grazing_deg: float,
    incident_phi_deg: float,
    polarization_kind: str,
    grating_height_nm: float,
    grating_width_x_nm: float,
) -> bool:
    """Restrict M120/M160 to the exact Review V3 execution contract."""

    point_id = task036_strong_trace_anchor_id(
        incident_grazing_deg=incident_grazing_deg,
        incident_phi_deg=incident_phi_deg,
        polarization_kind=polarization_kind,
        grating_height_nm=grating_height_nm,
        grating_width_x_nm=grating_width_x_nm,
    )
    return bool(
        point_id is not None
        and (
            requested_modes == 120
            or (requested_modes == 160 and point_id == "A001-P")
        )
    )


def task036_strong_trace_interface_scope(
    *,
    bottom_interface_nm: float,
    top_interface_nm: float,
    incident_grazing_deg: float,
    incident_phi_deg: float,
    polarization_kind: str,
    grating_height_nm: float,
    grating_width_x_nm: float,
) -> bool:
    """Open only the frozen Review V5 A004-S interface diagnostics."""

    pair = (float(bottom_interface_nm), float(top_interface_nm))
    if pair == (10.0, 110.0):
        return True
    return bool(
        pair in {(30.0, 90.0), (40.0, 80.0)}
        and task036_strong_trace_anchor_id(
            incident_grazing_deg=incident_grazing_deg,
            incident_phi_deg=incident_phi_deg,
            polarization_kind=polarization_kind,
            grating_height_nm=grating_height_nm,
            grating_width_x_nm=grating_width_x_nm,
        )
        == "A004-S"
    )


def valid_hex_digest(value: object, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _git(*arguments: str) -> str | None:
    """Run one read-only Git query, returning ``None`` on any failure."""

    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _task036_full3d_reference_source_compatibility(
    reference_source_sha: object,
    current_source_sha: object,
) -> dict[str, Any]:
    """Fail closed unless source drift is exact or Hybrid-component-disjoint."""

    valid = bool(
        valid_hex_digest(reference_source_sha, 40)
        and valid_hex_digest(current_source_sha, 40)
    )
    reference_sha = (
        str(reference_source_sha).lower() if valid else None
    )
    current_sha = str(current_source_sha).lower() if valid else None
    exact = bool(valid and reference_sha == current_sha)
    if exact:
        merge_base = reference_sha
        rendered_diff: str | None = ""
    elif valid:
        merge_base = _git("merge-base", reference_sha, current_sha)
        rendered_diff = _git(
            "diff",
            "--name-only",
            "--no-renames",
            f"{reference_sha}..{current_sha}",
            "--",
        )
    else:
        merge_base = None
        rendered_diff = None

    changed_paths = (
        []
        if rendered_diff is None
        else sorted(
            {
                line.strip()
                for line in rendered_diff.splitlines()
                if line.strip()
            }
        )
    )

    def allowed(path: str) -> bool:
        return bool(
            path in _TASK036_REFERENCE_COMPATIBLE_EXACT_PATHS
            or any(
                path.startswith(prefix)
                for prefix in _TASK036_REFERENCE_COMPATIBLE_PREFIXES
            )
        )

    allowed_paths = [path for path in changed_paths if allowed(path)]
    disallowed_paths = [path for path in changed_paths if not allowed(path)]
    checks = {
        "source_shas_valid": valid,
        "reference_source_is_ancestor": bool(
            valid and merge_base == reference_sha
        ),
        "source_diff_readable": rendered_diff is not None,
        "only_component_disjoint_or_nonnumerical_changes": (
            not disallowed_paths
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task036.full3d-source-compatibility.v1",
        "pass": not failures,
        "exact_source_sha": exact,
        "reference_source_sha": reference_sha,
        "current_source_sha": current_sha,
        "merge_base": merge_base,
        "changed_paths": changed_paths,
        "allowed_changed_paths": allowed_paths,
        "disallowed_changed_paths": disallowed_paths,
        "checks": checks,
        "failures": failures,
    }


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


def task036_full3d_reference_gate(
    record: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    current_source_sha: str | None,
    assembly_backend: str,
    degree: int,
    h_nm: float,
    mpi_size: int,
    polarization_kind: str,
    incident_grazing_deg: float,
    incident_phi_deg: float,
    grating_height_nm: float,
    grating_width_x_nm: float,
    mesh_axis_cell_counts: tuple[int, int, int],
) -> dict[str, Any]:
    """Bind one Task036 Hybrid point to its exact same-input Full3D authority."""

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
    reference_planes = config.get("full3d_reference_plane_z")
    reference_planes = (
        reference_planes if isinstance(reference_planes, list) else []
    )
    requested_axis_counts = config.get("mesh_axis_cell_counts_requested")
    if requested_axis_counts is None:
        requested_axis_counts = config.get("mesh_axis_cell_counts")
    direct_audit = payload.get("task036_direct_projection_audit")
    direct_audit = (
        direct_audit if isinstance(direct_audit, Mapping) else {}
    )
    residual = summary.get("linear_system_relative_residual")
    parent = payload.get("parent_launch_descriptor")
    parent = parent if isinstance(parent, Mapping) else {}
    parent_payload = parent.get("payload")
    parent_payload = (
        parent_payload if isinstance(parent_payload, Mapping) else {}
    )
    worker_contract = parent_payload.get("worker_contract")
    worker_contract = (
        worker_contract if isinstance(worker_contract, Mapping) else {}
    )
    reference_source_sha = source.get("commit_sha")
    source_compatibility = (
        _task036_full3d_reference_source_compatibility(
            reference_source_sha,
            current_source_sha,
        )
    )

    checks = {
        "object_present": bool(payload),
        "schema_identity": bool(
            payload.get("schema_version") == "task033.full3d-watchdog.v1"
            and payload.get("benchmark_id")
            == "task033_target_full3d_watchdog"
        ),
        "record_hash_expected_valid": valid_hex_digest(expected_sha256, 64),
        "record_hash_observed_valid": valid_hex_digest(observed_sha256, 64),
        "record_hash_matches_expected": bool(
            expected_sha256 == observed_sha256
        ),
        "reference_source_clean_and_self_consistent": bool(
            valid_hex_digest(reference_source_sha, 40)
            and source.get("verified_clean_sha") == reference_source_sha
            and source.get("head_after_sha") == reference_source_sha
            and source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
            and source.get("status_after") == ""
        ),
        "reference_source_exact_or_component_disjoint": (
            source_compatibility["pass"]
        ),
        "same_discretization_and_polarization": bool(
            payload.get("degree") == degree
            and math.isclose(
                float(payload.get("h_nm", math.nan)), float(h_nm)
            )
            and payload.get("mpi_size") == mpi_size
            and str(payload.get("polarization_kind", "")).lower()
            == str(polarization_kind).lower()
            and config.get("nedelec_degree") == degree
            and math.isclose(
                float(config.get("mesh_target_size", math.nan)), float(h_nm)
            )
            and requested_axis_counts == list(mesh_axis_cell_counts)
        ),
        "parent_worker_contract_matches": bool(
            parent_payload.get("schema_version")
            == "task033.watchdog-parent-launch.v1"
            and worker_contract.get("degree") == degree
            and math.isclose(
                float(worker_contract.get("h_nm", math.nan)), float(h_nm)
            )
            and worker_contract.get("mpi_size") == mpi_size
            and str(
                worker_contract.get("polarization_kind", "")
            ).lower()
            == str(polarization_kind).lower()
            and worker_contract.get("run_kind") == "full-solve"
            and worker_contract.get(
                "stage4_full3d_assembly_backend"
            )
            == assembly_backend
            and worker_contract.get("task036_forward_robustness_gate")
            is True
            and math.isclose(
                float(
                    worker_contract.get(
                        "incident_grazing_deg", math.nan
                    )
                ),
                float(incident_grazing_deg),
            )
            and math.isclose(
                float(
                    worker_contract.get("incident_phi_deg", math.nan)
                ),
                float(incident_phi_deg),
            )
            and math.isclose(
                float(
                    worker_contract.get("grating_height_nm", math.nan)
                ),
                float(grating_height_nm),
            )
            and math.isclose(
                float(
                    worker_contract.get(
                        "grating_width_x_nm", math.nan
                    )
                ),
                float(grating_width_x_nm),
            )
            and worker_contract.get("task036_mesh_axis_cell_counts")
            == list(mesh_axis_cell_counts)
            and worker_contract.get(
                "task036_y_invariant_n0_alias_preflight"
            )
            is True
            and worker_contract.get(
                "task036_dtn_direct_projection_audit"
            )
            is True
            and worker_contract.get("verified_clean_sha")
            == reference_source_sha
        ),
        "matching_static_backend": bool(
            assembly_backend == "assembly_time_static_condensed"
            and payload.get("stage4_full3d_assembly_backend_requested")
            == assembly_backend
            and payload.get("stage4_full3d_assembly_backend_actual")
            == assembly_backend
            and summary.get("stage4_full3d_assembly_backend_actual")
            == assembly_backend
        ),
        "matching_task036_physics_identity": bool(
            payload.get("task036_forward_robustness_gate") is True
            and summary.get("stage_case") == "stage4_block_grating"
            and summary.get("geometry_kind")
            == "rectangular_block_grating"
            and math.isclose(float(config.get("lambda0", math.nan)), 13.5)
            and math.isclose(
                float(config.get("incident_theta_deg", math.nan)),
                90.0 - float(incident_grazing_deg),
            )
            and math.isclose(
                float(config.get("incident_phi_deg", math.nan)),
                float(incident_phi_deg),
            )
            and str(config.get("polarization_kind", "")).lower()
            == str(polarization_kind).lower()
            and math.isclose(float(config.get("period_x", math.nan)), 50.0)
            and math.isclose(float(config.get("period_y", math.nan)), 25.0)
            and math.isclose(float(config.get("z_min", math.nan)), -10.0)
            and math.isclose(float(config.get("z_max", math.nan)), 130.0)
            and math.isclose(
                float(config.get("grating_height", math.nan)),
                float(grating_height_nm),
            )
            and math.isclose(
                float(config.get("grating_width_x", math.nan)),
                float(grating_width_x_nm),
            )
            and math.isclose(
                float(config.get("grating_width_y", math.nan)), 25.0
            )
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("scattering_background") == "layered"
            and config.get("dtn_y_invariant_n0_alias_preflight") is True
            and config.get("dtn_auxiliary_direct_projection_audit") is True
        ),
        "full_solve_and_reference_export_pass": bool(
            payload.get("run_kind") == "full-solve"
            and payload.get("status") == "full3d_reference_pass"
            and payload.get("return_code") == 0
            and payload.get("no_swap") is True
            and qualification.get("pass") is True
            and qualification.get("failures") == []
            and qualification_checks.get("official_result") is True
            and qualification_checks.get("ksp_converged") is True
            and qualification_checks.get("reference_exported") is True
            and qualification_checks.get("swap_policy_satisfied") is True
            and summary.get("official_result") is True
            and summary.get("full3d_reference_exported") is True
            and any(
                math.isclose(float(value), 10.0)
                for value in reference_planes
            )
            and any(
                math.isclose(float(value), 110.0)
                for value in reference_planes
            )
        ),
        "direct_projection_audit_pass": bool(
            direct_audit.get("requested") is True
            and direct_audit.get("pass") is True
            and isinstance(
                direct_audit.get(
                    "max_absolute_outgoing_projection_difference"
                ),
                (int, float),
            )
            and float(
                direct_audit[
                    "max_absolute_outgoing_projection_difference"
                ]
            )
            <= 1.0e-10
        ),
        "true_residual_le_1e-9": bool(
            isinstance(residual, (int, float))
            and not isinstance(residual, bool)
            and math.isfinite(float(residual))
            and 0.0 <= float(residual) <= 1.0e-9
        ),
        "raw_artifact_hashes_present": bool(
            valid_hex_digest(payload.get("solver_summary_sha256"), 64)
            and valid_hex_digest(payload.get("progress_sha256"), 64)
            and valid_hex_digest(payload.get("timeline_sha256"), 64)
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task036.full3d-reference-gate.v1",
        "pass": not failures,
        "reference_source_sha": reference_source_sha,
        "current_source_sha": current_source_sha,
        "source_compatibility": source_compatibility,
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "inputs": {
            "degree": degree,
            "h_nm": float(h_nm),
            "mpi_size": mpi_size,
            "polarization_kind": str(polarization_kind).lower(),
            "incident_grazing_deg": float(incident_grazing_deg),
            "incident_phi_deg": float(incident_phi_deg),
            "grating_height_nm": float(grating_height_nm),
            "grating_width_x_nm": float(grating_width_x_nm),
            "mesh_axis_cell_counts": list(mesh_axis_cell_counts),
            "assembly_backend": assembly_backend,
        },
        "checks": checks,
        "failures": failures,
    }
