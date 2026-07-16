"""Fail-closed qualification contracts for Task033 QEP shards and studies."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.task033_qep_measurement import (
    LEFT_CANDIDATE_POOL_POLICY,
    MESH_LEVELS_NM,
    MPI_SIZES,
    task033_left_candidate_pool_size,
)


FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
ANALYTIC_MATERIALS = ("air", "lossy_homogeneous")
PATTERNED_MATERIAL = "stage4_xy"
TREND_DEGREES = (1, 2, 3, 4)
TREND_H_NM = (5.0, 3.0, 2.5)

RIGHT_RESIDUAL_MAX = 1.0e-10
LEFT_RESIDUAL_MAX = 1.0e-8
BIORTHOGONALITY_MAX = 1.0e-6
LEFT_RIGHT_BETA_PAIR_RELATIVE_ERROR_MAX = 1.0e-7
RAISED_QUADRATURE_MATRIX_DELTA_MAX = 2.0e-12
TRACKING_OVERLAP_MIN = 0.5
TRACKING_RELATIVE_BETA_DRIFT_MAX = 0.25
TRACKING_COMPACT_KIND = (
    "measured_common_fourier_left_right_mode_fingerprints"
)
P3_ONLY_PARTIAL_CLASSIFICATION = "partial_p3_only"
CONTROLLED_P4_NUMERICAL_GATE_FAILURES = frozenset(
    {
        "polynomial_relative_residual_le_1e-10",
        "left_polynomial_relative_residual_le_1e-8",
        "biorthogonality_identity_error_le_1e-6",
        "left_right_beta_pair_relative_error_le_1e-7",
    }
)
QEP_SHARD_CHECK_NAMES = frozenset(
    {
        "record_identity",
        "candidate_axes",
        "measurement_identity",
        "measured_shard_status",
        "measured_pde_solver_identity",
        "no_exception_failure_payload",
        "source_identity",
        "resource_authority",
        "converged_eigenpairs",
        "right_residual",
        "left_residual",
        "biorthogonality",
        "biorthogonality_infinity_norm_diagnostic",
        "near_degenerate_group_contract",
        "left_candidate_pool_policy",
        "right_requested_modes",
        "left_candidate_requested_modes",
        "left_candidate_converged_modes",
        "left_pair_relative_errors_complete_and_finite",
        "left_pair_relative_error_max_matches_list",
        "left_right_beta_pair_relative_error_le_1e-7",
        "reported_left_right_beta_pair_gate_matches_recomputed",
        "raised_quadrature",
        "analytic_beta_identity",
        "patterned_tracking_compact_input",
        "runtime_preflight_complete",
        "reported_all_required_numerical_gates_pass",
        "reported_converged_eigenpair_gate",
        "reported_right_residual_gate_matches_recomputed",
        "reported_left_residual_gate_matches_recomputed",
        "reported_biorthogonality_gate_matches_recomputed",
        "reported_no_swap_gate",
        "reported_below_termination_gate",
        "reported_formal_resource_gate",
        "reported_raised_quadrature_gate_matches_recomputed",
        "reported_tracking_gate_matches_recomputed",
        "reported_single_shard_identity_gate",
        "reported_source_identity_gate",
        "reported_analytic_gate_matches_recomputed",
    }
)
QEP_CONTROLLED_CHECK_NAMES = frozenset(
    {
        "measured_shard_failed_status",
        "p4_mpi_candidate",
        "measured_pde_not_solver_pass",
        "runtime_preflight_complete",
        "all_required_numerical_gates_reported_failed",
        "positive_gate_failures_are_narrow",
        "reported_numeric_gates_are_boolean",
        "reported_numeric_gates_match_recomputed",
        "controlled_numeric_failure_present",
        "controlled_numeric_failure_whitelist",
        "no_exception_failure_payload",
        "converged_eigenpair",
        "no_swap",
        "below_controlled_termination",
        "formal_resource_authority_pass",
        "raised_quadrature_pass",
        "patterned_tracking_compact_ready",
        "single_shard_only_not_physical_qualification",
        "source_identity_stable_clean_pass",
        "analytic_beta_error_finite",
    }
)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _full_sha(value: object) -> bool:
    return isinstance(value, str) and FULL_SHA.fullmatch(value.lower()) is not None


def _complex_value(value: object) -> complex | None:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        return None
    real = _finite_number(value[0])
    imaginary = _finite_number(value[1])
    if real is None or imaginary is None:
        return None
    return complex(real, imaginary)


def _normalized_complex_vector(value: object) -> tuple[complex, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    parsed = tuple(_complex_value(item) for item in value)
    if not parsed or any(item is None for item in parsed):
        return None
    vector = tuple(complex(item) for item in parsed if item is not None)
    norm = math.sqrt(sum(abs(item) ** 2 for item in vector))
    if not math.isfinite(norm) or norm <= 1.0e-14:
        return None
    return tuple(item / norm for item in vector)


def _tracking_compact(record: Mapping[str, Any]) -> dict[str, Any] | None:
    numerical = record.get("numerical_results")
    numerical = numerical if isinstance(numerical, Mapping) else {}
    tracking = numerical.get("cross_h_tracking")
    if not isinstance(tracking, Mapping):
        return None
    if (
        tracking.get("evidence_kind")
        != "measured_per_shard_input_for_cross_h_tracking"
        or tracking.get("status") != "compact_input_ready_for_aggregate"
        or tracking.get("aggregate_recomputation_required") is not True
    ):
        return None
    compact = tracking.get("compact_evidence")
    if not isinstance(compact, Mapping):
        return None
    if (
        compact.get("evidence_kind") != TRACKING_COMPACT_KIND
        or compact.get("status")
        != "compact_input_ready_for_cross_h_aggregate"
        or compact.get("assignment_performed_in_shard") is not False
        or compact.get("cross_h_vector_dot_performed") is not False
        or compact.get("full_eigenvector_gathered") is not False
    ):
        return None
    fingerprint_length = compact.get("fingerprint_length")
    modes = compact.get("modes")
    if (
        type(fingerprint_length) is not int
        or fingerprint_length < 3
        or not isinstance(modes, list)
        or len(modes) < 2
        or compact.get("mode_count") != len(modes)
    ):
        return None
    parsed_modes: list[dict[str, Any]] = []
    indices: set[int] = set()
    for row in modes:
        if not isinstance(row, Mapping) or type(row.get("mode_index")) is not int:
            return None
        index = int(row["mode_index"])
        if index in indices:
            return None
        indices.add(index)
        beta = _complex_value(row.get("beta_per_nm"))
        right = _normalized_complex_vector(row.get("right_fourier_fingerprint"))
        left = _normalized_complex_vector(row.get("left_fourier_fingerprint"))
        if (
            beta is None
            or right is None
            or left is None
            or len(right) != fingerprint_length
            or len(left) != fingerprint_length
        ):
            return None
        parsed_modes.append(
            {
                "mode_index": index,
                "beta": beta,
                "right": right,
                "left": left,
                "direction": row.get("direction"),
                "kind": row.get("kind"),
            }
        )
    parsed_modes.sort(key=lambda row: int(row["mode_index"]))
    return {
        "probe_orders": compact.get("probe_orders"),
        "components_per_order": compact.get("components_per_order"),
        "fingerprint_length": fingerprint_length,
        "modes": parsed_modes,
    }


def _fingerprint_overlap(left: Sequence[complex], right: Sequence[complex]) -> float:
    value = abs(sum(first.conjugate() * second for first, second in zip(left, right)))
    return min(1.0, max(0.0, float(value)))


def recompute_cross_h_tracking(
    previous_record: Mapping[str, Any],
    current_record: Mapping[str, Any],
    *,
    previous_h_nm: float,
    current_h_nm: float,
) -> dict[str, Any]:
    """Recompute one cross-h assignment from measured compact mode evidence."""

    previous = _tracking_compact(previous_record)
    current = _tracking_compact(current_record)
    failures: list[str] = []
    if previous is None:
        failures.append("previous_compact_tracking_evidence_missing_or_invalid")
    if current is None:
        failures.append("current_compact_tracking_evidence_missing_or_invalid")
    if previous is None or current is None:
        return {
            "evidence_kind": "aggregate_recomputed_cross_h_mode_tracking",
            "previous_h_nm": previous_h_nm,
            "current_h_nm": current_h_nm,
            "matches": [],
            "minimum_overlap": None,
            "maximum_relative_beta_drift": None,
            "complete_stable_assignment": False,
            "pass": False,
            "failures": failures,
        }
    if (
        previous["fingerprint_length"] != current["fingerprint_length"]
        or previous["probe_orders"] != current["probe_orders"]
        or previous["components_per_order"] != current["components_per_order"]
    ):
        failures.append("common_physical_probe_dictionary_mismatch")
    previous_modes = previous["modes"]
    current_modes = current["modes"]
    if len(previous_modes) != len(current_modes):
        failures.append("mode_count_changed_across_h")

    from scipy.optimize import linear_sum_assignment
    import numpy as np

    overlap = np.empty((len(previous_modes), len(current_modes)), dtype=float)
    beta_drift = np.empty_like(overlap)
    compatibility = np.empty_like(overlap, dtype=bool)
    for row, first in enumerate(previous_modes):
        for column, second in enumerate(current_modes):
            forward = _fingerprint_overlap(first["left"], second["right"])
            reverse = _fingerprint_overlap(second["left"], first["right"])
            overlap[row, column] = math.sqrt(forward * reverse)
            beta_drift[row, column] = abs(first["beta"] - second["beta"]) / max(
                abs(first["beta"]), abs(second["beta"]), 1.0e-12
            )
            directions = (first.get("direction"), second.get("direction"))
            compatibility[row, column] = bool(
                directions[0] == directions[1]
                or "ambiguous" in directions
            )
    cost = (
        1.0
        - overlap
        + 0.05 * np.minimum(beta_drift, 10.0)
        + 2.0 * (~compatibility)
    )
    rows, columns = linear_sum_assignment(cost)
    matches = []
    for row, column in zip(rows, columns):
        matches.append(
            {
                "previous_mode_index": previous_modes[int(row)]["mode_index"],
                "current_mode_index": current_modes[int(column)]["mode_index"],
                "symmetric_left_right_fourier_overlap": float(
                    overlap[int(row), int(column)]
                ),
                "relative_beta_drift": float(beta_drift[int(row), int(column)]),
                "direction_compatible": bool(compatibility[int(row), int(column)]),
            }
        )
    minimum_overlap = min(
        (row["symmetric_left_right_fourier_overlap"] for row in matches),
        default=None,
    )
    maximum_drift = max(
        (row["relative_beta_drift"] for row in matches), default=None
    )
    complete = bool(
        not failures
        and len(matches) == len(previous_modes) == len(current_modes)
        and all(row["direction_compatible"] for row in matches)
    )
    if minimum_overlap is None or minimum_overlap < TRACKING_OVERLAP_MIN:
        failures.append("minimum_common_fourier_overlap_below_gate")
    if maximum_drift is None or maximum_drift > TRACKING_RELATIVE_BETA_DRIFT_MAX:
        failures.append("maximum_relative_beta_drift_above_gate")
    if not complete:
        failures.append("cross_h_assignment_incomplete_or_unstable")
    failures = list(dict.fromkeys(failures))
    return {
        "evidence_kind": "aggregate_recomputed_cross_h_mode_tracking",
        "overlap_identity": (
            "symmetric geometric mean of measured common Fourier left/right moments"
        ),
        "previous_h_nm": previous_h_nm,
        "current_h_nm": current_h_nm,
        "matches": matches,
        "minimum_overlap": minimum_overlap,
        "minimum_overlap_gate": TRACKING_OVERLAP_MIN,
        "maximum_relative_beta_drift": maximum_drift,
        "maximum_relative_beta_drift_gate": TRACKING_RELATIVE_BETA_DRIFT_MAX,
        "complete_stable_assignment": complete,
        "pass": not failures,
        "failures": failures,
    }


def source_identity_gate(provenance: Mapping[str, Any] | None) -> dict[str, Any]:
    """Require one clean, full-SHA checkout that stays stable across the run."""

    source = provenance or {}
    before = source.get("head_before_sha", source.get("commit_sha"))
    after = source.get("head_after_sha")
    attested = source.get("verified_clean_sha")
    before_status = source.get("tracked_status_before")
    after_status = source.get("tracked_status_after")
    checks = {
        "head_before_full_sha": _full_sha(before),
        "head_after_full_sha": _full_sha(after),
        "attested_full_sha": _full_sha(attested),
        "all_shas_identical": bool(
            _full_sha(before)
            and _full_sha(after)
            and _full_sha(attested)
            and str(before).lower() == str(after).lower() == str(attested).lower()
        ),
        "tracked_clean_before": before_status == "",
        "tracked_clean_after": after_status == "",
        "source_stable_during_run": source.get("source_stable_during_run") is True,
        "source_clean_verified": source.get("source_clean_verified") is True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "head_sha": before if _full_sha(before) else None,
    }


def resource_authority_gate(
    resource: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the authoritative live RSS/cgroup and no-swap contract."""

    values = resource or {}
    worker = _finite_number(values.get("simultaneous_live_worker_rss_sum_bytes"))
    cgroup = _finite_number(values.get("container_cgroup_current_bytes"))
    authority = _finite_number(values.get("memory_authority_bytes"))
    limit = _finite_number(values.get("container_memory_limit_bytes"))
    host_available = _finite_number(values.get("host_available_memory_bytes"))
    swap_current = _finite_number(values.get("container_swap_current_bytes"))
    pswpin = _finite_number(values.get("pswpin_delta_pages"))
    pswpout = _finite_number(values.get("pswpout_delta_pages"))
    expected_authority = (
        None if worker is None or cgroup is None else max(worker, cgroup)
    )
    checks = {
        "worker_rss_readable": worker is not None and worker > 0.0,
        "cgroup_current_readable": cgroup is not None and cgroup > 0.0,
        "authority_is_exact_max": bool(
            authority is not None
            and expected_authority is not None
            and authority == expected_authority
        ),
        "container_limit_readable": limit is not None and limit > 0.0,
        "authority_within_container_limit": bool(
            authority is not None and limit is not None and authority <= limit
        ),
        "host_available_memory_readable": (
            host_available is not None and host_available > 0.0
        ),
        "container_current_swap_zero": swap_current == 0.0,
        "pswpin_delta_zero": pswpin == 0.0,
        "pswpout_delta_zero": pswpout == 0.0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "expected_memory_authority_bytes": expected_authority,
    }


