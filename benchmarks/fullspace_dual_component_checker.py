"""Read-only checker for full-space physical-dual component evidence.

This module deliberately contains no runner, DOLFINx, PETSc, MPI, or solver
imports.  It re-reads local vector manifests and canonical packet shards and
derives every numerical gate from those raw artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "fullspace.full3d.dual-component-record.v1"
PROFILE = "full3d_scalable_v1"
SMALL_LIMIT = 1.0e-12
FROZEN_LIMIT = 1.0e-11
RECOMPOSE_LIMIT = 1.0e-12


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) != {"tuple"} or not isinstance(value["tuple"], list):
            raise ValueError("canonical tuple encoding is invalid")
        return tuple(_key(item) for item in value["tuple"])
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("canonical key encoding is invalid")


def _path(root: Path, descriptor: Any) -> Path:
    if not isinstance(descriptor, dict):
        raise ValueError("artifact descriptor is missing")
    relative = descriptor.get("manifest_relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact path is not relative")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("artifact path escapes raw directory")
    return result


def _read_local(root: Path, descriptor: Any) -> dict[str, Any]:
    manifest_path = _path(root, descriptor)
    if descriptor.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError("local vector manifest SHA mismatch")
    manifest = _json(manifest_path)
    if manifest.get("schema") != "fullspace.dual-component-local-v1":
        raise ValueError("local vector manifest schema mismatch")
    count = 0
    norm_sq = 0.0
    finite = True
    intervals: list[tuple[int, int]] = []
    row_map: dict[int, complex] = {}
    for shard in manifest.get("shards", []):
        shard_path = (root / shard["relative_path"]).resolve()
        if not shard_path.is_relative_to(root.resolve()):
            raise ValueError("local vector shard escapes raw directory")
        if shard_path.stat().st_size != int(shard["bytes"]):
            raise ValueError("local vector shard byte count mismatch")
        if _sha256(shard_path) != shard["sha256"]:
            raise ValueError("local vector shard SHA mismatch")
        values = np.load(shard_path, allow_pickle=False)
        values = np.asarray(values, dtype=np.complex128)
        row_start = int(shard["row_start"])
        row_end = int(shard["row_end"])
        if row_start < 0 or row_end < row_start:
            raise ValueError("local vector row interval is invalid")
        if values.size != int(shard["count"]) or row_end - row_start != values.size:
            raise ValueError("local vector shard count mismatch")
        observed_finite = bool(np.all(np.isfinite(values)))
        if observed_finite != bool(shard["finite"]):
            raise ValueError("local vector shard finite fact mismatch")
        observed_norm_sq = float(np.vdot(values, values).real)
        if not math.isclose(observed_norm_sq, float(shard["norm_sq"]), rel_tol=1e-13, abs_tol=1e-30):
            raise ValueError("local vector shard norm fact mismatch")
        count += int(values.size)
        norm_sq += observed_norm_sq
        finite = finite and observed_finite
        intervals.append((row_start, row_end))
        row_map.update(
            {row_start + index: complex(value) for index, value in enumerate(values)}
        )
    previous_end = -1
    for row_start, row_end in sorted(intervals):
        if row_start < previous_end:
            raise ValueError("local vector shard row intervals overlap")
        previous_end = row_end
    if count != int(manifest.get("owned_count", -1)):
        raise ValueError("local vector owned count mismatch")
    if bool(manifest.get("finite")) != finite:
        raise ValueError("local vector finite aggregate mismatch")
    return {
        "count": count,
        "norm": float(math.sqrt(norm_sq)),
        "finite": finite,
        "map": row_map,
        "path": str(manifest_path),
    }


def _read_canonical(root: Path, descriptor: Any) -> dict[str, Any]:
    manifest_path = _path(root, descriptor)
    if descriptor.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError("canonical manifest SHA mismatch")
    manifest = _json(manifest_path)
    if manifest.get("role") != "full_fe_dual":
        raise ValueError("canonical manifest role mismatch")
    packets: list[tuple[Any, complex]] = []
    for shard in manifest.get("per_rank_shards", []):
        shard_path = (manifest_path.parent / shard["filename"]).resolve()
        if _sha256(shard_path) != shard["file_sha256"]:
            raise ValueError("canonical shard SHA mismatch")
        for line in shard_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("schema_version") != "task037.canonical-vector-shard.v1":
                raise ValueError("canonical shard schema mismatch")
            key = _key(item["key"])
            key_bytes = json.dumps(
                _json_key(key), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if hashlib.sha256(key_bytes).hexdigest() != item.get("key_sha256"):
                raise ValueError("canonical key SHA mismatch")
            value = item.get("value")
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("canonical value encoding mismatch")
            packets.append((key, complex(float(value[0]), float(value[1]))))
    values = {key: value for key, value in packets}
    duplicate_count = len(packets) - len(values)
    finite = all(math.isfinite(value.real) and math.isfinite(value.imag) for value in values.values())
    norm = float(math.sqrt(sum(abs(value) ** 2 for value in values.values())))
    if len(packets) != int(manifest.get("global_summed_packet_count", -1)):
        raise ValueError("canonical packet count mismatch")
    if int(descriptor.get("duplicate_count", duplicate_count)) != int(manifest.get("summed_local_duplicate_count", -1)):
        raise ValueError("canonical duplicate descriptor mismatch")
    if bool(descriptor.get("finite")) != finite:
        raise ValueError("canonical finite descriptor mismatch")
    return {
        "map": values,
        "packet_count": len(packets),
        "unique_key_count": len(values),
        "duplicate_count": duplicate_count,
        "finite": finite,
        "norm": norm,
        "path": str(manifest_path),
    }


def _json_key(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_json_key(item) for item in value]}
    return value


def _compare_maps(left: dict[Any, complex], right: dict[Any, complex]) -> dict[str, Any]:
    left_keys = set(left)
    right_keys = set(right)
    common = left_keys & right_keys
    difference_sq = sum(abs(left[key] - right[key]) ** 2 for key in common)
    right_norm = math.sqrt(sum(abs(value) ** 2 for value in right.values()))
    return {
        "key_set_equal": left_keys == right_keys,
        "missing_key_count": len(right_keys - left_keys),
        "extra_key_count": len(left_keys - right_keys),
        "relative_l2": float(math.sqrt(difference_sq) / max(right_norm, 1.0e-30)),
        "max_abs": float(max((abs(left[key] - right[key]) for key in common), default=0.0)),
    }


def _sum_maps(maps: list[dict[Any, complex]]) -> dict[Any, complex]:
    if not maps:
        return {}
    keys = set(maps[0])
    if any(set(item) != keys for item in maps[1:]):
        raise ValueError("component canonical key sets are not identical")
    return {key: sum(item[key] for item in maps) for key in keys}


def _compare_state_sum(
    states: list[dict[str, Any]], reference: dict[str, Any], phase: str
) -> dict[str, Any] | None:
    maps = [state.get(phase, {}).get("map") for state in states]
    reference_map = reference.get(phase, {}).get("map")
    if not all(isinstance(item, dict) for item in (*maps, reference_map)):
        return None
    return _compare_maps(_sum_maps(maps), reference_map)


def _state(root: Path, state: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return {}, ["component state is missing"]
    facts: dict[str, Any] = {}
    for name in ("pre_mpc", "owner_local"):
        try:
            facts[name] = _read_local(root, state[name])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {exc}")
    try:
        facts["canonical"] = _read_canonical(root, state["canonical"])
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"canonical: {exc}")
    if facts.get("canonical", {}).get("duplicate_count") != 0:
        errors.append("canonical duplicate count is nonzero")
    if facts.get("canonical", {}).get("finite") is not True:
        errors.append("canonical vector is non-finite")
    return facts, errors


def _compare_state_phases(
    left: dict[str, Any], right: dict[str, Any], limit: float, context: str
) -> tuple[dict[str, Any], list[str]]:
    comparisons: dict[str, Any] = {}
    errors: list[str] = []
    for phase in ("pre_mpc", "owner_local", "canonical"):
        left_map = left.get(phase, {}).get("map")
        right_map = right.get(phase, {}).get("map")
        if not isinstance(left_map, dict) or not isinstance(right_map, dict):
            errors.append(f"{context} {phase} map could not be recomputed")
            continue
        comparison = _compare_maps(left_map, right_map)
        comparisons[phase] = comparison
        if not comparison["key_set_equal"] or comparison["relative_l2"] > limit:
            errors.append(f"{context} {phase} exceeds component gate")
    return comparisons, errors


def _compact_json(value: Any) -> Any:
    """Remove internal tuple-key packet maps before writing compact JSON."""

    if isinstance(value, dict):
        return {
            str(key): _compact_json(item)
            for key, item in value.items()
            if key != "map"
        }
    if isinstance(value, list):
        return [_compact_json(item) for item in value]
    return value


def _check_mode_grouping(
    record: dict[str, Any],
    mode_total_states: dict[int, dict[str, dict[str, Any]]],
    modal_state: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    modes = record.get("modes", {})
    grouping = modes.get("grouping")
    inventory = modes.get("inventory")
    if not isinstance(grouping, dict) or not isinstance(inventory, list):
        return {}, ["side/polarization grouping is missing"]
    inventory_by_index: dict[int, dict[str, Any]] = {}
    for item in inventory:
        if not isinstance(item, dict):
            errors.append("mode inventory item is invalid")
            continue
        try:
            index = int(item["mode_index"])
            amplitude = complex(*item["incident_amplitude"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"mode inventory scalar is invalid: {exc}")
            continue
        if index in inventory_by_index:
            errors.append(f"duplicate mode inventory index: {index}")
        inventory_by_index[index] = item
        if not math.isfinite(amplitude.real) or not math.isfinite(amplitude.imag):
            errors.append(f"mode inventory amplitude is non-finite: {index}")
    if sorted(inventory_by_index) != list(range(len(inventory))):
        errors.append("mode inventory indices are not an exact ordered partition")
    def check_group(category: str, name: str, group: Any) -> dict[str, Any]:
        if not isinstance(group, dict):
            errors.append(f"{category} group is missing: {name}")
            return {}
        expected_all = [
            index for index, item in inventory_by_index.items()
            if str(item.get(category)) == name
        ]
        expected = [
            index for index in expected_all
            if complex(*inventory_by_index[index]["incident_amplitude"]) != 0.0j
        ]
        expected_zero = [index for index in expected_all if index not in expected]
        selected = group.get("nonzero_mode_indices")
        if selected != expected:
            errors.append(f"{category} group nonzero inventory mismatch: {name}")
        zero = group.get("exact_zero_mode_indices")
        inventory_count = int(group.get("inventory_mode_count", -1))
        if not isinstance(selected, list) or not isinstance(zero, list):
            errors.append(f"{category} group index partition is missing: {name}")
            selected = [] if not isinstance(selected, list) else selected
            zero = [] if not isinstance(zero, list) else zero
        if zero != expected_zero:
            errors.append(f"{category} group exact-zero inventory mismatch: {name}")
        if inventory_count != len(expected_all):
            errors.append(f"{category} group inventory count mismatch: {name}")
        if inventory_count != len(selected) + len(zero) or len(set(selected + zero)) != inventory_count:
            errors.append(f"{category} group index partition is invalid: {name}")
        ref_indices = group.get("total", {}).get("mode_indices")
        if ref_indices != expected:
            errors.append(f"{category} group total descriptors mismatch: {name}")
        for index in expected:
            expected_states = mode_total_states.get(index)
            if expected_states is None:
                errors.append(f"{category} group refers to an unreadable mode: {name}/{index}")
        return {"mode_indices": expected, "exact_zero_mode_indices": expected_zero}

    result: dict[str, Any] = {}
    for category, required in (("side", ("top", "bottom")), ("polarization", ("s", "p"))):
        groups = grouping.get(category)
        if not isinstance(groups, dict):
            errors.append(f"{category} grouping is missing")
            continue
        result[category] = {}
        names = tuple(sorted(set(required) | set(groups)))
        for name in names:
            result[category][name] = check_group(category, name, groups.get(name))
        for side in ("candidate", "oracle"):
            for phase in ("pre_mpc", "owner_local", "canonical"):
                maps = [
                    mode_total_states[index][side][phase]["map"]
                    for index, item in inventory_by_index.items()
                    if str(item.get(category)) in names
                    and complex(*item["incident_amplitude"]) != 0.0j
                    and isinstance(mode_total_states.get(index, {}).get(side, {}).get(phase, {}).get("map"), dict)
                ]
                comparison = None
                reference = modal_state.get(side, {}).get(phase, {}).get("map")
                if isinstance(reference, dict) and maps and all(isinstance(item, dict) for item in maps):
                    comparison = _compare_maps(_sum_maps(maps), reference)
                result[category][f"{side}_{phase}_sum"] = comparison
                if comparison is None:
                    errors.append(f"{category} {side} {phase} group sum could not be recomputed")
                elif not comparison["key_set_equal"] or comparison["relative_l2"] > RECOMPOSE_LIMIT:
                    errors.append(f"{category} {side} {phase} group sum exceeds modal gate")
    return result, errors


def _check_record_payload(record: dict[str, Any], record_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if record.get("schema") != SCHEMA or record.get("profile") != PROFILE:
        errors.append("record schema/profile mismatch")
    source = record.get("source")
    source_ok = isinstance(source, dict) and (
        source.get("expected_sha") == source.get("commit_sha_start") == source.get("commit_sha_end")
        and isinstance(source.get("expected_sha"), str)
        and len(source["expected_sha"]) == 40
        and source.get("tracked_status_start") == ""
        and source.get("tracked_status_end") == ""
        and source.get("branch") == "codex/20260820-task38-extra-full3d-iterative-0p7nm"
    )
    if source_ok:
        source_ok = all(
            isinstance(source.get(name), str)
            and all(character in "0123456789abcdef" for character in source[name])
            for name in ("expected_sha", "commit_sha_start", "commit_sha_end")
        )
    if not source_ok:
        errors.append("source identity is not clean and hash-bound")
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    components = record.get("components")
    if not isinstance(components, dict):
        errors.append("component groups are missing")
        components = {}
    case = record.get("case")
    limit = SMALL_LIMIT if case in {"p2-h50", "p3-h50"} else FROZEN_LIMIT
    state_facts: dict[str, Any] = {}
    for name in ("incident_base", "modal_total", "rhs"):
        group = components.get(name)
        if not isinstance(group, dict):
            errors.append(f"component group is missing: {name}")
            continue
        candidate_facts, candidate_errors = _state(raw_dir, group.get("candidate"))
        oracle_facts, oracle_errors = _state(raw_dir, group.get("oracle"))
        errors.extend(f"{name} candidate: {error}" for error in candidate_errors)
        errors.extend(f"{name} oracle: {error}" for error in oracle_errors)
        state_facts[name] = {"candidate": candidate_facts, "oracle": oracle_facts}
        comparisons, comparison_errors = _compare_state_phases(
            candidate_facts, oracle_facts, limit, f"{name} candidate/oracle"
        )
        state_facts[name]["comparisons"] = comparisons
        errors.extend(comparison_errors)
        if name == "incident_base":
            component_sum = group.get("component_sum")
            if not isinstance(component_sum, dict) or component_sum.get("components") != ["0", "1"] or component_sum.get("candidate_component_api") is not False:
                errors.append("incident_base component-sum provenance is invalid")
            direct_components = group.get("direct_components")
            component_facts: dict[str, Any] = {}
            component_states: list[dict[str, Any]] = []
            if not isinstance(direct_components, dict):
                errors.append("incident_base direct component states are missing")
            else:
                for component in ("0", "1"):
                    facts, component_errors = _state(
                        raw_dir, direct_components.get(component)
                    )
                    errors.extend(
                        f"incident_base direct component {component}: {error}"
                        for error in component_errors
                    )
                    component_facts[component] = facts
                    component_states.append(facts)
            state_facts[name]["direct_components"] = component_facts
            direct_sums = {}
            candidate_vs_direct_sums = {}
            for phase in ("pre_mpc", "owner_local", "canonical"):
                direct_sum = _compare_state_sum(component_states, oracle_facts, phase)
                candidate_vs_direct_sum = _compare_state_sum(
                    component_states, candidate_facts, phase
                )
                direct_sums[phase] = direct_sum
                candidate_vs_direct_sums[phase] = candidate_vs_direct_sum
                for label, comparison in (
                    ("direct base component sum", direct_sum),
                    ("candidate whole versus direct base component sum", candidate_vs_direct_sum),
                ):
                    if comparison is None:
                        errors.append(f"{label} {phase} could not be recomputed")
                    elif not comparison["key_set_equal"] or comparison["relative_l2"] > limit:
                        errors.append(f"{label} {phase} exceeds component gate")
            state_facts[name]["direct_component_sum"] = direct_sums
            state_facts[name]["candidate_vs_direct_component_sum"] = candidate_vs_direct_sums
    mode_records = record.get("modes", {}).get("records", [])
    if not isinstance(mode_records, list) or not mode_records:
        errors.append("nonzero incident mode records are missing")
        mode_records = []
    mode_indices: set[int] = set()
    inventory_count = record.get("modes", {}).get("inventory_count")
    for item in mode_records:
        try:
            index = int(item["mode_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if index in mode_indices:
            errors.append(f"duplicate nonzero mode record: {index}")
        if isinstance(inventory_count, int) and not 0 <= index < inventory_count:
            errors.append(f"mode index is outside the inventory: {index}")
        mode_indices.add(index)
    inventory = record.get("modes", {}).get("inventory")
    if not isinstance(inventory, list):
        errors.append("full mode inventory is missing")
    else:
        if record.get("modes", {}).get("inventory_count") != len(inventory):
            errors.append("mode inventory count does not match its records")
        if record.get("modes", {}).get("nonzero_incident_count") != len(mode_records):
            errors.append("nonzero mode count does not match its records")
        expected_nonzero = set()
        for item in inventory:
            try:
                if complex(*item["incident_amplitude"]) != 0.0j:
                    expected_nonzero.add(int(item["mode_index"]))
            except (KeyError, TypeError, ValueError):
                errors.append("full mode inventory amplitude is invalid")
        if mode_indices != expected_nonzero:
            errors.append("recorded nonzero modes do not equal exact nonzero amplitudes")
    mode_facts = []
    mode_total_states: dict[int, dict[str, dict[str, Any]]] = {}
    for mode_record in mode_records:
        if not isinstance(mode_record, dict):
            errors.append("mode component record is invalid")
            continue
        try:
            candidate_amp = complex(*mode_record["candidate_amplitude"])
            direct_amp = complex(*mode_record["direct_amplitude"])
            candidate_h = float(mode_record["candidate_H"])
            direct_h = float(mode_record["direct_H"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"mode scalar facts are invalid: {exc}")
            continue
        if not all(math.isfinite(value) for value in (candidate_h, direct_h)) or min(candidate_h, direct_h) <= 0.0:
            errors.append("mode H is not finite and positive")
        amplitude_error = abs(candidate_amp - direct_amp) / max(abs(direct_amp), 1.0e-30)
        h_error = abs(candidate_h - direct_h) / max(abs(direct_h), 1.0e-30)
        try:
            candidate_traction = np.asarray(
                [complex(*value) for value in mode_record["candidate_traction"]],
                dtype=np.complex128,
            )
            direct_traction = np.asarray(
                [complex(*value) for value in mode_record["direct_traction"]],
                dtype=np.complex128,
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"mode traction facts are invalid: {exc}")
            candidate_traction = np.zeros(3, dtype=np.complex128)
            direct_traction = np.ones(3, dtype=np.complex128)
        traction_error = float(
            np.linalg.norm(candidate_traction - direct_traction)
            / max(np.linalg.norm(direct_traction), 1.0e-30)
        )
        try:
            wavevector = np.asarray(
                [
                    complex(*mode_record["alpha"]),
                    complex(*mode_record["gamma"]),
                    complex(*mode_record["kz"]),
                ],
                dtype=np.complex128,
            )
            e_vector = np.asarray(
                [complex(*value) for value in mode_record["e_vector"]],
                dtype=np.complex128,
            )
            normal = np.asarray(
                (0.0, 0.0, 1.0)
                if mode_record.get("side") == "top"
                else (0.0, 0.0, -1.0)
            )
            expected_traction = np.cross(
                1j * np.cross(wavevector, e_vector),
                normal,
            )
            candidate_traction_formula_error = float(
                np.linalg.norm(candidate_traction - expected_traction)
                / max(np.linalg.norm(expected_traction), 1.0e-30)
            )
            direct_traction_formula_error = float(
                np.linalg.norm(direct_traction - expected_traction)
                / max(np.linalg.norm(expected_traction), 1.0e-30)
            )
        except (KeyError, TypeError, ValueError):
            candidate_traction_formula_error = math.inf
            direct_traction_formula_error = math.inf
        if max(candidate_traction_formula_error, direct_traction_formula_error) > limit:
            errors.append("mode traction formula audit exceeds gate")
        if amplitude_error > limit or h_error > limit:
            errors.append("mode amplitude/H direct audit exceeds gate")
        if traction_error > limit:
            errors.append("mode traction direct audit exceeds gate")
        component_facts: dict[str, Any] = {}
        candidate_component_states: list[dict[str, Any]] = []
        oracle_component_states: list[dict[str, Any]] = []
        for component in ("0", "1"):
            item = mode_record.get("components", {}).get(component)
            if not isinstance(item, dict):
                errors.append(f"mode component {component} is missing")
                continue
            candidate_facts, candidate_errors = _state(raw_dir, item.get("candidate"))
            oracle_facts, oracle_errors = _state(raw_dir, item.get("oracle"))
            candidate_component_states.append(candidate_facts)
            oracle_component_states.append(oracle_facts)
            errors.extend(f"mode {mode_record.get('mode_index')} c{component} candidate: {error}" for error in candidate_errors)
            errors.extend(f"mode {mode_record.get('mode_index')} c{component} oracle: {error}" for error in oracle_errors)
            comparisons, comparison_errors = _compare_state_phases(
                candidate_facts,
                oracle_facts,
                limit,
                f"mode {mode_record.get('mode_index')} component {component}",
            )
            component_facts[component] = comparisons
            errors.extend(comparison_errors)
        candidate_total, candidate_total_errors = _state(
            raw_dir, mode_record.get("candidate_total")
        )
        oracle_total, oracle_total_errors = _state(
            raw_dir, mode_record.get("direct_total")
        )
        errors.extend(
            f"mode {mode_record.get('mode_index')} candidate total: {error}"
            for error in candidate_total_errors
        )
        errors.extend(
            f"mode {mode_record.get('mode_index')} oracle total: {error}"
            for error in oracle_total_errors
        )
        candidate_recompose = {}
        oracle_recompose = {}
        for phase in ("pre_mpc", "owner_local", "canonical"):
            candidate_recompose[phase] = _compare_state_sum(
                candidate_component_states, candidate_total, phase
            )
            oracle_recompose[phase] = _compare_state_sum(
                oracle_component_states, oracle_total, phase
            )
            for label, comparison in (
                ("candidate component recomposition", candidate_recompose[phase]),
                ("oracle component recomposition", oracle_recompose[phase]),
            ):
                if comparison is None:
                    errors.append(
                        f"mode {mode_record.get('mode_index')} {label} {phase} could not be recomputed"
                    )
                elif not comparison["key_set_equal"] or comparison["relative_l2"] > limit:
                    errors.append(
                        f"mode {mode_record.get('mode_index')} {label} {phase} exceeds gate"
                    )
        total_comparison, total_errors = _compare_state_phases(
            candidate_total,
            oracle_total,
            limit,
            f"mode {mode_record.get('mode_index')} candidate/oracle total",
        )
        errors.extend(total_errors)
        mode_total_states[int(mode_record["mode_index"])] = {
            "candidate": candidate_total,
            "oracle": oracle_total,
        }
        mode_facts.append(
            {
                "mode_index": mode_record.get("mode_index"),
                "amplitude_relative_error": amplitude_error,
                "H_relative_error": h_error,
                "traction_relative_error": traction_error,
                "candidate_traction_formula_error": candidate_traction_formula_error,
                "direct_traction_formula_error": direct_traction_formula_error,
                "components": component_facts,
                "candidate_recompose": candidate_recompose,
                "oracle_recompose": oracle_recompose,
                "total_comparison": total_comparison,
            }
        )
    grouping_facts, grouping_errors = _check_mode_grouping(
        record,
        mode_total_states,
        state_facts.get("modal_total", {}),
    )
    errors.extend(grouping_errors)
    all_mode_recompose: dict[str, dict[str, Any] | None] = {}
    modal_facts = state_facts.get("modal_total", {})
    for side in ("candidate", "oracle"):
        all_mode_recompose[side] = {}
        for phase in ("pre_mpc", "owner_local", "canonical"):
            maps = []
            for index in sorted(mode_total_states):
                value = mode_total_states[index][side].get(phase, {}).get("map")
                if not isinstance(value, dict):
                    maps = []
                    break
                maps.append(value)
            reference = modal_facts.get(side, {}).get(phase, {}).get("map")
            comparison = None
            if maps and isinstance(reference, dict):
                comparison = _compare_maps(_sum_maps(maps), reference)
            all_mode_recompose[side][phase] = comparison
            if comparison is None:
                errors.append(f"all-mode {side} {phase} sum could not be recomputed")
            elif not comparison["key_set_equal"] or comparison["relative_l2"] > RECOMPOSE_LIMIT:
                errors.append(f"all-mode {side} {phase} sum exceeds modal gate")
    audit = record.get("audit")
    if not isinstance(audit, dict):
        errors.append("component audit is missing")
    else:
        for field in ("numeric_allgather", "global_aij_materialized", "dense_interface_schur_materialized", "ksp_created", "pde_run", "official_physics"):
            if field in {"official_physics"}:
                if audit.get(field) != "not_run":
                    errors.append("official physics was not explicitly not_run")
            elif audit.get(field) is not False:
                errors.append(f"forbidden execution/materialization audit is true: {field}")
        if audit.get("mpc", {}).get("manual_phase_application") is not False:
            errors.append("manual Floquet phase application is not false")
    telemetry = record.get("telemetry", {})
    if not isinstance(telemetry, dict) or telemetry.get("rank_max_swap_used_bytes") != 0:
        errors.append("swap gate is not zero")
    repeated: dict[str, Any] = {}
    rhs_group = components.get("rhs", {}) if isinstance(components.get("rhs"), dict) else {}
    if "rhs" in state_facts:
        candidate_map = state_facts["rhs"]["candidate"].get("canonical", {}).get("map")
        oracle_map = state_facts["rhs"]["oracle"].get("canonical", {}).get("map")
        base_candidate = state_facts.get("incident_base", {}).get("candidate", {}).get("canonical", {}).get("map")
        base_oracle = state_facts.get("incident_base", {}).get("oracle", {}).get("canonical", {}).get("map")
        modal_candidate = state_facts.get("modal_total", {}).get("candidate", {}).get("canonical", {}).get("map")
        modal_oracle = state_facts.get("modal_total", {}).get("oracle", {}).get("canonical", {}).get("map")
        if all(isinstance(item, dict) for item in (candidate_map, oracle_map, base_candidate, base_oracle, modal_candidate, modal_oracle)):
            candidate_recompose = _compare_maps(_sum_maps([base_candidate, modal_candidate]), candidate_map)
            oracle_recompose = _compare_maps(_sum_maps([base_oracle, modal_oracle]), oracle_map)
            repeated["candidate_recompose"] = candidate_recompose
            repeated["oracle_recompose"] = oracle_recompose
            if candidate_recompose["relative_l2"] > RECOMPOSE_LIMIT or oracle_recompose["relative_l2"] > RECOMPOSE_LIMIT:
                errors.append("whole RHS recomposition exceeds gate")
    for name in ("candidate_repeat", "oracle_repeat"):
        descriptor = rhs_group.get(name)
        if descriptor is None:
            errors.append(f"RHS repeat artifact is missing: {name}")
            continue
        try:
            repeat_facts = _read_canonical(raw_dir, descriptor)
            reference = state_facts["rhs"]["candidate" if name == "candidate_repeat" else "oracle"]["canonical"]["map"]
            repeated[name] = _compare_maps(reference, repeat_facts["map"])
            if not repeated[name]["key_set_equal"] or repeated[name]["relative_l2"] > RECOMPOSE_LIMIT:
                errors.append(f"RHS repeat exceeds gate: {name}")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"RHS repeat unreadable: {name}: {exc}")
    if record.get("authority_classification") != "OLD_W5_PHYSICAL_DUAL_NOT_CURRENT_AUTHORITY":
        errors.append("old W5/current authority classification is missing")
    return {
        "schema": SCHEMA,
        "status": "pass" if not errors else "fail",
        "failures": errors,
        "classification": (
            "OLD_W5_PHYSICAL_DUAL_NOT_CURRENT_AUTHORITY + CURRENT_DUAL_ORACLE_PASS"
            if not errors
            else "CURRENT_DUAL_ORACLE_NOT_QUALIFIED"
        ),
        "gates": {
            "source_identity": source_ok,
            "component_oracle": not any("component" in error or "mode " in error for error in errors),
            "recompose": not any("recomposition" in error for error in errors),
            "repeat": not any("repeat" in error for error in errors),
            "resource_swap": telemetry.get("rank_max_swap_used_bytes") == 0 if isinstance(telemetry, dict) else False,
        },
        "derived": {
            "component_limit": limit,
            "states": _compact_json(state_facts),
            "modes": mode_facts,
            "grouping": grouping_facts,
            "all_mode_recompose": all_mode_recompose,
            "repeat_recompose": repeated,
        },
        "record_path": str(record_path.resolve()),
    }


def check_record(record_path: Path) -> dict[str, Any]:
    try:
        return _check_record_payload(_json(record_path), record_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": SCHEMA, "status": "fail", "failures": [f"record unreadable: {exc}"]}


def _cross_canonical(
    left_root: Path, left_descriptor: Any, right_root: Path, right_descriptor: Any
) -> dict[str, Any]:
    return _compare_maps(
        _read_canonical(left_root, left_descriptor)["map"],
        _read_canonical(right_root, right_descriptor)["map"],
    )


def check_pair(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = check_record(left_path)
    right = check_record(right_path)
    errors = list(left.get("failures", [])) + [f"right: {error}" for error in right.get("failures", [])]
    left_record = _json(left_path)
    right_record = _json(right_path)
    left_root = Path(left_record["raw_dir"]).resolve()
    right_root = Path(right_record["raw_dir"]).resolve()
    if left_record.get("case") != right_record.get("case") or left_record.get("degree") != right_record.get("degree"):
        errors.append("MPI pair case/degree mismatch")
    cross: dict[str, Any] = {}
    for name in ("incident_base", "modal_total", "rhs"):
        for side in ("candidate", "oracle"):
            try:
                left_desc = left_record["components"][name][side]["canonical"]
                right_desc = right_record["components"][name][side]["canonical"]
                left_facts = _read_canonical(left_root, left_desc)
                right_facts = _read_canonical(right_root, right_desc)
                comparison = _compare_maps(left_facts["map"], right_facts["map"])
                cross[f"{name}_{side}"] = comparison
                if not comparison["key_set_equal"] or comparison["relative_l2"] > SMALL_LIMIT:
                    errors.append(f"cross-MPI identity exceeds gate: {name}/{side}")
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"cross-MPI artifact unreadable: {name}/{side}: {exc}")
    for component in ("0", "1"):
        try:
            comparison = _cross_canonical(
                left_root,
                left_record["components"]["incident_base"]["direct_components"][component]["canonical"],
                right_root,
                right_record["components"]["incident_base"]["direct_components"][component]["canonical"],
            )
            cross[f"incident_base_direct_component_{component}"] = comparison
            if not comparison["key_set_equal"] or comparison["relative_l2"] > SMALL_LIMIT:
                errors.append(f"cross-MPI identity exceeds gate: incident_base/direct/{component}")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cross-MPI base component unreadable: {component}: {exc}")
    left_modes = {int(item["mode_index"]): item for item in left_record["modes"]["records"]}
    right_modes = {int(item["mode_index"]): item for item in right_record["modes"]["records"]}
    if set(left_modes) != set(right_modes):
        errors.append("cross-MPI nonzero mode inventory differs")
    for mode_index in sorted(set(left_modes) & set(right_modes)):
        for role in ("candidate", "oracle"):
            for component in ("0", "1"):
                try:
                    comparison = _cross_canonical(
                        left_root,
                        left_modes[mode_index]["components"][component][role]["canonical"],
                        right_root,
                        right_modes[mode_index]["components"][component][role]["canonical"],
                    )
                    key = f"mode{mode_index}_{role}_component{component}"
                    cross[key] = comparison
                    if not comparison["key_set_equal"] or comparison["relative_l2"] > SMALL_LIMIT:
                        errors.append(f"cross-MPI identity exceeds gate: mode {mode_index}/{role}/component {component}")
                except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(f"cross-MPI mode artifact unreadable: {mode_index}/{role}/{component}: {exc}")
            try:
                comparison = _cross_canonical(
                    left_root,
                    left_modes[mode_index]["candidate_total"]["canonical"],
                    right_root,
                    right_modes[mode_index]["candidate_total"]["canonical"],
                )
                cross[f"mode{mode_index}_candidate_total"] = comparison
                if not comparison["key_set_equal"] or comparison["relative_l2"] > SMALL_LIMIT:
                    errors.append(f"cross-MPI identity exceeds gate: mode {mode_index}/candidate total")
                comparison = _cross_canonical(
                    left_root,
                    left_modes[mode_index]["direct_total"]["canonical"],
                    right_root,
                    right_modes[mode_index]["direct_total"]["canonical"],
                )
                cross[f"mode{mode_index}_oracle_total"] = comparison
                if not comparison["key_set_equal"] or comparison["relative_l2"] > SMALL_LIMIT:
                    errors.append(f"cross-MPI identity exceeds gate: mode {mode_index}/oracle total")
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"cross-MPI mode total unreadable: {mode_index}: {exc}")
    return {
        "schema": "fullspace.full3d.dual-component-pair-check.v1",
        "status": "pass" if not errors else "fail",
        "failures": errors,
        "classification": "CURRENT_DUAL_ORACLE_PASS" if not errors else "CURRENT_DUAL_ORACLE_NOT_QUALIFIED",
        "individual": {"left": left, "right": right},
        "cross_mpi": cross,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check physical-dual component evidence")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path)
    group.add_argument("--pair", nargs=2, type=Path, metavar=("MPI1", "MPI2"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_record(args.record) if args.record is not None else check_pair(args.pair[0], args.pair[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
