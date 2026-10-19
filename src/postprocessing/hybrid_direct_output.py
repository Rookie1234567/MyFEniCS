"""Shared sampled-field validation and Task42 Hybrid-direct payload writer.

The validator derives array shape from the coordinates supplied by the actual
run.  It does not assume a particular sample-grid size or diffraction cutoff.
Task39 keeps its historical file name, metadata, and additional frozen-shape
checks; Task42 writes a separate identity-bound artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


def _array_sha256(array: np.ndarray) -> str:
    value = np.asarray(array)
    digest = hashlib.sha256()
    if value.flags.c_contiguous:
        digest.update(memoryview(value).cast("B"))
    else:
        iterator = np.nditer(
            value,
            flags=["external_loop", "buffered"],
            op_flags=["readonly"],
            order="C",
            buffersize=65536,
        )
        for chunk in iterator:
            digest.update(np.ascontiguousarray(chunk).view(np.uint8))
    return digest.hexdigest()


def _file_sha256(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("output metadata contains a non-finite float")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported output metadata value {type(value).__name__}")


def _external_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row["side"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def validate_hybrid_sampled_field_arrays(
    *,
    sample_x: Any,
    sample_y: Any,
    sample_z: Any,
    electric: Any,
    magnetic: Any,
    require_monotonic_coordinates: bool = True,
) -> dict[str, Any]:
    """Validate finite complex vector fields against their declared coordinates."""

    coordinates = {
        "x_nm": np.asarray(sample_x, dtype=np.float64),
        "y_nm": np.asarray(sample_y, dtype=np.float64),
        "z_nm": np.asarray(sample_z, dtype=np.float64),
    }
    for name, axis in coordinates.items():
        if axis.ndim != 1 or axis.size == 0 or not np.all(np.isfinite(axis)):
            raise ValueError(f"{name} must be a nonempty finite vector")
        if (
            require_monotonic_coordinates
            and axis.size > 1
            and np.any(np.diff(axis) <= 0.0)
        ):
            raise ValueError(f"{name} must be strictly increasing")
    expected = (
        int(coordinates["z_nm"].size),
        int(coordinates["y_nm"].size),
        int(coordinates["x_nm"].size),
        3,
    )
    fields = {
        "E_V_per_m": np.asarray(electric, dtype=np.complex128),
        "H_A_per_m": np.asarray(magnetic, dtype=np.complex128),
    }
    for name, array in fields.items():
        if array.shape != expected:
            raise ValueError(
                f"{name} layout {array.shape} does not match actual sample coordinates {expected}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{name} contains non-finite values")
    return {
        **coordinates,
        **fields,
        "shape_z_y_x_component": list(expected),
        "layout": "sample_z,sample_y,sample_x,vector_component_xyz",
    }


def validate_external_key_rows(
    inventory: Mapping[str, Any], rows: Any
) -> list[dict[str, Any]]:
    """Require a one-to-one actual record for every declared external key."""

    expected_rows = inventory.get("keys")
    if not isinstance(expected_rows, list) or not isinstance(rows, list):
        raise TypeError("full external key inventory and actual rows are required")
    if not expected_rows:
        raise ValueError("full external key inventory must not be empty")
    expected = [_external_key(row) for row in expected_rows if isinstance(row, Mapping)]
    actual = [_external_key(row) for row in rows if isinstance(row, Mapping)]
    if len(expected) != len(expected_rows) or len(actual) != len(rows):
        raise ValueError("external key rows contain a non-mapping entry")
    if len(set(expected)) != len(expected) or len(set(actual)) != len(actual):
        raise ValueError("external key rows contain duplicate keys")
    if set(expected) != set(actual):
        raise ValueError(
            "actual external key rows differ from the complete declared inventory"
        )
    return [_json_value(row) for row in rows]


def validate_external_auxiliary_mapping(
    rows: Any,
    external_auxiliary_amplitudes: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind each side-local q slot to the producer's actual order-row indices."""

    if not isinstance(rows, list):
        raise TypeError("external diffraction rows must be a list")
    q_arrays = {
        side: np.asarray(external_auxiliary_amplitudes.get(side), dtype=np.complex128)
        for side in ("bottom", "top")
    }
    if any(array.ndim != 1 for array in q_arrays.values()):
        raise ValueError("Task42 side auxiliary amplitudes must be one-dimensional")
    global_indices: list[int] = []
    by_side: dict[str, dict[int, tuple[tuple[int, int, int, int], int]]] = {
        "bottom": {},
        "top": {},
    }
    side_code = {"bottom": 0, "top": 1}
    pol_code = {"s": 0, "p": 1}
    row_global_indices: list[int] = []
    row_local_indices: list[int] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"external diffraction row {row_index} is not a mapping")
        side = row.get("side")
        if side not in side_code:
            raise ValueError(f"external diffraction row {row_index} has an invalid side")
        global_index = row.get("auxiliary_index")
        local_index = row.get("local_auxiliary_index")
        if type(global_index) is not int or global_index < 0:
            raise ValueError(
                f"external diffraction row {row_index} has an invalid auxiliary_index"
            )
        if type(local_index) is not int or not 0 <= local_index < q_arrays[side].size:
            raise ValueError(
                f"external diffraction row {row_index} has an invalid local_auxiliary_index"
            )
        polarization = row.get("polarization")
        if polarization not in pol_code:
            raise ValueError(
                f"external diffraction row {row_index} has an invalid polarization"
            )
        key = (
            side_code[side],
            int(row["m"]),
            int(row["n"]),
            pol_code[polarization],
        )
        if local_index in by_side[side]:
            raise ValueError(
                f"Task42 {side} external rows repeat local_auxiliary_index {local_index}"
            )
        by_side[side][local_index] = (key, global_index)
        global_indices.append(global_index)
        row_global_indices.append(global_index)
        row_local_indices.append(local_index)
    total = len(rows)
    if sorted(global_indices) != list(range(total)):
        raise ValueError("Task42 auxiliary_index values must cover one unique contiguous range")
    mapping_arrays: dict[str, np.ndarray] = {
        "external_keys_auxiliary_index": np.asarray(row_global_indices, dtype=np.int64),
        "external_keys_local_auxiliary_index": np.asarray(row_local_indices, dtype=np.int64),
    }
    for side in ("bottom", "top"):
        expected_indices = set(range(q_arrays[side].size))
        if set(by_side[side]) != expected_indices:
            raise ValueError(
                f"Task42 {side} local_auxiliary_index values do not cover the q vector"
            )
        ordered_rows = [by_side[side][index] for index in range(q_arrays[side].size)]
        mapping_arrays[f"{side}_q_external_keys_m_n_pol"] = np.asarray(
            [key[1:] for key, _global_index in ordered_rows], dtype=np.int64
        ).reshape((-1, 3))
        mapping_arrays[f"{side}_q_external_auxiliary_index"] = np.asarray(
            [global_index for _key, global_index in ordered_rows],
            dtype=np.int64,
        )
    return mapping_arrays


