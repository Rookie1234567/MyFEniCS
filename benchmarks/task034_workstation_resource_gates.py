"""Fail-closed Task034 WSL workstation launch authorization.

Task033's 14 GiB Case091 policy remains unchanged. This module provides the
explicit Task034 path that re-evaluates a tracked Case092 authority record
against the live WSL effective-memory formula and the external watchdog.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from benchmarks.task033_watchdog_launch import (
    CONDITIONAL_FUNNEL_MODE,
    FORMAL_FUNNEL_MODES,
    conditional_m240_evidence_gate,
)

GIB = 1024**3


def _positive_finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def task034_workstation_hybrid_launch_gate(
    authority: Mapping[str, Any] | None,
    *,
    authority_expected_sha256: str | None,
    authority_observed_sha256: str | None,
    degree: int,
    h_nm: float,
    requested_modes: int,
    candidate_modes: int,
    solver_path: str,
    comparison_solver_path: str,
    bottom_interface_nm: float,
    top_interface_nm: float,
    incident_grazing_deg: float,
    polarization_kind: str,
    effective_limit: Mapping[str, Any] | None,
    warning_gib: float,
    terminate_gib: float,
    core_gate: Mapping[str, Any] | None,
    mpi_size: int,
    available_physical_core_count: int | None,
    current_source_sha: str | None,
    source_compatibility: Mapping[str, Any] | None,
    source_clean_verified: bool,
    authority_is_canonical: bool,
    authority_is_tracked: bool,
    external_watchdog_active: bool,
    full3d_reference_sha256: str | None,
    resource_anchor_sha256: str | None = None,
    m160_funnel_evidence: Mapping[str, Any] | None = None,
    expected_m160_funnel_sha256: str | None = None,
    observed_m160_funnel_sha256: str | None = None,
) -> dict[str, Any]:
    """Authorize one Task034 fixed-geometry Hybrid shard.

    The checked Case092 record combines a current WSL measured resource anchor
    with an independent planning center.  Phase F uses the same-p/h Full-3D
    watchdog record or descriptor directly.  The preserved p4/h5 path may use
    its E0 assembly calibration before E3.  Historical models are never a
    standalone launch authority.
    """

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
    entry = matches[0] if len(matches) == 1 else {}
    reference = entry.get("full3d_reference")
    reference = reference if isinstance(reference, Mapping) else {}
    assembly_anchor = entry.get("assembly_resource_anchor")
    assembly_anchor = (
        assembly_anchor if isinstance(assembly_anchor, Mapping) else {}
    )
    anchor_kind = (
        "full3d_reference"
        if (
            full3d_reference_sha256 is not None
            and resource_anchor_sha256 is None
            and reference.get("status") == "full3d_reference_pass"
        )
        else (
            "assembly_calibration"
            if (
                resource_anchor_sha256 is not None
                and full3d_reference_sha256 is None
                and assembly_anchor.get("status") == "assembly_calibration_pass"
            )
            else None
        )
    )
    anchor = reference if anchor_kind == "full3d_reference" else assembly_anchor
    prediction = entry.get("workstation_prediction")
    prediction = prediction if isinstance(prediction, Mapping) else {}
    centers = prediction.get("centers_gib")
    centers = centers if isinstance(centers, Mapping) else {}
    parsed_centers = {
        str(name): _positive_finite(value) for name, value in centers.items()
    }
    upper = _positive_finite(prediction.get("conservative_upper_gib"))
    live = effective_limit if isinstance(effective_limit, Mapping) else {}
    effective_bytes = live.get("effective_limit_bytes")
    warning_bytes = live.get("warning_bytes")
    termination_bytes = live.get("termination_bytes")
    live_values_valid = bool(
        type(effective_bytes) is int
        and effective_bytes > 0
        and type(warning_bytes) is int
        and warning_bytes > 0
        and type(termination_bytes) is int
        and termination_bytes > warning_bytes
    )
    live_warning_gib = warning_bytes / GIB if live_values_valid else None
    live_termination_gib = termination_bytes / GIB if live_values_valid else None
    core = core_gate if isinstance(core_gate, Mapping) else {}
    compatibility = (
        source_compatibility
        if isinstance(source_compatibility, Mapping)
        else {}
    )
    m240_requested = requested_modes == CONDITIONAL_FUNNEL_MODE
    m240_gate = conditional_m240_evidence_gate(
        m160_funnel_evidence,
        expected_file_sha256=expected_m160_funnel_sha256,
        observed_file_sha256=observed_m160_funnel_sha256,
        current_source_sha=current_source_sha,
        degree=degree,
        h_nm=h_nm,
        incident_grazing_deg=incident_grazing_deg,
        polarization_kind=polarization_kind,
        bottom_interface_nm=bottom_interface_nm,
        top_interface_nm=top_interface_nm,
        graded_reference_h=None,
        solver_path=solver_path,
        required=m240_requested,
    )
    expected_anchor_sha = (
        reference.get("descriptor_sha256")
        if anchor_kind == "full3d_reference"
        else assembly_anchor.get("watchdog_record_sha256")
    )
    observed_anchor_sha = (
        full3d_reference_sha256
        if anchor_kind == "full3d_reference"
        else resource_anchor_sha256
    )
    full3d_residual = _positive_finite(reference.get("true_relative_residual"))
    anchor_stage_scope_valid = bool(
        (
            anchor_kind == "full3d_reference"
            and full3d_residual is not None
            and full3d_residual <= 1.0e-9
        )
        or (
            anchor_kind == "assembly_calibration"
            and assembly_anchor.get("factorization_or_solve_stage_seen") is False
            and _positive_finite(assembly_anchor.get("exact_rows")) is not None
            and _positive_finite(assembly_anchor.get("exact_assembled_nnz"))
            is not None
        )
    )
    checks = {
        "authority_object_present": bool(payload),
        "authority_identity_valid": bool(
            payload.get("schema_version") == 1
            and payload.get("benchmark_id")
            == "task034_case092_workstation_hybrid_launch_authority"
            and payload.get("record_type")
            == "task034_workstation_resource_prediction_and_launch_authority"
        ),
        "authority_expected_sha256_valid": _valid_hex(
            authority_expected_sha256, 64
        ),
        "authority_raw_sha256_matches": bool(
            authority_expected_sha256 == authority_observed_sha256
        ),
        "authority_path_is_canonical": bool(authority_is_canonical),
        "authority_file_is_git_tracked": bool(authority_is_tracked),
        "exactly_one_matching_p_h_entry": len(matches) == 1,
        "entry_status_authorizes_guarded_launch": (
            entry.get("status") == "calibrated_guarded_launch_authority"
        ),
        "task033_old_model_not_standalone_authority": (
            prediction.get("task033_old_model_is_launch_authority") is False
        ),
        "current_full_source_sha_valid": _valid_hex(current_source_sha, 40),
        "complete_nonignored_worktree_clean": bool(source_clean_verified),
        "authority_source_compatible_with_current": (
            compatibility.get("pass") is True
        ),
        "external_watchdog_is_launch_authority": bool(external_watchdog_active),
        "live_task034_effective_limit_readable": live_values_valid,
        "physical_core_inventory_readable": bool(
            type(available_physical_core_count) is int
            and available_physical_core_count > 0
        ),
        "requested_mpi_size_supported": mpi_size in (1, 2, 4, 8, 16, 32),
        "requested_mpi_size_does_not_oversubscribe": bool(
            type(available_physical_core_count) is int
            and type(mpi_size) is int
            and mpi_size <= available_physical_core_count
        ),
        "warning_threshold_matches_live_task034_gate": bool(
            live_warning_gib is not None
            and math.isclose(
                warning_gib, live_warning_gib, rel_tol=0.0, abs_tol=1.0e-9
            )
        ),
        "termination_threshold_matches_live_task034_gate": bool(
            live_termination_gib is not None
            and math.isclose(
                terminate_gib,
                live_termination_gib,
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
        ),
        "formal_funnel_mode_count": bool(
            requested_modes in FORMAL_FUNNEL_MODES
            or (m240_requested and m240_gate["pass"])
        ),
        "conditional_m240_prior_nonconvergence_evidence": m240_gate["pass"],
        "requested_mode_within_authorized_ceiling": bool(
            (
                type(entry.get("max_formal_modes")) is int
                and requested_modes <= entry["max_formal_modes"]
            )
            or (
                m240_requested
                and entry.get("conditional_m240_allowed") is True
                and m240_gate["pass"]
            )
        ),
        "candidate_pool_is_twice_requested_modes": bool(
            type(requested_modes) is int
            and requested_modes > 0
            and candidate_modes == 2 * requested_modes
        ),
        "primary_memory_minimal_solver_path": (
            solver_path == "modal-schur-memory-minimal"
        ),
        "comparison_solver_path_supported": comparison_solver_path == "fast",
        "fixed_10_110_interfaces": bool(
            math.isclose(bottom_interface_nm, 10.0)
            and math.isclose(top_interface_nm, 110.0)
        ),
        "fixed_incidence_and_polarization": bool(
            math.isclose(incident_grazing_deg, 10.0)
            and polarization_kind in {"s", "p"}
        ),
        "user_approved_p_polarization_scope": bool(
            polarization_kind == "s"
            or (
                polarization_kind == "p"
                and degree == 2
                and math.isclose(h_nm, 5.0)
                and mpi_size == 8
                and requested_modes == 160
            )
        ),
        "user_approved_p2_h1_added_point_scope": bool(
            not (degree == 2 and math.isclose(h_nm, 1.0))
            or (
                polarization_kind == "s"
                and mpi_size == 8
                and requested_modes == 160
                and candidate_modes == 320
                and anchor_kind == "assembly_calibration"
            )
        ),
        "user_approved_p3_h2_added_point_scope": bool(
            not (degree == 3 and math.isclose(h_nm, 2.0))
            or (
                polarization_kind == "s"
                and mpi_size == 8
                and requested_modes == 160
                and candidate_modes == 320
                and anchor_kind == "assembly_calibration"
            )
        ),
        "high_order_core_evidence": core.get("pass") is True,
        "measured_resource_anchor_kind_supported": anchor_kind
        in {"full3d_reference", "assembly_calibration"},
        "measured_resource_anchor_status_pass": (
            anchor.get("status")
            in {"full3d_reference_pass", "assembly_calibration_pass"}
        ),
        "measured_resource_anchor_qualification_pass": (
            anchor.get("qualification_pass") is True
        ),
        "measured_resource_anchor_no_swap": anchor.get("no_swap") is True,
        "measured_resource_anchor_stage_scope_valid": anchor_stage_scope_valid,
        "measured_resource_anchor_sha256_valid": _valid_hex(
            expected_anchor_sha, 64
        ),
        "measured_resource_anchor_sha256_matches": bool(
            expected_anchor_sha == observed_anchor_sha
        ),
        "measured_resource_anchor_peak_is_positive": (
            _positive_finite(anchor.get("peak_memory_gib")) is not None
        ),
        "two_independent_prediction_centers_present": bool(
            len(parsed_centers) >= 2
            and all(value is not None for value in parsed_centers.values())
        ),
        "conservative_upper_is_positive": upper is not None,
        "prediction_centers_within_live_warning": bool(
            live_warning_gib is not None
            and parsed_centers
            and all(
                value is not None and value <= live_warning_gib
                for value in parsed_centers.values()
            )
        ),
        "conservative_upper_within_live_warning": bool(
            live_warning_gib is not None
            and upper is not None
            and upper <= live_warning_gib
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "launch_eligible_recomputed": not failures,
        "scope": "task034_wsl_workstation_hybrid",
        "matrix_key": entry.get("matrix_key"),
        "mpi_size": mpi_size,
        "available_physical_core_count": available_physical_core_count,
        "live_task034_limits": {
            "effective_limit_gib": (
                effective_bytes / GIB if live_values_valid else None
            ),
            "warning_gib": live_warning_gib,
            "termination_gib": live_termination_gib,
            "formula": live.get("formula"),
        },
        "prediction": {
            "centers_gib": parsed_centers,
            "conservative_upper_gib": upper,
            "historical_task033_model_is_standalone_authority": False,
        },
        "resource_anchor_kind": anchor_kind,
        "resource_anchor": dict(anchor),
        "full3d_reference": dict(reference),
        "conditional_m240_evidence": m240_gate,
        "high_order_core_evidence": dict(core),
        "source_compatibility": dict(compatibility),
        "checks": checks,
        "failures": failures,
        "semantics": (
            "Task033's 14 GiB policy is unchanged. This explicit Task034 Gate "
            "requires a tracked Case092 authority, current WSL effective limits, "
            "a measured candidate-specific resource anchor, clean compatible source, "
            "and a live watchdog."
        ),
    }