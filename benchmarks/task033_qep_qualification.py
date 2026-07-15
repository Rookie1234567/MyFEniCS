"""Fail-closed qualification contracts for Task033 QEP shards and studies."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


FULL_SHA = re.compile(r"[0-9a-f]{40}")
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
LEFT_CANDIDATE_POOL_POLICY = "max_requested_plus_4_or_1p5x"
TRACKING_COMPACT_KIND = (
    "measured_common_fourier_left_right_mode_fingerprints"
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
    material = candidate.get("material_kind")
    analytic_error = _finite_number(numerical.get("analytic_beta_relative_error"))
    right_requested = classification.get("right_requested_modes")
    left_requested = classification.get("left_candidate_requested_modes")
    left_converged = classification.get("left_candidate_converged_modes")
    right_requested_valid = type(right_requested) is int and right_requested > 0
    left_requested_valid = type(left_requested) is int and left_requested > 0
    left_converged_valid = type(left_converged) is int and left_converged >= 0
    required_left_requested = (
        max(int(right_requested) + 4, math.ceil(1.5 * int(right_requested)))
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
    reported_pair_gate = record_gates.get(
        "left_right_beta_pair_relative_error_le_1e-7"
    )
    checks = {
        "measured_shard_status": record.get("status") == "measured_shard_pass",
        "not_physical_qualified": (
            (record.get("identity") or {}).get("is_physical_qualification_record")
            is False
        ),
        "source_identity": source_identity_gate(
            record.get("provenance")
            if isinstance(record.get("provenance"), Mapping)
            else None
        )["pass"],
        "resource_authority": resource_authority_gate(formal_resource)["pass"],
        "right_residual": bool(
            _finite_number(classification.get("right_polynomial_relative_residual_max"))
            is not None
            and float(classification["right_polynomial_relative_residual_max"])
            <= RIGHT_RESIDUAL_MAX
        ),
        "left_residual": bool(
            _finite_number(classification.get("left_polynomial_relative_residual_max"))
            is not None
            and float(classification["left_polynomial_relative_residual_max"])
            <= LEFT_RESIDUAL_MAX
        ),
        "biorthogonality": bool(
            _finite_number(classification.get("biorthogonality_identity_error"))
            is not None
            and float(classification["biorthogonality_identity_error"])
            <= BIORTHOGONALITY_MAX
        ),
        "left_candidate_pool_policy": (
            classification.get("left_candidate_pool_policy")
            == LEFT_CANDIDATE_POOL_POLICY
        ),
        "right_requested_modes": right_requested_valid,
        "left_candidate_requested_modes": bool(
            left_requested_valid
            and required_left_requested is not None
            and int(left_requested) >= int(right_requested) + 4
            and int(left_requested) >= math.ceil(1.5 * int(right_requested))
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
            and _finite_number(raised.get("max_matrix_relative_difference"))
            is not None
            and float(raised["max_matrix_relative_difference"])
            <= RAISED_QUADRATURE_MATRIX_DELTA_MAX
        ),
        "analytic_beta_identity": (
            analytic_error is not None
            if material in ANALYTIC_MATERIALS
            else analytic_error is None
        ),
        "patterned_tracking_compact_input": (
            _tracking_compact(record) is not None
            if material == PATTERNED_MATERIAL
            else True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _candidate_key(record: Mapping[str, Any]) -> tuple[str, int, float, int] | None:
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping):
        return None
    try:
        return (
            str(candidate["material_kind"]),
            int(candidate["degree"]),
            float(candidate["h_nm"]),
            int(candidate["mpi_size"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _nonincreasing(values: Sequence[float], *, slack: float = 0.05) -> bool:
    return all(
        later <= earlier * (1.0 + slack) + 1.0e-15
        for earlier, later in zip(values, values[1:], strict=False)
    ) and values[-1] < values[0]


def aggregate_qep_shards(
    records: Sequence[Mapping[str, Any]], *, mpi_size: int = 1
) -> dict[str, Any]:
    """Aggregate h/p QEP evidence; missing trends or tracking fail closed."""

    by_key = {
        key: record
        for record in records
        if (key := _candidate_key(record)) is not None and key[3] == mpi_size
    }
    duplicate_count = len(records) - len({_candidate_key(record) for record in records})
    required_keys = {
        (material, degree, h_nm, mpi_size)
        for material in (*ANALYTIC_MATERIALS, PATTERNED_MATERIAL)
        for degree in TREND_DEGREES
        for h_nm in TREND_H_NM
    }
    missing = sorted(required_keys - set(by_key))
    shard_results = {
        "|".join(map(str, key)): qep_shard_gate(record)
        for key, record in sorted(by_key.items())
        if key in required_keys
    }
    all_shards_pass = bool(
        not missing
        and duplicate_count == 0
        and len(shard_results) == len(required_keys)
        and all(result["pass"] for result in shard_results.values())
    )

    analytic_trends: dict[str, Any] = {}
    analytic_trends_pass = True
    p2_relative: dict[str, Any] = {}
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
            analytic_trends_pass &= passed
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
        analytic_trends_pass &= bool(
            finest["p3_error_over_p2"] is not None
            and finest["p4_error_over_p2"] is not None
            and float(finest["p3_error_over_p2"]) <= 1.0
            and float(finest["p4_error_over_p2"]) <= 1.0
        )

    patterned_tracking: dict[str, Any] = {}
    patterned_pass = True
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
            patterned_pass &= tracking["pass"] is True
            rows.append(tracking)
        patterned_tracking[f"p{degree}"] = rows

    gates = {
        "complete_unique_required_shards": not missing and duplicate_count == 0,
        "all_shard_contracts_pass": all_shards_pass,
        "air_lossy_h_p_trends_and_p2_relative_pass": analytic_trends_pass,
        "patterned_residual_biorth_and_cross_h_tracking_pass": (
            patterned_pass and all_shards_pass
        ),
    }
    qualified = all(gates.values())
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
            "is_physical_qualification_record": False,
            "proves_0p7nm_feasible": False,
        },
        "mpi_size": mpi_size,
        "required_shard_count": len(required_keys),
        "received_unique_shard_count": len(set(by_key) & required_keys),
        "duplicate_count": duplicate_count,
        "missing_candidates": [list(value) for value in missing],
        "shard_gates": shard_results,
        "analytic_beta_trends": analytic_trends,
        "relative_to_p2": p2_relative,
        "patterned_cross_h_tracking": patterned_tracking,
        "gates": gates,
    }
