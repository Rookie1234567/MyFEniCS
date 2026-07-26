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


def task034_adaptive_mechanism_evidence_gate(
    evidence: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    current_source_sha: str | None,
    degree: int,
    h_nm: float,
    requested_modes: int,
    mpi_size: int,
    polarization_kind: str,
    graded_reference_h: float | None,
    graded_profile: str | None,
) -> dict[str, Any]:
    """Authorize only Task034's measured p2/h3 graded-compression matrix."""

    if graded_reference_h is None:
        return {"pass": True, "applicable": False, "checks": {}, "failures": []}
    payload = evidence if isinstance(evidence, Mapping) else {}
    case = payload.get("case")
    case = case if isinstance(case, Mapping) else {}
    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    claims = payload.get("claims")
    claims = claims if isinstance(claims, Mapping) else {}
    plan = payload.get("plan")
    plan = plan if isinstance(plan, Mapping) else {}
    source_before = payload.get("source_before")
    source_before = source_before if isinstance(source_before, Mapping) else {}
    source_after = payload.get("source_after")
    source_after = source_after if isinstance(source_after, Mapping) else {}
    checks = {
        "adaptive_mechanism_object_present": bool(payload),
        "adaptive_mechanism_sha256_valid": bool(
            _valid_hex(expected_sha256, 64) and _valid_hex(observed_sha256, 64)
        ),
        "adaptive_mechanism_sha256_matches": expected_sha256 == observed_sha256,
        "adaptive_mechanism_record_identity": bool(
            payload.get("schema_version") == "task034.adaptive-mechanism.v1"
            and payload.get("record_type")
            == "task034_p2_h5_conforming_graded_mechanism"
        ),
        "adaptive_mechanism_recomputed_qualification_pass": bool(
            qualification.get("pass") is True
            and qualification.get("failures") == []
            and all(
                value is True for value in qualification.get("checks", {}).values()
            )
        ),
        "adaptive_mechanism_claim_scope": bool(
            claims.get("mechanism_qualified") is True
            and claims.get("pde_solved") is False
            and claims.get("equal_accuracy_compression_proven") is False
            and claims.get("genuine_adaptive_loop_proven") is False
        ),
        "adaptive_mechanism_p2_h5_scope": bool(
            case.get("degree") == 2
            and math.isclose(float(case.get("reference_h_nm", math.nan)), 5.0)
            and case.get("profile") == "mechanism"
            and case.get("polarization_kind") == "s"
        ),
        "adaptive_mechanism_plan_contract": bool(
            plan.get("material_planes_exact") is True
            and plan.get("matching_planes_exact") is True
            and plan.get("ordinary_uniform_default_changed") is False
            and plan.get("quality", {}).get("hanging_nodes_present") is False
            and plan.get("periodic_pairing", {}).get(
                "periodic_mate_refinement_synchronized"
            )
            is True
        ),
        "adaptive_mechanism_same_clean_source": bool(
            _valid_hex(current_source_sha, 40)
            and payload.get("verified_clean_sha") == current_source_sha
            and source_before.get("commit_sha") == current_source_sha
            and source_after.get("commit_sha") == current_source_sha
            and source_before.get("tracked_and_nonignored_untracked_clean") is True
            and source_after.get("tracked_and_nonignored_untracked_clean") is True
        ),
        "graded_compression_scope_exact": bool(
            degree == 2
            and math.isclose(h_nm, 3.0)
            and math.isclose(graded_reference_h, 3.0)
            and graded_profile in {"conservative", "balanced", "aggressive"}
            and requested_modes in FORMAL_FUNNEL_MODES
            and mpi_size == 8
            and polarization_kind == "s"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "applicable": True,
        "graded_profile": graded_profile,
        "checks": checks,
        "failures": failures,
    }


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
    assembly_backend: str = "standard_full",
    measured_full3d_anchor: Mapping[str, Any] | None = None,
    m160_funnel_evidence: Mapping[str, Any] | None = None,
    expected_m160_funnel_sha256: str | None = None,
    observed_m160_funnel_sha256: str | None = None,
    graded_reference_h: float | None = None,
    graded_profile: str | None = None,
    adaptive_mechanism_gate: Mapping[str, Any] | None = None,
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
    historical_reference = entry.get("full3d_reference")
    historical_reference = (
        historical_reference
        if isinstance(historical_reference, Mapping)
        else {}
    )
    fresh_anchor_gate = (
        measured_full3d_anchor
        if isinstance(measured_full3d_anchor, Mapping)
        else {}
    )
    fresh_reference = fresh_anchor_gate.get("anchor")
    fresh_reference = (
        fresh_reference if isinstance(fresh_reference, Mapping) else {}
    )
    static_backend = assembly_backend == "assembly_time_static_condensed"
    use_fresh_reference = bool(static_backend and fresh_anchor_gate)
    reference = (
        fresh_reference if use_fresh_reference else historical_reference
    )
    assembly_anchor = entry.get("assembly_resource_anchor")
    assembly_anchor = (
        assembly_anchor if isinstance(assembly_anchor, Mapping) else {}
    )
    anchor_kind = (
        "fresh_full3d_reference"
        if use_fresh_reference
        else (
        "full3d_reference"
        if (
            assembly_backend == "standard_full"
            and full3d_reference_sha256 is not None
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
    )
    anchor = (
        reference
        if anchor_kind in {"full3d_reference", "fresh_full3d_reference"}
        else assembly_anchor
    )
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
    adaptive_gate = (
        adaptive_mechanism_gate
        if isinstance(adaptive_mechanism_gate, Mapping)
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
        graded_reference_h=graded_reference_h,
        solver_path=solver_path,
        required=m240_requested,
    )
    expected_anchor_sha = (
        reference.get("descriptor_sha256")
        if anchor_kind in {"full3d_reference", "fresh_full3d_reference"}
        else assembly_anchor.get("watchdog_record_sha256")
    )
    observed_anchor_sha = (
        full3d_reference_sha256
        if anchor_kind in {"full3d_reference", "fresh_full3d_reference"}
        else resource_anchor_sha256
    )
    full3d_residual = _positive_finite(reference.get("true_relative_residual"))
    anchor_stage_scope_valid = bool(
        (
            anchor_kind in {"full3d_reference", "fresh_full3d_reference"}
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
        "assembly_backend_supported": assembly_backend
        in {"standard_full", "assembly_time_static_condensed"},
        "static_backend_requires_fresh_anchor": bool(
            not static_backend or fresh_anchor_gate
        ),
        "standard_backend_rejects_fresh_anchor": bool(
            static_backend or not fresh_anchor_gate
        ),
        "fresh_full3d_reference_qualified": bool(
            not fresh_anchor_gate
            or (
                fresh_anchor_gate.get("pass") is True
                and fresh_anchor_gate.get("failures") == []
                and isinstance(fresh_anchor_gate.get("checks"), Mapping)
                and all(fresh_anchor_gate["checks"].values())
                and isinstance(
                    fresh_anchor_gate.get("source_compatibility"), Mapping
                )
                and fresh_anchor_gate["source_compatibility"].get("pass")
                is True
                and fresh_reference.get("assembly_backend")
                == "assembly_time_static_condensed"
                and fresh_reference.get("degree") == degree
                and math.isclose(
                    float(fresh_reference.get("h_nm", math.nan)),
                    float(h_nm),
                )
                and fresh_reference.get("mpi_size") == mpi_size
                and fresh_reference.get("polarization_kind")
                == polarization_kind
            )
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
        "user_approved_p4_h3_added_point_scope": bool(
            not (degree == 4 and math.isclose(h_nm, 3.0))
            or (
                polarization_kind == "s"
                and mpi_size == 8
                and requested_modes == 160
                and candidate_modes == 320
                and anchor_kind == "assembly_calibration"
            )
        ),
        "task034_graded_compression_scope_authorized": bool(
            graded_reference_h is None or adaptive_gate.get("pass") is True
        ),
        "high_order_core_evidence": core.get("pass") is True,
        "measured_resource_anchor_kind_supported": anchor_kind
        in {
            "full3d_reference",
            "fresh_full3d_reference",
            "assembly_calibration",
        },
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
        "measured_resource_anchor_peak_within_live_warning": bool(
            live_warning_gib is not None
            and _positive_finite(anchor.get("peak_memory_gib")) is not None
            and float(anchor["peak_memory_gib"]) <= live_warning_gib
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
        "historical_full3d_reference": dict(historical_reference),
        "fresh_full3d_reference_gate": dict(fresh_anchor_gate),
        "assembly_backend": assembly_backend,
        "conditional_m240_evidence": m240_gate,
        "high_order_core_evidence": dict(core),
        "adaptive_mechanism_evidence": dict(adaptive_gate),
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
