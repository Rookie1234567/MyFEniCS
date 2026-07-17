"""Task033 Phase C0 prediction and Phase C evidence aggregation.

This module deliberately separates launch authorization from solver success.
The p3/h5 full-3D reference and each Hybrid path receive their own memory
prediction.  A failed full-3D Gate is preserved as a measured planning
negative; it is never converted into permission to run by the fact that the
smaller Hybrid candidates are safe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from benchmarks.task033_resource_gates import scaled_gate_limits
from benchmarks.task033_watchdog_launch import independent_variant_prediction


PHASEC_DEGREE = 3
PHASEC_H_NM = 5.0
PHASEC_MPI_SIZE = 4
PHASEC_MODES = (80, 120, 160)
PHASEC_SOURCE_REVIEW = (
    "docs/task033_high_order_floquet_hybrid_hp_adaptivity/review_report_v3.md"
)

# Clean, external simultaneous-worker RSS anchors from Task029.  These are the
# same target grating, degree 2, ordinary in-core direct path.
FULL3D_H5_RSS_GIB = 2.273578643798828
FULL3D_H3_RSS_GIB = 8.44833755493164
FULL3D_H5_ASSEMBLED_NNZ = 4_896_156.0
FULL3D_H3_ASSEMBLED_NNZ = 21_317_860.0
FULL3D_H5_FACTOR_NNZ = 33_862_428.0
FULL3D_H3_FACTOR_NNZ = 266_127_836.0

# Same-mesh p2/p3 ratios from accepted Case090 fixture B, g=10, S, h5,
# MPI4.  The RSS of that tiny fixture is not used.
CASE090_P2_ROWS = 304.0
CASE090_P3_ROWS = 886.0
CASE090_P2_ASSEMBLED_NNZ = 29_284.0
CASE090_P3_ASSEMBLED_NNZ = 203_868.0

FACTOR_STORAGE_BYTES_PER_NNZ = 24.017064706474375


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0.0 else None


def _full_sha(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.lower()
    return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else None


def _power_law(
    x1: float, y1: float, x2: float, y2: float, target: float
) -> tuple[float, float]:
    exponent = math.log(y2 / y1) / math.log(x2 / x1)
    return exponent, y1 * (target / x1) ** exponent


def full3d_p3_h5_prediction() -> dict[str, Any]:
    """Return two genuinely independent p3/h5 full-3D memory centers.

    Center A treats p/h as an effective resolution.  Center B first transfers
    the measured p2->p3 same-mesh Case090 assembled-NNZ ratio to the target,
    then extrapolates MUMPS fill from the two measured p2 target grids, and
    finally maps factor payload to simultaneous RSS.  The second chain is
    intentionally conservative because the high-order target factor has not
    been formed.
    """

    effective_exponent, effective_center = _power_law(
        2.0 / 5.0,
        FULL3D_H5_RSS_GIB,
        2.0 / 3.0,
        FULL3D_H3_RSS_GIB,
        3.0 / 5.0,
    )
    assembled_ratio = CASE090_P3_ASSEMBLED_NNZ / CASE090_P2_ASSEMBLED_NNZ
    projected_rows = int(round(44_778.0 * CASE090_P3_ROWS / CASE090_P2_ROWS))
    projected_assembled_nnz = FULL3D_H5_ASSEMBLED_NNZ * assembled_ratio

    fill_h5 = FULL3D_H5_FACTOR_NNZ / FULL3D_H5_ASSEMBLED_NNZ
    fill_h3 = FULL3D_H3_FACTOR_NNZ / FULL3D_H3_ASSEMBLED_NNZ
    fill_exponent, projected_fill = _power_law(
        FULL3D_H5_ASSEMBLED_NNZ,
        fill_h5,
        FULL3D_H3_ASSEMBLED_NNZ,
        fill_h3,
        projected_assembled_nnz,
    )
    projected_factor_nnz = projected_assembled_nnz * projected_fill

    payload_h5 = (
        FULL3D_H5_FACTOR_NNZ * FACTOR_STORAGE_BYTES_PER_NNZ / 1024.0**3
    )
    payload_h3 = (
        FULL3D_H3_FACTOR_NNZ * FACTOR_STORAGE_BYTES_PER_NNZ / 1024.0**3
    )
    rss_per_payload = (
        (FULL3D_H3_RSS_GIB - FULL3D_H5_RSS_GIB)
        / (payload_h3 - payload_h5)
    )
    rss_intercept = FULL3D_H5_RSS_GIB - rss_per_payload * payload_h5
    projected_payload = (
        projected_factor_nnz * FACTOR_STORAGE_BYTES_PER_NNZ / 1024.0**3
    )
    factor_center = rss_intercept + rss_per_payload * projected_payload
    centers = {
        "effective_p_over_h_power_law_gib": effective_center,
        "assembled_nnz_fill_factor_payload_gib": factor_center,
    }
    conservative_upper = 1.20 * max(centers.values())
    return {
        "candidate_id": "p3_h5_full3d_direct",
        "degree": PHASEC_DEGREE,
        "h_nm": PHASEC_H_NM,
        "mpi_size": PHASEC_MPI_SIZE,
        "solver_path": "ordinary_in_core_mumps_direct",
        "centers_gib": centers,
        "conservative_upper_gib": conservative_upper,
        "projected_rows": projected_rows,
        "projected_assembled_nnz": int(round(projected_assembled_nnz)),
        "projected_factor_nnz": int(round(projected_factor_nnz)),
        "projected_factor_payload_gib": projected_payload,
        "method_details": {
            "effective_resolution_exponent": effective_exponent,
            "case090_same_mesh_p3_to_p2_row_ratio": (
                CASE090_P3_ROWS / CASE090_P2_ROWS
            ),
            "case090_same_mesh_p3_to_p2_assembled_nnz_ratio": assembled_ratio,
            "target_p2_fill_exponent_vs_assembled_nnz": fill_exponent,
            "projected_fill_ratio": projected_fill,
            "rss_per_factor_payload_slope": rss_per_payload,
            "rss_intercept_gib": rss_intercept,
        },
        "calibration": {
            "task029_h5_record": (
                "benchmarks/cases/050_stage4_direct_memory_forensics/"
                "records/h5_baseline.json"
            ),
            "task029_h3_record": (
                "benchmarks/cases/050_stage4_direct_memory_forensics/"
                "records/h3_baseline.json"
            ),
            "case090_p2_p3_same_mesh": (
                "fixture_b_g10_s_h5_mpi4; rows 304/886; assembled NNZ "
                "29284/203868"
            ),
        },
        "limitations": [
            "No p3 target factor has been formed.",
            "The factor-payload chain is deliberately retained even though it is more pessimistic than the effective-resolution center.",
            "A failed center Gate cannot be overridden by the lower center.",
        ],
    }


def _resource_p3_h5_entry(resource_matrix: Mapping[str, Any]) -> Mapping[str, Any]:
    entries = resource_matrix.get("entries")
    entries = entries if isinstance(entries, list) else []
    matches = [
        row
        for row in entries
        if isinstance(row, Mapping)
        and row.get("matrix_key") == "p3_h5"
        and row.get("degree") == PHASEC_DEGREE
        and _finite(row.get("h_nm")) == PHASEC_H_NM
    ]
    if len(matches) != 1:
        raise ValueError("Phase C0 requires exactly one Case091 p3_h5 resource row.")
    return matches[0]


def _hybrid_prediction(
    entry: Mapping[str, Any],
    *,
    candidate_id: str,
    solver_path: str,
    requested_modes: int,
) -> dict[str, Any]:
    if solver_path == "modal-schur-memory-minimal":
        predictions = entry.get("predictions")
        predictions = predictions if isinstance(predictions, Mapping) else {}
        centers = {
            str(name): float(value["center_gib"])
            for name, value in predictions.items()
            if isinstance(value, Mapping) and _positive(value.get("center_gib"))
        }
        upper = _positive(entry.get("conservative_upper_gib"))
        if len(centers) != 2 or upper is None:
            raise ValueError("Case091 p3_h5 row lacks two valid memory centers.")
        method = {
            "pass": True,
            "prediction_identity": (
                "p3_h5_m160_uniform_ceiling_no_discount_for_smaller_M"
            ),
            "centers_gib": centers,
            "conservative_upper_gib": upper,
            "limitations": [
                "M80 and M120 deliberately inherit the measured-calibration M160 ceiling.",
                "This avoids claiming a memory discount before p3 modal payloads are measured.",
            ],
        }
    elif solver_path == "augmented":
        method = independent_variant_prediction(
            entry,
            solver_path="augmented",
            compare_modal_schur=True,
            bottom_interface_nm=10.0,
            top_interface_nm=110.0,
            graded_reference_h=None,
            incident_grazing_deg=10.0,
            polarization_kind="s",
            requested_modes=requested_modes,
        )
    else:
        raise ValueError(f"Unsupported Phase C solver path: {solver_path}")
    return {
        "candidate_id": candidate_id,
        "degree": PHASEC_DEGREE,
        "h_nm": PHASEC_H_NM,
        "mpi_size": PHASEC_MPI_SIZE,
        "requested_modes_per_direction": requested_modes,
        "candidate_modes_per_directional_solve": 2 * requested_modes,
        "solver_path": solver_path,
        "comparison_solver_path": (
            "modal-schur-memory-minimal" if solver_path == "augmented" else None
        ),
        "centers_gib": method["centers_gib"],
        "conservative_upper_gib": method["conservative_upper_gib"],
        "prediction_identity": method.get("prediction_identity"),
        "limitations": method.get("limitations", []),
    }


def _candidate_gate(
    candidate: Mapping[str, Any], limits: Mapping[str, Any]
) -> dict[str, Any]:
    centers = candidate.get("centers_gib")
    centers = centers if isinstance(centers, Mapping) else {}
    center_limit = float(limits["two_center_limit_gib"])
    upper_limit = float(limits["conservative_upper_limit_gib"])
    center_checks = {
        str(name): _positive(value) is not None and float(value) <= center_limit
        for name, value in centers.items()
    }
    upper = _positive(candidate.get("conservative_upper_gib"))
    checks = {
        "exactly_two_independent_centers": len(center_checks) == 2,
        "all_centers_within_limit": bool(center_checks)
        and all(center_checks.values()),
        "conservative_upper_within_limit": upper is not None
        and upper <= upper_limit,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "decision": "launch_eligible" if not failures else "not_run_by_memory_gate",
        "checks": checks,
        "center_checks": center_checks,
        "limits_gib": {
            "two_center": center_limit,
            "conservative_upper": upper_limit,
        },
        "failures": failures,
    }


def build_phasec_preflight(
    resource_matrix: Mapping[str, Any],
    *,
    source_commit_full_sha: str,
    container_limit_bytes: int,
    host_available_memory_bytes: int,
    container_current_bytes: int,
    container_swap_current_bytes: int,
    pswpin_pages: int,
    pswpout_pages: int,
) -> dict[str, Any]:
    """Build the complete candidate-specific Phase C0 launch record."""

    source_sha = _full_sha(source_commit_full_sha)
    if source_sha is None:
        raise ValueError("Phase C0 requires a full clean source SHA.")
    if min(
        container_limit_bytes,
        host_available_memory_bytes,
        container_current_bytes,
    ) <= 0:
        raise ValueError("Phase C0 live memory authorities must be positive.")
    if container_swap_current_bytes != 0:
        raise ValueError("Phase C0 refuses a nonzero cgroup swap current.")
    if pswpin_pages < 0 or pswpout_pages < 0:
        raise ValueError("Phase C0 swap counters must be readable.")

    effective_ceiling = min(container_limit_bytes, host_available_memory_bytes) / 1024.0**3
    limits = scaled_gate_limits(effective_ceiling)
    entry = _resource_p3_h5_entry(resource_matrix)
    candidates = [full3d_p3_h5_prediction()]
    candidates.extend(
        _hybrid_prediction(
            entry,
            candidate_id=f"p3_h5_schur_minimal_m{mode}",
            solver_path="modal-schur-memory-minimal",
            requested_modes=mode,
        )
        for mode in PHASEC_MODES
    )
    candidates.append(
        _hybrid_prediction(
            entry,
            candidate_id="p3_h5_augmented_vs_schur_minimal_m160",
            solver_path="augmented",
            requested_modes=160,
        )
    )
    rows = []
    for candidate in candidates:
        rows.append({**candidate, "gate": _candidate_gate(candidate, limits)})
    full3d = next(row for row in rows if row["candidate_id"] == "p3_h5_full3d_direct")
    hybrid_rows = [row for row in rows if row is not full3d]
    full_chain = all(row["gate"]["pass"] for row in rows)
    hybrid_chain = all(row["gate"]["pass"] for row in hybrid_rows)
    return {
        "schema_version": "task033.phaseC-preflight.v1",
        "record_type": "task033_phaseC_candidate_specific_preflight",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "all_candidates_launch_eligible"
            if full_chain
            else "full3d_memory_gated_hybrid_candidates_eligible"
            if hybrid_chain
            else "phaseC_launch_blocked"
        ),
        "identity": {
            "source_commit_full_sha": source_sha,
            "complete_nonignored_worktree_clean_required": True,
            "review_authority": PHASEC_SOURCE_REVIEW,
            "degree": PHASEC_DEGREE,
            "h_nm": PHASEC_H_NM,
            "mpi_size": PHASEC_MPI_SIZE,
            "primary_incident_grazing_deg": 10.0,
            "primary_polarization": "s",
            "ordinary_default_changed": False,
        },
        "environment": {
            "container_limit_bytes": int(container_limit_bytes),
            "container_limit_gib": container_limit_bytes / 1024.0**3,
            "host_available_memory_bytes": int(host_available_memory_bytes),
            "host_available_memory_gib": host_available_memory_bytes / 1024.0**3,
            "container_current_bytes": int(container_current_bytes),
            "container_current_gib": container_current_bytes / 1024.0**3,
            "container_swap_current_bytes": int(container_swap_current_bytes),
            "pswpin_pages": int(pswpin_pages),
            "pswpout_pages": int(pswpout_pages),
            "no_swap_preflight": bool(
                container_swap_current_bytes == 0
                and pswpin_pages >= 0
                and pswpout_pages >= 0
            ),
            "effective_live_ceiling_gib": effective_ceiling,
        },
        "limits": limits,
        "candidates": rows,
        "qualification": {
            "full_phaseC_chain_launchable": full_chain,
            "hybrid_component_chain_launchable": hybrid_chain,
            "full3d_disposition": full3d["gate"]["decision"],
            "one_heavy_case_at_a_time_required": True,
            "external_live_watchdog_required": True,
            "no_swap_required": True,
        },
        "limitations": [
            "This is a launch record, not a PDE or solver result.",
            "The full3D veto does not become a pass when Hybrid candidates are safe.",
            "Hybrid-only measurements cannot close selected-plane E/H comparison to a same-degree full3D reference.",
            "A future larger-memory host may recompute this record; the stored decision is not manually overridden.",
        ],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_preflight_for_candidate(
    payload: Mapping[str, Any],
    *,
    candidate_id: str,
    source_commit_full_sha: str,
) -> dict[str, Any]:
    """Recompute the immutable identity and selected-candidate launch decision."""

    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    candidates = payload.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    matches = [
        row
        for row in candidates
        if isinstance(row, Mapping) and row.get("candidate_id") == candidate_id
    ]
    gate = matches[0].get("gate") if len(matches) == 1 else {}
    gate = gate if isinstance(gate, Mapping) else {}
    checks = {
        "record_identity": bool(
            payload.get("schema_version") == "task033.phaseC-preflight.v1"
            and payload.get("record_type")
            == "task033_phaseC_candidate_specific_preflight"
        ),
        "same_source_sha": bool(
            _full_sha(source_commit_full_sha) is not None
            and identity.get("source_commit_full_sha")
            == source_commit_full_sha
        ),
        "exactly_one_candidate": len(matches) == 1,
        "candidate_launch_eligible": gate.get("pass") is True
        and gate.get("decision") == "launch_eligible",
        "no_swap_preflight": (
            (payload.get("environment") or {}).get("no_swap_preflight") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _descriptor(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def build_phasec_summary_from_paths(
    *,
    preflight_path: Path,
    funnel_path: Path,
    hybrid_paths: Sequence[Path],
    augmented_path: Path,
) -> dict[str, Any]:
    """Aggregate the C0 negative and the safe Hybrid component campaign."""

    preflight = _load_object(preflight_path)
    funnel = _load_object(funnel_path)
    hybrid = [_load_object(path) for path in hybrid_paths]
    augmented = _load_object(augmented_path)
    source_sha = (preflight.get("identity") or {}).get("source_commit_full_sha")
    source_shas = {
        (row.get("source") or {}).get("head_before_sha") for row in hybrid
    }
    source_shas.add((augmented.get("source") or {}).get("head_before_sha"))
    modes = sorted(row.get("requested_modes") for row in hybrid)
    augmented_measurements = augmented.get("measurements")
    augmented_measurements = (
        augmented_measurements if isinstance(augmented_measurements, Mapping) else {}
    )
    comparison = augmented_measurements.get("modal_schur_comparison")
    comparison = comparison if isinstance(comparison, Mapping) else {}
    comparison_gates = comparison.get("gates")
    comparison_gates = (
        comparison_gates if isinstance(comparison_gates, Mapping) else {}
    )
    checks = {
        "preflight_full3d_memory_gated": bool(
            (preflight.get("qualification") or {}).get("full3d_disposition")
            == "not_run_by_memory_gate"
        ),
        "preflight_hybrid_chain_eligible": bool(
            (preflight.get("qualification") or {}).get(
                "hybrid_component_chain_launchable"
            )
            is True
        ),
        "exact_m80_m120_m160": modes == list(PHASEC_MODES),
        "all_hybrid_watchdogs_measured": all(
            row.get("status") == "measured_shard_pass"
            and row.get("target") == "hybrid"
            and row.get("memory_authority_pass") is True
            and row.get("no_swap") is True
            and row.get("terminated_for_memory") is False
            and row.get("terminated_for_timeout") is False
            for row in hybrid
        ),
        "funnel_qualified": funnel.get("status") == "qualified",
        "augmented_watchdog_pass": bool(
            augmented.get("status") == "measured_shard_pass"
            and augmented.get("target") == "hybrid"
        ),
        "augmented_vs_schur_gates_pass": bool(
            comparison_gates and all(comparison_gates.values())
        ),
        "one_same_clean_numerical_source": source_shas == {source_sha},
    }
    failures = [name for name, passed in checks.items() if not passed]
    hybrid_component_pass = not failures
    return {
        "schema_version": "task033.phaseC-summary.v1",
        "record_type": "task033_p3_h5_phaseC_summary",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "hybrid_component_closed_full3d_not_run_by_memory_gate"
            if hybrid_component_pass
            else "phaseC_not_closed"
        ),
        "identity": {
            "degree": PHASEC_DEGREE,
            "h_nm": PHASEC_H_NM,
            "mpi_size": PHASEC_MPI_SIZE,
            "source_commit_full_sha": source_sha,
            "ordinary_default_changed": False,
            "whole_phaseC_pass": False,
        },
        "disposition": {
            "full3d_direct": "not_run_by_memory_gate",
            "hybrid_m80_m120_m160": (
                "component_pass" if hybrid_component_pass else "not_closed"
            ),
            "augmented_vs_schur_minimal_m160": (
                "component_pass"
                if checks["augmented_vs_schur_gates_pass"]
                else "not_closed"
            ),
            "selected_plane_e_h_against_same_degree_full3d": "not_available",
            "phaseC_whole_chain": "not_passed",
            "p3_h3": "not_approved",
            "p4_target": "not_approved",
            "h_adaptivity": "deferred",
        },
        "checks": checks,
        "failures": failures,
        "evidence": {
            "preflight": _descriptor(preflight_path),
            "funnel": _descriptor(funnel_path),
            "hybrid_watchdogs": [_descriptor(path) for path in hybrid_paths],
            "augmented_watchdog": _descriptor(augmented_path),
        },
        "measurements": {
            "funnel_qualification": funnel.get("qualification"),
            "funnel_comparisons": funnel.get("comparisons"),
            "augmented_vs_schur": comparison,
            "memory_authority_gib": {
                str(row.get("requested_modes")): (
                    (row.get("resource_authority") or {}).get(
                        "memory_authority_gib"
                    )
                )
                for row in hybrid
            },
            "augmented_memory_authority_gib": (
                (augmented.get("resource_authority") or {}).get(
                    "memory_authority_gib"
                )
            ),
        },
        "limitations": [
            "The Hybrid modal funnel and path equivalence do not replace a same-degree full3D reference.",
            "Selected-plane E/H and per-order full3D deltas remain unclosed because the full3D candidate failed C0.",
            "This result does not authorize p3/h3, p4 target Hybrid, or h adaptivity.",
        ],
    }