def apply_formal_preflight_gates(
    preflight: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None,
    resource: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Add source/resource failures without weakening the planning preflight."""

    source_gate = source_identity_gate(source)
    resource_gate = resource_authority_gate(resource)
    failures = list(preflight.get("failures") or [])
    failures.extend(f"source:{name}" for name in source_gate["failures"])
    failures.extend(f"resource:{name}" for name in resource_gate["failures"])
    failures = list(dict.fromkeys(failures))
    return {
        **dict(preflight),
        "source_identity_gate": source_gate,
        "resource_authority_gate": resource_gate,
        "runtime_contract_verified": not failures,
        "launch_eligible": not failures,
        "failures": failures,
    }


def _classification(record: Mapping[str, Any]) -> Mapping[str, Any]:
    numerical = record.get("numerical_results")
    if not isinstance(numerical, Mapping):
        return {}
    value = numerical.get("left_right_classification")
    return value if isinstance(value, Mapping) else {}


def _strict_candidate_key(
    candidate: Mapping[str, Any] | None,
) -> tuple[str, int, float, int] | None:
    values = candidate or {}
    material = values.get("material_kind")
    degree = values.get("degree")
    h_nm = _finite_number(values.get("h_nm"))
    mpi_size = values.get("mpi_size")
    if not (
        type(material) is str
        and material in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
        and type(degree) is int
        and degree in TREND_DEGREES
        and h_nm is not None
        and h_nm in MESH_LEVELS_NM
        and type(mpi_size) is int
        and mpi_size in MPI_SIZES
    ):
        return None
    return material, degree, h_nm, mpi_size


def _near_degenerate_group_contract(
    classification: Mapping[str, Any], *, requested_modes: int
) -> bool:
    groups = classification.get("near_degenerate_groups")
    if not isinstance(groups, list) or not groups or requested_modes < 1:
        return False
    observed: set[int] = set()
    for raw_group in groups:
        if not isinstance(raw_group, Mapping):
            return False
        indices = raw_group.get("indices")
        if (
            not isinstance(indices, list)
            or not indices
            or any(type(index) is not int for index in indices)
            or len(indices) != len(set(indices))
            or any(index < 0 or index >= requested_modes for index in indices)
            or observed.intersection(indices)
        ):
            return False
        spread = _finite_number(raw_group.get("max_relative_beta_spread"))
        condition = _finite_number(raw_group.get("overlap_condition"))
        post_error = _finite_number(
            raw_group.get("post_normalization_identity_error")
        )
        expected_method = (
            "near_degenerate_block_inverse"
            if len(indices) > 1
            else "diagonal_qprime"
        )
        if not (
            _complex_value(raw_group.get("beta_center_per_nm")) is not None
            and spread is not None
            and spread >= 0.0
            and condition is not None
            and 1.0 - 1.0e-12 <= condition <= 1.0e12
            and post_error is not None
            and post_error >= 0.0
            and raw_group.get("normalization_method") == expected_method
        ):
            return False
        observed.update(indices)
    return observed == set(range(requested_modes))


def qep_shard_gate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one measured shard without promoting it to aggregate success."""

    numerical = record.get("numerical_results")
    numerical = numerical if isinstance(numerical, Mapping) else {}
    classification = _classification(record)
    quadrature = numerical.get("quadrature")
    quadrature = quadrature if isinstance(quadrature, Mapping) else {}
    raised = quadrature.get("raised_comparison")
    raised = raised if isinstance(raised, Mapping) else {}
    resource = record.get("resource_measurements")
    resource = resource if isinstance(resource, Mapping) else {}
    formal_resource = resource.get("formal_resource_authority")
    formal_resource = (
        formal_resource if isinstance(formal_resource, Mapping) else {}
    )
    candidate = record.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    candidate_key = _strict_candidate_key(candidate)
    material = candidate.get("material_kind")
    analytic_error = _finite_number(numerical.get("analytic_beta_relative_error"))
    right_residual = _finite_number(
        classification.get("right_polynomial_relative_residual_max")
    )
    left_residual = _finite_number(
        classification.get("left_polynomial_relative_residual_max")
    )
    raised_quadrature_delta = _finite_number(
        raised.get("max_matrix_relative_difference")
    )
    right_requested = classification.get("right_requested_modes")
    left_requested = classification.get("left_candidate_requested_modes")
    left_converged = classification.get("left_candidate_converged_modes")
    right_requested_valid = type(right_requested) is int and right_requested >= 2
    left_requested_valid = type(left_requested) is int and left_requested > 0
    left_converged_valid = type(left_converged) is int and left_converged >= 0
    required_left_requested = (
        task033_left_candidate_pool_size(int(right_requested))
        if right_requested_valid
        else None
    )
    raw_pair_errors = classification.get("left_pair_relative_errors")
    pair_errors = (
        [_finite_number(value) for value in raw_pair_errors]
        if isinstance(raw_pair_errors, list)
        else []
    )
    pair_errors_valid = bool(
        right_requested_valid
        and len(pair_errors) == int(right_requested)
        and all(value is not None and value >= 0.0 for value in pair_errors)
    )
    recomputed_pair_max = (
        max(float(value) for value in pair_errors if value is not None)
        if pair_errors_valid
        else None
    )
    recorded_pair_max = _finite_number(
        classification.get("left_pair_relative_error_max")
    )
    biorthogonality_entry_error = _finite_number(
        classification.get("biorthogonality_identity_error")
    )
    biorthogonality_infinity_error = _finite_number(
        classification.get("biorthogonality_infinity_norm_error")
    )
    pair_max_consistent = bool(
        recomputed_pair_max is not None
        and recorded_pair_max is not None
        and math.isclose(
            recorded_pair_max,
            recomputed_pair_max,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
    )
    pair_error_pass = bool(
        recomputed_pair_max is not None
        and recomputed_pair_max <= LEFT_RIGHT_BETA_PAIR_RELATIVE_ERROR_MAX
    )
    record_gates = record.get("gates")
    record_gates = record_gates if isinstance(record_gates, Mapping) else {}
    runtime_preflight = record.get("runtime_preflight")
    runtime_preflight = (
        runtime_preflight if isinstance(runtime_preflight, Mapping) else {}
    )
    reported_pair_gate = record_gates.get(
        "left_right_beta_pair_relative_error_le_1e-7"
    )
    checks = {
        "record_identity": (
            record.get("schema_version")
            == "task033.case091.qep-measurement.v2"
            and record.get("record_type")
            == "task033_qep_measurement_shard"
            and record.get("case_id")
            == "091_hybrid_hp_adaptivity_feasibility"
        ),
        "candidate_axes": candidate_key is not None,
        "measurement_identity": (
            isinstance(record.get("identity"), Mapping)
            and record["identity"].get("is_pde_run") is True
            and record["identity"].get("is_memory_measurement") is True
            and record["identity"].get("result_identity")
            == "measured_shard"
            and record["identity"].get("is_physical_qualification_record")
            is False
            and record["identity"].get("physical_qualified") is False
            and record["identity"].get("ordinary_default_changed") is False
            and record["identity"].get("proves_0p7nm_feasible") is False
        ),
        "measured_shard_status": record.get("status") == "measured_shard_pass",
        "measured_pde_solver_identity": (
            isinstance(record.get("identity"), Mapping)
            and record["identity"].get("is_solver_pass") is True
        ),
        "no_exception_failure_payload": record.get("failure") in (None, {}),
        "source_identity": source_identity_gate(
            record.get("provenance")
            if isinstance(record.get("provenance"), Mapping)
            else None
        )["pass"],
        "resource_authority": resource_authority_gate(formal_resource)["pass"],
        "converged_eigenpairs": (
            type(numerical.get("converged_eigenpairs")) is int
            and right_requested_valid
            and numerical.get("converged_eigenpairs") >= right_requested
        ),
        "right_residual": bool(
            right_residual is not None
            and 0.0 <= right_residual <= RIGHT_RESIDUAL_MAX
        ),
        "left_residual": bool(
            left_residual is not None
            and 0.0 <= left_residual <= LEFT_RESIDUAL_MAX
        ),
        "biorthogonality": bool(
            biorthogonality_entry_error is not None
            and 0.0
            <= biorthogonality_entry_error
            <= BIORTHOGONALITY_MAX
        ),
        "biorthogonality_infinity_norm_diagnostic": bool(
            biorthogonality_entry_error is not None
            and biorthogonality_infinity_error is not None
            and biorthogonality_infinity_error >= 0.0
            and biorthogonality_infinity_error + 1.0e-15
            >= biorthogonality_entry_error
            and right_requested_valid
            and biorthogonality_infinity_error
            <= int(right_requested) * biorthogonality_entry_error + 1.0e-15
        ),
        "near_degenerate_group_contract": bool(
            right_requested_valid
            and _near_degenerate_group_contract(
                classification,
                requested_modes=int(right_requested),
            )
        ),
        "left_candidate_pool_policy": (
            classification.get("left_candidate_pool_policy")
            == LEFT_CANDIDATE_POOL_POLICY
        ),
        "right_requested_modes": right_requested_valid,
        "left_candidate_requested_modes": bool(
            left_requested_valid
            and required_left_requested is not None
            and int(left_requested) == int(required_left_requested)
        ),
        "left_candidate_converged_modes": bool(
            left_converged_valid
            and right_requested_valid
            and int(left_converged) >= int(right_requested)
        ),
        "left_pair_relative_errors_complete_and_finite": pair_errors_valid,
        "left_pair_relative_error_max_matches_list": pair_max_consistent,
        "left_right_beta_pair_relative_error_le_1e-7": pair_error_pass,
        "reported_left_right_beta_pair_gate_matches_recomputed": (
            type(reported_pair_gate) is bool
            and reported_pair_gate is pair_error_pass
        ),
        "raised_quadrature": bool(
            raised.get("pass") is True
            and raised_quadrature_delta is not None
            and 0.0
            <= raised_quadrature_delta
            <= RAISED_QUADRATURE_MATRIX_DELTA_MAX
        ),
        "analytic_beta_identity": (
            analytic_error is not None and analytic_error >= 0.0
            if material in ANALYTIC_MATERIALS
            else analytic_error is None
        ),
        "patterned_tracking_compact_input": (
            _tracking_compact(record) is not None
            if material == PATTERNED_MATERIAL
            else True
        ),
    }
    expected_analytic_gate = (
        "not_applicable_patterned_cross_section"
        if material == PATTERNED_MATERIAL
        else True
    )
    checks.update(
        {
            "runtime_preflight_complete": (
                runtime_preflight.get("runtime_contract_verified") is True
                and runtime_preflight.get("launch_eligible") is True
                and runtime_preflight.get("failures") == []
            ),
            "reported_all_required_numerical_gates_pass": (
                record_gates.get("all_required_numerical_gates_pass") is True
            ),
            "reported_converged_eigenpair_gate": (
                record_gates.get("converged_eigenpair")
                is checks["converged_eigenpairs"]
            ),
            "reported_right_residual_gate_matches_recomputed": (
                record_gates.get("polynomial_relative_residual_le_1e-10")
                is checks["right_residual"]
            ),
            "reported_left_residual_gate_matches_recomputed": (
                record_gates.get("left_polynomial_relative_residual_le_1e-8")
                is checks["left_residual"]
            ),
            "reported_biorthogonality_gate_matches_recomputed": (
                record_gates.get("biorthogonality_identity_error_le_1e-6")
                is checks["biorthogonality"]
            ),
            "reported_no_swap_gate": record_gates.get("no_swap") is True,
            "reported_below_termination_gate": (
                record_gates.get("below_controlled_termination") is True
            ),
            "reported_formal_resource_gate": (
                record_gates.get("formal_resource_authority_pass") is True
            ),
            "reported_raised_quadrature_gate_matches_recomputed": (
                record_gates.get("raised_quadrature_pass")
                is checks["raised_quadrature"]
            ),
            "reported_tracking_gate_matches_recomputed": (
                record_gates.get("patterned_tracking_compact_ready")
                is checks["patterned_tracking_compact_input"]
            ),
            "reported_single_shard_identity_gate": (
                record_gates.get(
                    "single_shard_only_not_physical_qualification"
                )
                is True
            ),
            "reported_source_identity_gate": (
                record_gates.get("source_identity_stable_clean_pass") is True
            ),
            "reported_analytic_gate_matches_recomputed": (
                record_gates.get("analytic_beta_error_finite")
                == expected_analytic_gate
            ),
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def qep_p4_controlled_negative_gate(
    record: Mapping[str, Any], *, mpi_size: int = 1
) -> dict[str, Any]:
    """Accept only a complete p4 shard with a narrow numerical Gate failure.

    This is deliberately stricter than ``status == measured_shard_failed``.
    Source, resource, swap, launch, convergence, quadrature, tracking, missing
    numerical payloads, and exception-derived failures remain hard failures.
    """

    positive = qep_shard_gate(record)
    positive_checks = positive["checks"]
    allowed_positive_failures = {
        "measured_shard_status",
        "measured_pde_solver_identity",
        "reported_all_required_numerical_gates_pass",
        "right_residual",
        "left_residual",
        "biorthogonality",
        "left_right_beta_pair_relative_error_le_1e-7",
    }
    observed_positive_failures = set(positive["failures"])
    numerical_positive_failures = observed_positive_failures - {
        "measured_shard_status",
        "measured_pde_solver_identity",
        "reported_all_required_numerical_gates_pass",
    }

    candidate = record.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    identity = record.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    runtime_preflight = record.get("runtime_preflight")
    runtime_preflight = (
        runtime_preflight if isinstance(runtime_preflight, Mapping) else {}
    )
    gates = record.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    numerical = record.get("numerical_results")
    numerical = numerical if isinstance(numerical, Mapping) else {}
    quadrature = numerical.get("quadrature")
    quadrature = quadrature if isinstance(quadrature, Mapping) else {}
    raised = quadrature.get("raised_comparison")
    raised = raised if isinstance(raised, Mapping) else {}
    tracking = numerical.get("cross_h_tracking")
    tracking = tracking if isinstance(tracking, Mapping) else {}

    reported_numeric_gates = {
        "polynomial_relative_residual_le_1e-10": gates.get(
            "polynomial_relative_residual_le_1e-10"
        ),
        "left_polynomial_relative_residual_le_1e-8": gates.get(
            "left_polynomial_relative_residual_le_1e-8"
        ),
        "biorthogonality_identity_error_le_1e-6": gates.get(
            "biorthogonality_identity_error_le_1e-6"
        ),
        "left_right_beta_pair_relative_error_le_1e-7": gates.get(
            "left_right_beta_pair_relative_error_le_1e-7"
        ),
    }
    recomputed_numeric_gates = {
        "polynomial_relative_residual_le_1e-10": positive_checks.get(
            "right_residual"
        ),
        "left_polynomial_relative_residual_le_1e-8": positive_checks.get(
            "left_residual"
        ),
        "biorthogonality_identity_error_le_1e-6": positive_checks.get(
            "biorthogonality"
        ),
        "left_right_beta_pair_relative_error_le_1e-7": positive_checks.get(
            "left_right_beta_pair_relative_error_le_1e-7"
        ),
    }
    controlled_failure_gates = sorted(
        name for name, value in reported_numeric_gates.items() if value is False
    )
    reported_numeric_boolean = all(
        type(value) is bool for value in reported_numeric_gates.values()
    )
    reported_numeric_matches = all(
        reported_numeric_gates[name] is recomputed_numeric_gates[name]
        for name in reported_numeric_gates
    )

    analytic_gate = gates.get("analytic_beta_error_finite")
    expected_analytic_gate = (
        "not_applicable_patterned_cross_section"
        if candidate.get("material_kind") == PATTERNED_MATERIAL
        else True
    )
    required_nonnegative_gates = {
        "converged_eigenpair": gates.get("converged_eigenpair") is True,
        "no_swap": gates.get("no_swap") is True,
        "below_controlled_termination": (
            gates.get("below_controlled_termination") is True
        ),
        "formal_resource_authority_pass": (
            gates.get("formal_resource_authority_pass") is True
        ),
        "raised_quadrature_pass": gates.get("raised_quadrature_pass") is True,
        "patterned_tracking_compact_ready": (
            gates.get("patterned_tracking_compact_ready") is True
        ),
        "single_shard_only_not_physical_qualification": (
            gates.get("single_shard_only_not_physical_qualification") is True
        ),
        "source_identity_stable_clean_pass": (
            gates.get("source_identity_stable_clean_pass") is True
        ),
        "analytic_beta_error_finite": analytic_gate == expected_analytic_gate,
    }
    checks = {
        "measured_shard_failed_status": (
            record.get("status") == "measured_shard_failed"
        ),
        "p4_mpi_candidate": (
            candidate.get("degree") == 4
            and candidate.get("mpi_size") == mpi_size
            and candidate.get("material_kind")
            in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
            and _finite_number(candidate.get("h_nm")) in TREND_H_NM
        ),
        "measured_pde_not_solver_pass": (
            identity.get("is_pde_run") is True
            and identity.get("is_solver_pass") is False
            and identity.get("is_physical_qualification_record") is False
            and identity.get("physical_qualified") is False
        ),
        "runtime_preflight_complete": (
            runtime_preflight.get("runtime_contract_verified") is True
            and runtime_preflight.get("launch_eligible") is True
            and runtime_preflight.get("failures") == []
        ),
        "all_required_numerical_gates_reported_failed": (
            gates.get("all_required_numerical_gates_pass") is False
        ),
        "positive_gate_failures_are_narrow": (
            "measured_shard_status" in observed_positive_failures
            and bool(numerical_positive_failures)
            and observed_positive_failures <= allowed_positive_failures
        ),
        "reported_numeric_gates_are_boolean": reported_numeric_boolean,
        "reported_numeric_gates_match_recomputed": reported_numeric_matches,
        "controlled_numeric_failure_present": bool(controlled_failure_gates),
        "controlled_numeric_failure_whitelist": (
            set(controlled_failure_gates)
            <= CONTROLLED_P4_NUMERICAL_GATE_FAILURES
        ),
        "no_exception_failure_payload": (
            record.get("failure") in (None, {})
            and raised.get("failure") is None
            and tracking.get("failure") is None
        ),
        **required_nonnegative_gates,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "controlled_failure_gates": controlled_failure_gates,
        "positive_shard_gate_failures": sorted(observed_positive_failures),
    }


def _candidate_key(record: Mapping[str, Any]) -> tuple[str, int, float, int] | None:
    candidate = record.get("candidate")
    return _strict_candidate_key(
        candidate if isinstance(candidate, Mapping) else None
    )


def _nonincreasing(values: Sequence[float], *, slack: float = 0.05) -> bool:
    return all(
        later <= earlier * (1.0 + slack) + 1.0e-15
        for earlier, later in zip(values, values[1:], strict=False)
    ) and values[-1] < values[0]


def aggregate_qep_shards(
    records: Sequence[Mapping[str, Any]],
    *,
    mpi_size: int = 1,
    allow_p4_controlled_negative: bool = False,
) -> dict[str, Any]:
    """Aggregate h/p QEP evidence with one narrow p4-only partial lane."""

    required_keys = {
        (material, degree, h_nm, mpi_size)
        for material in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
        for degree in TREND_DEGREES
        for h_nm in TREND_H_NM
    }
    parsed = [(_candidate_key(record), record) for record in records]
    required_records = [
        (key, record) for key, record in parsed if key in required_keys
    ]
    by_key = {key: record for key, record in required_records}
    duplicate_count = len(required_records) - len(
        {key for key, _ in required_records}
    )
    unexpected_record_count = sum(
        key not in required_keys for key, _ in parsed
    )
    missing = sorted(required_keys - set(by_key))
    shard_results: dict[str, Any] = {}
    positive_by_key: dict[tuple[str, int, float, int], dict[str, Any]] = {}
    controlled_negative_by_key: dict[
        tuple[str, int, float, int], dict[str, Any]
    ] = {}
    negative_observations: list[dict[str, Any]] = []
    for key, record in sorted(by_key.items()):
        if key not in required_keys:
            continue
        positive = qep_shard_gate(record)
        positive_by_key[key] = positive
        controlled = (
            qep_p4_controlled_negative_gate(record, mpi_size=mpi_size)
            if key[1] == 4
            else {
                "pass": False,
                "checks": {"controlled_negative_is_p4_only": False},
                "failures": ["controlled_negative_is_p4_only"],
                "controlled_failure_gates": [],
            }
        )
        controlled_negative_by_key[key] = controlled
        if positive["pass"]:
            disposition = "pass"
        elif allow_p4_controlled_negative and controlled["pass"]:
            disposition = "controlled_numeric_negative"
            negative_observations.append(
                {
                    "candidate": {
                        "material_kind": key[0],
                        "degree": key[1],
                        "h_nm": key[2],
                        "mpi_size": key[3],
                    },
                    "status": "measured_shard_failed",
                    "disposition": "controlled_numeric_negative",
                    "controlled_failure_gates": list(
                        controlled["controlled_failure_gates"]
                    ),
                    "is_qep_component_qualified": False,
                }
            )
        else:
            disposition = "failed"
        shard_results["|".join(map(str, key))] = {
            "pass": positive["pass"],
            "disposition": disposition,
            "positive_gate": positive,
            "controlled_negative_gate": controlled,
        }

    complete_unique = bool(
        not missing
        and duplicate_count == 0
        and unexpected_record_count == 0
        and len(shard_results) == len(required_keys)
    )
    all_shards_pass = bool(
        complete_unique
        and all(result["disposition"] == "pass" for result in shard_results.values())
    )
    lower_keys = {key for key in required_keys if key[1] <= 3}
    p4_keys = {key for key in required_keys if key[1] == 4}
    lower_shards_pass = bool(
        complete_unique
        and all(positive_by_key.get(key, {}).get("pass") is True for key in lower_keys)
    )
    p4_outcomes_controlled = bool(
        complete_unique
        and all(
            positive_by_key.get(key, {}).get("pass") is True
            or (
                allow_p4_controlled_negative
                and controlled_negative_by_key.get(key, {}).get("pass") is True
            )
            for key in p4_keys
        )
    )

    analytic_trends: dict[str, Any] = {}
    analytic_trend_pass_by_degree = {degree: True for degree in TREND_DEGREES}
    p2_relative: dict[str, Any] = {}
    p2_relative_pass_by_degree = {3: True, 4: True}
    for material in ANALYTIC_MATERIALS:
        material_trends: dict[str, Any] = {}
        for degree in TREND_DEGREES:
            values: list[float] = []
            for h_nm in TREND_H_NM:
                record = by_key.get((material, degree, h_nm, mpi_size), {})
                numerical = record.get("numerical_results") or {}
                value = _finite_number(numerical.get("analytic_beta_relative_error"))
                if value is None:
                    values = []
                    break
                values.append(value)
            passed = len(values) == len(TREND_H_NM) and _nonincreasing(values)
            analytic_trend_pass_by_degree[degree] &= passed
            material_trends[f"p{degree}"] = {
                "h_nm": list(TREND_H_NM),
                "relative_errors": values,
                "h_refinement_trend_pass": passed,
            }
        analytic_trends[material] = material_trends

        relative_rows: list[dict[str, Any]] = []
        for h_nm in TREND_H_NM:
            p2_record = by_key.get((material, 2, h_nm, mpi_size), {})
            p2_error = _finite_number(
                (p2_record.get("numerical_results") or {}).get(
                    "analytic_beta_relative_error"
                )
            )
            ratios: dict[str, float | None] = {}
            for degree in TREND_DEGREES:
                record = by_key.get((material, degree, h_nm, mpi_size), {})
                error = _finite_number(
                    (record.get("numerical_results") or {}).get(
                        "analytic_beta_relative_error"
                    )
                )
                ratios[f"p{degree}_error_over_p2"] = (
                    None
                    if error is None or p2_error is None
                    else error / max(p2_error, 1.0e-300)
                )
            relative_rows.append({"h_nm": h_nm, **ratios})
        p2_relative[material] = relative_rows
        finest = relative_rows[-1]
        for degree in (3, 4):
            ratio = finest[f"p{degree}_error_over_p2"]
            p2_relative_pass_by_degree[degree] &= bool(
                ratio is not None and float(ratio) <= 1.0
            )

    patterned_tracking: dict[str, Any] = {}
    patterned_pass_by_degree = {degree: True for degree in TREND_DEGREES}
    for degree in TREND_DEGREES:
        rows: list[dict[str, Any]] = []
        for previous_h_nm, current_h_nm in zip(
            TREND_H_NM,
            TREND_H_NM[1:],
            strict=False,
        ):
            previous_record = by_key.get(
                (PATTERNED_MATERIAL, degree, previous_h_nm, mpi_size), {}
            )
            current_record = by_key.get(
                (PATTERNED_MATERIAL, degree, current_h_nm, mpi_size), {}
            )
            tracking = recompute_cross_h_tracking(
                previous_record,
                current_record,
                previous_h_nm=previous_h_nm,
                current_h_nm=current_h_nm,
            )
            patterned_pass_by_degree[degree] &= tracking["pass"] is True
            rows.append(tracking)
        patterned_tracking[f"p{degree}"] = rows

    lower_analytic_pass = bool(
        all(analytic_trend_pass_by_degree[degree] for degree in (1, 2, 3))
        and p2_relative_pass_by_degree[3]
    )
    full_analytic_pass = bool(
        lower_analytic_pass
        and analytic_trend_pass_by_degree[4]
        and p2_relative_pass_by_degree[4]
    )
    lower_patterned_pass = all(
        patterned_pass_by_degree[degree] for degree in (1, 2, 3)
    )
    full_patterned_pass = bool(
        lower_patterned_pass and patterned_pass_by_degree[4]
    )
    gates = {
        "complete_unique_required_shards": complete_unique,
        "p1_p2_p3_27_shards_pass": lower_shards_pass,
        "p4_9_shards_complete_pass_or_controlled_numeric_negative": (
            p4_outcomes_controlled
        ),
        "p1_p2_p3_analytic_trends_and_p2_relative_pass": lower_analytic_pass,
        "p1_p2_p3_patterned_cross_h_tracking_pass": lower_patterned_pass,
        "all_shard_contracts_pass": all_shards_pass,
        "air_lossy_h_p_trends_and_p2_relative_pass": full_analytic_pass,
        "patterned_residual_biorth_and_cross_h_tracking_pass": (
            full_patterned_pass and all_shards_pass
        ),
    }
    qualified = all(gates.values())
    p3_only_partial = bool(
        allow_p4_controlled_negative
        and complete_unique
        and lower_shards_pass
        and p4_outcomes_controlled
        and bool(negative_observations)
        and lower_analytic_pass
        and lower_patterned_pass
    )
    qualification_classification = (
        "full_p1_p4_qualified"
        if qualified
        else P3_ONLY_PARTIAL_CLASSIFICATION
        if p3_only_partial
        else "not_qualified"
    )
    degree_qualification: dict[str, Any] = {}
    for degree in TREND_DEGREES:
        keys = {key for key in required_keys if key[1] == degree}
        passed_count = sum(
            positive_by_key.get(key, {}).get("pass") is True for key in keys
        )
        negative_count = sum(
            controlled_negative_by_key.get(key, {}).get("pass") is True
            and positive_by_key.get(key, {}).get("pass") is not True
            for key in keys
        )
        if degree <= 3 and lower_shards_pass:
            degree_status = "qualified"
        elif degree == 4 and qualified:
            degree_status = "qualified"
        elif degree == 4 and p3_only_partial:
            degree_status = "controlled_numeric_negative"
        else:
            degree_status = "not_qualified"
        degree_qualification[f"p{degree}"] = {
            "status": degree_status,
            "required_shard_count": len(keys),
            "passed_shard_count": passed_count,
            "controlled_negative_shard_count": negative_count,
        }
    return {
        "schema_version": "task033.qep-aggregate.v1",
        "record_type": "task033_qep_aggregate",
        "status": (
            "qep_component_aggregate_qualified"
            if qualified
            else "qep_component_aggregate_not_qualified"
        ),
        "identity": {
            "is_single_shard": False,
            "is_qep_component_qualified": qualified,
            "is_qep_p3_only_partial": p3_only_partial,
            "is_physical_qualification_record": False,
            "proves_0p7nm_feasible": False,
        },
        "qualification_classification": qualification_classification,
        "mpi_size": mpi_size,
        "required_shard_count": len(required_keys),
        "received_unique_shard_count": len(set(by_key) & required_keys),
        "duplicate_count": duplicate_count,
        "unexpected_record_count": unexpected_record_count,
        "missing_candidates": [list(value) for value in missing],
        "p1_p2_p3_passed_shard_count": sum(
            positive_by_key.get(key, {}).get("pass") is True for key in lower_keys
        ),
        "p4_completed_shard_count": sum(
            positive_by_key.get(key, {}).get("pass") is True
            or controlled_negative_by_key.get(key, {}).get("pass") is True
            for key in p4_keys
        ),
        "negative_observation_count": len(negative_observations),
        "negative_observations": negative_observations,
        "degree_qualification": degree_qualification,
        "shard_gates": shard_results,
        "analytic_beta_trends": analytic_trends,
        "relative_to_p2": p2_relative,
        "patterned_cross_h_tracking": patterned_tracking,
        "source_records": [],
        "gates": gates,
    }


def _expected_aggregate_keys(mpi_size: int) -> set[tuple[str, int, float, int]]:
    return {
        (material, degree, h_nm, mpi_size)
        for material in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
        for degree in TREND_DEGREES
        for h_nm in TREND_H_NM
    }


def _aggregate_shard_closure(
    payload: Mapping[str, Any], *, allow_controlled_p4: bool
) -> dict[str, Any]:
    shard_gates = payload.get("shard_gates")
    shard_gates = shard_gates if isinstance(shard_gates, Mapping) else {}
    expected = _expected_aggregate_keys(1)
    expected_rendered = {"|".join(map(str, key)) for key in expected}
    controlled_keys: set[tuple[str, int, float, int]] = set()
    failures: list[str] = []
    if set(shard_gates) != expected_rendered:
        failures.append("shard_key_closure")
    for rendered, raw in shard_gates.items():
        result = raw if isinstance(raw, Mapping) else {}
        tokens = rendered.split("|")
        try:
            key = (tokens[0], int(tokens[1]), float(tokens[2]), int(tokens[3]))
        except (IndexError, TypeError, ValueError):
            failures.append(f"invalid_shard_key:{rendered}")
            continue
        positive = result.get("positive_gate")
        positive = positive if isinstance(positive, Mapping) else {}
        positive_checks = positive.get("checks")
        positive_checks = positive_checks if isinstance(positive_checks, Mapping) else {}
        positive_failures = positive.get("failures")
        positive_failures = positive_failures if isinstance(positive_failures, list) else None
        controlled = result.get("controlled_negative_gate")
        controlled = controlled if isinstance(controlled, Mapping) else {}
        controlled_checks = controlled.get("checks")
        controlled_checks = controlled_checks if isinstance(controlled_checks, Mapping) else {}
        controlled_failures = controlled.get("failures")
        controlled_failures = controlled_failures if isinstance(controlled_failures, list) else None
        disposition = result.get("disposition")
        if disposition == "pass":
            valid = bool(
                result.get("pass") is True
                and positive.get("pass") is True
                and positive_failures == []
                and set(positive_checks) == QEP_SHARD_CHECK_NAMES
                and all(value is True for value in positive_checks.values())
            )
        elif disposition == "controlled_numeric_negative" and allow_controlled_p4:
            controlled_gate_failures = set(
                controlled.get("controlled_failure_gates") or []
            )
            positive_name_by_gate = {
                "polynomial_relative_residual_le_1e-10": "right_residual",
                "left_polynomial_relative_residual_le_1e-8": "left_residual",
                "biorthogonality_identity_error_le_1e-6": "biorthogonality",
                "left_right_beta_pair_relative_error_le_1e-7": (
                    "left_right_beta_pair_relative_error_le_1e-7"
                ),
            }
            expected_positive_failures = {
                "measured_shard_status",
                "measured_pde_solver_identity",
                "reported_all_required_numerical_gates_pass",
                *(
                    positive_name_by_gate[name]
                    for name in controlled_gate_failures
                    if name in positive_name_by_gate
                ),
            }
            valid = bool(
                key[1] == 4
                and result.get("pass") is False
                and positive.get("pass") is False
                and controlled.get("pass") is True
                and controlled_failures == []
                and set(controlled_checks) == QEP_CONTROLLED_CHECK_NAMES
                and all(value is True for value in controlled_checks.values())
                and controlled_gate_failures
                and controlled_gate_failures
                <= CONTROLLED_P4_NUMERICAL_GATE_FAILURES
                and set(positive_failures or []) == expected_positive_failures
                and set(positive_checks) == QEP_SHARD_CHECK_NAMES
                and all(
                    type(value) is bool
                    and value is (name not in expected_positive_failures)
                    for name, value in positive_checks.items()
                )
            )
            controlled_keys.add(key)
        else:
            valid = False
        if not valid:
            failures.append(f"invalid_shard_gate:{rendered}")
    return {
        "pass": not failures,
        "failures": failures,
        "controlled_keys": controlled_keys,
    }


def _aggregate_trend_structure(
    payload: Mapping[str, Any], *, required_degrees: Sequence[int]
) -> bool:
    analytic = payload.get("analytic_beta_trends")
    relative = payload.get("relative_to_p2")
    patterned = payload.get("patterned_cross_h_tracking")
    if not all(isinstance(value, Mapping) for value in (analytic, relative, patterned)):
        return False
    for material in ANALYTIC_MATERIALS:
        material_rows = analytic.get(material)
        relative_rows = relative.get(material)
        if not isinstance(material_rows, Mapping) or not isinstance(relative_rows, list):
            return False
        if len(relative_rows) != len(TREND_H_NM):
            return False
        for degree in TREND_DEGREES:
            row = material_rows.get(f"p{degree}")
            if (
                not isinstance(row, Mapping)
                or row.get("h_nm") != list(TREND_H_NM)
                or not isinstance(row.get("relative_errors"), list)
                or len(row["relative_errors"]) != len(TREND_H_NM)
            ):
                return False
            if degree in required_degrees and row.get("h_refinement_trend_pass") is not True:
                return False
        for index, h_nm in enumerate(TREND_H_NM):
            row = relative_rows[index]
            if not isinstance(row, Mapping) or row.get("h_nm") != h_nm:
                return False
            for degree in TREND_DEGREES:
                if f"p{degree}_error_over_p2" not in row:
                    return False
        finest = relative_rows[-1]
        for degree in (3, 4):
            if degree in required_degrees:
                value = _finite_number(finest.get(f"p{degree}_error_over_p2"))
                if value is None or value > 1.0:
                    return False
    for degree in TREND_DEGREES:
        rows = patterned.get(f"p{degree}")
        if not isinstance(rows, list) or len(rows) != len(TREND_H_NM) - 1:
            return False
        if degree in required_degrees and any(
            not isinstance(row, Mapping) or row.get("pass") is not True
            for row in rows
        ):
            return False
    return True


def _aggregate_source_record_closure(
    payload: Mapping[str, Any], *, controlled_keys: set[tuple[str, int, float, int]]
) -> dict[str, Any]:
    records = payload.get("source_records")
    records = records if isinstance(records, list) else []
    expected = _expected_aggregate_keys(1)
    observed: dict[tuple[str, int, float, int], Mapping[str, Any]] = {}
    valid = len(records) == 36
    for row in records:
        if not isinstance(row, Mapping):
            valid = False
            continue
        candidate = row.get("candidate")
        candidate = candidate if isinstance(candidate, Mapping) else {}
        key = _strict_candidate_key(candidate)
        if key is None:
            valid = False
            continue
        solver = row.get("solver_record")
        solver = solver if isinstance(solver, Mapping) else {}
        disposition = row.get("disposition")
        valid &= bool(
            key in expected
            and key not in observed
            and isinstance(row.get("path"), str)
            and row.get("path")
            and isinstance(row.get("sha256"), str)
            and SHA256.fullmatch(row["sha256"].lower())
            and isinstance(solver.get("path"), str)
            and solver.get("path")
            and isinstance(solver.get("sha256"), str)
            and SHA256.fullmatch(solver["sha256"].lower())
            and disposition
            == ("controlled_numeric_negative" if key in controlled_keys else "pass")
        )
        observed[key] = row
    return {"pass": valid and set(observed) == expected, "by_key": observed}


def qep_source_record_file_gate(
    payload: Mapping[str, Any], *, root: Path | str
) -> dict[str, Any]:
    """Reopen and hash every watchdog and solver record under one root."""

    resolved_root = Path(root).resolve()
    formal_source = payload.get("formal_source")
    formal_source = formal_source if isinstance(formal_source, Mapping) else {}
    expected_source_sha = formal_source.get("commit_sha")
    expected_source_sha = (
        str(expected_source_sha).lower()
        if _full_sha(expected_source_sha)
        and formal_source.get("tracked_source_clean") is True
        else None
    )

    def resolve(raw: object) -> Path | None:
        if not isinstance(raw, str) or not raw:
            return None
        normalized = raw.replace("\\", "/")
        requested = (
            resolved_root / normalized[len("/work/") :]
            if normalized.startswith("/work/")
            else Path(raw)
        )
        candidate = (
            requested.resolve()
            if requested.is_absolute()
            else (resolved_root / requested).resolve()
        )
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            return None
        return candidate

    def digest(path: Path) -> str:
        value = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(chunk)
        return value.hexdigest()

    records = payload.get("source_records")
    records = records if isinstance(records, list) else []
    failures: list[str] = []
    observed_source_shas: set[str] = set()
    if expected_source_sha is None:
        failures.append("formal_source:missing_or_not_clean_full_sha")
    for index, row in enumerate(records):
        if not isinstance(row, Mapping):
            failures.append(f"source_record_{index}:not_mapping")
            continue
        watchdog_path = resolve(row.get("path"))
        solver = row.get("solver_record")
        solver = solver if isinstance(solver, Mapping) else {}
        solver_path = resolve(solver.get("path"))
        if (
            watchdog_path is None
            or solver_path is None
            or not watchdog_path.is_file()
            or not solver_path.is_file()
        ):
            failures.append(f"source_record_{index}:missing_or_outside_root")
            continue
        watchdog_sha = digest(watchdog_path)
        solver_sha = digest(solver_path)
        if watchdog_sha != str(row.get("sha256", "")).lower():
            failures.append(f"source_record_{index}:watchdog_sha256")
            continue
        if solver_sha != str(solver.get("sha256", "")).lower():
            failures.append(f"source_record_{index}:solver_sha256")
            continue
        try:
            watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
            solver_payload = json.loads(solver_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            failures.append(f"source_record_{index}:invalid_json")
            continue
        watchdog = watchdog if isinstance(watchdog, Mapping) else {}
        solver_payload = (
            solver_payload if isinstance(solver_payload, Mapping) else {}
        )
        embedded = watchdog.get("measurements")
        candidate = row.get("candidate")
        disposition = row.get("disposition")
        embedded_status = (
            embedded.get("status") if isinstance(embedded, Mapping) else None
        )
        solver_provenance = solver_payload.get("provenance")
        solver_provenance = (
            solver_provenance
            if isinstance(solver_provenance, Mapping)
            else {}
        )
        solver_source_gate = source_identity_gate(solver_provenance)
        watchdog_source = watchdog.get("source")
        watchdog_source = (
            watchdog_source if isinstance(watchdog_source, Mapping) else {}
        )
        watchdog_source_gate = source_identity_gate(watchdog_source)
        reported_watchdog_source_gate = watchdog.get("source_gate")
        reported_watchdog_source_gate = (
            reported_watchdog_source_gate
            if isinstance(reported_watchdog_source_gate, Mapping)
            else {}
        )
        solver_source_sha = solver_source_gate.get("head_sha")
        watchdog_source_sha = watchdog_source_gate.get("head_sha")
        source_binding = bool(
            expected_source_sha is not None
            and solver_source_gate.get("pass") is True
            and watchdog_source_gate.get("pass") is True
            and reported_watchdog_source_gate == watchdog_source_gate
            and solver_source_sha == watchdog_source_sha == expected_source_sha
            and watchdog.get("worker_source") == solver_provenance
        )
        if source_binding:
            observed_source_shas.add(str(solver_source_sha))
        common = bool(
            watchdog.get("schema_version") == "task033.memory-watchdog.v2"
            and watchdog.get("benchmark_id") == "task033_external_memory_watchdog"
            and watchdog.get("target") == "qep"
            and watchdog.get("memory_authority_pass") is True
            and watchdog.get("no_swap") is True
            and watchdog.get("terminated_for_memory") is False
            and watchdog.get("terminated_for_timeout") is False
            and watchdog.get("terminated_for_authority_unreadable") is False
            and isinstance(watchdog.get("resource_authority"), Mapping)
            and isinstance(watchdog["resource_authority"].get("gate"), Mapping)
            and watchdog["resource_authority"]["gate"].get("pass") is True
            and source_binding
            and isinstance(watchdog.get("launch_gate"), Mapping)
            and watchdog["launch_gate"].get("pass") is True
            and watchdog.get("solver_record_sha256") == solver_sha
            and resolve(watchdog.get("solver_record_ignored_path")) == solver_path
            and embedded == solver_payload
            and isinstance(embedded, Mapping)
            and embedded.get("candidate") == candidate
        )
        positive_gate = qep_shard_gate(solver_payload)
        controlled_gate = (
            qep_p4_controlled_negative_gate(
                solver_payload,
                mpi_size=int(candidate.get("mpi_size", 1)),
            )
            if isinstance(candidate, Mapping)
            and type(candidate.get("mpi_size")) is int
            else {"pass": False}
        )
        if disposition == "pass":
            outcome = bool(
                watchdog.get("status") == "measured_shard_pass"
                and watchdog.get("formal_pass") is True
                and watchdog.get("numeric_pass") is True
                and watchdog.get("return_code") == 0
                and embedded_status == "measured_shard_pass"
                and positive_gate.get("pass") is True
            )
        else:
            outcome = bool(
                disposition == "controlled_numeric_negative"
                and watchdog.get("status") == "formal_not_pass"
                and watchdog.get("formal_pass") is False
                and watchdog.get("numeric_pass") is False
                and watchdog.get("return_code") == 2
                and embedded_status == "measured_shard_failed"
                and controlled_gate.get("pass") is True
            )
        if not common or not outcome:
            failures.append(f"source_record_{index}:semantic_binding")
    if (
        expected_source_sha is None
        or observed_source_shas != {expected_source_sha}
    ):
        failures.append("source_sha_closure")
    return {
        "pass": len(records) == 36 and not failures,
        "checked_record_count": len(records),
        "failures": failures,
    }


def qep_full_aggregate_gate(
    payload: Mapping[str, Any], *, require_evidence_descriptors: bool = False
) -> dict[str, Any]:
    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    degree = payload.get("degree_qualification")
    degree = degree if isinstance(degree, Mapping) else {}
    gates = payload.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    shard_closure = _aggregate_shard_closure(
        payload, allow_controlled_p4=False
    )
    source_closure = _aggregate_source_record_closure(
        payload, controlled_keys=set()
    ) if require_evidence_descriptors else {"pass": True}
    checks = {
        "qualified_identity": (
            payload.get("status") == "qep_component_aggregate_qualified"
            and payload.get("qualification_classification") == "full_p1_p4_qualified"
            and identity.get("is_qep_component_qualified") is True
            and identity.get("is_qep_p3_only_partial") is False
            and identity.get("is_physical_qualification_record") is False
        ),
        "complete_unique_36": (
            payload.get("required_shard_count") == 36
            and payload.get("received_unique_shard_count") == 36
            and payload.get("duplicate_count") == 0
            and payload.get("unexpected_record_count") == 0
            and payload.get("missing_candidates") == []
            and payload.get("p1_p2_p3_passed_shard_count") == 27
            and payload.get("p4_completed_shard_count") == 9
        ),
        "no_negative_observations": (
            payload.get("negative_observation_count") == 0
            and payload.get("negative_observations") == []
        ),
        "four_degrees_qualified": all(
            isinstance(degree.get(f"p{value}"), Mapping)
            and degree[f"p{value}"].get("status") == "qualified"
            and degree[f"p{value}"].get("required_shard_count") == 9
            and degree[f"p{value}"].get("passed_shard_count") == 9
            and degree[f"p{value}"].get("controlled_negative_shard_count") == 0
            for value in TREND_DEGREES
        ),
        "all_aggregate_gates_true": bool(gates) and all(
            value is True for value in gates.values()
        ),
        "shard_closure": shard_closure["pass"],
        "source_record_closure": source_closure["pass"],
        "trend_structure": _aggregate_trend_structure(
            payload, required_degrees=TREND_DEGREES
        ),
        "formal_source_if_present": (
            "formal_source" not in payload
            or (
                isinstance(payload.get("formal_source"), Mapping)
                and _full_sha(payload["formal_source"].get("commit_sha"))
                and payload["formal_source"].get("tracked_source_clean") is True
            )
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def qep_p3_only_partial_aggregate_gate(
    payload: Mapping[str, Any], *, require_evidence_descriptors: bool = False
) -> dict[str, Any]:
    """Independently recognize only the audited p4-negative partial shape."""

    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    gates = payload.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    degree = payload.get("degree_qualification")
    degree = degree if isinstance(degree, Mapping) else {}
    observations = payload.get("negative_observations")
    observations = observations if isinstance(observations, list) else []
    shard_gates = payload.get("shard_gates")
    shard_gates = shard_gates if isinstance(shard_gates, Mapping) else {}

    observation_keys: set[tuple[str, int, float, int]] = set()
    observations_valid = bool(observations)
    for row in observations:
        if not isinstance(row, Mapping):
            observations_valid = False
            continue
        candidate = row.get("candidate")
        candidate = candidate if isinstance(candidate, Mapping) else {}
        key = _strict_candidate_key(candidate)
        if key is None:
            observations_valid = False
            continue
        failures = row.get("controlled_failure_gates")
        failures = failures if isinstance(failures, list) else []
        evidence = row.get("evidence")
        evidence = evidence if isinstance(evidence, Mapping) else {}
        evidence_valid = True
        if require_evidence_descriptors:
            watchdog = evidence.get("watchdog_summary")
            solver = evidence.get("solver_record")
            watchdog = watchdog if isinstance(watchdog, Mapping) else {}
            solver = solver if isinstance(solver, Mapping) else {}
            evidence_valid = bool(
                isinstance(watchdog.get("path"), str)
                and watchdog.get("path")
                and isinstance(watchdog.get("sha256"), str)
                and SHA256.fullmatch(watchdog["sha256"].lower())
                and isinstance(solver.get("path"), str)
                and solver.get("path")
                and isinstance(solver.get("sha256"), str)
                and SHA256.fullmatch(solver["sha256"].lower())
                and evidence.get("watchdog_return_code") == 2
            )
        row_valid = bool(
            key[0] in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
            and key[1] == 4
            and key[2] in TREND_H_NM
            and key[3] == payload.get("mpi_size") == 1
            and row.get("status") == "measured_shard_failed"
            and row.get("disposition") == "controlled_numeric_negative"
            and row.get("is_qep_component_qualified") is False
            and failures
            and len(failures) == len(set(failures))
            and set(failures) <= CONTROLLED_P4_NUMERICAL_GATE_FAILURES
            and evidence_valid
        )
        observations_valid &= row_valid and key not in observation_keys
        observation_keys.add(key)

    lower_degree_valid = all(
        isinstance(degree.get(f"p{value}"), Mapping)
        and degree[f"p{value}"].get("status") == "qualified"
        and degree[f"p{value}"].get("required_shard_count") == 9
        and degree[f"p{value}"].get("passed_shard_count") == 9
        and degree[f"p{value}"].get("controlled_negative_shard_count") == 0
        for value in (1, 2, 3)
    )
    p4 = degree.get("p4")
    p4 = p4 if isinstance(p4, Mapping) else {}
    p4_valid = bool(
        p4.get("status") == "controlled_numeric_negative"
        and p4.get("required_shard_count") == 9
        and type(p4.get("passed_shard_count")) is int
        and type(p4.get("controlled_negative_shard_count")) is int
        and p4["controlled_negative_shard_count"] == len(observations)
        and p4["controlled_negative_shard_count"] >= 1
        and p4["passed_shard_count"] + p4["controlled_negative_shard_count"]
        == 9
    )
    expected_shard_keys = {
        "|".join(map(str, key)) for key in {
            (material, degree_value, h_nm, 1)
            for material in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
            for degree_value in TREND_DEGREES
            for h_nm in TREND_H_NM
        }
    }
    shard_gate_consistency = set(shard_gates) == expected_shard_keys
    controlled_shard_keys: set[tuple[str, int, float, int]] = set()
    if shard_gate_consistency:
        for rendered_key, raw_result in shard_gates.items():
            result = raw_result if isinstance(raw_result, Mapping) else {}
            tokens = rendered_key.split("|")
            try:
                key = (tokens[0], int(tokens[1]), float(tokens[2]), int(tokens[3]))
            except (IndexError, TypeError, ValueError):
                shard_gate_consistency = False
                continue
            positive = result.get("positive_gate")
            positive = positive if isinstance(positive, Mapping) else {}
            controlled = result.get("controlled_negative_gate")
            controlled = controlled if isinstance(controlled, Mapping) else {}
            positive_checks = positive.get("checks")
            positive_checks = (
                positive_checks if isinstance(positive_checks, Mapping) else {}
            )
            positive_failures = positive.get("failures")
            positive_failures = (
                positive_failures if isinstance(positive_failures, list) else []
            )
            controlled_checks = controlled.get("checks")
            controlled_checks = (
                controlled_checks
                if isinstance(controlled_checks, Mapping)
                else {}
            )
            controlled_failures = controlled.get("failures")
            controlled_failures = (
                controlled_failures
                if isinstance(controlled_failures, list)
                else []
            )
            disposition = result.get("disposition")
            if key[1] <= 3:
                valid = (
                    disposition == "pass"
                    and result.get("pass") is True
                    and positive.get("pass") is True
                    and positive_failures == []
                    and bool(positive_checks)
                    and all(value is True for value in positive_checks.values())
                )
            elif disposition == "pass":
                valid = bool(
                    result.get("pass") is True
                    and positive.get("pass") is True
                    and positive_failures == []
                    and positive_checks
                    and all(value is True for value in positive_checks.values())
                )
            elif disposition == "controlled_numeric_negative":
                controlled_gate_failures = set(
                    controlled.get("controlled_failure_gates") or []
                )
                positive_name_by_gate = {
                    "polynomial_relative_residual_le_1e-10": "right_residual",
                    "left_polynomial_relative_residual_le_1e-8": "left_residual",
                    "biorthogonality_identity_error_le_1e-6": "biorthogonality",
                    "left_right_beta_pair_relative_error_le_1e-7": (
                        "left_right_beta_pair_relative_error_le_1e-7"
                    ),
                }
                expected_positive_failures = {
                    "measured_shard_status",
                    "measured_pde_solver_identity",
                    "reported_all_required_numerical_gates_pass",
                    *(
                        positive_name_by_gate[name]
                        for name in controlled_gate_failures
                        if name in positive_name_by_gate
                    ),
                }
                valid = bool(
                    result.get("pass") is False
                    and positive.get("pass") is False
                    and controlled.get("pass") is True
                    and controlled_failures == []
                    and set(controlled_checks)
                    == QEP_CONTROLLED_CHECK_NAMES
                    and all(value is True for value in controlled_checks.values())
                    and controlled_gate_failures
                    and controlled_gate_failures
                    <= CONTROLLED_P4_NUMERICAL_GATE_FAILURES
                    and set(positive_failures) == expected_positive_failures
                    and set(positive_checks) == QEP_SHARD_CHECK_NAMES
                    and all(
                        value is (name not in expected_positive_failures)
                        for name, value in positive_checks.items()
                    )
                )
                controlled_shard_keys.add(key)
            else:
                valid = False
            shard_gate_consistency &= valid
    shard_gate_consistency &= controlled_shard_keys == observation_keys
    shared_shard_closure = _aggregate_shard_closure(
        payload, allow_controlled_p4=True
    )
    source_closure = (
        _aggregate_source_record_closure(
            payload, controlled_keys=observation_keys
        )
        if require_evidence_descriptors
        else {"pass": True, "by_key": {}}
    )
    observation_source_correspondence = True
    if require_evidence_descriptors:
        source_by_key = source_closure.get("by_key")
        source_by_key = source_by_key if isinstance(source_by_key, Mapping) else {}
        for row in observations:
            candidate = row.get("candidate") if isinstance(row, Mapping) else None
            candidate = candidate if isinstance(candidate, Mapping) else {}
            key = _strict_candidate_key(candidate)
            if key is None:
                observation_source_correspondence = False
                continue
            source_row = source_by_key.get(key)
            source_row = source_row if isinstance(source_row, Mapping) else {}
            evidence = row.get("evidence")
            evidence = evidence if isinstance(evidence, Mapping) else {}
            observation_source_correspondence &= bool(
                source_row.get("disposition") == "controlled_numeric_negative"
                and evidence.get("watchdog_summary")
                == {
                    "path": source_row.get("path"),
                    "sha256": source_row.get("sha256"),
                }
                and evidence.get("solver_record")
                == source_row.get("solver_record")
                and evidence.get("watchdog_return_code") == 2
            )
    required_partial_gates = (
        "complete_unique_required_shards",
        "p1_p2_p3_27_shards_pass",
        "p4_9_shards_complete_pass_or_controlled_numeric_negative",
        "p1_p2_p3_analytic_trends_and_p2_relative_pass",
        "p1_p2_p3_patterned_cross_h_tracking_pass",
    )
    checks = {
        "partial_status": (
            payload.get("status") == "qep_component_aggregate_not_qualified"
            and payload.get("qualification_classification")
            == P3_ONLY_PARTIAL_CLASSIFICATION
        ),
        "not_promoted_to_qualified": (
            identity.get("is_qep_component_qualified") is False
            and identity.get("is_qep_p3_only_partial") is True
            and identity.get("is_physical_qualification_record") is False
        ),
        "complete_unique_36": (
            payload.get("required_shard_count") == 36
            and payload.get("received_unique_shard_count") == 36
            and payload.get("duplicate_count") == 0
            and payload.get("unexpected_record_count") == 0
            and payload.get("missing_candidates") == []
            and len(shard_gates) == 36
        ),
        "lower_27_pass": payload.get("p1_p2_p3_passed_shard_count") == 27,
        "all_p4_completed": payload.get("p4_completed_shard_count") == 9,
        "negative_observation_count": (
            payload.get("negative_observation_count") == len(observations)
            and bool(observations)
        ),
        "negative_observations_narrow": observations_valid,
        "shard_gate_dispositions_consistent": shard_gate_consistency,
        "shared_shard_closure": (
            shared_shard_closure.get("pass") is True
            and shared_shard_closure.get("controlled_keys") == observation_keys
        ),
        "source_record_closure": source_closure.get("pass") is True,
        "negative_source_correspondence": observation_source_correspondence,
        "lower_trend_structure": _aggregate_trend_structure(
            payload, required_degrees=(1, 2, 3)
        ),
        "degree_qualification": lower_degree_valid and p4_valid,
        "required_partial_gates": all(gates.get(name) is True for name in required_partial_gates),
        "not_all_shards_pass": gates.get("all_shard_contracts_pass") is False,
        "formal_source_if_present": (
            "formal_source" not in payload
            or (
                isinstance(payload.get("formal_source"), Mapping)
                and _full_sha(payload["formal_source"].get("commit_sha"))
                and payload["formal_source"].get("tracked_source_clean") is True
            )
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}
