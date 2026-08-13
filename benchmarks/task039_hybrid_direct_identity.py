"""Offline Task39 Hybrid-direct own and comparison authority checks.

This checker only reads a completed run directory and reviewed Full3D evidence.
It never imports a solver runner, launches MPI, or writes into a run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.canonical_vector_artifacts import read_canonical_manifest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_MODEL_ID = re.compile(r"^task039_5nm_hybrid_direct_m(120|240|480|960)$")
_PLANES = (10.0, 30.0, 60.0, 90.0, 110.0)
_PAYLOAD_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "modal_amplitudes",
    "bottom_q",
    "top_q",
)
_CANONICAL_ROLES = ("active_trace", "full_fe")
_BLOCKED_BY = "T4_5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10"


class IdentityCheckError(ValueError):
    """An expected evidence-contract failure."""


def _fail(message: str) -> None:
    raise IdentityCheckError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityCheckError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        _fail(f"JSON artifact is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise IdentityCheckError(f"cannot hash artifact: {path}") from exc


def _artifact(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"missing {label}: {path}")
    return {"label": label, "path": str(path), "sha256": _sha256(path)}


def _resolve(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"artifact path is not a non-empty string: {value!r}")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    for path in (base / candidate, _REPO_ROOT / candidate):
        if path.exists():
            return path
    return base / candidate


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} is not a finite scalar: {value!r}")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label} is not finite: {value!r}")
    return result


def _complex_pair(value: Any, label: str) -> complex:
    if isinstance(value, list) and len(value) == 2:
        return complex(
            _finite(value[0], f"{label}.real"),
            _finite(value[1], f"{label}.imag"),
        )
    _fail(f"{label} is not a JSON complex pair")


def _mode_key(value: Any, label: str) -> tuple[str, int, int, str]:
    if isinstance(value, Mapping):
        side, m, n, polarization = (
            value.get(k) for k in ("side", "m", "n", "polarization")
        )
    elif isinstance(value, list) and len(value) == 4:
        side, m, n, polarization = value
    else:
        _fail(f"{label} is not a mode-key object or four-item list")
    if not isinstance(side, str) or not isinstance(polarization, str):
        _fail(f"{label} has invalid side or polarization")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in (m, n)):
        _fail(f"{label} has non-integer m/n")
    return side, m, n, polarization


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _key_sha(keys: Sequence[tuple[str, int, int, str]]) -> str:
    return hashlib.sha256(
        _canonical_bytes([list(key) for key in sorted(keys)])
    ).hexdigest()


def _parse_inventory(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("keys"), list):
        _fail(f"{label} external_mode_inventory is missing")
    keys = tuple(
        _mode_key(item, f"{label}.keys[{index}]")
        for index, item in enumerate(value["keys"])
    )
    if len(keys) != 604 or len(set(keys)) != 604:
        _fail(f"{label} external inventory must contain 604 unique keys")
    return {
        "value": dict(value),
        "keys": keys,
        "count": len(keys),
        "canonical_sha256": hashlib.sha256(_canonical_bytes(value)).hexdigest(),
        "key_sha256": _key_sha(keys),
        "counts": value.get("counts"),
    }


def _parse_orders(
    rows: Any, label: str
) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) != 604:
        _fail(f"{label} must contain 604 diffraction-order rows")
    result: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(f"{label}[{index}] is not an object")
        key = _mode_key(row, f"{label}[{index}]")
        if key in result:
            _fail(f"{label} contains duplicate key {key!r}")
        power = _finite(row.get("power_ratio"), f"{label}[{index}].power_ratio")
        if power < 0:
            _fail(f"{label}[{index}].power_ratio is negative")
        result[key] = {
            "power_ratio": power,
            "outgoing_amplitude": _complex_pair(
                row.get("outgoing_amplitude"), f"{label}[{index}].outgoing_amplitude"
            ),
        }
    return result


def _relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-15)


def _complex_relative(left: complex, right: complex) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-15)


def _array_relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
    )


def _load_payload(
    numeric_dir: Path, numeric: Mapping[str, Any], inventory: Mapping[str, Any]
) -> dict[str, Any]:
    physical = numeric.get("physical_field_reconstruction")
    descriptor = (
        physical.get("task039_direct_payload")
        if isinstance(physical, Mapping)
        else None
    )
    if not isinstance(descriptor, Mapping):
        _fail("Task39 direct comparison payload descriptor is missing")
    if descriptor.get("schema") != "task039.hybrid-direct-payload.v1":
        _fail("Task39 direct comparison payload schema is invalid")
    if descriptor.get("keys") != list(_PAYLOAD_KEYS):
        _fail("Task39 direct comparison payload keys are invalid")
    relative = Path(descriptor.get("path", ""))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
        _fail("Task39 direct comparison payload path escapes numerical_output")
    path = (numeric_dir / relative).resolve()
    if path.parent != numeric_dir.resolve():
        _fail("Task39 direct comparison payload path is not output-local")
    artifact = _artifact(path, "task039_direct_payload.npz")
    if (
        descriptor.get("sha256") != artifact["sha256"]
        or descriptor.get("bytes") != path.stat().st_size
    ):
        _fail("Task39 direct comparison payload file identity mismatches")
    counts = inventory.get("counts")
    side_counts = counts.get("per_side") if isinstance(counts, Mapping) else None
    hybrid = numeric.get("hybrid_system")
    internal = (
        hybrid.get("internal_unknown_count") if isinstance(hybrid, Mapping) else None
    )
    expected_shapes = {
        "x_nm": (40,),
        "y_nm": (20,),
        "z_nm": (5,),
        "E_V_per_m": (5, 20, 40, 3),
        "H_A_per_m": (5, 20, 40, 3),
        "modal_amplitudes": (int(internal),)
        if isinstance(internal, int) and not isinstance(internal, bool)
        else None,
        "bottom_q": (
            int(
                side_counts["bottom"],
            ),
        )
        if isinstance(side_counts, Mapping) and "bottom" in side_counts
        else None,
        "top_q": (
            int(
                side_counts["top"],
            ),
        )
        if isinstance(side_counts, Mapping) and "top" in side_counts
        else None,
    }
    expected_dtypes = {
        key: ("float64" if key.endswith("_nm") else "complex128")
        for key in _PAYLOAD_KEYS
    }
    metadata = descriptor.get("arrays")
    if not isinstance(metadata, Mapping) or set(metadata) != set(_PAYLOAD_KEYS):
        _fail("Task39 direct comparison payload array metadata is incomplete")
    try:
        with np.load(path, allow_pickle=False) as archive:
            if archive.files != list(_PAYLOAD_KEYS):
                _fail("Task39 direct comparison payload NPZ keys are invalid")
            arrays = {key: np.asarray(archive[key]).copy() for key in _PAYLOAD_KEYS}
    except (OSError, ValueError) as exc:
        raise IdentityCheckError(
            "cannot read Task39 direct comparison payload"
        ) from exc
    for key, array in arrays.items():
        item = metadata.get(key)
        if expected_shapes[key] is None or array.shape != expected_shapes[key]:
            _fail(f"Task39 direct comparison payload {key} shape is invalid")
        if str(array.dtype) != expected_dtypes[key] or not np.isfinite(array).all():
            _fail(
                f"Task39 direct comparison payload {key} dtype or finite contract failed"
            )
        if not isinstance(item, Mapping):
            _fail(f"Task39 direct comparison payload metadata missing {key}")
        if item.get("shape") != list(array.shape) or item.get("dtype") != str(
            array.dtype
        ):
            _fail(
                f"Task39 direct comparison payload {key} metadata shape/dtype mismatches"
            )
        digest = hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
        if (
            item.get("sha256") != digest
            or item.get("bytes") != int(array.nbytes)
            or item.get("finite") is not True
        ):
            _fail(
                f"Task39 direct comparison payload {key} metadata identity mismatches"
            )
    if not np.array_equal(arrays["z_nm"], np.asarray(_PLANES, dtype=np.float64)):
        _fail("Task39 direct comparison payload z planes are invalid")
    return {"descriptor": dict(descriptor), "artifact": artifact, "arrays": arrays}


def _canonical_entries(numeric_dir: Path, numeric: Mapping[str, Any]) -> dict[str, Any]:
    raw = numeric.get("canonical_exports")
    if not isinstance(raw, Mapping) or set(raw) != {"bottom", "top"}:
        _fail("Task39 Hybrid direct canonical bottom/top exports are missing")
    entries: dict[str, Any] = {}
    for side in ("bottom", "top"):
        item = raw.get(side)
        roles = item.get("roles") if isinstance(item, Mapping) else None
        if not isinstance(roles, Mapping) or set(roles) != set(_CANONICAL_ROLES):
            _fail(f"Task39 canonical {side} roles are incomplete")
        for role in _CANONICAL_ROLES:
            descriptor = roles[role]
            if (
                not isinstance(descriptor, Mapping)
                or descriptor.get("pass") is not True
            ):
                _fail(f"Task39 canonical {side}.{role} is not passed")
            manifest_path = _resolve(numeric_dir, descriptor.get("manifest"))
            manifest_sha = descriptor.get("manifest_sha256")
            if not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
                _fail(f"Task39 canonical {side}.{role} manifest SHA is invalid")
            try:
                manifest = read_canonical_manifest(manifest_path, manifest_sha)
            except (OSError, ValueError, KeyError) as exc:
                raise IdentityCheckError(
                    f"cannot read Task39 canonical {side}.{role}"
                ) from exc
            if (
                manifest.get("role") != f"{side}_{role}"
                or manifest.get("mpi_size") != 8
            ):
                _fail(f"Task39 canonical {side}.{role} manifest identity is invalid")
            shards = manifest.get("per_rank_shards")
            if not isinstance(shards, list) or len(shards) != 8:
                _fail(f"Task39 canonical {side}.{role} must have eight rank shards")
            if (
                manifest.get("summed_local_duplicate_count") != 0
                or manifest.get("global_summed_packet_count", 0) <= 0
            ):
                _fail(f"Task39 canonical {side}.{role} packet audit failed")
            entries[f"{side}.{role}"] = {
                "manifest": _artifact(manifest_path, f"canonical {side}.{role}"),
                "packet_count": manifest["global_summed_packet_count"],
                "shard_count": len(shards),
            }
    return entries


def _resource_authority(outer: Mapping[str, Any]) -> dict[str, Any]:
    raw = outer.get("resource_authority")
    if not isinstance(raw, Mapping):
        _fail("resource_authority is missing")
    aliases = {
        "rss_mb": ("process_tree_peak_rss_mb", "process_tree_peak_rss_mib"),
        "pss_mb": ("peak_pss_mb", "peak_pss_mib"),
        "uss_mb": ("peak_uss_mb", "peak_uss_mib"),
        "swap_mb": ("process_tree_peak_swap_mb", "swap_mib"),
    }
    result: dict[str, Any] = {}
    for output, names in aliases.items():
        value = next((raw[name] for name in names if name in raw), None)
        result[output] = _finite(value, f"resource_authority.{output}")
    result["swap_pass"] = result["swap_mb"] == 0.0
    result["raw"] = dict(raw)
    return result


def _mode_metrics(
    numeric: Mapping[str, Any], inventory: Mapping[str, Any], requested_modes: int
) -> dict[str, Any]:
    qep = numeric.get("qep")
    if not isinstance(qep, Mapping):
        _fail("Hybrid qep record is missing")
    positive = qep.get("positive_directional_selection")
    negative = qep.get("negative_directional_selection")
    if not isinstance(positive, Mapping) or not isinstance(negative, Mapping):
        _fail("Hybrid directional mode selection record is missing")
    fields = ("requested_modes", "candidate_modes", "selected_modes")
    counts: dict[str, Any] = {}
    for name, selection in (("positive", positive), ("negative", negative)):
        for field in fields:
            value = selection.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _fail(f"Hybrid qep {name}.{field} is missing")
            counts[f"{name}_{field}"] = value
        for field in (
            "direction_counts",
            "passive_candidate_count",
            "finite_candidate_count",
            "numerically_infinite_candidate_count",
        ):
            counts[f"{name}_{field}"] = selection.get(field, "not_available")
    for name, selection in (("positive", positive), ("negative", negative)):
        if selection["requested_modes"] != requested_modes:
            _fail(f"Hybrid qep {name}.requested_modes does not match model M")
    meta = numeric.get("task039_modal_metrics") or numeric.get("modal_metrics")
    meta = meta if isinstance(meta, Mapping) else {}
    system = numeric.get("hybrid_system")
    system = system if isinstance(system, Mapping) else {}
    block_shapes = system.get("block_shapes")
    block_shapes = block_shapes if isinstance(block_shapes, Mapping) else {}
    ledger = numeric.get("object_payload_ledger")
    ledger = ledger if isinstance(ledger, Mapping) else {}
    factor_inventory = ledger.get("local_or_augmented_factor_inventory")
    factor_inventory = factor_inventory if isinstance(factor_inventory, Mapping) else {}
    projection_matrix = ledger.get("projection_matrix")
    projection_matrix = (
        projection_matrix if isinstance(projection_matrix, Mapping) else {}
    )
    projection_bytes = {
        side: (
            projection_matrix.get(side, {}).get("matrix_memory_estimate_bytes")
            if isinstance(projection_matrix.get(side), Mapping)
            else None
        )
        for side in ("bottom", "top")
    }
    factor_components = {
        name: dict(item)
        for name, item in factor_inventory.items()
        if isinstance(item, Mapping)
    }
    projection_components = {
        side: {
            key: item.get(key)
            for key in (
                "matrix_rows",
                "matrix_cols",
                "matrix_nnz_used",
                "matrix_memory_estimate_bytes",
                "matrix_memory_estimate_mb",
                "matrix_type",
            )
            if key in item
        }
        for side, item in projection_matrix.items()
        if isinstance(item, Mapping)
    }
    measured_projection_bytes = tuple(
        projection_bytes[side] for side in ("bottom", "top")
    )
    derived_coupling_bytes = (
        sum(measured_projection_bytes)
        if all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0.0
            for value in measured_projection_bytes
        )
        else None
    )
    if meta.get("coupling_bytes") is not None:
        coupling_bytes = meta["coupling_bytes"]
        coupling_classification = "reported_task039_modal_metrics"
    elif ledger.get("projection_coupling_matrix_bytes") is not None:
        coupling_bytes = ledger["projection_coupling_matrix_bytes"]
        coupling_classification = "reported_projection_coupling_aggregate"
    elif derived_coupling_bytes is not None:
        coupling_bytes = derived_coupling_bytes
        coupling_classification = "derived_sum_of_projection_components"
    else:
        coupling_bytes = "not_available"
        coupling_classification = "not_available"
    candidates = {
        "qep_full_shape": qep.get("full_shape"),
        "qep_reduced_shape": qep.get("reduced_shape"),
        "H_modal_shape": block_shapes.get("H_modal"),
        "basis_bytes": meta.get(
            "basis_bytes", ledger.get("retained_right_left_eigenvector_bytes")
        ),
        "coupling_bytes": coupling_bytes,
        "coupling_bytes_derived_sum": derived_coupling_bytes
        if derived_coupling_bytes is not None
        else "not_available",
        "coupling_bytes_classification": coupling_classification,
        "modal_schur_shape": meta.get("modal_schur_shape"),
        "modal_schur_storage_bytes": meta.get(
            "modal_schur_storage_bytes",
            ledger.get("modal_schur_bytes", system.get("modal_schur_bytes")),
        ),
        "modal_lu_storage_bytes": meta.get(
            "modal_lu_storage_bytes", factor_inventory.get("lu_storage_bytes")
        ),
        "modal_schur_condition": meta.get(
            "modal_schur_condition", system.get("modal_schur_condition")
        ),
        "retained_right_left_eigenvector_bytes": ledger.get(
            "retained_right_left_eigenvector_bytes"
        ),
        "projection_coupling_matrix_bytes": projection_bytes,
        "phase_wall_seconds": numeric.get(
            "timing_seconds_max_rank", numeric.get("timing_seconds")
        ),
    }
    counts.update(
        {
            "external_propagating": inventory["counts"].get("propagating")
            if isinstance(inventory.get("counts"), Mapping)
            else None,
            "external_nonpropagating": inventory["counts"].get("nonpropagating")
            if isinstance(inventory.get("counts"), Mapping)
            else None,
            "external_counts": inventory.get("counts"),
        }
    )
    raw_modal_schur_bytes = ledger.get(
        "modal_schur_bytes", system.get("modal_schur_bytes")
    )
    modal_schur_state = (
        "not_materialized"
        if system.get("primary_solver_path") == "augmented"
        and (raw_modal_schur_bytes is None or raw_modal_schur_bytes == 0)
        else "materialized"
        if any(
            candidates.get(key) is not None
            for key in (
                "modal_schur_shape",
                "modal_schur_storage_bytes",
                "modal_lu_storage_bytes",
                "modal_schur_condition",
            )
        )
        else "not_available"
    )
    if modal_schur_state == "not_materialized":
        candidates["modal_schur_condition"] = "not_applicable_augmented_direct"
        candidates["modal_lu_storage_bytes"] = "not_applicable_augmented_direct"
    optional_unavailable = [key for key, value in candidates.items() if value is None]
    return {
        "mode_counts": counts,
        "metrics": candidates,
        "factor_inventory_components": factor_components,
        "projection_matrix_components": projection_components,
        "optional_unavailable": optional_unavailable,
        "modal_schur_state": modal_schur_state,
        "pass": True,
    }


def _load_hybrid(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    numeric_dir = root / "numerical_output"
    manifest_path, outer_path, numeric_path = (
        root / "run_manifest.json",
        root / "run_summary.json",
        numeric_dir / "run_summary.json",
    )
    manifest, outer, numeric = (
        _json(manifest_path),
        _json(outer_path),
        _json(numeric_path),
    )
    for source in (manifest, outer):
        if source.get("status") != "finished" or source.get("exit_status") != 0:
            _fail("Hybrid run is not finished with exit_status=0")
    if (
        manifest.get("method") != "hybrid_direct"
        or manifest.get("resolved_method_adapter") != "task039.hybrid_direct"
    ):
        _fail("run is not the Task39 Hybrid-direct adapter")
    model = manifest.get("model_id")
    model_match = _MODEL_ID.fullmatch(model) if isinstance(model, str) else None
    if model_match is None:
        _fail("Hybrid model_id is not a finite Task39 M identity")
    requested_modes = (
        numeric.get("case", {}).get("requested_modes_per_direction")
        if isinstance(numeric.get("case"), Mapping)
        else None
    )
    if (
        isinstance(requested_modes, bool)
        or not isinstance(requested_modes, int)
        or requested_modes != int(model_match.group(1))
    ):
        _fail("numeric.case.requested_modes_per_direction does not match model M")
    if manifest.get("mpi_size") != 8 or numeric.get("mpi_size", 8) != 8:
        _fail("Hybrid direct run must be MPI8")
    for key, pattern in (
        ("source_sha", _SOURCE_SHA),
        ("input_sha256", _SHA256),
        ("resolved_config_sha256", _SHA256),
        ("physical_model_sha256", _SHA256),
    ):
        if not isinstance(manifest.get(key), str) or not pattern.fullmatch(
            manifest[key]
        ):
            _fail(f"manifest.{key} identity is invalid")
    case = numeric.get("case")
    if not isinstance(case, Mapping):
        _fail("numeric.case is missing")
    for key, expected in (
        ("wavelength_nm", 5.0),
        ("degree", 6),
        ("h_nm", 10.0),
        ("polarization_kind", "s"),
        ("incident_grazing_deg", 10.0),
    ):
        if case.get(key) != expected:
            _fail(f"numeric.case.{key} does not match p6/h10 Task39 contract")
    inventory = _parse_inventory(manifest.get("external_mode_inventory"), "manifest")
    numeric_inventory = numeric.get("external_mode_inventory")
    numeric_inventory_exact: bool | str = "not_applicable"
    if numeric_inventory is not None:
        parsed_numeric = _parse_inventory(numeric_inventory, "numeric")
        numeric_inventory_exact = parsed_numeric["value"] == inventory["value"]
        if not numeric_inventory_exact:
            _fail("numeric and manifest external inventories differ")
    payload = _load_payload(numeric_dir, numeric, inventory)
    orders = _parse_orders(
        numeric.get("validation", {}).get("external_diffraction_orders")
        if isinstance(numeric.get("validation"), Mapping)
        else None,
        "validation.external_diffraction_orders",
    )
    if len(orders) != 604 or set(orders) != set(inventory["keys"]):
        _fail("Hybrid diffraction-order keys do not exactly match dynamic inventory")
    canonical = _canonical_entries(numeric_dir, numeric)
    resource = _resource_authority(outer)
    qualification = numeric.get("qualification")
    solve = numeric.get("solve")
    validation = numeric.get("validation")
    physical = numeric.get("physical_field_reconstruction")
    volume = (
        physical.get("volume_absorption") if isinstance(physical, Mapping) else None
    )
    port = validation.get("port_power") if isinstance(validation, Mapping) else None
    projection = (
        validation.get("interface_e_projection")
        if isinstance(validation, Mapping)
        else None
    )
    traction = (
        validation.get("fe_modal_traction_equilibrium")
        if isinstance(validation, Mapping)
        else None
    )
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("integration_pass") is not True
    ):
        _fail("Hybrid integration_pass is not true")
    residual = _finite(
        solve.get("true_relative_residual") if isinstance(solve, Mapping) else None,
        "solve.true_relative_residual",
    )
    if residual > 1.0e-9:
        _fail("Hybrid true residual exceeds 1e-9")
    if not isinstance(port, Mapping) or not isinstance(volume, Mapping):
        _fail("Hybrid R/T/A/A_volume authority is missing")
    observables = {
        name: _finite(port.get(name), f"port_power.{name}")
        for name in ("R_total", "T_total", "A_balance")
    }
    observables["A_volume"] = _finite(
        volume.get("A_volume_total"), "volume_absorption.A_volume_total"
    )
    closure = _finite(
        volume.get("energy_closure_error"), "volume_absorption.energy_closure_error"
    )
    if abs(closure) > 1.0e-5:
        _fail("Hybrid energy closure exceeds 1e-5")
    if (
        not isinstance(projection, Mapping)
        or _finite(projection.get("combined_relative_residual"), "interface projection")
        > 1.0e-8
    ):
        _fail("Hybrid interface projection exceeds 1e-8")
    if not isinstance(traction, Mapping) or any(
        _finite(traction.get(f"{side}_relative_residual"), f"traction {side}") > 1.0e-8
        for side in ("bottom", "top")
    ):
        _fail("Hybrid exact traction exceeds 1e-8")
    gates = numeric.get("gates")
    required_gates = (
        "monolithic_true_relative_residual_le_1e-9",
        "primary_direct_true_relative_residual_le_1e-9",
        "interface_e_projection_relative_residual_le_1e-8",
        "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
        "assembled_interface_h_t_exact_dual_le_1e-8",
        "volume_energy_closure_abs_le_1e-5",
        "external_port_rta_finite",
    )
    if not isinstance(gates, Mapping) or any(
        gates.get(name) is not True for name in required_gates
    ):
        _fail("one or more Hybrid own physics gates are not true")
    metadata = _mode_metrics(numeric, inventory, requested_modes)
    return {
        "root": root,
        "manifest": manifest,
        "numeric": numeric,
        "inventory": inventory,
        "numeric_inventory_exact": numeric_inventory_exact,
        "requested_modes": requested_modes,
        "orders": orders,
        "payload": payload,
        "canonical": canonical,
        "resource": resource,
        "observables": observables,
        "closure": closure,
        "residual": residual,
        "projection": float(projection["combined_relative_residual"]),
        "traction": {
            side: float(traction[f"{side}_relative_residual"])
            for side in ("bottom", "top")
        },
        "metadata": metadata,
    }


def _raw_full3d(run_dir: str | Path) -> dict[str, Any]:
    from benchmarks.task039_full3d_identity import _load_run

    raw = _load_run(run_dir, "direct", expected_mesh_target_size=None)
    numeric = raw["numeric"]
    mesh_target_size = _finite(
        numeric.get("mesh_target_size"), "Full3D mesh_target_size"
    )
    orders = raw["orders"]["rows"]
    inventory_keys = set(raw["inventory"]["keys"])
    if (
        not isinstance(orders, Mapping)
        or len(orders) != 604
        or set(orders) != inventory_keys
    ):
        _fail("Full3D diffraction-order mapping does not exactly match its inventory")
    return {
        "source_sha": raw["manifest"]["source_sha"],
        "physical_model_sha256": raw["manifest"]["physical_model_sha256"],
        "mesh_target_size": mesh_target_size,
        "inventory": raw["inventory"],
        "orders": orders,
        "fields": raw["reference"]["arrays"],
        "coordinates": raw["reference"]["coordinates"],
        "observables": {
            "R_total": _finite(numeric.get("R_total"), "Full3D R_total"),
            "T_total": _finite(numeric.get("T_total"), "Full3D T_total"),
            "A_balance": _finite(numeric.get("A_balance"), "Full3D A_balance"),
            "A_volume": _finite(numeric.get("A_volume_total"), "Full3D A_volume_total"),
        },
        "closure": _finite(
            numeric.get("energy_closure_error_port_volume"), "Full3D closure"
        ),
        "artifacts": raw["artifacts"],
    }


def _compact_full3d(record_path: str | Path) -> dict[str, Any]:
    path = Path(record_path).resolve()
    record = _json(path)
    raw = record.get("raw_run_directory")
    if not isinstance(raw, str):
        _fail("Full3D compact record.raw_run_directory is missing")
    raw_path = _resolve(path.parent, raw)
    if not raw_path.is_dir():
        _fail(f"Full3D compact raw_run_directory is unavailable: {raw_path}")
    return _raw_full3d(raw_path)


def _significant_comparison(
    left: Mapping[Any, Any], right: Mapping[Any, Any]
) -> dict[str, Any]:
    if set(left) != set(right):
        return {
            "pass": False,
            "keys_exact": False,
            "left_count": len(left),
            "right_count": len(right),
            "failures": [],
        }
    significant = tuple(
        sorted(
            key
            for key in left
            if max(left[key]["power_ratio"], right[key]["power_ratio"]) >= 1.0e-8
        )
    )
    failures: list[dict[str, Any]] = []
    max_power = max_amplitude = 0.0
    for key in significant:
        power = _relative(left[key]["power_ratio"], right[key]["power_ratio"])
        amplitude = _complex_relative(
            left[key]["outgoing_amplitude"], right[key]["outgoing_amplitude"]
        )
        max_power, max_amplitude = max(max_power, power), max(max_amplitude, amplitude)
        if power > 1.0e-4 or amplitude > 1.0e-4:
            failures.append(
                {
                    "key": list(key),
                    "power_relative_delta": power,
                    "amplitude_relative_delta": amplitude,
                }
            )
    return {
        "keys_exact": True,
        "significant_count": len(significant),
        "threshold": 1.0e-8,
        "normalization": "incident_power",
        "max_power_relative_delta": max_power,
        "max_amplitude_relative_delta": max_amplitude,
        "relative_delta_threshold": 1.0e-4,
        "failures": failures,
        "pass": not failures,
    }


def _planes(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    overall_threshold: float | None,
    plane_thresholds: Mapping[str, Mapping[float, float]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"planes_nm": list(_PLANES), "fields": {}}
    plane_thresholds = plane_thresholds or {}
    for field in ("E_V_per_m", "H_A_per_m"):
        values: list[dict[str, Any]] = []
        thresholds = plane_thresholds.get(field, {})
        for index, z in enumerate(_PLANES):
            delta = _array_relative(left[field][index], right[field][index])
            threshold = thresholds.get(z)
            values.append(
                {
                    "z_nm": z,
                    "relative_l2": delta,
                    "threshold": threshold,
                    "pass": threshold is None or delta <= threshold,
                }
            )
        overall = _array_relative(left[field], right[field])
        overall_pass = overall_threshold is None or overall <= overall_threshold
        result["fields"][field] = {
            "overall_relative_l2": overall,
            "overall_threshold": overall_threshold,
            "overall_pass": overall_pass,
            "planes": values,
            "pass": overall_pass and all(item["pass"] for item in values),
        }
    result["pass"] = all(value["pass"] for value in result["fields"].values())
    return result


def _coordinates_exact(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name in ("x_nm", "y_nm", "z_nm"):
        if name not in left or name not in right:
            _fail(f"coordinate array {name} is missing from comparison")
        left_array = np.asarray(left[name])
        right_array = np.asarray(right[name])
        exact = (
            left_array.dtype == right_array.dtype
            and left_array.shape == right_array.shape
            and np.array_equal(left_array, right_array)
        )
        fields[name] = {
            "left_shape": list(left_array.shape),
            "right_shape": list(right_array.shape),
            "left_dtype": str(left_array.dtype),
            "right_dtype": str(right_array.dtype),
            "exact": exact,
        }
    return {"fields": fields, "pass": all(item["exact"] for item in fields.values())}


def _compare_observables(
    left: Mapping[str, Any], right: Mapping[str, Any], threshold: float
) -> dict[str, Any]:
    values = {}
    for name in ("R_total", "T_total", "A_balance", "A_volume"):
        right_name = "A_volume" if name == "A_volume" else name
        if name not in right and right_name not in right:
            _fail(f"comparison observable {name} is missing")
        delta = abs(left[name] - right[right_name])
        values[name] = {
            "left": left[name],
            "right": right[right_name],
            "abs_delta": delta,
            "threshold": threshold,
            "pass": delta <= threshold,
        }
    return {"values": values, "pass": all(item["pass"] for item in values.values())}


def _compare_hybrid(
    left: Mapping[str, Any], right: Mapping[str, Any], threshold: float
) -> dict[str, Any]:
    observables = _compare_observables(
        left["observables"], right["observables"], threshold
    )
    orders = _significant_comparison(left["orders"], right["orders"])
    physical = {
        "left": left["manifest"]["physical_model_sha256"],
        "right": right["manifest"]["physical_model_sha256"],
        "pass": left["manifest"]["physical_model_sha256"]
        == right["manifest"]["physical_model_sha256"],
    }
    coordinates = _coordinates_exact(
        left["payload"]["arrays"], right["payload"]["arrays"]
    )
    fields = _planes(left["payload"]["arrays"], right["payload"]["arrays"], 5.0e-3)
    return {
        "observables": observables,
        "orders": orders,
        "physical_model_sha256": physical,
        "coordinates_exact": coordinates,
        "selected_EH": fields,
        "pass": observables["pass"]
        and orders["pass"]
        and physical["pass"]
        and coordinates["pass"]
        and fields["pass"],
    }


def _compare_full3d(
    hybrid: Mapping[str, Any], full: Mapping[str, Any]
) -> dict[str, Any]:
    observables = _compare_observables(
        hybrid["observables"], full["observables"], 1.0e-5
    )
    orders = _significant_comparison(hybrid["orders"], full["orders"])
    physical = {
        "hybrid": hybrid["manifest"]["physical_model_sha256"],
        "full3d": full["physical_model_sha256"],
        "pass": hybrid["manifest"]["physical_model_sha256"]
        == full["physical_model_sha256"],
    }
    coordinates = _coordinates_exact(hybrid["payload"]["arrays"], full["coordinates"])
    plane = _planes(
        hybrid["payload"]["arrays"],
        full["fields"],
        None,
        {
            "E_V_per_m": {10.0: 5.0e-3, 60.0: 5.0e-3, 110.0: 5.0e-3},
            "H_A_per_m": {10.0: 1.0e-2, 60.0: 5.0e-3, 110.0: 1.0e-2},
        },
    )
    closure = {
        "hybrid": {
            "value": hybrid["closure"],
            "threshold": 1.0e-5,
            "pass": abs(hybrid["closure"]) <= 1.0e-5,
        },
        "full3d": {
            "value": full["closure"],
            "threshold": 1.0e-5,
            "pass": abs(full["closure"]) <= 1.0e-5,
        },
    }
    return {
        "reference_mesh_target_nm": full["mesh_target_size"],
        "observables": observables,
        "energy_closure": closure,
        "orders": orders,
        "physical_model_sha256": physical,
        "coordinates_exact": coordinates,
        "selected_EH": plane,
        "pass": observables["pass"]
        and all(item["pass"] for item in closure.values())
        and orders["pass"]
        and physical["pass"]
        and coordinates["pass"]
        and plane["pass"],
    }


def check_hybrid_direct_identity(
    hybrid_run_dir: str | Path,
    *,
    adjacent_run_dir: str | Path | None = None,
    full3d_record: str | Path | None = None,
) -> dict[str, Any]:
    """Return JSON-safe own/diagnostic results; never claim production validation."""
    base = {
        "schema_version": "task039.hybrid-direct-identity.v1",
        "full3d_comparison_role": "diagnostic_against_direct_authority",
        "production_validation_allowed": False,
        "blocked_by": _BLOCKED_BY,
    }
    try:
        hybrid = _load_hybrid(hybrid_run_dir)
        result: dict[str, Any] = {
            **base,
            "own": {
                "pass": True,
                "model_id": hybrid["manifest"]["model_id"],
                "requested_modes": hybrid["requested_modes"],
                "qualification": {
                    key: hybrid["numeric"].get("qualification", {}).get(key)
                    for key in (
                        "integration_pass",
                        "official_record",
                        "mode_count_converged",
                    )
                },
                "source_sha": hybrid["manifest"]["source_sha"],
                "input_sha256": hybrid["manifest"]["input_sha256"],
                "resolved_config_sha256": hybrid["manifest"]["resolved_config_sha256"],
                "physical_model_sha256": hybrid["manifest"]["physical_model_sha256"],
                "inventory": {
                    "count": hybrid["inventory"]["count"],
                    "canonical_sha256": hybrid["inventory"]["canonical_sha256"],
                    "key_sha256": hybrid["inventory"]["key_sha256"],
                    "counts": hybrid["inventory"]["counts"],
                    "numeric_inventory_exact": hybrid["numeric_inventory_exact"],
                },
                "residual": hybrid["residual"],
                "observables": hybrid["observables"],
                "closure": hybrid["closure"],
                "projection": hybrid["projection"],
                "traction": hybrid["traction"],
                "payload": {
                    "descriptor": hybrid["payload"]["descriptor"],
                    "artifact": hybrid["payload"]["artifact"],
                },
                "canonical": hybrid["canonical"],
                "mode_evidence": hybrid["metadata"],
                "resources": hybrid["resource"],
            },
            "comparisons": {},
        }
        if adjacent_run_dir is not None:
            adjacent = _load_hybrid(adjacent_run_dir)
            result["comparisons"]["adjacent"] = _compare_hybrid(
                hybrid, adjacent, 1.0e-6
            )
        else:
            result["comparisons"]["adjacent"] = {"status": "not_run", "pass": True}
        if full3d_record is not None:
            full = _compact_full3d(full3d_record)
            result["comparisons"]["full3d_diagnostic"] = _compare_full3d(hybrid, full)
        else:
            result["comparisons"]["full3d_diagnostic"] = {
                "status": "not_run",
                "pass": True,
            }
        requested = [
            value
            for value in result["comparisons"].values()
            if isinstance(value, Mapping) and value.get("status") != "not_run"
        ]
        result["pass"] = result["own"]["pass"] and all(
            value.get("pass") is True for value in requested
        )
        result["classification"] = (
            "HYBRID_DIRECT_DIAGNOSTIC_PASS_ONLY"
            if result["pass"]
            else "HYBRID_DIRECT_DIAGNOSTIC_FAIL"
        )
        return result
    except IdentityCheckError as exc:
        return {
            **base,
            "pass": False,
            "classification": "HYBRID_DIRECT_OWN_AUTHORITY_FAIL",
            "errors": [str(exc)],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid-run", required=True, type=Path)
    parser.add_argument("--adjacent-run", type=Path)
    parser.add_argument("--full3d-record", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_hybrid_direct_identity(
            args.hybrid_run,
            adjacent_run_dir=args.adjacent_run,
            full3d_record=args.full3d_record,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"pass": False, "classification": "CHECKER_ERROR", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


__all__ = ["check_hybrid_direct_identity", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
