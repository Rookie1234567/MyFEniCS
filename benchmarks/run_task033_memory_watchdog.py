from __future__ import annotations

import argparse
from collections.abc import Mapping
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
)
from benchmarks.run_task031_memory_forensics import _sampler_summary
from benchmarks.run_task033_qep_matrix import _resource_environment_snapshot
from benchmarks.task033_qep_measurement import task033_left_candidate_pool_size
from benchmarks.task033_qep_qualification import (
    resource_authority_gate,
    source_identity_gate,
)
from benchmarks.task034_wsl_resources import (
    effective_memory_limit,
    resource_authority_sample,
)
from benchmarks.task034_workstation_resource_gates import (
    task034_adaptive_mechanism_evidence_gate,
    task034_workstation_hybrid_launch_gate,
)
from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MODE_COUNTS,
    TASK035C_P6_H10_MPI_SIZES,
    task035c_p6_h10_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
    task037b_h1_pinned_full3d_reference_gate,
    valid_hex_digest,
)
from benchmarks.task033_watchdog_launch import (
    DEFAULT_RESOURCE_MATRIX,
    high_order_core_evidence_gate,
    hybrid_launch_gate,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "091"
REDUCED_EQUAL_ACCURACY_RESOURCE_MATRIX = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "stage5_equal_accuracy"
    / "resource_matrix.json"
)
TASK034_WORKSTATION_RESOURCE_AUTHORITY = (
    ROOT
    / "benchmarks"
    / "cases"
    / "092_workstation_wsl_adaptive_scalability"
    / "records"
    / "workstation_hybrid_launch_authority.json"
)

CASE090_CORE_COMPATIBLE_DESCENDANT_FILES = frozenset(
    {
        "README.md",
        "benchmarks/cases/090_high_order_3d_floquet_hcurl/README.md",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/README.md",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage1_high_order/stage_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage2_matched_trace/phaseB_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage2_matched_trace/p4_four_mode_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/full3d_reference.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/full3d_closure_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/phaseC1_full3d_assembly_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/phaseC_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage4_p4_h5/calibration_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/full3d_reference_p3_h10.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/full3d_reference_p3_h7p5.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/resource_matrix.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/resource_matrix.csv",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/source_compatibility_audit.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "variable_p_capability_audit.json",
        "benchmarks/cases/README.md",
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/run_task033_matched_trace.py",
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/run_task033_phaseC.py",
        "benchmarks/run_task033_resource_matrix.py",
        "benchmarks/run_task033_source_compatibility.py",
        "benchmarks/run_task034_wsl_qualification.py",
        "benchmarks/task034_p3_h3_reranking.py",
        "benchmarks/task034_mpi_identity.py",
        "benchmarks/task034_numerical_blob_checker.py",
        "benchmarks/task033_resource_gates.py",
        "benchmarks/task033_matched_trace_qualification.py",
        "benchmarks/task033_phaseC.py",
        "benchmarks/task033_qep_qualification.py",
        "benchmarks/task033_source_compatibility.py",
        "benchmarks/task033_watchdog_launch.py",
        "benchmarks/task034_workstation_resource_gates.py",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/expected.json",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/README.md",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
        "workstation_hybrid_launch_authority.json",
        # Phase B changed only the Hybrid 3D/2D interface trace projection.
        # It is numerical source for Hybrid, but it is component-disjoint from
        # the already accepted pure-3D Case090 Floquet core.  Phase C creates
        # fresh target Hybrid evidence at the new SHA; this exception reuses
        # Case090 only as the high-order Floquet launch prerequisite.
        "src/coupling/modal_trace_projection.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
    }
)

CASE090_COMPONENT_DISJOINT_NUMERICAL_FILES = frozenset(
    {
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/task034_mpi_identity.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/coupling/modal_trace_projection.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
    }
)

TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES = frozenset(
    {
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/task034_mpi_identity.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
        "src/geometry/task034_adaptive_mesh.py",
        "benchmarks/run_task034_adaptive_mechanism.py",
        "benchmarks/task034_case093.py",
        "benchmarks/cases/README.md",
    }
)
TASK034_AUTHORITY_COMPATIBLE_CHANGED_FILES = frozenset(
    {
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/run_task034_wsl_qualification.py",
        "benchmarks/task034_numerical_blob_checker.py",
        "benchmarks/task034_workstation_resource_gates.py",
        *TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES,
    }
)
TASK035B_STATIC_HYBRID_RESOURCE_COMPATIBLE_FILES = frozenset(
    {
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/run_task033_memory_watchdog.py",
        "src/coupling/hybrid_internal_modes.py",
        "src/postprocessing/hybrid_field_reconstruction.py",
        "src/solvers/hybrid_fem_modal_augmented_direct.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
        "src/solvers/hybrid_local_dtn.py",
        "src/solvers/hybrid_local_static_condensation.py",
        "src/solvers/hybrid_static_field_recovery.py",
    }
)
TASK035B_STATIC_FULL3D_ANCHOR_COMPATIBLE_FILES = frozenset(
    {
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/task034_workstation_resource_gates.py",
    }
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _case090_source_compatibility(
    evidence: Mapping[str, Any] | None,
    *,
    current_source_sha: str | None,
) -> dict[str, Any]:
    """Audit whether Case090 may be reused by a core-compatible descendant.

    The legacy ``numerical_source_unchanged`` field is retained for consumers
    of the accepted Phase A record.  Its precise scope is the pure-3D Case090
    Floquet core, not every numerical component in the repository.
    """

    payload = evidence if isinstance(evidence, Mapping) else {}
    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    evidence_source_sha = identity.get("source_commit_full_sha")
    if not (
        isinstance(evidence_source_sha, str)
        and len(evidence_source_sha) == 40
        and isinstance(current_source_sha, str)
        and len(current_source_sha) == 40
    ):
        return {
            "pass": False,
            "evidence_source_sha": evidence_source_sha,
            "current_source_sha": current_source_sha,
            "numerical_source_unchanged": False,
            "case090_core_source_unchanged": False,
            "compatibility_scope": "case090_pure3d_floquet_core",
            "changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "disallowed_changed_paths": [],
            "failures": ["source_sha_missing_or_invalid"],
        }
    if evidence_source_sha == current_source_sha:
        return {
            "pass": True,
            "evidence_source_sha": evidence_source_sha,
            "current_source_sha": current_source_sha,
            "numerical_source_unchanged": True,
            "case090_core_source_unchanged": True,
            "compatibility_scope": "case090_pure3d_floquet_core",
            "changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "disallowed_changed_paths": [],
            "failures": [],
        }
    merge_base = _git("merge-base", evidence_source_sha, current_source_sha)
    rendered_paths = _git(
        "diff", "--name-only", f"{evidence_source_sha}..{current_source_sha}"
    )
    changed_paths = [] if rendered_paths is None else rendered_paths.splitlines()

    def allowed(path: str) -> bool:
        return bool(
            path in CASE090_CORE_COMPATIBLE_DESCENDANT_FILES
            or path.startswith(
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
            )
            or path.startswith("docs/")
            or path.startswith("notes/")
            or path.startswith("src/test/")
        )

    disallowed = [path for path in changed_paths if not allowed(path)]
    component_disjoint = [
        path
        for path in changed_paths
        if path in CASE090_COMPONENT_DISJOINT_NUMERICAL_FILES
    ]
    failures = []
    if merge_base != evidence_source_sha:
        failures.append("case090_source_is_not_ancestor_of_current_source")
    if rendered_paths is None:
        failures.append("case090_source_diff_unreadable")
    if disallowed:
        failures.append("numerical_or_unapproved_source_changed_since_case090")
    return {
        "pass": not failures,
        "evidence_source_sha": evidence_source_sha,
        "current_source_sha": current_source_sha,
        "case090_source_is_ancestor": merge_base == evidence_source_sha,
        "compatibility_scope": "case090_pure3d_floquet_core",
        "case090_core_source_unchanged": (
            not disallowed and rendered_paths is not None
        ),
        # Historical compatibility key; see the function docstring.
        "numerical_source_unchanged": not disallowed and rendered_paths is not None,
        "changed_paths": changed_paths,
        "component_disjoint_numerical_changed_paths": component_disjoint,
        "disallowed_changed_paths": disallowed,
        "failures": failures,
    }


def _task034_authority_source_compatibility(
    authority: Mapping[str, Any] | None,
    *,
    degree: int,
    h_nm: float,
    polarization_kind: str = "s",
    current_source_sha: str | None,
    assembly_backend: str = "standard_full",
) -> dict[str, Any]:
    """Audit a Case092 measured authority against the current clean source."""

    payload = authority if isinstance(authority, Mapping) else {}
    entries = payload.get("entries")
    entries = entries if isinstance(entries, list) else []
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping)
        and item.get("degree") == degree
        and math.isclose(float(item.get("h_nm", math.nan)), float(h_nm))
        and item.get("polarization_kind") == polarization_kind
    ]
    reference = matches[0].get("full3d_reference", {}) if len(matches) == 1 else {}
    reference = reference if isinstance(reference, Mapping) else {}
    if not reference and len(matches) == 1:
        reference = matches[0].get("assembly_resource_anchor", {})
        reference = reference if isinstance(reference, Mapping) else {}
    reference_source_sha = reference.get("source_sha")
    if not (
        isinstance(reference_source_sha, str)
        and len(reference_source_sha) == 40
        and isinstance(current_source_sha, str)
        and len(current_source_sha) == 40
    ):
        return {
            "pass": False,
            "reference_source_sha": reference_source_sha,
            "current_source_sha": current_source_sha,
            "changed_paths": [],
            "disallowed_changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "failures": ["source_sha_missing_or_invalid"],
        }
    if reference_source_sha == current_source_sha:
        return {
            "pass": True,
            "reference_source_sha": reference_source_sha,
            "current_source_sha": current_source_sha,
            "reference_source_is_ancestor": True,
            "changed_paths": [],
            "disallowed_changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "failures": [],
        }
    merge_base = _git("merge-base", reference_source_sha, current_source_sha)
    rendered_paths = _git(
        "diff", "--name-only", f"{reference_source_sha}..{current_source_sha}"
    )
    changed_paths = [] if rendered_paths is None else rendered_paths.splitlines()

    def allowed(path: str) -> bool:
        return bool(
            path in TASK034_AUTHORITY_COMPATIBLE_CHANGED_FILES
            or (
                assembly_backend == "assembly_time_static_condensed"
                and path in TASK035B_STATIC_HYBRID_RESOURCE_COMPATIBLE_FILES
            )
            or path.startswith(
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
            )
            or path.startswith(
                "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/"
            )
            or path.startswith("docs/")
            or path.startswith("notes/")
            or path.startswith("src/test/")
        )

    disallowed = [path for path in changed_paths if not allowed(path)]
    component_disjoint = [
        path
        for path in changed_paths
        if path in TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES
    ]
    static_resource_compatible = [
        path
        for path in changed_paths
        if (
            assembly_backend == "assembly_time_static_condensed"
            and path in TASK035B_STATIC_HYBRID_RESOURCE_COMPATIBLE_FILES
        )
    ]
    failures = []
    if merge_base != reference_source_sha:
        failures.append("reference_source_is_not_ancestor_of_current_source")
    if rendered_paths is None:
        failures.append("reference_source_diff_unreadable")
    if disallowed:
        failures.append("numerical_or_unapproved_source_changed_since_reference")
    return {
        "pass": not failures,
        "reference_source_sha": reference_source_sha,
        "current_source_sha": current_source_sha,
        "reference_source_is_ancestor": merge_base == reference_source_sha,
        "changed_paths": changed_paths,
        "disallowed_changed_paths": disallowed,
        "component_disjoint_numerical_changed_paths": component_disjoint,
        "static_hybrid_resource_compatible_changed_paths": (static_resource_compatible),
        "assembly_backend": assembly_backend,
        "failures": failures,
    }


