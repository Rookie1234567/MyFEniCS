from __future__ import annotations

import argparse
import gc
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host path
    resource = None

from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MODE_COUNTS,
    TASK035C_P6_H10_MPI_SIZES,
    task036_full3d_reference_gate,
    task036_strong_trace_interface_scope,
    task036_strong_trace_anchor_scope,
    task035c_p6_h10_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
    valid_hex_digest,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    target_stage4_config,
)
from src.solvers.common_3d_utils import (
    _current_rss_mb,
    _trim_process_heap,
)
from src.common.distributed_matrix_diagnostics import (
    distributed_active_column_count,
)
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    NearDegenerateBlockPartitionSplitError,
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    build_scalar_stage4_reciprocal_negative_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    compare_selected_planes_to_reference,
    hybrid_volume_absorption,
    interface_field_continuity,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    evaluate_hybrid_recovered_direct_projection_audit,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    build_hybrid_modal_schur_direct_system,
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_strong_trace_direct import (
    build_hybrid_strong_trace_direct_system,
    evaluate_hybrid_strong_trace_solution,
    recover_hybrid_strong_trace_static_fields,
    solve_hybrid_strong_trace_direct,
)
from src.solvers.common_3d_solve import (
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from src.solvers.dtn_port_3d import DtnTraceAliasError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase6"
    / "hybrid_augmented_research.json"
)
REFERENCE_BY_DEGREE_AND_H = {
    (2, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h5_reference.json",
    (2, 3.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h3_reference.json",
    (3, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "stage3_p3_h5"
    / "full3d_reference.json",
}


def _discrete_axial_qualification_scope(
    propagation_model: str,
    traction_model: str,
) -> dict[str, Any]:
    """Expose the fail-closed scope of the Task035c discrete axial symbols."""

    selected = (
        propagation_model == "full3d_uniform_cg"
        or traction_model == "scalar_cg_discrete_derivative"
    )
    return {
        "selected": selected,
        "status": (
            "qualified_only_for_listed_scope"
            if selected
            else "not_selected_ordinary_continuous_symbols"
        ),
        "qualified": [
            "fixed rectangular block grating",
            "structured tensor-product mesh",
            "axis-aligned first-order affine hexahedra",
            "uniform z segmentation in the modal middle region",
            "one axial h for the scalar CG(p) chain",
            "supported axial degree p1-p6",
            "complex128",
            "Floquet periodicity",
            "sparse auxiliary DtN",
            "direct standard/static Full3D and Hybrid",
        ],
        "not_qualified": [
            "nonuniform z spacing",
            "locally refined or hanging-node hexa mesh",
            "curved or distorted hexahedra",
            "high-order curved geometry mapping",
            "tetrahedral static condensation",
            "hexa/tetra/prism/pyramid mixed meshes",
            "irregular geometry",
            "production automatic hp adaptivity",
        ],
        "failure_policy": (
            "unsupported meshes and inconsistent propagation/traction "
            "combinations fail closed; no fallback is permitted"
        ),
    }


def _hybrid_p_disposition(
    polarization_kind: str,
    *,
    full3d_physical_solution_exists: bool,
    modal_rank_sufficient: bool | None,
    modal_rank_evidence: str,
    interface_closure_pass: bool,
    interface_closure_gate_names: tuple[str, ...],
    diagnostic_projection_bug: bool,
    diagnostic_projection_evidence: str,
) -> dict[str, Any]:
    """Classify Hybrid-P failures without calling the physical PDE invalid."""

    if str(polarization_kind).lower() != "p":
        return {
            "applicable": False,
            "primary_status": "not_applicable_s_polarization",
            "hybrid_p_production_qualified": False,
        }
    flags = {
        "full3d_physical_solution_exists": bool(
            full3d_physical_solution_exists
        ),
        "hybrid_modal_rank_insufficient": modal_rank_sufficient is False,
        "hybrid_modal_rank_pending_actual_M_convergence": (
            modal_rank_sufficient is None
        ),
        "hybrid_interface_closure_failed": not bool(
            interface_closure_pass
        ),
        "diagnostic_projection_bug": bool(diagnostic_projection_bug),
        "modal_rank_evidence": str(modal_rank_evidence),
        "interface_closure_gate_names": list(
            interface_closure_gate_names
        ),
        "diagnostic_projection_evidence": str(
            diagnostic_projection_evidence
        ),
    }
    if flags["diagnostic_projection_bug"]:
        primary = "diagnostic_projection_bug"
    elif flags["hybrid_modal_rank_insufficient"]:
        primary = "hybrid_modal_rank_insufficient"
    elif flags["hybrid_interface_closure_failed"]:
        primary = "hybrid_interface_closure_failed"
    elif flags["hybrid_modal_rank_pending_actual_M_convergence"]:
        primary = "hybrid_modal_rank_pending_actual_M_convergence"
    else:
        primary = "hybrid_p_research_observables_pass_production_quarantined"
    return {
        "applicable": True,
        "primary_status": primary,
        **flags,
        "hybrid_p_production_qualified": False,
        "full3d_fallback_is_hybrid_success": False,
    }


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = _git("status", "--porcelain", "--untracked-files=all")
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or tracked_status is None:
        raise SystemExit("Cannot verify Task32 Phase6 source provenance.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match HEAD {head}."
            )
        if tracked_status:
            raise SystemExit(
                "Tracked source is dirty despite --verified-clean-sha. "
                "Commit the implementation before a qualifying run."
            )
        tracked_dirty = False
        verification = "local_full_sha_and_tracked_status"
    else:
        if allow_dirty_research:
            tracked_dirty = True
            verification = "dirty_research_opt_in_with_status_scan"
        elif tracked_status:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase6 code first or pass "
                "--allow-dirty-research for a non-qualifying diagnostic."
            )
        else:
            tracked_dirty = False
            verification = "local_git_status"
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _verify_source_stable_at_end(
    comm: MPI.Intracomm,
    start: dict[str, Any],
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> None:
    """Require the same tracked-source state at the end of a formal shard."""

    end = _source_provenance(
        comm, verified_clean_sha, allow_dirty_research
    )
    if end["commit_sha"] != start["commit_sha"]:
        raise SystemExit("Tracked source HEAD changed during the Hybrid run.")
    if not allow_dirty_research and end["tracked_source_dirty"]:
        raise SystemExit("Tracked source became dirty during the Hybrid run.")
    start["source_commit_at_end_full_sha"] = end["commit_sha"]
    start["source_clean_and_stable"] = bool(
        not start["tracked_source_dirty"]
        and not end["tracked_source_dirty"]
        and end["commit_sha"] == start["commit_sha"]
    )


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _complex_json(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _json_default(value):
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _claim_memory_stage_file(
    comm: MPI.Intracomm,
    stage_path: Path | None,
    *,
    owner_path: Path,
) -> None:
    error = None
    if comm.rank == 0 and stage_path is not None:
        try:
            stage = Path(stage_path)
            owner = Path(owner_path)
            resolved_stage = stage.resolve(strict=False)
            resolved_owner = owner.resolve(strict=False)
            if resolved_stage == resolved_owner:
                raise ValueError("memory-stage path must differ from owner path")
            stage.parent.mkdir(parents=True, exist_ok=True)
            with stage.open("x", encoding="utf-8"):
                pass
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Memory-stage claim failed: {error}")


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    try:
        actual.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return float(
            difference.norm()
            / max(float(actual.norm()), float(expected.norm()), 1.0e-30)
        )
    finally:
        difference.destroy()


def _global_active_column_count(matrix: PETSc.Mat) -> int:
    """Count active columns without replicating their IDs on every rank."""

    return distributed_active_column_count(matrix).global_count


def _basis_summary(basis) -> dict[str, Any]:
    identity_difference = np.asarray(
        basis.biorthogonality_matrix, dtype=np.complex128
    ) - np.eye(len(basis.modes), dtype=np.complex128)
    absolute_difference = np.abs(identity_difference)
    row_sums = np.sum(absolute_difference, axis=1)
    worst_row = int(np.argmax(row_sums))
    worst_entry = tuple(
        int(index)
        for index in np.unravel_index(
            int(np.argmax(absolute_difference)),
            absolute_difference.shape,
        )
    )
    return {
        "basis_origin": basis.basis_origin,
        "basis_construction_audit": basis.basis_construction_audit,
        "mode_count": len(basis.modes),
        "max_biorthogonality_identity_error": basis.max_identity_error,
        "max_biorthogonality_entry_identity_error": (
            basis.max_entry_identity_error
        ),
        "biorthogonality_identity_diagnostics": {
            "worst_row_index": worst_row,
            "worst_row_sum": float(row_sums[worst_row]),
            "worst_entry_row": worst_entry[0],
            "worst_entry_column": worst_entry[1],
            "worst_entry_abs": float(absolute_difference[worst_entry]),
        },
        "left_pair_relative_errors": list(basis.left_pair_relative_errors),
        "near_degenerate_groups": [
            {
                "indices": list(group.indices),
                "beta_center_per_nm": _complex_json(group.beta_center),
                "max_relative_beta_spread": group.max_relative_beta_spread,
                "overlap_condition": group.overlap_condition,
                "normalization_method": group.normalization_method,
                "post_normalization_identity_error": (
                    group.post_normalization_identity_error
                ),
            }
            for group in basis.groups
        ],
        "near_degenerate_partition_audit": (
            basis.near_degenerate_partition_audit
        ),
        "betas_per_nm": [_complex_json(mode.beta) for mode in basis.modes],
        "directions": [mode.direction for mode in basis.modes],
        "kinds": [mode.kind for mode in basis.modes],
        "passive_branch_valid": [
            mode.passive_branch_valid for mode in basis.modes
        ],
        "polynomial_relative_residuals": [
            mode.right.polynomial_relative_residual for mode in basis.modes
        ],
        "left_polynomial_relative_residuals": [
            mode.left_polynomial_relative_residual for mode in basis.modes
        ],
        "full_vector_gathered": basis.full_vector_gathered,
    }


def _reciprocal_pairing_summary(pairs) -> list[dict[str, Any]]:
    return [
        {
            "positive_index": pair.positive_index,
            "negative_index": pair.negative_index,
            "relative_beta_error": pair.relative_beta_error,
            "electric_mass_overlap": pair.electric_mass_overlap,
            "opposite_direction": pair.opposite_direction,
            "passive_branches_valid": pair.passive_branches_valid,
        }
        for pair in pairs
    ]


def _directional_selection_summary(report) -> dict[str, Any]:
    return {
        "requested_modes": report.requested_modes,
        "candidate_modes": report.candidate_modes,
        "selected_modes": report.selected_modes,
        "desired_direction": report.desired_direction,
        "direction_counts": report.direction_counts,
        "passive_candidate_count": report.passive_candidate_count,
        "selected_candidate_indices": list(report.selected_candidate_indices),
        "flux_tolerance": report.flux_tolerance,
        "finite_candidate_count": report.finite_candidate_count,
        "numerically_infinite_candidate_count": (
            report.numerically_infinite_candidate_count
        ),
        "finite_spectrum_abs_beta_cutoff_per_nm": report.abs_beta_cutoff,
        "first_rejected_numerical_infinity_beta_per_nm": (
            None
            if report.first_rejected_numerical_infinity_beta is None
            else _complex_json(report.first_rejected_numerical_infinity_beta)
        ),
    }


class _ModalBasisCapacityStop(RuntimeError):
    """Internal control flow after writing a structured finite-spectrum negative."""


class _InterfacePreflightStop(RuntimeError):
    """Internal control flow after the Review V5 strong-matrix preflight."""


def _task036_middle_material_audit(
    cfg,
    cross_section,
    *,
    bottom_interface_nm: float,
    top_interface_nm: float,
) -> dict[str, Any]:
    """Check the frozen rectangular middle one structured z layer at a time."""

    plan = cross_section.axis_plan
    tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
    z_values = np.asarray(plan.z_values, dtype=np.float64)
    bottom_matches = np.flatnonzero(
        np.isclose(z_values, bottom_interface_nm, rtol=0.0, atol=tolerance)
    )
    top_matches = np.flatnonzero(
        np.isclose(z_values, top_interface_nm, rtol=0.0, atol=tolerance)
    )
    if len(bottom_matches) != 1 or len(top_matches) != 1:
        middle_indices = np.asarray([], dtype=np.int64)
    else:
        middle_indices = np.arange(
            int(bottom_matches[0]), int(top_matches[0]), dtype=np.int64
        )

    x_mid = 0.5 * (plan.x_values[:-1] + plan.x_values[1:])
    y_mid = 0.5 * (plan.y_values[:-1] + plan.y_values[1:])
    xx, yy = np.meshgrid(x_mid, y_mid, indexing="xy")
    inside_xy = (
        (xx >= cfg.grating_x_min - tolerance)
        & (xx <= cfg.grating_x_max + tolerance)
        & (yy >= cfg.grating_y_min - tolerance)
        & (yy <= cfg.grating_y_max + tolerance)
    )
    cross_section_labels = np.where(inside_xy, 2, 0).astype(np.uint8)
    layer_hashes: list[str] = []
    layer_records: list[dict[str, Any]] = []
    for index in middle_indices:
        z_mid = 0.5 * (z_values[index] + z_values[index + 1])
        if z_mid < cfg.interface_z - tolerance:
            labels = np.full_like(cross_section_labels, 1)
        elif cfg.grating_z_min - tolerance <= z_mid <= cfg.grating_z_max + tolerance:
            labels = cross_section_labels
        else:
            labels = np.zeros_like(cross_section_labels)
        digest = hashlib.sha256(np.ascontiguousarray(labels).tobytes()).hexdigest()
        layer_hashes.append(digest)
        layer_records.append(
            {
                "z_min_nm": float(z_values[index]),
                "z_max_nm": float(z_values[index + 1]),
                "material_pattern_sha256": digest,
            }
        )
    cross_section_hash = hashlib.sha256(
        np.ascontiguousarray(cross_section_labels).tobytes()
    ).hexdigest()
    return {
        "geometry_kind": cfg.geometry_kind,
        "bottom_interface_on_actual_plan": len(bottom_matches) == 1,
        "top_interface_on_actual_plan": len(top_matches) == 1,
        "middle_z_cell_count": int(len(middle_indices)),
        "layer_records": layer_records,
        "unique_material_layer_hashes": sorted(set(layer_hashes)),
        "cross_section_material_pattern_sha256": cross_section_hash,
        "epsilon_x_y_z_equals_epsilon_x_y": bool(
            layer_hashes
            and len(set(layer_hashes)) == 1
            and layer_hashes[0] == cross_section_hash
        ),
    }


NUMERICAL_INFINITY_BETA_H_CUTOFF = 1.0e4
_TASK036_DIRECT_PROJECTION_CHECKS = (
    "task036_direct_projection_requested",
    "task036_direct_projection_tolerance_frozen",
    "task036_direct_projection_nonempty_complete_finite_orders",
    "task036_direct_projection_exact_mode_count",
    "task036_direct_projection_unique_mode_identities",
    "task036_direct_projection_top_bottom_coverage",
    "task036_direct_projection_s_p_coverage",
    "task036_direct_projection_max_le_1e_10",
    "task036_direct_projection_pass",
)


_TASK036_HYBRID_DIRECT_PROJECTION_CHECKS = (
    "task036_hybrid_direct_projection_requested",
    "task036_hybrid_direct_projection_tolerance_frozen",
    "task036_hybrid_direct_projection_nonempty_complete_finite_orders",
    "task036_hybrid_direct_projection_exact_mode_count",
    "task036_hybrid_direct_projection_unique_mode_identities",
    "task036_hybrid_direct_projection_top_bottom_coverage",
    "task036_hybrid_direct_projection_s_p_coverage",
    "task036_hybrid_direct_projection_max_le_1e_10",
    "task036_hybrid_direct_projection_pass",
)


def _task036_hybrid_candidate_direct_projection_checks(
    audit: dict[str, Any],
) -> dict[str, bool]:
    """Recompute the Task036 Hybrid candidate projection evidence Gate."""

    orders = audit.get("orders")
    orders = orders if isinstance(orders, list) else []
    tolerance = audit.get("tolerance")
    tolerance_valid = bool(
        isinstance(tolerance, (int, float))
        and not isinstance(tolerance, bool)
        and math.isfinite(float(tolerance))
        and float(tolerance) == 1.0e-10
    )
    orders_valid = bool(orders) and all(
        isinstance(row, dict)
        and row.get("side") in {"top", "bottom"}
        and row.get("polarization") in {"s", "p"}
        and isinstance(row.get("m"), int)
        and not isinstance(row.get("m"), bool)
        and isinstance(row.get("n"), int)
        and not isinstance(row.get("n"), bool)
        and all(
            isinstance(row.get(key), (int, float))
            and not isinstance(row.get(key), bool)
            and math.isfinite(float(row[key]))
            and float(row[key]) >= 0.0
            for key in (
                "absolute_total_projection_difference",
                "absolute_outgoing_projection_difference",
            )
        )
        for row in orders
    )
    identities = (
        [
            (
                row["side"],
                int(row["m"]),
                int(row["n"]),
                row["polarization"],
            )
            for row in orders
        ]
        if orders_valid
        else []
    )
    expected = audit.get("expected_mode_count")
    audited = audit.get("audited_mode_count")
    exact_count = bool(
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and isinstance(audited, int)
        and not isinstance(audited, bool)
        and audited == expected
        and len(orders) == expected
    )
    maximum = audit.get(
        "max_absolute_outgoing_projection_difference"
    )
    maximum_valid = bool(
        isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and math.isfinite(float(maximum))
        and float(maximum) <= 1.0e-10
    )
    checks = {
        "task036_hybrid_direct_projection_requested": bool(
            audit.get("requested") is True
            and audit.get("scope") == "hybrid_candidate"
        ),
        "task036_hybrid_direct_projection_tolerance_frozen": (
            tolerance_valid
        ),
        "task036_hybrid_direct_projection_nonempty_complete_finite_orders": (
            orders_valid
        ),
        "task036_hybrid_direct_projection_exact_mode_count": exact_count,
        "task036_hybrid_direct_projection_unique_mode_identities": bool(
            identities and len(set(identities)) == len(identities)
        ),
        "task036_hybrid_direct_projection_top_bottom_coverage": bool(
            orders_valid
            and {row["side"] for row in orders} == {"top", "bottom"}
        ),
        "task036_hybrid_direct_projection_s_p_coverage": bool(
            orders_valid
            and {row["polarization"] for row in orders} == {"s", "p"}
        ),
        "task036_hybrid_direct_projection_max_le_1e_10": maximum_valid,
        "task036_hybrid_direct_projection_pass": bool(
            audit.get("pass") is True
        ),
    }
    if set(checks) != set(_TASK036_HYBRID_DIRECT_PROJECTION_CHECKS):
        raise RuntimeError(
            "Task036 Hybrid direct projection Gate names drifted."
        )
    return checks


def _case080_reference_path(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
) -> Path | None:
    references = (
        REFERENCE_BY_DEGREE_AND_H
        if reference_by_degree_and_h is None
        else reference_by_degree_and_h
    )
    matches = [
        path
        for (reference_degree, level), path in references.items()
        if degree == reference_degree and abs(h_nm - level) <= 1.0e-12
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple Case080 references match degree={degree}, h={h_nm} nm."
        )
    return matches[0] if matches else None


def _normalize_full3d_reference_record(
    reference: dict[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    """Normalize a native watchdog record without writing a derived descriptor."""

    if reference.get("record_type") == "task034_full3d_reference":
        return reference
    if reference.get("schema_version") != "task033.full3d-watchdog.v1":
        return reference
    try:
        source = reference["source"]
        qualification = reference["qualification"]
        solver = reference["solver_summary"]
        config = solver.get("config")
        config = config if isinstance(config, dict) else {}
        resource_authority = reference["resource_authority"]
        archive = Path(str(solver["full3d_reference_archive"]))
        metadata = Path(str(solver["full3d_reference_metadata"]))
        if not archive.is_absolute():
            archive = ROOT / archive
        if not metadata.is_absolute():
            metadata = ROOT / metadata
        archive = archive.resolve()
        metadata = metadata.resolve()
        try:
            run_root = archive.parent.relative_to(ROOT)
        except ValueError:
            run_root = archive.parent
        commit_sha = str(source["commit_sha"]).lower()
        polarization_kind = str(solver["polarization_kind"]).lower()
        incident_theta_deg = float(solver["incident_theta_deg"])
        incident_phi_deg = float(solver["incident_phi_deg"])
        archive_sha256 = str(
            solver["full3d_reference_archive_sha256"]
        ).lower()
        task036_checks = qualification.get("checks")
        task036_checks = (
            task036_checks if isinstance(task036_checks, dict) else {}
        )
        task036_audit = reference.get("task036_direct_projection_audit")
        task036_audit = (
            task036_audit if isinstance(task036_audit, dict) else {}
        )
        solver_audit = solver.get(
            "auxiliary_direct_tangential_projection_audit"
        )
        solver_audit = solver_audit if isinstance(solver_audit, dict) else {}
        audit_orders = task036_audit.get("orders")
        audit_orders = audit_orders if isinstance(audit_orders, list) else []
        audit_tolerance = task036_audit.get("tolerance")
        audit_tolerance_valid = bool(
            isinstance(audit_tolerance, (int, float))
            and not isinstance(audit_tolerance, bool)
            and math.isfinite(float(audit_tolerance))
            and float(audit_tolerance) == 1.0e-10
        )
        audit_orders_valid = bool(audit_orders) and all(
            isinstance(row, dict)
            and row.get("side") in {"top", "bottom"}
            and row.get("polarization") in {"s", "p"}
            and isinstance(row.get("m"), int)
            and not isinstance(row.get("m"), bool)
            and isinstance(row.get("n"), int)
            and not isinstance(row.get("n"), bool)
            and all(
                isinstance(row.get(key), (int, float))
                and not isinstance(row.get(key), bool)
                and math.isfinite(float(row[key]))
                and 0.0 <= float(row[key]) <= 1.0e-10
                for key in (
                    "absolute_total_projection_difference",
                    "absolute_outgoing_projection_difference",
                )
            )
            for row in audit_orders
        )
        audit_identities = (
            [
                (
                    row["side"],
                    int(row["m"]),
                    int(row["n"]),
                    row["polarization"],
                )
                for row in audit_orders
            ]
            if audit_orders_valid
            else []
        )
        task036_raw_gate_valid = bool(
            reference.get("task036_forward_robustness_gate") is True
            and qualification.get("failures") == []
            and all(
                task036_checks.get(name) is True
                for name in _TASK036_DIRECT_PROJECTION_CHECKS
            )
            and task036_audit == solver_audit
            and task036_audit.get("requested") is True
            and task036_audit.get("pass") is True
            and audit_tolerance_valid
            and audit_orders_valid
            and len(audit_orders) == solver.get("dtn_port_mode_count")
            and solver.get("dtn_port_top_mode_count")
            == sum(row["side"] == "top" for row in audit_orders)
            and solver.get("dtn_port_bottom_mode_count")
            == sum(row["side"] == "bottom" for row in audit_orders)
            and len(set(audit_identities)) == len(audit_identities)
            and {row["side"] for row in audit_orders} == {"top", "bottom"}
            and {row["polarization"] for row in audit_orders} == {"s", "p"}
            and isinstance(
                task036_audit.get(
                    "max_absolute_outgoing_projection_difference"
                ),
                (int, float),
            )
            and not isinstance(
                task036_audit.get(
                    "max_absolute_outgoing_projection_difference"
                ),
                bool,
            )
            and math.isfinite(
                float(
                    task036_audit[
                        "max_absolute_outgoing_projection_difference"
                    ]
                )
            )
            and 0.0
            <= float(
                task036_audit["max_absolute_outgoing_projection_difference"]
            )
            <= 1.0e-10
        )
        legacy_incidence_valid = bool(
            math.isclose(incident_theta_deg, 80.0)
            and math.isclose(incident_phi_deg, 0.0)
        )
        task036_incidence_valid = bool(
            task036_raw_gate_valid
            and math.isfinite(incident_theta_deg)
            and 0.0 < incident_theta_deg < 90.0
            and math.isfinite(incident_phi_deg)
        )
        finite_results = (
            solver["linear_system_relative_residual"],
            solver["R_total"],
            solver["T_total"],
            solver["A_balance"],
            solver["A_volume_total"],
            solver["energy_closure_error_port_volume"],
            resource_authority["memory_authority_gib"],
        )
        raw_valid = bool(
            reference["status"] == "full3d_reference_pass"
            and reference["run_kind"] == "full-solve"
            and qualification["pass"] is True
            and reference["no_swap"] is True
            and source["tracked_source_dirty"] is False
            and source["stable_and_clean_after"] is True
            and solver["case_status"] == "completed"
            and solver["official_result"] is True
            and solver["full3d_reference_exported"] is True
            and polarization_kind in {"s", "p"}
            and (legacy_incidence_valid or task036_incidence_valid)
            and float(solver["linear_system_relative_residual"]) <= 1.0e-9
            and archive.name == "full3d_reference_samples.npz"
            and metadata.name == "full3d_reference_samples.json"
            and metadata.parent == archive.parent
            and len(commit_sha) == 40
            and all(
                character in "0123456789abcdef"
                for character in commit_sha
            )
            and len(archive_sha256) == 64
            and all(
                character in "0123456789abcdef"
                for character in archive_sha256
            )
            and all(np.isfinite(float(value)) for value in finite_results)
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise RuntimeError(
            f"Native full3D watchdog reference is incomplete: {path}"
        ) from error
    if not raw_valid:
        raise RuntimeError(
            f"Native full3D watchdog reference failed its raw Gate: {path}"
        )
    return {
        "record_type": "task034_full3d_reference",
        "metadata": {
            "commit_sha": commit_sha,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "host_environment_id": "WSL2-Ubuntu-24.04",
            "provenance": (
                "in-memory normalization of native full3D watchdog evidence"
            ),
        },
        "physical_model": {
            "wavelength_nm": 13.5,
            "incident_theta_deg": incident_theta_deg,
            "incident_grazing_deg": 90.0 - incident_theta_deg,
            "incident_phi_deg": incident_phi_deg,
            "polarization_kind": polarization_kind,
            "nedelec_degree": int(reference["degree"]),
            "mesh_h_nm": float(reference["h_nm"]),
            "mpi_size": int(reference["mpi_size"]),
            "grating_height_nm": config.get("grating_height"),
            "grating_width_x_nm": config.get("grating_width_x"),
            "mesh_axis_cell_counts": config.get(
                "mesh_axis_cell_counts_requested",
                config.get("mesh_axis_cell_counts"),
            ),
            "linear_solver": "direct_lu_mumps",
        },
        "results": {
            "case_status": solver["case_status"],
            "official_result": True,
            "linear_system_true_relative_residual": float(
                solver["linear_system_relative_residual"]
            ),
            "R_total": float(solver["R_total"]),
            "T_total": float(solver["T_total"]),
            "A_balance": float(solver["A_balance"]),
            "A_volume_total": float(solver["A_volume_total"]),
            "energy_closure_error_port_volume": float(
                solver["energy_closure_error_port_volume"]
            ),
            "external_memory_authority_gib": float(
                resource_authority["memory_authority_gib"]
            ),
        },
        "artifacts": {
            "ignored_run_root": run_root.as_posix(),
            "reference_npz_sha256": archive_sha256,
        },
        "qualification": {
            "phase1_reference_pass": True,
            "grid_converged": False,
            "no_swap": True,
            "watchdog_status": reference["status"],
            "heavy_artifacts_tracked": False,
        },
    }


def _validate_case080_reference_identity(
    reference: dict[str, Any],
    *,
    degree: int,
    h_nm: float,
    path: Path,
    polarization_kind: str = "s",
    incident_grazing_deg: float = 10.0,
    incident_phi_deg: float = 0.0,
    grating_height_nm: float | None = None,
    grating_width_x_nm: float | None = None,
    mesh_axis_cell_counts: tuple[int, int, int] | None = None,
) -> None:
    try:
        physical_model = reference["physical_model"]
        qualification = reference["qualification"]
        metadata = reference["metadata"]
        commit_sha = str(metadata["commit_sha"]).lower()
        identity_valid = (
            physical_model["nedelec_degree"] == degree
            and abs(float(physical_model["mesh_h_nm"]) - h_nm) <= 1.0e-12
            and abs(
                float(physical_model["incident_grazing_deg"])
                - incident_grazing_deg
            )
            <= 1.0e-12
            and abs(
                float(physical_model["incident_theta_deg"])
                - (90.0 - incident_grazing_deg)
            )
            <= 1.0e-12
            and abs(
                float(physical_model["incident_phi_deg"])
                - incident_phi_deg
            )
            <= 1.0e-12
            and physical_model["polarization_kind"] == polarization_kind
            and (
                grating_height_nm is None
                or math.isclose(
                    float(physical_model["grating_height_nm"]),
                    float(grating_height_nm),
                )
            )
            and (
                grating_width_x_nm is None
                or math.isclose(
                    float(physical_model["grating_width_x_nm"]),
                    float(grating_width_x_nm),
                )
            )
            and (
                mesh_axis_cell_counts is None
                or physical_model["mesh_axis_cell_counts"]
                == list(mesh_axis_cell_counts)
            )
            and abs(float(physical_model["wavelength_nm"]) - 13.5)
            <= 1.0e-12
            and qualification["phase1_reference_pass"] is True
            and metadata["git_dirty"] is False
            and metadata["tracked_source_dirty"] is False
            and len(commit_sha) == 40
            and all(character in "0123456789abcdef" for character in commit_sha)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Case080 reference identity is incomplete or invalid: {path}"
        ) from error
    if not identity_valid:
        raise RuntimeError(
            "Case080 reference identity does not match the requested p/h and "
            f"incident-angle {polarization_kind}-polarized 13.5-nm model: {path}"
        )


def _load_case080_reference(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
    *,
    polarization_kind: str = "s",
    incident_grazing_deg: float = 10.0,
    incident_phi_deg: float = 0.0,
    grating_height_nm: float | None = None,
    grating_width_x_nm: float | None = None,
    mesh_axis_cell_counts: tuple[int, int, int] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    reference_path = _case080_reference_path(
        degree, h_nm, reference_by_degree_and_h
    )
    if reference_path is None:
        return None
    if not reference_path.exists():
        raise FileNotFoundError(
            f"Pinned Case080 reference record is missing: {reference_path}"
        )
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Cannot load pinned Case080 reference record: {reference_path}"
        ) from error
    reference = _normalize_full3d_reference_record(
        reference, path=reference_path
    )
    _validate_case080_reference_identity(
        reference,
        degree=degree,
        h_nm=h_nm,
        path=reference_path,
        polarization_kind=polarization_kind,
        incident_grazing_deg=incident_grazing_deg,
        incident_phi_deg=incident_phi_deg,
        grating_height_nm=grating_height_nm,
        grating_width_x_nm=grating_width_x_nm,
        mesh_axis_cell_counts=mesh_axis_cell_counts,
    )
    return reference_path, reference


def _reference_comparison(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
    port_power: dict[str, Any],
) -> dict[str, Any] | None:
    if loaded_reference is None:
        return None
    reference_path, reference = loaded_reference
    results = reference["results"]
    return {
        "reference_file": str(reference_path.relative_to(ROOT)),
        "reference_commit_sha": reference["metadata"]["commit_sha"],
        "reference_grid_converged": reference["qualification"][
            "grid_converged"
        ],
        "hybrid_minus_full3d": {
            "R_total": float(port_power["R_total"] - results["R_total"]),
            "T_total": float(port_power["T_total"] - results["T_total"]),
            "A_balance": float(
                port_power["A_balance"] - results["A_balance"]
            ),
        },
        "full3d": {
            "R_total": results["R_total"],
            "T_total": results["T_total"],
            "A_balance": results["A_balance"],
            "A_volume_total": results["A_volume_total"],
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_explicit_full3d_reference_hash(
    path: Path,
    expected_sha256: str | None,
) -> str | None:
    if expected_sha256 is None:
        return None
    resolved = path if path.is_absolute() else ROOT / path
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise RuntimeError(
            f"Explicit Full3D reference is missing: {resolved}"
        )
    observed_sha256 = _sha256(resolved)
    if observed_sha256.lower() != expected_sha256.lower():
        raise RuntimeError(
            "Explicit Full3D reference SHA-256 mismatch: "
            f"expected {expected_sha256.lower()}, observed {observed_sha256}."
        )
    return observed_sha256


def _should_load_full3d_reference(
    *,
    incident_grazing_deg: float,
    polarization_kind: str,
    explicit_reference: Path | None,
) -> bool:
    """Load every explicit reference plus the legacy 10-degree S registry."""

    return explicit_reference is not None or (
        abs(float(incident_grazing_deg) - 10.0) <= 1.0e-12
        and polarization_kind == "s"
    )


def _reference_archive(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
) -> tuple[Path, Path, dict[str, Any]] | None:
    if loaded_reference is None:
        return None
    record_path, record = loaded_reference
    run_root = ROOT / record["artifacts"]["ignored_run_root"]
    archive = run_root / "full3d_reference_samples.npz"
    if not archive.exists():
        raise FileNotFoundError(
            f"Pinned full-3D selected-plane archive is missing: {archive}"
        )
    expected_sha = str(record["artifacts"]["reference_npz_sha256"])
    actual_sha = _sha256(archive)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Full-3D selected-plane archive SHA256 {actual_sha} != {expected_sha}."
        )
    return archive, record_path, record


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase6 real-QEP hybrid augmented direct diagnostic"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument(
        "--degree", type=int, choices=(1, 2, 3, 4, 5, 6), default=2
    )
    parser.add_argument(
        "--modal-h-nm",
        type=float,
        help=(
            "Optional independent cross-section QEP mesh size. The local 3D "
            "FEM mesh remains controlled by --h-nm."
        ),
    )
    parser.add_argument(
        "--modal-degree",
        type=int,
        choices=(1, 2, 3, 4, 5, 6),
        help=(
            "Optional independent cross-section QEP polynomial degree. The "
            "local 3D FEM degree remains controlled by --degree."
        ),
    )
    parser.add_argument(
        "--internal-propagation-model",
        choices=("continuous_beta", "full3d_uniform_cg"),
        default="continuous_beta",
        help=(
            "Axial propagation used between the two Hybrid interfaces. "
            "full3d_uniform_cg is an explicit same-p/h Full3D closure audit "
            "qualified only for a fixed rectangular, axis-aligned affine "
            "tensor-hexa mesh with uniform middle-region z spacing, one "
            "axial h, p1-p6, complex128, Floquet and sparse auxiliary DtN; "
            "nonuniform/local-h/curved/mixed meshes fail closed. "
            "continuous_beta remains the ordinary default."
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
            "Modal interface traction symbol. The scalar-CG derivative is an "
            "explicit diagnostic and requires full3d_uniform_cg propagation "
            "under the same uniform-z affine-hexa qualification scope; "
            "unsupported meshes fail closed without fallback. "
            "continuous_qep_beta remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            STANDARD_FULL_ASSEMBLY_BACKEND,
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        ),
        default=STANDARD_FULL_ASSEMBLY_BACKEND,
        help=(
            "Single public local-FE assembly port. Static condensation is "
            "explicit opt-in; standard_full remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help=(
            "Optional explicit same-p/h full3D descriptor. This is required "
            "for review-v5 coarse p3 candidates that are not in the legacy "
            "reference registry."
        ),
    )
    parser.add_argument(
        "--full3d-reference-sha256",
        help="Expected SHA-256 for any explicit --full3d-reference.",
    )
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the fixed-rectangular Task035c p6/h10 "
            "M120/M160 Hybrid path. Ordinary defaults remain unchanged."
        ),
    )
    parser.add_argument(
        "--task036-domain-robustness-gate",
        action="store_true",
        help=(
            "Explicitly open one clean-source Task036 same-p Full3D/Hybrid "
            "robustness point. Ordinary defaults remain unchanged."
        ),
    )
    parser.add_argument(
        "--task036-interface-preflight-only",
        action="store_true",
        help=(
            "Stop the frozen Review V5 A004-S shifted-interface diagnostic "
            "after strong-matrix assembly and before MUMPS."
        ),
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument(
        "--task036-y-invariant-n0-alias-preflight",
        action="store_true",
        help=(
            "Opt-in pre-solve overlap Gate for a declared y-invariant, "
            "physical n=0 subspace; ordinary defaults remain unchanged."
        ),
    )
    parser.add_argument(
        "--task036-dtn-direct-projection-audit",
        action="store_true",
        help=(
            "Opt-in independent recovered-field tangential projection audit; "
            "official auxiliary amplitudes and ordinary defaults are unchanged."
        ),
    )
    parser.add_argument(
        "--task036-scalar-stage4-reciprocal-basis",
        action="store_true",
        help=(
            "Opt in to bounded Task036 scalar-stage4 partition repair for "
            "both independent bases, then use an audited analytic reciprocal "
            "negative basis for coupling. Ordinary defaults are unchanged."
        ),
    )
    parser.add_argument(
        "--task036-mesh-axis-cell-counts",
        type=int,
        nargs=3,
        metavar=("NX", "NY", "NZ"),
        help=(
            "Task036 regression-only explicit tensor topology, forwarded to "
            "the existing config authority."
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
    parser.add_argument("--incident-grazing-deg", type=float, default=10.0)
    parser.add_argument("--incident-phi-deg", type=float, default=0.0)
    parser.add_argument("--grating-height-nm", type=float, default=120.0)
    parser.add_argument("--grating-width-x-nm", type=float, default=17.0)
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p"),
        default="s",
    )
    parser.add_argument("--requested-modes", type=int, default=2)
    parser.add_argument(
        "--candidate-modes",
        type=int,
        help=(
            "QEP candidate count per target branch before passive-direction filtering. "
            "Default keeps M for M<=6 and uses 2M for wider funnels."
        ),
    )
    parser.add_argument("--near-degenerate-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--block-rotation-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument(
        "--memory-stages",
        type=Path,
        help="Optional JSONL stage marker consumed by the external memory sampler.",
    )
    parser.add_argument(
        "--compare-modal-schur",
        action="store_true",
        help="Also build the Phase7 multi-RHS modal-Schur direct path and compare it with augmented.",
    )
    parser.add_argument(
        "--comparison-solver-path",
        choices=("fast", "minimal"),
        default="fast",
        help=(
            "Modal-Schur builder used by --compare-modal-schur. The fast default "
            "preserves Task32 behavior; Task33 formal comparisons use minimal."
        ),
    )
    parser.add_argument(
        "--solver-path",
        choices=(
            "augmented",
            "modal-schur-fast",
            "modal-schur-memory-minimal",
            "strong-trace-direct",
        ),
        default="augmented",
        help=(
            "Primary direct solve lifecycle. Non-augmented choices are standalone "
            "Phase10 memory paths and never retain the monolithic augmented factor. "
            "strong-trace-direct is a Task036-only Petrov--Galerkin research path."
        ),
    )
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default=(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
        ),
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    args = parser.parse_args(argv)
    if args.degree == 5 and not args.task036_domain_robustness_gate:
        parser.error(
            "p5 Hybrid is fail-closed outside the scoped Task036 gate."
        )
    if (
        args.degree == 6
        and not args.task035c_p6_h10_gate
        and not args.task036_domain_robustness_gate
    ):
        parser.error(
            "p6 is fail-closed; pass a scoped Task035c or Task036 Hybrid gate."
        )
    if (
        args.task035c_p6_h10_gate
        and args.task036_domain_robustness_gate
    ):
        parser.error(
            "Task035c and Task036 Hybrid gates are mutually exclusive."
        )
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes in TASK035C_P6_H10_MODE_COUNTS
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            in TASK035C_P6_H10_BACKENDS
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model
            == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to clean-source fixed "
                "rectangular p6/h10 S-polarized Hybrid M120/M160, explicit "
                "modal p6/h10, exact 2M pool, modal-schur-memory-minimal, "
                "the qualified discrete axial propagation/traction pair, "
                "10/110 nm interfaces, standard/static backend, and "
                "hash-bound historical and matching Full3D authorities."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
    ):
        parser.error(
            "Task035c p6 preflight authority arguments require "
            "--task035c-p6-h10-gate."
        )
    if args.task036_domain_robustness_gate:
        strong_trace_scope = bool(
            args.solver_path == "strong-trace-direct"
            and args.degree == 5
            and task036_strong_trace_anchor_scope(
                requested_modes=args.requested_modes,
                incident_grazing_deg=args.incident_grazing_deg,
                incident_phi_deg=args.incident_phi_deg,
                polarization_kind=args.polarization_kind,
                grating_height_nm=args.grating_height_nm,
                grating_width_x_nm=args.grating_width_x_nm,
            )
        )
        projection_only_scope = bool(
            args.solver_path == "modal-schur-memory-minimal"
            and args.degree in {5, 6}
            and args.requested_modes >= 120
        )
        task036_scope = bool(
            (strong_trace_scope or projection_only_scope)
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == args.degree
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.candidate_modes == 2 * args.requested_modes
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            and (
                (
                    strong_trace_scope
                    and task036_strong_trace_interface_scope(
                        bottom_interface_nm=args.bottom_interface_nm,
                        top_interface_nm=args.top_interface_nm,
                        incident_grazing_deg=args.incident_grazing_deg,
                        incident_phi_deg=args.incident_phi_deg,
                        polarization_kind=args.polarization_kind,
                        grating_height_nm=args.grating_height_nm,
                        grating_width_x_nm=args.grating_width_x_nm,
                    )
                )
                or (
                    projection_only_scope
                    and math.isclose(args.bottom_interface_nm, 10.0)
                    and math.isclose(args.top_interface_nm, 110.0)
                )
            )
            and args.graded_reference_h is None
            and 0.5 <= args.incident_grazing_deg <= 10.0
            and 0.0 <= args.incident_phi_deg <= 90.0
            and args.polarization_kind in {"s", "p"}
            and 115.0 <= args.grating_height_nm <= 125.0
            and 16.0 <= args.grating_width_x_nm <= 18.0
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model
            == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task036_mesh_axis_cell_counts == [6, 4, 14]
            and args.task036_y_invariant_n0_alias_preflight
            and args.task036_dtn_direct_projection_audit
            and args.task036_scalar_stage4_reciprocal_basis
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.allow_dirty_research
        )
        if not task036_scope:
            parser.error(
                "--task036-domain-robustness-gate requires a clean-source "
                "fixed rectangular p5/p6 h10 same-degree Hybrid point, "
                "MPI worker topology 6/4/14, M>=120 with exact 2M pool, "
                "static modal-Schur-minimal or scoped p5 strong-trace solve, "
                "discrete propagation/"
                "traction, alias/direct-projection/reciprocal audits, and an "
                "explicit same-input Full3D reference."
            )
        if args.task036_interface_preflight_only and not (
            strong_trace_scope
            and math.isclose(args.bottom_interface_nm, 30.0)
            and math.isclose(args.top_interface_nm, 90.0)
            or strong_trace_scope
            and math.isclose(args.bottom_interface_nm, 40.0)
            and math.isclose(args.top_interface_nm, 80.0)
        ):
            parser.error(
                "--task036-interface-preflight-only is restricted to the "
                "Review V5 A004-S M120 30/90 or 40/80 strong-trace points."
            )
    elif args.solver_path == "strong-trace-direct":
        parser.error(
            "strong-trace-direct is fail-closed outside "
            "--task036-domain-robustness-gate."
        )
    elif args.task036_interface_preflight_only:
        parser.error(
            "--task036-interface-preflight-only requires "
            "--task036-domain-robustness-gate."
        )
    if not math.isfinite(args.incident_phi_deg):
        parser.error("--incident-phi-deg must be finite.")
    for option, value in (
        ("--grating-height-nm", args.grating_height_nm),
        ("--grating-width-x-nm", args.grating_width_x_nm),
    ):
        if not math.isfinite(value) or value <= 0.0:
            parser.error(f"{option} must be finite and positive.")
    if args.full3d_reference_sha256 is not None and (
        args.full3d_reference is None
        or not valid_hex_digest(args.full3d_reference_sha256, 64)
    ):
        parser.error(
            "--full3d-reference-sha256 requires an explicit "
            "--full3d-reference and a 64-hex digest."
        )
    return args


def _task035c_worker_authority_gate(
    args: argparse.Namespace,
    *,
    current_source_sha: str | None,
    mpi_size: int,
) -> dict[str, Any] | None:
    if not args.task035c_p6_h10_gate:
        return None

    authority_path = args.task035c_p6_preflight_authority
    reference_path = args.full3d_reference
    if authority_path is None or reference_path is None:
        raise SystemExit("Task035c p6/h10 authority paths are required.")
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    reference_path = (
        reference_path if reference_path.is_absolute() else ROOT / reference_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 historical authority is unreadable: {exc}"
        ) from exc
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 Full3D reference is unreadable: {exc}"
        ) from exc
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_is_tracked = bool(
        authority_relative is not None
        and _git(
            "ls-files", "--error-unmatch", "--", authority_relative
        )
        is not None
    )
    preflight_gate = task035c_p6_h10_preflight_authority_gate(
        authority if isinstance(authority, dict) else None,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=_sha256(authority_path),
        authority_is_tracked=authority_is_tracked,
    )
    reference_gate = task035c_p6_h10_full3d_reference_gate(
        reference if isinstance(reference, dict) else None,
        expected_sha256=args.full3d_reference_sha256,
        observed_sha256=_sha256(reference_path),
        current_source_sha=current_source_sha,
        assembly_backend=args.stage4_full3d_assembly_backend,
        mpi_size=mpi_size,
        incident_grazing_deg=args.incident_grazing_deg,
        incident_phi_deg=args.incident_phi_deg,
    )
    gate = {
        "schema_version": "task035c.p6-h10-worker-authority-gate.v1",
        "pass": bool(preflight_gate["pass"] and reference_gate["pass"]),
        "historical_preflight": {
            **preflight_gate,
            "path": str(authority_path),
        },
        "matching_full3d_reference": {
            **reference_gate,
            "path": str(reference_path),
        },
    }
    gate["failures"] = [
        *(
            []
            if preflight_gate["pass"]
            else [
                f"historical_preflight:{failure}"
                for failure in preflight_gate["failures"]
            ]
        ),
        *(
            []
            if reference_gate["pass"]
            else [
                f"matching_full3d_reference:{failure}"
                for failure in reference_gate["failures"]
            ]
        ),
    ]
    if not gate["pass"]:
        raise SystemExit(
            f"Task035c p6/h10 worker authority failed: {gate['failures']}"
        )
    return gate


def _task036_worker_authority_gate(
    args: argparse.Namespace,
    *,
    current_source_sha: str | None,
    mpi_size: int,
) -> dict[str, Any] | None:
    if not args.task036_domain_robustness_gate:
        return None
    reference_path = args.full3d_reference
    if reference_path is None:
        raise SystemExit("Task036 requires a same-input Full3D reference.")
    reference_path = (
        reference_path
        if reference_path.is_absolute()
        else ROOT / reference_path
    ).resolve()
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task036 Full3D reference is unreadable: {exc}"
        ) from exc
    gate = task036_full3d_reference_gate(
        reference if isinstance(reference, dict) else None,
        expected_sha256=args.full3d_reference_sha256,
        observed_sha256=_sha256(reference_path),
        current_source_sha=current_source_sha,
        assembly_backend=args.stage4_full3d_assembly_backend,
        degree=args.degree,
        h_nm=args.h_nm,
        mpi_size=mpi_size,
        polarization_kind=args.polarization_kind,
        incident_grazing_deg=args.incident_grazing_deg,
        incident_phi_deg=args.incident_phi_deg,
        grating_height_nm=args.grating_height_nm,
        grating_width_x_nm=args.grating_width_x_nm,
        mesh_axis_cell_counts=tuple(args.task036_mesh_axis_cell_counts),
    )
    gate["path"] = str(reference_path)
    if mpi_size != 8:
        gate["checks"]["task036_mpi8_worker"] = False
        gate["failures"].append("task036_mpi8_worker")
        gate["pass"] = False
    else:
        gate["checks"]["task036_mpi8_worker"] = True
    if not gate["pass"]:
        raise SystemExit(
            f"Task036 worker authority failed: {gate['failures']}"
        )
    return gate


def main() -> None:
    args = _parse_args()
    if args.full3d_reference is not None:
        try:
            _verify_explicit_full3d_reference_hash(
                args.full3d_reference,
                args.full3d_reference_sha256,
            )
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
    if args.h_nm <= 0.0:
        raise SystemExit("--h-nm must be positive.")
    modal_h_nm = (
        float(args.h_nm)
        if args.modal_h_nm is None
        else float(args.modal_h_nm)
    )
    modal_degree = (
        int(args.degree)
        if args.modal_degree is None
        else int(args.modal_degree)
    )
    if modal_h_nm <= 0.0:
        raise SystemExit("--modal-h-nm must be positive.")
    if not (
        0.0 < args.bottom_interface_nm < args.top_interface_nm < 120.0
    ):
        raise SystemExit(
            "Task33 buffer interfaces must satisfy "
            "0 < bottom-interface-nm < top-interface-nm < 120."
        )
    if args.graded_reference_h is not None:
        if args.modal_h_nm is not None or args.modal_degree is not None:
            raise SystemExit(
                "Independent modal h/p is not combined with the Task034 "
                "graded local-mesh research path."
            )
        if args.degree not in (2, 3):
            raise SystemExit("The Task034 fixed-p graded path is restricted to p2/p3.")
        if (
            args.bottom_interface_nm != 10.0
            or args.top_interface_nm != 110.0
        ):
            raise SystemExit(
                "The first Task033 graded path is qualified only at the "
                "reviewed 10/110 nm matching interfaces."
            )
        if not np.isclose(args.h_nm, args.graded_reference_h):
            raise SystemExit("--h-nm must equal --graded-reference-h.")
        if args.graded_coarse_factor <= 1.0:
            raise SystemExit("--graded-coarse-factor must be greater than one.")
    if not 0.0 < args.incident_grazing_deg < 90.0:
        raise SystemExit("--incident-grazing-deg must lie strictly between 0 and 90.")
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least 2.")
    candidate_modes = (
        int(args.candidate_modes)
        if args.candidate_modes is not None
        else (
            int(args.requested_modes)
            if args.requested_modes <= 6
            else 2 * int(args.requested_modes)
        )
    )
    if candidate_modes < args.requested_modes:
        raise SystemExit("--candidate-modes must be at least --requested-modes.")
    if args.near_degenerate_tolerance <= 0.0:
        raise SystemExit("--near-degenerate-tolerance must be positive.")
    if args.block_rotation_tolerance <= 0.0:
        raise SystemExit("--block-rotation-tolerance must be positive.")
    if args.compare_modal_schur and args.solver_path != "augmented":
        raise SystemExit("--compare-modal-schur requires --solver-path augmented.")
    if (
        args.internal_traction_model == "scalar_cg_discrete_derivative"
        and args.internal_propagation_model != "full3d_uniform_cg"
    ):
        raise SystemExit(
            "scalar_cg_discrete_derivative traction requires "
            "--internal-propagation-model full3d_uniform_cg."
        )
    task33_variant = bool(
        args.degree != 2
        or modal_degree != args.degree
        or not np.isclose(modal_h_nm, args.h_nm)
        or args.bottom_interface_nm != 10.0
        or args.top_interface_nm != 110.0
        or args.graded_reference_h is not None
        or not np.isclose(args.incident_grazing_deg, 10.0)
        or not np.isclose(args.incident_phi_deg, 0.0)
        or args.polarization_kind != "s"
        or not np.isclose(args.grating_height_nm, 120.0)
        or not np.isclose(args.grating_width_x_nm, 17.0)
        or args.task036_domain_robustness_gate
        or args.internal_propagation_model != "continuous_beta"
        or args.internal_traction_model != "continuous_qep_beta"
    )
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    if (
        args.task035c_p6_h10_gate
        and comm.size not in TASK035C_P6_H10_MPI_SIZES
    ):
        raise SystemExit(
            "Task035c p6/h10 Hybrid is restricted to MPI1/2/4/8."
        )
    task035c_p6_gate = _task035c_worker_authority_gate(
        args,
        current_source_sha=provenance.get("commit_sha"),
        mpi_size=comm.size,
    )
    task036_authority_gate = _task036_worker_authority_gate(
        args,
        current_source_sha=provenance.get("commit_sha"),
        mpi_size=comm.size,
    )

    _claim_memory_stage_file(
        comm,
        args.memory_stages,
        owner_path=args.output,
    )

    def mark_stage(stage: str) -> None:
        if comm.rank == 0 and args.memory_stages is not None:
            with args.memory_stages.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "stage": stage,
                            "elapsed_seconds": time.perf_counter() - total_started,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def progress(message: str) -> None:
        if comm.rank == 0:
            print(message, flush=True)

    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    cfg.stage4_full3d_assembly_backend = (
        args.stage4_full3d_assembly_backend
    )
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.incident_theta_deg = 90.0 - float(args.incident_grazing_deg)
    cfg.incident_phi_deg = float(args.incident_phi_deg)
    cfg.polarization_kind = args.polarization_kind
    cfg.grating_height = float(args.grating_height_nm)
    cfg.grating_width_x = float(args.grating_width_x_nm)
    cfg.dtn_y_invariant_n0_alias_preflight = bool(
        args.task036_y_invariant_n0_alias_preflight
    )
    cfg.dtn_auxiliary_direct_projection_audit = bool(
        args.task036_dtn_direct_projection_audit
    )
    if args.task036_mesh_axis_cell_counts is not None:
        cfg.mesh_axis_cell_counts = tuple(
            int(value) for value in args.task036_mesh_axis_cell_counts
        )
    modal_cfg = target_stage4_config(
        degree=modal_degree,
        h_nm=modal_h_nm,
    )
    modal_cfg.incident_theta_deg = cfg.incident_theta_deg
    modal_cfg.incident_phi_deg = cfg.incident_phi_deg
    modal_cfg.polarization_kind = cfg.polarization_kind
    modal_cfg.grating_height = cfg.grating_height
    modal_cfg.grating_width_x = cfg.grating_width_x
    modal_cfg.dtn_y_invariant_n0_alias_preflight = (
        cfg.dtn_y_invariant_n0_alias_preflight
    )
    modal_cfg.dtn_auxiliary_direct_projection_audit = (
        cfg.dtn_auxiliary_direct_projection_audit
    )
    modal_cfg.mesh_axis_cell_counts = cfg.mesh_axis_cell_counts
    operators = None
    positive = None
    negative = None
    independent_negative = None
    independent_negative_summary = None
    independent_reciprocal_pairing = None
    positive_qep_profiles = None
    negative_qep_profiles = None
    analytic_reciprocal_gate = {
        "requested": bool(args.task036_scalar_stage4_reciprocal_basis),
        "pass": None,
        "basis_origin_exact": None,
        "construction_audit_status_pass": None,
    }
    bottom = None
    top = None
    coupling = None
    system = None
    solution = None
    schur_system = None
    schur_solution = None
    primary_schur_system = None
    factor_inventory = None
    primary_release_audit = None
    primary_system_snapshot = None
    primary_schur_snapshot = None
    record = None
    graded_plan = None
    graded_bottom_mesh = None
    graded_top_mesh = None

    def finite_spectrum_capacity_record(
        *,
        direction: str,
        selection,
        solver_report,
    ) -> dict[str, Any]:
        """Preserve a clean measured negative when singular K2 yields infinity roots."""

        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        case = {
            "material_kind": "stage4_xy",
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": modal_degree,
            "modal_h_nm": modal_h_nm,
            "internal_propagation_model": (
                args.internal_propagation_model
            ),
            "internal_traction_model": args.internal_traction_model,
            "discrete_axial_qualification_scope": (
                _discrete_axial_qualification_scope(
                    args.internal_propagation_model,
                    args.internal_traction_model,
                )
            ),
            "requested_modes_per_direction": args.requested_modes,
            "candidate_modes_per_target_branch": candidate_modes,
            "near_degenerate_tolerance": args.near_degenerate_tolerance,
            "block_rotation_tolerance": args.block_rotation_tolerance,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "middle_length_nm": args.top_interface_nm - args.bottom_interface_nm,
            "wavelength_nm": cfg.lambda0,
            "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
            "polarization_kind": cfg.polarization_kind,
            "mesh_policy": "reviewed_stage4_axis_plan",
            "graded_reference_h_nm": args.graded_reference_h,
            "graded_coarse_factor": None,
            "graded_plan_hash": None,
            "graded_plan": None,
        }
        selection_record = _directional_selection_summary(selection)
        capacity = {
            "status": "insufficient_finite_admissible_modes",
            "direction": direction,
            "requested_modes_per_direction": args.requested_modes,
            "delivered_finite_admissible_modes": selection.selected_modes,
            "finite_candidate_count_both_directions": (
                selection.finite_candidate_count
            ),
            "numerically_infinite_candidate_count": (
                selection.numerically_infinite_candidate_count
            ),
            "finite_spectrum_abs_beta_h_cutoff": (
                NUMERICAL_INFINITY_BETA_H_CUTOFF
            ),
            "finite_spectrum_abs_beta_cutoff_per_nm": (
                selection.abs_beta_cutoff
            ),
            "first_rejected_numerical_infinity_beta_per_nm": (
                selection_record[
                    "first_rejected_numerical_infinity_beta_per_nm"
                ]
            ),
            "leading_coefficient_singular_by_design": (
                operators.leading_coefficient_singular_by_design
            ),
            "pair_tolerance_relaxed": False,
            "left_pair_relative_error_tolerance": 1.0e-7,
        }
        solver_profiles = {}
        if positive_qep_profiles is not None:
            solver_profiles["positive"] = positive_qep_profiles
        if negative_qep_profiles is not None:
            solver_profiles["negative"] = negative_qep_profiles
        direction_profiles = dict(solver_profiles.get(direction) or {})
        direction_profiles["right"] = solver_report.profile_provenance()
        solver_profiles[direction] = direction_profiles
        return {
            "schema_version": 1,
            "benchmark_id": "task033_hybrid_modal_basis_capacity",
            "timestamp_utc": timestamp,
            "status": "insufficient_finite_admissible_modes",
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (
                    args.internal_traction_model
                ),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task036_scalar_stage4_reciprocal_basis_requested": bool(
                    args.task036_scalar_stage4_reciprocal_basis
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task33_variant": True,
                "provenance": (
                    "clean_task033_finite_spectrum_capacity_negative"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task033_finite_spectrum_capacity_research"
                ),
            },
            "case": case,
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                f"{direction}_solver_converged_modes": (
                    solver_report.converged_modes
                ),
                "solver_profiles": solver_profiles,
                f"{direction}_directional_selection": selection_record,
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "dense_interface_square_formed": False,
                "full_field_or_mode_gathered": False,
            },
            "solve": {"true_relative_residual": None},
            "validation": {
                "port_power": None,
                "external_diffraction_orders": None,
            },
            "physical_field_reconstruction": None,
            "modal_schur_comparison": None,
            "object_payload_ledger": {
                "mode_count_per_direction": selection.selected_modes,
                "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
                "dense_interface_square_formed": False,
            },
            "full3d_reference_comparison": None,
            "gates": {"finite_admissible_mode_capacity": False},
            "qualification": {
                "integration_pass": False,
                "algebraic_chain_pass": False,
                "task033_physical_truncation_allowed": False,
                "clean_source_integration_record": False,
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": False,
                "modal_basis_capacity_pass": False,
                "capacity_disposition": "insufficient_finite_admissible_modes",
                "official_record": False,
                "boundary": (
                    "Measured finite-spectrum capacity negative; numerical-infinity "
                    "roots from singular K2 are rejected before adjoint pairing."
                ),
            },
            "modal_basis_capacity": capacity,
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }

    def near_degenerate_partition_record(
        error: NearDegenerateBlockPartitionSplitError,
    ) -> dict[str, Any]:
        """Preserve a deterministic pre-Hybrid fail-closed mode audit."""

        repair = error.audit.get("repair")
        repair = repair if isinstance(repair, dict) else {}
        bounded_repair_exhausted = bool(
            args.task036_scalar_stage4_reciprocal_basis
            and repair.get("requested") is True
            and repair.get("final_pass") is False
        )
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": 1,
            "benchmark_id": "task036_hybrid_near_degenerate_partition_guard",
            "timestamp_utc": timestamp,
            "status": str(error.audit["status"]),
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
            },
            "case": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": modal_degree,
                "modal_h_nm": modal_h_nm,
                "requested_modes_per_direction": args.requested_modes,
                "candidate_modes_per_target_branch": candidate_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "incident_phi_deg": cfg.incident_phi_deg,
                "polarization_kind": cfg.polarization_kind,
                "task036_scalar_stage4_reciprocal_basis_requested": bool(
                    args.task036_scalar_stage4_reciprocal_basis
                ),
            },
            "mode_partition_audit": error.audit,
            "solve": {"true_relative_residual": None},
            "gates": {
                "cross_block_biorthogonality_within_tolerance": False,
                "bounded_task036_partition_repair_pass": (
                    False
                    if args.task036_scalar_stage4_reciprocal_basis
                    else None
                ),
            },
            "qualification": {
                "integration_pass": False,
                "algebraic_chain_pass": False,
                "hybrid_p_production_qualified": False,
                "deferred_architecture_required": True,
                "bounded_task036_partition_repair_exhausted": (
                    bounded_repair_exhausted
                ),
                "mode_partition_stop_disposition": (
                    "bounded_repair_exhausted"
                    if bounded_repair_exhausted
                    else "deferred_architecture_required"
                ),
                "official_record": False,
                "boundary": (
                    (
                        "Hybrid solve was not entered; the bounded Task036 "
                        "scalar-stage4 partition repair was attempted and "
                        "exhausted, so further work requires a separately "
                        "reviewed numerical architecture."
                    )
                    if bounded_repair_exhausted
                    else (
                        "Hybrid solve was not entered; joint subspace rotation "
                        "requires a separately reviewed numerical architecture."
                    )
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }

    def dtn_trace_alias_record(
        error: DtnTraceAliasError,
    ) -> dict[str, Any]:
        """Preserve an opt-in pre-solve alias rejection as a compact record."""

        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": 1,
            "benchmark_id": "task036_dtn_n0_trace_alias_preflight",
            "timestamp_utc": timestamp,
            "status": str(error.audit["status"]),
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": (
                    "python -m benchmarks.run_task032_phase6_augmented "
                    + " ".join(
                        shlex.quote(value) for value in sys.argv[1:]
                    )
                ),
                "mpi_size": comm.size,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
            },
            "case": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": modal_degree,
                "modal_h_nm": modal_h_nm,
                "mesh_axis_cell_counts_requested": (
                    None
                    if cfg.mesh_axis_cell_counts_requested is None
                    else list(cfg.mesh_axis_cell_counts_requested)
                ),
                "incident_grazing_deg": (
                    90.0 - cfg.incident_theta_deg
                ),
                "incident_phi_deg": cfg.incident_phi_deg,
                "polarization_kind": cfg.polarization_kind,
            },
            "dtn_trace_alias_preflight": error.audit,
            "solve": {
                "entered": False,
                "true_relative_residual": None,
            },
            "gates": {
                "dtn_y_invariant_n0_trace_alias_preflight": False,
            },
            "qualification": {
                "integration_pass": False,
                "algebraic_chain_pass": False,
                "hybrid_p_production_qualified": False,
                "controlled_negative": True,
                "official_record": False,
                "boundary": (
                    "The opt-in trace-alias Gate rejected the topology before "
                    "matrix insertion or linear solve."
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }

    try:
        mark_stage("cross_section_eigen_assembly")
        started = time.perf_counter()
        if args.graded_reference_h is not None:
            from src.geometry.task034_adaptive_mesh import (
                Task034Stage4Geometry,
                build_task034_conforming_graded_plan,
                build_task034_graded_local_mesh_pair,
            )

            graded_plan = build_task034_conforming_graded_plan(
                reference_h_nm=args.graded_reference_h,
                geometry=Task034Stage4Geometry.from_config(
                    cfg,
                    bottom_interface_z_nm=args.bottom_interface_nm,
                    top_interface_z_nm=args.top_interface_nm,
                ),
                profile=args.graded_profile,
                coarse_factor=args.graded_coarse_factor,
                comm_size=comm.size,
            )
            graded_bottom_mesh, graded_top_mesh = (
                build_task034_graded_local_mesh_pair(cfg, graded_plan)
            )
            cross_section = build_matching_cross_section(
                cfg,
                "stage4_xy",
                x_values=graded_plan.x_values,
                y_values=graded_plan.y_values,
            )
        else:
            cross_section = build_matching_cross_section(
                modal_cfg,
                "stage4_xy",
            )
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=modal_degree
        )
        operators = assemble_quadratic_beta_operators(
            modal_cfg, cross_section, spaces
        )
        poynting_evaluator = PoyntingFluxEvaluator(
            modal_cfg, cross_section, spaces
        )
        target = analytic_homogeneous_beta(modal_cfg, modal_cfg.n_air)
        timings["cross_section_and_qep_assembly"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: cross-section QEP assembled")

        mark_stage("cross_section_eigen_solve")
        started = time.perf_counter()
        positive_right, positive_report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=candidate_modes,
            strict_profile=True,
        )
        progress("Task32 Phase6: positive right QEP modes complete")
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(
                NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm
            ),
        )
        if len(positive_right) != args.requested_modes:
            for mode in positive_right:
                mode.destroy()
            if positive_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="positive",
                    selection=positive_selection,
                    solver_report=positive_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Positive finite candidate pool did not deliver enough passive "
                f"forward modes: {positive_selection.direction_counts}."
            )
        mark_stage("mode_classification")
        positive = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            task036_scalar_stage4_partition_repair=(
                args.task036_scalar_stage4_reciprocal_basis
            ),
            poynting_evaluator=poynting_evaluator,
            log=progress,
            strict_qep_profile=True,
        )
        positive_qep_profiles = {
            "right": positive_report.profile_provenance(),
            "adjoint": positive.adjoint_solver_report.profile_provenance(),
        }
        progress("Task32 Phase6: positive adjoint basis complete")
        negative_right, negative_report = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=candidate_modes,
            strict_profile=True,
        )
        progress("Task32 Phase6: negative right QEP modes complete")
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(
                NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm
            ),
        )
        if len(negative_right) != args.requested_modes:
            for mode in negative_right:
                mode.destroy()
            if negative_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="negative",
                    selection=negative_selection,
                    solver_report=negative_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Negative finite candidate pool did not deliver enough passive "
                f"backward modes: {negative_selection.direction_counts}."
            )
        independent_negative = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            task036_scalar_stage4_partition_repair=(
                args.task036_scalar_stage4_reciprocal_basis
            ),
            poynting_evaluator=poynting_evaluator,
            log=progress,
            strict_qep_profile=True,
        )
        negative_qep_profiles = {
            "right": negative_report.profile_provenance(),
            "adjoint": (
                independent_negative.adjoint_solver_report.profile_provenance()
            ),
        }
        progress("Task32 Phase6: independent negative adjoint basis complete")
        independent_negative_summary = _basis_summary(independent_negative)
        independent_pairs = pair_reciprocal_mode_bases(
            operators,
            positive,
            independent_negative,
        )
        independent_reciprocal_pairing = _reciprocal_pairing_summary(
            independent_pairs
        )
        if args.task036_scalar_stage4_reciprocal_basis:
            negative = build_scalar_stage4_reciprocal_negative_basis(
                modal_cfg,
                cross_section,
                spaces,
                operators,
                positive,
                poynting_evaluator=poynting_evaluator,
            )
            construction_audit = negative.basis_construction_audit
            construction_audit = (
                construction_audit
                if isinstance(construction_audit, dict)
                else {}
            )
            analytic_reciprocal_gate.update(
                {
                    "basis_origin_exact": (
                        negative.basis_origin
                        == "analytic_scalar_stage4_reciprocal"
                    ),
                    "construction_audit_status_pass": (
                        construction_audit.get("status") == "pass"
                    ),
                }
            )
            analytic_reciprocal_gate["pass"] = bool(
                analytic_reciprocal_gate["basis_origin_exact"]
                and analytic_reciprocal_gate[
                    "construction_audit_status_pass"
                ]
            )
            if not analytic_reciprocal_gate["pass"]:
                negative.destroy()
                negative = None
                raise RuntimeError(
                    "Task036 analytic reciprocal negative basis failed its "
                    f"runner Gate: {analytic_reciprocal_gate}."
                )
            independent_negative.destroy()
            independent_negative = None
            progress(
                "Task32 Phase6: audited analytic reciprocal negative basis "
                "selected for coupling"
            )
        else:
            negative = independent_negative
            independent_negative = None
        progress(
            "Task32 Phase6: delivered basis counts "
            f"positive={len(positive.modes)}/{positive_report.converged_modes}, "
            f"negative={len(negative.modes)}/{negative_report.converged_modes}"
        )
        preview_count = min(len(positive.modes), 12)
        progress(
            "Task32 Phase6: positive beta preview "
            f"{[complex(mode.beta) for mode in positive.modes[:preview_count]]} "
            f"(showing {preview_count}/{len(positive.modes)})"
        )
        progress(
            "Task32 Phase6: positive near-degenerate group count "
            f"{len(positive.groups)}; first groups="
            f"{[group.indices for group in positive.groups[:8]]}"
        )
        pairs = pair_reciprocal_mode_bases(operators, positive, negative)
        timings["positive_and_negative_biorthogonal_bases"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: real positive/negative QEP bases complete")

        mark_stage("local_fem_dtn_assembly")
        started = time.perf_counter()
        bottom = assemble_hybrid_local_dtn_system(
            cfg,
            "bottom",
            bottom_interface_z_nm=args.bottom_interface_nm,
            top_interface_z_nm=args.top_interface_nm,
            local_mesh_override=graded_bottom_mesh,
        )
        top = assemble_hybrid_local_dtn_system(
            cfg,
            "top",
            bottom_interface_z_nm=args.bottom_interface_nm,
            top_interface_z_nm=args.top_interface_nm,
            local_mesh_override=graded_top_mesh,
        )
        timings["two_local_fem_dtn_systems"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: bottom/top local FEM-DtN systems complete")

        mark_stage("interface_projection_and_coupling")
        started = time.perf_counter()
        coupling = build_hybrid_internal_mode_coupling(
            cfg,
            spaces,
            positive,
            negative,
            bottom,
            top,
            length_nm=args.top_interface_nm - args.bottom_interface_nm,
            propagation_model=args.internal_propagation_model,
            modal_traction_model=args.internal_traction_model,
            log=progress,
        )
        timings["internal_modal_coupling"] = _max_elapsed(comm, started)

        started = time.perf_counter()
        if args.solver_path == "augmented":
            mark_stage("augmented_matrix_and_factor")
            system = build_hybrid_augmented_direct_system(
                bottom, top, coupling
            )
            timings["primary_system_build"] = _max_elapsed(comm, started)
            timings["monolithic_assembly"] = timings["primary_system_build"]
            progress("Task32 Phase6: monolithic augmented AIJ complete")
            solution = solve_hybrid_augmented_direct(
                system,
                bottom,
                top,
                coupling,
            )
        elif args.solver_path == "strong-trace-direct":
            mark_stage("strong_trace_petrov_galerkin_assembly")
            system = build_hybrid_strong_trace_direct_system(
                bottom, top, coupling
            )
            timings["primary_system_build"] = _max_elapsed(comm, started)
            timings["monolithic_assembly"] = timings["primary_system_build"]
            progress(
                "Task036: square strong-trace Petrov--Galerkin AIJ complete"
            )
            if args.task036_interface_preflight_only:
                material_audit = _task036_middle_material_audit(
                    cfg,
                    cross_section,
                    bottom_interface_nm=args.bottom_interface_nm,
                    top_interface_nm=args.top_interface_nm,
                )
                expected_length = float(
                    args.top_interface_nm - args.bottom_interface_nm
                )
                expected_cells = int(round(expected_length / args.h_nm))
                xy_match = (
                    np.array_equal(
                        cross_section.x_values,
                        cross_section.axis_plan.x_values,
                    )
                    and np.array_equal(
                        cross_section.y_values,
                        cross_section.axis_plan.y_values,
                    )
                    and tuple(bottom.local_mesh.mesh_cells[:2])
                    == tuple(cross_section.mesh_cells)
                    and tuple(top.local_mesh.mesh_cells[:2])
                    == tuple(cross_section.mesh_cells)
                )
                bottom_retained = int(
                    sum(map(len, system.bottom_interface.retained_rows_by_rank))
                )
                top_retained = int(
                    sum(map(len, system.top_interface.retained_rows_by_rank))
                )
                strong_trace = {
                    "interface_trace_rows": [
                        len(system.bottom_interface.interface_rows),
                        len(system.top_interface.interface_rows),
                    ],
                    "retained_rows": [bottom_retained, top_retained],
                    "D_R_identity_error": [
                        system.bottom_interface.projection_identity_error,
                        system.top_interface.projection_identity_error,
                    ],
                    "trace_complement_unknown_count": int(
                        system.bottom_interface.trace_complement_unknown_count
                        + system.top_interface.trace_complement_unknown_count
                    ),
                    "dense_interface_square_formed": bool(
                        system.dense_interface_square_formed
                    ),
                }
                matrix_stats = dict(system.matrix_stats)
                matrix_rows = int(matrix_stats["matrix_rows"])
                matrix_nnz = int(matrix_stats["matrix_nnz_used"])
                binding_checks = {
                    "source_and_full3d_authority": task036_authority_gate["pass"],
                    "middle_material_z_invariant": material_audit[
                        "epsilon_x_y_z_equals_epsilon_x_y"
                    ],
                    "interfaces_are_actual_mesh_planes": (
                        material_audit["bottom_interface_on_actual_plan"]
                        and material_audit["top_interface_on_actual_plan"]
                    ),
                    "cross_section_xy_matches_local_trace_grid": xy_match,
                    "modal_length_bound_to_interfaces": math.isclose(
                        coupling.propagation.length_nm, expected_length
                    ),
                    "forward_scalar_cg_cell_count_bound": (
                        coupling.propagation.forward.axial_cell_count
                        == expected_cells
                    ),
                    "backward_scalar_cg_cell_count_bound": (
                        coupling.propagation.backward.axial_cell_count
                        == expected_cells
                    ),
                    "traction_beta_bound_to_selected_model": (
                        coupling.modal_traction_model
                        == "scalar_cg_discrete_derivative"
                    ),
                    "strong_D_R_identity_le_1e_10": (
                        max(strong_trace["D_R_identity_error"])
                        <= 1.0e-10
                    ),
                    "no_trace_complement_unknown": (
                        strong_trace["trace_complement_unknown_count"] == 0
                    ),
                    "no_dense_interface_square": (
                        not strong_trace["dense_interface_square_formed"]
                    ),
                }
                _verify_source_stable_at_end(
                    comm,
                    provenance,
                    args.verified_clean_sha,
                    args.allow_dirty_research,
                )
                rss = comm.gather(_historical_peak_rss_mb(), root=0)
                preflight_pass = all(binding_checks.values())
                record = {
                    "schema_version": "task036.review-v5-interface-preflight.v1",
                    "status": (
                        "assemble_only_preflight_pass"
                        if preflight_pass
                        else "assemble_only_preflight_failed"
                    ),
                    "metadata": {
                        **provenance,
                        "command": (
                            "python -m benchmarks.run_task032_phase6_augmented "
                            + " ".join(
                                shlex.quote(value) for value in sys.argv[1:]
                            )
                        ),
                        "mpi_size": comm.size,
                        "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                        "full3d_authority_gate": task036_authority_gate,
                    },
                    "case": {
                        "point": "A004-S",
                        "degree": args.degree,
                        "h_nm": args.h_nm,
                        "requested_modes_per_direction": args.requested_modes,
                        "bottom_interface_nm": args.bottom_interface_nm,
                        "top_interface_nm": args.top_interface_nm,
                        "middle_length_nm": expected_length,
                        "middle_scalar_cg_cells": expected_cells,
                        "local_z_cells": [
                            bottom.local_mesh.mesh_cells[2],
                            top.local_mesh.mesh_cells[2],
                        ],
                        "total_endcap_thickness_nm": (
                            bottom.local_mesh.interface_z_nm
                            - bottom.local_mesh.external_z_nm
                            + top.local_mesh.external_z_nm
                            - top.local_mesh.interface_z_nm
                        ),
                    },
                    "material_and_mesh_identity": material_audit,
                    "binding_checks": binding_checks,
                    "hybrid_system": {
                        "matrix_stats": matrix_stats,
                        "strong_trace": strong_trace,
                        "structural_comparison": {
                            "rows_vs_old_ratio": matrix_rows / 13_296,
                            "matrix_nnz_vs_old_ratio": matrix_nnz / 8_901_696,
                            "rows_vs_full3d_ratio": matrix_rows / 46_656,
                            "matrix_nnz_vs_full3d_ratio": matrix_nnz / 26_952_096,
                            "endcap_thickness_vs_old_ratio": (
                                2.0 * (args.bottom_interface_nm + 10.0) / 40.0
                            ),
                            "factor_risk": (
                                "below_full3d_assembly_factor_unknown"
                                if matrix_rows < 46_656
                                and matrix_nnz < 26_952_096
                                else "full3d_or_higher_structural_risk"
                            ),
                        },
                    },
                    "timing_seconds_max_rank": {
                        **timings,
                        "total": _max_elapsed(comm, total_started),
                    },
                    "historical_peak_rss_mb_by_rank": rss,
                    "memory_semantics": (
                        "per-rank ru_maxrss historical peaks; preflight only, "
                        "not simultaneous whole-job authority"
                    ),
                    "qualification": {
                        "integration_pass": False,
                        "assemble_only_preflight_pass": preflight_pass,
                        "factorization_entered": False,
                        "solve_entered": False,
                        "ordinary_default_changed": False,
                    },
                }
                raise _InterfacePreflightStop
            mark_stage("strong_trace_mumps_factor_and_solve")
            solution = solve_hybrid_strong_trace_direct(
                system,
                bottom,
                top,
                coupling,
                recover_static=False,
            )
        else:
            builder = (
                build_hybrid_modal_schur_direct_system
                if args.solver_path == "modal-schur-fast"
                else build_hybrid_modal_schur_memory_minimal_system
            )
            primary_schur_system = builder(
                bottom, top, coupling, stage_callback=mark_stage
            )
            timings["primary_system_build"] = _max_elapsed(comm, started)
            progress(
                "Task32 Phase10: standalone "
                f"{primary_schur_system.lifecycle_strategy} Schur system complete"
            )
            solution = solve_hybrid_modal_schur_direct(
                primary_schur_system,
                bottom,
                top,
                coupling,
                stage_callback=mark_stage,
            )
        mark_stage("official_rta")
        validation = (
            evaluate_hybrid_strong_trace_solution(
                cfg, bottom, top, coupling, solution
            )
            if args.solver_path == "strong-trace-direct"
            else evaluate_hybrid_augmented_solution(
                cfg, bottom, top, coupling, solution
            )
        )
        port_power = validation["port_power"]
        modal_schur_comparison = None
        if args.compare_modal_schur:
            started = time.perf_counter()
            comparison_builder = (
                build_hybrid_modal_schur_direct_system
                if args.comparison_solver_path == "fast"
                else build_hybrid_modal_schur_memory_minimal_system
            )
            comparison_solver_path = (
                "modal-schur-fast"
                if args.comparison_solver_path == "fast"
                else "modal-schur-memory-minimal"
            )
            schur_system = comparison_builder(bottom, top, coupling)
            timings["modal_schur_build"] = _max_elapsed(comm, started)
            schur_solution = solve_hybrid_modal_schur_direct(
                schur_system, bottom, top, coupling
            )
            schur_validation = evaluate_hybrid_augmented_solution(
                cfg, bottom, top, coupling, schur_solution
            )
            modal_difference = np.asarray(
                schur_solution.modal_amplitudes - solution.modal_amplitudes,
                dtype=np.complex128,
            )
            modal_scale = max(
                float(np.linalg.norm(schur_solution.modal_amplitudes)),
                float(np.linalg.norm(solution.modal_amplitudes)),
                1.0e-30,
            )
            rta_delta = {
                key: float(
                    schur_validation["port_power"][key]
                    - validation["port_power"][key]
                )
                for key in ("R_total", "T_total", "A_balance")
            }
            comparison_gates = {
                "modal_coefficients_relative_error_le_1e-9": (
                    float(np.linalg.norm(modal_difference) / modal_scale) <= 1.0e-9
                ),
                "bottom_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.bottom, solution.bottom)
                    <= 1.0e-9
                ),
                "top_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.top, solution.top)
                    <= 1.0e-9
                ),
                "modal_schur_full_residual_le_1e-9": (
                    schur_solution.relative_residual <= 1.0e-9
                    and schur_solution.modal_relative_residual <= 1.0e-9
                ),
                "rta_absolute_delta_le_1e-10": max(
                    abs(value) for value in rta_delta.values()
                )
                <= 1.0e-10,
                "no_dense_interface_square": (
                    not schur_system.dense_interface_square_formed
                ),
                "multi_rhs_single_factor_context_per_local_block": (
                    schur_system.multi_rhs_count == 2 * args.requested_modes + 1
                ),
            }
            modal_schur_comparison = {
                "status": (
                    "pass" if all(comparison_gates.values()) else "failed"
                ),
                "comparison_solver_path": comparison_solver_path,
                "comparison_solver_path_argument": (
                    args.comparison_solver_path
                ),
                "comparison_lifecycle_strategy": (
                    schur_system.lifecycle_strategy
                ),
                "multi_rhs_count": schur_system.multi_rhs_count,
                "modal_schur_shape": list(schur_system.modal_schur.shape),
                "modal_schur_bytes": int(schur_system.modal_schur.nbytes),
                "modal_schur_condition": schur_system.modal_schur_condition,
                "dense_interface_square_formed": (
                    schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (
                    schur_system.full_field_or_mode_gathered
                ),
                "transient_dense_rhs_solution_bytes": (
                    schur_system.transient_dense_rhs_solution_bytes
                ),
                "factor_setup_seconds": schur_system.factor_setup_seconds,
                "multi_rhs_solve_seconds": schur_system.multi_rhs_solve_seconds,
                "modal_solve_seconds": schur_solution.modal_solve_seconds,
                "recovery_seconds": schur_solution.recovery_seconds,
                "residuals": {
                    "combined_relative": schur_solution.relative_residual,
                    "bottom_relative": schur_solution.bottom_relative_residual,
                    "top_relative": schur_solution.top_relative_residual,
                    "modal_relative": schur_solution.modal_relative_residual,
                },
                "augmented_vs_schur": {
                    "modal_coefficients_relative_error": float(
                        np.linalg.norm(modal_difference) / modal_scale
                    ),
                    "bottom_solution_relative_error": _relative_vector_error(
                        schur_solution.bottom, solution.bottom
                    ),
                    "top_solution_relative_error": _relative_vector_error(
                        schur_solution.top, solution.top
                    ),
                    "interface_e_projection_combined_residual_delta": float(
                        schur_validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                        - validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                    ),
                    "RTA_delta": rta_delta,
                },
                "gates": comparison_gates,
                "memory_comparison_semantics": (
                    "Correctness runner retains augmented and Schur factors concurrently; "
                    "its process peak is not a standalone Schur memory measurement."
                ),
            }
            progress(
                "Task32 Phase7: "
                f"{comparison_solver_path} direct comparison complete"
            )
            schur_solution.destroy()
            schur_solution = None
            schur_system.destroy()
            schur_system = None

        if system is not None:
            if solution.ksp is None:
                raise RuntimeError(
                    "Monolithic Hybrid factor disappeared before inventory."
                )
            factor_inventory = {
                (
                    "strong_trace_monolithic"
                    if args.solver_path == "strong-trace-direct"
                    else "augmented"
                ): _petsc_factor_inventory(solution.ksp)
            }
            primary_system_snapshot = {
                "shape": list(system.A.getSize()),
                "matrix_stats": dict(system.matrix_stats),
                "block_shapes": dict(system.block_shapes),
                "inserted_nnz_by_block": dict(
                    system.inserted_nnz_by_block
                ),
                "dense_interface_square_formed": bool(
                    system.dense_interface_square_formed
                ),
            }
            if args.solver_path == "strong-trace-direct":
                primary_system_snapshot["strong_trace"] = {
                    "formulation": (
                        "strong_trace_subspace_petrov_galerkin"
                    ),
                    "bottom_interface_trace_rows": int(
                        len(system.bottom_interface.interface_rows)
                    ),
                    "top_interface_trace_rows": int(
                        len(system.top_interface.interface_rows)
                    ),
                    "bottom_original_interface_rows": int(
                        system.bottom_interface.original_interface_rows
                    ),
                    "top_original_interface_rows": int(
                        system.top_interface.original_interface_rows
                    ),
                    "bottom_retained_rows": int(
                        sum(
                            map(
                                len,
                                system.bottom_interface.retained_rows_by_rank,
                            )
                        )
                    ),
                    "top_retained_rows": int(
                        sum(
                            map(
                                len,
                                system.top_interface.retained_rows_by_rank,
                            )
                        )
                    ),
                    "bottom_removed_floquet_slave_rows": int(
                        len(system.bottom_interface.removed_slave_rows)
                    ),
                    "top_removed_floquet_slave_rows": int(
                        len(system.top_interface.removed_slave_rows)
                    ),
                    "bottom_D_R_identity_error": float(
                        system.bottom_interface.projection_identity_error
                    ),
                    "top_D_R_identity_error": float(
                        system.top_interface.projection_identity_error
                    ),
                    "bottom_geometry_projection_support_match": bool(
                        system.bottom_interface.geometry_projection_support_match
                    ),
                    "top_geometry_projection_support_match": bool(
                        system.top_interface.geometry_projection_support_match
                    ),
                    "trace_complement_unknown_count": int(
                        system.bottom_interface.trace_complement_unknown_count
                        + system.top_interface.trace_complement_unknown_count
                    ),
                    "old_modal_constraint_retained": bool(
                        system.old_modal_constraint_retained
                    ),
                    "dense_interface_square_formed": bool(
                        system.dense_interface_square_formed
                    ),
                }
        else:
            factor_inventory = dict(primary_schur_system.factor_inventory)
            primary_system_snapshot = None
            primary_schur_snapshot = {
                "shape": list(primary_schur_system.modal_schur.shape),
                "bytes": int(primary_schur_system.modal_schur.nbytes),
                "condition": float(
                    primary_schur_system.modal_schur_condition
                ),
                "multi_rhs_count": int(
                    primary_schur_system.multi_rhs_count
                ),
                "transient_dense_rhs_solution_bytes": dict(
                    primary_schur_system.transient_dense_rhs_solution_bytes
                ),
                "factor_setup_seconds": dict(
                    primary_schur_system.factor_setup_seconds
                ),
                "multi_rhs_solve_seconds": dict(
                    primary_schur_system.multi_rhs_solve_seconds
                ),
                "lifecycle_strategy": str(
                    primary_schur_system.lifecycle_strategy
                ),
                "recovery_refactor_required": bool(
                    primary_schur_system.recovery_refactor_required
                ),
                "dense_interface_square_formed": bool(
                    primary_schur_system.dense_interface_square_formed
                ),
            }

        mark_stage("solver_objects_released_before_field_output")
        release_before_mb = _current_rss_mb()
        if system is not None:
            solution_release = solution.release_factorization()
            system.destroy()
            if args.solver_path == "strong-trace-direct":
                mark_stage("strong_trace_static_field_recovery")
                started = time.perf_counter()
                recover_hybrid_strong_trace_static_fields(
                    solution,
                    bottom,
                    top,
                    coupling,
                )
                timings["strong_trace_static_field_recovery"] = (
                    _max_elapsed(comm, started)
                )
        else:
            solution_release = {
                "released": True,
                "already_released": False,
                "retained_physical_fields": True,
                "released_objects": [
                    "bottom_local_KSP_MUMPS_factor",
                    "top_local_KSP_MUMPS_factor",
                ],
                "reason": (
                    "modal Schur solution vectors are independent of the "
                    "released local factors"
                ),
            }
            primary_schur_system.destroy()
            primary_schur_system = None
        if cfg.dtn_auxiliary_direct_projection_audit:
            mark_stage("hybrid_candidate_direct_projection_audit")
            started = time.perf_counter()
        candidate_direct_projection_audit = (
            evaluate_hybrid_recovered_direct_projection_audit(
                cfg,
                bottom,
                top,
                solution,
            )
        )
        validation["auxiliary_direct_tangential_projection_audit"] = (
            candidate_direct_projection_audit
        )
        if cfg.dtn_auxiliary_direct_projection_audit:
            timings["hybrid_candidate_direct_projection_audit"] = (
                _max_elapsed(comm, started)
            )
            progress(
                "Task36: Hybrid candidate recovered-trace direct projection "
                "audit complete"
            )
            mark_stage("solver_objects_released_before_field_output")
        bottom.destroy()
        top.destroy()
        gc.collect()
        PETSc.garbage_cleanup(comm)
        gc.collect()
        local_trim = _trim_process_heap()
        release_after_mb = _current_rss_mb()
        release_before_by_rank = comm.allgather(release_before_mb)
        release_after_by_rank = comm.allgather(release_after_mb)
        release_before_sum = (
            None
            if any(value is None for value in release_before_by_rank)
            else float(sum(float(value) for value in release_before_by_rank))
        )
        release_after_sum = (
            None
            if any(value is None for value in release_after_by_rank)
            else float(sum(float(value) for value in release_after_by_rank))
        )
        primary_release_audit = {
            "release_before_field_output": True,
            "global_factor_released_before_static_recovery": bool(
                args.solver_path != "strong-trace-direct"
                or solution_release.get("released", False)
                or solution_release.get("already_released", False)
            ),
            "solution_release": solution_release,
            "released_objects": [
                "primary_direct_factorization",
                "primary_system_matrix_and_rhs",
                "bottom_local_matrix_and_rhs",
                "top_local_matrix_and_rhs",
            ],
            "retained_objects": [
                "recovered_or_split_physical_field_vectors",
                "modal_amplitudes",
                "coupling_and_mode_metadata",
            ],
            "current_rss_before_mb_by_rank": release_before_by_rank,
            "current_rss_after_mb_by_rank": release_after_by_rank,
            "sum_current_rss_before_mb": release_before_sum,
            "sum_current_rss_after_mb": release_after_sum,
            "rss_measurement_semantics": (
                "diagnostic in-process phase-local rank samples; not the "
                "external synchronized process-tree RSS/PSS/USS authority"
            ),
            "heap_trim_by_rank": comm.allgather(local_trim),
        }
        pinned_reference_case = _should_load_full3d_reference(
            incident_grazing_deg=args.incident_grazing_deg,
            polarization_kind=args.polarization_kind,
            explicit_reference=args.full3d_reference,
        )
        explicit_reference = args.full3d_reference
        if explicit_reference is not None and not explicit_reference.is_absolute():
            explicit_reference = ROOT / explicit_reference
        reference_registry = (
            None
            if explicit_reference is None
            else {(args.degree, float(args.h_nm)): explicit_reference}
        )
        loaded_reference = (
            _load_case080_reference(
                args.degree,
                args.h_nm,
                reference_by_degree_and_h=reference_registry,
                polarization_kind=args.polarization_kind,
                incident_grazing_deg=args.incident_grazing_deg,
                incident_phi_deg=args.incident_phi_deg,
                grating_height_nm=args.grating_height_nm,
                grating_width_x_nm=args.grating_width_x_nm,
                mesh_axis_cell_counts=(
                    None
                    if args.task036_mesh_axis_cell_counts is None
                    else tuple(args.task036_mesh_axis_cell_counts)
                ),
            )
            if pinned_reference_case
            else None
        )
        reference = (
            _reference_comparison(loaded_reference, port_power)
            if pinned_reference_case
            else None
        )
        reference_archive = (
            _reference_archive(loaded_reference) if pinned_reference_case else None
        )
        reference_interface_planes_available = False
        reference_available_z_nm: list[float] = []
        if reference_archive is not None:
            archive_path, reference_record_path, reference_record = reference_archive
            with np.load(archive_path) as archive:
                sample_x = np.asarray(archive["x_nm"], dtype=np.float64)
                sample_y = np.asarray(archive["y_nm"], dtype=np.float64)
                reference_z = np.asarray(archive["z_nm"], dtype=np.float64)
            reference_available_z_nm = [float(value) for value in reference_z]
            in_middle = (
                (reference_z >= args.bottom_interface_nm - 1.0e-10)
                & (reference_z <= args.top_interface_nm + 1.0e-10)
            )
            sample_z = reference_z[in_middle]
            if len(sample_z) == 0:
                raise RuntimeError(
                    "The Full3D archive has no selected plane inside the "
                    "requested modal middle."
                )
            reference_interface_planes_available = bool(
                np.count_nonzero(
                    np.isclose(
                        reference_z,
                        args.bottom_interface_nm,
                        rtol=0.0,
                        atol=1.0e-10,
                    )
                )
                == 1
                and np.count_nonzero(
                    np.isclose(
                        reference_z,
                        args.top_interface_nm,
                        rtol=0.0,
                        atol=1.0e-10,
                    )
                )
                == 1
            )
        else:
            sample_x = cfg.x_min + (
                np.arange(40, dtype=np.float64) + 0.5
            ) * cfg.period_x / 40.0
            sample_y = cfg.y_min + (
                np.arange(20, dtype=np.float64) + 0.5
            ) * cfg.period_y / 20.0
            sample_z = np.linspace(
                args.bottom_interface_nm,
                args.top_interface_nm,
                5,
                dtype=np.float64,
            )
        mark_stage("middle_plane_reconstruction")
        started = time.perf_counter()
        reconstructor = ModalFieldReconstructor(
            cfg,
            cross_section,
            spaces,
            positive,
            negative,
            bottom_z_nm=args.bottom_interface_nm,
            top_z_nm=args.top_interface_nm,
            propagation=coupling.propagation,
            positive_traction_beta_per_nm=(
                coupling.positive_traction_beta_per_nm
            ),
            negative_traction_beta_per_nm=(
                coupling.negative_traction_beta_per_nm
            ),
        )
        (
            reconstruction_positive_traction_beta,
            reconstruction_negative_traction_beta,
        ) = reconstructor.traction_beta_per_nm
        reconstruction_beta_equals_traction_beta = bool(
            np.array_equal(
                reconstruction_positive_traction_beta,
                np.asarray(
                    coupling.positive_traction_beta_per_nm,
                    dtype=np.complex128,
                ),
            )
            and np.array_equal(
                reconstruction_negative_traction_beta,
                np.asarray(
                    coupling.negative_traction_beta_per_nm,
                    dtype=np.complex128,
                ),
            )
        )
        if not reconstruction_beta_equals_traction_beta:
            raise RuntimeError(
                "Hybrid field reconstruction lost the selected traction beta."
            )
        trace_modal_oracle = None
        if reference_archive is not None:
            if reference_interface_planes_available:
                mark_stage("full3d_trace_modal_oracle")
                trace_modal_oracle = reconstructor.full3d_trace_modal_oracle(
                    archive_path
                )
                mark_stage("middle_plane_reconstruction")
            else:
                trace_modal_oracle = {
                    "status": "not_available_missing_interface_planes",
                    "requested_interface_z_nm": [
                        float(args.bottom_interface_nm),
                        float(args.top_interface_nm),
                    ],
                    "available_z_nm": reference_available_z_nm,
                    "authority": (
                        "Review V4 exact 11-plane trace artifact remains the "
                        "interface-projection authority."
                    ),
                }
        selected_planes = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            sample_z,
        )
        interface_samples = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            np.asarray(
                [args.bottom_interface_nm, args.top_interface_nm],
                dtype=np.float64,
            ),
        )
        interface_continuity = interface_field_continuity(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            interface_samples,
        )
        for side in ("bottom", "top"):
            interface_continuity[side]["traction_hcurl_dual"] = (
                validation["fe_modal_traction_equilibrium"][f"{side}_dual"]
            )
        absorption = hybrid_volume_absorption(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            reconstructor,
            solution.modal_amplitudes,
            incident_power=float(port_power["incident_power_code_units"]),
        )
        field_reference = None
        if reference_archive is not None:
            field_reference = compare_selected_planes_to_reference(
                selected_planes, archive_path
            )
            expected_reference_npz_sha256 = str(
                reference_record["artifacts"]["reference_npz_sha256"]
            ).lower()
            observed_reference_npz_sha256 = _sha256(archive_path)
            field_reference.update(
                {
                    "reference_npz_sha256_expected": expected_reference_npz_sha256,
                    "reference_npz_sha256_observed": observed_reference_npz_sha256,
                    "reference_record": str(reference_record_path.relative_to(ROOT)),
                    "reference_record_sha256": _sha256(reference_record_path),
                    "reference_record_source_commit_full_sha": str(
                        reference_record["metadata"]["commit_sha"]
                    ).lower(),
                    "reference_binding_verified": (
                        expected_reference_npz_sha256
                        == observed_reference_npz_sha256
                    ),
                }
            )
        absorption["R_plus_T_plus_A_volume"] = float(
            port_power["R_total"]
            + port_power["T_total"]
            + absorption["A_volume_total"]
        )
        absorption["energy_closure_error"] = float(
            absorption["R_plus_T_plus_A_volume"] - 1.0
        )
        absorption["hybrid_A_balance_minus_A_volume_total"] = float(
            port_power["A_balance"] - absorption["A_volume_total"]
        )
        if reference_archive is not None:
            absorption["full3d_A_volume_total"] = float(
                reference_record["results"]["A_volume_total"]
            )
            absorption["hybrid_minus_full3d_A_volume_total"] = float(
                absorption["A_volume_total"]
                - reference_record["results"]["A_volume_total"]
            )
        physical_fields = {
            "sample_payload_bytes": int(
                selected_planes.electric_V_per_m.nbytes
                + selected_planes.magnetic_A_per_m.nbytes
            ),
            "sample_grid_shape_z_y_x_component": list(
                selected_planes.electric_V_per_m.shape
            ),
            "full_middle_volume_reconstructed": False,
            "interface_continuity": interface_continuity,
            "full3d_trace_modal_oracle": trace_modal_oracle,
            "volume_absorption": absorption,
            "selected_plane_full3d_comparison": field_reference,
        }
        timings["physical_field_reconstruction"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: physical interface/absorption/selected-plane reconstruction complete")
        mark_stage("record_and_release")
        directions_valid = (
            all(mode.direction == "forward" for mode in positive.modes)
            and all(mode.direction == "backward" for mode in negative.modes)
            and all(mode.passive_branch_valid for mode in positive.modes)
            and all(mode.passive_branch_valid for mode in negative.modes)
        )
        reciprocal_valid = len(pairs) == args.requested_modes and all(
            pair.opposite_direction and pair.passive_branches_valid
            for pair in pairs
        )
        forward_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        backward_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        finite_rta = all(
            np.isfinite(port_power[key])
            for key in ("R_total", "T_total", "A_balance", "R_plus_T")
        )
        gates = {
            "task036_analytic_reciprocal_basis_gate": (
                bool(analytic_reciprocal_gate["pass"])
                if args.task036_scalar_stage4_reciprocal_basis
                else True
            ),
            "exact_requested_mode_count_delivered": (
                len(positive.modes) == args.requested_modes
                and len(negative.modes) == args.requested_modes
            ),
            "requested_forward_and_backward_passive_bases": directions_valid,
            "reciprocal_pairing_complete": reciprocal_valid,
            "biorthogonality_identity_error_le_1e-6": (
                max(positive.max_identity_error, negative.max_identity_error)
                <= 1.0e-6
            ),
            "right_and_left_qep_residuals_le_1e-8": (
                max(
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in negative.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in negative.modes
                    ),
                )
                <= 1.0e-8
            ),
            "stable_propagation_no_growing_factor": bool(
                max(
                    np.max(np.abs(forward_factors), initial=0.0),
                    np.max(np.abs(backward_factors), initial=0.0),
                )
                <= 1.0 + 1.0e-12
            ),
            "monolithic_true_relative_residual_le_1e-9": (
                solution.relative_residual <= 1.0e-9
            ),
            "primary_direct_true_relative_residual_le_1e-9": (
                solution.relative_residual <= 1.0e-9
            ),
            "external_port_rta_finite": finite_rta,
        }
        if args.solver_path == "strong-trace-direct":
            strong_sides = tuple(
                solution.strong_residuals[side]
                for side in ("bottom", "top")
            )
            strong_snapshot = primary_system_snapshot["strong_trace"]
            gates.update(
                {
                    "strong_noninterface_fe_relative_residual_le_1e-9": (
                        max(
                            side["noninterface_fe"]["formal_relative"]
                            for side in strong_sides
                        )
                        <= 1.0e-9
                    ),
                    "strong_modal_petrov_flux_relative_residual_le_1e-8": (
                        max(
                            side["modal_petrov_flux"]["relative"]
                            for side in strong_sides
                        )
                        <= 1.0e-8
                    ),
                    "strong_trace_identity_relative_residual_le_1e-10": (
                        max(
                            side["strong_trace_identity"]["relative"]
                            for side in strong_sides
                        )
                        <= 1.0e-10
                    ),
                    "strong_external_dtn_relative_residual_le_1e-9": (
                        max(
                            side["external_dtn"]["formal_relative"]
                            for side in strong_sides
                        )
                        <= 1.0e-9
                    ),
                    "strong_D_R_identity_error_le_1e-10": (
                        max(
                            strong_snapshot[
                                "bottom_D_R_identity_error"
                            ],
                            strong_snapshot["top_D_R_identity_error"],
                        )
                        <= 1.0e-10
                    ),
                    "strong_geometry_projection_support_complete": (
                        strong_snapshot[
                            "bottom_geometry_projection_support_match"
                        ]
                        and strong_snapshot[
                            "top_geometry_projection_support_match"
                        ]
                    ),
                    "strong_trace_complement_unknown_count_zero": (
                        strong_snapshot["trace_complement_unknown_count"] == 0
                    ),
                    "strong_old_modal_constraint_absent": (
                        strong_snapshot["old_modal_constraint_retained"]
                        is False
                    ),
                    "strong_dense_interface_square_absent": (
                        strong_snapshot["dense_interface_square_formed"]
                        is False
                    ),
                    "diagnostic_interface_e_projection_relative_residual_le_1e-8": (
                        validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                        <= 1.0e-8
                    ),
                }
            )
        else:
            gates.update(
                {
                    "interface_e_projection_relative_residual_le_1e-8": (
                        validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                        <= 1.0e-8
                    ),
                    "fe_modal_traction_equilibrium_relative_residual_le_1e-8": (
                        max(
                            validation["fe_modal_traction_equilibrium"][
                                "bottom_relative_residual"
                            ],
                            validation["fe_modal_traction_equilibrium"][
                                "top_relative_residual"
                            ],
                        )
                        <= 1.0e-8
                    ),
                }
            )
        if solution.bottom_recovered is not None:
            if solution.top_recovered is None:
                raise RuntimeError(
                    "Hybrid static recovery completed on only one local side."
                )
            recovered_sides = (
                solution.bottom_recovered,
                solution.top_recovered,
            )
            gates.update(
                {
                    "condensed_full_operator_relative_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "linear_system_relative_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_eliminated_interior_max_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "eliminated_cell_interior_max_abs_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_full_surface_mode_matrix_not_retained": all(
                        not item.streaming_audit[
                            "full_surface_mode_matrix_retained"
                        ]
                        for item in recovered_sides
                    ),
                    "condensed_full_global_matrix_not_allocated": all(
                        not item.streaming_audit[
                            "full_global_matrix_allocated"
                        ]
                        for item in recovered_sides
                    ),
                }
            )
            if args.solver_path == "strong-trace-direct":
                gates.pop(
                    "condensed_full_operator_relative_residual_le_1e-9"
                )
                gates[
                    "diagnostic_historical_all_interface_fe_residual_le_1e-9"
                ] = bool(
                    max(
                        float(
                            item.full_operator_residual.get(
                                "historical_all_interface_fe_linear_system_relative_residual",
                                math.inf,
                            )
                        )
                        for item in recovered_sides
                    )
                    <= 1.0e-9
                )
        if physical_fields is not None:
            interface_physical = physical_fields["interface_continuity"]
            absorption_physical = physical_fields["volume_absorption"]
            sampled_e_gate = (
                "diagnostic_sampled_interface_e_t_relative_l2_le_5e-3"
                if args.solver_path == "strong-trace-direct"
                else "sampled_interface_e_t_relative_l2_le_5e-3"
            )
            assembled_h_gate = (
                "diagnostic_assembled_interface_h_t_exact_dual_le_1e-8"
                if args.solver_path == "strong-trace-direct"
                else "assembled_interface_h_t_exact_dual_le_1e-8"
            )
            gates.update(
                {
                    sampled_e_gate: (
                        max(
                            interface_physical[side]["electric_tangential"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 5.0e-3
                    ),
                    "diagnostic_sampled_traction_density_l2_proxy_le_1e-2": (
                        max(
                            interface_physical[side][
                                "traction_density_l2_proxy"
                            ][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 1.0e-2
                    ),
                    assembled_h_gate: (
                        max(
                            interface_physical[side][
                                "traction_hcurl_dual"
                            ]["relative_dual"]
                            for side in ("bottom", "top")
                        )
                        <= 1.0e-8
                    ),
                    "volume_energy_closure_abs_le_1e-5": (
                        abs(absorption_physical["energy_closure_error"])
                        <= 1.0e-5
                    ),
                }
            )
            planes_physical = physical_fields[
                "selected_plane_full3d_comparison"
            ]
            if planes_physical is not None:
                gates.update(
                    {
                        "volume_absorption_full3d_abs_delta_le_1e-5": (
                            abs(
                                absorption_physical[
                                    "hybrid_minus_full3d_A_volume_total"
                                ]
                            )
                            <= 1.0e-5
                        ),
                        "middle_plane_e_relative_l2_le_5e-3": (
                            planes_physical[
                                "max_middle_plane_electric_relative_l2"
                            ]
                            <= 5.0e-3
                        ),
                        "middle_plane_h_relative_l2_le_5e-3": (
                            planes_physical[
                                "max_middle_plane_magnetic_relative_l2"
                            ]
                            <= 5.0e-3
                        ),
                    }
                )
        task036_hybrid_projection_checks: dict[str, bool] = {}
        if args.task036_domain_robustness_gate:
            task036_hybrid_projection_checks = (
                _task036_hybrid_candidate_direct_projection_checks(
                    validation[
                        "auxiliary_direct_tangential_projection_audit"
                    ]
                )
            )
            gates.update(task036_hybrid_projection_checks)
        physical_gate_prefixes = (
            "sampled_interface_",
            "assembled_interface_",
            "volume_",
            "middle_plane_",
        )
        algebraic_chain_pass = all(
            value
            for key, value in gates.items()
            if (
                not key.startswith(physical_gate_prefixes)
                and not key.startswith("diagnostic_")
            )
        )
        integration_pass = all(
            value
            for key, value in gates.items()
            if not key.startswith("diagnostic_")
        )
        task033_physical_truncation_allowed = bool(
            not task33_variant or args.requested_modes >= 80
        )
        interface_closure_gate_names = (
            (
                "strong_trace_identity_relative_residual_le_1e-10",
                "strong_modal_petrov_flux_relative_residual_le_1e-8",
                "strong_external_dtn_relative_residual_le_1e-9",
                "volume_energy_closure_abs_le_1e-5",
            )
            if args.solver_path == "strong-trace-direct"
            else (
                "interface_e_projection_relative_residual_le_1e-8",
                "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
                "sampled_interface_e_t_relative_l2_le_5e-3",
                "assembled_interface_h_t_exact_dual_le_1e-8",
                "volume_energy_closure_abs_le_1e-5",
            )
        )
        interface_closure_pass = bool(
            physical_fields is not None
            and all(
                gates.get(name, False)
                for name in interface_closure_gate_names
            )
        )
        hybrid_p_disposition = _hybrid_p_disposition(
            cfg.polarization_kind,
            full3d_physical_solution_exists=loaded_reference is not None,
            # One PDE cannot prove adjacent-M convergence. Task036 leaves the
            # raw shard pending for its analyzer; historical paths retain
            # their explicit rank-insufficient quarantine.
            modal_rank_sufficient=(
                None
                if args.task036_domain_robustness_gate
                else False
            ),
            modal_rank_evidence=(
                (
                    "pending_review_v3_absolute_full3d_channel_comparison"
                    if args.solver_path == "strong-trace-direct"
                    else "pending_adjacent_M_comparison_in_task036_analyzer"
                )
                if args.task036_domain_robustness_gate
                else "not_qualified_no_M_convergence_funnel_in_this_runner"
            ),
            interface_closure_pass=interface_closure_pass,
            interface_closure_gate_names=interface_closure_gate_names,
            diagnostic_projection_bug=bool(
                args.task036_domain_robustness_gate
                and not all(task036_hybrid_projection_checks.values())
            ),
            diagnostic_projection_evidence=(
                (
                    "candidate_recovered_trace_direct_projection_gate="
                    f"{all(task036_hybrid_projection_checks.values())}; "
                    "candidate_max_absolute_outgoing_difference="
                    f"{validation['auxiliary_direct_tangential_projection_audit'].get('max_absolute_outgoing_projection_difference')}"
                )
                if args.task036_domain_robustness_gate
                else (
                    "task036_tangential_projection_fix_inactive_outside_"
                    "task036_domain_gate"
                )
            ),
        )
        projection_stats = {
            "bottom": _petsc_matrix_stats(
                coupling.bottom.projection, assemble=False
            ),
            "top": _petsc_matrix_stats(
                coupling.top.projection, assemble=False
            ),
        }
        if factor_inventory is None or primary_release_audit is None:
            raise RuntimeError(
                "Hybrid solver lifecycle evidence was not captured."
            )
        full_vector_size = int(positive.modes[0].right.right_full.getSize())
        reduced_vector_size = int(
            positive.modes[0].right.right_reduced.getSize()
        )
        eigenvector_bytes = int(
            2
            * args.requested_modes
            * 2
            * (full_vector_size + reduced_vector_size)
            * np.dtype(PETSc.ScalarType).itemsize
        )
        active_column_counts = {
            "bottom": distributed_active_column_count(
                coupling.bottom.projection
            ),
            "top": distributed_active_column_count(coupling.top.projection),
        }
        object_payload_ledger = {
            "scalar_bytes": int(np.dtype(PETSc.ScalarType).itemsize),
            "index_bytes": int(np.dtype(PETSc.IntType).itemsize),
            "interface_active_dofs": {
                side: result.global_count
                for side, result in active_column_counts.items()
            },
            "interface_active_column_count_diagnostics": {
                side: result.to_dict()
                for side, result in active_column_counts.items()
            },
            "mode_count_per_direction": args.requested_modes,
            "retained_right_left_eigenvector_bytes": eigenvector_bytes,
            "projection_matrix": projection_stats,
            "modal_schur_bytes": (
                0
                if primary_schur_snapshot is None
                else int(primary_schur_snapshot["bytes"])
            ),
            "local_or_augmented_factor_inventory": factor_inventory,
            "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
            "dense_interface_square_formed": False,
        }
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": (
                "task032_phase6_hybrid_augmented_direct"
                if args.degree == 2
                and args.bottom_interface_nm == 10.0
                and args.top_interface_nm == 110.0
                and args.solver_path == "augmented"
                else (
                    "task032_phase10_hybrid_modal_schur_direct"
                    if args.degree == 2
                    and args.bottom_interface_nm == 10.0
                    and args.top_interface_nm == 110.0
                    else "task033_high_order_or_buffer_hybrid_direct"
                )
            ),
            "timestamp_utc": timestamp,
            "status": (
                hybrid_p_disposition["primary_status"]
                if hybrid_p_disposition["applicable"]
                else (
                "algebraic_smoke_pass_physical_truncation_not_qualified"
                if task33_variant
                and algebraic_chain_pass
                and not task033_physical_truncation_allowed
                else (
                    "physical_integration_pass_mode_convergence_pending"
                    if integration_pass
                    else "physical_integration_failed"
                )
                )
            ),
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (
                    args.internal_traction_model
                ),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task036_scalar_stage4_reciprocal_basis_requested": bool(
                    args.task036_scalar_stage4_reciprocal_basis
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task036_domain_robustness_authority_gate": (
                    task036_authority_gate
                ),
                "task33_variant": task33_variant,
                "provenance": (
                    (
                        "clean_task033_high_order_or_buffer_hybrid_integration"
                        if task33_variant
                        else "clean_task032_phase6_real_qep_hybrid_integration"
                    )
                    if not provenance["tracked_source_dirty"]
                    else (
                        "dirty_task033_high_order_or_buffer_hybrid_research"
                        if task33_variant
                        else "dirty_task032_phase6_real_qep_hybrid_research"
                    )
                ),
            },
            "case": {
                "material_kind": "stage4_xy",
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": modal_degree,
                "modal_h_nm": modal_h_nm,
                "internal_propagation_model": (
                    args.internal_propagation_model
                ),
                "internal_traction_model": args.internal_traction_model,
                "discrete_axial_qualification_scope": (
                    _discrete_axial_qualification_scope(
                        args.internal_propagation_model,
                        args.internal_traction_model,
                    )
                ),
                "requested_modes_per_direction": args.requested_modes,
                "candidate_modes_per_target_branch": candidate_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "task036_scalar_stage4_reciprocal_basis_requested": bool(
                    args.task036_scalar_stage4_reciprocal_basis
                ),
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "middle_length_nm": (
                    args.top_interface_nm - args.bottom_interface_nm
                ),
                "wavelength_nm": cfg.lambda0,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "incident_phi_deg": cfg.incident_phi_deg,
                "polarization_kind": cfg.polarization_kind,
                "grating_height_nm": cfg.grating_height,
                "grating_width_x_nm": cfg.grating_width_x,
                "mesh_policy": (
                    "task034_periodic_conforming_fixed_p_graded_opt_in"
                    if graded_plan is not None
                    else "reviewed_stage4_axis_plan"
                ),
                "mesh_axis_cell_counts_requested": (
                    None
                    if cfg.mesh_axis_cell_counts_requested is None
                    else list(cfg.mesh_axis_cell_counts_requested)
                ),
                "mesh_axis_cell_counts_actual_full_plan": list(
                    cross_section.axis_plan.mesh_cells_resolved
                ),
                "mesh_axis_cell_counts_actual_cross_section": [
                    int(cross_section.mesh_cells[0]),
                    int(cross_section.mesh_cells[1]),
                ],
                "mesh_axis_cell_counts_actual_local_fem": {
                    "bottom": list(bottom.local_mesh.mesh_cells),
                    "top": list(top.local_mesh.mesh_cells),
                },
                "graded_reference_h_nm": args.graded_reference_h,
                "graded_profile": (
                    args.graded_profile if graded_plan is not None else None
                ),
                "graded_coarse_factor": (
                    args.graded_coarse_factor
                    if graded_plan is not None
                    else None
                ),
                "graded_plan_hash": (
                    graded_plan.plan_hash if graded_plan is not None else None
                ),
                "graded_plan": (
                    graded_plan.to_record() if graded_plan is not None else None
                ),
            },
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                "positive_solver_converged_modes": (
                    positive_report.converged_modes
                ),
                "negative_solver_converged_modes": (
                    negative_report.converged_modes
                ),
                "solver_profiles": {
                    "positive": positive_qep_profiles,
                    "negative": negative_qep_profiles,
                },
                "positive_directional_selection": (
                    _directional_selection_summary(positive_selection)
                ),
                "negative_directional_selection": (
                    _directional_selection_summary(negative_selection)
                ),
                "positive": _basis_summary(positive),
                "negative": _basis_summary(negative),
                "reciprocal_pairs": _reciprocal_pairing_summary(pairs),
                "task036_scalar_stage4_reciprocal_basis": {
                    "requested": bool(
                        args.task036_scalar_stage4_reciprocal_basis
                    ),
                    "runner_gate": analytic_reciprocal_gate,
                    "independent_negative": independent_negative_summary,
                    "independent_reciprocal_pairs": (
                        independent_reciprocal_pairing
                    ),
                    "coupling_negative_basis_origin": (
                        negative.basis_origin
                    ),
                    "coupling_negative_basis_audit": (
                        negative.basis_construction_audit
                    ),
                },
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "formulation": (
                    "strong_trace_subspace_petrov_galerkin"
                    if args.solver_path == "strong-trace-direct"
                    else "projection_only_hybrid"
                ),
                "strong_trace": (
                    primary_system_snapshot.get("strong_trace")
                    if primary_system_snapshot is not None
                    else None
                ),
                "matrix_size": (
                    primary_system_snapshot["shape"]
                    if primary_system_snapshot is not None
                    else None
                ),
                "matrix_stats": (
                    primary_system_snapshot["matrix_stats"]
                    if primary_system_snapshot is not None
                    else None
                ),
                "block_shapes": (
                    primary_system_snapshot["block_shapes"]
                    if primary_system_snapshot is not None
                    else None
                ),
                "inserted_nnz_by_block": (
                    primary_system_snapshot["inserted_nnz_by_block"]
                    if primary_system_snapshot is not None
                    else None
                ),
                "bottom_global_size": bottom.global_size,
                "top_global_size": top.global_size,
                "assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "bottom_assembly_backend_actual": (
                    bottom.assembly_backend_actual
                ),
                "top_assembly_backend_actual": top.assembly_backend_actual,
                "bottom_assembly_backend_qualification": (
                    bottom.assembly_backend_qualification
                ),
                "top_assembly_backend_qualification": (
                    top.assembly_backend_qualification
                ),
                "bottom_static_condensation": (
                    bottom.static_condensation.metadata.to_dict()
                    if bottom.static_condensation is not None
                    else None
                ),
                "top_static_condensation": (
                    top.static_condensation.metadata.to_dict()
                    if top.static_condensation is not None
                    else None
                ),
                "bottom_local_fe_dofs": bottom.n_fe,
                "top_local_fe_dofs": top.n_fe,
                "bottom_local_mesh_cells": list(bottom.local_mesh.mesh_cells),
                "top_local_mesh_cells": list(top.local_mesh.mesh_cells),
                "bottom_local_thickness_nm": (
                    bottom.local_mesh.interface_z_nm
                    - bottom.local_mesh.external_z_nm
                ),
                "top_local_thickness_nm": (
                    top.local_mesh.external_z_nm - top.local_mesh.interface_z_nm
                ),
                "bottom_matrix_stats": bottom.augmented_matrix_stats,
                "top_matrix_stats": top.augmented_matrix_stats,
                "dtn_trace_alias_preflight": {
                    "bottom": bottom.coupling_stats[
                        "dtn_trace_alias_preflight"
                    ],
                    "top": top.coupling_stats[
                        "dtn_trace_alias_preflight"
                    ],
                },
                "internal_unknown_count": coupling.internal_unknown_count,
                "internal_propagation": {
                    "model": coupling.propagation.propagation_model,
                    "authority_boundary": (
                        "scalar_CG_axial_phase_oracle; final authority remains "
                        "the measured 12-channel/field/residual closure"
                    ),
                    "modal_magnetic_and_traction_symbol": (
                        coupling.modal_traction_model
                    ),
                    "field_reconstruction_magnetic_beta_source": (
                        reconstructor.traction_model
                    ),
                    "field_reconstruction_beta_equals_traction_beta": (
                        reconstruction_beta_equals_traction_beta
                    ),
                    "field_reconstruction_positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_positive_traction_beta
                    ],
                    "field_reconstruction_negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_negative_traction_beta
                    ],
                    "positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.positive_traction_beta_per_nm
                    ],
                    "negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.negative_traction_beta_per_nm
                    ],
                    "axial_fem_degree": int(cfg.nedelec_degree),
                    "axial_h_nm": float(cfg.mesh_target_size),
                    "forward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.forward.beta_per_nm
                    ],
                    "forward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.forward.effective_beta_per_nm
                        )
                    ],
                    "forward_phase_corrections_rad": list(
                        coupling.propagation.forward.phase_corrections_rad
                    ),
                    "forward_log_magnitude_corrections": list(
                        coupling.propagation.forward.log_magnitude_corrections
                    ),
                    "backward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.backward.beta_per_nm
                    ],
                    "backward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.backward.effective_beta_per_nm
                        )
                    ],
                    "backward_phase_corrections_rad": list(
                        coupling.propagation.backward.phase_corrections_rad
                    ),
                    "backward_log_magnitude_corrections": list(
                        coupling.propagation.backward.log_magnitude_corrections
                    ),
                    "max_factor_magnitude": float(
                        coupling.propagation.max_factor_magnitude
                    ),
                    "passivity_valid": bool(
                        coupling.propagation.passivity_valid
                    ),
                },
                "qep_to_interface_quadrature_degree": (
                    coupling.interface_quadrature_degree
                ),
                "qep_to_interface_coefficient_degree": (
                    coupling.interface_quadrature_coefficient_degree
                ),
                "canonical_trace_raw_consistency_error": {
                    "bottom": (
                        coupling.bottom.canonical_trace_raw_consistency_error
                    ),
                    "top": coupling.top.canonical_trace_raw_consistency_error,
                },
                "canonical_trace_representation_error": {
                    "bottom": (
                        coupling.bottom.canonical_trace_representation_error
                    ),
                    "top": (
                        coupling.top.canonical_trace_representation_error
                    ),
                },
                "surface_trace_reduction_audits": {
                    "bottom": list(coupling.bottom.surface_reduction_audits),
                    "top": list(coupling.top.surface_reduction_audits),
                },
                "cell_interior_modal_correction_norms": {
                    side: {
                        "positive_frobenius": float(
                            np.linalg.norm(
                                block.positive_interior_correction
                            )
                        ),
                        "negative_frobenius": float(
                            np.linalg.norm(
                                block.negative_interior_correction
                            )
                        ),
                        "modal_rhs_l2": float(
                            np.linalg.norm(block.modal_rhs_correction)
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "tangential_surface_trace_only_audit": {
                    side: {
                        "verified": bool(
                            block.tangential_surface_trace_only_verified
                        ),
                        "pairwise_interior_schur_evaluated": bool(
                            block.interior_modal_pairwise_schur_evaluated
                        ),
                        "mathematical_contract": (
                            "pure tangential ds coupling; H(curl) "
                            "cell-interior tangential trace is zero"
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "full_surface_mode_vectors_retained": bool(
                    coupling.bottom.full_surface_mode_vectors_retained
                    or coupling.top.full_surface_mode_vectors_retained
                ),
                "dense_interface_square_formed": (
                    primary_system_snapshot[
                        "dense_interface_square_formed"
                    ]
                    if primary_system_snapshot is not None
                    else primary_schur_snapshot[
                        "dense_interface_square_formed"
                    ]
                ),
                "full_field_or_mode_gathered": (
                    coupling.full_field_or_mode_gathered
                ),
                "modal_schur": (
                    None if primary_schur_snapshot is None
                    else dict(primary_schur_snapshot)
                ),
            },
            "solve": {
                "factor_solver": solution.factor_solver,
                "converged_reason": solution.converged_reason,
                "true_relative_residual": solution.relative_residual,
                "setup_seconds": getattr(solution, "setup_seconds", None),
                "solve_seconds": getattr(solution, "solve_seconds", None),
                "modal_solve_seconds": getattr(
                    solution, "modal_solve_seconds", None
                ),
                "recovery_seconds": getattr(solution, "recovery_seconds", None),
                "recovery_factor_setup_seconds": getattr(
                    solution, "recovery_factor_setup_seconds", {}
                ),
                "strong_residuals": getattr(
                    solution, "strong_residuals", None
                ),
                "solver_release_before_field_output": (
                    primary_release_audit
                ),
                "bottom_static_recovery": (
                    None
                    if solution.bottom_recovered is None
                    else {
                        "recovery": (
                            solution.bottom_recovered.recovery_audit
                        ),
                        "full_operator_residual": (
                            solution.bottom_recovered.full_operator_residual
                        ),
                        "streaming": (
                            solution.bottom_recovered.streaming_audit
                        ),
                    }
                ),
                "top_static_recovery": (
                    None
                    if solution.top_recovered is None
                    else {
                        "recovery": solution.top_recovered.recovery_audit,
                        "full_operator_residual": (
                            solution.top_recovered.full_operator_residual
                        ),
                        "streaming": solution.top_recovered.streaming_audit,
                    }
                ),
            },
            "validation": validation,
            "physical_field_reconstruction": physical_fields,
            "modal_schur_comparison": modal_schur_comparison,
            "object_payload_ledger": object_payload_ledger,
            "full3d_reference_comparison": reference,
            "gates": gates,
            "qualification": {
                "integration_pass": integration_pass,
                "algebraic_chain_pass": algebraic_chain_pass,
                "task033_physical_truncation_allowed": (
                    task033_physical_truncation_allowed
                ),
                "task033_minimum_physical_modes_per_direction": (
                    80 if task33_variant else None
                ),
                "clean_source_integration_record": bool(
                    integration_pass
                    and task033_physical_truncation_allowed
                    and not provenance["tracked_source_dirty"]
                ),
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": bool(
                    physical_fields is not None
                    and all(
                        value
                        for key, value in gates.items()
                        if (
                            key.startswith("sampled_interface_")
                            or key.startswith("assembled_interface_")
                        )
                        and not key.startswith("diagnostic_")
                        or key.startswith("volume_")
                        or key.startswith("middle_plane_")
                    )
                ),
                "pointwise_h_jump_checked": physical_fields is not None,
                "pointwise_h_jump_role": "diagnostic_sampled_proxy_only",
                "exact_variational_conormal_dual_checked": bool(
                    physical_fields is not None
                    and all(
                        "traction_hcurl_dual"
                        in physical_fields["interface_continuity"][side]
                        for side in ("bottom", "top")
                    )
                ),
                "volume_absorption_reconstructed": physical_fields is not None,
                "selected_middle_planes_reconstructed": physical_fields is not None,
                "official_record": False,
                "hybrid_p_disposition": hybrid_p_disposition,
                "boundary": (
                    (
                        "real_QEP_internal_physical_chain; no pinned "
                        "degree-compatible Case080 full3D reference is registered; "
                        "requires an M funnel and a separate equal-accuracy comparison"
                    )
                    if loaded_reference is None
                    else (
                        "real_QEP_physical_field_chain with a degree-compatible "
                        "full3D reference; requires a wider M funnel before "
                        "official qualification"
                    )
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }
    except _ModalBasisCapacityStop:
        pass
    except _InterfacePreflightStop:
        pass
    except DtnTraceAliasError as error:
        record = dtn_trace_alias_record(error)
    except NearDegenerateBlockPartitionSplitError as error:
        record = near_degenerate_partition_record(error)
    finally:
        if schur_solution is not None:
            schur_solution.destroy()
        if schur_system is not None:
            schur_system.destroy()
        if solution is not None:
            solution.destroy()
        if primary_schur_system is not None:
            primary_schur_system.destroy()
        if system is not None:
            system.destroy()
        if coupling is not None:
            coupling.destroy()
        for local_system in (bottom, top):
            if local_system is not None:
                local_system.destroy()
        if positive is not None:
            positive.destroy()
        if negative is not None:
            negative.destroy()
        if independent_negative is not None:
            independent_negative.destroy()
        if operators is not None:
            operators.destroy()

    if comm.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        print(f"Task32 Phase6 record: {args.output}", flush=True)
        print(f"Task32 Phase6 status: {record['status']}", flush=True)
    comm.barrier()
    if args.task036_interface_preflight_only:
        if not record["qualification"]["assemble_only_preflight_pass"]:
            raise SystemExit(2)
        return
    if not record["qualification"]["integration_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
