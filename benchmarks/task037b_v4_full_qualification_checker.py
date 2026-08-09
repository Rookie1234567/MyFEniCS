"""Read-only V4 candidate evidence checker.

This module never imports a solver or starts a worker.  It verifies the
hash-bound candidate record, its small array payload, and canonical manifests;
comparisons to direct/Full3D authorities are kept offline and fail closed when
the authority does not carry the required numerical payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    MANIFEST_SCHEMA,
    read_canonical_manifest,
    read_canonical_packet_shard,
)
from benchmarks.task035c_channel_resource_checker import (
    _compare_to_significant_reference,
    _compare_full_hybrid,
    _load_significant_reference,
    _order_key,
)


ROOT = Path(__file__).resolve().parents[1]
ORDER_COMPLEX_FIELDS = (
    "total_projection",
    "incident_projection",
    "outgoing_amplitude",
    "outgoing_amplitude_at_boundary",
)
ORDER_REAL_FIELDS = (
    "power_ratio",
    "R",
    "T",
)
ARRAY_SHAPES = {
    "E_V_per_m": (5, 20, 40, 3),
    "H_A_per_m": (5, 20, 40, 3),
    "modal_amplitudes": (240,),
    "bottom_q": (40,),
    "top_q": (40,),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(value: Any, anchor: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    candidates = (
        (candidate,)
        if candidate.is_absolute()
        else (anchor.parent / candidate, ROOT / candidate)
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _complex_value(value: Any) -> complex | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(_finite(item) for item in value):
        return None
    return complex(float(value[0]), float(value[1]))


def _canonical_json_sha(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bind_file(
    *,
    label: str,
    value: Any,
    expected_sha256: Any,
    anchor: Path,
) -> tuple[dict[str, Any], Path | None]:
    path = _resolve(value, anchor)
    actual = _sha256(path) if path is not None else None
    passed = bool(
        path is not None
        and isinstance(expected_sha256, str)
        and actual == expected_sha256
    )
    return (
        {
            "path": value,
            "resolved": None if path is None else str(path),
            "expected_sha256": expected_sha256,
            "observed_sha256": actual,
            "pass": passed,
            "label": label,
        },
        path,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _validation(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("validation")
    return value if isinstance(value, Mapping) else {}


def _payload_telemetry(record: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("v4_telemetry", "h1_telemetry"):
        value = record.get(key)
        if isinstance(value, Mapping) and (
            "own_grid" in value or "canonical_export" in value
        ):
            return value
    return {}


def _order_map(value: Any) -> dict[tuple[str, int, int, str], Mapping[str, Any]] | None:
    if not isinstance(value, list) or len(value) != 80:
        return None
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            return None
        try:
            key = _order_key(row, "V4 order")
        except (TypeError, ValueError):
            return None
        if (
            key in result
            or not all(
                _complex_value(row.get(field)) is not None
                for field in ORDER_COMPLEX_FIELDS
            )
            or not all(_finite(row.get(field)) for field in ORDER_REAL_FIELDS)
        ):
            return None
        result[key] = row
    return result if len(result) == 80 else None


def _relative_payload(left: Any, right: Any) -> float | None:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        keys = set(left) | set(right)
        values = [_relative_payload(left.get(key), right.get(key)) for key in keys]
        return (
            None if any(value is None for value in values) else max(values, default=0.0)
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return None
        values = [_relative_payload(a, b) for a, b in zip(left, right)]
        return (
            None if any(value is None for value in values) else max(values, default=0.0)
        )
    left_complex = _complex_value(left)
    right_complex = _complex_value(right)
    if left_complex is not None and right_complex is not None:
        return abs(left_complex - right_complex) / max(
            abs(left_complex), abs(right_complex), 1.0e-15
        )
    if _finite(left) and _finite(right):
        return abs(float(left) - float(right)) / max(
            abs(float(left)), abs(float(right)), 1.0e-15
        )
    return 0.0 if left == right else None


def _payload_finite(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value) and all(_payload_finite(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and all(_payload_finite(item) for item in value)
    return _complex_value(value) is not None or _finite(value)


def _q_map(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for side in ("bottom", "top"):
        item = value.get(side)
        candidate = (
            item.get("q", item.get("values", item.get("amplitudes")))
            if isinstance(item, Mapping)
            else item
        )
        if not isinstance(candidate, list) or len(candidate) != 40:
            return None
        if not all(_complex_value(entry) is not None for entry in candidate):
            return None
        result[side] = candidate
    return result


def _relative_l2(left: Any, right: Any) -> float | None:
    if (
        not isinstance(left, list)
        or not isinstance(right, list)
        or len(left) != len(right)
    ):
        return None
    left_values = [_complex_value(value) for value in left]
    right_values = [_complex_value(value) for value in right]
    if any(value is None for value in left_values + right_values):
        return None
    left_array = np.asarray(left_values, dtype=np.complex128)
    right_array = np.asarray(right_values, dtype=np.complex128)
    return float(
        np.linalg.norm(left_array - right_array)
        / max(np.linalg.norm(left_array), np.linalg.norm(right_array), 1.0e-15)
    )


def _relative_array_l2(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.shape != right.shape:
        return None
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        return None
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-15)
    )


def _relative_magnitude_l2(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.shape != right.shape:
        return None
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        return None
    return float(
        np.linalg.norm(np.abs(left) - np.abs(right))
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-15)
    )


def _check_own_grid(
    record: Mapping[str, Any], anchor: Path
) -> tuple[bool, dict[str, Any]]:
    telemetry = _payload_telemetry(record)
    own_grid = telemetry.get("own_grid") if isinstance(telemetry, Mapping) else None
    if not isinstance(own_grid, Mapping) or not own_grid:
        return False, {"status": "missing"}
    binding, path = _bind_file(
        label="own_grid_npz",
        value=own_grid.get("path"),
        expected_sha256=own_grid.get("sha256"),
        anchor=anchor,
    )
    result: dict[str, Any] = {"binding": binding, "arrays": {}, "q_values": {}}
    if path is None or not binding["pass"]:
        return False, result
    try:
        with np.load(path, allow_pickle=False) as payload:
            for name, shape in ARRAY_SHAPES.items():
                array = np.asarray(payload[name])
                array_sha = hashlib.sha256(
                    np.ascontiguousarray(array).tobytes()
                ).hexdigest()
                descriptor = own_grid.get("arrays", {}).get(name, {})
                array_pass = bool(
                    array.shape == shape
                    and array.dtype == np.dtype("complex128")
                    and np.all(np.isfinite(array))
                    and descriptor.get("shape") == list(shape)
                    and descriptor.get("dtype") == "complex128"
                    and descriptor.get("sha256") == array_sha
                )
                result["arrays"][name] = {
                    "shape": list(array.shape),
                    "dtype": str(array.dtype),
                    "sha256": array_sha,
                    "pass": array_pass,
                }
                if name in ("bottom_q", "top_q"):
                    result["q_values"][name] = [
                        [float(value.real), float(value.imag)] for value in array
                    ]
    except (KeyError, OSError, ValueError):
        return False, result
    return bool(all(item["pass"] for item in result["arrays"].values())), result


def _check_canonical_exports(
    record: Mapping[str, Any], anchor: Path
) -> tuple[bool, dict[str, Any]]:
    telemetry = _payload_telemetry(record)
    exports = (
        telemetry.get("canonical_export") if isinstance(telemetry, Mapping) else None
    )
    if not isinstance(exports, Mapping) or not exports:
        return False, {"status": "missing"}
    results: dict[str, Any] = {}
    all_pass = True
    for side in ("bottom", "top"):
        roles = (
            exports.get(side, {}).get("roles")
            if isinstance(exports.get(side), Mapping)
            else None
        )
        for role in ("active_trace", "full_fe"):
            item = roles.get(role) if isinstance(roles, Mapping) else None
            binding, manifest_path = _bind_file(
                label=f"canonical_{side}_{role}_manifest",
                value=item.get("manifest") if isinstance(item, Mapping) else None,
                expected_sha256=item.get("manifest_sha256")
                if isinstance(item, Mapping)
                else None,
                anchor=anchor,
            )
            role_result: dict[str, Any] = {"binding": binding, "packets": 0}
            role_pass = bool(manifest_path is not None and binding["pass"])
            if role_pass:
                try:
                    manifest = read_canonical_manifest(
                        manifest_path, binding["observed_sha256"]
                    )
                    role_pass = bool(
                        manifest.get("schema_version") == MANIFEST_SCHEMA
                        and manifest.get("role") == f"{side}_{role}"
                        and manifest.get("dtype") == "complex128"
                    )
                    all_keys: list[Any] = []
                    packet_count = 0
                    for shard in manifest.get("per_rank_shards", []):
                        shard_path = manifest_path.parent / str(shard["filename"])
                        packets = read_canonical_packet_shard(
                            shard_path, shard.get("file_sha256")
                        )
                        keys = [
                            key
                            for key, value in packets
                            if np.isfinite(complex(value).real)
                            and np.isfinite(complex(value).imag)
                        ]
                        role_pass = bool(
                            role_pass
                            and len(keys) == len(packets)
                            and len(keys) == len(set(keys))
                            and int(shard.get("packet_count")) == len(packets)
                            and int(shard.get("local_duplicate_count", 0)) == 0
                        )
                        all_keys.extend(keys)
                        packet_count += len(packets)
                    role_pass = bool(
                        role_pass
                        and len(all_keys) == len(set(all_keys))
                        and int(manifest.get("global_summed_packet_count"))
                        == packet_count
                        and int(manifest.get("summed_local_duplicate_count", 0)) == 0
                        and item.get("pass") is True
                    )
                    role_result["packets"] = packet_count
                except (KeyError, OSError, ValueError, TypeError):
                    role_pass = False
            role_result["pass"] = role_pass
            results[f"{side}_{role}"] = role_result
            all_pass = bool(all_pass and role_pass)
    return all_pass, results


def _load_grid_arrays(record: Mapping[str, Any], anchor: Path) -> dict[str, Any]:
    telemetry = _payload_telemetry(record)
    own_grid = telemetry.get("own_grid")
    path = _resolve(
        own_grid.get("path") if isinstance(own_grid, Mapping) else None,
        anchor,
    )
    if path is None:
        raise FileNotFoundError("numeric grid payload is not bound")
    with np.load(path, allow_pickle=False) as payload:
        arrays: dict[str, Any] = {
            name: np.asarray(payload[name]) for name in ARRAY_SHAPES
        }
        for name in ("x_nm", "y_nm", "z_nm"):
            arrays[name] = np.asarray(payload[name]) if name in payload.files else None
        return arrays


def _load_canonical_values(
    record: Mapping[str, Any], anchor: Path
) -> dict[str, dict[str, complex]]:
    telemetry = _payload_telemetry(record)
    exports = telemetry.get("canonical_export")
    if not isinstance(exports, Mapping):
        raise FileNotFoundError("canonical payload is not bound")
    values: dict[str, dict[str, complex]] = {}
    for side in ("bottom", "top"):
        roles = exports.get(side, {}).get("roles")
        if not isinstance(roles, Mapping):
            raise ValueError("canonical roles are incomplete")
        for role in ("active_trace", "full_fe"):
            item = roles.get(role)
            if not isinstance(item, Mapping):
                raise ValueError("canonical role is incomplete")
            manifest_path = _resolve(item.get("manifest"), anchor)
            if manifest_path is None:
                raise FileNotFoundError("canonical manifest is missing")
            manifest = read_canonical_manifest(
                manifest_path, item.get("manifest_sha256")
            )
            role_values: dict[str, complex] = {}
            for shard in manifest.get("per_rank_shards", []):
                shard_path = manifest_path.parent / str(shard["filename"])
                packets = read_canonical_packet_shard(
                    shard_path, shard.get("file_sha256")
                )
                for key, value in packets:
                    key_label = json.dumps(key, sort_keys=True, separators=(",", ":"))
                    if key_label in role_values:
                        raise ValueError("canonical packet key is duplicated")
                    role_values[key_label] = complex(value)
            values[f"{side}_{role}"] = role_values
    return values


def _authority_payload_state(
    authority: Mapping[str, Any] | None,
    anchor: Path,
) -> dict[str, Any]:
    if not isinstance(authority, Mapping):
        return {"status": "not_run_authority_payload_gap", "payload_complete": False}
    try:
        grid_pass, grid = _check_own_grid(authority, anchor)
        canonical_pass, canonical = _check_canonical_exports(authority, anchor)
        modal_payload = bool(
            grid_pass
            and grid.get("arrays", {}).get("modal_amplitudes", {}).get("pass") is True
        )
        field_payload = bool(
            grid_pass
            and all(
                grid.get("arrays", {}).get(name, {}).get("pass") is True
                for name in ("E_V_per_m", "H_A_per_m")
            )
        )
        payload_complete = bool(modal_payload and field_payload and canonical_pass)
        return {
            "status": "available"
            if payload_complete
            else "not_run_authority_payload_gap",
            "payload_complete": payload_complete,
            "modal_numeric_payload": modal_payload,
            "field_numeric_payload": field_payload,
            "canonical_numeric_payload": canonical_pass,
            "grid": grid,
            "canonical": canonical,
        }
    except (OSError, KeyError, TypeError, ValueError):
        return {
            "status": "not_run_authority_payload_gap",
            "payload_complete": False,
            "modal_numeric_payload": False,
            "field_numeric_payload": False,
            "canonical_numeric_payload": False,
        }


def _compare_order_maps(
    left: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    right: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    keys_match = set(left) == set(right) and len(left) == 80 and len(right) == 80
    for key in sorted(set(left) & set(right)):
        left_row = left[key]
        right_row = right[key]
        left_power = float(left_row["power_ratio"])
        right_power = float(right_row["power_ratio"])
        left_amplitude = _complex_value(left_row["outgoing_amplitude_at_boundary"])
        right_amplitude = _complex_value(right_row["outgoing_amplitude_at_boundary"])
        if left_amplitude is None or right_amplitude is None:
            continue
        power_error = abs(left_power - right_power)
        power_relative = power_error / max(abs(left_power), abs(right_power), 1.0e-8)
        amplitude_error = abs(left_amplitude - right_amplitude)
        amplitude_relative = amplitude_error / max(
            abs(left_amplitude), abs(right_amplitude), 1.0e-15
        )
        rows.append(
            {
                "key": list(key),
                "power_absolute_error": power_error,
                "power_relative_error": power_relative,
                "boundary_amplitude_absolute_error": amplitude_error,
                "boundary_amplitude_relative_error": amplitude_relative,
                "diagnostic_pass": bool(
                    power_relative <= 1.0e-3 and amplitude_relative <= 1.0e-3
                ),
            }
        )
    significant = (
        _compare_full_hybrid(left, right)
        if keys_match
        else {"pass": False, "significant_channel_count": None, "channels": []}
    )
    coverage_pass = bool(keys_match and len(rows) == 80)
    return {
        "status": "pass" if coverage_pass and significant["pass"] else "fail",
        "count": len(rows),
        "all_order_coverage": coverage_pass,
        "key_and_finite_coverage_pass": coverage_pass,
        "numeric_pass": bool(significant["pass"]),
        "significant_count": significant.get("significant_channel_count"),
        "below_floor_count": (
            80 - int(significant["significant_channel_count"])
            if significant.get("significant_channel_count") is not None
            else None
        ),
        "significant_numeric_comparison": significant,
        "max_power_relative_error": max(
            (row["power_relative_error"] for row in rows), default=None
        ),
        "max_boundary_amplitude_relative_error": max(
            (row["boundary_amplitude_relative_error"] for row in rows),
            default=None,
        ),
        "rows": rows,
    }


def _validation_observables(record: Mapping[str, Any]) -> dict[str, Any]:
    validation = _validation(record)
    port = validation.get("port_power")
    if not isinstance(port, Mapping):
        port = {}
    volume = validation.get("A_volume")
    if not isinstance(volume, Mapping):
        reconstruction = record.get("physical_field_reconstruction")
        volume = (
            reconstruction.get("volume_absorption")
            if isinstance(reconstruction, Mapping)
            else {}
        )
    energy = validation.get("energy_closure")
    if not isinstance(energy, Mapping):
        energy = {}
    values = {
        "R": port.get("R_total", validation.get("R")),
        "T": port.get("T_total", validation.get("T")),
        "A": port.get("A_balance", validation.get("A")),
        "A_volume_total": volume.get("A_volume_total"),
        "local_regions": volume.get("local_regions"),
        "middle_modal_region": volume.get("middle_modal_region"),
        "R_plus_T_plus_A_volume": volume.get(
            "R_plus_T_plus_A_volume",
            energy.get("R_plus_T_plus_A_volume"),
        ),
        "energy_closure_error": volume.get(
            "energy_closure_error", energy.get("closure_error")
        ),
    }
    return values


def _significant_reference_order_map(
    reference: Mapping[str, Any],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    channels = reference.get("channels")
    if not isinstance(channels, Mapping) or len(channels) != 12:
        raise ValueError("significant reference must contain 12 channels")
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for key, item in channels.items():
        if not isinstance(item, Mapping):
            raise ValueError("significant reference channel is not an object")
        identity = item.get("analytic_identity")
        center = item.get("reference_center")
        if not isinstance(identity, Mapping) or not isinstance(center, Mapping):
            raise ValueError("significant reference channel payload is incomplete")
        order_key = _order_key(identity, "significant reference analytic identity")
        if order_key != key or order_key in result:
            raise ValueError("significant reference channel identity is duplicated")
        amplitude = center.get("complex_amplitude")
        if _complex_value(amplitude) is None or not _finite(center.get("power")):
            raise ValueError("significant reference channel payload is nonfinite")
        mapped = dict(identity)
        mapped["outgoing_amplitude_at_boundary"] = amplitude
        mapped["power_ratio"] = center["power"]
        result[order_key] = mapped
    if len(result) != 12:
        raise ValueError("significant reference channel identity is incomplete")
    return result


def check_v4_evidence(
    summary_path: Path | str,
    *,
    authorities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check one V4 summary without executing or mutating any candidate data."""

    started = time.perf_counter()
    summary_path = Path(summary_path).resolve()
    result: dict[str, Any] = {
        "schema": "task037b.v4-offline-check.v1",
        "summary_path": str(summary_path),
        "summary_sha256": _sha256(summary_path) if summary_path.is_file() else None,
        "candidate_evidence_pass": False,
        "evidence_integrity_pass": False,
        "authority_payload_gap": False,
        "pass": False,
        "failures": [],
    }
    summary = _load_json(summary_path) if summary_path.is_file() else None
    if summary is None:
        result["failures"].append("summary_unreadable")
        return result
    if summary.get("schema_version") != "task033.memory-watchdog.v2":
        result["failures"].append("summary_schema")
    artifacts = summary.get("v4_artifacts", {})
    if not isinstance(artifacts, Mapping):
        artifacts = {}
    bindings: dict[str, Any] = {}
    raw_path = None
    for name, path_key, sha_key in (
        ("solver", "solver_record_path", "solver_record_sha256"),
        ("timeline", "timeline_path", "timeline_sha256"),
        ("stdout", "stdout_path", "stdout_sha256"),
        ("stages", "stages_path", "stages_sha256"),
    ):
        binding, path = _bind_file(
            label=name,
            value=artifacts.get(path_key),
            expected_sha256=artifacts.get(sha_key),
            anchor=summary_path,
        )
        bindings[name] = binding
        if name == "solver":
            raw_path = path
    history = None
    record = (
        _load_json(raw_path)
        if raw_path is not None and bindings["solver"]["pass"]
        else None
    )
    if record is None:
        result["failures"].append("solver_record_binding")
    else:
        history = record.get("v4_telemetry", {}).get("history")
        history_sha = (
            _canonical_json_sha(history) if isinstance(history, list) else None
        )
        bindings["history"] = {
            "expected_sha256": artifacts.get("history_sha256"),
            "observed_sha256": history_sha,
            "pass": bool(
                history_sha and history_sha == artifacts.get("history_sha256")
            ),
        }
    result["artifacts"] = bindings
    own_grid_pass, own_grid = _check_own_grid(record or {}, summary_path)
    canonical_pass, canonical = _check_canonical_exports(record or {}, summary_path)
    result["own_grid"] = own_grid
    result["canonical"] = canonical
    qualification = (
        record.get("qualification", {}) if isinstance(record, Mapping) else {}
    )
    validation = _validation(record or {})
    candidate_gate = bool(
        isinstance(record, Mapping)
        and qualification.get("numerical_pass") is True
        and qualification.get("recovery_pass") is True
        and qualification.get("own_physics_pass") is True
        and qualification.get("canonical_pass") is True
        and qualification.get("physics_pass") is True
        and validation.get("official_record") == "candidate_measured_not_official"
        and validation.get("12_plus_12") == "not_run"
        and validation.get("Full3D") == "not_run"
        and validation.get("full3d_comparison") == "not_run"
    )
    numerical_pass = bool(
        isinstance(record, Mapping) and qualification.get("numerical_pass") is True
    )
    official_not_run = bool(
        isinstance(validation, Mapping)
        and validation.get("official_record") == "not_run"
        and all(
            validation.get(key) == "not_run"
            for key in (
                "R",
                "T",
                "A",
                "A_volume",
                "orders",
                "external_diffraction_orders",
                "field",
                "candidate_sample_grid",
                "canonical_export",
                "12_plus_12",
                "Full3D",
                "full3d_comparison",
            )
        )
    )
    telemetry = record.get("v4_telemetry", {}) if isinstance(record, Mapping) else {}
    negative_boundary = bool(
        not numerical_pass
        and official_not_run
        and isinstance(telemetry, Mapping)
        and telemetry.get("own_grid") in (None, {})
        and telemetry.get("canonical_export") in (None, {})
    )
    post_linear_negative = bool(
        numerical_pass
        and official_not_run
        and summary.get("v4_contract_pass") is True
        and qualification.get("recovery_phase")
        in {
            "external_auxiliary",
            "full_fe",
            "own_physics",
            "canonical",
            "own_physics_and_canonical",
        }
        and (
            qualification.get("recovery_pass") is False
            or qualification.get("own_physics_pass") is False
            or qualification.get("canonical_pass") is False
            or qualification.get("physics_pass") is False
        )
        and (not telemetry.get("own_grid") or own_grid_pass)
        and (not telemetry.get("canonical_export") or canonical_pass)
    )
    base_evidence = bool(
        summary.get("v4_contract_pass") is True
        and bindings.get("solver", {}).get("pass") is True
        and bindings.get("timeline", {}).get("pass") is True
        and bindings.get("stdout", {}).get("pass") is True
        and bindings.get("stages", {}).get("pass") is True
        and bindings.get("history", {}).get("pass") is True
    )
    candidate_evidence_pass = bool(
        base_evidence
        and (
            (numerical_pass and own_grid_pass and canonical_pass and candidate_gate)
            or negative_boundary
            or post_linear_negative
        )
    )
    result["candidate_evidence_pass"] = candidate_evidence_pass
    result["candidate_gate"] = candidate_gate
    result["recognized_controlled_negative"] = bool(
        negative_boundary or post_linear_negative
    )
    authority_specs = (
        authorities if authorities is not None else summary.get("v4_authorities", {})
    )
    authority_records: dict[str, Any] = {}
    authority_bindings: dict[str, Any] = {}
    for name in ("h1_direct", "h1_summary", "full3d", "significant_reference"):
        spec = (
            authority_specs.get(name) if isinstance(authority_specs, Mapping) else None
        )
        binding, path = _bind_file(
            label=name,
            value=spec.get("path") if isinstance(spec, Mapping) else None,
            expected_sha256=spec.get("sha256") if isinstance(spec, Mapping) else None,
            anchor=summary_path,
        )
        authority_bindings[name] = binding
        authority_records[name] = (
            _load_json(path) if path is not None and binding["pass"] else None
        )
    h1_state = _authority_payload_state(
        authority_records.get("h1_direct"), summary_path
    )
    authority_payload_gap = h1_state["payload_complete"] is False
    result["authorities"] = {
        "bindings": authority_bindings,
        "h1_payload": h1_state,
    }
    result["authority_payload_gap"] = authority_payload_gap
    authority_bindings_pass = bool(
        all(item.get("pass") is True for item in authority_bindings.values())
    )
    result["authority_bindings_pass"] = authority_bindings_pass
    direct_status = (
        "not_run_authority_payload_gap"
        if authority_payload_gap
        else "not_run_dependency_gate"
    )
    comparisons: dict[str, Any] = {
        "q": {"status": "not_run_authority_payload_gap"},
        "orders": {"status": "not_run_authority_payload_gap"},
        "significant_reference": {"status": "not_run"},
        "twelve_plus_twelve": {"status": "not_run"},
        "energy": {"status": "not_run_authority_payload_gap"},
        "modal": {"status": direct_status},
        "canonical": {"status": direct_status},
        "selected_fields": {"status": direct_status},
        "direct_hybrid_vs_full3d": {"status": "not_run_dependency_gate"},
        "iterative_vs_full3d": {
            "status": "not_run_dependency_gate",
            "dimensions": {
                "twelve_plus_twelve_powers_amplitudes": {
                    "status": "not_run_dependency_gate",
                    "source": "significant_reference",
                },
                "modal": {
                    "status": "not_available",
                    "reason": "pinned Full3D authority has no numeric modal array",
                },
                "canonical": {
                    "status": "not_available",
                    "reason": "pinned Full3D authority has no numeric canonical arrays",
                },
                "selected_interface_fields": {
                    "status": "not_available",
                    "reason": "pinned Full3D authority has no selected interface E/H arrays",
                },
                "selected_middle_fields": {
                    "status": "not_available",
                    "reason": "pinned Full3D authority has no selected middle E/H arrays",
                },
                "direct_hybrid_vs_frozen_full3d": {
                    "status": "not_run_dependency_gate",
                    "source": "significant_reference",
                },
            },
        },
        "offline_resource": {"status": "not_run"},
    }
    comparison_ready = bool(
        candidate_evidence_pass and candidate_gate and authority_bindings_pass
    )
    if not comparison_ready:
        for name in (
            "q",
            "orders",
            "significant_reference",
            "twelve_plus_twelve",
            "energy",
        ):
            comparisons[name] = {"status": "not_run_dependency_gate"}
    h1 = authority_records.get("h1_direct")
    if comparison_ready and isinstance(h1, Mapping) and isinstance(record, Mapping):
        candidate_validation = _validation(record)
        h1_validation = _validation(h1)
        candidate_q = _q_map(
            {
                "bottom": own_grid.get("q_values", {}).get("bottom_q"),
                "top": own_grid.get("q_values", {}).get("top_q"),
            }
        )
        candidate_arrays = _load_grid_arrays(record, summary_path)
        h1_grid_pass = bool(
            isinstance(h1_state.get("grid"), Mapping)
            and all(
                h1_state["grid"].get("arrays", {}).get(name, {}).get("pass") is True
                for name in ARRAY_SHAPES
            )
        )
        h1_arrays = _load_grid_arrays(h1, summary_path) if h1_grid_pass else None
        if h1_arrays is not None:
            h1_q = _q_map(
                {
                    "bottom": [
                        [float(value.real), float(value.imag)]
                        for value in h1_arrays["bottom_q"]
                    ],
                    "top": [
                        [float(value.real), float(value.imag)]
                        for value in h1_arrays["top_q"]
                    ],
                }
            )
        else:
            h1_q = _q_map(h1_validation.get("external_auxiliary_amplitudes"))
        if candidate_q is not None and h1_q is not None:
            q_rows = {}
            for side in ("bottom", "top"):
                q_error = _relative_l2(candidate_q[side], h1_q[side])
                q_rows[side] = {
                    "relative_l2_error": q_error,
                    "pass": q_error is not None and q_error <= 1.0e-5,
                }
            comparisons["q"] = {
                "status": "pass"
                if all(row["pass"] for row in q_rows.values())
                else "fail",
                "sides": q_rows,
            }
        candidate_orders = _order_map(
            candidate_validation.get("external_diffraction_orders")
        )
        h1_orders = _order_map(h1_validation.get("external_diffraction_orders"))
        if candidate_orders is not None and h1_orders is not None:
            comparisons["orders"] = _compare_order_maps(h1_orders, candidate_orders)
            twelve_plus_twelve = comparisons["orders"]["significant_numeric_comparison"]
            comparisons["twelve_plus_twelve"] = {
                "status": "pass" if twelve_plus_twelve.get("pass") is True else "fail",
                "result": twelve_plus_twelve,
            }
        if h1_arrays is None or not h1_state.get("modal_numeric_payload"):
            comparisons["modal"] = {
                "status": "not_run_authority_payload_gap",
                "qualification_pass": False,
            }
        else:
            modal_error = _relative_array_l2(
                candidate_arrays["modal_amplitudes"],
                h1_arrays["modal_amplitudes"],
            )
            comparisons["modal"] = {
                "status": "diagnostic_not_comparable_independent_qep_gauge",
                "diagnostic_only": True,
                "relative_l2_error": modal_error,
                "magnitude_relative_l2": _relative_magnitude_l2(
                    candidate_arrays["modal_amplitudes"],
                    h1_arrays["modal_amplitudes"],
                ),
                "qualification_pass": False,
            }
        selected_parts = {
            "bottom_interface": (0, slice(None), slice(None), slice(0, 2)),
            "top_interface": (4, slice(None), slice(None), slice(0, 2)),
            "middle": (slice(1, 4), slice(None), slice(None), slice(None)),
        }
        if h1_arrays is None or not h1_state.get("field_numeric_payload"):
            comparisons["selected_fields"] = {"status": "not_run_authority_payload_gap"}
        else:
            coordinate_alignment = {
                name: bool(
                    candidate_arrays.get(name) is not None
                    and h1_arrays.get(name) is not None
                    and candidate_arrays[name].shape == h1_arrays[name].shape
                    and np.array_equal(candidate_arrays[name], h1_arrays[name])
                )
                for name in ("x_nm", "y_nm", "z_nm")
            }
            coordinate_alignment_pass = all(coordinate_alignment.values())
            selected_errors: dict[str, Any] = {}
            for part, selector in selected_parts.items():
                fields: dict[str, Any] = {}
                for name in ("E_V_per_m", "H_A_per_m"):
                    error = _relative_array_l2(
                        candidate_arrays[name][selector], h1_arrays[name][selector]
                    )
                    fields[name] = {
                        "relative_l2_error": error,
                        "pass": error is not None and error <= 5.0e-3,
                    }
                selected_errors[part] = {
                    "fields": fields,
                    "pass": all(item["pass"] for item in fields.values()),
                }
            comparisons["selected_fields"] = {
                "status": "pass"
                if coordinate_alignment_pass
                and all(item["pass"] for item in selected_errors.values())
                else "fail",
                "threshold": 5.0e-3,
                "coordinate_alignment_pass": coordinate_alignment_pass,
                "coordinate_alignment": coordinate_alignment,
                "parts": selected_errors,
            }
        if comparisons["modal"].get("diagnostic_only") is True:
            comparisons["modal"]["qualification_pass"] = bool(
                comparisons["selected_fields"].get("status") == "pass"
            )
        if not h1_state.get("canonical_numeric_payload"):
            comparisons["canonical"] = {"status": "not_run_authority_payload_gap"}
        else:
            candidate_canonical = _load_canonical_values(record, summary_path)
            h1_canonical = _load_canonical_values(h1, summary_path)
            canonical_rows: dict[str, Any] = {}
            for role in sorted(set(candidate_canonical) | set(h1_canonical)):
                left = candidate_canonical.get(role, {})
                right = h1_canonical.get(role, {})
                common_keys = sorted(set(left) & set(right))
                keys_match = set(left) == set(right) and bool(left)
                left_values = np.asarray([left[key] for key in common_keys])
                right_values = np.asarray([right[key] for key in common_keys])
                relative_l2 = _relative_array_l2(left_values, right_values)
                diagnostic_rows = [
                    {
                        "key": key,
                        "absolute_difference": abs(left[key] - right[key]),
                        "relative_difference": abs(left[key] - right[key])
                        / max(abs(left[key]), abs(right[key]), 1.0e-15),
                    }
                    for key in common_keys
                ]
                max_absolute = max(
                    diagnostic_rows,
                    key=lambda row: row["absolute_difference"],
                    default=None,
                )
                max_relative = max(
                    diagnostic_rows,
                    key=lambda row: row["relative_difference"],
                    default=None,
                )
                canonical_rows[role] = {
                    "key_coverage_pass": keys_match,
                    "relative_l2_error": relative_l2,
                    "max_absolute_difference": (
                        max_absolute["absolute_difference"]
                        if max_absolute is not None
                        else None
                    ),
                    "max_absolute_key": (
                        max_absolute["key"] if max_absolute is not None else None
                    ),
                    "max_relative_difference": (
                        max_relative["relative_difference"]
                        if max_relative is not None
                        else None
                    ),
                    "max_relative_key": (
                        max_relative["key"] if max_relative is not None else None
                    ),
                    "pass": bool(
                        keys_match and relative_l2 is not None and relative_l2 <= 1.0e-5
                    ),
                }
            comparisons["canonical"] = {
                "status": "pass"
                if all(item["pass"] for item in canonical_rows.values())
                else "fail",
                "relative_l2_threshold": 1.0e-5,
                "roles": canonical_rows,
            }
        candidate_values = _validation_observables(record)
        h1_values = _validation_observables(h1)
        required_energy = (
            "R",
            "T",
            "A",
            "A_volume_total",
            "local_regions",
            "middle_modal_region",
            "R_plus_T_plus_A_volume",
            "energy_closure_error",
        )
        missing_candidate = [
            key
            for key in required_energy
            if candidate_values.get(key) is None
            or not _payload_finite(candidate_values.get(key))
        ]
        missing_authority = [
            key
            for key in required_energy
            if h1_values.get(key) is None or not _payload_finite(h1_values.get(key))
        ]
        if missing_candidate or missing_authority:
            comparisons["energy"] = {
                "status": (
                    "not_run_authority_payload_gap" if missing_authority else "fail"
                ),
                "missing_candidate": missing_candidate,
                "missing_authority": missing_authority,
            }
        else:
            energy_rows: dict[str, Any] = {}
            for key in ("R", "T", "A", "A_volume_total"):
                error = abs(float(candidate_values[key]) - float(h1_values[key]))
                energy_rows[key] = {
                    "absolute_error": error,
                    "pass": error <= 1.0e-5,
                }
            for key in ("local_regions", "middle_modal_region"):
                error = _relative_payload(candidate_values[key], h1_values[key])
                energy_rows[key] = {
                    "relative_error": error,
                    "pass": error is not None and error <= 1.0e-5,
                }
            closure_difference = abs(
                float(candidate_values["R_plus_T_plus_A_volume"])
                - float(h1_values["R_plus_T_plus_A_volume"])
            )
            energy_rows["R_plus_T_plus_A_volume"] = {
                "absolute_difference": closure_difference,
                "pass": closure_difference <= 1.0e-5,
            }
            candidate_closure = float(candidate_values["energy_closure_error"])
            authority_closure = float(h1_values["energy_closure_error"])
            closure_error_difference = abs(candidate_closure - authority_closure)
            energy_rows["energy_closure_error"] = {
                "candidate_absolute": abs(candidate_closure),
                "authority_absolute": abs(authority_closure),
                "absolute_difference": closure_error_difference,
                "pass": bool(
                    abs(candidate_closure) <= 1.0e-5
                    and abs(authority_closure) <= 1.0e-5
                    and closure_error_difference <= 1.0e-5
                ),
            }
            comparisons["energy"] = {
                "status": "pass"
                if all(item["pass"] for item in energy_rows.values())
                else "fail",
                "fields": energy_rows,
            }
        if candidate_q is None or h1_q is None:
            comparisons["q"] = {"status": "not_run_authority_payload_gap"}
        if candidate_orders is None or h1_orders is None:
            comparisons["orders"] = {"status": "not_run_authority_payload_gap"}
            comparisons["twelve_plus_twelve"] = {"status": "not_run_dependency_gate"}
    reference_spec = (
        authority_specs.get("significant_reference", {})
        if isinstance(authority_specs, Mapping)
        else {}
    )
    if (
        comparison_ready
        and not authority_payload_gap
        and isinstance(h1, Mapping)
        and isinstance(record, Mapping)
    ):
        try:
            reference_path = _resolve(reference_spec.get("path"), summary_path)
            reference_sha = reference_spec.get("sha256")
            if reference_path is None or not isinstance(reference_sha, str):
                raise ValueError("significant reference binding is incomplete")
            reference = _load_significant_reference(reference_path, reference_sha)
            frozen_orders = _significant_reference_order_map(reference)
            direct_orders = _order_map(
                _validation(h1).get("external_diffraction_orders")
            )
            iterative_orders = _order_map(
                _validation(record).get("external_diffraction_orders")
            )
            if direct_orders is None or iterative_orders is None:
                raise ValueError("significant comparison order payload is incomplete")
            iterative_reference = _compare_to_significant_reference(
                frozen_orders, iterative_orders, reference
            )
            direct_reference = _compare_to_significant_reference(
                frozen_orders, direct_orders, reference
            )
            comparisons["significant_reference"] = {
                "status": (
                    "pass" if iterative_reference.get("pass") is True else "fail"
                ),
                "source": "hash_bound_significant_reference",
                "result": iterative_reference,
            }
            comparisons["direct_hybrid_vs_full3d"] = {
                "status": ("pass" if direct_reference.get("pass") is True else "fail"),
                "source": "hash_bound_significant_reference",
                "result": direct_reference,
            }
            comparisons["iterative_vs_full3d"]["status"] = (
                "pass" if iterative_reference.get("pass") is True else "fail"
            )
            comparisons["iterative_vs_full3d"]["dimensions"][
                "twelve_plus_twelve_powers_amplitudes"
            ] = {
                "status": (
                    "pass" if iterative_reference.get("pass") is True else "fail"
                ),
                "source": "hash_bound_significant_reference",
                "result": iterative_reference,
            }
            comparisons["iterative_vs_full3d"]["dimensions"][
                "direct_hybrid_vs_frozen_full3d"
            ] = {
                "status": ("pass" if direct_reference.get("pass") is True else "fail"),
                "source": "hash_bound_significant_reference",
                "result": direct_reference,
            }
        except (OSError, TypeError, ValueError, KeyError):
            comparisons["significant_reference"] = {"status": "fail"}
            comparisons["direct_hybrid_vs_full3d"] = {"status": "fail"}
            comparisons["iterative_vs_full3d"]["status"] = "fail"
            comparisons["iterative_vs_full3d"]["dimensions"][
                "twelve_plus_twelve_powers_amplitudes"
            ] = {"status": "fail", "source": "hash_bound_significant_reference"}
            comparisons["iterative_vs_full3d"]["dimensions"][
                "direct_hybrid_vs_frozen_full3d"
            ] = {"status": "fail", "source": "hash_bound_significant_reference"}
    else:
        comparisons["significant_reference"] = {"status": "not_run_dependency_gate"}
        comparisons["direct_hybrid_vs_full3d"] = {"status": "not_run_dependency_gate"}
        comparisons["iterative_vs_full3d"]["dimensions"][
            "twelve_plus_twelve_powers_amplitudes"
        ] = {"status": "not_run_dependency_gate", "source": "significant_reference"}
        comparisons["iterative_vs_full3d"]["dimensions"][
            "direct_hybrid_vs_frozen_full3d"
        ] = {"status": "not_run_dependency_gate", "source": "significant_reference"}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    comparisons["offline_resource"] = {
        "status": "measured",
        "wall_seconds": float(time.perf_counter() - started),
        "ru_maxrss_peak_mib": float(usage.ru_maxrss) / 1024.0,
        "ru_maxrss_semantics": "historical checker-process peak on Linux",
        "online_rss_included": False,
    }
    result["comparisons"] = comparisons
    result["fail_closed"] = bool(
        not candidate_evidence_pass
        or not authority_bindings_pass
        or any(
            item.get("status") == "fail"
            for item in comparisons.values()
            if isinstance(item, Mapping)
        )
    )
    result["evidence_integrity_pass"] = bool(
        candidate_evidence_pass and authority_bindings_pass
    )
    result["pass"] = bool(
        candidate_evidence_pass
        and not authority_payload_gap
        and comparisons["modal"].get("qualification_pass") is True
        and comparisons["iterative_vs_full3d"].get("status") == "pass"
        and comparisons["direct_hybrid_vs_full3d"].get("status") == "pass"
        and all(
            item.get("status")
            in {"pass", "not_run", "diagnostic_not_comparable_independent_qep_gauge"}
            for item in comparisons.values()
            if isinstance(item, Mapping)
            and "status" in item
            and item is not comparisons["iterative_vs_full3d"]
            and item is not comparisons["offline_resource"]
        )
    )
    if not candidate_evidence_pass:
        result["failures"].append("candidate_evidence_contract")
    if authority_payload_gap:
        result["failures"].append("h1_authority_payload_gap")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Task037b V4 evidence checker"
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--h1-authority", type=Path)
    parser.add_argument("--h1-sha256")
    parser.add_argument("--h1-summary", type=Path)
    parser.add_argument("--h1-summary-sha256")
    parser.add_argument("--full3d-authority", type=Path)
    parser.add_argument("--full3d-sha256")
    parser.add_argument("--significant-reference", type=Path)
    parser.add_argument("--significant-reference-sha256")
    args = parser.parse_args(argv)
    authorities = {
        "h1_direct": {"path": str(args.h1_authority), "sha256": args.h1_sha256},
        "h1_summary": {"path": str(args.h1_summary), "sha256": args.h1_summary_sha256},
        "full3d": {"path": str(args.full3d_authority), "sha256": args.full3d_sha256},
        "significant_reference": {
            "path": str(args.significant_reference),
            "sha256": args.significant_reference_sha256,
        },
    }
    result = check_v4_evidence(args.summary, authorities=authorities)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["evidence_integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
