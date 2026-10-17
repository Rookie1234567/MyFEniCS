"""Hash-bound A1/A2 numerical comparison helpers for Task41 P0."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


TASK41_COMPARISON_SCHEMA = "task41.p0.a1_a2_comparison.v1"
TASK41_MODE_RELATIVE_LIMIT = 1.0e-4
TASK41_TOTAL_ABSOLUTE_LIMIT = 1.0e-5
TASK41_MODE_POWER_ABSOLUTE_LIMIT = 1.0e-6
TASK41_SIGNIFICANT_MODE_POWER = 1.0e-8
TASK41_MPC_MAP_SCHEMA = "task41.p0.numeric_mpc_map.v1"


def task41_numeric_mpc_map(mpc: Any) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Copy a finalized MPC adjacency into pointer-free numeric arrays.

    Some pybind adjacency views expose ``dtype=object`` arrays.  Their raw
    memory bytes contain Python object pointers, so identity is recorded from
    normalized numeric values instead.
    """
    coefficients, offsets = mpc.coefficients()
    raw_arrays = {
        "slaves": np.asarray(mpc.slaves),
        "masters": np.asarray(mpc.masters.array),
        "coefficients": np.asarray(coefficients),
        "offsets": np.asarray(offsets),
    }
    integer_names = {"slaves", "masters", "offsets"}
    numeric: dict[str, np.ndarray] = {}
    records: dict[str, Any] = {}
    for name, raw in raw_arrays.items():
        source_values = raw.tolist() if raw.dtype.kind == "O" else raw
        target_dtype = np.dtype("int64") if name in integer_names else np.dtype("complex128")
        try:
            values = np.asarray(source_values, dtype=target_dtype)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Task41 MPC {name} adjacency is not numeric") from exc
        if values.shape != raw.shape or not np.isfinite(values).all():
            raise ValueError(f"Task41 MPC {name} adjacency is nonfinite or changed shape")
        if name in integer_names and not np.array_equal(values.astype(np.float64), np.asarray(source_values, dtype=np.float64)):
            raise ValueError(f"Task41 MPC {name} adjacency contains non-integral values")
        canonical_dtype = np.dtype("<i8") if name in integer_names else np.dtype("<c16")
        canonical = np.ascontiguousarray(values, dtype=canonical_dtype)
        numeric[name] = values.copy()
        records[name] = {
            "source_dtype": str(raw.dtype),
            "numeric_dtype": str(values.dtype),
            "shape": list(values.shape),
            "values_sha256": hashlib.sha256(canonical.tobytes()).hexdigest(),
        }
    return numeric, records


