"""Independent admission checker for the Review V17 p4 BLR sequence.

The worker's status and gate booleans are not evidence. ``check_run`` reads
saved arrays, raw MUMPS fields, control readbacks, map identities and the same
parent resource scopes used by the V16 checker, then passes only recomputed
facts to the small pure policy functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.check_p4_blr_v16 import (
    STEMS,
    _array,
    _hash,
    _json,
    resource_scope,
)


RHO_LIMIT = 0.5
FIELD_LIMIT = 0.25
PEAK_LIMIT = 0.90
LIVE_LIMIT = 0.80
PEAK_WITH_LIVE_LIMIT = 1.05
IDENTITY_LIMIT = 1.0e-10
TRADEOFF_THRESHOLDS = {
    "T1_BLR_CONTROL": 1.0e-3,
    "T2_BLR_CONTROL": 1.0e-4,
}
MATRIX_KEYS = (
    "fe_rows",
    "port_rows",
    "augmented_rows",
    "allocated_nnz",
    "preallocated_nnz",
)
MAP_KEYS = (
    "dofmap",
    "geometry",
    "geometry_dofmap",
    "permutations",
    "slaves",
    "masters",
    "coefficients",
    "offsets",
    "independent_indices",
)
MUMPS_FIXED_ICNTL = {
    2: 0,
    3: 6,
    4: 2,
    10: 0,
    22: 0,
    31: 0,
    32: 0,
    35: 2,
    37: 0,
}
BASELINE_ICNTL = {
    # These are the post-symbolic values recorded by the accepted V16
    # factor.  The BLR opt-in may change only the explicitly reviewed
    # controls above; ordering, scaling, pivoting and the contribution-block
    # controls remain the same.
    6: 7,
    7: 7,
    8: 77,
    14: 20,
    18: 0,
    28: 1,
    29: 0,
    36: 0,
    38: 600,
}
BASELINE_CNTL = {1: 0.01, 3: 0.0, 4: -1.0}
STDOUT_COVERAGE_MAX_BYTES = 16 * 1024 * 1024


def _finite(*values: Any) -> bool:
    try:
        return all(math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float:
    if isinstance(value, Mapping):
        value = value.get("value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite numeric evidence: {value!r}")
    return result


def _array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _records(summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = summary.get("solve_records")
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, Mapping)]


def _quality_from_raw(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "three_rhs": len(rows) == 3,
        "finite": True,
        "residual_identity": True,
        "rho": True,
        "field_l2": True,
        "scaled_curl": True,
    }
    failures: list[str] = []
    for index, row in enumerate(rows):
        values = {
            "rho": row.get("rho"),
            "field_l2": row.get("field_l2_relative"),
            "scaled_curl": row.get("scaled_curl_relative"),
            "identity": row.get("native_identity_relative"),
        }
        if not all(_finite(value) for value in values.values()):
            checks["finite"] = False
            failures.append(f"rhs[{index}].nonfinite")
            continue
        if float(values["identity"]) > IDENTITY_LIMIT:
            checks["residual_identity"] = False
            failures.append(f"rhs[{index}].residual_identity")
        if float(values["rho"]) > RHO_LIMIT:
            checks["rho"] = False
            failures.append(f"rhs[{index}].rho")
        if float(values["field_l2"]) > FIELD_LIMIT:
            checks["field_l2"] = False
            failures.append(f"rhs[{index}].field_l2")
        if float(values["scaled_curl"]) > FIELD_LIMIT:
            checks["scaled_curl"] = False
            failures.append(f"rhs[{index}].scaled_curl")
    correctness = bool(
        checks["three_rhs"]
        and checks["finite"]
        and checks["residual_identity"]
    )
    quality = bool(
        correctness
        and checks["rho"]
        and checks["field_l2"]
        and checks["scaled_curl"]
    )
    return {
        "correctness_pass": correctness,
        "quality_pass": quality,
        "checks": checks,
        "quality_failures": failures,
        "rho_limit": RHO_LIMIT,
        "field_limit": FIELD_LIMIT,
        "identity_limit": IDENTITY_LIMIT,
    }


def quality_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate Q only from the raw, independently recomputed RHS facts."""

    return _quality_from_raw(_records(summary))


def memory_facts(*, peak_ratio: Any, live_ratio: Any) -> dict[str, Any]:
    """Evaluate the fixed M gate from measured same-scope ratios."""

    peak_ok = _finite(peak_ratio) and float(peak_ratio) <= PEAK_LIMIT
    live_ok = _finite(live_ratio) and float(live_ratio) <= LIVE_LIMIT
    peak_with_live_ok = (
        _finite(peak_ratio) and float(peak_ratio) <= PEAK_WITH_LIVE_LIMIT
    )
    passed = bool(peak_ok or (live_ok and peak_with_live_ok))
    return {
        "peak_ratio": float(peak_ratio) if _finite(peak_ratio) else None,
        "live_ratio": float(live_ratio) if _finite(live_ratio) else None,
        "peak_gate": peak_ok,
        "live_gate": live_ok,
        "peak_with_live_gate": peak_with_live_ok,
        "memory_pass": passed,
    }


def _decoded_infog(value: Any) -> tuple[float | None, str | None]:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(raw):
        return None, None
    if raw < 0.0:
        return -raw * 1_000_000.0, "negative_million_entry_encoding"
    return raw, "native_entry_encoding"