def write_task42_hybrid_direct_payload(
    *,
    run_directory: str | Path,
    fields: Mapping[str, Any],
    identity: Mapping[str, Any],
    external_mode_inventory: Mapping[str, Any],
    external_diffraction_orders: Any,
    modal_amplitudes: Any,
    external_auxiliary_amplitudes: Mapping[str, Any],
) -> dict[str, Any]:
    """Write a Task42-only payload and sidecar without overwriting evidence."""

    required_identity = (
        "model_id",
        "run_id",
        "comparison_group",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "source_sha",
        "material_identity_sha256",
        "material_record_sha256",
        "canonical_export_prefix",
    )
    if any(not isinstance(identity.get(key), str) or not identity[key] for key in required_identity):
        raise ValueError("Task42 output identity is incomplete")
    if identity["canonical_export_prefix"] != "task42_hybrid_direct":
        raise ValueError("Task42 output canonical prefix is invalid")
    if (
        type(identity.get("wavelength_nm")) not in (int, float)
        or not math.isfinite(float(identity["wavelength_nm"]))
        or type(identity.get("requested_modes_per_direction")) is not int
        or identity["requested_modes_per_direction"] < 1
    ):
        raise ValueError("Task42 output wavelength or requested mode count is invalid")
    inventory_identity = external_mode_inventory.get("identity")
    if (
        not isinstance(inventory_identity, Mapping)
        or identity.get("external_mode_inventory_identity") != inventory_identity
    ):
        raise ValueError(
            "Task42 output identity does not match the complete external-mode inventory"
        )
    inventory_sha256 = inventory_identity.get("inventory_sha256")
    if (
        not isinstance(inventory_sha256, str)
        or len(inventory_sha256) != 64
        or inventory_sha256.lower() != inventory_sha256
        or any(character not in "0123456789abcdef" for character in inventory_sha256)
    ):
        raise ValueError("Task42 external-mode inventory SHA256 is invalid")
    inventory_payload = {
        str(key): value
        for key, value in external_mode_inventory.items()
        if key != "identity"
    }
    computed_inventory_sha256 = hashlib.sha256(
        json.dumps(
            _json_value(inventory_payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    inventory_keys = external_mode_inventory.get("keys")
    if (
        inventory_sha256 != computed_inventory_sha256
        or inventory_identity.get("schema")
        != "task42.a2.external-mode-inventory-identity.v1"
        or inventory_identity.get("model_id") != identity["model_id"]
        or inventory_identity.get("material_identity_sha256")
        != identity["material_identity_sha256"]
        or inventory_identity.get("wavelength_nm")
        != identity["wavelength_nm"]
        or inventory_identity.get("key_count") != len(inventory_keys or [])
        or inventory_identity.get("selection")
        != inventory_payload.get("selection")
        or external_mode_inventory.get("count") != len(inventory_keys or [])
    ):
        raise ValueError(
            "Task42 output provenance differs from the canonical external-mode inventory"
        )
    for key in (
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "material_identity_sha256",
        "material_record_sha256",
    ):
        value = identity[key]
        if len(value) != 64 or value.lower() != value or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"Task42 output identity {key} is not lowercase SHA256")
    source_sha = identity["source_sha"]
    if len(source_sha) != 40 or source_sha.lower() != source_sha or any(
        character not in "0123456789abcdef" for character in source_sha
    ):
        raise ValueError("Task42 output source_sha is not a full lowercase Git SHA")
    validated_fields = validate_hybrid_sampled_field_arrays(
        sample_x=fields["x_nm"],
        sample_y=fields["y_nm"],
        sample_z=fields["z_nm"],
        electric=fields["E_V_per_m"],
        magnetic=fields["H_A_per_m"],
    )
    arrays = {
        key: np.asarray(validated_fields[key])
        for key in ("x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m")
    }
    arrays["modal_amplitudes"] = np.asarray(modal_amplitudes, dtype=np.complex128)
    arrays["bottom_q"] = np.asarray(
        external_auxiliary_amplitudes["bottom"], dtype=np.complex128
    )
    arrays["top_q"] = np.asarray(
        external_auxiliary_amplitudes["top"], dtype=np.complex128
    )
    if arrays["modal_amplitudes"].ndim != 1 or any(
        arrays[key].ndim != 1 for key in ("bottom_q", "top_q")
    ):
        raise ValueError("Task42 modal and auxiliary arrays must be one-dimensional")
    if arrays["modal_amplitudes"].size != 2 * int(
        identity["requested_modes_per_direction"]
    ):
        raise ValueError("Task42 modal output length differs from the requested two-way mode count")
    external_rows = validate_external_key_rows(
        external_mode_inventory, external_diffraction_orders
    )
    arrays.update(
        validate_external_auxiliary_mapping(
            external_diffraction_orders, external_auxiliary_amplitudes
        )
    )
    key_rows = [_external_key(row) for row in external_diffraction_orders]
    side_code = {"bottom": 0, "top": 1}
    pol_code = {"s": 0, "p": 1}
    if any(side not in side_code or pol not in pol_code for side, _, _, pol in key_rows):
        raise ValueError("Task42 output encountered an unsupported external side/polarization")
    arrays["external_keys_side_m_n_pol"] = np.asarray(
        [
            (side_code[side], m, n, pol_code[pol])
            for side, m, n, pol in key_rows
        ],
        dtype=np.int64,
    )
    if any(not np.all(np.isfinite(array)) for array in arrays.values()):
        raise ValueError("Task42 output contains a non-finite array")

    root = Path(run_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    payload_path = root / "task42_hybrid_direct_fields.npz"
    identity_path = root / "task42_hybrid_direct_identity.json"
    # Exclusive creation prevents a rerun from replacing a previous result.
    with payload_path.open("xb") as stream:
        np.savez(stream, **arrays)
    array_inventory = {
        key: {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "bytes": int(array.nbytes),
            "sha256": _array_sha256(array),
        }
        for key, array in arrays.items()
    }
    sidecar = {
        "schema": "task42.hybrid-direct-sampled-fields.v1",
        "identity": _json_value(identity),
        "payload": {
            "path": payload_path.name,
            "sha256": _file_sha256(payload_path),
            "bytes": payload_path.stat().st_size,
            "arrays": array_inventory,
            "coordinate_derived_shape": validated_fields.get(
                "shape_z_y_x_component"
            ),
            "layout": validated_fields.get("layout"),
        },
        "external_mode_inventory": _json_value(external_mode_inventory),
        "external_diffraction_orders": external_rows,
    }
    with identity_path.open("x", encoding="utf-8") as stream:
        json.dump(sidecar, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
        stream.flush()
    return {
        "schema": sidecar["schema"],
        "payload_path": str(payload_path),
        "payload_sha256": sidecar["payload"]["sha256"],
        "identity_path": str(identity_path),
        "identity_sha256": _file_sha256(identity_path),
        "external_key_count": len(key_rows),
        "layout": validated_fields.get("layout"),
        "shape_z_y_x_component": validated_fields.get("shape_z_y_x_component"),
    }


def write_task42_hybrid_direct_payload_collectively(
    comm: Any,
    *,
    run_directory: str | Path,
    sample_x: Any,
    sample_y: Any,
    sample_z: Any,
    electric: Any,
    magnetic: Any,
    identity: Mapping[str, Any],
    external_mode_inventory: Mapping[str, Any],
    external_diffraction_orders: Any,
    modal_amplitudes: Any,
    external_auxiliary_amplitudes: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate locally, refuse collectively, then let rank zero write once."""

    validated_fields = None
    local_error = None
    try:
        validated_fields = validate_hybrid_sampled_field_arrays(
            sample_x=sample_x,
            sample_y=sample_y,
            sample_z=sample_z,
            electric=electric,
            magnetic=magnetic,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        # Local validation must reach the matching gather.
        local_error = f"{type(exc).__name__}: {exc}"
    local_errors = comm.allgather(local_error)
    failures = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(local_errors)
        if error is not None
    ]
    if failures:
        raise ValueError(
            "Task42 sampled-field validation failed collectively: "
            + "; ".join(failures)
        )

    writer_result = None
    if comm.rank == 0:
        try:
            writer_result = {
                "ok": True,
                "descriptor": write_task42_hybrid_direct_payload(
                    run_directory=run_directory,
                    fields=validated_fields,
                    identity=identity,
                    external_mode_inventory=external_mode_inventory,
                    external_diffraction_orders=external_diffraction_orders,
                    modal_amplitudes=modal_amplitudes,
                    external_auxiliary_amplitudes=external_auxiliary_amplitudes,
                ),
            }
        except BaseException as exc:  # noqa: BLE001 - root failure is broadcast
            writer_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    writer_result = comm.bcast(writer_result, root=0)
    if not isinstance(writer_result, Mapping) or writer_result.get("ok") is not True:
        raise RuntimeError(
            "Task42 Hybrid output writer failed: "
            + str(
                writer_result.get("error")
                if isinstance(writer_result, Mapping)
                else "missing root receipt"
            )
        )
    return {
        "fields": validated_fields,
        "descriptor": dict(writer_result["descriptor"]),
    }


__all__ = [
    "validate_external_auxiliary_mapping",
    "validate_external_key_rows",
    "validate_hybrid_sampled_field_arrays",
    "write_task42_hybrid_direct_payload",
    "write_task42_hybrid_direct_payload_collectively",
]