def _valid_hex_digest(value: object, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _task035b_static_full3d_anchor_gate(
    record: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    degree: int,
    h_nm: float,
    mpi_size: int,
    polarization_kind: str,
    current_source_sha: str | None,
) -> dict[str, Any]:
    """Qualify a fresh same-p/h static Full3D resource anchor.

    Case092 remains the tracked workstation limit and prediction authority.
    The opt-in static Hybrid route binds its measured matrix and memory identity
    to this fresh watchdog record instead of the historical standard matrix.
    """

    payload = record if isinstance(record, Mapping) else {}
    source = payload.get("source")
    source = source if isinstance(source, Mapping) else {}
    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    qualification_checks = qualification.get("checks")
    qualification_checks = (
        qualification_checks if isinstance(qualification_checks, Mapping) else {}
    )
    calibration = payload.get("calibration")
    calibration = calibration if isinstance(calibration, Mapping) else {}
    summary = payload.get("solver_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    config = summary.get("config")
    config = config if isinstance(config, Mapping) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    factor_inventory = summary.get("stage4_dtn_factor_inventory")
    factor_inventory = factor_inventory if isinstance(factor_inventory, Mapping) else {}
    factor_matrix = factor_inventory.get("matrix_stats")
    factor_matrix = factor_matrix if isinstance(factor_matrix, Mapping) else {}
    condensation = summary.get("cell_static_condensation")
    condensation = condensation if isinstance(condensation, Mapping) else {}
    recovery = condensation.get("recovery")
    recovery = recovery if isinstance(recovery, Mapping) else {}
    residual = condensation.get("full_explicit_true_residual")
    residual = residual if isinstance(residual, Mapping) else {}
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}

    reference_source_sha = source.get("commit_sha")
    source_sha_valid = bool(
        _valid_hex_digest(reference_source_sha, 40)
        and _valid_hex_digest(current_source_sha, 40)
    )
    if source_sha_valid and reference_source_sha == current_source_sha:
        merge_base = reference_source_sha
        changed_paths: list[str] = []
        rendered_paths: str | None = ""
    elif source_sha_valid:
        merge_base = _git(
            "merge-base", str(reference_source_sha), str(current_source_sha)
        )
        rendered_paths = _git(
            "diff",
            "--name-only",
            f"{reference_source_sha}..{current_source_sha}",
        )
        changed_paths = [] if rendered_paths is None else rendered_paths.splitlines()
    else:
        merge_base = None
        rendered_paths = None
        changed_paths = []
    disallowed_changed_paths = [
        path
        for path in changed_paths
        if not (
            path in TASK035B_STATIC_FULL3D_ANCHOR_COMPATIBLE_FILES
            or path.startswith("docs/")
            or path.startswith("src/test/")
        )
    ]
    source_compatibility_checks = {
        "source_sha_valid": source_sha_valid,
        "reference_source_is_ancestor": bool(
            source_sha_valid and merge_base == reference_source_sha
        ),
        "source_diff_readable": rendered_paths is not None,
        "only_resource_contract_or_non_numerical_changes": not (
            disallowed_changed_paths
        ),
    }
    source_compatibility_failures = [
        name for name, passed in source_compatibility_checks.items() if not passed
    ]
    source_compatibility = {
        "pass": not source_compatibility_failures,
        "reference_source_sha": reference_source_sha,
        "current_source_sha": current_source_sha,
        "reference_source_is_ancestor": bool(
            source_sha_valid and merge_base == reference_source_sha
        ),
        "changed_paths": changed_paths,
        "disallowed_changed_paths": disallowed_changed_paths,
        "checks": source_compatibility_checks,
        "failures": source_compatibility_failures,
    }

    relative_residual = residual.get("linear_system_relative_residual")
    interior_residual = residual.get("eliminated_cell_interior_max_abs_residual")
    rows = matrix.get("matrix_rows")
    assembled_nnz = matrix.get("matrix_nnz_used")
    factor_nnz = factor_matrix.get("matrix_nnz_used")
    peak_memory_gib = resource.get("memory_authority_gib")
    elapsed_seconds = summary.get("elapsed_seconds")
    reference_planes = config.get("full3d_reference_plane_z")
    reference_planes = reference_planes if isinstance(reference_planes, list) else []
    checks = {
        "object_present": bool(payload),
        "schema_identity": bool(
            payload.get("schema_version") == "task033.full3d-watchdog.v1"
            and payload.get("benchmark_id") == "task033_target_full3d_watchdog"
        ),
        "record_hash_expected_valid": _valid_hex_digest(expected_sha256, 64),
        "record_hash_observed_valid": _valid_hex_digest(observed_sha256, 64),
        "record_hash_matches_expected": bool(expected_sha256 == observed_sha256),
        "same_discretization_identity": bool(
            payload.get("degree") == degree
            and math.isclose(float(payload.get("h_nm", math.nan)), float(h_nm))
            and payload.get("mpi_size") == mpi_size
            and payload.get("polarization_kind") == polarization_kind
            and config.get("nedelec_degree") == degree
            and math.isclose(
                float(config.get("mesh_target_size", math.nan)), float(h_nm)
            )
        ),
        "fixed_task034_physics_identity": bool(
            summary.get("stage_case") == "stage4_block_grating"
            and summary.get("geometry_kind") == "rectangular_block_grating"
            and math.isclose(float(config.get("lambda0", math.nan)), 13.5)
            and math.isclose(float(config.get("incident_theta_deg", math.nan)), 80.0)
            and math.isclose(float(config.get("incident_phi_deg", math.nan)), 0.0)
            and math.isclose(float(config.get("period_x", math.nan)), 50.0)
            and math.isclose(float(config.get("period_y", math.nan)), 25.0)
            and math.isclose(float(config.get("z_min", math.nan)), -10.0)
            and math.isclose(float(config.get("z_max", math.nan)), 130.0)
            and math.isclose(float(config.get("grating_height", math.nan)), 120.0)
            and math.isclose(float(config.get("grating_width_x", math.nan)), 17.0)
            and math.isclose(float(config.get("grating_width_y", math.nan)), 25.0)
            and config.get("n_substrate") == [0.999002304859, 0.00182649365]
            and config.get("n_grating") == [0.999002304859, 0.00182649365]
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("scattering_background") == "layered"
        ),
        "full_solve_pass": bool(
            payload.get("run_kind") == "full-solve"
            and payload.get("status") == "full3d_reference_pass"
            and payload.get("return_code") == 0
            and qualification.get("pass") is True
            and qualification.get("failures") == []
        ),
        "qualification_checks_complete": bool(
            qualification_checks.get("process_completed") is True
            and qualification_checks.get("live_authority_readable") is True
            and qualification_checks.get("all_expected_mpi_ranks_observed") is True
            and qualification_checks.get("official_result") is True
            and qualification_checks.get("ksp_converged") is True
            and qualification_checks.get("true_residual_le_1e-9") is True
            and qualification_checks.get("reference_exported") is True
            and qualification_checks.get("swap_policy_satisfied") is True
            and qualification_checks.get("source_stable_and_clean_after") is True
        ),
        "static_backend_identity": bool(
            payload.get("stage4_full3d_assembly_backend_requested")
            == "assembly_time_static_condensed"
            and payload.get("stage4_full3d_assembly_backend_actual")
            == "assembly_time_static_condensed"
            and summary.get("stage4_full3d_assembly_backend_actual")
            == "assembly_time_static_condensed"
            and condensation.get("ordinary_default_changed") is False
        ),
        "official_result_and_reference_export": bool(
            summary.get("official_result") is True
            and summary.get("case_status") == "completed"
            and config.get("full3d_reference_export") is True
            and any(math.isclose(float(value), 10.0) for value in reference_planes)
            and any(math.isclose(float(value), 110.0) for value in reference_planes)
        ),
        "raw_artifact_hashes_present": bool(
            _valid_hex_digest(payload.get("solver_summary_sha256"), 64)
            and _valid_hex_digest(payload.get("progress_sha256"), 64)
            and _valid_hex_digest(payload.get("timeline_sha256"), 64)
        ),
        "source_record_clean_and_stable": bool(
            source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
            and source.get("commit_sha") == source.get("verified_clean_sha")
            and source.get("head_after_sha") == source.get("commit_sha")
        ),
        "source_compatible_with_current": source_compatibility["pass"],
        "no_swap": payload.get("no_swap") is True,
        "not_resource_terminated": bool(
            payload.get("terminated_for_memory") is False
            and payload.get("terminated_for_timeout") is False
            and payload.get("terminated_for_authority_unreadable") is False
        ),
        "exact_positive_rows": bool(
            type(rows) is int and rows > 0 and calibration.get("exact_rows") == rows
        ),
        "exact_positive_assembled_nnz": bool(
            isinstance(assembled_nnz, (int, float))
            and assembled_nnz > 0
            and calibration.get("exact_assembled_nnz") == assembled_nnz
        ),
        "factor_inventory_positive": bool(
            factor_inventory.get("available") is True
            and isinstance(factor_nnz, (int, float))
            and factor_nnz > 0
        ),
        "peak_memory_positive": bool(
            isinstance(peak_memory_gib, (int, float))
            and math.isfinite(float(peak_memory_gib))
            and peak_memory_gib > 0
        ),
        "full_explicit_true_residual": bool(
            isinstance(relative_residual, (int, float))
            and math.isfinite(float(relative_residual))
            and 0.0 <= relative_residual <= 1.0e-9
            and isinstance(interior_residual, (int, float))
            and math.isfinite(float(interior_residual))
            and 0.0 <= interior_residual <= 1.0e-9
            and residual.get("full_global_matrix_allocated_for_residual") is False
            and residual.get("full_trace_matrix_allocated_for_residual") is False
        ),
        "physical_row_reduction_and_recovery": bool(
            condensation.get("full_global_matrix_allocated") is False
            and condensation.get("full_trace_matrix_allocated") is False
            and condensation.get("inactive_max_p_rows_retained_in_matrix") is False
            and recovery.get("status")
            == "full_field_recovered_without_full_global_matrix"
            and recovery.get("full_global_matrix_allocated") is False
            and recovery.get("full_trace_matrix_allocated") is False
        ),
        "elapsed_seconds_positive": bool(
            isinstance(elapsed_seconds, (int, float))
            and math.isfinite(float(elapsed_seconds))
            and elapsed_seconds > 0
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    anchor = {
        "role": "task035b_fresh_static_full3d_resource_anchor",
        "source_sha": reference_source_sha,
        "watchdog_record_sha256": observed_sha256,
        "descriptor_sha256": expected_sha256,
        "reference_input_kind": "fresh_static_full3d_watchdog_record",
        "status": payload.get("status"),
        "qualification_pass": qualification.get("pass"),
        "no_swap": payload.get("no_swap"),
        "peak_memory_gib": peak_memory_gib,
        "true_relative_residual": relative_residual,
        "exact_rows": rows,
        "exact_assembled_nnz": assembled_nnz,
        "factor_nnz": factor_nnz,
        "elapsed_seconds": elapsed_seconds,
        "degree": payload.get("degree"),
        "h_nm": payload.get("h_nm"),
        "mpi_size": payload.get("mpi_size"),
        "polarization_kind": payload.get("polarization_kind"),
        "assembly_backend": payload.get("stage4_full3d_assembly_backend_actual"),
    }
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "anchor": anchor,
        "source_compatibility": source_compatibility,
    }


def _watchdog_source_before(verified_clean_sha: str) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    worktree = _git("status", "--short", "--untracked-files=all")
    untracked = [
        line[3:] for line in (worktree or "").splitlines() if line.startswith("?? ")
    ]
    return {
        "commit_sha": head,
        "head_before_sha": head,
        "head_after_sha": None,
        "verified_clean_sha": verified_clean_sha,
        # Retain the historical key consumed by source_identity_gate, but its
        # value now covers tracked changes plus all nonignored untracked paths.
        "tracked_status_before": worktree,
        "tracked_status_after": None,
        "worktree_status_before": worktree,
        "worktree_status_after": None,
        "nonignored_untracked_before": untracked,
        "nonignored_untracked_after": None,
        "cleanliness_semantics": (
            "git status including all nonignored untracked paths; ignored artifacts excluded"
        ),
        "source_stable_during_run": False,
        "source_clean_verified": bool(head == verified_clean_sha and worktree == ""),
    }


def _watchdog_source_after(source: dict[str, Any]) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    worktree = _git("status", "--short", "--untracked-files=all")
    untracked = [
        line[3:] for line in (worktree or "").splitlines() if line.startswith("?? ")
    ]
    updated = {
        **source,
        "head_after_sha": head,
        "tracked_status_after": worktree,
        "worktree_status_after": worktree,
        "nonignored_untracked_after": untracked,
    }
    updated["source_stable_during_run"] = bool(
        source.get("head_before_sha") == head
        and source.get("tracked_status_before") == ""
        and worktree == ""
    )
    updated["source_clean_verified"] = source_identity_gate(updated)["pass"]
    return updated


def _environment_preflight(snapshot: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "cgroup_current_readable": snapshot.get("memory_current_bytes") is not None,
        "container_limit_readable": snapshot.get("memory_limit_bytes") is not None,
        "host_available_readable": (
            snapshot.get("host_available_memory_bytes") is not None
        ),
        "container_current_swap_zero": snapshot.get("swap_current_bytes") == 0,
        "pswpin_readable": snapshot.get("pswpin_pages") is not None,
        "pswpout_readable": snapshot.get("pswpout_pages") is not None,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _worker_command(
    args: argparse.Namespace,
    record_path: Path,
    stage_path: Path,
) -> list[str]:
    if args.target == "qep":
        # ``run`` installs the live effective limit after reading cgroup and
        # host authorities.  Keep the pure command helper usable by contract
        # tests and tooling without ever spelling a bogus ``None`` limit.
        effective_limit_gib = getattr(args, "_qep_effective_limit_gib", None)
        command = [
            "mpiexec",
            "-n",
            str(args.mpi_size),
            sys.executable,
            "-m",
            "benchmarks.run_task033_qep_matrix",
            "--execute",
            "--degree",
            str(args.degree),
            "--h-nm",
            str(args.h_nm),
            "--material-kind",
            args.material_kind,
            "--requested-modes",
            str(args.requested_modes),
            "--left-candidate-modes",
            str(args.candidate_modes),
            "--verified-clean-sha",
            args.verified_clean_sha,
            "--watchdog-enabled-verified",
            "--one-large-case-verified",
            "--output",
            str(record_path),
            "--container-image",
            args.container_image,
            "--container-digest",
            args.container_digest,
            "--host-environment-id",
            args.host_environment_id,
        ]
        if effective_limit_gib is not None:
            command.extend(("--container-limit-gib", str(effective_limit_gib)))
        if getattr(args, "_no_swap_verified", True):
            command.append("--no-swap-verified")
        if args.high_order_core_evidence_sha256 is not None:
            command.extend(
                (
                    "--high-order-core-evidence-sha256",
                    args.high_order_core_evidence_sha256,
                )
            )
        return command

    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task032_phase6_augmented",
        "--degree",
        str(args.degree),
        "--h-nm",
        str(args.h_nm),
        "--bottom-interface-nm",
        str(args.bottom_interface_nm),
        "--top-interface-nm",
        str(args.top_interface_nm),
        "--incident-grazing-deg",
        str(args.incident_grazing_deg),
        "--polarization-kind",
        args.polarization_kind,
        "--requested-modes",
        str(args.requested_modes),
        "--candidate-modes",
        str(args.candidate_modes),
        "--solver-path",
        args.solver_path,
        "--stage4-full3d-assembly-backend",
        args.stage4_full3d_assembly_backend,
        "--comparison-solver-path",
        args.comparison_solver_path,
        "--verified-clean-sha",
        args.verified_clean_sha,
        "--output",
        str(record_path),
        "--memory-stages",
        str(stage_path),
        "--container-image",
        args.container_image,
        "--container-digest",
        args.container_digest,
        "--host-environment-id",
        args.host_environment_id,
    ]
    if args.modal_h_nm is not None:
        command.extend(("--modal-h-nm", str(args.modal_h_nm)))
    if args.modal_degree is not None:
        command.extend(("--modal-degree", str(args.modal_degree)))
    if args.internal_propagation_model != "continuous_beta":
        command.extend(
            (
                "--internal-propagation-model",
                args.internal_propagation_model,
            )
        )
    if args.internal_traction_model != "continuous_qep_beta":
        command.extend(
            (
                "--internal-traction-model",
                args.internal_traction_model,
            )
        )
    if args.full3d_reference is not None:
        command.extend(("--full3d-reference", str(args.full3d_reference)))
    if (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ):
        command.extend(
            (
                "--full3d-reference-sha256",
                str(args.full3d_reference_sha256),
                (
                    "--task035c-p6-h10-gate"
                    if args.task035c_p6_h10_gate
                    else (
                        "--task037b-h1-gate"
                        if args.task037b_h1_gate
                        else (
                            "--task037b-h3-gate"
                            if args.task037b_h3_gate
                            else (
                                "--task037b-h4-gate"
                                if args.task037b_h4_gate
                                else (
                                    "--task037b-h5-gate"
                                    if args.task037b_h5_gate
                                    else (
                                        "--task037b-v4-gate"
                                        if args.task037b_v4_gate
                                        else (
                                            "--task037b-v3-gate"
                                            if args.task037b_v3_gate
                                            else "--task037b-v2-gate"
                                            if args.task037b_v2_gate
                                            else "--task037b-v1-gate"
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
                "--task035c-p6-preflight-authority",
                str(args.task035c_p6_preflight_authority),
                "--task035c-p6-preflight-sha256",
                str(args.task035c_p6_preflight_sha256),
            )
        )
    if args.task037b_v2_gate:
        command.extend(
            (
                "--task037b-v2-profile",
                str(args.task037b_v2_profile),
                "--task037b-v2-max-it",
                str(args.task037b_v2_max_it),
            )
        )
    if args.compare_modal_schur:
        command.append("--compare-modal-schur")
    if args.graded_reference_h is not None:
        command.extend(
            (
                "--graded-reference-h",
                str(args.graded_reference_h),
                "--graded-coarse-factor",
                str(args.graded_coarse_factor),
                "--graded-profile",
                args.graded_profile,
            )
        )
    return command


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "path_not_supplied"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, "json_root_is_not_an_object"
    return payload, None


def _task034_terminal_record_is_complete(record_path: Path) -> bool:
    payload, error = _read_json_object(record_path)
    if error is not None or payload is None:
        return False
    v1_record = payload.get(
        "record_schema"
    ) == "task037b.v1-r1-dtn-component-action.v1" and isinstance(
        payload.get("v1_telemetry"), dict
    )
    v1_r2_record = payload.get(
        "record_schema"
    ) == "task037b.v1-r2-f-only-local-inverse.v1" and isinstance(
        payload.get("v1_r2_telemetry"), dict
    )
    v1_r3_record = payload.get(
        "record_schema"
    ) == "task037b.v1-r3-whole-endcap-ilu0.v1" and isinstance(
        payload.get("v1_r3_telemetry"), dict
    )
    v1_r4_record = payload.get(
        "record_schema"
    ) == "task037b.v1-r4-dtn-woodbury.v1" and isinstance(
        payload.get("v1_r4_telemetry"), dict
    )
    v1_r5_record = payload.get(
        "record_schema"
    ) == "task037b.v1-r5-dtn-woodbury-local-inverse.v1" and isinstance(
        payload.get("v1_r5_telemetry"), dict
    )
    v2_record = payload.get(
        "record_schema"
    ) == "task037b.v2-block-pc-screen.v1" and isinstance(
        payload.get("v2_telemetry"), dict
    )
    v3_record = payload.get(
        "record_schema"
    ) == "task037b.v3-progressive-block-pc-screen.v1" and isinstance(
        payload.get("v3_telemetry"), dict
    )
    v4_record = payload.get(
        "record_schema"
    ) == "task037b.v4-full-block-pc.v1" and isinstance(
        payload.get("v4_telemetry"), dict
    )
    return bool(
        payload.get("schema_version") == 1
        and isinstance(payload.get("benchmark_id"), str)
        and isinstance(payload.get("timestamp_utc"), str)
        and isinstance(payload.get("status"), str)
        and isinstance(payload.get("qualification"), dict)
        and (
            isinstance(payload.get("solve"), dict)
            or v1_record
            or v1_r2_record
            or v1_r3_record
            or v1_r4_record
            or v1_r5_record
            or v2_record
            or v3_record
            or v4_record
        )
        and isinstance(payload.get("gates"), dict)
    )


def _task034_terminal_worker_drain(
    *,
    task034_workstation_gate: bool,
    process_running: bool,
    authority_readable: bool,
    stage: str | None,
    terminal_record_complete: bool,
    live_worker_count: int | None,
    terminal_stage: str = "record_and_release",
) -> bool:
    """Recognize only the normal worker-before-launcher MPI exit window."""

    return bool(
        task034_workstation_gate
        and process_running
        and not authority_readable
        and stage == terminal_stage
        and terminal_record_complete
        and live_worker_count == 0
    )


def _resource_readability_sample_is_formal(
    *,
    task034_workstation_gate: bool,
    process_running: bool,
    terminal_worker_drain: bool = False,
) -> bool:
    """Exclude only Task034 samples observed during or after terminal drain.

    A process-tree read racing with ``Popen.poll`` may contain a disappearing
    worker or launcher PID and report ``all_status_readable=False``. Once the
    complete terminal worker record exists and no worker remains, it is not a
    live authority sample. Task033's historical default semantics remain
    unchanged.
    """

    return bool(
        (process_running and not terminal_worker_drain) or not task034_workstation_gate
    )


def _authority_unreadable_requires_termination(
    *,
    process_running: bool,
    readability_sample_is_formal: bool,
    authority_readable: bool,
) -> bool:
    """Terminate only when a formal live authority sample is unreadable."""

    return bool(
        process_running and readability_sample_is_formal and not authority_readable
    )


def _live_task033_worker_rss(
    root_pid: int, target: str
) -> tuple[float | None, list[dict[str, Any]]]:
    """Read the live RSS sum of this watchdog's MPI Python workers.

    The shared legacy sampler does not classify the Task033 QEP module as a
    worker.  Scan ``/proc`` here so both QEP and Hybrid use the same authority
    instead of silently treating the QEP worker sum as zero.
    """

    marker = (
        "benchmarks.run_task033_qep_matrix"
        if target == "qep"
        else "benchmarks.run_task032_phase6_augmented"
    )
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return None, []
    workers: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == root_pid:
            continue
        try:
            cmdline = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="ignore")
            )
            if marker not in cmdline or "mpiexec" in cmdline.lower():
                continue
            rss_kib = None
            for line in (
                (entry / "status")
                .read_text(encoding="utf-8", errors="ignore")
                .splitlines()
            ):
                if line.startswith("VmRSS:"):
                    rss_kib = float(line.split()[1])
                    break
            if rss_kib is None:
                continue
            workers.append(
                {
                    "pid": int(entry.name),
                    "rss_mb": rss_kib / 1024.0,
                }
            )
        except (OSError, ValueError, IndexError):
            continue
    return sum(item["rss_mb"] for item in workers), workers


def _hybrid_measurements(record: dict[str, Any]) -> dict[str, Any]:
    physical = record.get("physical_field_reconstruction") or {}
    validation = record.get("validation") or {}
    return {
        "h1_telemetry": record.get("h1_telemetry"),
        "h3_telemetry": record.get("h3_telemetry"),
        "h4_telemetry": record.get("h4_telemetry"),
        "h5_telemetry": record.get("h5_telemetry"),
        "v1_telemetry": record.get("v1_telemetry"),
        "v1_r2_telemetry": record.get("v1_r2_telemetry"),
        "v1_r3_telemetry": record.get("v1_r3_telemetry"),
        "v1_r4_telemetry": record.get("v1_r4_telemetry"),
        "v1_r5_telemetry": record.get("v1_r5_telemetry"),
        "v2_telemetry": record.get("v2_telemetry"),
        "status": record.get("status"),
        "case": record.get("case"),
        "qep": {
            key: record.get("qep", {}).get(key)
            for key in (
                "full_shape",
                "reduced_shape",
                "field_degree",
                "geometry_degree",
                "coefficient_degree",
                "quadrature_degree",
                "quadrature_policy",
            )
        },
        "hybrid_system": {
            key: record.get("hybrid_system", {}).get(key)
            for key in (
                "primary_solver_path",
                "operator_inventory",
                "matrix_size",
                "matrix_stats",
                "block_shapes",
                "inserted_nnz_by_block",
                "bottom_matrix_stats",
                "top_matrix_stats",
                "bottom_global_size",
                "top_global_size",
                "bottom_local_fe_dofs",
                "top_local_fe_dofs",
                "bottom_local_mesh_cells",
                "top_local_mesh_cells",
                "bottom_local_thickness_nm",
                "top_local_thickness_nm",
                "internal_unknown_count",
                "internal_propagation",
                "qep_to_interface_quadrature_degree",
                "dense_interface_square_formed",
                "full_field_or_mode_gathered",
                "modal_schur",
            )
        },
        "solve": record.get("solve"),
        "validation": {
            "port_power": validation.get("port_power"),
            "interface_e_projection": validation.get("interface_e_projection"),
            "fe_modal_traction_equilibrium": validation.get(
                "fe_modal_traction_equilibrium"
            ),
            "external_diffraction_orders": validation.get(
                "external_diffraction_orders"
            ),
        },
        "physical_field_reconstruction": {
            "interface_continuity": physical.get("interface_continuity"),
            "full3d_trace_modal_oracle": physical.get("full3d_trace_modal_oracle"),
            "volume_absorption": physical.get("volume_absorption"),
            "selected_plane_full3d_comparison": physical.get(
                "selected_plane_full3d_comparison"
            ),
            "sample_payload_bytes": physical.get("sample_payload_bytes"),
            "sample_grid_shape_z_y_x_component": physical.get(
                "sample_grid_shape_z_y_x_component"
            ),
            "full_middle_volume_reconstructed": physical.get(
                "full_middle_volume_reconstructed"
            ),
        },
        "full3d_reference_comparison": record.get("full3d_reference_comparison"),
        "modal_schur_comparison": record.get("modal_schur_comparison"),
        "modal_basis_capacity": record.get("modal_basis_capacity"),
        "object_payload_ledger": {
            key: (record.get("object_payload_ledger") or {}).get(key)
            for key in (
                "scalar_bytes",
                "index_bytes",
                "interface_active_dofs",
                "mode_count_per_direction",
                "retained_right_left_eigenvector_bytes",
                "projection_matrix",
                "modal_schur_bytes",
                "local_or_augmented_factor_inventory",
                "storage_complexity_contract",
                "dense_interface_square_formed",
            )
        },
        "gates": record.get("gates"),
        "qualification": record.get("qualification"),
        "timing_seconds_max_rank": record.get("timing_seconds_max_rank"),
    }


def _task037b_h5_numerical_pass(record: dict[str, Any]) -> bool:
    """Use only the H5 worker qualification contract for H5 numerical status."""

    qualification = record.get("qualification")
    if not isinstance(qualification, dict):
        return False
    return bool(
        qualification.get("task037b_h5_gate") is True
        and qualification.get("worker_numerical_pass") is True
        and qualification.get("integration_pass") is True
    )


def _task037b_v1_r1_numerical_pass(record: dict[str, Any]) -> bool:
    """Recompute the bounded V1-R1 result from raw component-audit fields."""

    if not isinstance(record, dict):
        return False
    if record.get("schema_version") != 1:
        return False
    if record.get("record_schema") != "task037b.v1-r1-dtn-component-action.v1":
        return False
    if record.get("benchmark_id") != "task037b_v1_dtn_component_action":
        return False
    if record.get("status") != "task037b_v1_r1_pass_awaiting_r2":
        return False
    qualification = record.get("qualification")
    telemetry = record.get("v1_telemetry")
    gates = record.get("gates")
    if not isinstance(qualification, dict) or not isinstance(telemetry, dict):
        return False
    if qualification.get("task037b_v1_gate") is not True:
        return False
    if qualification.get("r1_pass") is not True:
        return False
    if qualification.get("integration_pass") is not True:
        return False
    if telemetry.get("task037b_v1_gate") is not True:
        return False
    if telemetry.get("formal_probe_count_per_side") != 6:
        return False
    if not isinstance(gates, dict) or gates.get("r1_pass") is not True:
        return False
    sides = telemetry.get("sides")
    if not isinstance(sides, dict) or set(sides) != {"bottom", "top"}:
        return False
    hybrid_system = record.get("hybrid_system")
    if not isinstance(hybrid_system, dict):
        return False
    if any(
        (
            hybrid_system.get("global_action_constructed") is not False,
            hybrid_system.get("global_A_materialized") is not False,
            hybrid_system.get("global_F_materialized") is not False,
            hybrid_system.get("explicit_global_C_D_materialized") is not False,
            hybrid_system.get("direct_factor_count") != 0,
        )
    ):
        return False
    required_names = {
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_negative_lowest_propagating_or_lossy",
    }
    for side_name in ("bottom", "top"):
        side = sides.get(side_name)
        if not isinstance(side, dict):
            return False
        if side.get("component_destroyed") is not True:
            return False
        if side.get("action_usable_after_component_destroy") is not True:
            return False
        if side.get("pass") is not True:
            return False
        probes = side.get("probes")
        if not isinstance(probes, list) or len(probes) != 6:
            return False
        if any(not isinstance(probe, dict) for probe in probes):
            return False
        if {probe.get("name") for probe in probes} != required_names:
            return False
        for probe in probes:
            if not isinstance(probe, dict):
                return False
            if probe.get("finite") is not True:
                return False
            if probe.get("pass") is not True:
                return False
            action_error = probe.get("action_relative_error")
            repeat_error = probe.get("component_repeat_relative_error")
            if not isinstance(action_error, (int, float)) or not math.isfinite(
                action_error
            ):
                return False
            if not isinstance(repeat_error, (int, float)) or not math.isfinite(
                repeat_error
            ):
                return False
            if (
                action_error < 0.0
                or repeat_error < 0.0
                or action_error > 1.0e-11
                or repeat_error > 1.0e-12
            ):
                return False
    return True


def _task037b_v1_r2_numerical_pass(
    record: dict[str, Any], *, require_numerical_pass: bool = True
) -> bool:
    """Recompute V1-R2 contract and optionally require all probes to pass."""

    if not isinstance(record, dict):
        return False
    if (
        record.get("schema_version") != 1
        or record.get("record_schema") != "task037b.v1-r2-f-only-local-inverse.v1"
        or record.get("benchmark_id") != "task037b_v1_r2_f_only_local_inverse"
        or record.get("status") != "task037b_v1_r2_complete_awaiting_r3"
    ):
        return False
    qualification = record.get("qualification")
    telemetry = record.get("v1_r2_telemetry")
    gates = record.get("gates")
    if not isinstance(qualification, dict) or not isinstance(telemetry, dict):
        return False
    if (
        qualification.get("task037b_v1_gate") is not True
        or qualification.get("integration_pass") is not True
        or telemetry.get("task037b_v1_gate") is not True
        or telemetry.get("formal_probe_count_per_side") != 11
        or telemetry.get("external_dtn_correction_excluded") is not True
        or not isinstance(gates, dict)
        or gates.get("r2_record_complete") is not True
    ):
        return False
    hybrid_system = record.get("hybrid_system")
    if not isinstance(hybrid_system, dict) or any(
        (
            hybrid_system.get("global_action_constructed") is not False,
            hybrid_system.get("global_A_materialized") is not False,
            hybrid_system.get("global_F_materialized") is not False,
            hybrid_system.get("explicit_global_C_D_materialized") is not False,
            hybrid_system.get("direct_factor_count") != 0,
        )
    ):
        return False
    validation = record.get("validation")
    physical_field_reconstruction = record.get("physical_field_reconstruction")
    if (
        not isinstance(validation, dict)
        or any(
            validation.get(name) != "not_run"
            for name in (
                "port_power",
                "R_total",
                "T_total",
                "A_balance",
                "A_volume_total",
            )
        )
        or not isinstance(physical_field_reconstruction, dict)
        or physical_field_reconstruction.get("status") != "not_run"
    ):
        return False
    base_names = {
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
    }
    modal_names = {
        f"modal_{direction}_{criterion}"
        for direction in ("positive", "negative")
        for criterion in (
            "lowest_propagating_or_lossy",
            "highest_retained_index",
            "first_kind_evanescent",
            "proxy_abs_im_beta_gt_abs_re_beta",
        )
    }
    sides = telemetry.get("sides")
    contracts = telemetry.get("preconditioner")
    if (
        not isinstance(sides, dict)
        or set(sides) != {"bottom", "top"}
        or not isinstance(contracts, dict)
        or set(contracts) != {"bottom", "top"}
    ):
        return False
    all_pass = True
    for side_name in ("bottom", "top"):
        side = sides.get(side_name)
        contract = contracts.get(side_name)
        configuration = (
            contract.get("configuration") if isinstance(contract, dict) else None
        )
        smoother = contract.get("smoother") if isinstance(contract, dict) else None
        factor_fingerprints = (
            smoother.get("factor_fingerprints") if isinstance(smoother, dict) else None
        )
        if (
            not isinstance(side, dict)
            or not isinstance(contract, dict)
            or side.get("operator_identity") != "fine_action_F_only"
            or side.get("external_dtn_correction") != "excluded"
            or side.get("probe_count") != 11
            or type(contract.get("factor_count_before_destroy")) is not int
            or contract.get("factor_count_before_destroy") != 6
            or contract.get("no_direct_fallback") is not True
            or contract.get("factor_count_after_destroy") != 0
            or contract.get("factors_released") is not True
            or not isinstance(configuration, dict)
            or configuration.get("coordinate_axis") != 0
            or configuration.get("num_slabs") != 6
            or configuration.get("overlap_fraction") != 0.125
            or configuration.get("interpolation") != "partition"
            or configuration.get("ilu_levels") != 0
            or configuration.get("factor_only") is not True
            or configuration.get("one_apply_per_pc_apply") is not True
            or configuration.get("two_step_action_operator") is not None
            or configuration.get("outer_solver") != "right_fgmres"
            or configuration.get("restart") != 30
            or configuration.get("max_it") != 300
            or configuration.get("rtol") != 1.0e-10
            or configuration.get("atol") != 0.0
            or configuration.get("true_residual_limit") != 1.0e-8
            or not isinstance(smoother, dict)
            or smoother.get("subdomain_local_diagonal_shift") is not True
            or not isinstance(factor_fingerprints, list)
            or len(factor_fingerprints) != 6
        ):
            return False
        probes = side.get("probes")
        if (
            not isinstance(probes, list)
            or len(probes) != 11
            or not all(isinstance(probe, dict) for probe in probes)
        ):
            return False
        if any(type(probe.get("name")) is not str for probe in probes):
            return False
        names = {probe["name"] for probe in probes}
        expected_names = base_names | {name for name in names if name in modal_names}
        for direction in ("positive", "negative"):
            if not {
                f"modal_{direction}_lowest_propagating_or_lossy",
                f"modal_{direction}_highest_retained_index",
            }.issubset(names):
                return False
            if (
                len(
                    {
                        f"modal_{direction}_first_kind_evanescent",
                        f"modal_{direction}_proxy_abs_im_beta_gt_abs_re_beta",
                    }
                    & names
                )
                != 1
            ):
                return False
        if names != expected_names or len(names) != 11:
            return False
        side_pass = True
        for probe in probes:
            first = probe.get("first")
            second = probe.get("second")
            stationary_keys = {"1", "2", "4", "8"}
            if (
                not isinstance(first, dict)
                or not isinstance(second, dict)
                or first.get("operator_identity") != "fine_action_F_only"
                or second.get("operator_identity") != "fine_action_F_only"
                or first.get("external_dtn_correction") != "excluded"
                or second.get("external_dtn_correction") != "excluded"
                or first.get("explicit_true_residual_recomputed") is not True
                or second.get("explicit_true_residual_recomputed") is not True
                or set(first.get("stationary_correction_residuals", {}))
                != stationary_keys
                or set(second.get("stationary_correction_residuals", {}))
                != stationary_keys
            ):
                return False
            numeric_keys = (
                "reported_residual",
                "f_only_true_residual",
                "setup_seconds",
                "solve_seconds",
                "apply_seconds",
            )
            finite = True
            for result in (first, second):
                if (
                    type(result.get("reason")) is not int
                    or type(result.get("iterations")) is not int
                ):
                    return False
                finite &= all(
                    isinstance(result.get(key), (int, float))
                    and math.isfinite(float(result[key]))
                    for key in numeric_keys
                )
                finite &= all(
                    isinstance(value, (int, float)) and math.isfinite(float(value))
                    for value in result["stationary_correction_residuals"].values()
                )
            repeat_error = probe.get("repeat_solution_relative_error")
            finite &= isinstance(repeat_error, (int, float)) and math.isfinite(
                float(repeat_error)
            )
            finite &= float(repeat_error) >= 0.0
            expected_pass = bool(
                finite
                and first["reason"] > 0
                and second["reason"] > 0
                and first["iterations"] <= 300
                and second["iterations"] <= 300
                and first["f_only_true_residual"] <= 1.0e-8
                and second["f_only_true_residual"] <= 1.0e-8
                and probe.get("repeat_reason_equal") is True
                and probe.get("repeat_iterations_equal") is True
                and float(repeat_error) <= 1.0e-10
            )
            if (
                type(probe.get("finite")) is not bool
                or type(probe.get("pass")) is not bool
                or probe.get("finite") is not finite
                or probe.get("pass") is not expected_pass
                or probe.get("repeat_reason_equal")
                is not (first["reason"] == second["reason"])
                or probe.get("repeat_iterations_equal")
                is not (first["iterations"] == second["iterations"])
            ):
                return False
            side_pass &= expected_pass
        if side.get("pass") is not side_pass:
            return False
        all_pass &= side_pass
    expected_disposition = (
        "pass_awaiting_r3"
        if all_pass
        else "F_ONLY_LOCAL_INVERSE_FAMILY_DIAGNOSTIC_NEGATIVE"
    )
    if (
        gates.get("r2_all_probe_records_complete") is not True
        or gates.get("r2_all_probes_finite")
        is not all(
            probe["finite"] for side in sides.values() for probe in side["probes"]
        )
        or gates.get("r2_no_direct_fallback") is not True
        or gates.get("r2_factors_released") is not True
        or gates.get("r2_pass") is not all_pass
        or qualification.get("r2_pass") is not all_pass
        or qualification.get("worker_numerical_pass") is not all_pass
        or qualification.get("disposition") != expected_disposition
    ):
        return False
    return bool(all_pass if require_numerical_pass else True)


def _task037b_v1_r3_numerical_pass(
    record: dict[str, Any], *, require_numerical_pass: bool = True
) -> bool:
    """Recompute the V1-R3 whole-endcap contract from raw probe fields."""

    if not isinstance(record, dict):
        return False
    if (
        record.get("schema_version") != 1
        or record.get("record_schema") != "task037b.v1-r3-whole-endcap-ilu0.v1"
        or record.get("benchmark_id") != "task037b_v1_r3_whole_endcap_ilu0"
        or record.get("status") != "task037b_v1_r3_complete_awaiting_r4"
    ):
        return False
    telemetry = record.get("v1_r3_telemetry")
    qualification = record.get("qualification")
    gates = record.get("gates")
    if (
        not isinstance(telemetry, dict)
        or not isinstance(qualification, dict)
        or not isinstance(gates, dict)
        or telemetry.get("task037b_v1_gate") is not True
        or telemetry.get("preconditioner_profile") != "v1_whole_endcap_ilu0"
        or telemetry.get("formal_probe_count_per_side") != 11
        or qualification.get("task037b_v1_gate") is not True
        or qualification.get("integration_pass") is not True
    ):
        return False
    hybrid_system = record.get("hybrid_system")
    if (
        not isinstance(hybrid_system, dict)
        or hybrid_system.get("global_action_constructed") is not False
        or hybrid_system.get("global_A_materialized") is not False
        or hybrid_system.get("global_F_materialized") is not False
        or hybrid_system.get("explicit_global_C_D_materialized") is not False
        or hybrid_system.get("direct_factor_count") != 0
    ):
        return False
    validation = record.get("validation")
    physical = record.get("physical_field_reconstruction")
    if (
        not isinstance(validation, dict)
        or any(
            validation.get(name) != "not_run"
            for name in (
                "port_power",
                "R_total",
                "T_total",
                "A_balance",
                "A_volume_total",
            )
        )
        or not isinstance(physical, dict)
        or physical.get("status") != "not_run"
    ):
        return False
    base_names = {
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
    }
    sides = telemetry.get("sides")
    if (
        not isinstance(sides, dict)
        or set(sides) != {"bottom", "top"}
        or telemetry.get("r3_contract_pass") is not True
    ):
        return False
    all_numeric_pass = True
    all_finite = True
    all_contract = True
    expected_identity = {
        "R3-F": ("fine_action_F_only", "excluded"),
        "R3-A": ("complete_hybrid_action", "included"),
    }
    for side in ("bottom", "top"):
        side_record = sides.get(side)
        if not isinstance(side_record, dict) or set(side_record.get("cases", {})) != {
            "R3-F",
            "R3-A",
        }:
            return False
        side_numeric_pass = True
        for case_name, (identity, correction) in expected_identity.items():
            case = side_record["cases"].get(case_name)
            if (
                not isinstance(case, dict)
                or case.get("operator_identity") != identity
                or case.get("external_dtn_correction") != correction
                or case.get("probe_count") != 11
                or not isinstance(case.get("preconditioner"), dict)
                or not isinstance(case.get("probes"), list)
                or len(case["probes"]) != 11
            ):
                return False
            preconditioner = case["preconditioner"]
            configuration = preconditioner.get("configuration")
            fingerprints = preconditioner.get("factor_fingerprints")
            operator = preconditioner.get("operator")
            partition_audit = preconditioner.get("partition_audit")
            owner_partition = preconditioner.get("owner_partition")
            if (
                not isinstance(configuration, dict)
                or configuration.get("preconditioner_profile") != "v1_whole_endcap_ilu0"
                or configuration.get("coordinate_axis") != 0
                or configuration.get("num_slabs") != 1
                or configuration.get("overlap_fraction") != 0.0
                or configuration.get("interpolation") != "partition"
                or configuration.get("ilu_levels") != 0
                or configuration.get("factor_only") is not True
                or configuration.get("one_apply_per_pc_apply") is not True
                or configuration.get("two_step_action_operator") is not None
                or configuration.get("outer_solver") != "right_fgmres"
                or configuration.get("restart") != 30
                or configuration.get("max_it") != 300
                or configuration.get("rtol") != 1.0e-10
                or configuration.get("atol") != 0.0
                or configuration.get("true_residual_limit") != 1.0e-8
                or not isinstance(operator, dict)
                or operator.get("identity") != identity
                or operator.get("external_dtn_correction") != correction
                or preconditioner.get("shift") is not True
                or preconditioner.get("candidate_direct_factor_count") != 0
                or preconditioner.get("no_direct_fallback") is not True
                or preconditioner.get("borrowed_action_survives_after_release")
                is not True
                or preconditioner.get("factor_count_before_destroy") != 1
                or preconditioner.get("factor_count_after_destroy") != 0
                or preconditioner.get("factors_released") is not True
                or not isinstance(fingerprints, list)
                or len(fingerprints) != 1
                or type(preconditioner.get("rows")) is not int
                or preconditioner["rows"] <= 0
                or type(preconditioner.get("source_matrix_nnz")) is not int
                or preconditioner["source_matrix_nnz"] <= 0
                or type(preconditioner.get("factor_nnz")) is not int
                or preconditioner["factor_nnz"] <= 0
                or type(preconditioner.get("factor_csr_payload_estimate_bytes"))
                is not int
                or preconditioner["factor_csr_payload_estimate_bytes"] <= 0
                or not isinstance(partition_audit, dict)
                or not isinstance(owner_partition, dict)
            ):
                return False
            partition_weight_error = partition_audit.get("partition_weight_sum_error")
            owners = owner_partition.get("owners")
            row_counts = owner_partition.get("row_counts")
            intervals = owner_partition.get("intervals")
            if (
                type(partition_weight_error) not in (int, float)
                or not math.isfinite(float(partition_weight_error))
                or float(partition_weight_error) > 1.0e-12
                or not isinstance(owners, list)
                or len(owners) != 1
                or not isinstance(row_counts, list)
                or len(row_counts) != 1
                or type(row_counts[0]) is not int
                or row_counts[0] != preconditioner["rows"]
                or not isinstance(intervals, list)
                or len(intervals) != 1
            ):
                return False
            probes = case["probes"]
            names = {probe.get("name") for probe in probes}
            if any(type(probe.get("name")) is not str for probe in probes):
                return False
            expected_names = set(base_names)
            for direction in ("positive", "negative"):
                expected_names.update(
                    {
                        f"modal_{direction}_lowest_propagating_or_lossy",
                        f"modal_{direction}_highest_retained_index",
                    }
                )
                modal_options = {
                    f"modal_{direction}_first_kind_evanescent",
                    f"modal_{direction}_proxy_abs_im_beta_gt_abs_re_beta",
                }
                selected_options = names & modal_options
                if len(selected_options) != 1:
                    return False
                expected_names.update(selected_options)
            if names != expected_names or len(names) != 11:
                return False
            case_numeric_pass = True
            case_finite = True
            for probe in probes:
                stationary = probe.get("stationary_correction_residuals")
                numeric_values = (
                    probe.get("reported_residual"),
                    probe.get("true_relative_residual"),
                    probe.get("setup_seconds"),
                    probe.get("solve_seconds"),
                    probe.get("apply_seconds"),
                )
                finite = bool(
                    probe.get("explicit_true_residual_recomputed") is True
                    and all(
                        isinstance(value, (int, float)) and math.isfinite(float(value))
                        for value in numeric_values
                    )
                    and isinstance(stationary, dict)
                    and set(stationary) == {"1", "2", "4", "8"}
                    and all(
                        isinstance(value, (int, float)) and math.isfinite(float(value))
                        for value in stationary.values()
                    )
                )
                expected_pass = bool(
                    finite
                    and type(probe.get("reason")) is int
                    and type(probe.get("iterations")) is int
                    and probe["reason"] > 0
                    and probe["iterations"] <= 300
                    and probe["true_relative_residual"] <= 1.0e-8
                )
                if (
                    type(probe.get("finite")) is not bool
                    or type(probe.get("pass")) is not bool
                    or probe.get("finite") is not finite
                    or probe.get("pass") is not expected_pass
                ):
                    return False
                case_finite &= finite
                case_numeric_pass &= expected_pass
            if case.get("all_probes_finite") is not case_finite:
                return False
            if case.get("pass") is not case_numeric_pass:
                return False
            side_numeric_pass &= case_numeric_pass
            all_finite &= case_finite
            all_contract &= bool(
                preconditioner.get("factors_released") is True
                and preconditioner.get("factor_count_after_destroy") == 0
                and preconditioner.get("no_direct_fallback") is True
                and preconditioner.get("borrowed_action_survives_after_release") is True
            )
        if side_record.get("pass") is not side_numeric_pass:
            return False
        all_numeric_pass &= side_numeric_pass
    if (
        telemetry.get("r3_contract_pass") is not all_contract
        or telemetry.get("r3_numerical_pass") is not all_numeric_pass
        or gates.get("r3_record_complete") is not all_contract
        or gates.get("r3_all_cases_complete") is not all_contract
        or gates.get("r3_all_probes_finite") is not all_finite
        or gates.get("r3_no_direct_fallback") is not True
        or gates.get("r3_factors_released") is not all_contract
        or gates.get("r3_pass") is not all_numeric_pass
        or qualification.get("r3_pass") is not all_numeric_pass
        or qualification.get("worker_numerical_pass") is not all_numeric_pass
        or qualification.get("disposition")
        != (
            "r3_numerical_pass_awaiting_r4"
            if all_numeric_pass
            else "r3_numerical_negative_awaiting_r4"
        )
    ):
        return False
    return bool(
        all_numeric_pass if require_numerical_pass else all_contract and all_finite
    )


def _h5_stage_memory_summary(
    rows: list[dict[str, Any]], *, expected_mpi_size: int
) -> dict[str, dict[str, Any]]:
    """Summarize H5 RSS/PSS/USS without mixing direct and candidate stages."""

    stage_groups = {
        "common_action_coupling": {"h5_action_coupling_build"},
        "h5a_direct_reference": {
            "oracle_local_matrix_build",
            "h5a_bottom_factor",
            "h5a_bottom_solve",
            "h5a_bottom_release",
            "h5a_top_factor",
            "h5a_top_solve",
            "h5a_top_release",
        },
        "h5_post_direct_trim": {"h5_post_direct_heap_trim"},
        "h5b_candidate": {
            "h5b_simultaneous_inverse_setup",
            "h5b_bottom_solves",
            "h5b_top_solves",
            "h5b_release_record",
        },
    }

    def finite_values(group_rows: list[dict[str, Any]], key: str) -> list[float]:
        values: list[float] = []
        for row in group_rows:
            value = row.get(key)
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
        return values

    summary: dict[str, dict[str, Any]] = {}
    for name, stages in stage_groups.items():
        group_rows = [row for row in rows if row.get("stage") in stages]
        complete_rows: list[dict[str, Any]] = []
        for row in group_rows:
            try:
                readable_count = int(row.get("worker_rank_smaps_readable_count"))
            except (TypeError, ValueError):
                continue
            if readable_count == expected_mpi_size:
                complete_rows.append(row)
        pss_values = finite_values(complete_rows, "worker_rank_pss_sum_mb")
        uss_values = finite_values(complete_rows, "worker_rank_uss_sum_mb")
        rss_values = finite_values(group_rows, "worker_rank_rss_sum_mb")
        tree_rss_values = finite_values(group_rows, "mpi_process_tree_rss_mb")
        summary[name] = {
            "stages": sorted(stages),
            "sample_count": len(group_rows),
            "complete_smaps_sample_count": len(complete_rows),
            "peak_worker_rank_rss_sum_mb": (max(rss_values) if rss_values else None),
            "peak_worker_rank_pss_sum_mb": (max(pss_values) if pss_values else None),
            "peak_worker_rank_uss_sum_mb": (max(uss_values) if uss_values else None),
            "peak_mpi_process_tree_rss_mb": (
                max(tree_rss_values) if tree_rss_values else None
            ),
        }
    return summary


def _external_resource_authority(
    rows: list[dict[str, Any]],
    memory: dict[str, Any],
    *,
    environment_before: dict[str, Any],
    environment_after: dict[str, Any],
    live_authority_all_readable: bool,
) -> dict[str, Any]:
    worker_gib = memory.get("max_simultaneous_worker_rss_gib")
    cgroup_gib = memory.get("max_container_cgroup_current_gib")
    worker_bytes = None if worker_gib is None else int(float(worker_gib) * 1024**3)
    cgroup_bytes = None if cgroup_gib is None else int(float(cgroup_gib) * 1024**3)
    dedicated_cgroup = memory.get("dedicated_job_cgroup_observed") is True
    authority = (
        None
        if worker_bytes is None or (dedicated_cgroup and cgroup_bytes is None)
        else max(worker_bytes, cgroup_bytes if dedicated_cgroup else 0)
    )
    limits = [
        environment_before.get("memory_limit_bytes"),
        environment_after.get("memory_limit_bytes"),
    ]
    host_available = [
        environment_before.get("host_available_memory_bytes"),
        environment_after.get("host_available_memory_bytes"),
    ]
    sampled_swap_all_readable = memory.get("job_swap_all_samples_readable") is True
    swap_current = (
        0
        if sampled_swap_all_readable
        and int(memory.get("max_process_tree_swap_bytes") or 0) == 0
        and int(memory.get("max_dedicated_cgroup_swap_bytes") or 0) == 0
        else None
    )
    record = {
        "simultaneous_live_worker_rss_sum_bytes": worker_bytes,
        "container_cgroup_current_bytes": cgroup_bytes,
        "memory_authority_bytes": authority,
        "memory_authority_gib": (None if authority is None else authority / 1024**3),
        "memory_authority_semantics": (
            "max(simultaneous live MPI worker RSS sum, container cgroup current)"
        ),
        "container_memory_limit_bytes": (
            None
            if any(value is None for value in limits)
            else min(int(value) for value in limits)
        ),
        "host_available_memory_bytes": (
            None
            if any(value is None for value in host_available)
            else min(int(value) for value in host_available)
        ),
        "container_swap_current_bytes": swap_current,
        "pswpin_delta_pages": memory.get("wsl_pswpin_delta_pages"),
        "pswpout_delta_pages": memory.get("wsl_pswpout_delta_pages"),
        "job_cgroup_dedicated": dedicated_cgroup,
        "wsl_global_pswp_formal": False,
        "wsl_global_pswp_role": "diagnostic_only",
        "job_process_tree_swap_bytes": memory.get("max_process_tree_swap_bytes"),
        "environment_before": environment_before,
        "environment_after": environment_after,
        "all_live_authority_samples_readable": live_authority_all_readable,
        "all_live_swap_samples_readable": sampled_swap_all_readable,
    }
    gate = resource_authority_gate(record)
    extra_checks = {
        "all_live_authority_samples_readable": live_authority_all_readable,
        "all_live_swap_samples_readable": sampled_swap_all_readable,
    }
    gate["checks"].update(extra_checks)
    gate["failures"] = [name for name, passed in gate["checks"].items() if not passed]
    gate["pass"] = not gate["failures"]
    record["gate"] = gate
    return record


def _available_physical_core_count() -> int | None:
    allowed = (
        set(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else set(range(os.cpu_count() or 0))
    )
    try:
        completed = subprocess.run(
            ["lscpu", "-p=CPU,CORE,SOCKET,ONLINE"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    physical_cores: set[tuple[int, int]] = set()
    for line in completed.stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            cpu, core, socket, online = line.split(",")
            if int(cpu) in allowed and online.strip().lower() in {"y", "yes"}:
                physical_cores.add((int(socket), int(core)))
        except (TypeError, ValueError):
            return None
    return len(physical_cores) or None


def _task037b_v1_r4_numerical_pass(record: dict[str, Any]) -> bool:
    """Recompute the bounded R4 Woodbury contract from raw probe fields."""

    if not isinstance(record, dict):
        return False
    if (
        record.get("schema_version") != 1
        or record.get("record_schema") != "task037b.v1-r4-dtn-woodbury.v1"
        or record.get("benchmark_id") != "task037b_v1_r4_dtn_woodbury_oracle"
        or record.get("status") != "task037b_v1_r4_complete_awaiting_r5"
    ):
        return False
    telemetry = record.get("v1_r4_telemetry")
    qualification = record.get("qualification")
    gates = record.get("gates")
    if (
        not isinstance(telemetry, dict)
        or not isinstance(qualification, dict)
        or not isinstance(gates, dict)
        or telemetry.get("task037b_v1_gate") is not True
        or telemetry.get("n_aux") != 40
        or telemetry.get("normal_equations") is not False
        or telemetry.get("formal_probe_count_per_side") != 11
        or telemetry.get("r4_contract_pass") is not True
        or telemetry.get("r4_numerical_pass") is not True
        or telemetry.get("ordinary_default_changed") is not False
        or qualification.get("task037b_v1_gate") is not True
        or qualification.get("integration_pass") is not True
    ):
        return False
    hybrid_system = record.get("hybrid_system")
    validation = record.get("validation")
    physical = record.get("physical_field_reconstruction")
    if (
        not isinstance(hybrid_system, dict)
        or hybrid_system.get("global_action_constructed") is not False
        or hybrid_system.get("global_A_materialized") is not False
        or hybrid_system.get("global_F_materialized") is not False
        or hybrid_system.get("explicit_global_C_D_materialized") is not False
        or hybrid_system.get("direct_factor_count") != 0
        or hybrid_system.get("external_auxiliary_rows_in_krylov") != 0
        or not isinstance(validation, dict)
        or any(
            validation.get(name) != "not_run"
            for name in (
                "port_power",
                "R_total",
                "T_total",
                "A_balance",
                "A_volume_total",
                "external_diffraction_orders",
            )
        )
        or not isinstance(physical, dict)
        or physical.get("status") != "not_run"
    ):
        return False
    sides = telemetry.get("sides")
    if not isinstance(sides, dict) or set(sides) != {"bottom", "top"}:
        return False
    expected_side_pass = True
    capacity_pass_total = 0
    for side_name, side in sides.items():
        expected_capacity = 10 if side_name == "bottom" else 11
        expected_zero = 1 if side_name == "bottom" else 0
        if (
            not isinstance(side, dict)
            or side.get("probe_count") != 11
            or side.get("contract_pass") is not True
            or side.get("action_survives_after_release") is not True
            or side.get("all_probes_finite") is not True
            or not isinstance(side.get("rows"), list)
            or len(side["rows"]) != 11
            or side.get("operator", {}).get("n_aux") != 40
            or side.get("operator", {}).get("normal_equations") is not False
            or side.get("operator", {}).get("identity")
            != "borrowed_F_plus_Dtn_Woodbury"
            or side.get("operator", {}).get("base_identity")
            != "exact_F_direct_test_only"
            or side.get("operator", {}).get("external_dtn_correction") != "included"
        ):
            return False
        components = side.get("operator", {}).get("components")
        if (
            not isinstance(components, dict)
            or not isinstance(components.get("F"), dict)
            or not isinstance(components.get("C"), dict)
            or not isinstance(components.get("D"), dict)
            or not isinstance(components.get("H"), dict)
            or components["F"].get("type") != "python"
            or components["C"].get("type") != "python"
            or components["D"].get("type") != "python"
            or components["F"].get("shape") != [8424, 8424]
            or components["C"].get("shape") != [8424, 40]
            or components["D"].get("shape") != [40, 8424]
            or components["H"].get("shape") != [40, 40]
        ):
            return False
        woodbury = side.get("woodbury")
        release = side.get("factor_release")
        if (
            not isinstance(woodbury, dict)
            or woodbury.get("base_identity") != "exact_F_direct_test_only"
            or woodbury.get("n_aux") != 40
            or woodbury.get("K_rank") != 40
            or woodbury.get("K_shape") != [40, 40]
            or woodbury.get("K_dtype") != "complex128"
            or not isinstance(woodbury.get("K_condition_number"), (int, float))
            or not math.isfinite(float(woodbury["K_condition_number"]))
            or float(woodbury["K_condition_number"]) > 1.0e10
            or woodbury.get("normal_equations") is not False
            or not isinstance(woodbury.get("W_local_nbytes_by_rank"), list)
            or not woodbury["W_local_nbytes_by_rank"]
            or not isinstance(release, dict)
            or release.get("never_simultaneous") is not True
            or release.get("max_active_factor_count") != 1
            or release.get("final_active_factor_count") != 0
            or release.get("a_released_before_f_created") is not True
            or release.get("explicit_reference_C_D_H_released_before_f_factor")
            is not True
        ):
            return False
        for factor_name in ("a_factor", "f_factor"):
            factor = release.get(factor_name)
            if (
                not isinstance(factor, dict)
                or factor.get("factor_count_before") != 1
                or factor.get("factor_count_after") != 0
                or factor.get("released") is not True
            ):
                return False
        side_pass = True
        nonzero_rows = []
        zero_rows = []
        for row in side["rows"]:
            if not isinstance(row, dict):
                return False
            numeric = (
                "direct_true_residual",
                "woodbury_true_residual",
                "solution_relative_error",
                "repeat_error",
            )
            finite = all(
                isinstance(row.get(key), (int, float))
                and math.isfinite(float(row[key]))
                and float(row[key]) >= 0.0
                for key in numeric
            )
            expected = bool(
                finite
                and float(row["direct_true_residual"]) <= 1.0e-10
                and float(row["woodbury_true_residual"]) <= 1.0e-10
                and float(row["solution_relative_error"]) <= 1.0e-10
                and float(row["repeat_error"]) <= 1.0e-12
            )
            if row.get("finite") is not finite or row.get("pass") is not expected:
                return False
            if row.get("zero_physical_rhs") is True:
                if row.get("zero_equation_pass") is not expected:
                    return False
                zero_rows.append(row)
            elif row.get("zero_physical_rhs") is False:
                if row.get("capacity_pass") is not expected:
                    return False
                nonzero_rows.append(row)
            else:
                return False
        capacity_pass_count = sum(bool(row["capacity_pass"]) for row in nonzero_rows)
        zero_equation_pass = bool(
            len(zero_rows) == expected_zero
            and all(row.get("zero_equation_pass") is True for row in zero_rows)
        )
        side_pass = bool(
            len(nonzero_rows) == expected_capacity
            and capacity_pass_count == expected_capacity
            and zero_equation_pass
        )
        capacity_pass_total += capacity_pass_count
        if (
            side.get("pass") is not side_pass
            or side.get("nonzero_capacity_count") != len(nonzero_rows)
            or side.get("capacity_pass_count") != capacity_pass_count
            or side.get("capacity_expected_count") != expected_capacity
            or side.get("zero_physical_count") != len(zero_rows)
            or side.get("zero_equation_pass") is not zero_equation_pass
        ):
            return False
        zero_names = {row.get("name") for row in zero_rows}
        if (
            side_name == "bottom"
            and zero_names != {"physical"}
            or side_name == "top"
            and zero_names
        ):
            return False
        expected_side_pass &= side_pass
    if (
        gates.get("r4_record_complete") is not True
        or gates.get("r4_all_probe_records_complete") is not True
        or gates.get("r4_all_probes_finite") is not True
        or gates.get("r4_factor_noncoexistence") is not True
        or gates.get("r4_factors_released") is not True
        or gates.get("r4_no_direct_fallback") is not True
        or capacity_pass_total != 21
        or gates.get("r4_pass") is not expected_side_pass
        or qualification.get("r4_pass") is not expected_side_pass
        or qualification.get("worker_numerical_pass") is not expected_side_pass
        or qualification.get("disposition")
        != (
            "r4_pass_awaiting_r5"
            if expected_side_pass
            else "DTN_WOODBURY_ORACLE_IMPLEMENTATION_FAILED"
        )
    ):
        return False
    return True


def _task037b_v1_r5_numerical_pass(
    record: dict[str, Any], *, require_numerical_pass: bool = True
) -> bool:
    """Recompute the fixed R5 local-inverse Woodbury contract from raw data."""

    if not isinstance(record, dict):
        return False
    telemetry = record.get("v1_r5_telemetry")
    qualification = record.get("qualification")
    gates = record.get("gates")
    hybrid = record.get("hybrid_system")
    validation = record.get("validation")
    physical = record.get("physical_field_reconstruction")
    if (
        record.get("schema_version") != 1
        or record.get("record_schema") != "task037b.v1-r5-dtn-woodbury-local-inverse.v1"
        or record.get("benchmark_id") != "task037b_v1_r5_dtn_woodbury_local_inverse"
        or not isinstance(telemetry, dict)
        or not isinstance(qualification, dict)
        or not isinstance(gates, dict)
        or not isinstance(hybrid, dict)
        or not isinstance(validation, dict)
        or not isinstance(physical, dict)
        or telemetry.get("task037b_v1_gate") is not True
        or telemetry.get("ordinary_default_changed") is not False
        or qualification.get("task037b_v1_gate") is not True
        or hybrid.get("global_A_materialized") is not False
        or hybrid.get("global_F_materialized") is not False
        or hybrid.get("explicit_global_C_D_materialized") is not False
        or hybrid.get("direct_factor_count") != 0
        or hybrid.get("external_auxiliary_rows_in_krylov") != 0
        or any(
            validation.get(name) != "not_run"
            for name in (
                "port_power",
                "R_total",
                "T_total",
                "A_balance",
                "A_volume_total",
                "external_diffraction_orders",
            )
        )
        or physical.get("status") != "not_run"
    ):
        return False

    def finite_number(value: Any) -> bool:
        return bool(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    def row_residual(row: dict[str, Any]) -> float:
        return max(
            float(row["first"]["complete_A_true_residual"]),
            float(row["second"]["complete_A_true_residual"]),
        )

    sides = telemetry.get("sides")
    if not isinstance(sides, dict) or set(sides) != {"bottom", "top"}:
        return False
    factor_lifecycle = gates.get("r5_factor_lifecycle")
    if (
        not isinstance(factor_lifecycle, dict)
        or factor_lifecycle.get("bottom_released_before_top_setup") is not True
        or factor_lifecycle.get("global_max_active_factor_count") != 1
        or factor_lifecycle.get("global_final_active_factor_count") != 0
    ):
        return False
    side_contracts: dict[str, bool] = {}
    side_algebra: dict[str, bool] = {}
    side_numeric: dict[str, bool] = {}
    all_random_values: list[float] = []
    all_modal_values: list[float] = []
    all_iterations_ok = True
    all_rows_finite = True
    severe_negative = False
    for side_name, side in sides.items():
        if not isinstance(side, dict):
            return False
        expected_capacity = 10 if side_name == "bottom" else 11
        expected_zero = 1 if side_name == "bottom" else 0
        operator = side.get("operator")
        configuration = side.get("configuration")
        base = side.get("base")
        woodbury = side.get("woodbury")
        pc_audit = side.get("pc_audit")
        release = side.get("factor_release")
        rows = side.get("rows")
        if (
            not isinstance(operator, dict)
            or not isinstance(configuration, dict)
            or not isinstance(base, dict)
            or not isinstance(woodbury, dict)
            or not isinstance(pc_audit, dict)
            or not isinstance(release, dict)
            or not isinstance(rows, list)
            or len(rows) != 11
            or side.get("probe_count") != 11
            or side.get("nonzero_capacity_count") != expected_capacity
            or side.get("zero_physical_count") != expected_zero
            or operator.get("identity")
            != "complete_hybrid_action_with_whole_endcap_dtn_woodbury"
            or operator.get("base_identity") != "whole_endcap_ilu0_smoother"
            or operator.get("external_dtn_correction") != "included"
            or operator.get("matrix_type") != "python"
            or operator.get("matrix_free") is not True
            or operator.get("global_A_materialized") is not False
            or configuration.get("preconditioner_profile") != "v1_whole_endcap_ilu0"
            or configuration.get("num_subdomains") != 1
            or configuration.get("overlap_fraction") != 0.0
            or configuration.get("coordinate_axis") != 0
            or configuration.get("interpolation") != "partition"
            or configuration.get("ilu_levels") != 0
            or configuration.get("factor_only") is not True
            or configuration.get("one_apply_per_pc_apply") is not True
            or configuration.get("two_step_action_operator") is not None
            or configuration.get("outer_solver") != "right_fgmres"
            or configuration.get("restart") != 30
            or configuration.get("max_it") != 300
            or configuration.get("rtol") != 1.0e-10
            or configuration.get("atol") != 0.0
            or configuration.get("true_residual_limit") != 1.0e-8
            or base.get("identity") != "whole_endcap_ilu0_smoother"
            or not all(
                isinstance(base.get(name), int) and base.get(name) > 0
                for name in (
                    "source_matrix_nnz",
                    "factor_nnz",
                    "factor_csr_payload_estimate_bytes",
                )
            )
            or woodbury.get("base_identity") != "whole_endcap_ilu0_smoother"
            or woodbury.get("n_aux") != 40
            or woodbury.get("K_shape") != [40, 40]
            or woodbury.get("K_dtype") != "complex128"
            or not isinstance(woodbury.get("W_local_nbytes_by_rank"), list)
            or not woodbury["W_local_nbytes_by_rank"]
            or release.get("factor_count_before") != 1
            or release.get("factor_count_after") != 0
            or release.get("factors_released") is not True
            or release.get("woodbury_destroyed") is not True
            or release.get("max_active_factor_count") != 1
            or release.get("never_simultaneous") is not True
            or side.get("action_survives_after_release") is not True
        ):
            return False
        row_names: set[str] = set()
        random_rows = []
        modal_rows = []
        physical_rows = []
        all_finite = True
        all_numeric = True
        nonzero_rows = []
        nonzero_numeric_flags = []
        zero_rows = []
        zero_numeric_flags = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                return False
            if row["name"] in row_names:
                return False
            row_names.add(row["name"])
            first = row.get("first")
            second = row.get("second")
            if not isinstance(first, dict) or not isinstance(second, dict):
                return False
            numeric_keys = (
                "reported_residual",
                "complete_A_true_residual",
                "setup_seconds",
                "solve_seconds",
                "apply_seconds",
            )
            finite = bool(
                all(finite_number(first.get(key)) for key in numeric_keys)
                and all(finite_number(second.get(key)) for key in numeric_keys)
                and all(
                    float(first.get(key)) >= 0.0 and float(second.get(key)) >= 0.0
                    for key in numeric_keys
                )
                and isinstance(first.get("reason"), int)
                and not isinstance(first.get("reason"), bool)
                and isinstance(second.get("reason"), int)
                and not isinstance(second.get("reason"), bool)
                and isinstance(first.get("iterations"), int)
                and not isinstance(first.get("iterations"), bool)
                and isinstance(second.get("iterations"), int)
                and not isinstance(second.get("iterations"), bool)
                and finite_number(row.get("repeat_solution_relative_error"))
                and float(row["repeat_solution_relative_error"]) >= 0.0
                and row.get("repeat_reason_equal")
                is (first["reason"] == second["reason"])
                and row.get("repeat_iterations_equal")
                is (first["iterations"] == second["iterations"])
            )
            finite &= bool(
                float(first.get("complete_A_true_residual", 0.0)) >= 0.0
                and float(second.get("complete_A_true_residual", 0.0)) >= 0.0
            )
            row_numeric = bool(
                finite
                and first["reason"] > 0
                and second["reason"] > 0
                and first["iterations"] <= 300
                and second["iterations"] <= 300
                and float(first["complete_A_true_residual"]) <= 1.0e-8
                and float(second["complete_A_true_residual"]) <= 1.0e-8
                and float(row["repeat_solution_relative_error"]) <= 1.0e-12
            )
            if row.get("finite") is not finite or row.get("pass") is not row_numeric:
                return False
            all_finite &= finite
            all_numeric &= row_numeric
            if row.get("zero_physical_rhs") is True:
                if row.get("zero_equation_pass") is not row_numeric:
                    return False
                zero_rows.append(row)
                zero_numeric_flags.append(row_numeric)
            elif row.get("zero_physical_rhs") is False:
                if row.get("capacity_pass") is not row_numeric:
                    return False
                nonzero_rows.append(row)
                nonzero_numeric_flags.append(row_numeric)
            else:
                return False
            kind = (row.get("metadata") or {}).get("kind")
            if kind == "partition_independent_complex_random":
                random_rows.append(row)
            elif kind == "frozen_modal_traction":
                modal_rows.append(row)
            elif kind == "physical_action_rhs":
                physical_rows.append(row)
        expected_random_names = {
            f"random_seed_{seed}" for seed in (3701, 3702, 3703, 3704)
        }
        expected_modal_identity = True
        for direction in ("positive", "negative"):
            direction_modal = [
                row
                for row in modal_rows
                if isinstance(row.get("metadata"), dict)
                and isinstance(row["metadata"].get("mode_identity"), dict)
                and row["metadata"]["mode_identity"].get("direction") == direction
            ]
            criteria = [
                row["metadata"]["mode_identity"].get("criterion")
                for row in direction_modal
            ]
            expected_modal_identity &= bool(
                len(direction_modal) == 3
                and criteria.count("lowest_propagating_or_lossy") == 1
                and criteria.count("highest_retained_index") == 1
                and sum(
                    criterion
                    in {
                        "first_kind_evanescent",
                        "proxy_abs_im_beta_gt_abs_re_beta",
                    }
                    for criterion in criteria
                )
                == 1
                and all(
                    row["metadata"]["mode_identity"].get("local_mode_index") == 119
                    for row in direction_modal
                    if row["metadata"]["mode_identity"].get("criterion")
                    == "highest_retained_index"
                )
            )
        expected_capacity_pass_count = sum(
            bool(value) for value in nonzero_numeric_flags
        )
        expected_zero_equation_pass = bool(
            len(zero_rows) == expected_zero and all(zero_numeric_flags)
        )
        if (
            side.get("capacity_pass_count") != expected_capacity_pass_count
            or side.get("zero_equation_pass") is not expected_zero_equation_pass
        ):
            return False
        expected_contract = bool(
            len(nonzero_rows) == expected_capacity
            and len(zero_rows) == expected_zero
            and len(random_rows) == 4
            and {row["name"] for row in random_rows} == expected_random_names
            and len(modal_rows) == 6
            and len(physical_rows) == 1
            and physical_rows[0]["name"] == "physical"
            and physical_rows[0]["zero_physical_rhs"] is (side_name == "bottom")
            and expected_modal_identity
            and side.get("capacity_expected_count") == expected_capacity
            and side.get("zero_equation_pass") is expected_zero_equation_pass
        )
        expected_no_direct_fallback = bool(
            operator.get("direct_factor_count") == 0
            and base.get("identity") == "whole_endcap_ilu0_smoother"
        )
        expected_algebra = bool(
            all_finite
            and all(
                float(row["repeat_solution_relative_error"]) <= 1.0e-12 for row in rows
            )
            and side.get("pc_audit", {}).get("finite") is True
            and finite_number(side["pc_audit"].get("linearity_error"))
            and finite_number(side["pc_audit"].get("determinism_error"))
            and float(side["pc_audit"]["linearity_error"]) <= 1.0e-11
            and float(side["pc_audit"]["determinism_error"]) <= 1.0e-12
            and expected_no_direct_fallback
            and woodbury.get("normal_equations") is False
            and woodbury.get("K_rank") == 40
            and finite_number(woodbury.get("K_condition_number"))
            and float(woodbury["K_condition_number"]) <= 1.0e10
            and woodbury.get("arrays_finite") is True
        )
        expected_side_numeric = bool(
            expected_contract
            and expected_algebra
            and expected_capacity_pass_count == expected_capacity
            and all_numeric
        )
        if (
            side.get("contract_pass") is not expected_contract
            or side.get("algebra_legality_pass") is not expected_algebra
            or side.get("pass") is not expected_side_numeric
            or side.get("all_probes_finite") is not all_finite
            or side.get("no_direct_fallback") is not expected_no_direct_fallback
        ):
            return False
        side_contracts[side_name] = expected_contract
        side_algebra[side_name] = expected_algebra
        side_numeric[side_name] = expected_side_numeric
        random_values = [row_residual(row) for row in random_rows]
        other_values = [row_residual(row) for row in (*modal_rows, *physical_rows)]
        all_random_values.extend(random_values)
        all_modal_values.extend(other_values)
        all_iterations_ok &= all(
            summary["iterations"] <= 300
            for row in rows
            for summary in (row["first"], row["second"])
        )
        all_rows_finite &= all_finite
        severe_negative |= bool(
            sum(value > 1.0e-2 for value in random_values) > len(random_values) / 2
            or any(value > 1.0e-3 for value in other_values)
        )

    expected_contract = bool(
        all(side_contracts.values())
        and factor_lifecycle["bottom_released_before_top_setup"] is True
        and factor_lifecycle["global_max_active_factor_count"] == 1
        and factor_lifecycle["global_final_active_factor_count"] == 0
    )
    expected_algebra = bool(expected_contract and all(side_algebra.values()))
    expected_numeric = bool(expected_algebra and all(side_numeric.values()))
    expected_pc_linearity = bool(
        all(
            finite_number(side["pc_audit"].get("linearity_error"))
            and float(side["pc_audit"]["linearity_error"]) <= 1.0e-11
            for side in sides.values()
        )
    )
    expected_pc_determinism = bool(
        all(
            finite_number(side["pc_audit"].get("determinism_error"))
            and float(side["pc_audit"]["determinism_error"]) <= 1.0e-12
            for side in sides.values()
        )
    )
    expected_factors_released = bool(
        all(
            side["factor_release"].get("factor_count_after") == 0
            and side["factor_release"].get("factors_released") is True
            for side in sides.values()
        )
    )
    expected_no_direct_fallback = bool(
        all(side.get("no_direct_fallback") is True for side in sides.values())
    )
    expected_factor_noncoexistence = bool(
        factor_lifecycle["bottom_released_before_top_setup"] is True
        and factor_lifecycle["global_max_active_factor_count"] == 1
        and factor_lifecycle["global_final_active_factor_count"] == 0
    )
    expected_borderline = bool(
        not expected_numeric
        and expected_contract
        and expected_algebra
        and all_modal_values
        and all_random_values
        and all(value <= 1.0e-8 for value in all_modal_values)
        and all(value <= 1.0e-5 for value in all_random_values)
        and any(value > 1.0e-8 for value in all_random_values)
        and all_iterations_ok
        and all_rows_finite
    )
    expected_status = (
        "task037b_v1_r5_complete_awaiting_h6"
        if expected_numeric
        else "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
        if expected_borderline
        else "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
        if expected_contract
        else "DTN_WOODBURY_LOCAL_INVERSE_IMPLEMENTATION_FAILED"
    )
    expected_disposition = (
        "r5_pass_awaiting_h6"
        if expected_numeric
        else "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
        if expected_borderline
        else "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
        if expected_contract
        else "DTN_WOODBURY_LOCAL_INVERSE_IMPLEMENTATION_FAILED"
    )
    if (
        record.get("status") != expected_status
        or telemetry.get("r5_contract_pass") is not expected_contract
        or telemetry.get("r5_algebra_legality_pass") is not expected_algebra
        or telemetry.get("r5_numerical_pass") is not expected_numeric
        or telemetry.get("r5_borderline") is not expected_borderline
        or telemetry.get("severe_negative") is not severe_negative
        or gates.get("r5_record_complete") is not expected_contract
        or gates.get("r5_all_probe_records_complete") is not True
        or gates.get("r5_all_probes_finite")
        is not all(side.get("all_probes_finite") is True for side in sides.values())
        or gates.get("r5_pc_linearity") is not expected_pc_linearity
        or gates.get("r5_pc_determinism") is not expected_pc_determinism
        or gates.get("r5_factors_released") is not expected_factors_released
        or gates.get("r5_no_direct_fallback") is not expected_no_direct_fallback
        or gates.get("r5_factor_noncoexistence") is not expected_factor_noncoexistence
        or gates.get("r5_algebra_legality_pass") is not expected_algebra
        or gates.get("r5_pass") is not expected_numeric
        or qualification.get("r5_pass") is not expected_numeric
        or qualification.get("worker_numerical_pass") is not expected_numeric
        or qualification.get("integration_pass") is not expected_contract
        or qualification.get("disposition") != expected_disposition
    ):
        return False
    return bool(expected_numeric if require_numerical_pass else expected_contract)


def _v2_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _task037b_v2_resource_classification(
    process_tree_peak_mb: float | int | None,
) -> dict[str, Any]:
    measurement_present = bool(
        _v2_finite_number(process_tree_peak_mb) and float(process_tree_peak_mb) >= 0.0
    )
    peak_mb = float(process_tree_peak_mb) if measurement_present else None
    peak_gib = None if peak_mb is None else peak_mb / 1024.0
    return {
        "process_tree_peak_mb": peak_mb,
        "process_tree_peak_gib": peak_gib,
        "resource_threshold_gib": 6.0,
        "engineering_threshold_gib": 5.0,
        "measurement_present": measurement_present,
        "resource_positive": bool(measurement_present and peak_gib <= 6.0),
        "engineering_positive": bool(measurement_present and peak_gib <= 5.0),
        "resource_review": bool(measurement_present and peak_gib > 6.0),
        "measurement_failure": not measurement_present,
    }


def _task037b_v2_numerical_pass(
    record: dict[str, Any], *, require_numerical_pass: bool = True
) -> bool:
    """Recompute the V2 raw contract and bounded screen Gate from evidence."""

    try:
        if not isinstance(record, dict):
            return False
        case = record.get("case")
        screen = record.get("screen")
        telemetry = record.get("v2_telemetry")
        gates = record.get("gates")
        qualification = record.get("qualification")
        hybrid = record.get("hybrid_system")
        validation = record.get("validation")
        physical = record.get("physical_field_reconstruction")
        if not all(
            isinstance(item, dict)
            for item in (
                case,
                screen,
                telemetry,
                gates,
                qualification,
                hybrid,
                validation,
                physical,
            )
        ):
            return False
        inventory_before_release = screen.get("inventory_before_release")
        if not isinstance(inventory_before_release, dict):
            return False
        pc_apply_count = inventory_before_release.get("pc_apply_count")
        if not (
            isinstance(pc_apply_count, int)
            and not isinstance(pc_apply_count, bool)
            and pc_apply_count >= 0
        ):
            return False
        profile = case.get("v2_profile")
        max_it = case.get("v2_max_it")
        if profile not in {"bottom-approx", "top-approx", "double"} or max_it not in {
            20,
            100,
            200,
        }:
            return False
        if profile != "double" and max_it != 20:
            return False
        if (
            record.get("schema_version") != 1
            or record.get("record_schema") != "task037b.v2-block-pc-screen.v1"
            or record.get("benchmark_id") != "task037b_v2_bounded_block_pc_screen"
            or record.get("official_record") is not False
            or case.get("degree") != 6
            or case.get("h_nm") != 10.0
            or case.get("modal_degree") != 6
            or case.get("modal_h_nm") != 10.0
            or case.get("requested_modes") != 120
            or case.get("candidate_modes") != 240
            or case.get("mpi_size") != 8
            or case.get("solver_path") != "block-ldu-action-screen"
            or case.get("polarization_kind") != "s"
            or case.get("incident_grazing_deg") != 10.0
            or case.get("bottom_interface_nm") != 10.0
            or case.get("top_interface_nm") != 110.0
            or physical.get("status") != "not_run"
            or validation.get("official_record") is not False
            or qualification.get("official_record") is not False
        ):
            return False
        if any(
            validation.get(key) != "not_run"
            for key in (
                "R",
                "T",
                "A",
                "A_volume",
                "orders",
                "external_diffraction_orders",
                "field",
                "12_plus_12",
                "Full3D",
                "full3d_comparison",
            )
        ):
            return False
        if telemetry.get("task037b_v2_gate") is not True:
            return False
        if telemetry.get("profile") != profile or telemetry.get("max_it") != max_it:
            return False
        if qualification.get("task037b_v2_gate") is not True:
            return False
        if (
            qualification.get("profile") != profile
            or qualification.get("max_it") != max_it
        ):
            return False
        if telemetry.get("ordinary_default_changed") is not False:
            return False

        expected_factors = {
            "bottom-approx": {"bottom": (0, 1), "top": (1, 0)},
            "top-approx": {"bottom": (1, 0), "top": (0, 1)},
            "double": {"bottom": (0, 1), "top": (0, 1)},
        }[profile]
        sides = telemetry.get("sides")
        factor_identity = telemetry.get("factor_identity")
        certificates = telemetry.get("fixed_callback_certificates")
        if (
            not isinstance(sides, dict)
            or not isinstance(factor_identity, dict)
            or not isinstance(certificates, dict)
        ):
            return False
        if set(sides) != {"bottom", "top"} or set(factor_identity) != {"bottom", "top"}:
            return False
        approximate_action_sides = (
            {"bottom"}
            if profile == "bottom-approx"
            else {"top"}
            if profile == "top-approx"
            else {"bottom", "top"}
        )
        one_apply_diagnostic_sides = (
            {"bottom"}
            if profile == "bottom-approx"
            else {"top"}
            if profile == "top-approx"
            else set()
        )
        callback_contract = True
        factor_contract = True
        online_contract = True
        release_contract = True
        raw_release_records = telemetry.get("release_records")
        if not isinstance(raw_release_records, dict):
            return False
        side_release_recomputed: dict[str, bool] = {}
        for side in ("bottom", "top"):
            side_record = sides[side]
            identity = factor_identity[side]
            if not isinstance(side_record, dict) or not isinstance(identity, dict):
                return False
            expected_direct, expected_ilu = expected_factors[side]
            factor_contract &= bool(
                identity.get("direct_factor_count") == expected_direct
                and identity.get("ilu_factor_count") == expected_ilu
                and identity.get("borrowed_local_factor_count")
                == expected_direct + expected_ilu
                and identity.get("expected_direct_factor_count") == expected_direct
                and identity.get("expected_ilu_factor_count") == expected_ilu
                and identity.get("pass") is True
            )
            certificate = certificates.get(side)
            if side in approximate_action_sides:
                if not isinstance(certificate, dict):
                    callback_contract = False
                else:
                    woodbury = certificate.get("woodbury")
                    callback_contract &= bool(
                        certificate.get("pass") is True
                        and _v2_finite_number(
                            certificate.get("wrapper_vs_internal_woodbury_error")
                        )
                        and float(certificate["wrapper_vs_internal_woodbury_error"])
                        <= 1.0e-13
                        and _v2_finite_number(certificate.get("linearity_error"))
                        and float(certificate["linearity_error"]) <= 1.0e-12
                        and _v2_finite_number(certificate.get("determinism_error"))
                        and float(certificate["determinism_error"]) <= 1.0e-14
                        and certificate.get("repeat_hash_equal") is True
                        and isinstance(woodbury, dict)
                        and woodbury.get("K_rank") == 40
                        and _v2_finite_number(woodbury.get("K_condition_number"))
                        and float(woodbury["K_condition_number"]) <= 1.0e10
                        and woodbury.get("arrays_finite") is True
                        and certificate.get("base_factor_count") == 1
                        and certificate.get("local_direct_factor_count") == 0
                        and certificate.get("nested_ksp_created") is False
                        and isinstance(certificate.get("apply_count_before"), int)
                        and not isinstance(certificate.get("apply_count_before"), bool)
                        and certificate.get("apply_count_before") >= 0
                        and isinstance(certificate.get("apply_count_after"), int)
                        and not isinstance(certificate.get("apply_count_after"), bool)
                        and certificate.get("apply_count_after") >= 0
                        and isinstance(certificate.get("apply_count_increment"), int)
                        and not isinstance(
                            certificate.get("apply_count_increment"), bool
                        )
                        and certificate.get("apply_count_increment") >= 0
                        and certificate.get("apply_count_after")
                        - certificate.get("apply_count_before")
                        == certificate.get("apply_count_increment")
                        == 7
                    )
            elif certificate is not None:
                callback_contract = False
            online = side_record.get("online_apply")
            online_contract &= bool(
                isinstance(online, dict)
                and online.get("pass") is True
                and all(
                    isinstance(online.get(key), int)
                    and not isinstance(online.get(key), bool)
                    and online.get(key) >= 0
                    for key in ("before", "after", "increment", "expected_increment")
                )
                and online.get("after") - online.get("before")
                == online.get("increment")
                == online.get("expected_increment")
                == 2 * pc_apply_count
            )
            one_apply = side_record.get("one_apply_diagnostic")
            if side in one_apply_diagnostic_sides:
                rho_records = side_record.get("rho_records")
                expected_count = 10 if side == "bottom" else 11
                online_contract &= bool(
                    isinstance(one_apply, dict)
                    and one_apply.get("status") == "pass"
                    and isinstance(rho_records, list)
                    and len(rho_records) == expected_count
                    and all(
                        isinstance(row, dict)
                        and isinstance(row.get("apply_count_before"), int)
                        and not isinstance(row.get("apply_count_before"), bool)
                        and row.get("apply_count_before") >= 0
                        and isinstance(row.get("apply_count_after"), int)
                        and not isinstance(row.get("apply_count_after"), bool)
                        and row.get("apply_count_after") >= 0
                        and isinstance(row.get("apply_count_increment"), int)
                        and not isinstance(row.get("apply_count_increment"), bool)
                        and row.get("apply_count_increment") >= 0
                        and row.get("apply_count_after") - row.get("apply_count_before")
                        == row.get("apply_count_increment")
                        == 1
                        and row.get("finite") is True
                        and _v2_finite_number(row.get("rho"))
                        for row in rho_records
                    )
                )
            elif profile == "double":
                online_contract &= bool(
                    isinstance(one_apply, dict)
                    and one_apply.get("status") == "not_run_here"
                )
            else:
                online_contract &= one_apply is None
            release = raw_release_records.get(side)
            side_release = side_record.get("release_records")
            if side in approximate_action_sides:
                side_release_recomputed[side] = bool(
                    isinstance(release, dict)
                    and isinstance(release.get("woodbury"), dict)
                    and isinstance(release["woodbury"].get("after"), dict)
                    and release["woodbury"]["after"].get("destroyed") is True
                    and isinstance(release.get("fixed_base"), dict)
                    and isinstance(release["fixed_base"].get("after"), dict)
                    and release["fixed_base"]["after"].get("destroyed") is True
                    and isinstance(release.get("components"), dict)
                    and release["components"].get("destroyed") is True
                )
            else:
                side_release_recomputed[side] = bool(
                    isinstance(release, dict)
                    and isinstance(release.get("direct_action"), dict)
                    and isinstance(release["direct_action"].get("after"), dict)
                    and release["direct_action"]["after"].get("destroyed") is True
                    and isinstance(release.get("oracle"), dict)
                    and release["oracle"].get("destroyed") is True
                )
            release_contract &= bool(
                isinstance(release, dict)
                and isinstance(side_release, dict)
                and side_release == release
                and side_release_recomputed[side] is True
                and release.get("release_pass") is side_release_recomputed[side]
                and side_record.get("release_pass") is side_release_recomputed[side]
                and side_record.get("borrowed_action_survives_after_screen") is True
            )

        modal = telemetry.get("modal_schur")
        modal_contract = bool(
            isinstance(modal, dict)
            and modal.get("shape") == [240, 240]
            and modal.get("rank") == 240
            and modal.get("finite") is True
            and _v2_finite_number(modal.get("condition"))
            and float(modal["condition"]) <= 1.0e12
            and _v2_finite_number(modal.get("matrix_repeat_error"))
            and float(modal["matrix_repeat_error"]) <= 1.0e-13
            and _v2_finite_number(modal.get("lu_repeat_solve_error"))
            and float(modal["lu_repeat_solve_error"]) <= 1.0e-13
            and isinstance(modal.get("build_apply_count"), dict)
            and modal["build_apply_count"].get("bottom") == 480
            and modal["build_apply_count"].get("top") == 480
        )
        operator_inventory = telemetry.get("global_operator_inventory")
        pc_inventory = telemetry.get("pc_setup_inventory")
        global_contract = bool(
            isinstance(operator_inventory, dict)
            and isinstance(pc_inventory, dict)
            and hybrid.get("global_A_materialized") is False
            and hybrid.get("global_direct_factor_count") == 0
            and operator_inventory.get("global_A_materialized") is False
            and operator_inventory.get("matrix_free") is True
            and operator_inventory.get("p6_direct_factor_count") == 0
            and telemetry.get("global_operator_contract") is True
            and pc_inventory.get("global_A_materialized") is False
            and pc_inventory.get("borrowed_local_factor_count") == 2
            and pc_inventory.get("pc_owned_local_factor_count") == 0
            and all(
                pc_inventory.get(f"{side}_{kind}_factor_count")
                == expected_factors[side][index]
                for side in ("bottom", "top")
                for kind, index in (("direct", 0), ("ilu", 1))
            )
            and telemetry.get("pc_inventory_pass") is True
        )
        outer_release = raw_release_records.get("outer")
        outer_destroy_complete = bool(
            isinstance(outer_release, dict)
            and outer_release.get("outer_rhs_destroy_call_completed") is True
            and outer_release.get("action_matrix_destroy_call_completed") is True
            and outer_release.get("action_context_destroyed") is True
        )
        release_recomputed = bool(
            outer_destroy_complete
            and all(
                side_release_recomputed.get(side) is True for side in ("bottom", "top")
            )
        )
        release_contract &= bool(
            isinstance(outer_release, dict)
            and outer_destroy_complete is True
            and outer_release.get("destroy_calls_complete") is outer_destroy_complete
            and release_recomputed is True
            and telemetry.get("release_pass") is release_recomputed
        )
        contract = bool(
            callback_contract
            and factor_contract
            and modal_contract
            and global_contract
            and online_contract
            and release_contract
            and telemetry.get("factor_identity_pass") is True
            and telemetry.get("modal_schur_contract_pass") is True
            and gates.get("v2_fixed_callback_certificate") is callback_contract
            and gates.get("v2_modal_schur") is modal_contract
            and gates.get("v2_online_apply_counts") is online_contract
            and gates.get("v2_factor_identity") is factor_contract
            and gates.get("v2_global_operator") is global_contract
            and gates.get("v2_pc_inventory") is True
            and gates.get("v2_release") is release_contract
            and gates.get("v2_integration_pass") is True
            and qualification.get("integration_pass") is True
        )

        history = screen.get("history")
        finite_history = isinstance(history, list) and bool(history)
        residuals: list[float] = []
        history_iterations: list[float] = []
        history_pc_apply_counts: list[int] = []
        history_bottom_action_apply_counts: list[int] = []
        history_top_action_apply_counts: list[int] = []
        if finite_history:
            for row in history:
                if not isinstance(row, dict):
                    finite_history = False
                    break
                values = [
                    row.get(key)
                    for key in (
                        "reported_relative_residual",
                        "global_true_relative_residual",
                        "bottom_true_relative_residual",
                        "top_true_relative_residual",
                        "modal_true_relative_residual",
                    )
                ]
                if not all(
                    _v2_finite_number(value) and float(value) >= 0.0 for value in values
                ):
                    finite_history = False
                    break
                if not _v2_finite_number(row.get("iteration")) or not _v2_finite_number(
                    row.get("elapsed_seconds")
                ):
                    finite_history = False
                    break
                count_values = [
                    row.get("pc_apply_count"),
                    row.get("bottom_action_apply_count"),
                    row.get("top_action_apply_count"),
                ]
                if not all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in count_values
                ):
                    finite_history = False
                    break
                history_iterations.append(float(row["iteration"]))
                residuals.append(float(row["global_true_relative_residual"]))
                history_pc_apply_counts.append(row["pc_apply_count"])
                history_bottom_action_apply_counts.append(
                    row["bottom_action_apply_count"]
                )
                history_top_action_apply_counts.append(row["top_action_apply_count"])
        iterations = screen.get("iterations")
        reason = screen.get("converged_reason")
        screen_contract = bool(
            isinstance(iterations, int)
            and not isinstance(iterations, bool)
            and 0 <= iterations <= max_it
            and isinstance(reason, int)
            and not isinstance(reason, bool)
            and finite_history
            and history_iterations[-1] == float(iterations)
            and all(
                current >= previous
                for previous, current in zip(history_iterations, history_iterations[1:])
            )
            and screen.get("profile") == profile
            and screen.get("max_it") == max_it
            and screen.get("restart") == 90
            and screen.get("rtol") == 1.0e-6
            and screen.get("atol") == 0.0
            and screen.get("zero_initial") is True
        )
        online_after_by_side = {
            side: sides[side].get("online_apply", {}).get("after")
            for side in ("bottom", "top")
        }
        history_apply_contract = bool(
            finite_history
            and history_pc_apply_counts[-1] == pc_apply_count
            and history_bottom_action_apply_counts[-1] == online_after_by_side["bottom"]
            and history_top_action_apply_counts[-1] == online_after_by_side["top"]
        )
        contract = bool(contract and history_apply_contract)
        if screen_contract:
            final = residuals[-1]
            minimum = min(residuals)
            window_size = 5 if max_it == 20 else 40
            window = residuals[-window_size:]
            descending = len(window) >= 2 and window[-1] < window[0]
            boundary_or_earlier = bool(
                iterations == max_it or (iterations < max_it and reason > 0)
            )
            if max_it == 20:
                numeric = (
                    boundary_or_earlier
                    and final < 0.35
                    and minimum < 0.35
                    and descending
                )
            elif max_it == 100:
                numeric = (
                    boundary_or_earlier
                    and final <= 0.12
                    and minimum <= 0.12
                    and descending
                )
            else:
                predicted = None
                predicted_wall = None
                if final <= 1.0e-6:
                    predicted = iterations
                    predicted_wall = float(history[-1]["elapsed_seconds"])
                elif descending and len(window) >= 2:
                    x = [float(row["iteration"]) for row in history[-len(window) :]]
                    y = [
                        math.log(
                            max(float(row["global_true_relative_residual"]), 1.0e-300)
                        )
                        for row in history[-len(window) :]
                    ]
                    x_mean = sum(x) / len(x)
                    y_mean = sum(y) / len(y)
                    denominator = sum((value - x_mean) ** 2 for value in x)
                    slope = (
                        sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y))
                        / denominator
                        if denominator > 0.0
                        else 0.0
                    )
                    if slope < 0.0 and final > 0.0 and denominator > 0.0:
                        predicted = int(
                            math.ceil(
                                x[-1] + (math.log(1.0e-6) - math.log(final)) / slope
                            )
                        )
                        elapsed = [
                            float(row["elapsed_seconds"])
                            for row in history[-len(window) :]
                        ]
                        elapsed_mean = sum(elapsed) / len(elapsed)
                        wall_slope = (
                            sum(
                                (xv - x_mean) * (tv - elapsed_mean)
                                for xv, tv in zip(x, elapsed)
                            )
                            / denominator
                        )
                        predicted_wall = elapsed[-1] + max(
                            predicted - int(x[-1]), 0
                        ) * max(wall_slope, 0.0)
                numeric = (
                    boundary_or_earlier
                    and final <= 0.05
                    and minimum <= 0.05
                    and descending
                    and predicted is not None
                    and predicted_wall is not None
                    and predicted <= 3000
                )
        else:
            numeric = False
        raw_contract = bool(contract and screen_contract)
        numeric = bool(raw_contract and finite_history and numeric)
        if (
            gates.get("v2_screen") is not numeric
            or gates.get("v2_worker_numerical_pass") is not numeric
        ):
            return False
        expected_status = (
            "task037b_v2_screen_pass"
            if numeric
            else "task037b_v2_screen_numerical_negative"
        )
        expected_disposition = "screen_pass" if numeric else "screen_numerical_negative"
        if (
            record.get("status") != expected_status
            or qualification.get("worker_numerical_pass") is not numeric
            or qualification.get("disposition") != expected_disposition
        ):
            return False
        return bool(numeric if require_numerical_pass else raw_contract)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        ZeroDivisionError,
    ):
        return False


_TASK037B_V3_PASS = "DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW"
_TASK037B_V3_SLOW = "DOUBLE_APPROXIMATE_SLOW_CONTRACTION_AWAITING_REVIEW"
_TASK037B_V3_NEGATIVE = "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE"
_TASK037B_V3_IMPLEMENTATION = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"


def _task037b_v3_resource_classification(
    process_tree_peak_mb: float | int | None,
) -> dict[str, Any]:
    """Classify V3 process-tree measurement without changing numeric status."""

    present = bool(
        _v2_finite_number(process_tree_peak_mb) and float(process_tree_peak_mb) >= 0.0
    )
    peak_mb = float(process_tree_peak_mb) if present else None
    peak_gib = None if peak_mb is None else peak_mb / 1024.0
    return {
        "process_tree_peak_mb": peak_mb,
        "process_tree_peak_gib": peak_gib,
        "resource_threshold_gib": 6.0,
        "engineering_threshold_gib": 5.0,
        "stretch_threshold_gib": 3.77,
        "measurement_present": present,
        "resource_positive": bool(present and peak_gib <= 6.0),
        "engineering_positive": bool(present and peak_gib <= 5.0),
        "stretch_positive": bool(present and peak_gib <= 3.77),
        "resource_review": bool(present and peak_gib > 6.0),
        "measurement_failure": not present,
    }


def _task037b_v3_evaluate_record(record: dict[str, Any]) -> dict[str, Any]:
    """Independently recompute the V3 raw contract and classification."""

    result = {
        "contract_pass": False,
        "numerical_pass": False,
        "disposition": _TASK037B_V3_IMPLEMENTATION,
        "status": "task037b_v3_implementation_gate_failed",
        "bounded_convergence": False,
        "reported_true_agree": False,
        "prediction_sample_count": 0,
        "prediction_q_fit": None,
        "failures": ["record_contract_not_evaluated"],
    }

    def finite(value: Any) -> bool:
        return _v2_finite_number(value) and float(value) >= 0.0

    def nonnegative_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    try:
        if not isinstance(record, dict):
            return result
        case = record.get("case")
        screen = record.get("screen")
        telemetry = record.get("v3_telemetry")
        gates = record.get("gates")
        qualification = record.get("qualification")
        hybrid = record.get("hybrid_system")
        validation = record.get("validation")
        physical = record.get("physical_field_reconstruction")
        if not all(
            isinstance(item, dict)
            for item in (
                case,
                screen,
                telemetry,
                gates,
                qualification,
                hybrid,
                validation,
                physical,
            )
        ):
            return result

        official_keys = (
            "R",
            "T",
            "A",
            "A_volume",
            "orders",
            "external_diffraction_orders",
            "field",
            "12_plus_12",
            "Full3D",
            "full3d_comparison",
        )
        official_output_keys = (
            "R",
            "T",
            "A",
            "A_volume",
            "orders",
            "field",
            "12_plus_12",
            "Full3D",
        )
        validation_outputs = validation.get("official_outputs")
        telemetry_outputs = telemetry.get("official_outputs")
        official_boundary = bool(
            record.get("schema_version") == 1
            and record.get("record_schema")
            == "task037b.v3-progressive-block-pc-screen.v1"
            and record.get("benchmark_id") == "task037b_v3_progressive_block_pc_screen"
            and record.get("official_record") is False
            and validation.get("official_record") is False
            and qualification.get("official_record") is False
            and physical.get("status") == "not_run"
            and all(validation.get(key) == "not_run" for key in official_keys)
            and isinstance(validation_outputs, dict)
            and all(
                validation_outputs.get(key) == "not_run" for key in official_output_keys
            )
            and isinstance(telemetry_outputs, dict)
            and all(
                telemetry_outputs.get(key) == "not_run" for key in official_output_keys
            )
        )
        case_contract = bool(
            case.get("degree") == 6
            and math.isclose(float(case.get("h_nm")), 10.0)
            and case.get("modal_degree") == 6
            and math.isclose(float(case.get("modal_h_nm")), 10.0)
            and case.get("requested_modes") == 120
            and case.get("candidate_modes") == 240
            and math.isclose(float(case.get("wavelength_nm")), 13.5)
            and case.get("mpi_size") == 8
            and case.get("polarization_kind") == "s"
            and math.isclose(float(case.get("incident_grazing_deg")), 10.0)
            and math.isclose(float(case.get("bottom_interface_nm")), 10.0)
            and math.isclose(float(case.get("top_interface_nm")), 110.0)
            and case.get("solver_path") == "block-ldu-action-screen"
            and case.get("internal_propagation_model") == "full3d_uniform_cg"
            and case.get("internal_traction_model") == "scalar_cg_discrete_derivative"
            and case.get("stage4_full3d_assembly_backend")
            == "assembly_time_static_condensed"
            and case.get("v3_gate") is True
        )
        screen_contract = bool(
            screen.get("profile") == "double"
            and screen.get("max_it") == 200
            and screen.get("restart") == 90
            and math.isclose(float(screen.get("rtol")), 1.0e-6)
            and math.isclose(float(screen.get("atol")), 0.0)
            and screen.get("zero_initial") is True
            and screen.get("outer_solver") == "fgmres"
            and screen.get("pc_side") == "right"
        )
        telemetry_identity = bool(
            telemetry.get("task037b_v3_gate") is True
            and telemetry.get("profile") == "double"
            and telemetry.get("max_it") == 200
            and telemetry.get("ordinary_default_changed") is False
            and qualification.get("task037b_v3_gate") is True
            and qualification.get("profile") == "double"
            and qualification.get("max_it") == 200
        )

        history = screen.get("history")
        iterations = screen.get("iterations")
        reason = screen.get("converged_reason")
        history_contract = bool(
            isinstance(history, list)
            and history
            and nonnegative_int(iterations)
            and iterations <= 200
            and isinstance(reason, int)
            and not isinstance(reason, bool)
            and [row.get("iteration") for row in history] == list(range(iterations + 1))
        )
        reported_true_agree = True
        residuals: list[float] = []
        pc_counts: list[int] = []
        bottom_counts: list[int] = []
        top_counts: list[int] = []
        if history_contract:
            for row in history:
                if not isinstance(row, dict):
                    history_contract = False
                    break
                row_values = [
                    row.get(key)
                    for key in (
                        "reported_relative_residual",
                        "global_true_relative_residual",
                        "bottom_true_relative_residual",
                        "top_true_relative_residual",
                        "modal_true_relative_residual",
                    )
                ]
                if not all(finite(value) for value in row_values):
                    history_contract = False
                    break
                reported = float(row_values[0])
                true = float(row_values[1])
                reported_true_agree &= bool(
                    abs(reported - true) <= 1.0e-6 * max(reported, true)
                )
                counts = [
                    row.get("pc_apply_count"),
                    row.get("bottom_action_apply_count"),
                    row.get("top_action_apply_count"),
                ]
                if not all(nonnegative_int(value) for value in counts):
                    history_contract = False
                    break
                residuals.append(true)
                pc_counts.append(counts[0])
                bottom_counts.append(counts[1])
                top_counts.append(counts[2])
        result["reported_true_agree"] = reported_true_agree
        inventory_before = screen.get("inventory_before_release")
        pc_apply_count = (
            inventory_before.get("pc_apply_count")
            if isinstance(inventory_before, dict)
            else None
        )
        count_contract = bool(
            nonnegative_int(pc_apply_count)
            and history_contract
            and pc_counts[-1] == pc_apply_count
        )
        sides = telemetry.get("sides")
        certificates = telemetry.get("fixed_callback_certificates")
        factor_identity = telemetry.get("factor_identity")
        if not all(
            isinstance(item, dict) for item in (sides, certificates, factor_identity)
        ):
            return result
        callback_contract = True
        factor_contract = True
        online_contract = True
        release_contract = True
        raw_release_records = telemetry.get("release_records")
        if not isinstance(raw_release_records, dict):
            return result
        side_release_recomputed: dict[str, bool] = {}
        for side in ("bottom", "top"):
            side_record = sides.get(side)
            cert = certificates.get(side)
            identity = factor_identity.get(side)
            if not isinstance(side_record, dict) or not isinstance(identity, dict):
                return result
            factor_contract &= bool(
                identity.get("direct_factor_count") == 0
                and identity.get("ilu_factor_count") == 1
                and identity.get("borrowed_local_factor_count") == 1
            )
            if not isinstance(cert, dict):
                callback_contract = False
            else:
                woodbury = cert.get("woodbury")
                callback_contract &= bool(
                    finite(cert.get("wrapper_vs_internal_woodbury_error"))
                    and float(cert["wrapper_vs_internal_woodbury_error"]) <= 1.0e-12
                    and finite(cert.get("linearity_error"))
                    and float(cert["linearity_error"]) <= 1.0e-12
                    and finite(cert.get("determinism_error"))
                    and float(cert["determinism_error"]) <= 1.0e-14
                    and cert.get("repeat_hash_equal") is True
                    and isinstance(woodbury, dict)
                    and woodbury.get("K_rank") == 40
                    and finite(woodbury.get("K_condition_number"))
                    and float(woodbury["K_condition_number"]) <= 1.0e6
                    and woodbury.get("arrays_finite") is True
                    and cert.get("base_factor_count") == 1
                    and cert.get("local_direct_factor_count") == 0
                    and cert.get("nested_ksp_created") is False
                    and nonnegative_int(cert.get("apply_count_before"))
                    and nonnegative_int(cert.get("apply_count_after"))
                    and nonnegative_int(cert.get("apply_count_increment"))
                    and cert["apply_count_after"] - cert["apply_count_before"]
                    == cert["apply_count_increment"]
                    == 7
                )
            online = side_record.get("online_apply")
            online_contract &= bool(
                isinstance(online, dict)
                and nonnegative_int(online.get("before"))
                and nonnegative_int(online.get("after"))
                and nonnegative_int(online.get("increment"))
                and nonnegative_int(online.get("expected_increment"))
                and online["after"] - online["before"]
                == online["increment"]
                == online["expected_increment"]
                == 2 * pc_apply_count
                and side_record.get("borrowed_action_survives_after_screen") is True
            )
            release = raw_release_records.get(side)
            side_release = side_record.get("release_records")
            side_release_recomputed[side] = bool(
                isinstance(release, dict)
                and isinstance(release.get("woodbury"), dict)
                and isinstance(release["woodbury"].get("after"), dict)
                and release["woodbury"]["after"].get("destroyed") is True
                and isinstance(release.get("fixed_base"), dict)
                and isinstance(release["fixed_base"].get("after"), dict)
                and release["fixed_base"]["after"].get("destroyed") is True
                and isinstance(release.get("components"), dict)
                and release["components"].get("destroyed") is True
            )
            release_contract &= bool(
                side_release_recomputed[side] is True
                and isinstance(side_release, dict)
                and side_release == release
                and release.get("release_pass") is True
                and side_record.get("release_pass") is True
            )
        if history_contract:
            online_after = {
                side: sides[side].get("online_apply", {}).get("after")
                for side in ("bottom", "top")
            }
            count_contract &= bool(
                bottom_counts[-1] == online_after["bottom"]
                and top_counts[-1] == online_after["top"]
            )
        modal = telemetry.get("modal_schur")
        modal_contract = bool(
            isinstance(modal, dict)
            and modal.get("shape") == [240, 240]
            and modal.get("rank") == 240
            and modal.get("dtype") == "complex128"
            and modal.get("finite") is True
            and finite(modal.get("condition"))
            and float(modal["condition"]) <= 1.0e6
            and modal.get("normal_equations") is False
            and finite(modal.get("matrix_repeat_error"))
            and float(modal["matrix_repeat_error"]) <= 1.0e-12
            and finite(modal.get("lu_repeat_solve_error"))
            and float(modal["lu_repeat_solve_error"]) <= 1.0e-12
            and isinstance(modal.get("build_apply_count"), dict)
            and modal["build_apply_count"].get("bottom") == 480
            and modal["build_apply_count"].get("top") == 480
        )
        operator = telemetry.get("global_operator_inventory")
        pc_inventory = telemetry.get("pc_setup_inventory")
        hybrid_inventory = hybrid.get("operator_inventory")
        global_contract = bool(
            isinstance(operator, dict)
            and isinstance(pc_inventory, dict)
            and isinstance(hybrid_inventory, dict)
            and operator.get("global_A_materialized") is False
            and operator.get("matrix_free") is True
            and operator.get("p6_direct_factor_count") == 0
            and hybrid.get("global_A_materialized") is False
            and hybrid.get("global_direct_factor_count") == 0
            and pc_inventory.get("global_A_materialized") is False
            and pc_inventory.get("pc_owned_local_factor_count") == 0
            and pc_inventory.get("borrowed_local_factor_count") == 2
            and pc_inventory.get("bottom_direct_factor_count") == 0
            and pc_inventory.get("bottom_ilu_factor_count") == 1
            and pc_inventory.get("top_direct_factor_count") == 0
            and pc_inventory.get("top_ilu_factor_count") == 1
        )
        object_contract = bool(
            all(
                isinstance(sides[side].get("object_ledger"), dict)
                and isinstance(sides[side]["object_ledger"].get("inventory"), dict)
                and sides[side]["object_ledger"]["inventory"].get(
                    "fine_global_A_materialized"
                )
                is False
                and sides[side]["object_ledger"]["inventory"].get(
                    "explicit_external_c_matrix_count"
                )
                == 0
                and sides[side]["object_ledger"]["inventory"].get(
                    "explicit_external_d_matrix_count"
                )
                == 0
                for side in ("bottom", "top")
            )
            and all(
                isinstance(certificates[side], dict)
                and certificates[side].get("nested_ksp_created") is False
                for side in ("bottom", "top")
            )
        )
        outer = raw_release_records.get("outer")
        outer_contract = bool(
            isinstance(outer, dict)
            and outer.get("outer_rhs_destroy_call_completed") is True
            and outer.get("action_matrix_destroy_call_completed") is True
            and outer.get("action_context_destroyed") is True
            and outer.get("destroy_calls_complete") is True
        )
        stage_markers = telemetry.get("stage_markers")
        required_stages = (
            "action_coupling_build_started",
            "action_coupling_build_ready",
            "bottom_approx_setup_started",
            "bottom_approx_setup_ready",
            "top_approx_setup_started",
            "top_approx_setup_ready",
            "modal_schur_build_started",
            "modal_schur_build_ready",
            "release_started",
            "release_finished",
        )
        expected_outer = [
            event
            for checkpoint, event in (
                (20, "outer_iter_20"),
                (60, "outer_iter_60"),
                (100, "outer_iter_100"),
                (200, "outer_iter_200"),
            )
            if int(iterations) >= checkpoint
        ]
        relevant_stages = [
            *required_stages[:8],
            "outer_iter_20",
            "outer_iter_60",
            "outer_iter_100",
            "outer_iter_200",
            "release_started",
            "release_finished",
        ]
        actual_relevant = (
            [stage for stage in stage_markers if stage in set(relevant_stages)]
            if isinstance(stage_markers, list)
            else []
        )
        expected_relevant = [
            *required_stages[:8],
            *expected_outer,
            "release_started",
            "release_finished",
        ]
        stage_contract = bool(actual_relevant == expected_relevant)
        contract = bool(
            official_boundary
            and case_contract
            and screen_contract
            and telemetry_identity
            and history_contract
            and reported_true_agree
            and count_contract
            and callback_contract
            and factor_contract
            and online_contract
            and modal_contract
            and global_contract
            and object_contract
            and outer_contract
            and release_contract
            and stage_contract
            and telemetry.get("ordinary_default_changed") is False
            and telemetry.get("v3_release") is True
            and gates.get("v3_fixed_callback_certificate") is callback_contract
            and gates.get("v3_modal_schur") is modal_contract
            and gates.get("v3_online_apply_counts") is online_contract
            and gates.get("v3_factor_identity") is factor_contract
            and gates.get("v3_global_operator") is global_contract
            and gates.get("v3_pc_inventory") is True
            and gates.get("v3_release") is True
            and gates.get("v3_integration_pass") is True
            and qualification.get("integration_pass") is True
        )

        final_iteration = int(iterations)
        rows_by_iteration = (
            {int(row["iteration"]): row for row in history} if history_contract else {}
        )
        progressive_stop_cause = screen.get("progressive_stop_cause")
        final_true = residuals[-1] if history_contract else math.inf
        bounded = bool(
            history_contract
            and final_iteration < 200
            and isinstance(reason, int)
            and reason > 0
            and final_true <= 1.0e-6
        )
        if bounded:
            expected_not_reached = [
                checkpoint
                for checkpoint in (
                    0,
                    1,
                    2,
                    5,
                    10,
                    20,
                    30,
                    40,
                    60,
                    80,
                    90,
                    100,
                    120,
                    150,
                    160,
                    180,
                    200,
                )
                if checkpoint > final_iteration
            ]
            gate_not_reached = screen.get("gate", {}).get(
                "not_reached_due_to_convergence"
            )
        else:
            expected_not_reached = []
            gate_not_reached = screen.get("gate", {}).get(
                "not_reached_due_to_convergence"
            )
        not_reached_contract = gate_not_reached == expected_not_reached
        hard_stop = False
        for start in range(max(0, len(residuals) - 4)):
            if len(residuals[start : start + 5]) == 5 and all(
                value > 1.25 for value in residuals[start : start + 5]
            ):
                hard_stop = True
        for start in range(max(0, len(residuals) - 5)):
            window = residuals[start : start + 6]
            if len(window) == 6 and all(window[i + 1] > window[i] for i in range(5)):
                if (
                    not residuals[start + 6 :]
                    or min(residuals[start + 6 :]) >= window[-1]
                ):
                    hard_stop = True
        reason_cause_contract = False
        if history_contract:
            if bounded:
                reason_cause_contract = progressive_stop_cause is None
            elif hard_stop:
                reason_cause_contract = bool(
                    reason == -4 and progressive_stop_cause == "v3_hard_stop"
                )
            elif final_iteration in (20, 60, 100) and reason == -4:
                reason_cause_contract = bool(
                    progressive_stop_cause == f"v3_{final_iteration}_admission_failed"
                )
            elif (
                final_iteration < 200
                and reason < 0
                and reason not in (-3, -4)
                and progressive_stop_cause is None
            ):
                reason_cause_contract = True
            elif final_iteration == 200:
                reason_cause_contract = bool(
                    progressive_stop_cause is None
                    and (reason == -3 or (reason > 0 and final_true <= 1.0e-6))
                )
        contract = bool(contract and reason_cause_contract)
        gates_numeric = {"20": False, "60": False, "100": False, "200": False}
        if 20 in rows_by_iteration:
            r10 = rows_by_iteration.get(10, {}).get("global_true_relative_residual")
            r20 = rows_by_iteration[20]["global_true_relative_residual"]
            q10_20 = (
                math.exp((math.log(r20) - math.log(r10)) / 10.0)
                if r10 and r20
                else None
            )
            gates_numeric["20"] = bool(
                r10 is not None
                and r20 < 0.65
                and r20 / max(r10, 1.0e-300) < 0.85
                and q10_20 is not None
                and q10_20 < 0.98
            )
        if 60 in rows_by_iteration:
            r40 = rows_by_iteration.get(40, {}).get("global_true_relative_residual")
            r60 = rows_by_iteration[60]["global_true_relative_residual"]
            q40_60 = (
                math.exp((math.log(r60) - math.log(r40)) / 20.0)
                if r40 and r60
                else None
            )
            gates_numeric["60"] = bool(
                r40 is not None
                and r60 < 0.30
                and r60 < r40
                and q40_60 is not None
                and q40_60 < 0.99
                and rows_by_iteration[60]["global_true_relative_residual"]
                < rows_by_iteration[41]["global_true_relative_residual"]
                if 41 in rows_by_iteration
                else False
            )
        if 100 in rows_by_iteration:
            r60 = rows_by_iteration.get(60, {}).get("global_true_relative_residual")
            r90 = rows_by_iteration.get(90, {}).get("global_true_relative_residual")
            r100 = rows_by_iteration[100]["global_true_relative_residual"]
            gates_numeric["100"] = bool(
                r60 is not None
                and r90 is not None
                and r100 <= 0.12
                and r100 < r60
                and r100 <= r90
                and rows_by_iteration[100]["global_true_relative_residual"]
                < rows_by_iteration[61]["global_true_relative_residual"]
                if 61 in rows_by_iteration
                else False
            )
        prediction_rows = [
            rows_by_iteration[i]["global_true_relative_residual"]
            for i in range(120, 201)
            if i in rows_by_iteration
        ]
        prediction_slope = None
        prediction_intercept = None
        predicted_iterations = None
        if len(prediction_rows) == 81:
            xs = list(range(120, 201))
            ys = [math.log(max(float(value), 1.0e-300)) for value in prediction_rows]
            x_mean = sum(xs) / len(xs)
            y_mean = sum(ys) / len(ys)
            denominator = sum((x - x_mean) ** 2 for x in xs)
            prediction_slope = (
                sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
            )
            prediction_intercept = y_mean - prediction_slope * x_mean
            if prediction_slope < 0.0:
                predicted_iterations = max(
                    200,
                    math.ceil(
                        (math.log(1.0e-6) - prediction_intercept) / prediction_slope
                    ),
                )
        if final_iteration == 200:
            r160 = rows_by_iteration.get(160, {}).get("global_true_relative_residual")
            r200 = rows_by_iteration.get(200, {}).get("global_true_relative_residual")
            q160_200 = (
                math.exp((math.log(r200) - math.log(r160)) / 40.0)
                if r160 and r200
                else None
            )
            gates_numeric["200"] = bool(
                len(prediction_rows) == 81
                and r160 is not None
                and r200 is not None
                and r200 <= 0.05
                and r200 < r160
                and q160_200 is not None
                and q160_200 < 0.997
                and residuals[-40] > residuals[-1]
                and prediction_slope is not None
                and prediction_slope < 0.0
                and predicted_iterations is not None
                and predicted_iterations <= 3000
            )
        admission_gate_contract = True
        if (
            final_iteration in (20, 60, 100)
            and reason == -4
            and progressive_stop_cause == f"v3_{final_iteration}_admission_failed"
        ):
            current_key = str(final_iteration)
            earlier_keys = {
                20: (),
                60: ("20",),
                100: ("20", "60"),
            }[final_iteration]
            admission_gate_contract = bool(
                not gates_numeric[current_key]
                and all(gates_numeric[key] for key in earlier_keys)
            )
        reason_cause_contract = bool(reason_cause_contract and admission_gate_contract)
        contract = bool(contract and reason_cause_contract)
        raw_gate = screen.get("gate")
        prediction_contract = True
        if final_iteration == 200:
            prediction_contract = bool(
                isinstance(raw_gate, dict)
                and raw_gate.get("prediction_interval") == [120, 200]
                and raw_gate.get("prediction_sample_count") == 81
                and prediction_slope is not None
                and prediction_intercept is not None
                and _v2_finite_number(raw_gate.get("prediction_slope"))
                and _v2_finite_number(raw_gate.get("prediction_intercept"))
                and _v2_finite_number(raw_gate.get("prediction_q_fit"))
                and math.isclose(
                    float(raw_gate["prediction_slope"]),
                    prediction_slope,
                    rel_tol=1.0e-9,
                )
                and math.isclose(
                    float(raw_gate["prediction_intercept"]),
                    prediction_intercept,
                    rel_tol=1.0e-9,
                )
                and math.isclose(
                    float(raw_gate["prediction_q_fit"]),
                    math.exp(prediction_slope),
                    rel_tol=1.0e-9,
                )
            )
            if prediction_slope is not None and prediction_slope < 0.0:
                prediction_contract &= (
                    raw_gate.get("predicted_iterations") == predicted_iterations
                )
            else:
                prediction_contract &= raw_gate.get("predicted_iterations") is None
        contract = bool(contract and not_reached_contract and prediction_contract)
        reached_gates = [
            gates_numeric[key]
            for key, checkpoint in (("20", 20), ("60", 60), ("100", 100), ("200", 200))
            if final_iteration >= checkpoint
        ]
        numerical = bool(
            contract
            and reported_true_agree
            and not hard_stop
            and prediction_contract
            and (bounded or (final_iteration == 200 and all(reached_gates)))
        )
        slow = bool(
            contract
            and not numerical
            and final_iteration == 200
            and all(gates_numeric[key] for key in ("20", "60", "100"))
            and not hard_stop
            and reported_true_agree
            and 0.05 < residuals[-1] <= 0.12
            and residuals[-40] > residuals[-1]
            and math.exp((math.log(residuals[-1]) - math.log(residuals[-41])) / 40.0)
            < 0.995
            and prediction_contract
        )
        if not contract:
            disposition = _TASK037B_V3_IMPLEMENTATION
            status = "task037b_v3_implementation_gate_failed"
        elif numerical:
            disposition = _TASK037B_V3_PASS
            status = "task037b_v3_pass"
        elif slow:
            disposition = _TASK037B_V3_SLOW
            status = "task037b_v3_slow"
        else:
            disposition = _TASK037B_V3_NEGATIVE
            status = "task037b_v3_family_negative"
        failure_names = [
            name
            for name, passed in {
                "official_boundary": official_boundary,
                "case": case_contract,
                "screen": screen_contract,
                "telemetry": telemetry_identity,
                "history": history_contract,
                "reported_true_agree": reported_true_agree,
                "counts": count_contract,
                "callback": callback_contract,
                "factor_identity": factor_contract,
                "online_counts": online_contract,
                "modal": modal_contract,
                "global_operator": global_contract,
                "object_inventory": object_contract,
                "outer_release": outer_contract,
                "release": release_contract,
                "stages": stage_contract,
                "not_reached": not_reached_contract,
                "reason_cause": reason_cause_contract,
                "prediction": prediction_contract,
            }.items()
            if not passed
        ]
        result.update(
            {
                "contract_pass": contract,
                "numerical_pass": numerical,
                "disposition": disposition,
                "status": status,
                "bounded_convergence": bounded,
                "hard_stop": hard_stop,
                "prediction_sample_count": len(prediction_rows),
                "prediction_slope": prediction_slope,
                "prediction_intercept": prediction_intercept,
                "prediction_q_fit": (
                    None if prediction_slope is None else math.exp(prediction_slope)
                ),
                "prediction_infinite": bool(
                    final_iteration == 200
                    and prediction_slope is not None
                    and prediction_slope >= 0.0
                ),
                "predicted_iterations": predicted_iterations,
                "failures": failure_names,
            }
        )
        consistency_failures = []
        if record.get("status") != status:
            consistency_failures.append("record_status_mismatch")
        if qualification.get("disposition") != disposition:
            consistency_failures.append("qualification_disposition_mismatch")
        if qualification.get("worker_numerical_pass") is not numerical:
            consistency_failures.append("qualification_worker_numerical_pass_mismatch")
        if consistency_failures:
            failure_names.extend(consistency_failures)
            result.update(
                {
                    "contract_pass": False,
                    "numerical_pass": False,
                    "disposition": _TASK037B_V3_IMPLEMENTATION,
                    "status": "task037b_v3_implementation_gate_failed",
                    "failures": failure_names,
                }
            )
            return result
        return result
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        ZeroDivisionError,
    ):
        result["failures"] = ["evaluator_exception"]
        return result


def _task037b_v3_numerical_pass(
    record: dict[str, Any], *, require_numerical_pass: bool = True
) -> bool:
    evaluation = _task037b_v3_evaluate_record(record)
    return bool(
        evaluation["numerical_pass"]
        if require_numerical_pass
        else evaluation["contract_pass"]
    )


_TASK037B_V4_PASS = "FULL_LINEAR_SOLVE_PASS_AWAITING_REVIEW"
_TASK037B_V4_SLOW = "DOUBLE_APPROXIMATE_FULL_SLOW_CONTRACTION_AWAITING_REVIEW"
_TASK037B_V4_NEGATIVE = "FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE"
_TASK037B_V4_IMPLEMENTATION = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"


def _task037b_v4_resource_classification(
    process_tree_peak_mb: float | int | None,
) -> dict[str, Any]:
    present = bool(
        _v2_finite_number(process_tree_peak_mb) and float(process_tree_peak_mb) > 0.0
    )
    peak_mb = float(process_tree_peak_mb) if present else None
    peak_gib = None if peak_mb is None else peak_mb / 1024.0
    return {
        "process_tree_peak_mb": peak_mb,
        "process_tree_peak_gib": peak_gib,
        "resource_threshold_gib": 6.0,
        "engineering_threshold_gib": 5.0,
        "stretch_threshold_gib": 3.77,
        "measurement_present": present,
        "resource_positive": bool(present and peak_gib <= 6.0),
        "engineering_positive": bool(present and peak_gib <= 5.0),
        "stretch_positive": bool(present and peak_gib <= 3.77),
        "resource_review": bool(present and peak_gib > 6.0),
        "measurement_failure": not present,
    }


def _task037b_v4_hash_bound_provenance_gate() -> dict[str, Any]:
    expected = {
        "h1_solver_record": (
            "benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/"
            "solver_record.json",
            "290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c",
        ),
        "h1_summary": (
            "benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8.json",
            "e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2",
        ),
        "v3_compact": (
            "benchmarks/cases/101_hybrid_iterative_block_solver/records/"
            "task037b_v3_double_block_pc_screen_v1.json",
            "4b04bd54e17e12cff36e42f59f97af88d2296ce74e7b90eade3fedbd199cbee1",
        ),
        "v3_solver_record": (
            "benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8/"
            "solver_record.json",
            "df54c36ccca35a79b61bbd3fcf4dde47222aae0574b5d7c09ded1444ec7fc3d0",
        ),
        "v3_summary": (
            "benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8.json",
            "49343b30ec892b9f3a06b525b1535467f70b87637f5f73daf6d499a185a608fe",
        ),
        "v3_memory_stages": (
            "benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8/"
            "memory_stages.jsonl",
            "47b4127b1bec86eb44012fbf0a906afd0710889d674e8d0aaa1b9ebadf9238ec",
        ),
        "v3_timeline": (
            "benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8/"
            "memory_timeline.csv",
            "e6eca60fd6caf35bf9a8d29bfa23a99dc1c0422d5dfe93b73db0976082173dc1",
        ),
        "v3_stdout": (
            "benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8/"
            "worker_stdout.txt",
            "5b7c57c38969540da4e49a642969e747eb84cca859b92370f05210988fa9d6bf",
        ),
    }
    observed: dict[str, Any] = {}
    failures: list[str] = []
    for name, (relative_path, expected_sha256) in expected.items():
        path = ROOT / relative_path
        observed_sha256 = _sha256(path) if path.is_file() else None
        passed = observed_sha256 == expected_sha256
        observed[name] = {
            "path": relative_path,
            "expected_sha256": expected_sha256,
            "observed_sha256": observed_sha256,
            "pass": passed,
        }
        if not passed:
            failures.append(name)
    return {
        "schema": "task037b.v4-hash-bound-provenance.v1",
        "pass": not failures,
        "failures": failures,
        "artifacts": observed,
    }


def _v4_full_fe_threshold_pass(
    full_relative: Any,
    interior_relative: Any,
    interior_max: Any,
) -> bool:
    """Apply the frozen V4 full-FE and interior recovery thresholds."""

    try:
        values = tuple(
            float(value)
            for value in (
                full_relative,
                interior_relative,
                interior_max,
            )
        )
    except (TypeError, ValueError):
        return False
    return bool(
        all(_v2_finite_number(value) and float(value) >= 0.0 for value in values)
        and values[0] <= 1.0e-6
        and values[1] <= 1.0e-8
        and values[2] <= 1.0e-8
    )


def _task037b_v4_evaluate_record(record: dict[str, Any]) -> dict[str, Any]:
    """Independently recompute the V4 numerical and lifecycle evidence."""

    result = {
        "contract_pass": False,
        "numerical_pass": False,
        "recovery_pass": False,
        "physics_pass": False,
        "disposition": _TASK037B_V4_IMPLEMENTATION,
        "failures": ["record_contract_not_evaluated"],
    }

    def finite(value: Any) -> bool:
        return _v2_finite_number(value) and float(value) >= 0.0

    def signed_finite(value: Any) -> bool:
        return _v2_finite_number(value)

    def nonnegative_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    try:
        if not isinstance(record, dict):
            return result
        case = record.get("case", {})
        solver = record.get("solver", {})
        telemetry = record.get("v4_telemetry", {})
        validation = record.get("validation")
        qualification = record.get("qualification", {})
        hybrid = record.get("hybrid_system", {})
        screen = telemetry.get("screen", {})
        history = telemetry.get("history")
        failures: list[str] = []
        case_contract = bool(
            record.get("record_schema") == "task037b.v4-full-block-pc.v1"
            and case.get("degree") == 6
            and case.get("h_nm") == 10.0
            and case.get("wavelength_nm") == 13.5
            and case.get("modal_degree") == 6
            and case.get("modal_h_nm") == 10.0
            and case.get("requested_modes") == 120
            and case.get("candidate_modes") == 240
            and case.get("external_modes_per_endcap") == 40
            and case.get("interfaces_nm") == [10.0, 110.0]
            and case.get("grazing_deg") == 10.0
            and case.get("polarization") == "s"
            and case.get("propagation_model") == "full3d_uniform_cg"
            and case.get("traction_model") == "scalar_cg_discrete_derivative"
            and case.get("assembly_backend") == "assembly_time_static_condensed"
            and case.get("mpi_size") == 8
        )
        solver_contract = bool(
            solver.get("solver_path") == "block-ldu-action-full-solve"
            and solver.get("outer_solver") == "right_fgmres"
            and solver.get("restart") == 90
            and solver.get("rtol") == 1.0e-6
            and solver.get("atol") == 0.0
            and solver.get("max_it") == 700
            and solver.get("zero_initial") is True
            and solver.get("normal_equations") is False
            and solver.get("local_inverse_solve_called") is False
            and solver.get("nested_ksp_created") is False
            and solver.get("direct_fallback") is False
        )
        official_keys = {
            "official_record",
            "R",
            "T",
            "A",
            "A_volume",
            "orders",
            "external_diffraction_orders",
            "field",
            "12_plus_12",
            "Full3D",
            "full3d_comparison",
            "candidate_sample_grid",
            "canonical_export",
        }
        official_shape_contract = bool(
            isinstance(validation, dict)
            and official_keys.issubset(validation)
            and validation.get("official_record")
            in {
                "not_run",
                "candidate_measured_not_official",
            }
        )
        if not case_contract:
            failures.append("case_contract")
        if not solver_contract:
            failures.append("solver_contract")

        required_residual_keys = (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        )
        screen_history_contract = False
        iterations = screen.get("iterations")
        if (
            isinstance(history, list)
            and history
            and nonnegative_int(iterations)
            and int(iterations) <= 700
        ):
            expected_iterations = list(range(int(iterations) + 1))
            actual_iterations = [row.get("iteration") for row in history]
            screen_history_contract = bool(
                actual_iterations == expected_iterations
                and all(
                    isinstance(row, dict)
                    and all(finite(row.get(key)) for key in required_residual_keys)
                    and all(
                        nonnegative_int(row.get(key))
                        for key in (
                            "pc_apply_count",
                            "bottom_action_apply_count",
                            "top_action_apply_count",
                        )
                    )
                    for row in history
                )
            )
        final_row_contract = False
        checkpoint_contract = False
        last90_roundoff = None
        last90_no_rebound = False
        if screen_history_contract:
            final_row = history[-1]
            final_blocks = screen.get("block_relative_residuals", {})
            final_row_contract = bool(
                isinstance(final_blocks, dict)
                and finite(screen.get("final_reported_relative_residual"))
                and finite(screen.get("final_true_relative_residual"))
                and finite(final_blocks.get("bottom"))
                and finite(final_blocks.get("top"))
                and finite(final_blocks.get("modal"))
                and screen.get("final_reported_relative_residual")
                == final_row["reported_relative_residual"]
                and screen.get("final_true_relative_residual")
                == final_row["global_true_relative_residual"]
                and final_blocks.get("bottom")
                == final_row["bottom_true_relative_residual"]
                and final_blocks.get("top") == final_row["top_true_relative_residual"]
                and final_blocks.get("modal")
                == final_row["modal_true_relative_residual"]
            )
            fixed_checkpoints = {
                0,
                1,
                2,
                5,
                10,
                20,
                40,
                60,
                80,
                90,
                100,
                120,
                150,
                180,
                200,
                270,
                360,
                450,
                540,
                630,
                700,
            }
            required_checkpoints = {
                checkpoint
                for checkpoint in fixed_checkpoints
                if checkpoint <= int(iterations)
            }
            required_checkpoints.add(int(iterations))
            checkpoint_rows = telemetry.get("checkpoints")
            checkpoint_iterations = (
                [row.get("iteration") for row in checkpoint_rows]
                if isinstance(checkpoint_rows, list)
                else []
            )
            history_by_iteration = {row["iteration"]: row for row in history}
            checkpoint_value_keys = required_residual_keys + (
                "pc_apply_count",
                "bottom_action_apply_count",
                "top_action_apply_count",
            )
            checkpoint_matches_history = bool(
                isinstance(checkpoint_rows, list)
                and all(
                    isinstance(row, dict)
                    and row.get("iteration") in history_by_iteration
                    and all(
                        row.get(key) == history_by_iteration[row["iteration"]].get(key)
                        for key in checkpoint_value_keys
                    )
                    for row in checkpoint_rows
                )
            )
            checkpoint_contract = bool(
                isinstance(checkpoint_rows, list)
                and len(checkpoint_iterations) == len(set(checkpoint_iterations))
                and all(
                    isinstance(row, dict)
                    and nonnegative_int(row.get("iteration"))
                    and int(row["iteration"]) <= int(iterations)
                    and all(finite(row.get(key)) for key in required_residual_keys)
                    and all(
                        nonnegative_int(row.get(key))
                        for key in (
                            "pc_apply_count",
                            "bottom_action_apply_count",
                            "top_action_apply_count",
                        )
                    )
                    for row in checkpoint_rows
                )
                and required_checkpoints.issubset(set(checkpoint_iterations))
                and checkpoint_matches_history
            )
            last90_values = [
                float(row["global_true_relative_residual"]) for row in history[-90:]
            ]
            last90_roundoff = (
                1024.0
                * sys.float_info.epsilon
                * max(
                    max((abs(value) for value in last90_values), default=0.0),
                    1.0e-30,
                )
            )
            last90_no_rebound = bool(
                len(last90_values) >= 2
                and all(
                    right <= left + last90_roundoff
                    for left, right in zip(last90_values, last90_values[1:])
                )
            )
        roundoff_contract = bool(
            last90_roundoff is not None
            and finite(screen.get("last90_roundoff_tolerance"))
            and math.isclose(
                float(screen["last90_roundoff_tolerance"]),
                float(last90_roundoff),
                rel_tol=1.0e-12,
                abs_tol=1.0e-30,
            )
        )
        screen_contract = bool(
            screen_history_contract
            and screen.get("converged_reason") is not None
            and solver.get("restart") == 90
            and solver.get("rtol") == 1.0e-6
            and solver.get("atol") == 0.0
            and solver.get("zero_initial") is True
            and solver.get("max_it") == 700
            and screen.get("iterations") == len(history) - 1
            and int(iterations) <= 700
            and final_row_contract
            and checkpoint_contract
            and roundoff_contract
        )
        if not screen_contract:
            failures.append("screen_history_contract")
        if not checkpoint_contract:
            failures.append("checkpoint_contract")
        if not roundoff_contract:
            failures.append("roundoff_contract")

        callback_contract = True
        callbacks = telemetry.get("fixed_callback")
        if not isinstance(callbacks, dict):
            callback_contract = False
        else:
            for side in ("bottom", "top"):
                certificate = callbacks.get(side, {})
                woodbury = certificate.get("woodbury", {})
                side_pass = bool(
                    isinstance(certificate, dict)
                    and finite(certificate.get("wrapper_vs_internal_woodbury_error"))
                    and certificate["wrapper_vs_internal_woodbury_error"] <= 1.0e-12
                    and finite(certificate.get("linearity_error"))
                    and certificate["linearity_error"] <= 1.0e-12
                    and finite(certificate.get("determinism_error"))
                    and certificate["determinism_error"] <= 1.0e-14
                    and certificate.get("repeat_hash_equal") is True
                    and woodbury.get("K_rank") == 40
                    and finite(woodbury.get("K_condition_number"))
                    and woodbury["K_condition_number"] <= 1.0e6
                    and woodbury.get("arrays_finite") is True
                    and certificate.get("base_factor_count") == 1
                    and certificate.get("local_direct_factor_count") == 0
                    and certificate.get("nested_ksp_created") is False
                    and certificate.get("apply_count_increment") == 7
                )
                callback_contract = bool(callback_contract and side_pass)
        if not callback_contract:
            failures.append("fixed_callback_contract")

        modal = telemetry.get("modal_schur", {})
        modal_contract = bool(
            isinstance(modal, dict)
            and modal.get("shape") == [240, 240]
            and modal.get("dtype") == "complex128"
            and modal.get("rank") == 240
            and modal.get("normal_equations") is False
            and finite(modal.get("condition"))
            and modal["condition"] <= 1.0e8
            and finite(modal.get("matrix_repeat_error"))
            and modal["matrix_repeat_error"] <= 1.0e-12
            and finite(modal.get("lu_repeat_solve_error"))
            and modal["lu_repeat_solve_error"] <= 1.0e-12
            and isinstance(modal.get("build_apply_count"), dict)
            and modal["build_apply_count"].get("bottom") == 480
            and modal["build_apply_count"].get("top") == 480
        )
        if not modal_contract:
            failures.append("modal_schur_contract")

        pc_inventory = telemetry.get("pc_setup_inventory", {})
        global_inventory = hybrid.get("global_operator_inventory", {})
        object_ledger = hybrid.get("object_ledger", {})
        inventory_contract = bool(
            isinstance(pc_inventory, dict)
            and pc_inventory.get("global_A_materialized") is False
            and pc_inventory.get("borrowed_local_factor_count") == 2
            and pc_inventory.get("pc_owned_local_factor_count") == 0
            and pc_inventory.get("bottom_direct_factor_count") == 0
            and pc_inventory.get("top_direct_factor_count") == 0
            and pc_inventory.get("bottom_ilu_factor_count") == 1
            and pc_inventory.get("top_ilu_factor_count") == 1
            and hybrid.get("global_direct_factor_count") == 0
            and hybrid.get("global_A_materialized") is False
            and isinstance(global_inventory, dict)
            and global_inventory.get("matrix_free") is True
            and global_inventory.get("bottom_global_F_materialized") is False
            and global_inventory.get("top_global_F_materialized") is False
            and global_inventory.get("explicit_external_c_matrix_count") == 0
            and global_inventory.get("explicit_external_d_matrix_count") == 0
            and all(
                isinstance(object_ledger.get(side), dict)
                and isinstance(object_ledger[side].get("action_system_inventory"), dict)
                and object_ledger[side]["action_system_inventory"].get(
                    "fine_global_A_materialized"
                )
                is False
                for side in ("bottom", "top")
            )
        )
        if not inventory_contract:
            failures.append("outer_ready_inventory")

        restart_basis = telemetry.get("restart_basis_bytes", {})
        rows_by_rank = (
            restart_basis.get("rows_by_rank")
            if isinstance(restart_basis, dict)
            else None
        )
        bytes_by_rank = (
            restart_basis.get("bytes_by_rank")
            if isinstance(restart_basis, dict)
            else None
        )
        restart_basis_contract = bool(
            isinstance(restart_basis, dict)
            and restart_basis.get("derived_estimate") is True
            and restart_basis.get("formula") == "(2*restart+1)*rows*complex128_bytes"
            and restart_basis.get("restart") == 90
            and isinstance(rows_by_rank, list)
            and isinstance(bytes_by_rank, list)
            and len(rows_by_rank) == int(case.get("mpi_size", -1))
            and len(bytes_by_rank) == len(rows_by_rank)
            and all(nonnegative_int(value) for value in rows_by_rank)
            and bytes_by_rank
            == [int((2 * 90 + 1) * rows * 16) for rows in rows_by_rank]
            and restart_basis.get("sum_rows") == sum(rows_by_rank)
            and restart_basis.get("max_rows") == max(rows_by_rank)
            and restart_basis.get("sum_bytes") == sum(bytes_by_rank)
            and restart_basis.get("max_bytes") == max(bytes_by_rank)
            and restart_basis.get("global_rows") == sum(rows_by_rank)
            and restart_basis.get("global_bytes") == sum(bytes_by_rank)
            and nonnegative_int(restart_basis.get("local_rows"))
            and restart_basis.get("local_bytes")
            == int((2 * 90 + 1) * restart_basis.get("local_rows") * 16)
        )
        if not restart_basis_contract:
            failures.append("restart_basis_contract")

        online = telemetry.get("online_apply", {})
        online_contract = bool(
            isinstance(online, dict)
            and all(
                isinstance(online.get(side), dict)
                and nonnegative_int(online[side].get("before"))
                and nonnegative_int(online[side].get("after"))
                and online[side].get("increment")
                == online[side].get("expected_increment")
                and online[side].get("increment")
                == 2 * int(telemetry.get("pc_apply_count", -1))
                for side in ("bottom", "top")
            )
        )
        if not online_contract:
            failures.append("online_apply_contract")

        release = telemetry.get("release", {})
        side_records = record.get("side_records", {})
        side_release_contract = bool(
            isinstance(release, dict)
            and isinstance(release.get("sides"), dict)
            and all(
                isinstance(release["sides"].get(side), dict)
                and release["sides"][side].get("release_pass") is True
                and isinstance(side_records.get(side), dict)
                and side_records[side].get("release_records") == release["sides"][side]
                for side in ("bottom", "top")
            )
        )
        outer = release.get("outer", {}) if isinstance(release, dict) else {}
        core_release = (
            release.get("core_solve", {}) if isinstance(release, dict) else {}
        )
        release_order = (
            outer.get("release_order", []) if isinstance(outer, dict) else []
        )
        required_release_prefix = [
            "pc_context",
            "bottom_fixed_ilu",
            "top_fixed_ilu",
            "bottom_woodbury_wklu",
            "top_woodbury_wklu",
            "action_modal_schur",
        ]
        release_order_contract = bool(
            isinstance(release_order, list)
            and all(
                release_order.index(name) < release_order.index(next_name)
                for name, next_name in zip(
                    required_release_prefix, required_release_prefix[1:]
                )
                if name in release_order and next_name in release_order
            )
            and all(name in release_order for name in required_release_prefix)
        )
        main_release = telemetry.get("main_postprocess_release", {})
        release_contract = bool(
            side_release_contract
            and isinstance(outer, dict)
            and isinstance(core_release, dict)
            and core_release.get("ksp_destroyed") is True
            and core_release.get("pc_context_destroyed") is True
            and core_release.get("action_modal_schur_retained_after_pc_destroyed")
            is True
            and core_release.get("borrowed_side_actions_retained") is True
            and outer.get("outer_rhs_destroy_call_completed") is True
            and outer.get("action_matrix_destroy_call_completed") is True
            and outer.get("action_context_destroyed") is True
            and outer.get("action_modal_schur_retained_after_pc_destroyed") is True
            and outer.get("action_modal_schur_released") is True
            and release_order_contract
            and release.get("release_pass") is True
            and isinstance(main_release, dict)
            and main_release.get("release_pass") is True
        )
        if not release_contract:
            failures.append("release_contract")

        reason = screen.get("converged_reason")
        numeric = bool(
            screen_history_contract
            and isinstance(reason, int)
            and not isinstance(reason, bool)
            and reason > 0
            and all(float(history[-1][key]) <= 1.0e-6 for key in required_residual_keys)
        )
        gates = telemetry.get("physics_gates", {})
        recovery_gates = telemetry.get("recovery_gates", {})

        def recompute_q_gate(gate: Any) -> tuple[bool, bool]:
            if not isinstance(gate, dict):
                return False, False
            relative = gate.get("relative_residual")
            finite_value = finite(relative)
            expected = bool(finite_value and float(relative) <= 1.0e-10)
            consistent = bool(
                gate.get("finite") is finite_value and gate.get("pass") is expected
            )
            return expected, consistent

        def recompute_mode_gate(gate: Any) -> tuple[bool, bool]:
            if not isinstance(gate, dict) or not isinstance(gate.get("rows"), list):
                return False, False
            rows = gate["rows"]
            keys = []
            rows_finite = True
            for row in rows:
                beta = row.get("beta") if isinstance(row, dict) else None
                row_ok = bool(
                    isinstance(row, dict)
                    and isinstance(row.get("m"), int)
                    and not isinstance(row.get("m"), bool)
                    and isinstance(row.get("n"), int)
                    and not isinstance(row.get("n"), bool)
                    and isinstance(row.get("polarization"), str)
                    and row.get("polarization") in {"s", "p"}
                    and isinstance(row.get("rayleigh_warning"), bool)
                    and isinstance(beta, (list, tuple))
                    and len(beta) == 2
                    and signed_finite(beta[0])
                    and signed_finite(beta[1])
                )
                rows_finite = bool(rows_finite and row_ok)
                if row_ok:
                    keys.append(
                        (
                            row["m"],
                            row["n"],
                            row["polarization"],
                        )
                    )
            count = len(rows)
            unique = len(keys) == len(set(keys)) if rows_finite else False
            expected = bool(count == 40 and rows_finite and unique)
            consistent = bool(
                gate.get("count") == count
                and gate.get("unique") is unique
                and gate.get("finite") is rows_finite
                and gate.get("pass") is expected
            )
            return expected, consistent

        def recompute_full_fe_gate(side: str, item: Any) -> tuple[bool, bool]:
            if not isinstance(item, dict):
                return False, False
            residual = item.get("full_operator_residual", {})
            full_relative = residual.get("linear_system_relative_residual")
            interior_relative = item.get("interior_relative_residual")
            interior_max = residual.get("eliminated_cell_interior_max_abs_residual")
            trace = item.get("trace_constraint_audit", {})
            trace_full = trace.get("full_trace_rows")
            trace_active = trace.get("active_rows")
            trace_slave = trace.get("slave_rows")
            trace_contract = bool(
                isinstance(trace, dict)
                and trace.get("status") == "exact_mpc_trace_expansion_built"
                and trace.get("constraint_applied_before_global_matrix_insertion")
                is True
                and trace.get("embedded_identity_slave_rows_allocated") is False
            )
            trace_rows = bool(
                trace_contract
                and nonnegative_int(trace_full)
                and nonnegative_int(trace_active)
                and nonnegative_int(trace_slave)
                and trace_full == trace_active + trace_slave
            )
            static_metadata = (
                object_ledger.get(side, {}).get("static_condensation", {})
                if isinstance(object_ledger.get(side), dict)
                else {}
            )
            recovered_interior_rows = (
                item.get("recovery_audit", {}).get("recovered_interior_rows")
                if isinstance(item.get("recovery_audit"), dict)
                else None
            )
            metadata_rows = bool(
                isinstance(static_metadata, dict)
                and nonnegative_int(static_metadata.get("active_trace_rows"))
                and nonnegative_int(
                    static_metadata.get("trace_rows_before_constraints")
                )
                and nonnegative_int(static_metadata.get("cell_interior_rows"))
                and trace_active == static_metadata.get("active_trace_rows")
                and trace_full == static_metadata.get("trace_rows_before_constraints")
                and recovered_interior_rows == static_metadata.get("cell_interior_rows")
            )
            trace_rows = bool(trace_rows and metadata_rows)
            recovery_audit = item.get("recovery_audit", {})
            recovery_ok = bool(
                isinstance(recovery_audit, dict)
                and recovery_audit.get("status")
                == "full_field_recovered_without_full_global_matrix"
                and recovery_audit.get("full_global_matrix_allocated") is False
                and recovery_audit.get("full_trace_matrix_allocated") is False
                and nonnegative_int(recovery_audit.get("recovered_interior_rows"))
            )
            streaming_audit = item.get("streaming_audit", {})
            streaming_ok = bool(
                isinstance(streaming_audit, dict)
                and streaming_audit.get("full_surface_mode_matrix_retained") is False
                and streaming_audit.get("full_global_matrix_allocated") is False
                and streaming_audit.get("full_effective_rhs_reassembled_once") is True
            )
            full_finite = bool(
                finite(full_relative)
                and finite(interior_relative)
                and finite(interior_max)
            )
            expected = bool(
                _v4_full_fe_threshold_pass(
                    full_relative,
                    interior_relative,
                    interior_max,
                )
                and trace_rows
                and recovery_ok
                and streaming_ok
            )
            consistent = bool(
                item.get("full_finite") is full_finite
                and item.get("trace_contract_pass") is trace_contract
                and item.get("trace_rows_pass") is trace_rows
                and item.get("recovery_audit_pass") is recovery_ok
                and item.get("streaming_pass") is streaming_ok
                and item.get("full_fe_pass") is expected
            )
            return expected, consistent

        external_recovery_pass = False
        full_fe_recovery_pass = False
        recovery_contract = True
        if numeric:
            recovery_contract = bool(
                isinstance(recovery_gates, dict)
                and all(
                    isinstance(recovery_gates.get(side), dict)
                    for side in ("bottom", "top")
                )
            )
            if recovery_contract:
                external_results = []
                full_results = []
                for side in ("bottom", "top"):
                    item = recovery_gates[side]
                    q_pass, q_consistent = recompute_q_gate(
                        item.get("external_q_identity")
                    )
                    mode_pass, mode_consistent = recompute_mode_gate(
                        item.get("mode_identity")
                    )
                    full_pass, full_consistent = recompute_full_fe_gate(side, item)
                    external_results.append(q_pass and mode_pass)
                    full_results.append(full_pass)
                    recovery_contract = bool(
                        recovery_contract
                        and q_consistent
                        and mode_consistent
                        and full_consistent
                    )
                external_recovery_pass = all(external_results)
                full_fe_recovery_pass = all(full_results)
        else:
            recovery_contract = bool(
                isinstance(recovery_gates, dict) and not recovery_gates
            )
        recovery_pass = bool(external_recovery_pass and full_fe_recovery_pass)

        def finite_complex(value: Any) -> bool:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return signed_finite(value[0]) and signed_finite(value[1])
            return signed_finite(value)

        canonical_raw = telemetry.get("canonical_export")
        canonical_pass = bool(
            isinstance(canonical_raw, dict)
            and all(
                isinstance(canonical_raw.get(side), dict)
                and isinstance(canonical_raw[side].get("roles"), dict)
                and all(
                    canonical_raw[side]["roles"].get(role, {}).get("pass") is True
                    for role in ("active_trace", "full_fe")
                )
                for side in ("bottom", "top")
            )
        )
        own_physics_pass = False
        physics_pass = False
        physics_contract = True
        if numeric and recovery_pass:
            interface_reports = gates.get("interface_e", {}).get("reports", {})
            interface_e_pass = bool(
                isinstance(interface_reports, dict)
                and all(
                    finite(
                        interface_reports.get(side, {})
                        .get("electric_tangential", {})
                        .get("relative_l2")
                    )
                    and float(
                        interface_reports.get(side, {})
                        .get("electric_tangential", {})
                        .get("relative_l2")
                    )
                    <= 5.0e-3
                    for side in ("bottom", "top")
                )
            )
            traction_reports = gates.get("exact_traction_dual", {}).get("reports", {})
            traction_pass = bool(
                isinstance(traction_reports, dict)
                and all(
                    finite(
                        traction_reports.get(f"{side}_dual", {}).get("relative_dual")
                    )
                    and float(
                        traction_reports.get(f"{side}_dual", {}).get("relative_dual")
                    )
                    <= 1.0e-8
                    for side in ("bottom", "top")
                )
            )
            own_grid = telemetry.get("own_grid", {})
            arrays = own_grid.get("arrays", {}) if isinstance(own_grid, dict) else {}
            sample_descriptor_pass = bool(
                isinstance(arrays, dict)
                and all(
                    isinstance(arrays.get(name), dict)
                    and arrays[name].get("shape") == [5, 20, 40, 3]
                    and arrays[name].get("dtype") == "complex128"
                    for name in ("E_V_per_m", "H_A_per_m")
                )
            )
            sample_finite = bool(
                gates.get("middle_interface_samples_finite") is True
                and sample_descriptor_pass
            )
            order_rows = gates.get("external_order_reports")
            if not isinstance(order_rows, list) and isinstance(validation, dict):
                order_rows = validation.get("external_diffraction_orders")
            order_fields = (
                "total_projection",
                "incident_projection",
                "outgoing_amplitude",
                "outgoing_amplitude_at_boundary",
                "power_ratio",
                "R",
                "T",
            )
            order_keys: list[tuple[Any, ...]] = []
            order_rows_finite = True
            if isinstance(order_rows, list):
                for row in order_rows:
                    row_ok = bool(
                        isinstance(row, dict)
                        and row.get("side") in {"bottom", "top"}
                        and isinstance(row.get("m"), int)
                        and not isinstance(row.get("m"), bool)
                        and isinstance(row.get("n"), int)
                        and not isinstance(row.get("n"), bool)
                        and row.get("polarization") in {"s", "p"}
                        and all(finite_complex(row.get(key)) for key in order_fields)
                    )
                    order_rows_finite = bool(order_rows_finite and row_ok)
                    if row_ok:
                        order_keys.append(
                            (
                                row["side"],
                                row["m"],
                                row["n"],
                                row["polarization"],
                            )
                        )
            orders_finite = bool(
                isinstance(order_rows, list)
                and len(order_rows) == 80
                and order_rows_finite
                and len(order_keys) == len(set(order_keys))
            )
            energy = gates.get("energy", {})
            a_volume_raw = (
                validation.get("A_volume", {}).get("A_volume_total")
                if isinstance(validation, dict)
                and isinstance(validation.get("A_volume"), dict)
                else None
            )
            r_value = validation.get("R") if isinstance(validation, dict) else None
            t_value = validation.get("T") if isinstance(validation, dict) else None
            a_value = validation.get("A") if isinstance(validation, dict) else None
            energy_values = all(
                finite(value) for value in (r_value, t_value, a_value, a_volume_raw)
            )
            closure_error = (
                float(r_value) + float(t_value) + float(a_volume_raw) - 1.0
                if energy_values
                else math.inf
            )
            balance_error = (
                float(a_value) - float(a_volume_raw) if energy_values else math.inf
            )
            energy_pass = bool(
                energy_values
                and signed_finite(closure_error)
                and signed_finite(balance_error)
                and abs(closure_error) <= 1.0e-5
                and signed_finite(energy.get("closure_error"))
                and signed_finite(energy.get("A_balance_minus_A_volume"))
                and math.isclose(
                    float(energy["closure_error"]),
                    closure_error,
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-15,
                )
                and math.isclose(
                    float(energy["A_balance_minus_A_volume"]),
                    balance_error,
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-15,
                )
            )
            own_physics_pass = bool(
                interface_e_pass
                and traction_pass
                and sample_finite
                and orders_finite
                and energy_pass
            )
            physics_pass = bool(own_physics_pass and canonical_pass)
            physics_contract = bool(
                isinstance(gates, dict)
                and gates.get("interface_e", {}).get("pass") is interface_e_pass
                and gates.get("exact_traction_dual", {}).get("pass") is traction_pass
                and gates.get("middle_interface_samples_finite") is sample_finite
                and gates.get("external_orders_finite") is orders_finite
                and gates.get("energy", {}).get("pass") is energy_pass
                and gates.get("own_physics_pass") is own_physics_pass
                and gates.get("pass") is physics_pass
            )
        else:
            physics_contract = bool(
                isinstance(gates, dict)
                and gates.get("pass") is False
                and canonical_raw in (None, {})
            )
        if not recovery_contract:
            failures.append("recovery_contract")
        if not physics_contract:
            failures.append("physics_contract")
        if telemetry.get("ordinary_default_changed") is not False:
            failures.append("ordinary_default_changed")
        official_not_run = bool(
            official_shape_contract
            and validation.get("official_record") == "not_run"
            and all(validation[key] == "not_run" for key in official_keys)
        )
        candidate_boundary = bool(
            official_shape_contract
            and validation.get("official_record") == "candidate_measured_not_official"
            and validation.get("12_plus_12") == "not_run"
            and validation.get("Full3D") == "not_run"
            and validation.get("full3d_comparison") == "not_run"
        )
        official_boundary = bool(
            official_not_run
            if (not numeric or not recovery_pass or not physics_pass)
            else candidate_boundary
        )
        if not official_boundary:
            failures.append("official_boundary")
        integration = bool(
            case_contract
            and solver_contract
            and official_boundary
            and screen_contract
            and callback_contract
            and modal_contract
            and inventory_contract
            and restart_basis_contract
            and online_contract
            and release_contract
            and recovery_contract
            and physics_contract
            and telemetry.get("ordinary_default_changed") is False
            and record.get("qualification", {}).get("integration_pass") is True
        )
        contract_pass = bool(integration)
        if not integration:
            disposition = _TASK037B_V4_IMPLEMENTATION
        elif numeric and recovery_pass and physics_pass:
            disposition = (
                "FULL_LINEAR_SOLVE_PASS_AWAITING_REVIEW_NOT_RUN_AUTHORITY_PAYLOAD_GAP"
            )
        elif numeric and recovery_pass and not physics_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_OWN_PHYSICS_GATE_FAIL"
        elif numeric and not recovery_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_RECOVERY_GATE_FAIL"
        else:
            disposition = _TASK037B_V4_NEGATIVE
        if (
            not numeric
            and int(screen.get("converged_reason", 0)) == -3
            and screen.get("iterations") == 700
        ):
            values = [
                float(row["global_true_relative_residual"]) for row in history[-90:]
            ]
            if len(values) >= 2 and values[-1] < values[0] and last90_no_rebound:
                disposition = _TASK037B_V4_SLOW
        if numeric and not recovery_pass:
            if not external_recovery_pass:
                disposition = "FULL_LINEAR_SOLVE_PASS_EXTERNAL_RECOVERY_FAIL"
            else:
                disposition = "FULL_LINEAR_SOLVE_PASS_FULL_FE_RECOVERY_FAIL"
        elif numeric and recovery_pass and not physics_pass:
            if not own_physics_pass:
                disposition = "FULL_LINEAR_SOLVE_PASS_OWN_PHYSICS_GATE_FAIL"
            else:
                disposition = "FULL_LINEAR_SOLVE_PASS_CANONICAL_GATE_FAIL"
        expected_status = (
            "task037b_v4_full_solve_awaiting_authority_payload"
            if disposition
            == "FULL_LINEAR_SOLVE_PASS_AWAITING_REVIEW_NOT_RUN_AUTHORITY_PAYLOAD_GAP"
            else "task037b_v4_full_solve_numerical_negative"
            if disposition == _TASK037B_V4_SLOW
            else "task037b_v4_external_recovery_failed"
            if disposition == "FULL_LINEAR_SOLVE_PASS_EXTERNAL_RECOVERY_FAIL"
            else "task037b_v4_full_fe_recovery_failed"
            if disposition == "FULL_LINEAR_SOLVE_PASS_FULL_FE_RECOVERY_FAIL"
            else "task037b_v4_own_physics_failed"
            if disposition == "FULL_LINEAR_SOLVE_PASS_OWN_PHYSICS_GATE_FAIL"
            else "task037b_v4_canonical_failed"
            if disposition == "FULL_LINEAR_SOLVE_PASS_CANONICAL_GATE_FAIL"
            else "task037b_v4_full_solve_numerical_negative"
            if disposition == _TASK037B_V4_NEGATIVE
            else "task037b_v4_implementation_gate_failed"
        )
        if record.get("status") != expected_status:
            failures.append("record_status_mismatch")
        if qualification.get("disposition") != disposition:
            failures.append("qualification_disposition_mismatch")
        if qualification.get("numerical_pass") is not numeric:
            failures.append("qualification_numerical_pass_mismatch")
        for field, expected in (
            ("recovery_pass", recovery_pass),
            ("own_physics_pass", own_physics_pass),
            ("canonical_pass", canonical_pass),
            ("physics_pass", physics_pass),
        ):
            if qualification.get(field) is not expected:
                failures.append(f"qualification_{field}_mismatch")
        result.update(
            {
                "contract_pass": bool(contract_pass and not failures),
                "numerical_pass": bool(contract_pass and numeric and not failures),
                "recovery_pass": recovery_pass,
                "physics_pass": physics_pass,
                "disposition": disposition,
                "status": expected_status,
                "failures": failures,
            }
        )
        return result
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        result["failures"] = ["evaluator_exception"]
        return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task033 external RSS/cgroup/swap/wall-time watchdog for one "
            "QEP or Hybrid shard."
        )
    )
    parser.add_argument("--target", choices=("qep", "hybrid"), required=True)
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--degree", type=int, choices=(1, 2, 3, 4, 6), required=True)
    parser.add_argument("--h-nm", type=float, required=True)
    parser.add_argument(
        "--modal-h-nm",
        type=float,
        help=(
            "Independent Hybrid cross-section QEP mesh size; local 3D FEM "
            "continues to use --h-nm."
        ),
    )
    parser.add_argument(
        "--modal-degree",
        type=int,
        choices=(1, 2, 3, 4, 6),
        help=(
            "Independent Hybrid cross-section QEP degree; local 3D FEM "
            "continues to use --degree."
        ),
    )
    parser.add_argument(
        "--internal-propagation-model",
        choices=("continuous_beta", "full3d_uniform_cg"),
        default="continuous_beta",
        help=(
            "Explicit Hybrid middle-segment propagation model. "
            "full3d_uniform_cg is qualified only for fixed rectangular, "
            "axis-aligned affine tensor-hexa meshes with uniform middle-z "
            "spacing, one axial h and p1-p6; nonuniform/local-h/curved/mixed "
            "meshes fail closed. The ordinary default remains continuous_beta."
        ),
    )
    parser.add_argument(
        "--internal-traction-model",
        choices=(
            "continuous_qep_beta",
            "scalar_cg_discrete_derivative",
        ),
        default="continuous_qep_beta",
        help=(
            "Explicit Hybrid traction-symbol diagnostic. "
            "scalar_cg_discrete_derivative requires full3d_uniform_cg and its "
            "same uniform-z affine-hexa qualification scope; unsupported "
            "meshes fail closed. The ordinary default remains "
            "continuous_qep_beta."
        ),
    )
    parser.add_argument(
        "--mpi-size",
        type=int,
        choices=(1, 2, 4, 8, 16, 32),
        required=True,
    )
    parser.add_argument("--requested-modes", type=int, default=8)
    parser.add_argument("--candidate-modes", type=int, default=16)
    parser.add_argument(
        "--material-kind", choices=("air", "lossy_homogeneous", "stage4_xy")
    )
    parser.add_argument(
        "--solver-path",
        choices=(
            "augmented",
            "modal-schur-fast",
            "modal-schur-memory-minimal",
            "block-ldu-exact",
            "local-inverse-qualification",
            "dtn-component-qualification",
            "f-only-local-inverse-qualification",
            "whole-endcap-ilu0-qualification",
            "dtn-woodbury-oracle-qualification",
            "dtn-woodbury-local-inverse-qualification",
            "block-ldu-action-screen",
            "block-ldu-action-full-solve",
        ),
        default="modal-schur-memory-minimal",
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=("standard_full", "assembly_time_static_condensed"),
        default="standard_full",
    )
    parser.add_argument("--compare-modal-schur", action="store_true")
    parser.add_argument(
        "--comparison-solver-path",
        choices=("fast", "minimal"),
        default="fast",
        help=(
            "Comparison builder passed to Task32. Task033 augmented comparison "
            "records must explicitly select minimal."
        ),
    )
    parser.add_argument("--bottom-interface-nm", type=float, default=10.0)
    parser.add_argument("--top-interface-nm", type=float, default=110.0)
    parser.add_argument("--graded-reference-h", type=float, choices=(5.0, 3.0))
    parser.add_argument("--graded-coarse-factor", type=float, default=2.0)
    parser.add_argument(
        "--graded-profile",
        choices=("mechanism", "conservative", "balanced", "aggressive"),
        default="mechanism",
    )
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help="Explicit same-p/h full3D descriptor for Hybrid field closure.",
    )
    parser.add_argument(
        "--full3d-reference-sha256",
        help=(
            "Expected SHA-256 of a fresh Full3D watchdog record. Required by "
            "the static-condensed Hybrid backend and by both Task035c p6/h10 "
            "backends."
        ),
    )
    parser.add_argument("--incident-grazing-deg", type=float, default=10.0)
    parser.add_argument("--polarization-kind", choices=("s", "p"), default="s")
    parser.add_argument("--m160-funnel-evidence-file", type=Path)
    parser.add_argument("--m160-funnel-evidence-sha256")
    parser.add_argument("--high-order-core-evidence-sha256")
    parser.add_argument("--high-order-core-evidence-file", type=Path)
    parser.add_argument(
        "--resource-matrix",
        type=Path,
        default=DEFAULT_RESOURCE_MATRIX,
        help=(
            "Checked Case091 resource matrix. Hybrid launches are fail-closed "
            "when the matching p/h decision cannot be verified."
        ),
    )
    parser.add_argument(
        "--task034-workstation-gate",
        action="store_true",
        help=(
            "Explicitly use the Task034 WSL dynamic workstation Gate. Task033's "
            "14 GiB Case091 policy remains unchanged when this flag is absent."
        ),
    )
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the fixed-rectangular Task035c p6/h10 "
            "M120/M160 Hybrid authority path. Ordinary defaults are unchanged."
        ),
    )
    parser.add_argument(
        "--task037b-h1-gate",
        action="store_true",
        help="Open only the frozen Task037b H1 augmented MPI8 path.",
    )
    parser.add_argument(
        "--task037b-h3-gate",
        action="store_true",
        help="Open only the frozen Task037b H3 exact block-LDU MPI8 path.",
    )
    parser.add_argument(
        "--task037b-h4-gate",
        action="store_true",
        help="Open only the frozen Task037b H4 bounded modal-block diagnostic path.",
    )
    parser.add_argument(
        "--task037b-h5-gate",
        action="store_true",
        help="Open only the frozen Task37b H5 local-inverse qualification path.",
    )
    parser.add_argument(
        "--task037b-v1-gate",
        action="store_true",
        help="Open only the frozen Task037b V1 DtN component-action path.",
    )
    parser.add_argument(
        "--task037b-v2-gate",
        action="store_true",
        help="Open only the frozen Task037b V2 bounded block-PC screen path.",
    )
    parser.add_argument(
        "--task037b-v3-gate",
        action="store_true",
        help="Open only the frozen Task037b V3 progressive double block-PC path.",
    )
    parser.add_argument(
        "--task037b-v4-gate",
        action="store_true",
        help="Open only the frozen Task037b V4 full double fixed-action path.",
    )
    parser.add_argument(
        "--task037b-v2-profile",
        choices=("bottom-approx", "top-approx", "double"),
    )
    parser.add_argument(
        "--task037b-v2-max-it",
        type=int,
        choices=(20, 100, 200),
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument(
        "--task034-workstation-resource-authority",
        type=Path,
        default=TASK034_WORKSTATION_RESOURCE_AUTHORITY,
        help="Tracked Case092 measured launch-authority record.",
    )
    parser.add_argument("--task034-workstation-resource-authority-sha256")
    parser.add_argument("--task034-adaptive-mechanism-evidence-file", type=Path)
    parser.add_argument("--task034-adaptive-mechanism-evidence-sha256")
    parser.add_argument(
        "--task034-workstation-resource-anchor",
        type=Path,
        help=(
            "Explicit p4/h5 E0 assembly watchdog record used only as the "
            "pre-E2 Task034 launch resource anchor."
        ),
    )
    parser.add_argument(
        "--task033-same-sha-anchor-requalification",
        action="store_true",
        help=(
            "Explicitly authorize one p2/h3 10/110 nm primary minimal M80/M120/M160 "
            "shard for Task033 same-SHA formal requalification. The default still "
            "reuses and does not rerun the Task032 anchor."
        ),
    )
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float, default=11.211267857142857)
    parser.add_argument("--terminate-gib", type=float, default=12.673607142857142)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default=(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
        ),
    )
    parser.add_argument("--host-environment-id", default="windows-docker-desktop")
    args = parser.parse_args(argv)
    if args.solver_path == "local-inverse-qualification" and not args.task037b_h5_gate:
        parser.error("local-inverse-qualification requires --task037b-h5-gate.")
    if args.solver_path == "dtn-component-qualification" and not args.task037b_v1_gate:
        parser.error("dtn-component-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "f-only-local-inverse-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("f-only-local-inverse-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "whole-endcap-ilu0-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("whole-endcap-ilu0-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "dtn-woodbury-oracle-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("dtn-woodbury-oracle-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error(
            "dtn-woodbury-local-inverse-qualification requires --task037b-v1-gate."
        )
    if args.solver_path == "block-ldu-action-screen" and not (
        args.task037b_v2_gate or args.task037b_v3_gate
    ):
        parser.error(
            "block-ldu-action-screen requires --task037b-v2-gate or --task037b-v3-gate."
        )
    if args.task037b_v2_gate and args.solver_path != "block-ldu-action-screen":
        parser.error(
            "--task037b-v2-gate requires --solver-path block-ldu-action-screen."
        )
    if args.task037b_v3_gate and args.solver_path != "block-ldu-action-screen":
        parser.error(
            "--task037b-v3-gate requires --solver-path block-ldu-action-screen."
        )
    if args.task037b_v4_gate and args.solver_path != "block-ldu-action-full-solve":
        parser.error(
            "--task037b-v4-gate requires --solver-path block-ldu-action-full-solve."
        )
    if args.solver_path == "block-ldu-action-full-solve" and not args.task037b_v4_gate:
        parser.error("block-ldu-action-full-solve requires --task037b-v4-gate.")
    if (
        args.task037b_v2_profile is not None or args.task037b_v2_max_it is not None
    ) and not args.task037b_v2_gate:
        parser.error("V2 profile/max-it require --task037b-v2-gate.")
    if args.task037b_v2_gate:
        if args.task037b_v2_profile is None or args.task037b_v2_max_it is None:
            parser.error(
                "V2 gate requires --task037b-v2-profile and --task037b-v2-max-it."
            )
        if args.task037b_v2_profile != "double" and args.task037b_v2_max_it != 20:
            parser.error("V2 one-sided profiles require --task037b-v2-max-it 20.")
    if args.task037b_v3_gate and (
        args.task037b_v2_profile is not None or args.task037b_v2_max_it is not None
    ):
        parser.error("V3 does not accept V2 profile/max-it options.")
    if args.task037b_v4_gate and (
        args.task037b_v2_profile is not None or args.task037b_v2_max_it is not None
    ):
        parser.error("V4 does not accept V2 profile/max-it options.")
    selected_scoped_gates = (
        args.task035c_p6_h10_gate,
        args.task037b_h1_gate,
        args.task037b_h3_gate,
        args.task037b_h4_gate,
        args.task037b_h5_gate,
        args.task037b_v1_gate,
        args.task037b_v2_gate,
        args.task037b_v3_gate,
        args.task037b_v4_gate,
    )
    if sum(bool(value) for value in selected_scoped_gates) > 1:
        parser.error(
            "Task035c p6/h10, Task037b H1, H3, H4, H5, V1, V2, V3, and V4 gates are "
            "mutually exclusive."
        )
    if args.degree == 6 and not any(selected_scoped_gates):
        parser.error(
            "p6 is fail-closed; pass a fixed scoped Task035c, Task037b H1, "
            "or Task037b H3/H4/H5/V1/V2/V3/V4 gate."
        )
    if (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ) and args.task034_workstation_gate:
        parser.error(
            "--task034-workstation-gate and the Task035c/H1/H3/H4/H5/V1/V2/V3/V4 gates "
            "are mutually exclusive."
        )
    if (
        args.mpi_size not in (1, 2, 4)
        and not args.task034_workstation_gate
        and not args.task035c_p6_h10_gate
        and not args.task037b_h1_gate
        and not args.task037b_h3_gate
        and not args.task037b_h4_gate
        and not args.task037b_h5_gate
        and not args.task037b_v1_gate
        and not args.task037b_v2_gate
        and not args.task037b_v3_gate
        and not args.task037b_v4_gate
    ):
        parser.error(
            "MPI8/16/32 require --task034-workstation-gate or the scoped "
            "Task035c p6/h10, Task037b H1/H3/H4/H5/V1/V2/V3/V4 gate."
        )
    if args.target == "qep" and args.material_kind is None:
        parser.error("--target qep requires --material-kind.")
    if args.target != "hybrid" and (
        args.modal_h_nm is not None
        or args.modal_degree is not None
        or args.internal_propagation_model != "continuous_beta"
        or args.internal_traction_model != "continuous_qep_beta"
    ):
        parser.error("Independent modal h/p and propagation options are Hybrid-only.")
    if args.modal_h_nm is not None and args.modal_h_nm <= 0.0:
        parser.error("--modal-h-nm must be positive.")
    if (
        args.internal_traction_model == "scalar_cg_discrete_derivative"
        and args.internal_propagation_model != "full3d_uniform_cg"
    ):
        parser.error(
            "scalar_cg_discrete_derivative traction requires "
            "--internal-propagation-model full3d_uniform_cg."
        )
    if args.graded_reference_h is not None and (
        args.modal_h_nm is not None or args.modal_degree is not None
    ):
        parser.error(
            "Independent modal h/p is not combined with the Task034 graded path."
        )
    if args.target == "hybrid" and args.requested_modes < 2:
        parser.error("Hybrid requested modes must be at least two.")
    static_backend = (
        args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    )
    if static_backend:
        if args.target != "hybrid":
            parser.error(
                "The static-condensed assembly backend is currently qualified "
                "only for Hybrid watchdog shards."
            )
        if args.full3d_reference is None:
            parser.error(
                "The static-condensed Hybrid backend requires a fresh same-p/h "
                "--full3d-reference."
            )
        if not _valid_hex_digest(args.full3d_reference_sha256, 64):
            parser.error(
                "The static-condensed Hybrid backend requires an explicit "
                "64-hex --full3d-reference-sha256."
            )
    elif args.full3d_reference_sha256 is not None and not (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ):
        parser.error(
            "--full3d-reference-sha256 is reserved for a scoped "
            "static-condensed Hybrid gate."
        )
    if not 0.0 < args.incident_grazing_deg < 90.0:
        parser.error("--incident-grazing-deg must lie strictly between 0 and 90.")
    if args.candidate_modes < args.requested_modes:
        parser.error("--candidate-modes must be at least --requested-modes.")
    if args.target == "hybrid" and args.candidate_modes != 2 * args.requested_modes:
        parser.error(
            "Hybrid --candidate-modes must equal exactly twice "
            "--requested-modes so Task32 can retain M forward and M backward "
            "modes."
        )
    if args.target == "qep" and args.candidate_modes < task033_left_candidate_pool_size(
        args.requested_modes
    ):
        parser.error(
            "QEP --candidate-modes must satisfy the audited adjoint-pool "
            "oversampling policy."
        )
    if args.target == "hybrid" and args.requested_modes == 240:
        if (
            args.m160_funnel_evidence_file is None
            or args.m160_funnel_evidence_sha256 is None
        ):
            parser.error(
                "Conditional M240 requires the M80/M120/M160 funnel evidence "
                "file and its raw SHA-256."
            )
    if not args.warning_gib < args.terminate_gib:
        parser.error("--warning-gib must be lower than --terminate-gib.")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be positive.")
    if args.task037b_v2_gate:
        expected_timeout = (
            7200.0
            if args.task037b_v2_profile == "double"
            and args.task037b_v2_max_it in (100, 200)
            else 3600.0
        )
        if not math.isclose(args.warning_gib, 10.0):
            parser.error("V2 watchdog warning threshold is fixed at 10 GiB.")
        if not math.isclose(args.terminate_gib, 14.0):
            parser.error("V2 watchdog termination threshold is fixed at 14 GiB.")
        if not math.isclose(args.timeout_seconds, expected_timeout):
            parser.error(
                f"V2 {args.task037b_v2_profile}/{args.task037b_v2_max_it} "
                f"timeout is fixed at {expected_timeout:g} seconds."
            )
    if args.task037b_v3_gate:
        if not math.isclose(args.warning_gib, 10.0):
            parser.error("V3 watchdog warning threshold is fixed at 10 GiB.")
        if not math.isclose(args.terminate_gib, 14.0):
            parser.error("V3 watchdog termination threshold is fixed at 14 GiB.")
        if not math.isclose(args.timeout_seconds, 7200.0):
            parser.error("V3 watchdog timeout is fixed at 7200 seconds.")
    if args.task037b_v4_gate:
        if not math.isclose(args.warning_gib, 10.0):
            parser.error("V4 watchdog warning threshold is fixed at 10 GiB.")
        if not math.isclose(args.terminate_gib, 14.0):
            parser.error("V4 watchdog termination threshold is fixed at 14 GiB.")
        if not math.isclose(args.timeout_seconds, 7200.0):
            parser.error("V4 watchdog timeout is fixed at 7200 seconds.")
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size in TASK035C_P6_H10_MPI_SIZES
            and args.requested_modes in TASK035C_P6_H10_MODE_COUNTS
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend in TASK035C_P6_H10_BACKENDS
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to WSL fixed rectangular "
                "p6/h10 S-polarized Hybrid M120/M160 on MPI1/2/4/8, explicit "
                "modal p6/h10, exact 2M pool, modal-schur-memory-minimal, "
                "the qualified discrete axial propagation/traction pair, "
                "10/110 nm interfaces, standard/static backend, and "
                "hash-bound historical and matching Full3D authorities."
            )
    elif args.task037b_v1_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path
            in (
                "dtn-component-qualification",
                "f-only-local-inverse-qualification",
                "whole-endcap-ilu0-qualification",
                "dtn-woodbury-oracle-qualification",
                "dtn-woodbury-local-inverse-qualification",
            )
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-v1-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, dtn-component-qualification, "
                "f-only-local-inverse-qualification or "
                "whole-endcap-ilu0-qualification or "
                "dtn-woodbury-oracle-qualification, "
                "dtn-woodbury-local-inverse-qualification, "
                "static-condensed MPI8 path."
            )
    elif args.task037b_h1_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "augmented"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-h1-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, augmented, static-condensed MPI8 path."
            )
    elif args.task037b_h3_gate or args.task037b_h4_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-exact"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-h3-gate/--task037b-h4-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, block-ldu-exact, static-condensed MPI8 path."
            )
    elif args.task037b_h5_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "local-inverse-qualification"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-h5-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, local-inverse-qualification, "
                "static-condensed MPI8 path."
            )
    elif args.task037b_v3_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-screen"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-v3-gate is restricted to the fixed WSL p6/h10, "
                "modal p6/h10, S-polarized 10/110 nm, full3d/scalar-CG, "
                "M120/candidate240, block-ldu-action-screen, static-condensed "
                "MPI8 path."
            )
    elif args.task037b_v4_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-full-solve"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-v4-gate is restricted to the fixed WSL p6/h10, "
                "modal p6/h10, 13.5 nm S-polarized 10/110 nm, "
                "full3d/scalar-CG, M120/candidate240, block-ldu-action-full-solve, "
                "static-condensed MPI8 path."
            )
    elif args.task037b_v2_gate:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.mpi_size == 8
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-screen"
            and args.task037b_v2_profile in {"bottom-approx", "top-approx", "double"}
            and args.task037b_v2_max_it in {20, 100, 200}
            and (args.task037b_v2_profile == "double" or args.task037b_v2_max_it == 20)
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
        )
        if not scoped:
            parser.error(
                "--task037b-v2-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm S-polarized full3d/scalar-CG static-condensed MPI8 "
                "M120/candidate240 block-ldu-action-screen path with frozen "
                "V2 profile/max-it."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
    ):
        parser.error(
            "Task035c/H1/H3/H4/H5/V1/V2/V3/V4 preflight authority arguments require a "
            "scoped gate."
        )
    if args.task033_same_sha_anchor_requalification:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 2
            and math.isclose(args.h_nm, 3.0)
            and args.requested_modes in (80, 120, 160)
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and not args.compare_modal_schur
            and args.graded_reference_h is None
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
        )
        if not scoped:
            parser.error(
                "--task033-same-sha-anchor-requalification is restricted to the "
                "uniform p2/h3 10/110 nm primary modal-schur-memory-minimal "
                "M80/M120/M160 funnel with an exact 2M candidate pool."
            )
    if args.task034_workstation_gate:
        p4_anchor_is_exclusive = bool(
            (args.full3d_reference is None)
            != (args.task034_workstation_resource_anchor is None)
        )
        p2_h1_resource_anchor_scope = bool(
            args.degree == 2
            and math.isclose(args.h_nm, 1.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        p3_h2_resource_anchor_scope = bool(
            args.degree == 3
            and math.isclose(args.h_nm, 2.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        p4_h3_resource_anchor_scope = bool(
            args.degree == 4
            and math.isclose(args.h_nm, 3.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        phase_f_matrix = {
            (2, 5.0),
            (2, 3.0),
            (2, 2.0),
            (2, 1.0),
            (3, 10.0),
            (3, 7.5),
            (3, 5.0),
            (3, 3.0),
            (3, 2.0),
            (4, 10.0),
            (4, 7.5),
            (4, 5.0),
            (4, 3.0),
        }
        anchor_selection_valid = bool(
            (
                (args.degree, args.h_nm) in phase_f_matrix
                and not (
                    args.degree == 2
                    and math.isclose(args.h_nm, 1.0)
                    or (args.degree == 3 and math.isclose(args.h_nm, 2.0))
                    or (args.degree == 4 and math.isclose(args.h_nm, 3.0))
                )
                and args.full3d_reference is not None
                and args.task034_workstation_resource_anchor is None
            )
            or (
                args.degree == 4
                and math.isclose(args.h_nm, 5.0)
                and p4_anchor_is_exclusive
            )
            or p2_h1_resource_anchor_scope
            or p3_h2_resource_anchor_scope
            or p4_h3_resource_anchor_scope
        )
        approved_p_scope = bool(
            args.polarization_kind == "p"
            and args.degree == 2
            and math.isclose(args.h_nm, 5.0)
            and args.mpi_size == 8
            and args.requested_modes == 160
        )
        approved_p2_h1_scope = bool(
            not (args.degree == 2 and math.isclose(args.h_nm, 1.0))
            or p2_h1_resource_anchor_scope
        )
        approved_p3_h2_scope = bool(
            not (args.degree == 3 and math.isclose(args.h_nm, 2.0))
            or p3_h2_resource_anchor_scope
        )
        approved_p4_h3_scope = bool(
            not (args.degree == 4 and math.isclose(args.h_nm, 3.0))
            or p4_h3_resource_anchor_scope
        )
        graded_compression_scope = bool(
            args.graded_reference_h is not None
            and args.degree == 2
            and math.isclose(args.h_nm, 3.0)
            and math.isclose(args.graded_reference_h, 3.0)
            and args.graded_profile in {"conservative", "balanced", "aggressive"}
            and args.mpi_size == 8
            and args.requested_modes in (80, 120, 160)
            and args.polarization_kind == "s"
            and args.task034_adaptive_mechanism_evidence_file is not None
            and isinstance(args.task034_adaptive_mechanism_evidence_sha256, str)
            and len(args.task034_adaptive_mechanism_evidence_sha256) == 64
        )
        scoped = bool(
            args.target == "hybrid"
            and (args.degree, args.h_nm) in phase_f_matrix
            and args.requested_modes in (80, 120, 160, 240)
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and (args.graded_reference_h is None or graded_compression_scope)
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and math.isclose(args.incident_grazing_deg, 10.0)
            and (args.polarization_kind == "s" or approved_p_scope)
            and approved_p2_h1_scope
            and approved_p3_h2_scope
            and approved_p4_h3_scope
            and anchor_selection_valid
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
            and isinstance(args.task034_workstation_resource_authority_sha256, str)
            and len(args.task034_workstation_resource_authority_sha256) == 64
        )
        if not scoped:
            parser.error(
                "--task034-workstation-gate is restricted to the Task034 fixed "
                "p2/p3/p4 Phase F matrix, WSL Hybrid M80/M120/M160 "
                "(conditional M240) funnel, exact 2M pool, a same-p/h Full-3D "
                "watchdog/descriptor reference (or an explicitly authorized "
                "assembly-only resource anchor), canonical resource authority, "
                "and WSL2-Ubuntu-24.04 identity."
                " The only P-polarized exception is the user-approved "
                "p2/h5 MPI8 M160 capability example. The p2/h1 S added point "
                "and the p3/h2 S added point are each restricted to MPI8 M160 "
                "with their candidate-specific assembly resource anchor. The "
                "p4/h3 S added point has the same MPI8 M160-only restriction."
            )
    return args


def _formal_shard_pass(
    *,
    return_code: int,
    numerical_pass: bool,
    resource_gate_pass: bool,
    source_gate_pass: bool,
    launch_gate_pass: bool,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    terminated_for_authority_unreadable: bool,
    no_swap_pass: bool = True,
) -> bool:
    """Centralize the fail-closed measured-shard promotion contract."""

    return bool(
        return_code == 0
        and numerical_pass
        and resource_gate_pass
        and source_gate_pass
        and launch_gate_pass
        and not terminated_for_memory
        and not terminated_for_timeout
        and not terminated_for_authority_unreadable
        and no_swap_pass
    )


def _task037b_r5_resource_gate(
    *,
    formal_pass: bool,
    record_complete: bool,
    numerical_pass: bool,
    process_tree_peak_mb: float | None,
) -> dict[str, Any]:
    """Classify the R5 process-tree threshold without using worker-only RSS."""

    measurement_present = bool(
        isinstance(process_tree_peak_mb, (int, float))
        and not isinstance(process_tree_peak_mb, bool)
        and math.isfinite(float(process_tree_peak_mb))
    )
    peak_mb = float(process_tree_peak_mb) if measurement_present else None
    exceeds_threshold = bool(measurement_present and peak_mb > 7.0 * 1024.0)
    resource_review = bool(
        formal_pass and numerical_pass and measurement_present and exceeds_threshold
    )
    measurement_failure = bool(formal_pass and not measurement_present)
    h6_eligible = bool(
        formal_pass
        and record_complete
        and numerical_pass
        and measurement_present
        and not exceeds_threshold
    )
    return {
        "process_tree_peak_mb": peak_mb,
        "process_tree_peak_gib": None if peak_mb is None else peak_mb / 1024.0,
        "threshold_gib": 7.0,
        "measurement_present": measurement_present,
        "exceeds_threshold": exceeds_threshold,
        "resource_review": resource_review,
        "measurement_failure": measurement_failure,
        "h6_eligible": h6_eligible,
    }


def run(args: argparse.Namespace) -> int:
    source_before = _watchdog_source_before(args.verified_clean_sha)
    environment_before = _resource_environment_snapshot()
    environment_preflight = _environment_preflight(environment_before)
    effective = effective_memory_limit()
    if args.task034_workstation_gate:
        warning_bytes = effective.get("warning_bytes")
        termination_bytes = effective.get("termination_bytes")
        if (
            type(warning_bytes) is int
            and warning_bytes > 0
            and type(termination_bytes) is int
            and termination_bytes > warning_bytes
        ):
            args.warning_gib = warning_bytes / 1024**3
            args.terminate_gib = termination_bytes / 1024**3
    finite_authorities = (
        effective.get("effective_limit_bytes"),
        environment_before.get("host_available_memory_bytes"),
    )
    environment_before["task034_effective_limit"] = effective
    args._qep_effective_limit_gib = (
        None
        if any(not isinstance(value, int) or value <= 0 for value in finite_authorities)
        else min(int(value) for value in finite_authorities) / 1024**3
    )
    source_preflight_gate = {
        "pass": source_before["source_clean_verified"],
        "failures": (
            []
            if source_before["source_clean_verified"]
            else ["pre_run_full_sha_or_complete_nonignored_worktree_clean_gate_failed"]
        ),
    }
    core_path = args.high_order_core_evidence_file
    if core_path is not None and not core_path.is_absolute():
        core_path = ROOT / core_path
    core_evidence, core_read_error = (
        _read_json_object(core_path) if args.degree >= 3 else (None, None)
    )
    core_source_compatibility = _case090_source_compatibility(
        core_evidence,
        current_source_sha=source_before.get("commit_sha"),
    )
    m160_funnel_path = args.m160_funnel_evidence_file
    if m160_funnel_path is not None and not m160_funnel_path.is_absolute():
        m160_funnel_path = ROOT / m160_funnel_path
    m160_funnel_evidence, m160_funnel_read_error = (
        _read_json_object(m160_funnel_path)
        if args.target == "hybrid" and args.requested_modes == 240
        else (None, None)
    )
    observed_m160_funnel_sha256 = (
        _sha256(m160_funnel_path) if m160_funnel_path is not None else None
    )
    if args.target == "hybrid":
        if (
            args.task035c_p6_h10_gate
            or args.task037b_h1_gate
            or args.task037b_h3_gate
            or args.task037b_h4_gate
            or args.task037b_h5_gate
            or args.task037b_v1_gate
            or args.task037b_v2_gate
            or args.task037b_v3_gate
            or args.task037b_v4_gate
        ):
            authority_path = args.task035c_p6_preflight_authority
            if authority_path is not None and not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            authority_path = (
                None if authority_path is None else authority_path.resolve()
            )
            authority, authority_read_error = _read_json_object(authority_path)
            authority_observed_sha256 = (
                None if authority_path is None else _sha256(authority_path)
            )
            try:
                authority_relative = (
                    None
                    if authority_path is None
                    else authority_path.relative_to(ROOT).as_posix()
                )
            except ValueError:
                authority_relative = None
            authority_is_tracked = bool(
                authority_relative is not None
                and _git(
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    authority_relative,
                )
                is not None
            )
            preflight_authority_gate = task035c_p6_h10_preflight_authority_gate(
                authority,
                expected_sha256=args.task035c_p6_preflight_sha256,
                observed_sha256=authority_observed_sha256,
                authority_is_tracked=authority_is_tracked,
            )

            full3d_path = args.full3d_reference
            if full3d_path is not None and not full3d_path.is_absolute():
                full3d_path = ROOT / full3d_path
            full3d_path = None if full3d_path is None else full3d_path.resolve()
            full3d_reference, full3d_reference_read_error = _read_json_object(
                full3d_path
            )
            full3d_reference_observed_sha256 = (
                None if full3d_path is None else _sha256(full3d_path)
            )
            full3d_reference_gate = (
                task037b_h1_pinned_full3d_reference_gate(
                    full3d_reference,
                    expected_sha256=args.full3d_reference_sha256,
                    observed_sha256=full3d_reference_observed_sha256,
                    current_source_sha=source_before.get("commit_sha"),
                    assembly_backend=args.stage4_full3d_assembly_backend,
                    mpi_size=args.mpi_size,
                )
                if (
                    args.task037b_h1_gate
                    or args.task037b_h3_gate
                    or args.task037b_h4_gate
                    or args.task037b_h5_gate
                    or args.task037b_v1_gate
                    or args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                )
                else task035c_p6_h10_full3d_reference_gate(
                    full3d_reference,
                    expected_sha256=args.full3d_reference_sha256,
                    observed_sha256=full3d_reference_observed_sha256,
                    current_source_sha=source_before.get("commit_sha"),
                    assembly_backend=args.stage4_full3d_assembly_backend,
                    mpi_size=args.mpi_size,
                )
            )
            checks = {
                "scoped_gate_parser_passed": bool(
                    args.task035c_p6_h10_gate
                    or args.task037b_h1_gate
                    or args.task037b_h3_gate
                    or args.task037b_h4_gate
                    or args.task037b_h5_gate
                    or args.task037b_v1_gate
                    or args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                ),
                "historical_preflight_readable": (authority_read_error is None),
                "historical_preflight_gate": preflight_authority_gate["pass"],
                "matching_full3d_reference_readable": (
                    full3d_reference_read_error is None
                ),
                "matching_full3d_reference_gate": (full3d_reference_gate["pass"]),
                "source_clean_and_exact": source_before["source_clean_verified"],
                "environment_preflight": environment_preflight["pass"],
                "external_watchdog_active": True,
            }
            failures = [name for name, passed in checks.items() if not passed]
            launch_gate = {
                "schema_version": (
                    "task037b.h4-hybrid-launch-gate.v1"
                    if args.task037b_h4_gate
                    else "task037b.v4-worker-authority-gate.v1"
                    if args.task037b_v4_gate
                    else "task037b.v2-worker-authority-gate.v1"
                    if args.task037b_v2_gate
                    else "task037b.v3-worker-authority-gate.v1"
                    if args.task037b_v3_gate
                    else "task037b.h3-hybrid-launch-gate.v1"
                    if args.task037b_h3_gate
                    else "task037b.h1-hybrid-launch-gate.v1"
                    if args.task037b_h1_gate
                    else (
                        "task037b.h5-hybrid-launch-gate.v1"
                        if args.task037b_h5_gate
                        else (
                            (
                                "task037b.v1-r3-hybrid-launch-gate.v1"
                                if args.solver_path == "whole-endcap-ilu0-qualification"
                                else "task037b.v1-r2-hybrid-launch-gate.v1"
                                if args.solver_path
                                == "f-only-local-inverse-qualification"
                                else "task037b.v1-r4-hybrid-launch-gate.v1"
                                if args.solver_path
                                == "dtn-woodbury-oracle-qualification"
                                else "task037b.v1-hybrid-launch-gate.v1"
                            )
                            if args.task037b_v1_gate
                            else "task035c.p6-h10-hybrid-launch-gate.v1"
                        )
                    )
                ),
                "pass": not failures,
                "launch_eligible_recomputed": not failures,
                "scope": (
                    "task037b_h4_fixed_block_ldu_p6_h10"
                    if args.task037b_h4_gate
                    else "task037b_v4_full_double_block_pc_p6_h10"
                    if args.task037b_v4_gate
                    else "task037b_v2_fixed_block_pc_screen_p6_h10"
                    if args.task037b_v2_gate
                    else "task037b_v3_progressive_double_block_pc_screen_p6_h10"
                    if args.task037b_v3_gate
                    else "task037b_h3_fixed_block_ldu_p6_h10"
                    if args.task037b_h3_gate
                    else "task037b_h1_fixed_augmented_p6_h10"
                    if args.task037b_h1_gate
                    else (
                        "task037b_h5_fixed_local_inverse_p6_h10"
                        if args.task037b_h5_gate
                        else (
                            (
                                "task037b_v1_r3_fixed_whole_endcap_p6_h10"
                                if args.solver_path == "whole-endcap-ilu0-qualification"
                                else "task037b_v1_r2_fixed_f_only_p6_h10"
                                if args.solver_path
                                == "f-only-local-inverse-qualification"
                                else "task037b_v1_r4_fixed_dtn_woodbury_p6_h10"
                                if args.solver_path
                                == "dtn-woodbury-oracle-qualification"
                                else "task037b_v1_fixed_dtn_component_p6_h10"
                            )
                            if args.task037b_v1_gate
                            else "task035c_fixed_rectangular_p6_h10"
                        )
                    )
                ),
                "checks": checks,
                "failures": failures,
                "historical_preflight_authority": {
                    **preflight_authority_gate,
                    "path": (None if authority_path is None else str(authority_path)),
                    "read_error": authority_read_error,
                },
                "matching_full3d_reference": {
                    **full3d_reference_gate,
                    "path": (None if full3d_path is None else str(full3d_path)),
                    "read_error": full3d_reference_read_error,
                },
                "high_order_core_evidence": {},
            }
        elif args.task034_workstation_gate:
            authority_path = args.task034_workstation_resource_authority
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            authority_path = authority_path.resolve()
            authority_is_canonical = (
                authority_path == TASK034_WORKSTATION_RESOURCE_AUTHORITY.resolve()
            )
            try:
                authority_relative = authority_path.relative_to(ROOT).as_posix()
            except ValueError:
                authority_relative = None
            authority_is_tracked = bool(
                authority_relative is not None
                and _git("ls-files", "--error-unmatch", "--", authority_relative)
                is not None
            )
            authority, authority_read_error = _read_json_object(authority_path)
            authority_observed_sha256 = _sha256(authority_path)
            historical_authority_source_compatibility = (
                _task034_authority_source_compatibility(
                    authority,
                    degree=args.degree,
                    h_nm=args.h_nm,
                    polarization_kind=args.polarization_kind,
                    current_source_sha=source_before.get("commit_sha"),
                    assembly_backend=(args.stage4_full3d_assembly_backend),
                )
            )
            full3d_path = args.full3d_reference
            if full3d_path is not None and not full3d_path.is_absolute():
                full3d_path = ROOT / full3d_path
            full3d_path = None if full3d_path is None else full3d_path.resolve()
            full3d_reference_sha256 = (
                None if full3d_path is None else _sha256(full3d_path)
            )
            fresh_static_record, fresh_static_read_error = (
                _read_json_object(full3d_path)
                if args.stage4_full3d_assembly_backend
                == "assembly_time_static_condensed"
                else (None, None)
            )
            fresh_static_anchor_gate = (
                _task035b_static_full3d_anchor_gate(
                    fresh_static_record,
                    expected_sha256=args.full3d_reference_sha256,
                    observed_sha256=full3d_reference_sha256,
                    degree=args.degree,
                    h_nm=args.h_nm,
                    mpi_size=args.mpi_size,
                    polarization_kind=args.polarization_kind,
                    current_source_sha=source_before.get("commit_sha"),
                )
                if args.stage4_full3d_assembly_backend
                == "assembly_time_static_condensed"
                else None
            )
            active_source_compatibility = (
                fresh_static_anchor_gate["source_compatibility"]
                if fresh_static_anchor_gate is not None
                else historical_authority_source_compatibility
            )
            resource_anchor_path = args.task034_workstation_resource_anchor
            if (
                resource_anchor_path is not None
                and not resource_anchor_path.is_absolute()
            ):
                resource_anchor_path = ROOT / resource_anchor_path
            resource_anchor_path = (
                None if resource_anchor_path is None else resource_anchor_path.resolve()
            )
            resource_anchor_sha256 = (
                None if resource_anchor_path is None else _sha256(resource_anchor_path)
            )
            adaptive_mechanism_path = args.task034_adaptive_mechanism_evidence_file
            if (
                adaptive_mechanism_path is not None
                and not adaptive_mechanism_path.is_absolute()
            ):
                adaptive_mechanism_path = ROOT / adaptive_mechanism_path
            adaptive_mechanism_evidence, adaptive_mechanism_error = (
                _read_json_object(adaptive_mechanism_path)
                if args.graded_reference_h is not None
                else (None, None)
            )
            adaptive_mechanism_observed_sha256 = (
                _sha256(adaptive_mechanism_path)
                if adaptive_mechanism_path is not None
                else None
            )
            adaptive_mechanism_gate = task034_adaptive_mechanism_evidence_gate(
                adaptive_mechanism_evidence,
                expected_sha256=args.task034_adaptive_mechanism_evidence_sha256,
                observed_sha256=adaptive_mechanism_observed_sha256,
                current_source_sha=source_before.get("commit_sha"),
                degree=args.degree,
                h_nm=args.h_nm,
                requested_modes=args.requested_modes,
                mpi_size=args.mpi_size,
                polarization_kind=args.polarization_kind,
                graded_reference_h=args.graded_reference_h,
                graded_profile=args.graded_profile,
            )
            core_gate = high_order_core_evidence_gate(
                args.degree,
                core_evidence,
                expected_sha256=args.high_order_core_evidence_sha256,
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=core_source_compatibility,
            )
            launch_gate = task034_workstation_hybrid_launch_gate(
                authority,
                authority_expected_sha256=(
                    args.task034_workstation_resource_authority_sha256
                ),
                authority_observed_sha256=authority_observed_sha256,
                degree=args.degree,
                h_nm=args.h_nm,
                requested_modes=args.requested_modes,
                candidate_modes=args.candidate_modes,
                solver_path=args.solver_path,
                comparison_solver_path=args.comparison_solver_path,
                bottom_interface_nm=args.bottom_interface_nm,
                top_interface_nm=args.top_interface_nm,
                incident_grazing_deg=args.incident_grazing_deg,
                polarization_kind=args.polarization_kind,
                effective_limit=effective,
                warning_gib=args.warning_gib,
                terminate_gib=args.terminate_gib,
                core_gate=core_gate,
                mpi_size=args.mpi_size,
                available_physical_core_count=_available_physical_core_count(),
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=active_source_compatibility,
                source_clean_verified=source_before["source_clean_verified"],
                authority_is_canonical=authority_is_canonical,
                authority_is_tracked=authority_is_tracked,
                external_watchdog_active=True,
                full3d_reference_sha256=full3d_reference_sha256,
                resource_anchor_sha256=resource_anchor_sha256,
                assembly_backend=args.stage4_full3d_assembly_backend,
                measured_full3d_anchor=fresh_static_anchor_gate,
                m160_funnel_evidence=m160_funnel_evidence,
                expected_m160_funnel_sha256=(args.m160_funnel_evidence_sha256),
                observed_m160_funnel_sha256=observed_m160_funnel_sha256,
                graded_reference_h=args.graded_reference_h,
                graded_profile=args.graded_profile,
                adaptive_mechanism_gate=adaptive_mechanism_gate,
            )
            launch_gate.update(
                {
                    "resource_authority_path": str(authority_path),
                    "resource_authority_read_error": authority_read_error,
                    "resource_authority_observed_sha256": (authority_observed_sha256),
                    "full3d_reference_path": (
                        None if full3d_path is None else str(full3d_path)
                    ),
                    "full3d_reference_observed_sha256": (full3d_reference_sha256),
                    "full3d_reference_expected_sha256": (args.full3d_reference_sha256),
                    "fresh_static_reference_read_error": (fresh_static_read_error),
                    "historical_authority_source_compatibility": (
                        historical_authority_source_compatibility
                    ),
                    "resource_anchor_path": (
                        None
                        if resource_anchor_path is None
                        else str(resource_anchor_path)
                    ),
                    "resource_anchor_observed_sha256": resource_anchor_sha256,
                    "m160_funnel_evidence_path": (
                        None if m160_funnel_path is None else str(m160_funnel_path)
                    ),
                    "m160_funnel_evidence_read_error": (m160_funnel_read_error),
                    "adaptive_mechanism_evidence_path": (
                        None
                        if adaptive_mechanism_path is None
                        else str(adaptive_mechanism_path)
                    ),
                    "adaptive_mechanism_evidence_read_error": (
                        adaptive_mechanism_error
                    ),
                }
            )
            launch_gate["checks"].update(
                {
                    "task034_resource_authority_readable": (
                        authority_read_error is None
                    ),
                    "task034_measured_resource_anchor_readable": (
                        full3d_reference_sha256 is not None
                        or resource_anchor_sha256 is not None
                    ),
                }
            )
            launch_gate["failures"] = [
                name for name, passed in launch_gate["checks"].items() if not passed
            ]
            launch_gate["pass"] = not launch_gate["failures"]
            launch_gate["launch_eligible_recomputed"] = launch_gate["pass"]
        else:
            resource_matrix_path = args.resource_matrix
            if not resource_matrix_path.is_absolute():
                resource_matrix_path = ROOT / resource_matrix_path
            resource_matrix_path = resource_matrix_path.resolve()
            canonical_resource_matrices = {
                DEFAULT_RESOURCE_MATRIX.resolve(),
                REDUCED_EQUAL_ACCURACY_RESOURCE_MATRIX.resolve(),
            }
            resource_matrix_is_canonical = (
                resource_matrix_path in canonical_resource_matrices
            )
            try:
                matrix_relative = resource_matrix_path.relative_to(ROOT).as_posix()
            except ValueError:
                matrix_relative = None
            resource_matrix_is_tracked = bool(
                matrix_relative is not None
                and _git("ls-files", "--error-unmatch", "--", matrix_relative)
                is not None
            )
            resource_matrix, resource_matrix_read_error = _read_json_object(
                resource_matrix_path
            )
            launch_gate = hybrid_launch_gate(
                resource_matrix,
                degree=args.degree,
                h_nm=args.h_nm,
                requested_modes=args.requested_modes,
                candidate_modes=args.candidate_modes,
                solver_path=args.solver_path,
                compare_modal_schur=args.compare_modal_schur,
                comparison_solver_path=args.comparison_solver_path,
                bottom_interface_nm=args.bottom_interface_nm,
                top_interface_nm=args.top_interface_nm,
                graded_reference_h=args.graded_reference_h,
                incident_grazing_deg=args.incident_grazing_deg,
                polarization_kind=args.polarization_kind,
                container_limit_bytes=environment_before.get("memory_limit_bytes"),
                host_available_memory_bytes=environment_before.get(
                    "host_available_memory_bytes"
                ),
                warning_gib=args.warning_gib,
                terminate_gib=args.terminate_gib,
                core_evidence=core_evidence,
                expected_core_sha256=args.high_order_core_evidence_sha256,
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=core_source_compatibility,
                m160_funnel_evidence=m160_funnel_evidence,
                expected_m160_funnel_sha256=(args.m160_funnel_evidence_sha256),
                observed_m160_funnel_sha256=observed_m160_funnel_sha256,
                task033_same_sha_anchor_requalification=(
                    args.task033_same_sha_anchor_requalification
                ),
                source_clean_verified=source_before["source_clean_verified"],
                resource_matrix_is_canonical=resource_matrix_is_canonical,
                resource_matrix_is_tracked=resource_matrix_is_tracked,
                external_watchdog_active=True,
            )
            launch_gate["resource_matrix_path"] = str(resource_matrix_path)
            launch_gate["resource_matrix_read_error"] = resource_matrix_read_error
            launch_gate["m160_funnel_evidence_path"] = (
                None if m160_funnel_path is None else str(m160_funnel_path)
            )
            launch_gate["m160_funnel_evidence_read_error"] = m160_funnel_read_error
            launch_gate["checks"].update(
                {
                    "canonical_case091_resource_matrix_path": (
                        resource_matrix_is_canonical
                    ),
                    "case091_resource_matrix_is_git_tracked": (
                        resource_matrix_is_tracked
                    ),
                }
            )
            launch_gate["failures"] = [
                name for name, passed in launch_gate["checks"].items() if not passed
            ]
            launch_gate["pass"] = not launch_gate["failures"]
            launch_gate["launch_eligible_recomputed"] = launch_gate["pass"]
    else:
        core_gate = high_order_core_evidence_gate(
            args.degree,
            core_evidence,
            expected_sha256=args.high_order_core_evidence_sha256,
            current_source_sha=source_before.get("commit_sha"),
            source_compatibility=core_source_compatibility,
        )
        launch_gate = {
            "pass": bool(
                core_gate["pass"] and args._qep_effective_limit_gib is not None
            ),
            "launch_eligible_recomputed": bool(
                core_gate["pass"] and args._qep_effective_limit_gib is not None
            ),
            "scope": "qep_component_uses_its_own_two_center_preflight",
            "qep_effective_limit_gib_forwarded_to_worker": (
                args._qep_effective_limit_gib
            ),
            "high_order_core_evidence": core_gate,
            "failures": [
                *core_gate["failures"],
                *(
                    []
                    if args._qep_effective_limit_gib is not None
                    else ["finite_qep_effective_limit_unavailable"]
                ),
            ],
        }
    launch_gate["high_order_core_evidence_file"] = (
        None if core_path is None else str(core_path)
    )
    launch_gate["high_order_core_evidence_read_error"] = core_read_error
    if (
        args.degree >= 3
        and not (
            args.task035c_p6_h10_gate
            or args.task037b_h1_gate
            or args.task037b_h3_gate
            or args.task037b_h4_gate
            or args.task037b_h5_gate
            or args.task037b_v1_gate
            or args.task037b_v2_gate
            or args.task037b_v3_gate
            or args.task037b_v4_gate
        )
        and core_read_error is not None
    ):
        launch_gate["pass"] = False
        launch_gate["launch_eligible_recomputed"] = False
        launch_gate.setdefault("failures", []).append(
            "high_order_core_evidence_file_unreadable"
        )
    v4_path = bool(
        args.task037b_v4_gate and args.solver_path == "block-ldu-action-full-solve"
    )
    v4_provenance_gate = (
        _task037b_v4_hash_bound_provenance_gate()
        if v4_path
        else {"pass": True, "failures": [], "artifacts": {}}
    )
    if v4_path:
        launch_gate["v4_provenance_gate"] = v4_provenance_gate
    if v4_path and not v4_provenance_gate["pass"]:
        launch_gate["pass"] = False
        launch_gate["launch_eligible_recomputed"] = False
        launch_gate.setdefault("failures", []).append(
            "v4_hash_bound_provenance_gate_failed"
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / f"{args.case_label}_{args.target}_p{args.degree}_h{args.h_nm:g}_mpi{args.mpi_size}_{timestamp}"
    ).resolve()
    summary_output_path = (
        None
        if args.summary_output is None
        else (
            args.summary_output
            if args.summary_output.is_absolute()
            else ROOT / args.summary_output
        ).resolve()
    )
    if v4_path and (
        run_dir.exists()
        or (summary_output_path is not None and summary_output_path.exists())
    ):
        raise RuntimeError("V4 run-dir or summary-output already exists.")
    run_dir.mkdir(parents=True, exist_ok=False)
    preflight_pass = bool(
        source_preflight_gate["pass"]
        and environment_preflight["pass"]
        and launch_gate["pass"]
        and v4_provenance_gate["pass"]
    )
    if not preflight_pass:
        summary = {
            "schema_version": "task033.memory-watchdog.v2",
            "benchmark_id": "task033_external_memory_watchdog",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": ("task037b_v4_formal_not_pass" if v4_path else "formal_not_pass"),
            "target": args.target,
            "case_label": args.case_label,
            "launch_state": "not_run_preflight_failed",
            "formal_pass": False,
            "memory_authority_pass": False,
            "physical_qualified": False,
            "source": source_before,
            "source_gate": source_preflight_gate,
            "launch_gate": launch_gate,
            "v4_provenance_gate": v4_provenance_gate,
            "task033_anchor_requalification": launch_gate.get(
                "task033_anchor_requalification"
            ),
            "resource_authority": {
                "environment_before": environment_before,
                "preflight": environment_preflight,
                "gate": {"pass": False, "failures": ["run_not_started"]},
            },
            "requested_modes": args.requested_modes,
            "measurements": None,
        }
        rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        (run_dir / "memory_sampler_summary.json").write_text(rendered, encoding="utf-8")
        if args.summary_output is not None:
            promoted = (
                args.summary_output
                if args.summary_output.is_absolute()
                else ROOT / args.summary_output
            )
            promoted.parent.mkdir(parents=True, exist_ok=True)
            promoted.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 2

    core_gate = launch_gate.get("high_order_core_evidence", {})
    if args.degree >= 3 and not (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ):
        args.high_order_core_evidence_sha256 = core_gate.get("evidence_sha256")
    args._no_swap_verified = True
    record_path = run_dir / "solver_record.json"
    stage_path = run_dir / "memory_stages.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = _worker_command(args, record_path, stage_path)
    scoped_worker_gate = bool(
        args.task034_workstation_gate
        or args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    )
    terminal_stage = (
        "v4_worker_cleanup_finished"
        if args.task037b_v4_gate
        else "release_finished"
        if args.task037b_v3_gate
        else "v2_record"
        if args.task037b_v2_gate
        else "v1_r5_record"
        if args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
        else "v1_r4_record"
        if args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-oracle-qualification"
        else "v1_r3_record"
        if args.task037b_v1_gate
        and args.solver_path == "whole-endcap-ilu0-qualification"
        else "v1_r2_f_only_record"
        if args.task037b_v1_gate
        and args.solver_path == "f-only-local-inverse-qualification"
        else "v1_r1_record"
        if args.task037b_v1_gate
        else "h5b_release_record"
        if args.task037b_h5_gate
        else "record_and_release"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "BENCHMARK_EXACT_COMMAND": " ".join(command),
        }
    )

    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    terminated_for_authority_unreadable = False
    terminated_for_swap = False
    live_authority_all_readable = True
    job_swap_all_samples_readable = True
    max_process_tree_swap_bytes = 0
    max_dedicated_cgroup_swap_bytes = 0
    dedicated_job_cgroup_observed = False
    post_exit_readability_samples_excluded = 0
    terminal_worker_drain_samples_excluded = 0
    max_live_authority_gib = 0.0
    v2_process_control: dict[str, Any] | None = None
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            **(
                worker_process_group_popen_kwargs()
                if args.task037b_v2_gate
                or args.task037b_v3_gate
                or args.task037b_v4_gate
                else {}
            ),
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, stage_path, elapsed)
            job_sample = resource_authority_sample(process.pid)
            process_tree = job_sample["process_tree"]
            job_cgroup = job_sample["job_cgroup"]
            live_worker_rss_mb = float(process_tree["rss_bytes"]) / 1024**2
            live_workers = [
                {"pid": pid, "scope": "process_tree"} for pid in process_tree["pids"]
            ]
            if not (
                args.task037b_h5_gate
                or args.task037b_v1_gate
                or args.task037b_v2_gate
                or args.task037b_v3_gate
                or args.task037b_v4_gate
            ):
                row["worker_rank_rss_sum_mb"] = live_worker_rss_mb
                row["worker_rank_rss_mb_json"] = json.dumps(
                    live_workers, separators=(",", ":")
                )
            row["mpi_process_tree_swap_mb"] = (
                float(process_tree["swap_bytes"]) / 1024**2
            )
            row["job_cgroup_path"] = job_cgroup["path"]
            row["job_cgroup_dedicated"] = job_cgroup["dedicated_job_cgroup"]
            if job_cgroup["dedicated_job_cgroup"]:
                row["container_cgroup_current_mb"] = (
                    None
                    if job_cgroup["memory_current_bytes"] is None
                    else float(job_cgroup["memory_current_bytes"]) / 1024**2
                )
                row["container_swap_current_mb"] = (
                    None
                    if job_cgroup["swap_current_bytes"] is None
                    else float(job_cgroup["swap_current_bytes"]) / 1024**2
                )
            else:
                row["container_cgroup_current_mb"] = None
                row["container_swap_current_mb"] = None
            process_running = process.poll() is None
            cgroup_current_mb = row.get("container_cgroup_current_mb")
            authority_readable = bool(
                process_tree["all_status_readable"]
                and (
                    not job_cgroup["dedicated_job_cgroup"]
                    or cgroup_current_mb is not None
                )
            )
            live_worker_count: int | None = None
            terminal_record_complete = False
            if (
                scoped_worker_gate
                and process_running
                and not authority_readable
                and row.get("stage") == terminal_stage
            ):
                terminal_record_complete = _task034_terminal_record_is_complete(
                    record_path
                )
                live_worker_rss, discovered_workers = _live_task033_worker_rss(
                    process.pid, args.target
                )
                if live_worker_rss is not None:
                    process_tree_pids = set(process_tree["pids"])
                    live_worker_count = sum(
                        int(worker["pid"]) in process_tree_pids
                        for worker in discovered_workers
                    )
            terminal_worker_drain = _task034_terminal_worker_drain(
                task034_workstation_gate=scoped_worker_gate,
                process_running=process_running,
                authority_readable=authority_readable,
                stage=row.get("stage"),
                terminal_record_complete=terminal_record_complete,
                live_worker_count=live_worker_count,
                terminal_stage=terminal_stage,
            )
            readability_sample_is_formal = _resource_readability_sample_is_formal(
                task034_workstation_gate=scoped_worker_gate,
                process_running=process_running,
                terminal_worker_drain=terminal_worker_drain,
            )
            if readability_sample_is_formal:
                job_swap_all_samples_readable &= bool(
                    process_tree["all_status_readable"]
                )
                max_process_tree_swap_bytes = max(
                    max_process_tree_swap_bytes, int(process_tree["swap_bytes"])
                )
                if job_cgroup["dedicated_job_cgroup"]:
                    dedicated_job_cgroup_observed = True
                    if job_cgroup["swap_current_bytes"] is None:
                        job_swap_all_samples_readable = False
                    else:
                        max_dedicated_cgroup_swap_bytes = max(
                            max_dedicated_cgroup_swap_bytes,
                            int(job_cgroup["swap_current_bytes"]),
                        )
            elif terminal_worker_drain:
                terminal_worker_drain_samples_excluded += 1
            else:
                post_exit_readability_samples_excluded += 1
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            if readability_sample_is_formal:
                live_authority_all_readable &= authority_readable
            live_authority_gib = (
                None
                if not readability_sample_is_formal or not authority_readable
                else max(float(live_worker_rss_mb), float(cgroup_current_mb or 0.0))
                / 1024.0
            )
            if live_authority_gib is not None:
                max_live_authority_gib = max(max_live_authority_gib, live_authority_gib)
                warning_triggered |= live_authority_gib >= args.warning_gib
            if (
                process_running
                and (
                    args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                )
                and readability_sample_is_formal
                and (
                    int(process_tree["swap_bytes"]) > 0
                    or (
                        job_cgroup["dedicated_job_cgroup"]
                        and job_cgroup["swap_current_bytes"] is not None
                        and int(job_cgroup["swap_current_bytes"]) > 0
                    )
                )
            ):
                terminated_for_swap = True
                if v2_process_control is None:
                    v2_process_control = terminate_process_tree(process)
                process_running = False
            if _authority_unreadable_requires_termination(
                process_running=process_running,
                readability_sample_is_formal=readability_sample_is_formal,
                authority_readable=authority_readable,
            ):
                terminated_for_authority_unreadable = True
                if (
                    args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                ):
                    if v2_process_control is None:
                        v2_process_control = terminate_process_tree(process)
                    process_running = False
                else:
                    process.terminate()
            if (
                process_running
                and live_authority_gib is not None
                and live_authority_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                if (
                    args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                ):
                    if v2_process_control is None:
                        v2_process_control = terminate_process_tree(process)
                    process_running = False
                else:
                    process.terminate()
            if process_running and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                if (
                    args.task037b_v2_gate
                    or args.task037b_v3_gate
                    or args.task037b_v4_gate
                ):
                    if v2_process_control is None:
                        v2_process_control = terminate_process_tree(process)
                    process_running = False
                else:
                    process.terminate()
            if not process_running:
                break
            time.sleep(max(args.poll_interval, 0.05))
        return_code = int(process.returncode or 0)
        if (
            args.task037b_v2_gate or args.task037b_v3_gate or args.task037b_v4_gate
        ) and v2_process_control is None:
            v2_process_control = terminate_process_tree(process)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solver_record = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.is_file()
        else {}
    )
    v4_history_sha256 = None
    if args.task037b_v4_gate:
        history = solver_record.get("v4_telemetry", {}).get("history")
        if isinstance(history, list):
            v4_history_sha256 = hashlib.sha256(
                json.dumps(
                    history,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
    memory = _sampler_summary(rows, poll_interval=args.poll_interval)
    memory.update(
        {
            "job_swap_all_samples_readable": job_swap_all_samples_readable,
            "max_process_tree_swap_bytes": max_process_tree_swap_bytes,
            "max_dedicated_cgroup_swap_bytes": max_dedicated_cgroup_swap_bytes,
            "dedicated_job_cgroup_observed": dedicated_job_cgroup_observed,
            "post_exit_readability_samples_excluded": (
                post_exit_readability_samples_excluded
            ),
            "terminal_worker_drain_samples_excluded": (
                terminal_worker_drain_samples_excluded
            ),
        }
    )
    h5_memory_stages = (
        _h5_stage_memory_summary(rows, expected_mpi_size=args.mpi_size)
        if args.task037b_h5_gate
        else None
    )
    environment_after = _resource_environment_snapshot()
    environment_after["task034_effective_limit"] = effective_memory_limit()
    source = _watchdog_source_after(source_before)
    resource_authority = _external_resource_authority(
        rows,
        memory,
        environment_before=environment_before,
        environment_after=environment_after,
        live_authority_all_readable=live_authority_all_readable,
    )
    resource_authority["live_control_peak_authority_gib"] = max_live_authority_gib
    resource_authority["live_control_semantics"] = (
        "Every warning and controlled termination decision used "
        "max(live Task033 MPI worker RSS sum, cgroup memory.current)."
    )
    resource_gate = resource_authority["gate"]
    source_gate = source_identity_gate(source)
    no_swap = bool(
        resource_gate["checks"].get("container_current_swap_zero")
        and resource_gate["checks"].get("all_live_swap_samples_readable")
        and max_process_tree_swap_bytes == 0
        and max_dedicated_cgroup_swap_bytes == 0
    )
    if args.target == "qep":
        numerical_pass = solver_record.get("status") == "measured_shard_pass"
        formal_numerical_pass = numerical_pass
        measurements: dict[str, Any] = solver_record
    else:
        qualification = solver_record.get("qualification", {})
        if args.task037b_v4_gate:
            v4_evaluation = _task037b_v4_evaluate_record(solver_record)
            numerical_pass = bool(v4_evaluation["numerical_pass"])
            formal_numerical_pass = bool(v4_evaluation["contract_pass"])
        elif args.task037b_v3_gate:
            v3_evaluation = _task037b_v3_evaluate_record(solver_record)
            numerical_pass = bool(v3_evaluation["numerical_pass"])
            formal_numerical_pass = bool(v3_evaluation["contract_pass"])
        elif args.task037b_v2_gate:
            numerical_pass = _task037b_v2_numerical_pass(solver_record)
            formal_numerical_pass = _task037b_v2_numerical_pass(
                solver_record, require_numerical_pass=False
            )
        elif args.task037b_v1_gate:
            if args.solver_path == "dtn-woodbury-local-inverse-qualification":
                numerical_pass = _task037b_v1_r5_numerical_pass(solver_record)
                formal_numerical_pass = _task037b_v1_r5_numerical_pass(
                    solver_record, require_numerical_pass=False
                )
            elif args.solver_path == "dtn-woodbury-oracle-qualification":
                numerical_pass = _task037b_v1_r4_numerical_pass(solver_record)
                formal_numerical_pass = numerical_pass
            elif args.solver_path == "f-only-local-inverse-qualification":
                numerical_pass = _task037b_v1_r2_numerical_pass(solver_record)
                formal_numerical_pass = _task037b_v1_r2_numerical_pass(
                    solver_record, require_numerical_pass=False
                )
            elif args.solver_path == "whole-endcap-ilu0-qualification":
                numerical_pass = _task037b_v1_r3_numerical_pass(solver_record)
                formal_numerical_pass = _task037b_v1_r3_numerical_pass(
                    solver_record, require_numerical_pass=False
                )
            else:
                numerical_pass = _task037b_v1_r1_numerical_pass(solver_record)
                formal_numerical_pass = numerical_pass
        elif args.task037b_h5_gate:
            numerical_pass = _task037b_h5_numerical_pass(solver_record)
            formal_numerical_pass = numerical_pass
        else:
            numerical_pass = bool(
                qualification.get("integration_pass")
                and qualification.get("task033_physical_truncation_allowed")
            )
            formal_numerical_pass = numerical_pass
        measurements = _hybrid_measurements(solver_record)
        if args.task037b_h5_gate:
            measurements["h5_memory_stages"] = h5_memory_stages
    formal_pass = _formal_shard_pass(
        return_code=return_code,
        numerical_pass=formal_numerical_pass,
        resource_gate_pass=resource_gate["pass"],
        source_gate_pass=source_gate["pass"],
        launch_gate_pass=launch_gate["pass"],
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        terminated_for_authority_unreadable=(terminated_for_authority_unreadable),
        no_swap_pass=(
            no_swap
            if args.task037b_h5_gate
            or args.task037b_v2_gate
            or args.task037b_v3_gate
            or args.task037b_v4_gate
            or (
                args.task037b_v1_gate
                and args.solver_path
                in (
                    "whole-endcap-ilu0-qualification",
                    "dtn-woodbury-oracle-qualification",
                    "dtn-woodbury-local-inverse-qualification",
                )
            )
            else True
        ),
    )
    v2_path = bool(
        args.task037b_v2_gate and args.solver_path == "block-ldu-action-screen"
    )
    v3_path = bool(
        args.task037b_v3_gate and args.solver_path == "block-ldu-action-screen"
    )
    v2_raw_contract = bool(
        v2_path
        and _task037b_v2_numerical_pass(solver_record, require_numerical_pass=False)
    )
    v2_process_group_pass = bool(
        not v2_path
        or (
            isinstance(v2_process_control, dict)
            and v2_process_control.get("worker_exited") is True
            and v2_process_control.get("process_group_exited") is True
        )
    )
    if v2_path and not v2_process_group_pass:
        formal_pass = False
    v2_process_tree_peak_mb = max(
        (
            float(stage.get("max_mpi_process_tree_rss_mb"))
            for stage in (memory.get("stage_peaks") or [])
            if isinstance(stage, dict)
            and _v2_finite_number(stage.get("max_mpi_process_tree_rss_mb"))
        ),
        default=None,
    )
    v2_resource_state = _task037b_v2_resource_classification(v2_process_tree_peak_mb)
    v2_resource_measurement_failure = bool(
        v2_path and v2_resource_state["measurement_failure"]
    )
    if v2_resource_measurement_failure:
        formal_pass = False
    v2_record_complete = bool(v2_path and formal_pass and v2_raw_contract)
    v3_raw_contract = bool(
        v3_path and v3_evaluation is not None and v3_evaluation["contract_pass"]
    )
    v3_process_group_pass = bool(
        not v3_path
        or (
            isinstance(v2_process_control, dict)
            and v2_process_control.get("worker_exited") is True
            and v2_process_control.get("process_group_exited") is True
        )
    )
    if v3_path and not v3_process_group_pass:
        formal_pass = False
    v3_process_tree_peak_mb = max(
        (
            float(stage.get("max_mpi_process_tree_rss_mb"))
            for stage in (memory.get("stage_peaks") or [])
            if isinstance(stage, dict)
            and _v2_finite_number(stage.get("max_mpi_process_tree_rss_mb"))
        ),
        default=None,
    )
    v3_resource_state = _task037b_v3_resource_classification(v3_process_tree_peak_mb)
    v3_resource_measurement_failure = bool(
        v3_path and v3_resource_state["measurement_failure"]
    )
    if v3_resource_measurement_failure:
        formal_pass = False
    v3_record_complete = bool(v3_path and formal_pass and v3_raw_contract)
    v3_solver_record_available = bool(
        v3_path
        and isinstance(solver_record, dict)
        and solver_record.get("record_schema")
        == "task037b.v3-progressive-block-pc-screen.v1"
        and isinstance(solver_record.get("v3_telemetry"), dict)
        and isinstance(solver_record.get("screen"), dict)
    )
    v4_raw_contract = bool(
        v4_path and v4_evaluation is not None and v4_evaluation["contract_pass"]
    )
    v4_process_group_pass = bool(
        not v4_path
        or (
            isinstance(v2_process_control, dict)
            and v2_process_control.get("worker_exited") is True
            and v2_process_control.get("process_group_exited") is True
        )
    )
    if v4_path and not v4_process_group_pass:
        formal_pass = False
    v4_process_tree_peak_mb = max(
        (
            float(stage.get("max_mpi_process_tree_rss_mb"))
            for stage in (memory.get("stage_peaks") or [])
            if isinstance(stage, dict)
            and _v2_finite_number(stage.get("max_mpi_process_tree_rss_mb"))
        ),
        default=None,
    )
    v4_resource_state = _task037b_v4_resource_classification(v4_process_tree_peak_mb)
    v4_resource_measurement_failure = bool(
        v4_path and v4_resource_state["measurement_failure"]
    )
    if v4_resource_measurement_failure:
        formal_pass = False
    v4_record_complete = bool(v4_path and formal_pass and v4_raw_contract)
    v4_solver_record_available = bool(
        v4_path
        and isinstance(solver_record, dict)
        and solver_record.get("record_schema") == "task037b.v4-full-block-pc.v1"
        and isinstance(solver_record.get("v4_telemetry"), dict)
    )
    r5_raw_contract = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and _task037b_v1_r5_numerical_pass(solver_record, require_numerical_pass=False)
    )
    r5_process_tree_peak_mb = max(
        (
            float(stage.get("max_mpi_process_tree_rss_mb"))
            for stage in (memory.get("stage_peaks") or [])
            if isinstance(stage, dict)
            and isinstance(stage.get("max_mpi_process_tree_rss_mb"), (int, float))
            and math.isfinite(float(stage["max_mpi_process_tree_rss_mb"]))
        ),
        default=None,
    )
    r5_resource_state = _task037b_r5_resource_gate(
        formal_pass=formal_pass,
        record_complete=r5_raw_contract,
        numerical_pass=numerical_pass,
        process_tree_peak_mb=r5_process_tree_peak_mb,
    )
    r5_resource_review = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and r5_resource_state["resource_review"]
    )
    r5_resource_measurement_failure = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and r5_resource_state["measurement_failure"]
    )
    if r5_resource_measurement_failure:
        formal_pass = False
    r5_record_complete = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and formal_pass
        and formal_numerical_pass
        and r5_raw_contract
    )
    r5_h6_eligible = bool(r5_record_complete and r5_resource_state["h6_eligible"])
    r3_record_complete = bool(
        args.task037b_v1_gate
        and args.solver_path == "whole-endcap-ilu0-qualification"
        and formal_pass
        and formal_numerical_pass
    )
    r4_record_complete = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-oracle-qualification"
        and formal_pass
        and formal_numerical_pass
    )
    r2_record_complete = bool(
        args.task037b_v1_gate
        and args.solver_path == "f-only-local-inverse-qualification"
        and formal_pass
        and formal_numerical_pass
    )
    r5_path = bool(
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
    )
    if v4_path:
        if v4_resource_measurement_failure:
            summary_status = "task037b_v4_resource_measurement_failed"
        elif v4_solver_record_available and not v4_raw_contract:
            summary_status = "task037b_v4_implementation_gate_failed"
        elif not formal_pass or not v4_solver_record_available:
            summary_status = "task037b_v4_formal_not_pass"
        else:
            summary_status = str(
                solver_record.get("status", "task037b_v4_full_solve_numerical_negative")
            )
    elif v3_path:
        if v3_resource_measurement_failure:
            summary_status = "task037b_v3_resource_measurement_failed"
        elif v3_solver_record_available and not v3_raw_contract:
            summary_status = "task037b_v3_implementation_gate_failed"
        elif not formal_pass or not v3_solver_record_available:
            summary_status = "task037b_v3_formal_not_pass"
        else:
            summary_status = str(
                solver_record.get("status", "task037b_v3_family_negative")
            )
    elif v2_path:
        if v2_resource_measurement_failure:
            summary_status = "task037b_v2_resource_measurement_failed"
        elif not formal_pass:
            summary_status = "task037b_v2_formal_not_pass"
        elif not v2_raw_contract:
            summary_status = "task037b_v2_screen_contract_failed"
        elif v2_resource_state["resource_review"]:
            summary_status = "task037b_v2_resource_review_required"
        elif numerical_pass:
            summary_status = "task037b_v2_screen_pass"
        else:
            summary_status = "task037b_v2_screen_numerical_negative"
    elif r5_path:
        if r5_resource_measurement_failure:
            summary_status = "R5_RESOURCE_MEASUREMENT_FAILED"
        elif r5_resource_review:
            summary_status = "NUMERICAL_PASS_RESOURCE_REVIEW_REQUIRED"
        elif r5_h6_eligible:
            summary_status = "task037b_v1_r5_complete_awaiting_h6"
        elif r5_record_complete:
            # A contract-complete bounded negative/borderline is a controlled
            # stop, not a formal-record failure.
            summary_status = str(
                solver_record.get("status", "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE")
            )
        else:
            summary_status = "task037b_v1_r5_raw_record_formal_not_pass"
    else:
        summary_status = (
            "task037b_v1_r4_complete_awaiting_r5"
            if r4_record_complete
            else "task037b_v1_r4_raw_record_formal_not_pass"
            if args.task037b_v1_gate
            and args.solver_path == "dtn-woodbury-oracle-qualification"
            else "task037b_v1_r3_complete_awaiting_r4"
            if r3_record_complete
            else "task037b_v1_r2_complete_awaiting_r3"
            if r2_record_complete
            else "task037b_v1_r1_pass_awaiting_r2"
            if args.task037b_v1_gate and formal_pass
            else "formal_not_pass"
            if args.task037b_v1_gate
            else "measured_shard_pass"
            if formal_pass
            else "formal_not_pass"
        )
    summary = {
        "schema_version": "task033.memory-watchdog.v2",
        "benchmark_id": "task033_external_memory_watchdog",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": summary_status,
        "target": args.target,
        "case_label": args.case_label,
        "command": command,
        "return_code": return_code,
        "numeric_pass": numerical_pass,
        "formal_pass": formal_pass,
        "memory_authority_pass": resource_gate["pass"],
        "physical_qualified": False,
        "v4_numerical_disposition": (
            None
            if not v4_path or v4_evaluation is None
            else v4_evaluation["disposition"]
        ),
        "v3_numerical_disposition": (
            None
            if not v3_path or v3_evaluation is None
            else v3_evaluation["disposition"]
        ),
        "qualification_identity": (
            "task037b_v4_resource_measurement_failed"
            if v4_path and v4_resource_measurement_failure
            else "task037b_v4_implementation_gate_failed"
            if v4_path and v4_solver_record_available and not v4_raw_contract
            else "task037b_v4_formal_not_pass"
            if v4_path and (not formal_pass or not v4_solver_record_available)
            else "task037b_v4_raw_record_complete"
            if v4_path and v4_record_complete
            else "task037b_v4_not_run"
            if v4_path
            else "task037b_v3_resource_measurement_failed"
            if v3_path and v3_resource_measurement_failure
            else "task037b_v3_implementation_gate_failed"
            if v3_path and v3_solver_record_available and not v3_raw_contract
            else "task037b_v3_formal_not_pass"
            if v3_path and (not formal_pass or not v3_solver_record_available)
            else "task037b_v3_raw_record_complete"
            if v3_path and v3_record_complete
            else "task037b_v3_not_run"
            if v3_path
            else "task037b_v2_resource_measurement_failed"
            if v2_path and v2_resource_measurement_failure
            else "task037b_v2_formal_not_pass"
            if v2_path and not formal_pass
            else "task037b_v2_screen_contract_failed"
            if v2_path and not v2_raw_contract
            else "task037b_v2_resource_review_required"
            if v2_path and v2_resource_state["resource_review"]
            else "task037b_v2_raw_record_complete"
            if v2_path and v2_record_complete
            else "task037b_v2_not_run"
            if v2_path
            else "task037b_v1_r5_resource_review_required"
            if r5_resource_review
            else "task037b_v1_r5_resource_measurement_failed"
            if r5_resource_measurement_failure
            else "task037b_v1_r5_raw_record_gate_awaiting_h6"
            if r5_h6_eligible
            else "task037b_v1_r5_raw_record_complete_controlled_stop"
            if args.task037b_v1_gate
            and args.solver_path == "dtn-woodbury-local-inverse-qualification"
            and r5_record_complete
            else "task037b_v1_r5_raw_record_formal_not_pass"
            if args.task037b_v1_gate
            and args.solver_path == "dtn-woodbury-local-inverse-qualification"
            else "task037b_v1_r4_raw_record_gate_awaiting_r5"
            if r4_record_complete
            else "task037b_v1_r4_raw_record_formal_not_pass"
            if args.task037b_v1_gate
            and args.solver_path == "dtn-woodbury-oracle-qualification"
            else "task037b_v1_r3_raw_record_gate_awaiting_r4"
            if r3_record_complete
            else "task037b_v1_r3_raw_record_formal_not_pass"
            if args.task037b_v1_gate
            and args.solver_path == "whole-endcap-ilu0-qualification"
            else "task037b_v1_r2_raw_record_gate_awaiting_r3"
            if r2_record_complete
            else "task037b_v1_r2_raw_record_formal_not_pass"
            if args.task037b_v1_gate
            and args.solver_path == "f-only-local-inverse-qualification"
            else "task037b_v1_r1_raw_record_gate_awaiting_r2"
            if args.task037b_v1_gate
            else "measured_shard_pass_requires_funnel_aggregate_for_physical_qualification"
        ),
        "requested_modes": args.requested_modes,
        "candidate_modes": args.candidate_modes,
        "no_swap": no_swap,
        "warning_threshold_gib": args.warning_gib,
        "termination_threshold_gib": args.terminate_gib,
        "wall_time_limit_seconds": args.timeout_seconds,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "terminated_for_authority_unreadable": (terminated_for_authority_unreadable),
        "terminated_for_swap": terminated_for_swap,
        "memory": memory,
        "resource_authority": resource_authority,
        "launch_gate": launch_gate,
        "task033_anchor_requalification": launch_gate.get(
            "task033_anchor_requalification"
        ),
        "source": source,
        "source_gate": source_gate,
        "worker_source": solver_record.get("metadata")
        or solver_record.get("provenance"),
        "solver_record_sha256": _sha256(record_path),
        "solver_record_ignored_path": str(record_path.relative_to(ROOT)),
        "timeline_ignored_path": str(timeline_path.relative_to(ROOT)),
        "stdout_ignored_path": str(stdout_path.relative_to(ROOT)),
        "timeline_sha256": _sha256(timeline_path),
        "stdout_sha256": _sha256(stdout_path),
        "measurements": measurements,
        "memory_semantics": (
            "Authority is max(simultaneous live MPI worker RSS sum, container "
            "dedicated job cgroup current when present); process-tree VmSwap and "
            "dedicated cgroup swap must be zero. WSL-global pswp is diagnostic only."
        ),
    }
    if (
        args.task037b_v1_gate
        and args.solver_path == "dtn-woodbury-local-inverse-qualification"
    ):
        summary["r5_resource_gate"] = {
            "process_tree_peak_mb": r5_process_tree_peak_mb,
            "process_tree_peak_gib": (
                None
                if r5_process_tree_peak_mb is None
                else r5_process_tree_peak_mb / 1024.0
            ),
            "threshold_gib": 7.0,
            "measurement_present": r5_process_tree_peak_mb is not None,
            "exceeds_threshold": bool(
                r5_process_tree_peak_mb is not None
                and r5_process_tree_peak_mb > 7.0 * 1024.0
            ),
            "resource_review": r5_resource_review,
            "h6_eligible": r5_h6_eligible,
        }
    if v2_path:
        summary["v2_resource_gate"] = v2_resource_state
        summary["v2_process_control"] = v2_process_control
        summary["v2_record_complete"] = v2_record_complete
        summary["v2_numeric_pass"] = numerical_pass
        summary["v2_contract_pass"] = v2_raw_contract
        summary["v2_terminal_stage"] = terminal_stage
        summary["v2_artifacts"] = {
            "solver_record_path": str(record_path.relative_to(ROOT)),
            "solver_record_sha256": _sha256(record_path),
            "timeline_path": str(timeline_path.relative_to(ROOT)),
            "timeline_sha256": _sha256(timeline_path),
            "stdout_path": str(stdout_path.relative_to(ROOT)),
            "stdout_sha256": _sha256(stdout_path),
        }
    if v3_path:
        summary["v3_resource_gate"] = v3_resource_state
        summary["v3_process_control"] = v2_process_control
        summary["v3_record_complete"] = v3_record_complete
        summary["v3_contract_pass"] = v3_raw_contract
        summary["v3_numeric_pass"] = numerical_pass
        summary["v3_terminal_stage"] = terminal_stage
        summary["v3_failures"] = (
            [] if v3_evaluation is None else v3_evaluation.get("failures", [])
        )
        summary["v3_artifacts"] = {
            "solver_record_path": str(record_path.relative_to(ROOT)),
            "solver_record_sha256": _sha256(record_path),
            "timeline_path": str(timeline_path.relative_to(ROOT)),
            "timeline_sha256": _sha256(timeline_path),
            "stdout_path": str(stdout_path.relative_to(ROOT)),
            "stdout_sha256": _sha256(stdout_path),
        }
    if v4_path:
        summary["v4_resource_gate"] = v4_resource_state
        summary["v4_process_control"] = v2_process_control
        summary["v4_provenance_gate"] = v4_provenance_gate
        summary["v4_record_complete"] = v4_record_complete
        summary["v4_contract_pass"] = v4_raw_contract
        summary["v4_numeric_pass"] = numerical_pass
        summary["v4_terminal_stage"] = terminal_stage
        summary["v4_failures"] = (
            [] if v4_evaluation is None else v4_evaluation.get("failures", [])
        )
        summary["v4_artifacts"] = {
            "solver_record_path": str(record_path.relative_to(ROOT)),
            "solver_record_sha256": _sha256(record_path),
            "stages_path": str(stage_path.relative_to(ROOT)),
            "stages_sha256": _sha256(stage_path),
            "timeline_path": str(timeline_path.relative_to(ROOT)),
            "timeline_sha256": _sha256(timeline_path),
            "stdout_path": str(stdout_path.relative_to(ROOT)),
            "stdout_sha256": _sha256(stdout_path),
            "history_sha256": v4_history_sha256,
        }
    if args.task037b_h5_gate:
        summary.update(
            {
                "h5_memory_stages": h5_memory_stages,
                "h5_external_no_swap_gate": no_swap,
            }
        )
    summary_path = run_dir / "memory_sampler_summary.json"
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    summary_path.write_text(rendered, encoding="utf-8")
    if args.summary_output is not None:
        promoted = (
            args.summary_output
            if args.summary_output.is_absolute()
            else ROOT / args.summary_output
        )
        promoted.parent.mkdir(parents=True, exist_ok=True)
        promoted.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if formal_pass else (return_code or 2)


def main(argv: list[str] | None = None) -> int:
    return run(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
