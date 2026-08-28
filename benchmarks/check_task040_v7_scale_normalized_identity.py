"""Independent raw checker for V7 scale-normalized diagnostics."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "task040.v7.scale_normalized_identity.v1"
CHECKER_SCHEMA = "task040.v7.scale_normalized_identity_checker.v1"
SAFE_DENOMINATOR = 1.0e-300
IDENTITY_SOURCE_INDICES = (0, 1, 2)
LINEARITY_SOURCE_INDICES = (10, 11)
SCALE_EXPONENTS = (-10, 0, 10)
LINEARITY_ALPHA_REAL = 0.37
LINEARITY_ALPHA_IMAG = -0.21
LINEARITY_ALPHA_ABS = math.hypot(LINEARITY_ALPHA_REAL, LINEARITY_ALPHA_IMAG)
IDENTITY_TOLERANCE = 1.0e-10
BACKWARD_TOLERANCE = 1.0e-10
REPEAT_TOLERANCE = 1.0e-11
LINEARITY_TOLERANCE = 1.0e-11
LEGACY_THRESHOLDS = {
    "zero_map": 1.0e-13,
    "repeat": 1.0e-11,
    "linearity": 1.0e-11,
    "restriction_prolongation": 1.0e-11,
    "full_elimination_gamma": 1.0e-10,
    "full_elimination_interior": 1.0e-10,
}
CONTRIBUTION_NAMES = (
    "middle_boundary", "middle_correction", "lower_correction", "upper_correction"
)
GROUPS = dict(zip(CONTRIBUTION_NAMES, (1, 1, 0, 2), strict=True))
FORMULA_SPECS = {
    "repeat": (("diff", "n1", "n2"), None),
    "identity": (("diff", "naction", "nfull"), None),
    "backward": (("residual", "n_aii_x", "n_rhs"), None),
    "d0_d1": (("diff", "nd0", "nd1"), None),
    "linearity": (("diff", "ncombined", "nleft", "nright"), "alpha_abs"),
}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _nn(value: Any) -> bool:
    return _finite(value) and float(value) >= 0.0


def relative_from_terms(diff: float, *terms: float) -> float:
    if not _nn(diff) or not all(_nn(term) for term in terms):
        raise ValueError("metric terms must be finite non-negative scalars")
    return float(diff) / max(float(sum(terms)), SAFE_DENOMINATOR)


def _formula(kind: str, terms: Mapping[str, Any]) -> float:
    names, weight = FORMULA_SPECS[kind]
    values = [float(terms[name]) for name in names]
    if weight is not None:
        values[-1] *= float(terms[weight])
    return relative_from_terms(values[0], *values[1:])


def repeat_relative(terms: Mapping[str, Any]) -> float:
    return _formula("repeat", terms)


def identity_relative(terms: Mapping[str, Any]) -> float:
    return _formula("identity", terms)


def backward_relative(terms: Mapping[str, Any]) -> float:
    return _formula("backward", terms)


def linearity_relative(terms: Mapping[str, Any]) -> float:
    return _formula("linearity", terms)


def _metric(entry: Any, kind: str, path: str, errors: list[str]) -> float | None:
    if not isinstance(entry, Mapping) or not isinstance(entry.get("terms"), Mapping):
        errors.append(f"{path}.terms is missing")
        return None
    terms = entry["terms"]
    names, weight = FORMULA_SPECS[kind]
    required = names + ((weight,) if weight else ())
    if any(not _nn(terms.get(name)) for name in required):
        errors.append(f"{path}.terms contains an invalid scalar")
        return None
    try:
        return _formula(kind, terms)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"{path} cannot be recomputed: {exc}")
        return None


def _scales(payload: Mapping[str, Any], errors: list[str]) -> dict[int, float]:
    expected = {exp: float(2.0**exp) for exp in SCALE_EXPONENTS}
    values = payload.get("scales")
    if not isinstance(values, list) or len(values) != len(SCALE_EXPONENTS):
        errors.append("scales must contain exactly -10, 0, and 10")
        return {}
    observed = {}
    for item, exp in zip(values, SCALE_EXPONENTS, strict=True):
        if not isinstance(item, Mapping) or item.get("exponent") != exp or item.get("scale") != expected[exp]:
            errors.append("scale records are not the exact reviewed triplet")
        else:
            observed[exp] = expected[exp]
    return observed


def _norms(item: Any, key: str, path: str, errors: list[str]) -> bool:
    values = item.get(key) if isinstance(item, Mapping) else None
    ok = isinstance(values, Mapping) and all(_nn(values.get(name)) for name in ("left", "right", "combined"))
    if not ok:
        errors.append(f"{path}.{key} is invalid")
    return ok


def _check_identity(
    payload: Mapping[str, Any], scales: Mapping[int, float], errors: list[str]
) -> tuple[dict[str, Any], dict[str, str], dict[str, bool], dict[str, list[float]]]:
    expected = {(source, exp) for source in IDENTITY_SOURCE_INDICES for exp in SCALE_EXPONENTS}
    records = payload.get("identity_records")
    metrics: dict[str, Any] = {}
    factor_ids: dict[str, str] = {}
    flags = {"finite": True, "factor_stable": True, "solve_delta": True}
    values = {name: [] for name in ("d0_identity", "d0_repeat", "d1_identity", "d1_repeat", "backward", "group_repeat", "eta")}
    seen: set[tuple[int, int]] = set()
    if not isinstance(records, list):
        errors.append("identity_records must be a list")
        return metrics, factor_ids, flags, values
    if len(records) != len(expected):
        errors.append("identity record count is not exactly nine")
    for index, record in enumerate(records):
        path = f"identity_records[{index}]"
        if not isinstance(record, Mapping):
            errors.append(f"{path} is not an object")
            continue
        source, exp = record.get("source_index"), record.get("scale_exponent")
        key_ok = isinstance(source, int) and not isinstance(source, bool) and isinstance(exp, int) and not isinstance(exp, bool)
        if not key_ok:
            errors.append(f"{path} identity key is invalid")
        else:
            seen.add((source, exp))
        if source not in IDENTITY_SOURCE_INDICES:
            errors.append(f"{path}.source_index is invalid")
        if exp not in SCALE_EXPONENTS:
            errors.append(f"{path}.scale_exponent is invalid")
        if isinstance(exp, int) and exp in scales and record.get("scale") != scales[exp]:
            errors.append(f"{path}.scale does not match exponent")
        if not _nn(record.get("source_norm")):
            errors.append(f"{path}.source_norm is invalid")

        layer_a = record.get("layer_a")
        groups = layer_a.get("groups") if isinstance(layer_a, Mapping) else None
        if not isinstance(groups, list):
            errors.append(f"{path}.layer_a.groups is missing")
            groups = []
        if len(groups) != 3:
            errors.append(f"{path}.layer_a must contain exactly three groups")
        group_seen: set[int] = set()
        for gi, group_record in enumerate(groups):
            gpath = f"{path}.layer_a.groups[{gi}]"
            if not isinstance(group_record, Mapping):
                errors.append(f"{gpath} is not an object")
                continue
            group = group_record.get("group")
            if isinstance(group, int) and not isinstance(group, bool):
                group_seen.add(group)
            if group not in (0, 1, 2):
                errors.append(f"{gpath}.group is invalid")
            for name in ("rhs_norm", "solution1_norm", "solution2_norm"):
                if not _nn(group_record.get(name)):
                    errors.append(f"{gpath}.{name} is invalid")
                    flags["finite"] = False
            backward = _metric(group_record.get("backward"), "backward", f"{gpath}.backward", errors)
            repeat = _metric(group_record.get("repeat"), "repeat", f"{gpath}.repeat", errors)
            if backward is not None:
                values["backward"].append(backward)
            if repeat is not None:
                values["group_repeat"].append(repeat)
            before, after, delta = (group_record.get(name) for name in ("solve_count_before", "solve_count_after", "solve_count_delta"))
            counts_ok = all(isinstance(value, int) and not isinstance(value, bool) for value in (before, after, delta))
            if not counts_ok or after - before != delta or delta != 2:
                errors.append(f"{gpath} solve_count delta is not 2")
                flags["solve_delta"] = False
            before_id, after_id = group_record.get("factor_identity_before"), group_record.get("factor_identity_after")
            stable = isinstance(before_id, str) and bool(before_id) and before_id == after_id
            if not stable:
                errors.append(f"{gpath} factor identity is not stable")
                flags["factor_stable"] = False
            elif str(group) in factor_ids and factor_ids[str(group)] != before_id:
                errors.append(f"{gpath} factor identity changed across records")
                flags["factor_stable"] = False
            elif group in (0, 1, 2):
                factor_ids.setdefault(str(group), before_id)
            for name, count in (("factor_diagnostics_before", before), ("factor_diagnostics_after", after)):
                diagnostic = group_record.get(name)
                if not isinstance(diagnostic, Mapping) or diagnostic.get("solve_count") != count:
                    errors.append(f"{gpath}.{name} readback disagrees")
            if group_record.get("finite") is not True:
                errors.append(f"{gpath}.finite is not true")
                flags["finite"] = False
        if group_seen != {0, 1, 2}:
            errors.append(f"{path}.layer_a must contain groups 0, 1, and 2")

        layer_c = record.get("layer_c")
        if not isinstance(layer_c, Mapping):
            errors.append(f"{path}.layer_c is missing")
            continue
        full = layer_c.get("full")
        if not isinstance(full, Mapping) or not _nn(full.get("output_norm")) or not _nn(full.get("interior_residual_norm")) or full.get("finite") is not True:
            errors.append(f"{path}.layer_c.full is invalid")
            flags["finite"] = False
        row: dict[str, Any] = {}
        for variant in ("d0", "d1"):
            vpath, item = f"{path}.layer_c.{variant}", layer_c.get(variant)
            if not isinstance(item, Mapping) or not _nn(item.get("output_norm")):
                errors.append(f"{vpath}.output_norm is invalid")
                continue
            if item.get("finite") is not True:
                errors.append(f"{vpath}.finite is not true")
                flags["finite"] = False
            identity = _metric(item.get("identity"), "identity", f"{vpath}.identity", errors)
            repeat = _metric(item.get("repeat"), "repeat", f"{vpath}.repeat", errors)
            if identity is not None:
                values[f"{variant}_identity"].append(identity)
            if repeat is not None:
                values[f"{variant}_repeat"].append(repeat)
            row[variant] = {"identity_relative": identity, "repeat_relative": repeat}
        eta = _metric(layer_c.get("d0_d1"), "d0_d1", f"{path}.layer_c.d0_d1", errors)
        if eta is not None:
            values["eta"].append(eta)
            row["d0_d1_eta"] = eta
        contributions = layer_c.get("contribution_output_norms")
        if not isinstance(contributions, Mapping):
            errors.append(f"{path}.layer_c contributions are missing")
        else:
            for name in CONTRIBUTION_NAMES:
                item = contributions.get(name)
                if not isinstance(item, Mapping) or not _nn(item.get("output_norm")) or item.get("finite") is not True:
                    errors.append(f"{path}.layer_c contribution {name} is invalid")
                    flags["finite"] = False
        if not _nn(layer_c.get("roundtrip_error")):
            errors.append(f"{path}.layer_c.roundtrip_error is invalid")
        if key_ok:
            metrics[f"{source}:{exp}"] = row
    if seen != expected:
        errors.append(f"identity record coverage mismatch: missing {sorted(expected - seen)}")
    return metrics, factor_ids, flags, values


def _check_linearity(
    payload: Mapping[str, Any], scales: Mapping[int, float], errors: list[str]
) -> tuple[dict[str, Any], dict[str, list[float]]]:
    records = payload.get("linearity_records")
    values = {name: [] for name in ("layer_b_repeat", "layer_b_linearity", "d0_linearity", "d1_linearity")}
    if not isinstance(records, list):
        errors.append("linearity_records must be a list")
        return {}, values
    if len(records) != len(SCALE_EXPONENTS):
        errors.append("linearity records do not contain exactly three scales")
    metrics: dict[str, Any] = {}
    seen: set[int] = set()
    for index, record in enumerate(records):
        path = f"linearity_records[{index}]"
        if not isinstance(record, Mapping):
            errors.append(f"{path} is not an object")
            continue
        exp = record.get("scale_exponent")
        if isinstance(exp, int) and not isinstance(exp, bool):
            seen.add(exp)
        if exp not in scales or record.get("scale") != scales.get(exp):
            errors.append(f"{path}.scale is invalid")
        if (record.get("left_source_index"), record.get("right_source_index")) != LINEARITY_SOURCE_INDICES:
            errors.append(f"{path} source indices are invalid")
        alpha = record.get("alpha")
        if not isinstance(alpha, Mapping) or any(alpha.get(name) != value for name, value in (("real", LINEARITY_ALPHA_REAL), ("imag", LINEARITY_ALPHA_IMAG), ("abs", LINEARITY_ALPHA_ABS))):
            errors.append(f"{path}.alpha is invalid")
        _norms(record, "input_norms", path, errors)
        layer_b = record.get("layer_b")
        if not isinstance(layer_b, Mapping) or set(layer_b) != set(GROUPS):
            errors.append(f"{path}.layer_b contribution set is invalid")
            layer_b = {}
        bm: dict[str, Any] = {}
        for name, group in GROUPS.items():
            item, ipath = layer_b.get(name), f"{path}.layer_b.{name}"
            if not isinstance(item, Mapping) or item.get("group") != group:
                errors.append(f"{ipath}.group is invalid")
                continue
            _norms(item, "output_norms", ipath, errors)
            repeat = _metric(item.get("repeat"), "repeat", f"{ipath}.repeat", errors)
            linear = _metric(item.get("linearity"), "linearity", f"{ipath}.linearity", errors)
            if repeat is not None:
                values["layer_b_repeat"].append(repeat)
            if linear is not None:
                values["layer_b_linearity"].append(linear)
            if item.get("finite") is not True:
                errors.append(f"{ipath}.finite is not true")
            bm[name] = {"repeat_relative": repeat, "linearity_relative": linear}
        layer_c = record.get("layer_c")
        if not isinstance(layer_c, Mapping):
            errors.append(f"{path}.layer_c is missing")
            layer_c = {}
        cm: dict[str, Any] = {}
        for variant in ("d0", "d1"):
            item, vpath = layer_c.get(variant), f"{path}.layer_c.{variant}"
            if not isinstance(item, Mapping):
                errors.append(f"{vpath} is missing")
                continue
            _norms(item, "output_norms", vpath, errors)
            linear = _metric(item, "linearity", vpath, errors)
            if linear is not None:
                values[f"{variant}_linearity"].append(linear)
            if item.get("finite") is not True:
                errors.append(f"{vpath}.finite is not true")
            cm[variant] = linear
        if isinstance(exp, int) and not isinstance(exp, bool):
            metrics[str(exp)] = {"layer_b": bm, "layer_c": cm}
    if seen != set(SCALE_EXPONENTS):
        errors.append("linearity records do not cover exactly three scales")
    return metrics, values


def _check_structure(payload: Mapping[str, Any], errors: list[str]) -> bool:
    structure = payload.get("structure")
    if not isinstance(structure, Mapping):
        errors.append("structural diagnostics are missing")
        return False
    valid = True
    snapshots: dict[str, Mapping[str, Any]] = {}
    for phase in ("before", "after"):
        item, path = structure.get(phase), f"structure.{phase}"
        if not isinstance(item, Mapping):
            errors.append(f"{path} is missing")
            valid = False
            continue
        snapshots[phase] = item
        layout = item.get("layout")
        fields = ("canonical_position_bijection", "coverage_exact", "owner_distributed")
        if not isinstance(layout, Mapping) or any(layout.get(name) is not True for name in fields):
            errors.append(f"{path}.layout coverage/bijection is invalid")
            valid = False
        if isinstance(layout, Mapping):
            counts = [layout.get(name) for name in ("global_size", "lower_global_rows", "upper_global_rows", "owner_local_mapping_count")]
            positive = all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in counts[:3])
            owner_range = (
                isinstance(counts[0], int)
                and not isinstance(counts[0], bool)
                and isinstance(counts[3], int)
                and not isinstance(counts[3], bool)
                and 0 <= counts[3] <= counts[0]
            )
            if not positive or not owner_range or counts[0] != counts[1] + counts[2]:
                errors.append(f"{path}.layout counts are invalid")
                valid = False
        if item.get("factor_count_ready") != 3 or item.get("factor_count_ready_observed") != 3:
            errors.append(f"{path} does not report three ready factors")
            valid = False
        for name in ("numeric_allgather", "fe_numeric_allgather", "full_interface_numeric_replica"):
            if item.get(name) is not False:
                errors.append(f"{path}.{name} is not false")
                valid = False
        if item.get("scratch_vectors_allocated_per_apply") != 0:
            errors.append(f"{path}.scratch_vectors_allocated_per_apply is not zero")
            valid = False
    if len(snapshots) == 2 and snapshots["before"] != snapshots["after"]:
        errors.append("structure before/after mappings differ")
        valid = False
    return valid


def _check_legacy(payload: Mapping[str, Any], errors: list[str]) -> tuple[bool, dict[str, bool]]:
    legacy = payload.get("legacy_v6_2_absolute_diagnostic")
    if not isinstance(legacy, Mapping):
        errors.append("legacy V6 diagnostic is missing")
        return False, {}
    if (legacy.get("scale_exponent"), legacy.get("scale")) != (0, 1.0):
        errors.append("legacy diagnostic is not scale 1")
    thresholds = legacy.get("thresholds")
    unchanged = isinstance(thresholds, Mapping) and all(thresholds.get(name) == value for name, value in LEGACY_THRESHOLDS.items())
    if not unchanged:
        errors.append("legacy V6 thresholds changed")
    records = legacy.get("deterministic")
    by_index = {item.get("vector_index"): item for item in records if isinstance(item, Mapping)} if isinstance(records, list) else {}
    if len(by_index) != len(IDENTITY_SOURCE_INDICES) or set(by_index) != set(IDENTITY_SOURCE_INDICES):
        errors.append("legacy deterministic vectors are incomplete")
    names = ("gamma_action_error", "full_interior_residual_error", "roundtrip_error", "repeat_error")
    maxima: dict[str, float] = {}
    for name in names:
        values = [item.get(name) for item in by_index.values()]
        if not all(_nn(value) for value in values):
            errors.append(f"legacy {name} is invalid")
            maxima[name] = math.inf
        else:
            maxima[name] = max(float(value) for value in values)
    zero, linearity = legacy.get("zero_error"), legacy.get("linearity_error")
    if not _nn(zero) or not _nn(linearity):
        errors.append("legacy absolute observations are invalid")
    gate = {
        "zero_map": _nn(zero) and zero <= LEGACY_THRESHOLDS["zero_map"],
        "repeat": maxima["repeat_error"] <= LEGACY_THRESHOLDS["repeat"],
        "linearity": _nn(linearity) and linearity <= LEGACY_THRESHOLDS["linearity"],
        "restriction_prolongation": maxima["roundtrip_error"] <= LEGACY_THRESHOLDS["restriction_prolongation"],
        "full_elimination_gamma": maxima["gamma_action_error"] <= LEGACY_THRESHOLDS["full_elimination_gamma"],
        "full_elimination_interior": maxima["full_interior_residual_error"] <= LEGACY_THRESHOLDS["full_elimination_interior"],
        "three_deterministic_vectors": set(by_index) == set(IDENTITY_SOURCE_INDICES),
    }
    return unchanged, gate


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "spread": None}
    low, high = min(values), max(values)
    return {"min": low, "max": high, "spread": high - low}


def check_v7_scale_normalized_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"schema": CHECKER_SCHEMA, "status": "invalid_raw_diagnostics", "checker_pass": False, "evidence_valid": False, "formal_adjudication": False, "classification": "not_formal_adjudication", "errors": ["payload is not an object"]}
    errors: list[str] = []
    for key, expected in (("schema", SCHEMA), ("safe_denominator", SAFE_DENOMINATOR), ("identity_source_indices", list(IDENTITY_SOURCE_INDICES)), ("linearity_source_indices", list(LINEARITY_SOURCE_INDICES)), ("d1_contribution_order", list(CONTRIBUTION_NAMES))):
        if payload.get(key) != expected:
            errors.append(f"{key} changed")
    scales = _scales(payload, errors)
    alpha = payload.get("linearity_alpha")
    if not isinstance(alpha, Mapping) or any(alpha.get(name) != value for name, value in (("real", LINEARITY_ALPHA_REAL), ("imag", LINEARITY_ALPHA_IMAG), ("abs", LINEARITY_ALPHA_ABS))):
        errors.append("linearity_alpha changed")
    setup = payload.get("factor_setup")
    if not isinstance(setup, Mapping) or setup.get("same_action") is not True or setup.get("same_factor_setup") is not True or not isinstance(setup.get("factor_identity_by_group"), Mapping) or not isinstance(setup.get("factor_readback_by_group"), Mapping):
        errors.append("factor setup/readback contract is invalid")
    identity_metrics, factor_ids, flags, identity_values = _check_identity(payload, scales, errors)
    linearity_metrics, linearity_values = _check_linearity(payload, scales, errors)
    legacy_thresholds, legacy_gate = _check_legacy(payload, errors)
    structure_gate = _check_structure(payload, errors)
    if isinstance(setup, Mapping):
        root_ids, readback = setup.get("factor_identity_by_group"), setup.get("factor_readback_by_group")
        if isinstance(root_ids, Mapping) and isinstance(readback, Mapping):
            values = []
            for group in ("0", "1", "2"):
                root_id, detail = root_ids.get(group), readback.get(group)
                if not isinstance(root_id, str) or not root_id or root_id != factor_ids.get(group):
                    errors.append(f"factor setup group {group} identity disagrees")
                if not isinstance(detail, Mapping) or detail.get("factor_identity") != root_id:
                    errors.append(f"factor setup group {group} readback disagrees")
                values.append(root_id)
            if len(set(values)) != 3:
                errors.append("factor setup identities are not three distinct values")

    def within(values: list[float], limit: float, count: int) -> bool:
        return len(values) == count and max(values, default=math.inf) <= limit

    d0_identity = within(identity_values["d0_identity"], IDENTITY_TOLERANCE, 9)
    d0_repeat = within(identity_values["d0_repeat"], REPEAT_TOLERANCE, 9)
    d1_identity = within(identity_values["d1_identity"], IDENTITY_TOLERANCE, 9)
    d1_repeat = within(identity_values["d1_repeat"], REPEAT_TOLERANCE, 9)
    d0_linearity = within(linearity_values["d0_linearity"], LINEARITY_TOLERANCE, 3)
    d1_linearity = within(linearity_values["d1_linearity"], LINEARITY_TOLERANCE, 3)
    group_backward = within(identity_values["backward"], BACKWARD_TOLERANCE, 27)
    group_repeat = within(identity_values["group_repeat"], REPEAT_TOLERANCE, 27)
    layer_b_repeat = within(linearity_values["layer_b_repeat"], REPEAT_TOLERANCE, 12)
    layer_b_linearity = within(linearity_values["layer_b_linearity"], LINEARITY_TOLERANCE, 12)
    factor_gate = flags["finite"] and flags["solve_delta"] and flags["factor_stable"]
    legacy_required = legacy_thresholds and legacy_gate.get("zero_map", False) and legacy_gate.get("restriction_prolongation", False)
    shared = group_backward and group_repeat and layer_b_repeat and layer_b_linearity and factor_gate and structure_gate and legacy_required
    d0_core = d0_identity and d0_repeat and d0_linearity
    d1_core = d1_identity and d1_repeat and d1_linearity
    d0_pass = bool(shared and d0_core)
    d1_pass = bool(shared and d1_core)
    evidence_valid = not errors
    refinement = bool(any(value > BACKWARD_TOLERANCE for value in identity_values["backward"]) or any(value > REPEAT_TOLERANCE for value in identity_values["group_repeat"]))
    partition = bool(group_backward and group_repeat and not d0_core and not d1_core)
    checker_pass = bool(evidence_valid and (d0_pass or d1_pass))
    if not evidence_valid:
        next_stage = "fix_raw_evidence"
    elif refinement:
        next_stage = "conditional_one_residual_correction"
    elif checker_pass:
        next_stage = "formal_integration_requires_full_spectrum_continuation"
    elif partition:
        next_stage = "group_partition_closure_audit"
    else:
        next_stage = "resolve_group_local_or_structural_identity_gate"
    if d0_pass and d1_pass:
        selected_candidate = "d0_lower_memory"
    elif d1_pass:
        selected_candidate = "fixed_order_d1"
    elif d0_pass:
        selected_candidate = "d0"
    else:
        selected_candidate = None
    candidates = {
        "d0_identity": d0_identity, "d0_repeat": d0_repeat, "d0_linearity": d0_linearity,
        "d1_identity": d1_identity, "d1_repeat": d1_repeat, "d1_linearity": d1_linearity,
        "d0_pass_candidate": d0_pass, "d1_pass_candidate": d1_pass,
        "group_backward": group_backward, "group_solve_repeat": group_repeat,
        "layer_b_repeat": layer_b_repeat, "layer_b_linearity": layer_b_linearity,
        "structure": structure_gate, "finite": flags["finite"],
        "factor_solve_delta": flags["solve_delta"], "factor_identity_stable": flags["factor_stable"],
        "group_refinement_trigger": refinement, "partition_audit_trigger": partition,
        "diagnostic_eta_d0_d1_within_1e-10": within(identity_values["eta"], IDENTITY_TOLERANCE, 9),
        "legacy_thresholds_unchanged": legacy_thresholds,
        "legacy_zero_map_absolute": legacy_gate.get("zero_map", False),
        "legacy_roundtrip_absolute": legacy_gate.get("restriction_prolongation", False),
        "legacy_absolute_gate": bool(legacy_gate) and bool(all(legacy_gate.values())),
    }
    summary = {
        "d0": {name: _summary(identity_values[name]) for name in ("d0_identity", "d0_repeat")},
        "d1": {name: _summary(identity_values[name]) for name in ("d1_identity", "d1_repeat")},
        "linearity": {name: _summary(linearity_values[name]) for name in ("d0_linearity", "d1_linearity")},
        "group": {"backward": _summary(identity_values["backward"]), "solve_repeat": _summary(identity_values["group_repeat"])},
        "layer_b": {name: _summary(linearity_values[name]) for name in ("layer_b_repeat", "layer_b_linearity")},
        "eta_d0_d1": _summary(identity_values["eta"]),
    }
    return {
        "schema": CHECKER_SCHEMA, "source_schema": payload.get("schema"),
        "status": "raw_diagnostics_gate_candidate_pass" if checker_pass else "raw_diagnostics_gate_candidate_fail" if evidence_valid else "invalid_raw_diagnostics",
        "checker_pass": checker_pass, "evidence_valid": evidence_valid,
        "formal_adjudication": False, "classification": "not_formal_adjudication",
        "next_required_stage": next_stage, "selected_candidate": selected_candidate,
        "gate_candidates": candidates,
        "recomputed_metrics": {"identity_records": identity_metrics, "linearity_records": linearity_metrics, "summary": summary},
        "runner_claims": payload.get("runner_claims"), "errors": errors,
    }


check_payload = check_v7_scale_normalized_identity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = check_v7_scale_normalized_identity(json.loads(Path(args.input).read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["checker_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