def compare_task41_numeric_mpc_maps(
    a1_mpc: Any, a2_mpc: Any
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Compare the actual slave/master adjacency, offsets, and coefficients."""
    a1_arrays, a1_records = task41_numeric_mpc_map(a1_mpc)
    a2_arrays, a2_records = task41_numeric_mpc_map(a2_mpc)
    arrays = {
        f"a1_mpc_map_{name}": a1_arrays[name] for name in a1_arrays
    } | {
        f"a2_mpc_map_{name}": a2_arrays[name] for name in a2_arrays
    }
    checks = {
        name: bool(
            a1_records[name]["source_dtype"] == a2_records[name]["source_dtype"]
            and a1_records[name]["shape"] == a2_records[name]["shape"]
            and a1_records[name]["values_sha256"] == a2_records[name]["values_sha256"]
            and np.array_equal(a1_arrays[name], a2_arrays[name])
        )
        for name in a1_arrays
    }
    return arrays, {
        "schema": TASK41_MPC_MAP_SCHEMA,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "arrays": {
            name: {"a1": a1_records[name], "a2": a2_records[name]}
            for name in a1_records
        },
        "identity_basis": "numeric MPC slaves, masters, coefficient offsets, and complex coefficients; dtype/shape/value checked",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mode_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _read_orders(path: str | Path) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("orders") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("Task41 diffraction artifact must contain an orders list")
    result = {_mode_key(row): dict(row) for row in rows if isinstance(row, Mapping)}
    if len(result) != len(rows) or not result:
        raise ValueError("Task41 diffraction artifact has malformed or duplicate mode rows")
    return result


def compare_task41_modal_artifacts(
    reference_modal: str | Path,
    candidate_modal: str | Path,
    reference_orders: str | Path,
    candidate_orders: str | Path,
) -> dict[str, Any]:
    """Compare physical-boundary amplitudes and per-mode power without phase fitting."""
    archive_rows: list[dict[tuple[str, int, int, str], dict[str, Any]]] = []
    arrays_by_key: list[dict[str, np.ndarray]] = []
    for raw_path in (reference_modal, candidate_modal):
        path = Path(raw_path).resolve()
        with np.load(path, allow_pickle=False) as data:
            required = {
                "side", "m", "n", "polarization",
                "physical_boundary_outgoing_amplitude",
                "physical_boundary_outgoing_representable",
                "physical_boundary_incident_amplitude",
                "physical_boundary_amplitude_coordinate",
            }
            if not required.issubset(data.files):
                raise ValueError("Task41 modal archive omits physical-boundary amplitude identity")
            keys = [
                (str(side), int(m), int(n), str(pol))
                for side, m, n, pol in zip(
                    data["side"], data["m"], data["n"], data["polarization"], strict=True
                )
            ]
            if len(keys) != len(set(keys)):
                raise ValueError("Task41 modal archive has duplicate mode identities")
            arrays_by_key.append(
                {
                    "amplitude": np.asarray(data["physical_boundary_outgoing_amplitude"], dtype=np.complex128).copy(),
                    "representable": np.asarray(data["physical_boundary_outgoing_representable"], dtype=bool).copy(),
                    "incident": np.asarray(data["physical_boundary_incident_amplitude"], dtype=np.complex128).copy(),
                    "coordinate": np.asarray(data["physical_boundary_amplitude_coordinate"]).copy(),
                }
            )
            archive_rows.append({key: {"index": index} for index, key in enumerate(keys)})

    reference_orders_map = _read_orders(reference_orders)
    candidate_orders_map = _read_orders(candidate_orders)
    reference_keys = set(archive_rows[0])
    candidate_keys = set(archive_rows[1])
    if not (
        reference_keys == candidate_keys == set(reference_orders_map) == set(candidate_orders_map)
    ):
        raise ValueError("Task41 A1/A2 full physical mode inventories differ")
    for arrays in arrays_by_key:
        if arrays["coordinate"].size != 1:
            raise ValueError("Task41 modal archive has an invalid amplitude-coordinate identity")
    reference_coordinate = str(arrays_by_key[0]["coordinate"].item())
    candidate_coordinate = str(arrays_by_key[1]["coordinate"].item())
    if reference_coordinate != candidate_coordinate:
        raise ValueError("Task41 modal archives use different physical-boundary amplitude coordinates")
    incoming_scales = [
        abs(complex(arrays["incident"][index]))
        for arrays in arrays_by_key
        for index, representable in enumerate(arrays["representable"])
        if representable
    ]
    if not incoming_scales or not np.isfinite(incoming_scales).all():
        raise ValueError("Task41 modal archives have no finite physical-boundary incident scale")
    incident_scale_reference = max(incoming_scales)
    if incident_scale_reference <= np.finfo(float).tiny:
        raise ValueError("Task41 physical-boundary incident scale is zero")

    power_rows: list[dict[str, Any]] = []
    weak_channels: list[dict[str, Any]] = []
    significant_reference: list[complex] = []
    significant_candidate: list[complex] = []
    significant_relative: list[float] = []
    power_deltas: list[float] = []
    flags_match = True
    for key in sorted(reference_keys):
        reference_index = int(archive_rows[0][key]["index"])
        candidate_index = int(archive_rows[1][key]["index"])
        reference_arrays, candidate_arrays = arrays_by_key
        reference_amplitude = complex(reference_arrays["amplitude"][reference_index])
        candidate_amplitude = complex(candidate_arrays["amplitude"][candidate_index])
        reference_representable = bool(reference_arrays["representable"][reference_index])
        candidate_representable = bool(candidate_arrays["representable"][candidate_index])
        flags_match = flags_match and reference_representable == candidate_representable
        if reference_representable != candidate_representable:
            raise ValueError(f"Task41 A1/A2 physical-boundary representability differs for {key}")
        if reference_representable and not np.isfinite(
            [reference_amplitude.real, reference_amplitude.imag,
             candidate_amplitude.real, candidate_amplitude.imag,
             complex(reference_arrays["incident"][reference_index]).real,
             complex(reference_arrays["incident"][reference_index]).imag,
             complex(candidate_arrays["incident"][candidate_index]).real,
             complex(candidate_arrays["incident"][candidate_index]).imag]
        ).all():
            raise ValueError(f"Task41 representable amplitude is nonfinite for {key}")
        reference_order = reference_orders_map[key]
        candidate_order = candidate_orders_map[key]
        row_power_deltas = {}
        for quantity in ("R", "T"):
            reference_power = float(reference_order[quantity])
            candidate_power = float(candidate_order[quantity])
            if not np.isfinite(reference_power) or not np.isfinite(candidate_power):
                raise ValueError(f"Task41 per-mode {quantity} power is nonfinite for {key}")
            delta = abs(candidate_power - reference_power)
            row_power_deltas[quantity] = delta
            power_deltas.append(delta)
        significant_power = max(
            float(reference_order["power_ratio"]),
            float(candidate_order["power_ratio"]),
        )
        if not np.isfinite(significant_power):
            raise ValueError(f"Task41 per-mode power_ratio is nonfinite for {key}")
        is_significant = significant_power >= TASK41_SIGNIFICANT_MODE_POWER
        amplitude_delta = (
            abs(candidate_amplitude - reference_amplitude)
            if reference_representable
            else None
        )
        relative = None
        if is_significant:
            if not reference_representable or not np.isfinite(reference_amplitude + candidate_amplitude):
                raise ValueError(f"Task41 significant mode amplitude is not representable for {key}")
            denominator = max(abs(reference_amplitude), np.finfo(float).tiny)
            relative = float(amplitude_delta / denominator)
            significant_reference.append(reference_amplitude)
            significant_candidate.append(candidate_amplitude)
            significant_relative.append(relative)
        else:
            weak_channels.append(
                {
                    "mode_key": list(key),
                    "representable": reference_representable,
                    "absolute_amplitude_delta": amplitude_delta,
                    "incident_scale": float(incident_scale_reference),
                    "incident_scaled_absolute_delta": (
                        float(amplitude_delta / incident_scale_reference)
                        if amplitude_delta is not None else None
                    ),
                }
            )
        power_rows.append(
            {
                "mode_key": list(key),
                "significant_union_power": significant_power,
                "significant": is_significant,
                "R_absolute_delta": row_power_deltas["R"],
                "T_absolute_delta": row_power_deltas["T"],
                "amplitude_absolute_delta": amplitude_delta,
                "amplitude_relative_delta": relative,
            }
        )
    amplitude_l2_relative = float(
        np.linalg.norm(np.asarray(significant_candidate) - np.asarray(significant_reference))
        / max(float(np.linalg.norm(significant_reference)), np.finfo(float).tiny)
    ) if significant_reference else float("inf")
    power_max = max(power_deltas, default=float("inf"))
    amplitude_max = max(significant_relative, default=float("inf"))
    passed = bool(
        flags_match
        and any(row["significant"] for row in power_rows)
        and amplitude_max <= TASK41_MODE_RELATIVE_LIMIT
        and amplitude_l2_relative <= TASK41_MODE_RELATIVE_LIMIT
        and power_max <= TASK41_MODE_POWER_ABSOLUTE_LIMIT
    )
    return {
        "mode_count": len(reference_keys),
        "physical_boundary_amplitude_coordinate": reference_coordinate,
        "solver_gauges_compared": False,
        "phase_fitting": False,
        "representability_flags_match": flags_match,
        "significant_union_threshold": TASK41_SIGNIFICANT_MODE_POWER,
        "significant_mode_count": sum(bool(row["significant"]) for row in power_rows),
        "significant_amplitude_max_relative": amplitude_max,
        "significant_amplitude_l2_relative": amplitude_l2_relative,
        "significant_amplitude_relative_limit": TASK41_MODE_RELATIVE_LIMIT,
        "per_mode_power_max_absolute_delta": power_max,
        "per_mode_power_absolute_limit": TASK41_MODE_POWER_ABSOLUTE_LIMIT,
        "all_mode_deltas": power_rows,
        "weak_channel_incident_scaled_deltas": weak_channels,
        "pass": passed,
    }


def compare_task41_power_totals(
    reference_port: Mapping[str, Any],
    reference_volume: Mapping[str, Any],
    candidate_output: Mapping[str, Any],
) -> dict[str, Any]:
    reference_values = {
        "R": float(reference_port["R_total"]),
        "T": float(reference_port["T_total"]),
        "A": float(reference_port["A_balance"]),
        "A_volume": float(reference_volume["A_volume_total"]),
    }
    candidate_port = candidate_output.get("port_metrics", {})
    candidate_volume = candidate_output.get("volume_metrics", {})
    candidate_values = {
        "R": float(candidate_port["R_total"]),
        "T": float(candidate_port["T_total"]),
        "A": float(candidate_port["A_balance"]),
        "A_volume": float(candidate_volume["A_volume_total"]),
    }
    deltas = {key: abs(candidate_values[key] - value) for key, value in reference_values.items()}
    return {
        "reference": reference_values,
        "candidate": candidate_values,
        "absolute_deltas": deltas,
        "absolute_limit": TASK41_TOTAL_ABSOLUTE_LIMIT,
        "pass": bool(max(deltas.values()) <= TASK41_TOTAL_ABSOLUTE_LIMIT),
    }


def evaluate_task41_metric_packet(
    packet_json: str | Path,
    *,
    reference_full_field: np.ndarray,
    candidate_full_field: np.ndarray,
    expected_binding_sha256: str,
) -> dict[str, Any]:
    """Recompute FE metric scalars from the worker's hash-bound raw action vectors."""
    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != "task41.p0.a1_a2_metric_packet.v1":
        raise ValueError("Task41 FE metric packet schema is invalid")
    if record.get("a1_binding_sha256") != expected_binding_sha256:
        raise ValueError("Task41 FE metric packet is not bound to the registered A1 evidence")
    arrays_record = record.get("arrays")
    if not isinstance(arrays_record, Mapping):
        raise ValueError("Task41 FE metric packet omits its NPZ manifest")
    npz_path = Path(str(arrays_record.get("path", ""))).resolve()
    if not npz_path.is_file() or _sha256(npz_path) != arrays_record.get("sha256"):
        raise ValueError("Task41 FE metric packet NPZ hash changed")
    reference = np.asarray(reference_full_field, dtype=np.complex128).reshape(-1)
    candidate = np.asarray(candidate_full_field, dtype=np.complex128).reshape(-1)
    if reference.shape != candidate.shape or not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("Task41 A1/A2 full field vectors are malformed")
    with np.load(npz_path, allow_pickle=False) as arrays:
        def get(name: str, *, dtype: Any | None = None) -> np.ndarray:
            item = record.get(name)
            if not isinstance(item, Mapping) or not isinstance(item.get("array_key"), str):
                raise ValueError(f"Task41 FE metric packet omits raw array {name!r}")
            value = np.asarray(arrays[item["array_key"]])
            if list(value.shape) != item.get("shape") or str(value.dtype) != item.get("dtype"):
                raise ValueError(f"Task41 FE metric packet array identity changed for {name}")
            return np.asarray(value, dtype=dtype) if dtype is not None else value

        indices = get("independent_indices", dtype=np.int64)
        a1_slaves = get("a1_mpc_slave_local_rows", dtype=np.int64)
        a2_slaves = get("a2_mpc_slave_local_rows", dtype=np.int64)
        mass_reference = get("mass_reference_applied", dtype=np.complex128)
        mass_difference = get("mass_difference_applied", dtype=np.complex128)
        curl_reference = get("scaled_curl_reference_applied", dtype=np.complex128)
        curl_difference = get("scaled_curl_difference_applied", dtype=np.complex128)
        mpc_packet = record.get("mpc_map_packet")
        if (
            not isinstance(mpc_packet, Mapping)
            or not isinstance(mpc_packet.get("arrays"), Mapping)
        ):
            raise ValueError("Task41 metric packet omits its numeric MPC-map packet")
        mpc_npz_path = Path(str(mpc_packet["arrays"].get("path", ""))).resolve(strict=True)
        if (
            mpc_npz_path.parent != path.parent
            or _sha256(mpc_npz_path) != mpc_packet["arrays"].get("sha256")
        ):
            raise ValueError("Task41 numeric MPC-map packet identity changed or escaped its run")
        mpc_json_path = mpc_npz_path.with_suffix(".json")
        mpc_record = json.loads(mpc_json_path.read_text(encoding="utf-8"))
        mpc_identity = mpc_record.get("mpc_map_identity")
        if (
            not isinstance(mpc_identity, Mapping)
            or mpc_identity.get("schema") != TASK41_MPC_MAP_SCHEMA
            or mpc_identity.get("status") != "PASS"
            or not isinstance(mpc_identity.get("arrays"), Mapping)
        ):
            raise ValueError("Task41 numeric MPC-map packet is not a passing identity")
        mpc_map_recheck: dict[str, Any] = {}
        with np.load(mpc_npz_path, allow_pickle=False) as mpc_arrays:
            for name in ("slaves", "masters", "coefficients", "offsets"):
                facts = mpc_identity["arrays"].get(name)
                if not isinstance(facts, Mapping) or not all(
                    isinstance(facts.get(side), Mapping) for side in ("a1", "a2")
                ):
                    raise ValueError(f"Task41 metric packet omits MPC {name} numeric identity")
                side_values: dict[str, np.ndarray] = {}
                side_checks: dict[str, bool] = {}
                expected_dtype = "complex128" if name == "coefficients" else "int64"
                canonical_dtype = np.dtype("<c16") if name == "coefficients" else np.dtype("<i8")
                for side in ("a1", "a2"):
                    array_name = f"{side}_mpc_map_{name}"
                    array_descriptor = mpc_record.get(array_name)
                    if not isinstance(array_descriptor, Mapping):
                        raise ValueError(f"Task41 MPC packet omits raw array {array_name}")
                    value = np.asarray(mpc_arrays[str(array_descriptor["array_key"])])
                    side_values[side] = value
                    item = facts[side]
                    canonical = np.ascontiguousarray(value, dtype=canonical_dtype)
                    side_checks[side] = bool(
                        str(value.dtype) == expected_dtype
                        and item.get("numeric_dtype") == expected_dtype
                        and item.get("shape") == list(value.shape)
                        and hashlib.sha256(canonical.tobytes()).hexdigest()
                        == item.get("values_sha256")
                    )
                equal = bool(
                    facts["a1"].get("source_dtype") == facts["a2"].get("source_dtype")
                    and np.array_equal(side_values["a1"], side_values["a2"])
                )
                mpc_map_recheck[name] = {
                    "a1_values_rechecked": side_checks["a1"],
                    "a2_values_rechecked": side_checks["a2"],
                    "equal": equal,
                }
                if not all(side_checks.values()) or not equal:
                    raise ValueError(f"Task41 A1/A2 numeric MPC {name} adjacency differs")
    if (
        indices.ndim != 1
        or indices.size == 0
        or np.unique(indices).size != indices.size
        or int(indices.min()) < 0
        or int(indices.max()) >= reference.size
        or mass_reference.shape != indices.shape
        or mass_difference.shape != indices.shape
        or curl_reference.shape != indices.shape
        or curl_difference.shape != indices.shape
    ):
        raise ValueError("Task41 metric packet independent-coordinate layout is invalid")
    if (
        a1_slaves.ndim != 1
        or a2_slaves.ndim != 1
        or not np.array_equal(np.sort(a1_slaves), np.sort(a2_slaves))
        or np.unique(a1_slaves).size != a1_slaves.size
        or np.any(a1_slaves < 0)
        or np.any(a1_slaves >= reference.size)
    ):
        raise ValueError("Task41 A1 MPC slave rows do not match the live A2 map")
    expected_independent = np.setdiff1d(
        np.arange(reference.size, dtype=np.int64), np.unique(a1_slaves)
    )
    if not np.array_equal(np.sort(indices), expected_independent):
        raise ValueError("Task41 metric packet does not cover every independent full-space row")

    reference_independent = reference[indices]
    difference_independent = candidate[indices] - reference_independent

    def square(vector: np.ndarray, applied: np.ndarray) -> float:
        value = np.vdot(vector, applied)
        scale = max(float(np.linalg.norm(vector) * np.linalg.norm(applied)), np.finfo(float).tiny)
        if not np.isfinite(value) or abs(value.imag) > 1.0e-10 * scale or value.real < -1.0e-10 * scale:
            raise ValueError("Task41 FE metric action is not Hermitian positive on the saved field")
        return float(max(0.0, value.real))

    mass_reference_sq = square(reference_independent, mass_reference)
    mass_difference_sq = square(difference_independent, mass_difference)
    curl_reference_sq = square(reference_independent, curl_reference)
    curl_difference_sq = square(difference_independent, curl_difference)
    mass_relative = float(np.sqrt(mass_difference_sq) / max(np.sqrt(mass_reference_sq), np.finfo(float).tiny))
    curl_relative = float(np.sqrt(curl_difference_sq) / max(np.sqrt(curl_reference_sq), np.finfo(float).tiny))
    stored = record.get("metrics", {})
    for key, actual in (
        ("electric_relative_l2", mass_relative),
        ("scaled_curl_relative_l2", curl_relative),
    ):
        if not np.isclose(float(stored.get(key, np.nan)), actual, rtol=1.0e-11, atol=1.0e-13):
            raise ValueError(f"Task41 metric packet stored {key} differs from recomputed algebra")
    return {
        "electric_relative_l2": mass_relative,
        "scaled_curl_relative_l2": curl_relative,
        "electric_reference_norm": float(np.sqrt(mass_reference_sq)),
        "electric_absolute_error_norm": float(np.sqrt(mass_difference_sq)),
        "scaled_curl_reference_norm": float(np.sqrt(curl_reference_sq)),
        "scaled_curl_absolute_error_norm": float(np.sqrt(curl_difference_sq)),
        "limit": TASK41_MODE_RELATIVE_LIMIT,
        "pass": bool(
            mass_relative <= TASK41_MODE_RELATIVE_LIMIT
            and curl_relative <= TASK41_MODE_RELATIVE_LIMIT
        ),
        "operator_reapplied_by_checker": False,
        "raw_action_algebra_recomputed": True,
        "numeric_mpc_map_recheck": {
            "schema": TASK41_MPC_MAP_SCHEMA,
            "checks": mpc_map_recheck,
            "passed": all(
                row["equal"]
                and row["a1_values_rechecked"]
                and row["a2_values_rechecked"]
                for row in mpc_map_recheck.values()
            ),
        },
    }