def _raw_compression_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    factor = summary.get("factor")
    raw = factor.get("numeric_raw") if isinstance(factor, Mapping) else None
    infog = raw.get("infog") if isinstance(raw, Mapping) else None
    rinfog = raw.get("rinfog") if isinstance(raw, Mapping) else None
    infog = infog if isinstance(infog, Mapping) else {}
    rinfog = rinfog if isinstance(rinfog, Mapping) else {}
    entries: dict[str, float] = {}
    encodings: dict[str, str | None] = {}
    for key in ("9", "29", "35"):
        value, encoding = _decoded_infog(infog.get(key))
        if value is not None:
            entries[key] = value
        encodings[key] = encoding
    flops: dict[str, float] = {}
    for key in ("3", "14"):
        if _finite(rinfog.get(key)):
            flops[key] = float(rinfog[key])
    actual = entries.get("9")
    theoretical = entries.get("29")
    effective = entries.get("35")
    passed = bool(
        actual is not None
        and theoretical is not None
        and effective is not None
        and actual > 0.0
        and theoretical > 0.0
        and effective > 0.0
        and actual < theoretical
        and effective < theoretical
        and len(flops) == 2
        and all(value > 0.0 for value in flops.values())
    )
    return {
        "actual_storage_entries": actual,
        "theoretical_entries": theoretical,
        "effective_storage_entries": effective,
        "native_flops": flops,
        "infog_encoding": encodings,
        "raw_infog": dict(infog),
        "raw_rinfog": dict(rinfog),
        "actual_compression_present": passed,
        "ratio": actual / theoretical if passed and theoretical else None,
    }


def compression_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Require actual measured BLR entries from raw native MUMPS fields."""

    return _raw_compression_facts(summary)


def _matrix_content_hash_facts(
    summary: Mapping[str, Any], baseline: Mapping[str, Any]
) -> dict[str, Any]:
    """Report serialized global-matrix content identity separately.

    The p4 records currently retain dimensions/NNZ and operator-action
    diagnostics, but do not retain a byte hash of the global CSR numerical
    values.  Do not infer such a hash from dimensions, NNZ, input identity,
    or source/map hashes.
    """

    current_matrix = summary.get("matrix")
    baseline_matrix = baseline.get("matrix")
    current_matrix = current_matrix if isinstance(current_matrix, Mapping) else {}
    baseline_matrix = baseline_matrix if isinstance(baseline_matrix, Mapping) else {}
    current_hash = current_matrix.get("matrix_content_sha256")
    baseline_hash = baseline_matrix.get("matrix_content_sha256")
    current_hash = current_hash if isinstance(current_hash, str) and current_hash else None
    baseline_hash = (
        baseline_hash if isinstance(baseline_hash, str) and baseline_hash else None
    )
    return {
        "available": current_hash is not None,
        "current_available": current_hash is not None,
        "baseline_available": baseline_hash is not None,
        "comparable": current_hash is not None and baseline_hash is not None,
        "match": (
            current_hash == baseline_hash
            if current_hash is not None and baseline_hash is not None
            else None
        ),
        "field": "matrix.matrix_content_sha256",
        "current_sha256": current_hash,
        "baseline_sha256": baseline_hash,
    }


def decide_t1(
    summary: Mapping[str, Any],
    *,
    resource_evidence_complete: bool,
    peak_ratio: Any,
    live_ratio: Any,
) -> dict[str, Any]:
    """Return the only allowed next action after T1."""

    quality = quality_facts(summary)
    memory = memory_facts(peak_ratio=peak_ratio, live_ratio=live_ratio)
    compression = compression_facts(summary)
    if not quality["correctness_pass"] or not resource_evidence_complete:
        action = "T5_CLOSE"
        reason = "correctness_or_resource_evidence_failed"
    elif not memory["memory_pass"]:
        action = "T5_CLOSE"
        reason = "M_gate_failed"
    elif not compression["actual_compression_present"]:
        action = "T5_CLOSE"
        reason = "actual_compression_not_measured"
    elif quality["quality_pass"]:
        action = "SELECT_T1"
        reason = "T1_Q_and_M_pass"
    else:
        action = "RUN_T2"
        reason = "T1_M_pass_but_only_Q_quality_failed"
    return {
        "action": action,
        "reason": reason,
        "quality": quality,
        "memory": memory,
        "compression": compression,
        "resource_evidence_complete": bool(resource_evidence_complete),
        "next_threshold": 1.0e-4 if action == "RUN_T2" else None,
    }


def decide_t2(
    summary: Mapping[str, Any],
    *,
    resource_evidence_complete: bool,
    peak_ratio: Any,
    live_ratio: Any,
) -> dict[str, Any]:
    """Apply the same fixed gates to T2 without reopening threshold search."""

    quality = quality_facts(summary)
    memory = memory_facts(peak_ratio=peak_ratio, live_ratio=live_ratio)
    compression = compression_facts(summary)
    passed = bool(
        quality["correctness_pass"]
        and quality["quality_pass"]
        and memory["memory_pass"]
        and compression["actual_compression_present"]
        and resource_evidence_complete
    )
    return {
        "action": "SELECT_T2" if passed else "T5_CLOSE",
        "reason": "T2_Q_and_M_pass" if passed else "T2_gate_failed",
        "quality": quality,
        "memory": memory,
        "compression": compression,
        "resource_evidence_complete": bool(resource_evidence_complete),
    }


def _resolve(root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _control_value(container: Any, kind: str, index: int) -> Any:
    if not isinstance(container, Mapping):
        return None
    table = container.get(kind)
    if not isinstance(table, Mapping):
        table = container
    item = table.get(str(index))
    if isinstance(item, Mapping):
        return item.get("value")
    return item


def _close(value: Any, expected: float | int) -> bool:
    return _finite(value) and math.isclose(
        float(value), float(expected), rel_tol=0.0, abs_tol=1.0e-12
    )


def _exact_icntl_settings(exact_factor: Mapping[str, Any], name: str) -> dict[int, Any]:
    settings = exact_factor.get(name)
    if not isinstance(settings, Mapping):
        return {}
    table = settings.get("icntl")
    if not isinstance(table, Mapping):
        return {}
    return {
        int(key): value.get("value") if isinstance(value, Mapping) else value
        for key, value in table.items()
        if str(key).isdigit()
    }


def _control_facts(
    summary: Mapping[str, Any],
    threshold: float,
    exact_factor: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    factor = summary.get("factor")
    controls = factor.get("backend_control_facts") if isinstance(factor, Mapping) else None
    controls = controls if isinstance(controls, Mapping) else {}
    requested = controls.get("requested")
    requested = requested if isinstance(requested, Mapping) else {}
    requested_icntl = requested.get("icntl")
    requested_icntl = requested_icntl if isinstance(requested_icntl, Mapping) else {}
    requested_cntl = requested.get("cntl")
    requested_cntl = requested_cntl if isinstance(requested_cntl, Mapping) else {}
    factor_setup_zero = (
        factor.get("factor_solve_calls_at_factorization") == 0
        if isinstance(factor, Mapping)
        else False
    )
    gates: dict[str, bool] = {
        "profile": controls.get("profile") == "physical_p4_blr_tradeoff_v17",
        "threshold": _close(controls.get("threshold"), threshold),
        "coverage_requested": controls.get("coverage_statistics_requested") is True,
        "configured_before_symbolic": controls.get("configured_before_symbolic") is True,
        "public_initial_state_pre_symbolic": controls.get("public_initial_state_is_pre_symbolic") is True,
        "requested_icntl": all(
            _close(requested_icntl.get(str(index)), value)
            for index, value in MUMPS_FIXED_ICNTL.items()
        ),
        "requested_cntl7": _close(requested_cntl.get("7"), threshold),
        "factor_setup_zero": factor_setup_zero,
    }
    for name in ("effective_after", "effective_after_symbolic", "effective_after_numeric"):
        bundle = controls.get(name)
        gates[f"{name}_icntl"] = isinstance(bundle, Mapping) and all(
            _close(_control_value(bundle, "icntl", index), value)
            for index, value in MUMPS_FIXED_ICNTL.items()
        )
    for name in ("cntl_after", "cntl_after_symbolic"):
        bundle = controls.get(name)
        gates[f"{name}_cntl7"] = _close(_control_value(bundle, "cntl", 7), threshold)
    numeric = controls.get("effective_after_numeric")
    gates["effective_after_numeric_cntl7"] = _close(
        _control_value(numeric, "cntl", 7), threshold
    )
    gates["observability_reapplied_after_symbolic"] = (
        controls.get("observability_controls_reapplied_after_symbolic") is True
    )

    # Verify the inherited MUMPS ordering/scaling/pivot and contribution
    # controls against the accepted V16 values.  The exact Q1 readbacks are
    # preferred for fields that it exposes, while the V16 invariant supplies
    # the public values that Q1's compact summary does not carry.
    baseline_icntl = dict(BASELINE_ICNTL)
    baseline_symbolic = {}
    baseline_numeric = {}
    if isinstance(exact_factor, Mapping):
        baseline_symbolic = _exact_icntl_settings(
            exact_factor, "symbolic_memory_settings"
        )
        baseline_numeric = _exact_icntl_settings(
            exact_factor, "symbolic_memory_settings_after_memory_limit"
        )
    for index in (7, 10, 14, 18, 22, 23):
        if index in baseline_symbolic:
            # The symbolic Q1 snapshot is the baseline before its memory
            # limit is applied; numeric comparison below uses the after-limit
            # snapshot where available.
            baseline_icntl[index] = baseline_symbolic[index]
    symbolic = controls.get("effective_after_symbolic")
    numeric_icntl = numeric
    gates["baseline_ordering_scaling_pivot_symbolic"] = all(
        _close(_control_value(symbolic, "icntl", index), value)
        for index, value in baseline_icntl.items()
    )
    numeric_expected = dict(baseline_icntl)
    numeric_expected.update(baseline_numeric)
    gates["baseline_ordering_scaling_pivot_numeric"] = all(
        _close(_control_value(numeric_icntl, "icntl", index), value)
        for index, value in numeric_expected.items()
    )
    gates["blr_default_icntl_36_38"] = (
        _close(_control_value(symbolic, "icntl", 36), 0)
        and _close(_control_value(symbolic, "icntl", 38), 600)
        and _close(_control_value(numeric_icntl, "icntl", 36), 0)
        and _close(_control_value(numeric_icntl, "icntl", 38), 600)
        and _close(_control_value(controls.get("default_controls_frozen"), "icntl", 36), 0)
        and _close(_control_value(controls.get("default_controls_frozen"), "icntl", 38), 600)
    )
    symbolic_cntl = controls.get("cntl_after_symbolic")
    numeric_cntl = numeric_icntl
    gates["baseline_pivot_cntl_symbolic"] = all(
        _close(_control_value(symbolic_cntl, "cntl", index), value)
        for index, value in BASELINE_CNTL.items()
    )
    gates["baseline_pivot_cntl_numeric"] = all(
        _close(_control_value(numeric_cntl, "cntl", index), value)
        for index, value in BASELINE_CNTL.items()
    )
    return {"gates": gates, "raw": controls}, all(gates.values())


def _stdout_coverage_facts(
    directory: Path, run_summary: Mapping[str, Any]
) -> dict[str, Any]:
    markers = (
        "Beginning of BLR statistics",
        "Number of BLR fronts",
        "Fraction of factors in BLR fronts",
        "INFOG(29)",
        "INFOG(35)",
        "RINFOG(3)",
        "RINFOG(14)",
    )
    descriptor = run_summary.get("launcher_stdout")
    unavailable = {
        "captures": [],
        "markers": {marker: False for marker in markers},
        "coverage": {
            "number_of_blr_fronts": None,
            "percent_of_factors_in_blr_fronts": None,
            "fraction_of_factors_in_blr_fronts": None,
        },
        "bounded_stdout_present": False,
        "status": "coverage_unavailable",
        "passed": False,
    }
    if not isinstance(descriptor, Mapping):
        return {**unavailable, "reason": "launcher_log_descriptor_missing"}
    raw_path = descriptor.get("path")
    expected_hash = descriptor.get("sha256")
    expected_bytes = descriptor.get("bytes")
    if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
        return {**unavailable, "reason": "launcher_log_descriptor_incomplete"}
    path = Path(raw_path)
    if not path.is_absolute():
        path = directory / path
    try:
        size = path.stat().st_size
    except OSError:
        return {**unavailable, "reason": "launcher_log_missing"}
    if size > STDOUT_COVERAGE_MAX_BYTES:
        return {**unavailable, "reason": "launcher_log_exceeds_bound"}
    if expected_bytes is not None and expected_bytes != size:
        return {**unavailable, "reason": "launcher_log_size_hash_mismatch"}
    actual_hash = _hash(path)
    if actual_hash != expected_hash:
        return {**unavailable, "reason": "launcher_log_hash_mismatch"}
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return {**unavailable, "reason": "launcher_log_read_failed"}
    captures = [{"path": str(path), "sha256": actual_hash, "bytes": size}]
    found = {marker: marker.lower() in text.lower() for marker in markers}
    fronts_match = re.search(
        r"Number\s+of\s+BLR\s+fronts\s*[:=]\s*([0-9]+)", text, re.IGNORECASE
    )
    fraction_match = re.search(
        r"Fraction\s+of\s+factors\s+in\s+BLR\s+fronts\s*[:=]\s*"
        r"([-+0-9.eE]+)\s*%",
        text,
        re.IGNORECASE,
    )
    fronts = int(fronts_match.group(1)) if fronts_match else None
    percent = float(fraction_match.group(1)) if fraction_match else None
    finite_fraction = percent is not None and math.isfinite(percent)
    fraction = percent / 100.0 if finite_fraction else None
    return {
        "captures": captures,
        "markers": found,
        "coverage": {
            "number_of_blr_fronts": fronts,
            "percent_of_factors_in_blr_fronts": percent,
            "fraction_of_factors_in_blr_fronts": fraction,
            "fronts_parsed": fronts is not None,
            "fraction_parsed": finite_fraction,
        },
        "bounded_stdout_present": True,
        "status": (
            "measured"
            if all(found.values()) and fronts is not None and finite_fraction
            else "coverage_unavailable"
        ),
        "passed": bool(all(found.values()) and fronts is not None and finite_fraction),
    }


def _map_layout_facts(arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    slaves = arrays["slaves"]
    masters = arrays["masters"]
    coefficients = arrays["coefficients"]
    offsets = arrays["offsets"]
    independent = arrays["independent_indices"]
    row_count = len(offsets) - 1
    checks = {
        "integer_vectors": all(
            value.ndim == 1 and np.issubdtype(value.dtype, np.integer)
            for value in (slaves, masters, offsets, independent)
        ),
        "finite_coefficients": bool(np.isfinite(coefficients).all()),
        "master_coefficient_lengths": len(masters) == len(coefficients),
        "offsets": bool(
            len(offsets) > 0
            and int(offsets[0]) == 0
            and int(offsets[-1]) == len(masters)
            and np.all(np.diff(offsets) >= 0)
        ),
        "slave_unique": len(np.unique(slaves)) == len(slaves),
        "master_slave_disjoint": not bool(np.intersect1d(slaves, masters).size),
        "independent_unique": len(np.unique(independent)) == len(independent),
        "slave_zero_independent": not bool(np.intersect1d(slaves, independent).size),
        "rows_in_bounds": all(
            value.size == 0
            or (int(np.min(value)) >= 0 and int(np.max(value)) < row_count)
            for value in (slaves, masters, independent)
        ),
    }
    return {"checks": checks, "passed": all(checks.values()), "row_count": row_count}


def _map_evidence(
    root: Path,
    packet_identity: Mapping[str, Any],
    current_identity: Mapping[str, Any],
    exact_identity: Mapping[str, Any],
    cache: dict[str, tuple[dict[str, Any], dict[str, np.ndarray]]],
) -> dict[str, Any]:
    current_map = current_identity.get("fresh_p4_map")
    exact_map = exact_identity.get("fresh_p4_map")
    reference_identity = packet_identity.get("reference_identity")
    reference_identity = reference_identity if isinstance(reference_identity, Mapping) else {}
    map_ref = reference_identity.get("constraints")
    map_ref = map_ref if isinstance(map_ref, Mapping) else {}
    map_npz = _resolve(root, map_ref.get("path"))
    map_json = map_npz.with_suffix(".json")
    cache_key = str(map_json)
    if cache_key not in cache:
        descriptor_packet = _json(map_json)
        arrays = {key: _array(descriptor_packet, key, root) for key in MAP_KEYS}
        cache[cache_key] = (descriptor_packet, arrays)
    descriptor_packet, arrays = cache[cache_key]
    descriptor_fields: dict[str, bool] = {}
    for key in MAP_KEYS:
        actual = {
            "dtype": str(arrays[key].dtype),
            "shape": list(arrays[key].shape),
            "sha256": _array_sha256(arrays[key]),
        }
        descriptor = current_map.get(key) if isinstance(current_map, Mapping) else None
        exact_descriptor = exact_map.get(key) if isinstance(exact_map, Mapping) else None
        packet_descriptor = descriptor_packet.get(key)
        descriptor_fields[key] = bool(
            isinstance(descriptor, Mapping)
            and isinstance(exact_descriptor, Mapping)
            and isinstance(packet_descriptor, Mapping)
            and descriptor.get("dtype") == actual["dtype"]
            and descriptor.get("shape") == actual["shape"]
            and descriptor.get("sha256") == actual["sha256"]
            and exact_descriptor.get("dtype") == actual["dtype"]
            and exact_descriptor.get("shape") == actual["shape"]
            and exact_descriptor.get("sha256") == actual["sha256"]
            and packet_descriptor.get("dtype") == actual["dtype"]
            and packet_descriptor.get("shape") == actual["shape"]
        )
    identity = current_identity.get("fresh_p4_map_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    identity_gates = {
        "status": identity.get("status") == "PASS",
        "master_slave_layout_checked": identity.get("master_slave_layout_checked") is True,
        "primal_map_arrays_checked": identity.get("primal_map_arrays_checked") is True,
        "numeric_keys": identity.get("numeric_keys") == list(MAP_KEYS),
    }
    layout = _map_layout_facts(arrays)
    reference_hash = _hash(map_npz)
    return {
        "reference_npz": str(map_npz),
        "reference_npz_sha256": reference_hash,
        "reference_hash_matches_identity": reference_hash == map_ref.get("sha256"),
        "descriptor_fields": descriptor_fields,
        "identity_gates": identity_gates,
        "layout": layout,
        "passed": all(descriptor_fields.values())
        and all(identity_gates.values())
        and layout["passed"]
        and reference_hash == map_ref.get("sha256")
        and map_npz.is_file(),
    }


def _field_facts(record: Mapping[str, Any]) -> tuple[float, float, float]:
    metrics = record.get("field_metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("field metrics are missing")
    fields = metrics.get("fields")
    if not isinstance(fields, Mapping):
        raise ValueError("raw field norm fields are missing")
    l2 = fields.get("L2")
    curl = fields.get("scaled_curl")
    if not isinstance(l2, Mapping) or not isinstance(curl, Mapping):
        raise ValueError("raw L2/scaled-curl norm fields are missing")
    l2_value = _number(l2.get("absolute_error_norm")) / _number(l2.get("reference_norm"))
    curl_value = _number(curl.get("absolute_error_norm")) / _number(curl.get("reference_norm"))
    if not _close(metrics.get("field_l2_relative"), l2_value) or not _close(
        metrics.get("scaled_curl_relative"), curl_value
    ):
        raise ValueError("saved field relative values disagree with raw norms")
    return l2_value, curl_value, max(l2_value, curl_value)


def _rhs_evidence(
    root: Path,
    packet_directory: Path,
    record: Mapping[str, Any],
    packet: Mapping[str, Any],
    exact_record: Mapping[str, Any],
    exact_packet: Mapping[str, Any],
    stage: str,
    expected_threshold: float,
) -> dict[str, Any]:
    identity = packet.get("identity")
    old_identity = exact_packet.get("identity")
    if not isinstance(identity, Mapping) or not isinstance(old_identity, Mapping):
        raise ValueError("packet identity is missing")
    identity_keys = (
        "input_sha256",
        "input_npz_sha256",
        "g_sha256",
        "reference_json_sha256",
        "reference_npz_sha256",
        "logical_rhs",
        "stem",
    )
    same_identity = all(identity.get(key) == old_identity.get(key) for key in identity_keys)
    input_json = _resolve(root, identity.get("input_json"))
    input_npz = _resolve(root, identity.get("input_npz"))
    reference_json = _resolve(root, identity.get("reference_json"))
    reference_npz = _resolve(root, identity.get("reference_npz"))
    file_hashes = {
        "input_json": _hash(input_json) == identity.get("input_sha256"),
        "input_npz": _hash(input_npz) == identity.get("input_npz_sha256"),
        "reference_json": _hash(reference_json) == identity.get("reference_json_sha256"),
        "reference_npz": _hash(reference_npz) == identity.get("reference_npz_sha256"),
    }
    input_packet = _json(input_json)
    g_input = _array(input_packet, "g", root)
    g = _array(packet, "g", root)
    native = _array(packet, "native_A4_residual", root)
    native_action = _array(packet, "native_action", root)
    native_volume = _array(packet, "native_volume_top_residual", root)
    augmented_top = _array(packet, "augmented_top_residual", root)
    port = _array(packet, "port_residual", root)
    raw_native = _array(packet, "raw_native_A4_residual", root)
    raw_native_volume = _array(packet, "raw_native_volume_top_residual", root)
    raw_augmented_top = _array(packet, "raw_augmented_top_residual", root)
    raw_port = _array(packet, "raw_port_residual", root)
    x = _array(packet, "x_augmented", root)
    identity_facts = record.get("native_residual_identity")
    if not isinstance(identity_facts, Mapping):
        raise ValueError("native residual identity is missing")
    difference = _number(identity_facts.get("absolute_difference"))
    operation_scale = _number(identity_facts.get("operation_scale"))
    identity_relative = difference / operation_scale if operation_scale > 0.0 else math.inf
    augmented = record.get("augmented_residual")
    if not isinstance(augmented, Mapping):
        raise ValueError("augmented residual facts are missing")
    rhs_norm = float(np.linalg.norm(g))
    native_norm = float(np.linalg.norm(native))
    native_action_norm = float(np.linalg.norm(native_action))
    raw_norm_gates = {
        "g_matches_input": bool(np.array_equal(g, g_input)),
        "g_hash": _array_sha256(g) == identity.get("g_sha256"),
        "native_action_is_g_minus_native": bool(np.array_equal(native_action, g - native)),
        "raw_native_sign": bool(np.array_equal(raw_native, -native)),
        "raw_volume_sign": bool(np.array_equal(raw_native_volume, -native_volume)),
        "raw_augmented_sign": bool(np.array_equal(raw_augmented_top, -augmented_top)),
        "raw_port_sign": bool(np.array_equal(raw_port, -port)),
        "identity_rhs_norm": _close(identity_facts.get("rhs_norm"), rhs_norm),
        "identity_native_action_norm": _close(
            identity_facts.get("native_action_norm"), native_action_norm
        ),
        "identity_native_residual_norm": _close(
            identity_facts.get("native_residual_norm"), native_norm
        ),
        "identity_scale_positive": operation_scale > 0.0,
    }
    augmented_gates = {
        "rhs_norm": _close(augmented.get("rhs_norm"), rhs_norm),
        "native_norm": _close(augmented.get("native_A4_norm"), native_norm),
        "top_norm": _close(augmented.get("augmented_top_norm"), np.linalg.norm(augmented_top)),
        "volume_norm": _close(
            augmented.get("native_volume_top_norm"), np.linalg.norm(native_volume)
        ),
        "port_norm": _close(augmented.get("port_residual_norm"), np.linalg.norm(port)),
        "native_relative": _close(
            augmented.get("native_A4_relative"), native_norm / max(rhs_norm, np.finfo(float).tiny)
        ),
        "top_relative": _close(
            augmented.get("augmented_top_relative"),
            np.linalg.norm(augmented_top) / max(rhs_norm, np.finfo(float).tiny),
        ),
    }
    field_l2, curl, _ = _field_facts(record)
    controls = record.get("controls_after_solve")
    control_gates = {
        "one_mat_solve": record.get("factor_solve_call_delta") == 1
        and record.get("factor_solve_calls_after")
        == record.get("factor_solve_calls_before", -1) + 1,
        "no_hidden_refinement": record.get("hidden_refinement") is False,
        "icntl10_zero": _close(_control_value(controls, "icntl", 10), 0),
        "icntl35_two": _close(_control_value(controls, "icntl", 35), 2),
        "cntl7_threshold": _close(_control_value(controls, "cntl", 7), expected_threshold),
    }
    solution_hash = _array_sha256(x)
    gates = {
        "same_input_and_reference": same_identity and all(file_hashes.values()),
        "packet_schema": packet.get("schema")
        == f"task039extra.v17.{stage.lower()}.rhs-packet.v1",
        "packet_array_hash": isinstance(packet.get("arrays"), Mapping)
        and _hash(_resolve(packet_directory, packet["arrays"].get("path")))
        == packet["arrays"].get("sha256"),
        "solution_hash": solution_hash == record.get("solution_sha256"),
        "raw_vectors": all(raw_norm_gates.values()),
        "augmented_raw_vectors": all(augmented_gates.values()),
        "identity": _finite(identity_relative) and identity_relative <= IDENTITY_LIMIT,
        "field_norms": _finite(field_l2, curl),
        "controls": all(control_gates.values()),
    }
    quality = {
        "stem": identity.get("stem"),
        "rho": native_norm / max(rhs_norm, np.finfo(float).tiny),
        "field_l2_relative": field_l2,
        "scaled_curl_relative": curl,
        "native_identity_relative": identity_relative,
        "quality_pass": bool(
            _finite(native_norm, rhs_norm, field_l2, curl, identity_relative)
            and native_norm / max(rhs_norm, np.finfo(float).tiny) <= RHO_LIMIT
            and field_l2 <= FIELD_LIMIT
            and curl <= FIELD_LIMIT
        ),
    }
    exact_field_l2, exact_curl, _ = _field_facts(exact_record)
    gates["exact_A4_qualified"] = bool(
        _finite(exact_record.get("native_A4_relative_residual"))
        and float(exact_record["native_A4_relative_residual"]) <= 1.0e-10
        and exact_field_l2 <= 1.0e-8
        and exact_curl <= 1.0e-8
    )
    return {
        **quality,
        "gates": gates,
        "raw_norm_gates": raw_norm_gates,
        "augmented_gates": augmented_gates,
        "control_gates": control_gates,
        "input_hashes": file_hashes,
        "packet_sha256": _hash(packet_directory / f"{record.get('stem')}.json"),
    }


def check_run(directory: Path, baseline: Path, root: Path) -> dict[str, Any]:
    """Independently check one measured V17 T1/T2 run against exact Q1."""

    summary = _json(directory / "physical_p4_blr_v17_summary.json")
    exact = _json(baseline / "physical_p4_schur_v14_summary.json")
    stage = str(summary.get("stage"))
    threshold = TRADEOFF_THRESHOLDS.get(stage)
    if threshold is None:
        raise ValueError(f"unsupported V17 checker stage: {stage}")
    current_scope = resource_scope(directory, "v17")
    exact_scope = resource_scope(baseline, "v14")
    records = _records(summary)
    if tuple(record.get("stem") for record in records) != STEMS:
        raise ValueError("frozen V17 RHS order changed")
    exact_records = _records(exact)
    exact_by_stem = {record.get("stem"): record for record in exact_records}
    map_identity_file = _json(directory / "reviewed_rhs_identity.json")
    exact_map_identity_file = _json(baseline / "reviewed_rhs_identity.json")
    current_maps = {
        row.get("stem"): row
        for row in map_identity_file.get("records", [])
        if isinstance(row, Mapping)
    }
    exact_maps = {
        row.get("stem"): row
        for row in exact_map_identity_file.get("records", [])
        if isinstance(row, Mapping)
    }
    map_cache: dict[str, tuple[dict[str, Any], dict[str, np.ndarray]]] = {}
    rows: list[dict[str, Any]] = []
    for record in records:
        stem = str(record["stem"])
        old_record = exact_by_stem.get(stem)
        if not isinstance(old_record, Mapping):
            raise ValueError(f"exact Q1 record is missing: {stem}")
        packet_directory = directory / f"{stage.lower()}_rhs_packets"
        packet_path = packet_directory / f"{stem}.json"
        packet = _json(packet_path)
        old_packet = _json(baseline / "q1_rhs_packets" / f"{stem}.json")
        row = _rhs_evidence(
            root,
            packet_directory,
            record,
            packet,
            old_record,
            old_packet,
            stage,
            threshold,
        )
        row["stem"] = stem
        row["map"] = _map_evidence(
            root,
            packet["identity"],
            current_maps.get(stem, {}),
            exact_maps.get(stem, {}),
            map_cache,
        )
        map_cache_key = str(Path(row["map"]["reference_npz"]).with_suffix(".json"))
        _map_descriptor, map_arrays = map_cache[map_cache_key]
        x_storage = _array(packet, "x_storage", root)
        slave_indices = map_arrays["slaves"]
        slave_values = x_storage[slave_indices]
        slave_norm = float(np.linalg.norm(slave_values))
        row["solution_layout"] = {
            "storage_rows": int(x_storage.size),
            "slave_count": int(slave_indices.size),
            "slave_nonzero_count": int(np.count_nonzero(slave_values)),
            "slave_max_abs": float(np.max(np.abs(slave_values), initial=0.0)),
            "slave_norm": slave_norm,
            "slave_relative_norm": slave_norm
            / max(float(np.linalg.norm(x_storage)), np.finfo(float).tiny),
            "slave_zero": bool(
                slave_indices.size == 0
                or (
                    int(np.min(slave_indices)) >= 0
                    and int(np.max(slave_indices)) < x_storage.size
                    and np.all(x_storage[slave_indices] == 0)
                )
            ),
        }
        row["gates"]["solution_slave_zero"] = row["solution_layout"]["slave_zero"]
        row["gates"]["map_identity"] = row["map"]["passed"]
        row["gates"]["all_raw_evidence"] = all(row["gates"].values())
        rows.append(row)
    map_file_gate = {
        "schema": map_identity_file.get("schema") == "task039extra.v14.reviewed-rhs-identity.v1",
        "source_sha": map_identity_file.get("source_sha") == summary.get("source_sha"),
        "rhs_count": map_identity_file.get("rhs_count") == 3,
        "ordered_stems": map_identity_file.get("ordered_stems") == list(STEMS),
    }
    raw_compression = _raw_compression_facts(summary)
    exact_factor = exact.get("factor", {})
    control_facts, controls_pass = _control_facts(summary, threshold, exact_factor)
    run_summary = _json(directory / "run_summary.json")
    stdout_facts = _stdout_coverage_facts(directory, run_summary)
    source = _json(directory / "run_manifest.json")
    resolved = _json(directory / "resolved_config.json")
    old_source = _json(baseline / "run_manifest.json")
    resolved_solver = resolved.get("solver") if isinstance(resolved, Mapping) else {}
    resolved_solver = resolved_solver if isinstance(resolved_solver, Mapping) else {}
    resolved_profile = (
        resolved.get("derived", {}).get("physical_intermediate_profile")
        if isinstance(resolved.get("derived"), Mapping)
        else None
    )
    resolved_profile_id = (
        resolved_profile.get("identity")
        if isinstance(resolved_profile, Mapping)
        else resolved_profile
    )
    source_gates = {
        "summary_source_sha": source.get("source_sha") == summary.get("source_sha"),
        "source_after_sha": source.get("source_after", {}).get("source_sha") == summary.get("source_sha"),
        "resolved_config_hash": _hash(directory / "resolved_config.json")
        == source.get("resolved_config_sha256"),
        "physical_model_identity": source.get("physical_model_sha256")
        == old_source.get("physical_model_sha256"),
        "resolved_profile": (
            resolved_solver.get("preconditioner") == "physical_p4_blr_tradeoff_v17"
            and resolved_profile_id == "physical_p4_blr_tradeoff_v17"
        ),
        "resolved_stage": resolved_solver.get("stage") == stage,
    }
    matrix_gates = {
        key: summary.get("matrix", {}).get(key) == exact.get("matrix", {}).get(key)
        for key in MATRIX_KEYS
    }
    matrix_dimensions_match = all(matrix_gates.values())
    matrix_content = _matrix_content_hash_facts(summary, exact)
    comparison_gates = {
        "BLR_resources": current_scope["passed"],
        "exact_resources": exact_scope["passed"],
        "resource_scope_identity": current_scope["scope"] == exact_scope["scope"],
        "all_rhs_evidence": all(row["gates"]["all_raw_evidence"] for row in rows),
        "map_file": all(map_file_gate.values()),
        "map_identity": all(row["map"]["passed"] for row in rows),
        "matrix_dimensions_match": matrix_dimensions_match,
        "matrix_content_hash_available": matrix_content["available"],
        "physical_identity": source_gates["physical_model_identity"],
        "source_identity": all(source_gates.values()),
        "controls": controls_pass,
        "compression_raw_fields": raw_compression["actual_compression_present"],
    }
    comparison_valid = all(comparison_gates.values())
    peak_ratio = current_scope["full_rss_peak_bytes"] / exact_scope["full_rss_peak_bytes"]
    live_ratio = current_scope["live_rss_peak_bytes"] / exact_scope["live_rss_peak_bytes"]
    # Feed the policy only the independently recomputed raw rows.  The
    # worker's status/booleans and its derived quality/compression fields are
    # intentionally not an alternate policy input.
    policy_summary = dict(summary)
    policy_summary["solve_records"] = rows
    policy_kwargs = {
        "resource_evidence_complete": comparison_valid,
        "peak_ratio": peak_ratio,
        "live_ratio": live_ratio,
    }
    decision = (
        decide_t1(policy_summary, **policy_kwargs)
        if stage == "T1_BLR_CONTROL"
        else decide_t2(policy_summary, **policy_kwargs)
    )
    factor = summary.get("factor", {})
    return {
        "schema": "task039extra.v17.independent-checker.v1",
        "source_sha": summary.get("source_sha"),
        "baseline_source_sha": exact.get("source_sha"),
        "directory": str(directory),
        "baseline": str(baseline),
        "stage": stage,
        "threshold": threshold,
        "summary_sha256": _hash(directory / "physical_p4_blr_v17_summary.json"),
        "baseline_summary_sha256": _hash(
            baseline / "physical_p4_schur_v14_summary.json"
        ),
        "manifest_sha256": _hash(directory / "run_manifest.json"),
        "decision": decision,
        "comparison_gates": comparison_gates,
        "matrix_evidence": {
            "dimensions_match": matrix_dimensions_match,
            "dimension_fields": matrix_gates,
            "content_hash_available": matrix_content["available"],
            "content_hash_comparable": matrix_content["comparable"],
            "content_hash_match": matrix_content["match"],
            "content_hash_field": matrix_content["field"],
            "current_content_sha256": matrix_content["current_sha256"],
            "baseline_content_sha256": matrix_content["baseline_sha256"],
        },
        "control_gates": control_facts,
        "stdout_coverage": stdout_facts,
        "rhs": rows,
        "BLR_resources": current_scope,
        "exact_resources": exact_scope,
        "native_entries": {
            key: raw_compression.get(name)
            for key, name in (
                ("9", "actual_storage_entries"),
                ("29", "theoretical_entries"),
                ("35", "effective_storage_entries"),
            )
        },
        "native_flops": raw_compression.get("native_flops"),
        "factor_memory": factor.get("mumps_memory_observation"),
        "exact_factor_memory": exact_factor.get("mumps_memory_observation"),
        "actual_storage_ratio_to_theoretical": raw_compression.get("ratio"),
        "phase_times": {
            "BLR_symbolic_seconds": factor.get("symbolic_seconds"),
            "BLR_numeric_seconds": factor.get("numeric_seconds"),
            "exact_symbolic_seconds": exact_factor.get("symbolic_seconds"),
            "exact_numeric_seconds": exact_factor.get("numeric_seconds"),
            "BLR_rhs": [
                {
                    key: value
                    for key, value in record.items()
                    if key == "stem" or key.endswith("seconds")
                }
                for record in records
            ],
        },
        "input_result_hashes": {
            str(directory / "physical_p4_blr_v17_summary.json"): _hash(
                directory / "physical_p4_blr_v17_summary.json"
            ),
            str(baseline / "physical_p4_schur_v14_summary.json"): _hash(
                baseline / "physical_p4_schur_v14_summary.json"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("baseline_directory", type=Path)
    args = parser.parse_args()
    result = check_run(
        args.run_directory.resolve(),
        args.baseline_directory.resolve(),
        Path(__file__).resolve().parents[1],
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()


__all__ = [
    "check_run",
    "compression_facts",
    "decide_t1",
    "decide_t2",
    "memory_facts",
    "quality_facts",
]
