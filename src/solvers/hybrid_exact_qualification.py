"""Current-layout exact qualification primitives.

This module contains the reusable, benchmark-independent pieces of the V6
qualification path.  Owner-row arrays are numeric values in the PETSc
ownership order; no array named ``*_owner_rows.npy`` is interpreted as a row
number map.  All distributed transfers use PETSc ownership and reductions;
the module never gathers finite-element-sized numeric data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

__all__ = (
    "ExactQualificationContractError",
    "hash_file_sha256",
    "hash_array_bytes_sha256",
    "rank_local_shard_binding_sha256",
    "validate_owner_vector_descriptor",
    "validate_canonical_layout",
    "canonical_values_roundtrip_error",
    "make_live_canonical_roundtrip_callback",
    "make_live_persisted_canonical_roundtrip_callback",
    "load_owner_local_vector",
    "load_owner_local_vector_collective",
    "LoadedExactQualificationRHS",
    "load_and_condense_exact_rhs",
    "run_exact_qualification_family",
    "gamma_layout_packet_identity",
    "make_current_exact_packet_identity_provider",
    "make_current_exact_solution_packet_consumer",
    "write_current_exact_solution_packet",
    "make_current_exact_packet_writer",
    "aggregate_exact_packet_manifests",
    "validate_distributed_owner_vector",
    "run_exact_interface_fgmres",
)


V5_VECTOR_SCHEMA = "task040.v5.current_bare_f_authority_vector.v1"
V5_VECTOR_SIDE = "bottom"


class ExactQualificationContractError(ValueError):
    """A current-layout vector or exact-qualification contract is invalid."""


def hash_file_sha256(path: str | Path) -> str:
    """Hash one file without interpreting its contents."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_array_bytes_sha256(values: np.ndarray) -> str:
    """Hash contiguous numeric bytes, matching the packet writer contract.

    A ``.npy`` file hash includes the NumPy header and is deliberately not the
    identity stored in the V5 vector metadata.  This helper is kept separate
    from :func:`hash_file_sha256` so a caller cannot accidentally compare the
    two different contracts.
    """

    return hashlib.sha256(np.ascontiguousarray(values).tobytes(order="C")).hexdigest()


def _is_hex_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_hex_commit(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _descriptor_values(
    descriptor: Mapping[str, Any], key: str
) -> tuple[tuple[str, Any], ...]:
    """Return every present copy of one provenance/identity field."""

    locations: list[tuple[str, Any]] = []
    if key in descriptor:
        locations.append((f"descriptor.{key}", descriptor[key]))
    for container_name in ("source_provenance", "provenance"):
        provenance = descriptor.get(container_name)
        if isinstance(provenance, Mapping) and key in provenance:
            locations.append((f"{container_name}.{key}", provenance[key]))
    source_definition = descriptor.get("source_definition")
    if isinstance(source_definition, Mapping):
        if key in source_definition:
            locations.append((f"source_definition.{key}", source_definition[key]))
        for container_name in ("source_provenance", "provenance"):
            provenance = source_definition.get(container_name)
            if isinstance(provenance, Mapping) and key in provenance:
                locations.append(
                    (f"source_definition.{container_name}.{key}", provenance[key])
                )
    return tuple(locations)


def _descriptor_value(descriptor: Mapping[str, Any], key: str) -> Any:
    values = _descriptor_values(descriptor, key)
    return values[0][1] if values else None


def _consistent_descriptor_value(
    descriptor: Mapping[str, Any], key: str
) -> Any:
    values = _descriptor_values(descriptor, key)
    if not values:
        return None
    first = values[0][1]
    if any(value != first for _location, value in values[1:]):
        details = ", ".join(f"{location}={value!r}" for location, value in values)
        raise ExactQualificationContractError(
            f"descriptor copies of {key} disagree: {details}"
        )
    return first


def _descriptor_source_candidates(descriptor: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return all supported locations of the committed source identity."""

    candidates: list[Any] = []
    for key in ("source_sha", "committed_source_sha"):
        candidates.extend(value for _location, value in _descriptor_values(descriptor, key))
    return tuple(candidates)


def _json_safe_binding(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_binding(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_binding(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe_binding(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe_binding(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"shard binding is not JSON-safe: {type(value)!r}")


def rank_local_shard_binding_sha256(
    *,
    rank: int,
    label: str,
    role: str,
    source_definition_sha256: str,
    key_set_sha256: str,
    canonical_layout_sha256: str,
    identity: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
    bare_f_operator_hash: str | None,
    rhs_repeat: Mapping[str, Any] | None,
) -> str:
    """Recompute the producer's rank-local shard binding payload.

    The field names and canonical JSON serialization intentionally match the
    existing V5 packet writer.  This is an identity hash over metadata only;
    numeric values are validated separately from their contiguous byte hashes.
    """

    payload = {
        "rank": int(rank),
        "label": str(label),
        "role": str(role),
        "source_definition_sha256": str(source_definition_sha256),
        "canonical_key_set_sha256": str(key_set_sha256),
        "canonical_layout_sha256": str(canonical_layout_sha256),
        "bare_f_operator_hash": bare_f_operator_hash,
        "source_provenance": _json_safe_binding(dict(source_provenance)),
        "ownership_range": _json_safe_binding(identity.get("ownership_range")),
        "array_sha256": _json_safe_binding(identity.get("array_sha256")),
        "owner_row_array_sha256": _json_safe_binding(
            identity.get("owner_row_array_sha256")
        ),
        "canonical_to_current_roundtrip_relative": _json_safe_binding(
            identity.get("canonical_to_current_roundtrip_relative")
        ),
        "rhs_repeat": _json_safe_binding(dict(rhs_repeat)) if rhs_repeat else None,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _expected_field(
    descriptor: Mapping[str, Any],
    key: str,
    expected: Any,
) -> None:
    if expected is None:
        return
    observed = _descriptor_value(descriptor, key)
    if observed != expected:
        raise ExactQualificationContractError(
            f"{key} identity mismatch: observed={observed!r}, expected={expected!r}"
        )


def validate_owner_vector_descriptor(
    descriptor: Mapping[str, Any],
    *,
    expected_label: str | None = None,
    expected_role: str = "rhs",
    expected_schema: str | None = V5_VECTOR_SCHEMA,
    expected_side: str | None = V5_VECTOR_SIDE,
    expected_source_sha256: str | None = None,
    expected_input_sha256: str | None = None,
    expected_physical_model_sha256: str | None = None,
    expected_selected_manifest_sha256: str | None = None,
    expected_resolved_config_sha256: str | None = None,
    expected_operator_hash: str | None = None,
    expected_layout_sha256: str | None = None,
    expected_canonical_key_set_sha256: str | None = None,
    expected_global_size: int | None = None,
    expected_ownership_range: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Validate metadata for one current PETSc owner-local numeric vector.

    This function does not open an array.  It returns only normalized scalar
    metadata so callers can perform a small collective ownership audit before
    constructing a PETSc Vec.
    """

    if not isinstance(descriptor, Mapping):
        raise ExactQualificationContractError("vector descriptor is not a mapping")
    required = (
        "schema",
        "side",
        "label",
        "role",
        "dtype",
        "global_size",
        "local_size",
        "ownership_range",
        "array_path",
        "array_sha256",
        "owner_row_array_path",
        "owner_row_array_sha256",
        "canonical_layout_path",
        "canonical_layout_sha256",
        "canonical_key_set_sha256",
        "canonical_key_count_local",
        "global_sha256",
        "source_definition_sha256",
        "rank_local_shard_binding_sha256",
        "canonical_to_current_roundtrip_relative",
        "vector_identity",
        "raw_global_row_remap",
    )
    missing = [key for key in required if key not in descriptor]
    if missing:
        raise ExactQualificationContractError(
            f"vector descriptor is missing fields: {missing}"
        )
    if expected_schema is not None and descriptor["schema"] != expected_schema:
        raise ExactQualificationContractError(
            f"vector descriptor schema is invalid: {descriptor['schema']!r}"
        )
    if expected_side is not None and descriptor["side"] != expected_side:
        raise ExactQualificationContractError(
            f"vector descriptor side is invalid: {descriptor['side']!r}"
        )
    if descriptor["raw_global_row_remap"] is not False:
        raise ExactQualificationContractError(
            "owner vector must not use raw global-row remapping"
        )
    label = descriptor["label"]
    role = descriptor["role"]
    if not isinstance(label, str) or not label:
        raise ExactQualificationContractError("vector descriptor label is invalid")
    if not isinstance(role, str) or role != expected_role:
        raise ExactQualificationContractError(
            f"vector descriptor role is invalid: {role!r}"
        )
    if expected_label is not None and label != expected_label:
        raise ExactQualificationContractError(
            f"vector label mismatch: observed={label!r}, expected={expected_label!r}"
        )
    if descriptor["dtype"] != "complex128":
        raise ExactQualificationContractError("current RHS dtype must be complex128")
    try:
        global_size = int(descriptor["global_size"])
        local_size = int(descriptor["local_size"])
        ownership = tuple(int(value) for value in descriptor["ownership_range"])
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "vector size or ownership metadata is not integral"
        ) from exc
    if global_size <= 0 or local_size < 0 or len(ownership) != 2:
        raise ExactQualificationContractError("vector size or ownership is invalid")
    first, last = ownership
    if first < 0 or last < first or last > global_size:
        raise ExactQualificationContractError("vector ownership is out of bounds")
    if last - first != local_size:
        raise ExactQualificationContractError(
            "vector local_size does not equal ownership_range length"
        )
    array_sha256 = descriptor["array_sha256"]
    if not _is_hex_sha256(array_sha256):
        raise ExactQualificationContractError("array_sha256 is not a 64-digit hex digest")
    array_path = descriptor["array_path"]
    if not isinstance(array_path, str) or not array_path.endswith(".npy"):
        raise ExactQualificationContractError("array_path must name a .npy file")
    owner_row_path = descriptor.get("owner_row_array_path")
    if not isinstance(owner_row_path, str) or not owner_row_path.endswith(".npy"):
        raise ExactQualificationContractError(
            "owner_row_array_path must name a .npy file"
        )
    owner_row_sha256 = descriptor["owner_row_array_sha256"]
    if not _is_hex_sha256(owner_row_sha256):
        raise ExactQualificationContractError(
            "owner_row_array_sha256 is not a 64-digit hex digest"
        )
    canonical_layout_path = descriptor["canonical_layout_path"]
    if not isinstance(canonical_layout_path, str) or not canonical_layout_path.endswith(
        ".json"
    ):
        raise ExactQualificationContractError(
            "canonical_layout_path must name a JSON file"
        )
    canonical_layout_sha256 = descriptor["canonical_layout_sha256"]
    if not _is_hex_sha256(canonical_layout_sha256):
        raise ExactQualificationContractError(
            "canonical_layout_sha256 is not a 64-digit hex digest"
        )
    canonical_key_set_sha256 = descriptor["canonical_key_set_sha256"]
    if not _is_hex_sha256(canonical_key_set_sha256):
        raise ExactQualificationContractError(
            "canonical_key_set_sha256 is not a 64-digit hex digest"
        )
    global_sha256 = descriptor["global_sha256"]
    if not _is_hex_sha256(global_sha256):
        raise ExactQualificationContractError(
            "global_sha256 is not a 64-digit hex digest"
        )
    source_definition_sha256 = descriptor["source_definition_sha256"]
    if not _is_hex_sha256(source_definition_sha256):
        raise ExactQualificationContractError(
            "source_definition_sha256 is not a 64-digit hex digest"
        )
    rank_local_binding_sha256 = descriptor["rank_local_shard_binding_sha256"]
    if not _is_hex_sha256(rank_local_binding_sha256):
        raise ExactQualificationContractError(
            "rank_local_shard_binding_sha256 is not a 64-digit hex digest"
        )
    try:
        canonical_roundtrip = float(
            descriptor["canonical_to_current_roundtrip_relative"]
        )
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "canonical_to_current_roundtrip_relative is not numeric"
        ) from exc
    if not np.isfinite(canonical_roundtrip) or canonical_roundtrip < 0.0:
        raise ExactQualificationContractError(
            "canonical_to_current_roundtrip_relative is invalid"
        )
    if canonical_roundtrip > 1.0e-12:
        raise ExactQualificationContractError(
            "canonical_to_current_roundtrip_relative exceeds 1e-12"
        )
    source_definition = descriptor.get("source_definition")
    if not isinstance(source_definition, Mapping):
        raise ExactQualificationContractError("source_definition is not a mapping")
    if source_definition.get("source_definition_sha256") != source_definition_sha256:
        raise ExactQualificationContractError(
            "source_definition_sha256 does not match source_definition"
        )
    rhs_repeat = source_definition.get("rhs_repeat")
    if not isinstance(rhs_repeat, Mapping):
        raise ExactQualificationContractError("source_definition.rhs_repeat is missing")
    try:
        repeat_relative_difference = float(rhs_repeat["relative_difference"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "source_definition.rhs_repeat.relative_difference is missing"
        ) from exc
    if (
        rhs_repeat.get("pass") is not True
        or not np.isfinite(repeat_relative_difference)
        or repeat_relative_difference < 0.0
        or repeat_relative_difference > 1.0e-12
    ):
        raise ExactQualificationContractError(
            "source_definition.rhs_repeat does not pass the 1e-12 repeat gate"
        )
    try:
        canonical_key_count_local = int(descriptor["canonical_key_count_local"])
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "canonical_key_count_local is not integral"
        ) from exc
    if canonical_key_count_local < 0:
        raise ExactQualificationContractError("canonical key count is negative")
    if (
        expected_canonical_key_set_sha256 is not None
        and canonical_key_set_sha256 != expected_canonical_key_set_sha256
    ):
        raise ExactQualificationContractError(
            "canonical_key_set_sha256 does not match the live authority"
        )
    if descriptor.get("owner_row_order") != "petsc_current_ownership_range":
        raise ExactQualificationContractError(
            "vector owner_row_order is not the current PETSc ownership contract"
        )
    if expected_source_sha256 is not None and expected_source_sha256 not in (
        *_descriptor_source_candidates(descriptor),
    ):
        raise ExactQualificationContractError(
            "source_sha identity mismatch: observed="
            f"{_descriptor_source_candidates(descriptor)!r}, "
            f"expected={expected_source_sha256!r}"
        )
    source_candidates = _descriptor_source_candidates(descriptor)
    if not source_candidates or any(not _is_hex_commit(value) for value in source_candidates):
        raise ExactQualificationContractError(
            "source provenance must contain a 40-hex committed source SHA"
        )
    for identity_key in (
        "input_sha256",
        "physical_model_sha256",
        "selected_manifest_sha256",
        "selected_identity_sha256",
        "resolved_config_sha256",
    ):
        identity_value = _consistent_descriptor_value(descriptor, identity_key)
        if not _is_hex_sha256(identity_value):
            raise ExactQualificationContractError(
                f"source provenance field {identity_key} is not a SHA256 digest"
            )
    for identity_key in (
        "input_sha256",
        "physical_model_sha256",
        "selected_manifest_sha256",
        "selected_identity_sha256",
        "resolved_config_sha256",
        "bare_f_operator_hash",
        "canonical_layout_sha256",
        "canonical_key_set_sha256",
    ):
        _consistent_descriptor_value(descriptor, identity_key)
    source_candidates = _descriptor_source_candidates(descriptor)
    if len(set(source_candidates)) != 1:
        raise ExactQualificationContractError(
            "source provenance copies do not agree across descriptor locations"
        )
    operator_hash = _consistent_descriptor_value(descriptor, "bare_f_operator_hash")
    if not _is_hex_sha256(operator_hash):
        raise ExactQualificationContractError(
            "bare_f_operator_hash is not a SHA256 digest"
        )
    _expected_field(descriptor, "input_sha256", expected_input_sha256)
    _expected_field(
        descriptor,
        "physical_model_sha256",
        expected_physical_model_sha256,
    )
    _expected_field(
        descriptor,
        "selected_manifest_sha256",
        expected_selected_manifest_sha256,
    )
    _expected_field(
        descriptor,
        "resolved_config_sha256",
        expected_resolved_config_sha256,
    )
    _expected_field(descriptor, "bare_f_operator_hash", expected_operator_hash)
    _expected_field(descriptor, "canonical_layout_sha256", expected_layout_sha256)
    if expected_global_size is not None and global_size != int(expected_global_size):
        raise ExactQualificationContractError("vector global_size does not match expected")
    if expected_ownership_range is not None and ownership != tuple(
        int(value) for value in expected_ownership_range
    ):
        raise ExactQualificationContractError(
            "vector ownership_range does not match expected"
        )
    vector_identity = descriptor["vector_identity"]
    if not isinstance(vector_identity, Mapping):
        raise ExactQualificationContractError("vector_identity is not a mapping")
    identity_fields = (
        "array_sha256",
        "canonical_key_count_local",
        "canonical_key_set_sha256",
        "dtype",
        "global_size",
        "local_size",
        "owner_row_array_sha256",
        "owner_row_order",
        "ownership_range",
        "raw_global_row_remap",
        "global_sha256",
        "canonical_to_current_roundtrip_relative",
    )
    for field in identity_fields:
        if vector_identity.get(field) != descriptor.get(field):
            raise ExactQualificationContractError(
                f"vector_identity.{field} does not match the descriptor"
            )
    return {
        "label": label,
        "role": role,
        "dtype": "complex128",
        "global_size": global_size,
        "local_size": local_size,
        "ownership_range": [first, last],
        "array_path": array_path,
        "array_sha256": array_sha256,
        "owner_row_array_path": owner_row_path,
        "owner_row_array_sha256": owner_row_sha256,
        "owner_row_values_not_row_ids": True,
        "schema": descriptor["schema"],
        "side": descriptor["side"],
        "owner_row_order": "petsc_current_ownership_range",
        "canonical_layout_path": canonical_layout_path,
        "canonical_layout_sha256": canonical_layout_sha256,
        "canonical_key_set_sha256": canonical_key_set_sha256,
        "canonical_key_count_local": canonical_key_count_local,
        "global_sha256": global_sha256,
        "source_definition_sha256": source_definition_sha256,
        "rank_local_shard_binding_sha256": rank_local_binding_sha256,
        "canonical_to_current_roundtrip_relative": canonical_roundtrip,
        "bare_f_operator_hash": operator_hash,
        "source_sha": source_candidates[0],
        "source_provenance": {
            key: _consistent_descriptor_value(descriptor, key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
                "source_sha",
            )
        },
        "source_definition": dict(source_definition),
        "rhs_repeat": dict(rhs_repeat),
    }


def _canonical_key_token(value: Any) -> str:
    """Normalize one persisted canonical token without changing its meaning."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "canonical layout contains a non-JSON-safe key"
        ) from exc


def _canonical_key_order_sha256(tokens: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(tokens).encode("utf-8")).hexdigest()


def _canonical_key_set_sha256(tokens: Sequence[str]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(tokens)).encode("utf-8")
    ).hexdigest()


def make_live_canonical_roundtrip_callback(
    system: Any,
    *,
    canonical_packets_for_vector: Callable[..., Any],
    canonical_to_current_roundtrip_relative: Callable[..., float],
    frozen_tokens: Sequence[Any],
    frozen_values: np.ndarray,
    tolerance: float = 1.0e-12,
) -> Callable[[Mapping[str, Any], PETSc.Vec, np.ndarray], float]:
    """Build the production live-key callback used by the owner-vector loader.

    The callback first asks the live current-layout implementation for its
    canonical packets, then compares both token order and values with the
    persisted frozen packet.  Only after that identity check does it call the
    live canonical-to-current round-trip routine.  This keeps a loader caller
    from accidentally replacing a physical reconstruction with a raw row
    comparison while remaining easy to exercise with a tiny system adapter.
    """

    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "live canonical roundtrip tolerance is not numeric"
        ) from exc
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ExactQualificationContractError(
            "live canonical roundtrip tolerance is invalid"
        )
    expected_tokens = tuple(_canonical_key_token(value) for value in frozen_tokens)
    expected_values = np.asarray(frozen_values, dtype=np.complex128).copy()
    if expected_values.ndim != 1 or not np.isfinite(expected_values).all():
        raise ExactQualificationContractError(
            "frozen canonical values are not a finite vector"
        )
    if len(expected_tokens) != expected_values.size:
        raise ExactQualificationContractError(
            "frozen canonical token/value lengths differ"
        )

    def callback(
        _layout_audit: Mapping[str, Any],
        loaded_vector: PETSc.Vec,
        persisted_values: np.ndarray,
    ) -> float:
        try:
            layout_tokens = tuple(
                _canonical_key_token(value)
                for value in _layout_audit["canonical_tokens"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExactQualificationContractError(
                "persisted canonical layout tokens are unavailable"
            ) from exc
        if layout_tokens != expected_tokens:
            raise ExactQualificationContractError(
                "persisted canonical layout tokens differ from the frozen packet"
            )
        live_result = canonical_packets_for_vector(system, loaded_vector)
        if not isinstance(live_result, tuple) or len(live_result) < 2:
            raise ExactQualificationContractError(
                "live canonical packet API returned no token/value pair"
            )
        live_tokens = tuple(
            _canonical_key_token(value) for value in live_result[0]
        )
        live_values = np.asarray(live_result[1], dtype=np.complex128)
        if live_tokens != expected_tokens:
            raise ExactQualificationContractError(
                "live canonical tokens differ from the frozen packet"
            )
        if (
            live_values.ndim != 1
            or live_values.shape != expected_values.shape
            or not np.isfinite(live_values).all()
            or not np.allclose(
                live_values,
                expected_values,
                rtol=0.0,
                atol=tolerance,
            )
        ):
            raise ExactQualificationContractError(
                "live canonical values differ from the frozen packet"
            )
        persisted = np.asarray(persisted_values, dtype=np.complex128)
        if (
            persisted.shape != expected_values.shape
            or not np.isfinite(persisted).all()
            or not np.allclose(
                persisted,
                expected_values,
                rtol=0.0,
                atol=tolerance,
            )
        ):
            raise ExactQualificationContractError(
                "persisted canonical values differ from the frozen packet"
            )
        try:
            relative = float(
                canonical_to_current_roundtrip_relative(
                    system,
                    expected_tokens,
                    expected_values.copy(),
                    loaded_vector,
                )
            )
        except ExactQualificationContractError:
            raise
        except Exception as exc:
            raise ExactQualificationContractError(
                "live canonical-to-current roundtrip callback failed"
            ) from exc
        if (
            not np.isfinite(relative)
            or relative < 0.0
            or relative > tolerance
        ):
            raise ExactQualificationContractError(
                f"live canonical/current roundtrip exceeds tolerance: {relative}"
            )
        return relative

    return callback


def make_live_persisted_canonical_roundtrip_callback(
    system: Any,
    *,
    canonical_packets_for_vector: Callable[..., Any],
    canonical_to_current_roundtrip_relative: Callable[..., float],
    tolerance: float = 1.0e-12,
) -> Callable[[Mapping[str, Any], PETSc.Vec, np.ndarray], float]:
    """Bind a live canonical API to the persisted values supplied by a loader.

    Unlike :func:`make_live_canonical_roundtrip_callback`, this factory does
    not retain a second copy of a packet.  The loader has already hashed and
    loaded the persisted canonical values; this callback checks that the live
    current system emits the same token order and values before invoking its
    physical reconstruction/round-trip routine.
    """

    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "persisted canonical roundtrip tolerance is not numeric"
        ) from exc
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ExactQualificationContractError(
            "persisted canonical roundtrip tolerance is invalid"
        )

    def callback(
        layout_audit: Mapping[str, Any],
        loaded_vector: PETSc.Vec,
        persisted_values: np.ndarray,
    ) -> float:
        try:
            expected_tokens = tuple(
                _canonical_key_token(value)
                for value in layout_audit["canonical_tokens"]
            )
            persisted = np.asarray(persisted_values, dtype=np.complex128)
            if persisted.ndim != 1 or not np.isfinite(persisted).all():
                raise ExactQualificationContractError(
                    "persisted canonical values are not a finite vector"
                )
            live_result = canonical_packets_for_vector(system, loaded_vector)
            if not isinstance(live_result, tuple) or len(live_result) < 2:
                raise ExactQualificationContractError(
                    "live canonical packet API returned no token/value pair"
                )
            live_tokens = tuple(
                _canonical_key_token(value) for value in live_result[0]
            )
            live_values = np.asarray(live_result[1], dtype=np.complex128)
        except ExactQualificationContractError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ExactQualificationContractError(
                "live canonical packet identity is not readable"
            ) from exc
        if live_tokens != expected_tokens:
            raise ExactQualificationContractError(
                "live canonical tokens differ from persisted layout"
            )
        if (
            live_values.ndim != 1
            or live_values.shape != persisted.shape
            or not np.isfinite(live_values).all()
            or not np.allclose(live_values, persisted, rtol=0.0, atol=tolerance)
        ):
            raise ExactQualificationContractError(
                "live canonical values differ from persisted packet"
            )
        try:
            relative = float(
                canonical_to_current_roundtrip_relative(
                    system,
                    expected_tokens,
                    persisted.copy(),
                    loaded_vector,
                )
            )
        except ExactQualificationContractError:
            raise
        except Exception as exc:
            raise ExactQualificationContractError(
                "live canonical-to-current roundtrip callback failed"
            ) from exc
        if (
            not np.isfinite(relative)
            or relative < 0.0
            or relative > tolerance
        ):
            raise ExactQualificationContractError(
                f"live canonical/current roundtrip exceeds tolerance: {relative}"
            )
        return relative

    return callback


def validate_canonical_layout(
    layout: Mapping[str, Any],
    *,
    expected_global_size: int | None = None,
    expected_layout_sha256: str | None = None,
    observed_layout_sha256: str | None = None,
    expected_key_set_sha256: str | None = None,
    expected_rank: int | None = None,
    expected_mpi_size: int | None = None,
) -> dict[str, Any]:
    """Validate one rank's canonical layout metadata and key-token payload.

    The persisted layout contains only that rank's canonical token slice.  Its
    declared key-set digest is therefore checked against the independently
    supplied global authority; this function never mistakes a local slice for
    the global key set.  A caller that has the live current keys must still run
    :func:`canonical_values_roundtrip_error` before using the owner values.
    """

    if not isinstance(layout, Mapping):
        raise ExactQualificationContractError("canonical layout is not a mapping")
    required = (
        "canonical_keys",
        "canonical_key_set_sha256",
        "global_size",
        "local_size",
        "ownership_range",
        "rank",
        "mpi_size",
    )
    missing = [key for key in required if key not in layout]
    if missing:
        raise ExactQualificationContractError(
            f"canonical layout is missing fields: {missing}"
        )
    try:
        global_size = int(layout["global_size"])
        local_size = int(layout["local_size"])
        rank = int(layout["rank"])
        mpi_size = int(layout["mpi_size"])
        ownership = tuple(int(value) for value in layout["ownership_range"])
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "canonical layout size/ownership metadata is invalid"
        ) from exc
    if (
        global_size <= 0
        or local_size < 0
        or len(ownership) != 2
        or ownership[0] > ownership[1]
    ):
        raise ExactQualificationContractError("canonical layout size is invalid")
    if ownership[0] < 0 or ownership[1] > global_size:
        raise ExactQualificationContractError(
            "canonical layout ownership is out of bounds"
        )
    if expected_global_size is not None and global_size != int(expected_global_size):
        raise ExactQualificationContractError("canonical layout global_size mismatch")
    if expected_layout_sha256 is not None:
        if not _is_hex_sha256(expected_layout_sha256):
            raise ExactQualificationContractError(
                "expected canonical layout hash is not a SHA256 digest"
            )
        if observed_layout_sha256 != expected_layout_sha256:
            raise ExactQualificationContractError("canonical layout file hash mismatch")
    if expected_rank is not None and rank != int(expected_rank):
        raise ExactQualificationContractError("canonical layout rank mismatch")
    if expected_mpi_size is not None and mpi_size != int(expected_mpi_size):
        raise ExactQualificationContractError("canonical layout MPI size mismatch")
    keys = layout["canonical_keys"]
    if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)):
        raise ExactQualificationContractError("canonical_keys is not a sequence")
    tokens = tuple(_canonical_key_token(value) for value in keys)
    if len(set(tokens)) != len(tokens):
        raise ExactQualificationContractError("canonical layout contains duplicate keys")
    if len(tokens) != local_size:
        raise ExactQualificationContractError(
            "canonical key count does not match canonical local_size"
        )
    declared_key_set = layout["canonical_key_set_sha256"]
    if not _is_hex_sha256(declared_key_set):
        raise ExactQualificationContractError(
            "canonical layout key-set hash is not a SHA256 digest"
        )
    if expected_key_set_sha256 is not None and declared_key_set != expected_key_set_sha256:
        raise ExactQualificationContractError(
            "canonical layout key-set hash does not match authority"
        )
    return {
        "global_size": global_size,
        "local_size": local_size,
        "rank": rank,
        "mpi_size": mpi_size,
        "ownership_range": [ownership[0], ownership[1]],
        "canonical_key_count_local": len(tokens),
        "canonical_key_set_sha256": declared_key_set,
        "canonical_key_order_sha256": _canonical_key_order_sha256(tokens),
        "canonical_key_set_local_sha256": _canonical_key_set_sha256(tokens),
        "canonical_tokens": tokens,
    }


def canonical_values_roundtrip_error(
    canonical_keys: Sequence[Any],
    canonical_values: np.ndarray,
    owner_keys: Sequence[Any],
    owner_values: np.ndarray,
    *,
    max_relative_error: float = 1.0e-12,
) -> float:
    """Compare owner values after a caller-supplied canonical-key reconstruction.

    ``owner_values`` must already be in the live PETSc owner order and
    ``owner_keys`` must be the corresponding live current canonical keys.  The
    function performs no row-number remap and is intentionally independent of
    any solver.  In production the caller obtains ``owner_values`` through its
    live canonical-key reconstruction; this helper only verifies the resulting
    round trip.
    """

    canonical_tokens = tuple(_canonical_key_token(value) for value in canonical_keys)
    owner_tokens = tuple(_canonical_key_token(value) for value in owner_keys)
    canonical_array = np.asarray(canonical_values, dtype=np.complex128)
    owner_array = np.asarray(owner_values, dtype=np.complex128)
    if canonical_array.ndim != 1 or owner_array.ndim != 1:
        raise ExactQualificationContractError("canonical/owner values must be vectors")
    if len(canonical_tokens) != canonical_array.size:
        raise ExactQualificationContractError(
            "canonical key/value lengths differ"
        )
    if len(owner_tokens) != owner_array.size:
        raise ExactQualificationContractError("owner key/value lengths differ")
    if len(set(canonical_tokens)) != len(canonical_tokens):
        raise ExactQualificationContractError("canonical keys are not unique")
    if len(set(owner_tokens)) != len(owner_tokens):
        raise ExactQualificationContractError("owner keys are not unique")
    canonical_by_key = dict(zip(canonical_tokens, canonical_array, strict=True))
    missing = [key for key in owner_tokens if key not in canonical_by_key]
    if missing:
        raise ExactQualificationContractError(
            "live owner keys are not covered by the canonical values"
        )
    expected = np.asarray([canonical_by_key[key] for key in owner_tokens])
    difference = float(np.linalg.norm(owner_array - expected))
    denominator = max(float(np.linalg.norm(expected)), 1.0e-30)
    relative = difference / denominator
    if not np.isfinite(relative) or relative > float(max_relative_error):
        raise ExactQualificationContractError(
            f"canonical/current owner round-trip exceeds tolerance: {relative}"
        )
    return relative


def _resolve_under_root(root: Path, value: str) -> Path:
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ExactQualificationContractError(
            f"vector path escapes its artifact root: {value!r}"
        ) from exc
    return resolved


def load_owner_local_vector(
    descriptor: Mapping[str, Any],
    *,
    base_directory: str | Path,
    template: PETSc.Vec | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    canonical_roundtrip: Callable[
        [Mapping[str, Any], PETSc.Vec, np.ndarray], float
    ] | None = None,
    canonical_roundtrip_tolerance: float = 1.0e-12,
    **validation: Any,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Load a canonical/owner pair into one current-layout PETSc Vec.

    V5 stores two different numeric arrays.  ``array_path`` is the local
    canonical-key order and its digest is a contiguous-value digest; the
    ``owner_row_array_path`` is the current PETSc ownership order.  The latter
    is the only array copied into the Vec.  A live-key round-trip callback is
    mandatory so loading an owner array cannot silently bypass canonical
    identity.  The callback runs after the current-layout Vec is constructed
    and filled, and receives the persisted layout audit, that live Vec, and
    the canonical values.  A production caller can therefore invoke its
    actual canonical packet reconstruction path instead of comparing two raw
    row arrays.
    """

    normalized = validate_owner_vector_descriptor(descriptor, **validation)
    root = Path(base_directory).resolve()
    if canonical_roundtrip is None:
        raise ExactQualificationContractError(
            "live canonical-key roundtrip callback is required"
        )
    if not np.isfinite(float(canonical_roundtrip_tolerance)) or float(
        canonical_roundtrip_tolerance
    ) < 0.0:
        raise ExactQualificationContractError(
            "canonical roundtrip tolerance must be finite and nonnegative"
        )
    canonical_path = _resolve_under_root(root, normalized["array_path"])
    owner_path = _resolve_under_root(root, normalized["owner_row_array_path"])
    layout_path = _resolve_under_root(root, normalized["canonical_layout_path"])
    if not layout_path.is_file():
        raise ExactQualificationContractError(
            f"canonical layout does not exist: {layout_path}"
        )
    observed_layout_sha256 = hash_file_sha256(layout_path)
    if observed_layout_sha256 != normalized["canonical_layout_sha256"]:
        raise ExactQualificationContractError(
            "canonical layout file hash mismatch"
        )
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExactQualificationContractError(
            "canonical layout cannot be decoded as JSON"
        ) from exc
    layout_audit = validate_canonical_layout(
        layout,
        expected_global_size=normalized["global_size"],
        expected_layout_sha256=normalized["canonical_layout_sha256"],
        observed_layout_sha256=observed_layout_sha256,
        expected_key_set_sha256=normalized["canonical_key_set_sha256"],
        expected_rank=int(comm.Get_rank()),
        expected_mpi_size=int(comm.Get_size()),
    )
    if layout_audit["canonical_key_count_local"] != int(
        normalized["canonical_key_count_local"]
    ):
        raise ExactQualificationContractError(
            "canonical layout key count differs from vector metadata"
        )
    if not canonical_path.is_file():
        raise ExactQualificationContractError(
            f"canonical vector array does not exist: {canonical_path}"
        )
    if not owner_path.is_file():
        raise ExactQualificationContractError(
            f"owner-local vector array does not exist: {owner_path}"
        )
    try:
        canonical_values = np.load(
            canonical_path,
            mmap_mode="r",
            allow_pickle=False,
        )
        owner_values = np.load(owner_path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ExactQualificationContractError(
            "canonical or owner-local vector array cannot be read as NPY"
        ) from exc
    if (
        canonical_values.ndim != 1
        or canonical_values.dtype != np.dtype(np.complex128)
        or owner_values.ndim != 1
        or owner_values.dtype != np.dtype(np.complex128)
    ):
        raise ExactQualificationContractError(
            "canonical and owner arrays must be one-dimensional complex128"
        )
    if int(canonical_values.size) != layout_audit["canonical_key_count_local"]:
        raise ExactQualificationContractError(
            "canonical array length does not match canonical key count"
        )
    if int(owner_values.size) != normalized["local_size"]:
        raise ExactQualificationContractError(
            "owner-local array length does not match PETSc metadata"
        )
    observed_canonical_sha256 = hash_array_bytes_sha256(canonical_values)
    if observed_canonical_sha256 != normalized["array_sha256"]:
        raise ExactQualificationContractError(
            "canonical array contiguous-value hash mismatch"
        )
    observed_owner_sha256 = hash_array_bytes_sha256(owner_values)
    if observed_owner_sha256 != normalized["owner_row_array_sha256"]:
        raise ExactQualificationContractError(
            "owner-local array contiguous-value hash mismatch"
        )
    if not np.isfinite(np.asarray(canonical_values)).all():
        raise ExactQualificationContractError("canonical array contains nonfinite values")
    if not np.isfinite(np.asarray(owner_values)).all():
        raise ExactQualificationContractError(
            "owner-local array contains nonfinite values"
        )
    vector: PETSc.Vec | None = None
    try:
        if template is None:
            vector = PETSc.Vec().createMPI(
                (normalized["local_size"], normalized["global_size"]),
                comm=comm,
            )
        else:
            vector = template.duplicate()
        actual_range = tuple(int(value) for value in vector.getOwnershipRange())
        if (
            vector.getSize() != normalized["global_size"]
            or vector.getLocalSize() != normalized["local_size"]
            or actual_range != tuple(normalized["ownership_range"])
        ):
            raise ExactQualificationContractError(
                "constructed PETSc Vec does not match current ownership metadata"
            )
        vector.array[:] = np.asarray(owner_values, dtype=PETSc.ScalarType)
        vector.assemble()
        try:
            roundtrip = float(
                canonical_roundtrip(
                    layout_audit,
                    vector,
                    np.asarray(canonical_values),
                )
            )
        except ExactQualificationContractError:
            raise
        except Exception as exc:
            raise ExactQualificationContractError(
                "canonical/current owner roundtrip callback failed"
            ) from exc
        if (
            not np.isfinite(roundtrip)
            or roundtrip < 0.0
            or roundtrip > float(canonical_roundtrip_tolerance)
        ):
            raise ExactQualificationContractError(
                f"canonical/current owner roundtrip is outside tolerance: {roundtrip}"
            )
        return vector, {
            **normalized,
            "array_sha256_observed": observed_canonical_sha256,
            "owner_row_array_sha256_observed": observed_owner_sha256,
            "canonical_layout_sha256_observed": observed_layout_sha256,
            "canonical_key_order_sha256": layout_audit[
                "canonical_key_order_sha256"
            ],
            "canonical_key_set_local_sha256": layout_audit[
                "canonical_key_set_local_sha256"
            ],
            "canonical_layout_rank": layout_audit["rank"],
            "canonical_layout_mpi_size": layout_audit["mpi_size"],
            "canonical_roundtrip_relative": roundtrip,
            "canonical_values_loaded": True,
            "owner_values_loaded": True,
            "numeric_values_loaded": True,
            "canonical_values_retained": False,
            "owner_values_retained": False,
            "owner_row_array_loaded": True,
            "owner_row_values_not_row_ids": True,
        }
    except Exception:
        if vector is not None:
            vector.destroy()
        raise


def validate_distributed_owner_vector(
    descriptor: Mapping[str, Any],
    vector: PETSc.Vec,
    *,
    comm: MPI.Intracomm | None = None,
    expected_role: str | None = None,
    canonical_layout_rank: int | None = None,
    canonical_layout_mpi_size: int | None = None,
) -> dict[str, Any]:
    """Cross-check owner ranges and hashes using only small metadata gathers."""

    mpi_comm = comm or vector.getComm().tompi4py()
    local_error: str | None = None
    local: dict[str, Any] | None = None
    try:
        normalized = validate_owner_vector_descriptor(
            descriptor,
            expected_role=(
                str(descriptor.get("role"))
                if expected_role is None
                else expected_role
            ),
        )
        actual_range = tuple(int(value) for value in vector.getOwnershipRange())
        if (
            int(vector.getSize()) != normalized["global_size"]
            or int(vector.getLocalSize()) != normalized["local_size"]
            or actual_range != tuple(normalized["ownership_range"])
        ):
            raise ExactQualificationContractError(
                "loaded Vec ownership differs from descriptor"
            )
        expected_binding = rank_local_shard_binding_sha256(
            rank=int(mpi_comm.rank),
            label=str(normalized["label"]),
            role=str(normalized["role"]),
            source_definition_sha256=str(normalized["source_definition_sha256"]),
            key_set_sha256=str(normalized["canonical_key_set_sha256"]),
            canonical_layout_sha256=str(normalized["canonical_layout_sha256"]),
            identity=descriptor["vector_identity"],
            source_provenance=normalized["source_provenance"],
            bare_f_operator_hash=str(normalized["bare_f_operator_hash"]),
            rhs_repeat=normalized["rhs_repeat"],
        )
        if normalized["rank_local_shard_binding_sha256"] != expected_binding:
            raise ExactQualificationContractError(
                "rank_local_shard_binding_sha256 does not match producer payload"
            )
        local = {
            "rank": int(mpi_comm.rank),
            "label": normalized["label"],
            "role": normalized["role"],
            "global_size": normalized["global_size"],
            "local_size": normalized["local_size"],
            "ownership_range": normalized["ownership_range"],
            "array_sha256": normalized["array_sha256"],
            "owner_row_array_sha256": normalized["owner_row_array_sha256"],
            "canonical_layout_sha256": normalized["canonical_layout_sha256"],
            "canonical_key_set_sha256": normalized["canonical_key_set_sha256"],
            "global_sha256": normalized["global_sha256"],
            "source_definition_sha256": normalized["source_definition_sha256"],
            "rank_local_shard_binding_sha256": normalized[
                "rank_local_shard_binding_sha256"
            ],
            "canonical_layout_rank": canonical_layout_rank,
            "canonical_layout_mpi_size": canonical_layout_mpi_size,
            "bare_f_operator_hash": normalized["bare_f_operator_hash"],
            "source_sha": normalized["source_sha"],
            "source_provenance": normalized["source_provenance"],
        }
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = mpi_comm.allgather(local_error)
    if any(error is not None for error in errors):
        first = next(error for error in errors if error is not None)
        raise ExactQualificationContractError(
            f"distributed owner-vector validation failed: {first}"
        )
    gathered = mpi_comm.allgather(local)
    if any(not isinstance(item, Mapping) for item in gathered):
        raise ExactQualificationContractError(
            "distributed owner-vector validation received an incomplete rank record"
        )
    records = [dict(item) for item in gathered]
    labels = {item["label"] for item in records}
    roles = {item["role"] for item in records}
    sizes = {int(item["global_size"]) for item in records}
    if len(labels) != 1 or len(roles) != 1 or len(sizes) != 1:
        raise ExactQualificationContractError(
            "distributed owner-vector identity differs across ranks"
        )
    for field in (
        "canonical_key_set_sha256",
        "global_sha256",
        "source_definition_sha256",
        "bare_f_operator_hash",
        "source_sha",
    ):
        if len({item[field] for item in records}) != 1:
            raise ExactQualificationContractError(
                f"distributed owner-vector {field} differs across ranks"
            )
    provenance_records = [
        tuple(
            item["source_provenance"].get(key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
            )
        )
        for item in records
    ]
    if len(set(provenance_records)) != 1:
        raise ExactQualificationContractError(
            "distributed owner-vector source provenance differs across ranks"
        )
    if canonical_layout_rank is not None or canonical_layout_mpi_size is not None:
        layout_ranks = {item["canonical_layout_rank"] for item in records}
        layout_mpi_sizes = {item["canonical_layout_mpi_size"] for item in records}
        if layout_ranks != set(range(int(mpi_comm.size))) or layout_mpi_sizes != {
            int(mpi_comm.size)
        }:
            raise ExactQualificationContractError(
                "distributed canonical layout rank/MPI identity is incomplete"
            )
    ordered = sorted(records, key=lambda item: item["ownership_range"][0])
    expected_start = 0
    for item in ordered:
        first, last = map(int, item["ownership_range"])
        if first != expected_start or last - first != int(item["local_size"]):
            raise ExactQualificationContractError(
                "distributed owner-vector ranges are not contiguous"
            )
        expected_start = last
    global_size = next(iter(sizes))
    if expected_start != global_size:
        raise ExactQualificationContractError(
            "distributed owner-vector ranges do not cover the global size"
        )
    canonical_hashes = [
        str(item["array_sha256"])
        for item in sorted(records, key=lambda item: int(item["rank"]))
    ]
    if any(not _is_hex_sha256(value) for value in canonical_hashes):
        raise ExactQualificationContractError(
            "distributed owner-vector canonical array hash is invalid"
        )
    expected_global_sha256 = hashlib.sha256(
        "\n".join(canonical_hashes).encode("ascii")
    ).hexdigest()
    if any(item["global_sha256"] != expected_global_sha256 for item in records):
        raise ExactQualificationContractError(
            "distributed owner-vector global canonical hash does not match rank shards"
        )
    return {
        "label": next(iter(labels)),
        "role": next(iter(roles)),
        "global_size": global_size,
        "rank_records": records,
        "owner_local": True,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "ownership_coverage_exact": True,
        "global_sha256": expected_global_sha256,
    }


def load_owner_local_vector_collective(
    descriptor: Mapping[str, Any],
    *,
    base_directory: str | Path,
    template: PETSc.Vec | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    **validation: Any,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Load one rank's vector and turn one-rank errors into a collective stop."""

    vector: PETSc.Vec | None = None
    local_error: str | None = None
    try:
        vector, local_audit = load_owner_local_vector(
            descriptor,
            base_directory=base_directory,
            template=template,
            comm=comm,
            **validation,
        )
    except Exception as exc:
        local_audit = None
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        if vector is not None:
            vector.destroy()
        first_rank, first_error = next(
            (rank, error)
            for rank, error in enumerate(errors)
            if error is not None
        )
        raise ExactQualificationContractError(
            f"collective owner-vector load failed on rank {first_rank}: {first_error}"
        )
    if vector is None or local_audit is None:
        raise ExactQualificationContractError(
            "collective owner-vector load produced no vector"
        )
    try:
        distributed = validate_distributed_owner_vector(
            descriptor,
            vector,
            comm=comm,
            expected_role=validation.get("expected_role"),
            canonical_layout_rank=local_audit["canonical_layout_rank"],
            canonical_layout_mpi_size=local_audit["canonical_layout_mpi_size"],
        )
    except Exception:
        vector.destroy()
        raise
    return vector, {**local_audit, "distributed": distributed}


@dataclass
class LoadedExactQualificationRHS:
    """Caller-owned vectors prepared for one exact current-layout source."""

    active_rhs: PETSc.Vec
    gamma_rhs: PETSc.Vec
    interior_rhs_by_group: dict[int, PETSc.Vec]
    condensed_rhs: PETSc.Vec
    audit: dict[str, Any]
    _destroyed: bool = False

    def compact_audit(self) -> dict[str, Any]:
        """Return JSON-safe adapter metadata without embedding PETSc objects."""

        return {
            **_compact_recovery_audit(self.audit),
            "retained_during_callbacks": not self._destroyed,
            "released_by_driver": self._destroyed,
            "destroyed_after_source": self._destroyed,
            "interior_rhs_group_count": len(self.interior_rhs_by_group),
            "numeric_allgather": False,
        }

    def destroy(self) -> None:
        """Destroy every vector exactly once; safe on success and failure paths."""

        if self._destroyed:
            return
        vectors: list[PETSc.Vec] = [
            self.condensed_rhs,
            self.gamma_rhs,
            *self.interior_rhs_by_group.values(),
            self.active_rhs,
        ]
        destroyed: set[int] = set()
        for vector in vectors:
            if id(vector) in destroyed:
                continue
            destroyed.add(id(vector))
            vector.destroy()
        self._destroyed = True


def _collect_petsc_vectors(value: Any) -> list[PETSc.Vec]:
    """Collect PETSc Vec objects nested in a builder result.

    A condensed-RHS builder can fail its return-shape contract after creating
    vectors.  The adapter therefore inspects the returned mapping/sequence
    before validating that contract, so those objects remain adapter-owned
    and can be released without calling methods on arbitrary values.
    """

    vectors: list[PETSc.Vec] = []
    visited: set[int] = set()

    def visit(item: Any) -> None:
        if isinstance(item, PETSc.Vec):
            if id(item) not in visited:
                visited.add(id(item))
                vectors.append(item)
            return
        if isinstance(item, Mapping):
            if id(item) in visited:
                return
            visited.add(id(item))
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            if id(item) in visited:
                return
            visited.add(id(item))
            for nested in item:
                visit(nested)

    visit(value)
    return vectors


def _destroy_petsc_vectors(vectors: Sequence[Any]) -> None:
    """Destroy each identified PETSc Vec once, ignoring non-Vec values."""

    destroyed: set[int] = set()
    for vector in vectors:
        if not isinstance(vector, PETSc.Vec) or id(vector) in destroyed:
            continue
        destroyed.add(id(vector))
        vector.destroy()


def load_and_condense_exact_rhs(
    descriptor: Mapping[str, Any],
    *,
    base_directory: str | Path,
    action: Any,
    canonical_roundtrip: Callable[
        [Mapping[str, Any], PETSc.Vec, np.ndarray], float
    ],
    template: PETSc.Vec | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    **validation: Any,
) -> LoadedExactQualificationRHS:
    """Load one V5 owner-row RHS and form its condensed current-layout RHS.

    This is the consumer boundary between persisted V5 packets and the V6-2
    Schur action.  The loader first proves the live canonical reconstruction,
    then the action extracts ``b_Gamma``/``b_I`` and computes
    ``g=b_Gamma-A_Gamma,I A_I,I^-1 b_I``.  All returned PETSc objects belong to
    the caller and must be released with :meth:`LoadedExactQualificationRHS.destroy`.
    """

    builder = getattr(action, "build_condensed_rhs_from_active_vector", None)
    if not callable(builder):
        raise TypeError(
            "exact qualification action lacks build_condensed_rhs_from_active_vector"
        )
    active_rhs: PETSc.Vec | None = None
    gamma_rhs: PETSc.Vec | None = None
    interior_rhs_by_group: dict[int, PETSc.Vec] = {}
    condensed_rhs: PETSc.Vec | None = None
    builder_owned_vectors: list[PETSc.Vec] = []
    try:
        active_rhs, load_audit = load_owner_local_vector_collective(
            descriptor,
            base_directory=base_directory,
            template=template,
            comm=comm,
            canonical_roundtrip=canonical_roundtrip,
            **validation,
        )
        result = builder(active_rhs)
        builder_owned_vectors = _collect_petsc_vectors(result)
        if not isinstance(result, tuple) or len(result) != 3:
            raise TypeError(
                "build_condensed_rhs_from_active_vector must return gamma, interior, condensed"
            )
        gamma_rhs, interior_values, condensed_rhs = result
        if isinstance(interior_values, Mapping):
            interior_rhs_by_group = {
                int(group): vector for group, vector in interior_values.items()
            }
        else:
            try:
                sequence = tuple(interior_values)
            except TypeError as exc:
                raise TypeError("interior RHS result is not a group sequence") from exc
            interior_rhs_by_group = {
                group: vector for group, vector in enumerate(sequence)
            }
        if set(interior_rhs_by_group) != {0, 1, 2}:
            raise ValueError("condensed RHS action must return groups 0, 1, 2")
        vectors = (gamma_rhs, condensed_rhs, *interior_rhs_by_group.values())
        if any(not isinstance(vector, PETSc.Vec) for vector in vectors):
            raise TypeError("condensed RHS action returned a non-PETSc vector")
        audit = {
            "load": load_audit,
            "condensed_rhs_built": True,
            "interior_rhs_group_count": len(interior_rhs_by_group),
            "numeric_allgather": False,
            "full_numeric_replica": False,
        }
        return LoadedExactQualificationRHS(
            active_rhs=active_rhs,
            gamma_rhs=gamma_rhs,
            interior_rhs_by_group=interior_rhs_by_group,
            condensed_rhs=condensed_rhs,
            audit=audit,
        )
    except Exception:
        _destroy_petsc_vectors(
            [
                *builder_owned_vectors,
                condensed_rhs,
                gamma_rhs,
                *interior_rhs_by_group.values(),
                active_rhs,
            ]
        )
        raise


def run_exact_qualification_family(
    descriptors: Mapping[str, Mapping[str, Any]],
    *,
    base_directory: str | Path,
    interface_operator: PETSc.Mat,
    bare_operator: PETSc.Mat,
    schur_action: Any,
    canonical_roundtrip: Callable[
        [Mapping[str, Any], PETSc.Vec, np.ndarray], float
    ]
    | Mapping[str, Callable[[Mapping[str, Any], PETSc.Vec, np.ndarray], float]],
    right_preconditioner: Any | None = None,
    initial_labels: Sequence[str] | None = None,
    restart: int = 32,
    mandatory_checkpoints: Sequence[int] = (16, 32, 64, 128),
    conditional_checkpoints: Sequence[int] = (256, 512),
    authorize_conditional: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    max_iterations: int | None = None,
    checkpoint_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    accepted_solution_callback: (
        Callable[[str, Mapping[str, Any], PETSc.Vec], None] | None
    ) = None,
    accepted_solution_consumer: (
        Callable[
            [str, Mapping[str, Any], PETSc.Vec, LoadedExactQualificationRHS], Any
        ]
        | None
    ) = None,
    packetization_required: bool = True,
    validation: Mapping[str, Any] | None = None,
    full_residual_tolerance: float = 1.0e-9,
) -> dict[str, Any]:
    """Run one same-process exact-qualification source family.

    The first two labels form the guarded qualification pair.  Remaining
    sources are attempted only when both guarded sources reach the explicit
    full-``F`` residual tolerance.  Each source owns its loader bundle and
    accepted solution only for the duration of its callbacks; no PETSc Vec is
    placed in the returned record.
    """

    if not isinstance(descriptors, Mapping) or not descriptors:
        raise TypeError("exact qualification descriptors must be a nonempty mapping")
    if not _finite_nonnegative(full_residual_tolerance) or full_residual_tolerance <= 0.0:
        raise ValueError("exact qualification residual tolerance must be positive")
    family_comm = interface_operator.getComm().tompi4py()
    labels = tuple(str(label) for label in descriptors)
    if len(set(labels)) != len(labels):
        raise ValueError("exact qualification labels must be unique")
    for label in labels:
        descriptor = descriptors[label]
        if not isinstance(descriptor, Mapping):
            raise TypeError(f"descriptor for {label} is not a mapping")
        if descriptor.get("label") != label:
            raise ExactQualificationContractError(
                f"descriptor label does not match family key: {label!r}"
            )
    guarded = tuple(
        str(label) for label in (initial_labels or labels[:2])
    )
    if len(guarded) != 2 or len(set(guarded)) != 2:
        raise ValueError("exact qualification needs two distinct initial labels")
    if any(label not in descriptors for label in guarded):
        raise ValueError("initial exact qualification label is missing")
    ordered_labels = guarded + tuple(label for label in labels if label not in guarded)
    validation_kwargs = dict(validation or {})
    supplied_label = validation_kwargs.get("expected_label")
    if supplied_label is not None and any(
        str(supplied_label) != label for label in labels
    ):
        raise ValueError("one common expected_label cannot validate a source family")
    source_records: list[dict[str, Any]] = []

    def callback_for(label: str) -> Callable[[Mapping[str, Any], PETSc.Vec, np.ndarray], float]:
        if isinstance(canonical_roundtrip, Mapping):
            callback = canonical_roundtrip.get(label)
            if not callable(callback):
                raise TypeError(f"missing canonical roundtrip callback for {label}")
            return callback
        if not callable(canonical_roundtrip):
            raise TypeError("canonical roundtrip must be callable or label-indexed")
        return canonical_roundtrip

    # Validate every label-indexed callback before the first source loader.
    # The loader and its live canonical roundtrip both have collective stages;
    # a one-rank missing callback must therefore not let the other ranks enter
    # the first source independently.
    _collective_contract_call(
        family_comm,
        "exact family canonical-roundtrip preflight",
        lambda: [callback_for(label) for label in ordered_labels],
    )

    def run_source(label: str) -> dict[str, Any]:
        bundle: LoadedExactQualificationRHS | None = None
        accepted: PETSc.Vec | None = None
        source_result: dict[str, Any] | None = None
        adapter_during_callbacks: dict[str, Any] | None = None
        try:
            bundle = load_and_condense_exact_rhs(
                descriptors[label],
                base_directory=base_directory,
                action=schur_action,
                canonical_roundtrip=callback_for(label),
                comm=interface_operator.getComm().tompi4py(),
                **{
                    **validation_kwargs,
                    "expected_label": label,
                },
            )

            def source_checkpoint(row: Mapping[str, Any]) -> None:
                if checkpoint_callback is not None:
                    checkpoint_callback(label, row)

            def source_accepted(row: Mapping[str, Any], vector: PETSc.Vec) -> None:
                if accepted_solution_callback is not None:
                    accepted_solution_callback(label, row, vector)

            fgmres = run_exact_interface_fgmres(
                interface_operator=interface_operator,
                schur_action=schur_action,
                bare_operator=bare_operator,
                condensed_rhs=bundle.condensed_rhs,
                active_rhs=bundle.active_rhs,
                interior_rhs_by_group=bundle.interior_rhs_by_group,
                right_preconditioner=right_preconditioner,
                label=label,
                restart=restart,
                mandatory_checkpoints=mandatory_checkpoints,
                conditional_checkpoints=conditional_checkpoints,
                authorize_conditional=authorize_conditional,
                resource_callback=resource_callback,
                max_iterations=max_iterations,
                checkpoint_callback=source_checkpoint,
                accepted_solution_callback=(
                    source_accepted if accepted_solution_callback is not None else None
                ),
                full_residual_tolerance=full_residual_tolerance,
            )
            accepted = fgmres.pop("accepted_solution", None)
            checkpoint_rows = [
                row
                for row in fgmres.get("checkpoint_history", [])
                if isinstance(row, Mapping)
            ]
            accepted_row = next(
                (
                    row
                    for row in reversed(checkpoint_rows)
                    if bool(row.get("accepted_full_solution"))
                ),
                {},
            )
            accepted_solution_consumed = False
            accepted_solution_packet_audit: Any = None
            packetization_gate_error: str | None = None
            if accepted is not None and accepted_solution_consumer is not None:
                accepted_solution_packet_audit = accepted_solution_consumer(
                    label,
                    accepted_row,
                    accepted,
                    bundle,
                )
                accepted_solution_consumed = True
            packet_write_audit = (
                accepted_solution_packet_audit.get("packet_write")
                if isinstance(accepted_solution_packet_audit, Mapping)
                else None
            )
            packetization_gate_pass = False
            if packetization_required and accepted_solution_consumed:
                try:
                    normalized_packet_write = _validate_packet_write_audit(
                        str(label),
                        packet_write_audit,
                        expected_packet_identities=(
                            accepted_solution_packet_audit.get(
                                "expected_packet_identities"
                            )
                            if isinstance(
                                accepted_solution_packet_audit, Mapping
                            )
                            else None
                        ),
                    )
                except (TypeError, ValueError) as exc:
                    normalized_packet_write = None
                    packetization_gate_error = (
                        f"{type(exc).__name__}: {exc}"
                    )
                else:
                    packetization_gate_pass = True
                    accepted_solution_packet_audit = {
                        **dict(accepted_solution_packet_audit),
                        "packet_write": normalized_packet_write,
                    }
            elif not packetization_required:
                packetization_gate_pass = True
            full_residuals = [
                float(row["full_true_residual_relative"])
                for row in checkpoint_rows
                if _finite_nonnegative(row.get("full_true_residual_relative"))
            ]
            best_full_residual = min(full_residuals, default=float("inf"))
            adapter_during_callbacks = bundle.compact_audit()
            source_result = {
                "label": label,
                # This is replaced after the finally block so the persisted
                # lifecycle describes the observed post-source state rather
                # than the state while callbacks still own the Vecs.
                "adapter": adapter_during_callbacks,
                "fgmres": {
                    **_json_safe_binding(fgmres),
                    "accepted_solution_present": accepted is not None,
                    "accepted_solution_released_by_driver": accepted is not None,
                    "accepted_solution_consumed": accepted_solution_consumed,
                    "accepted_solution_packet_audit": (
                        _json_safe_binding(accepted_solution_packet_audit)
                        if accepted_solution_packet_audit is not None
                        else None
                    ),
                    "packetization_gate_error": packetization_gate_error,
                },
                "best_full_true_residual_relative": best_full_residual,
                "full_residual_gate_pass": bool(
                    np.isfinite(best_full_residual)
                    and best_full_residual <= float(full_residual_tolerance)
                ),
                "packetization_gate_pass": bool(
                    packetization_gate_pass
                ),
            }
        finally:
            if accepted is not None:
                accepted.destroy()
            if bundle is not None:
                bundle.destroy()
                if source_result is not None:
                    source_result["adapter"] = {
                        **bundle.compact_audit(),
                        "retained_during_callbacks": bool(
                            (adapter_during_callbacks or {}).get(
                                "retained_during_callbacks", False
                            )
                        ),
                        "released_by_driver": True,
                        "destroyed_after_source": True,
                    }
        if source_result is None:
            raise RuntimeError(f"exact qualification source {label} returned no record")
        return source_result

    def run_source_collective(label: str) -> dict[str, Any]:
        """Complete one source or make its failure collective and typed."""

        record: dict[str, Any] | None = None
        local_error: dict[str, str] | None = None
        try:
            record = run_source(label)
        except ExactQualificationContractError as exc:
            local_error = {
                "kind": "contract",
                "type": type(exc).__name__,
                "message": str(exc),
            }
        except Exception as exc:
            # Preserve implementation failures as implementation failures,
            # but still synchronize them before another rank advances to the
            # next source.  This is a liveness barrier, not an identity claim.
            local_error = {
                "kind": "implementation",
                "type": type(exc).__name__,
                "message": str(exc),
            }
        errors = family_comm.allgather(local_error)
        contract_error = next(
            (error for error in errors if error and error.get("kind") == "contract"),
            None,
        )
        if contract_error is not None:
            raise ExactQualificationContractError(
                "collective exact qualification contract failed at "
                f"{label}: {contract_error['type']}: {contract_error['message']}"
            )
        implementation_error = next((error for error in errors if error), None)
        if implementation_error is not None:
            raise RuntimeError(
                "collective exact qualification implementation failure at "
                f"{label}: {implementation_error['type']}: "
                f"{implementation_error['message']}"
            )
        if not isinstance(record, dict):
            raise RuntimeError(
                f"collective exact qualification source {label} returned no record"
            )

        fgmres_record = record.get("fgmres")
        packet_error: str | None = None
        if isinstance(fgmres_record, Mapping):
            packet_error_value = fgmres_record.get("packetization_gate_error")
            if packet_error_value:
                packet_error = str(packet_error_value)
        if (
            packet_error is None
            and packetization_required
            and bool(record.get("full_residual_gate_pass"))
            and not bool(record.get("packetization_gate_pass"))
        ):
            packet_error = "accepted full-residual source has no valid packet audit"
        packet_errors = family_comm.allgather(packet_error)
        first_packet_error = next(
            (error for error in packet_errors if error is not None), None
        )
        if first_packet_error is not None:
            raise ExactQualificationContractError(
                "collective exact qualification packetization contract failed at "
                f"{label}: {first_packet_error}"
            )
        return record

    for label in ordered_labels[:2]:
        source_records.append(run_source_collective(label))
    local_initial_pair_pass = all(
        bool(record["full_residual_gate_pass"])
        and bool(record["packetization_gate_pass"])
        for record in source_records
    )
    initial_pair_pass = bool(
        family_comm.allreduce(local_initial_pair_pass, op=MPI.LAND)
    )
    skipped_labels: list[str] = []
    if initial_pair_pass:
        for label in ordered_labels[2:]:
            source_records.append(run_source_collective(label))
    else:
        skipped_labels.extend(ordered_labels[2:])
    local_normal_numerical_negative = any(
        not bool(record["full_residual_gate_pass"])
        and not bool(
            record.get("fgmres", {}).get("packetization_gate_error")
            if isinstance(record.get("fgmres"), Mapping)
            else False
        )
        for record in source_records
    )
    normal_numerical_negative = bool(
        family_comm.allreduce(local_normal_numerical_negative, op=MPI.LOR)
    )
    local_all_sources_gate_pass = bool(
        initial_pair_pass
        and len(source_records) == len(ordered_labels)
        and all(
            bool(record["full_residual_gate_pass"])
            and bool(record["packetization_gate_pass"])
            for record in source_records
        )
    )
    all_sources_gate_pass = bool(
        family_comm.allreduce(local_all_sources_gate_pass, op=MPI.LAND)
    )
    return {
        "schema": "task040.v6.exact_qualification_family.v1",
        "status": (
            "completed_initial_pair_and_remaining_sources"
            if all_sources_gate_pass
            else (
                "completed_exact_numerical_gate_negative_continuation_allowed"
                if normal_numerical_negative
                else (
                    "stopped_by_exact_family_contract_gate"
                    if skipped_labels
                    else "completed_all_sources_gate_negative"
                )
            )
        ),
        "classification": (
            "V6_EXACT_QUALIFICATION_READY"
            if all_sources_gate_pass
            else (
                "V6_EXACT_QUALIFICATION_GATE_FAIL"
            )
        ),
        "initial_labels": list(guarded),
        "ordered_labels": list(ordered_labels),
        "source_records": source_records,
        "skipped_labels": skipped_labels,
        "initial_pair_gate_pass": initial_pair_pass,
        "all_sources_gate_pass": all_sources_gate_pass,
        "normal_numerical_negative": normal_numerical_negative,
        "packetization_required": bool(packetization_required),
        "full_residual_tolerance": float(full_residual_tolerance),
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }


def _packet_provenance(source_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the six immutable identities required by every packet role."""

    provenance = source_metadata.get("source_provenance")
    if not isinstance(provenance, Mapping):
        raise ExactQualificationContractError(
            "packet source_provenance must be a mapping"
        )
    fields = (
        "input_sha256",
        "physical_model_sha256",
        "selected_manifest_sha256",
        "selected_identity_sha256",
        "resolved_config_sha256",
        "source_sha",
    )
    result: dict[str, Any] = {}
    for field in fields:
        value = provenance.get(field)
        valid = _is_hex_commit(value) if field == "source_sha" else _is_hex_sha256(value)
        if not valid:
            raise ExactQualificationContractError(
                f"packet source_provenance.{field} is not a valid identity"
            )
        result[field] = str(value)
    return result


def _layout_json_payload(layout: Any) -> dict[str, Any]:
    """Return a compact, transform-bound description of one Gamma layout."""

    keys = tuple(_canonical_key_token(value) for value in layout.canonical_keys)
    blocks = getattr(layout, "blocks", None)
    audit = getattr(layout, "audit", None)
    if not isinstance(blocks, Sequence) or not isinstance(audit, Mapping):
        raise ExactQualificationContractError(
            "Gamma packet requires a real GammaCanonicalLayout"
        )
    positions: list[int] = []
    block_payload: list[dict[str, Any]] = []
    for placement in blocks:
        block = getattr(placement, "block", None)
        block_positions = np.asarray(
            getattr(placement, "positions", ()), dtype=np.int64
        )
        raw_rows = np.asarray(
            getattr(block, "raw_row_ids", ()), dtype=np.int64
        )
        block_keys = tuple(
            _canonical_key_token(value)
            for value in getattr(block, "canonical_keys", ())
        )
        transform = np.asarray(
            getattr(block, "raw_to_canonical", ()), dtype=np.complex128
        )
        inverse = np.asarray(
            getattr(block, "canonical_to_raw", ()), dtype=np.complex128
        )
        if (
            block is None
            or block_positions.ndim != 1
            or raw_rows.ndim != 1
            or len(block_positions) != len(raw_rows)
            or len(block_keys) != len(block_positions)
            or transform.shape != (len(block_positions), len(block_positions))
            or inverse.shape != transform.shape
            or not np.isfinite(transform).all()
            or not np.isfinite(inverse).all()
        ):
            raise ExactQualificationContractError(
                "Gamma layout block transform or positions are invalid"
            )
        if not np.allclose(
            transform @ inverse,
            np.eye(len(block_positions), dtype=np.complex128),
            rtol=0.0,
            atol=1.0e-11,
        ):
            raise ExactQualificationContractError(
                "Gamma layout block transform is not invertible"
            )
        if any(int(position) < 0 for position in block_positions):
            raise ExactQualificationContractError(
                "Gamma layout contains a negative canonical position"
            )
        positions.extend(int(position) for position in block_positions)
        block_payload.append(
            {
                "name": str(getattr(block, "name", "")),
                "raw_row_ids": raw_rows.tolist(),
                "positions": block_positions.tolist(),
                "canonical_keys": list(block_keys),
                "raw_to_canonical": _json_safe_binding(transform),
                "canonical_to_raw": _json_safe_binding(inverse),
                "orientation_state": _json_safe_binding(
                    getattr(block, "orientation_state", None)
                ),
                "floquet_master": _json_safe_binding(
                    getattr(block, "floquet_master", None)
                ),
                "floquet_coefficient": _json_safe_binding(
                    getattr(block, "floquet_coefficient", None)
                ),
            }
        )
    if sorted(positions) != list(range(len(keys))):
        raise ExactQualificationContractError(
            "Gamma layout positions are not an exact canonical bijection"
        )
    global_count = audit.get("global_row_count")
    global_key_set = audit.get("global_key_set_sha256")
    try:
        global_count = int(global_count)
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError(
            "Gamma layout global canonical count is missing"
        ) from exc
    if global_count < len(keys) or not _is_hex_sha256(global_key_set):
        raise ExactQualificationContractError(
            "Gamma layout global key-set authority is missing"
        )
    payload = {
        "canonical_keys": list(keys),
        "blocks": block_payload,
        "plane_identity": _json_safe_binding(
            getattr(layout, "plane_identity", {})
        ),
        "global_key_set_sha256": str(global_key_set),
        "global_row_count": global_count,
    }
    return payload


def gamma_layout_packet_identity(layout: Any) -> dict[str, Any]:
    """Describe one real Gamma layout without materializing a global Vec."""

    payload = _layout_json_payload(layout)
    keys = tuple(payload["canonical_keys"])
    transform_sha256 = hashlib.sha256(
        json.dumps(
            payload["blocks"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    layout_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "canonical_key_count_local": len(keys),
        "canonical_global_size": int(payload["global_row_count"]),
        "canonical_key_order_sha256": _canonical_key_order_sha256(keys),
        "canonical_key_set_local_sha256": _canonical_key_set_sha256(keys),
        "canonical_key_set_sha256": str(payload["global_key_set_sha256"]),
        "gamma_transform_sha256": transform_sha256,
        "canonical_layout_sha256": layout_sha256,
    }


def _canonical_gamma_values(
    vector: PETSc.Vec,
    layout: Any,
    provider: Callable[[PETSc.Vec, Any], Any],
    *,
    role: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    identity = gamma_layout_packet_identity(layout)
    raw = provider(vector, layout)
    values = np.asarray(raw)
    if (
        values.dtype != np.dtype(np.complex128)
        or values.ndim != 1
        or values.size != identity["canonical_key_count_local"]
        or not np.isfinite(values).all()
    ):
        raise ExactQualificationContractError(
            f"{role} canonical Gamma provider returned invalid complex128 values"
        )
    identity = {
        **identity,
        "role": role,
        "value_sha256": hash_array_bytes_sha256(values),
    }
    return np.asarray(values, dtype=np.complex128).copy(), identity


def make_current_exact_packet_identity_provider(
    *,
    lower_gamma_layout: Any,
    upper_gamma_layout: Any,
) -> Callable[
    [str, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
    Mapping[str, Any],
]:
    """Build the live, writer-independent identity provider for four packets.

    The provider derives canonical exact-output identity from the live packet
    returned for ``full_state`` and derives Gamma identity from the actual
    ``GammaCanonicalLayout`` objects.  It deliberately does not consume paths,
    file hashes, or any writer-returned metadata, so a writer cannot make an
    arbitrary persisted shard appear authoritative.
    """

    lower_layout_identity = gamma_layout_packet_identity(lower_gamma_layout)
    upper_layout_identity = gamma_layout_packet_identity(upper_gamma_layout)

    def provider(
        label: str,
        vectors: Mapping[str, Any],
        packet_audit: Mapping[str, Any],
        canonical_packet: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not isinstance(vectors, Mapping) or not isinstance(packet_audit, Mapping):
            raise TypeError("live packet identity inputs must be mappings")
        active_state = vectors.get("exact_output_active_state")
        if not isinstance(active_state, PETSc.Vec):
            raise TypeError("live packet identity provider requires full active Vec")
        if not isinstance(canonical_packet, Mapping):
            raise TypeError("live packet identity provider requires canonical packet")
        canonical_tokens = tuple(
            _canonical_key_token(value)
            for value in canonical_packet.get("tokens", ())
        )
        canonical_values = np.asarray(canonical_packet.get("values"))
        if (
            canonical_values.dtype != np.dtype(np.complex128)
            or canonical_values.ndim != 1
            or canonical_values.size != len(canonical_tokens)
            or not np.isfinite(canonical_values).all()
            or len(set(canonical_tokens)) != len(canonical_tokens)
        ):
            raise ExactQualificationContractError(
                "live packet identity provider received an invalid canonical packet"
            )
        source_provenance = _packet_provenance(
            {"source_provenance": packet_audit.get("source_provenance")}
        )
        source_definition_sha256 = packet_audit.get("source_definition_sha256")
        bare_f_operator_hash = packet_audit.get("bare_f_operator_hash")
        active_layout_sha256 = packet_audit.get("canonical_layout_sha256")
        active_key_set_sha256 = packet_audit.get("canonical_key_set_sha256")
        if not all(
            _is_hex_sha256(value)
            for value in (
                source_definition_sha256,
                bare_f_operator_hash,
                active_layout_sha256,
                active_key_set_sha256,
            )
        ):
            raise ExactQualificationContractError(
                "live packet identity provider lacks common packet identities"
            )
        comm = active_state.getComm().tompi4py()

        def common(
            role: str,
            value_sha256: str,
            *,
            layout_identity: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            layout_sha256 = (
                active_layout_sha256
                if layout_identity is None
                else layout_identity["canonical_layout_sha256"]
            )
            key_set_sha256 = (
                active_key_set_sha256
                if layout_identity is None
                else layout_identity["canonical_key_set_sha256"]
            )
            return {
                "label": str(label),
                "role": role,
                "dtype": "complex128",
                "rank": int(comm.rank),
                "mpi_size": int(comm.size),
                "value_sha256": str(value_sha256),
                "source_definition_sha256": str(source_definition_sha256),
                "bare_f_operator_hash": str(bare_f_operator_hash),
                "canonical_layout_sha256": str(layout_sha256),
                "canonical_key_set_sha256": str(key_set_sha256),
                "source_provenance": dict(source_provenance),
            }

        exact_audit = packet_audit.get("exact_output_canonical")
        if not isinstance(exact_audit, Mapping):
            raise ExactQualificationContractError(
                "live packet identity provider lacks exact-output audit"
            )
        exact_identity = {
            **common(
                "exact_output_canonical",
                hash_array_bytes_sha256(canonical_values),
            ),
            "canonical_key_count_local": int(len(canonical_tokens)),
            "global_active_size": int(active_state.getSize()),
            "canonical_key_order_sha256": _canonical_key_order_sha256(
                canonical_tokens
            ),
            "canonical_key_set_local_sha256": _canonical_key_set_sha256(
                canonical_tokens
            ),
            "canonical_roundtrip_relative": float(
                packet_audit["exact_output_canonical_roundtrip_relative"]
            ),
        }
        owner_values = np.asarray(active_state.array, dtype=np.complex128)
        owner_first, owner_last = map(int, active_state.getOwnershipRange())
        owner_identity = {
            **common(
                "exact_output_owner_rows",
                hash_array_bytes_sha256(owner_values),
            ),
            "local_size": int(active_state.getLocalSize()),
            "global_size": int(active_state.getSize()),
            "ownership_range": [owner_first, owner_last],
            "owner_row_order": "petsc_current_ownership_range",
        }

        result: dict[str, Any] = {
            "exact_output_canonical": exact_identity,
            "exact_output_owner_rows": owner_identity,
        }
        for role, vector_key, layout_identity in (
            (
                "gamma_l_canonical",
                "gamma_lower_canonical",
                lower_layout_identity,
            ),
            (
                "gamma_u_canonical",
                "gamma_upper_canonical",
                upper_layout_identity,
            ),
        ):
            values = np.asarray(vectors.get(vector_key))
            if (
                values.dtype != np.dtype(np.complex128)
                or values.ndim != 1
                or not np.isfinite(values).all()
                or values.size
                != int(layout_identity["canonical_key_count_local"])
            ):
                raise ExactQualificationContractError(
                    f"live packet identity provider received invalid {role} values"
                )
            result[role] = {
                **common(
                    role,
                    hash_array_bytes_sha256(values),
                    layout_identity=layout_identity,
                ),
                **layout_identity,
            }
            result[role]["role"] = role
            result[role]["label"] = str(label)
            result[role]["rank"] = int(comm.rank)
            result[role]["mpi_size"] = int(comm.size)
            result[role]["value_sha256"] = hash_array_bytes_sha256(values)
            result[role]["source_definition_sha256"] = str(
                source_definition_sha256
            )
            result[role]["bare_f_operator_hash"] = str(bare_f_operator_hash)
            result[role]["source_provenance"] = dict(source_provenance)
        return result

    return provider


def make_current_exact_solution_packet_consumer(
    *,
    system: Any,
    schur_action: Any,
    bare_operator: PETSc.Mat,
    packet_callback: Callable[
        [str, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
        Mapping[str, Any],
    ],
    canonical_packets_for_vector: Callable[..., Any],
    expected_packet_identity_provider: Callable[
        [str, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
        Mapping[str, Any],
    ],
    lower_gamma_layout: Any,
    upper_gamma_layout: Any,
    gamma_canonical_values_for_vector: Callable[[PETSc.Vec, Any], Any],
    exact_output_canonical_roundtrip: Callable[..., float],
    full_residual_tolerance: float = 1.0e-9,
) -> Callable[
    [str, Mapping[str, Any], PETSc.Vec, LoadedExactQualificationRHS], Mapping[str, Any]
]:
    """Create the accepted-solution bridge used by a current-layout consumer.

    The callback receives a caller-owned interface solution while its source
    bundle is still alive.  It reconstructs the full current active state,
    checks an independent explicit ``bare_operator`` residual, extracts the
    owner-local canonical Gamma vector, and hands both live vectors to a
    caller-owned packet writer.  The writer must copy or persist its values
    before returning; all temporary PETSc objects are destroyed here.
    """

    if not isinstance(bare_operator, PETSc.Mat):
        raise TypeError("exact packet consumer requires a PETSc bare operator")
    if not callable(canonical_packets_for_vector):
        raise TypeError("exact packet consumer requires the live canonical API")
    if not callable(expected_packet_identity_provider):
        raise TypeError(
            "exact packet consumer requires an independent packet identity provider"
        )
    if not callable(
        getattr(schur_action, "build_full_state_from_condensed_solution", None)
    ):
        raise TypeError("exact packet consumer requires the public recovery API")
    if not callable(getattr(schur_action, "extract_interface_from_active_vector", None)):
        raise TypeError("exact packet consumer requires the public Gamma extraction API")
    if not callable(getattr(schur_action, "restrict_interface", None)):
        raise TypeError("exact packet consumer requires the public Gamma split API")
    if lower_gamma_layout is None or upper_gamma_layout is None:
        raise TypeError("exact packet consumer requires lower and upper Gamma layouts")
    if not callable(gamma_canonical_values_for_vector):
        raise TypeError("exact packet consumer requires the canonical Gamma provider")
    if not callable(exact_output_canonical_roundtrip):
        raise TypeError(
            "exact packet consumer requires the exact-output canonical roundtrip"
        )
    # Validate the layout identities before the first accepted solution is
    # handed to a writer.  This also prevents a caller from passing a raw
    # group-vector descriptor in place of a real canonical layout.
    gamma_layout_packet_identity(lower_gamma_layout)
    gamma_layout_packet_identity(upper_gamma_layout)
    if not callable(packet_callback):
        raise TypeError("exact packet consumer requires a packet callback")
    try:
        tolerance = float(full_residual_tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("exact packet residual tolerance is not numeric") from exc
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("exact packet residual tolerance must be positive")

    def consume(
        label: str,
        checkpoint: Mapping[str, Any],
        accepted_solution: PETSc.Vec,
        bundle: LoadedExactQualificationRHS,
    ) -> Mapping[str, Any]:
        if not isinstance(accepted_solution, PETSc.Vec):
            raise TypeError("accepted exact solution is not a PETSc Vec")
        if not isinstance(bundle, LoadedExactQualificationRHS):
            raise TypeError("exact packet consumer received an invalid RHS bundle")
        packet_comm = bare_operator.getComm().tompi4py()
        full_state: PETSc.Vec | None = None
        interface_trace: PETSc.Vec | None = None
        gamma_lower: PETSc.Vec | None = None
        gamma_upper: PETSc.Vec | None = None
        residual: PETSc.Vec | None = None
        try:
            recovered = schur_action.build_full_state_from_condensed_solution(
                accepted_solution,
                bundle.interior_rhs_by_group,
            )
            if not isinstance(recovered, tuple) or len(recovered) != 2:
                raise TypeError(
                    "full-state recovery must return (Vec, mapping audit)"
                )
            full_state, recovery_audit = recovered
            if not isinstance(full_state, PETSc.Vec) or not isinstance(
                recovery_audit, Mapping
            ):
                raise TypeError("full-state recovery returned an invalid result")
            if (
                full_state.getSize() != bare_operator.getSize()[0]
                or full_state.getLocalSize()
                != bare_operator.getOwnershipRange()[1]
                - bare_operator.getOwnershipRange()[0]
                or tuple(map(int, full_state.getOwnershipRange()))
                != tuple(map(int, bare_operator.getOwnershipRange()))
            ):
                raise ValueError("recovered full state has the wrong bare-F layout")
            if bundle.active_rhs.getSize() != full_state.getSize() or tuple(
                map(int, bundle.active_rhs.getOwnershipRange())
            ) != tuple(map(int, full_state.getOwnershipRange())):
                raise ValueError("active RHS and recovered state layouts differ")
            residual = bare_operator.createVecLeft()
            bare_operator.mult(full_state, residual)
            residual.axpy(PETSc.ScalarType(-1.0), bundle.active_rhs)
            residual_norm = float(residual.norm())
            rhs_norm = float(bundle.active_rhs.norm())
            relative = residual_norm / max(rhs_norm, 1.0e-30)
            if (
                not np.isfinite(relative)
                or relative < 0.0
                or relative > tolerance
            ):
                raise ValueError(
                    f"accepted exact solution full residual exceeds tolerance: {relative}"
                )
            full_state_hash_after_residual = _distributed_vector_sha256(full_state)

            def require_full_state_unchanged(stage: str) -> None:
                observed_hash = _distributed_vector_sha256(full_state)
                if observed_hash != full_state_hash_after_residual:
                    raise ExactQualificationContractError(
                        "accepted full state changed during "
                        f"{stage} callback"
                    )

            interface_trace = schur_action.extract_interface_from_active_vector(full_state)
            if not isinstance(interface_trace, PETSc.Vec):
                raise TypeError("Gamma extraction returned a non-PETSc vector")
            split = schur_action.restrict_interface(interface_trace)
            if not isinstance(split, tuple) or len(split) != 2:
                raise TypeError("Gamma split did not return lower and upper vectors")
            gamma_lower, gamma_upper = split
            if not isinstance(gamma_lower, PETSc.Vec) or not isinstance(
                gamma_upper, PETSc.Vec
            ):
                raise TypeError("Gamma split returned a non-PETSc vector")
            def live_packet_stage() -> tuple[Any, ...]:
                live_result = canonical_packets_for_vector(system, full_state)
                if not isinstance(live_result, tuple) or len(live_result) < 3:
                    raise TypeError(
                        "live canonical packet API must return tokens, values, audit"
                    )
                if not isinstance(live_result[2], Mapping):
                    raise TypeError("live canonical packet audit is not a mapping")
                live_packet_audit = dict(live_result[2])
                try:
                    live_global_packet_count = int(
                        live_packet_audit["global_packet_count"]
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "live canonical packet global count is missing"
                    ) from exc
                if live_global_packet_count != int(full_state.getSize()):
                    raise ValueError(
                        "live canonical packet global count differs from current F size"
                    )
                canonical_tokens = tuple(
                    _canonical_key_token(value) for value in live_result[0]
                )
                raw_canonical_values = np.asarray(live_result[1])
                if raw_canonical_values.dtype != np.dtype(np.complex128):
                    raise ValueError(
                        "live exact-output canonical packet must be complex128"
                    )
                canonical_values = raw_canonical_values.copy()
                if (
                    len(canonical_tokens) != canonical_values.size
                    or canonical_values.ndim != 1
                    or len(set(canonical_tokens)) != len(canonical_tokens)
                    or not np.isfinite(canonical_values).all()
                ):
                    raise ValueError("live exact-output canonical packet is invalid")
                load_audit = bundle.audit.get("load")
                if not isinstance(load_audit, Mapping):
                    raise ValueError("exact RHS bundle lacks load provenance")
                live_key_order_sha256 = _canonical_key_order_sha256(canonical_tokens)
                live_key_set_local_sha256 = _canonical_key_set_sha256(canonical_tokens)
                if load_audit.get("canonical_key_order_sha256") != (
                    live_key_order_sha256
                ):
                    raise ValueError(
                        "live exact-output canonical key order differs from loaded layout"
                    )
                if load_audit.get("canonical_key_set_local_sha256") != (
                    live_key_set_local_sha256
                ):
                    raise ValueError(
                        "live exact-output local canonical key set differs from loaded layout"
                    )
                source_provenance = _packet_provenance(load_audit)
                source_definition_sha256 = load_audit.get(
                    "source_definition_sha256"
                )
                bare_f_operator_hash = load_audit.get("bare_f_operator_hash")
                canonical_layout_sha256 = load_audit.get("canonical_layout_sha256")
                canonical_key_set_sha256 = load_audit.get(
                    "canonical_key_set_sha256"
                )
                if not all(
                    _is_hex_sha256(value)
                    for value in (
                        source_definition_sha256,
                        bare_f_operator_hash,
                        canonical_layout_sha256,
                        canonical_key_set_sha256,
                    )
                ):
                    raise ValueError("exact RHS load provenance lacks packet identities")
                return (
                    live_result,
                    live_packet_audit,
                    live_global_packet_count,
                    canonical_tokens,
                    canonical_values,
                    live_key_order_sha256,
                    live_key_set_local_sha256,
                    source_provenance,
                    source_definition_sha256,
                    bare_f_operator_hash,
                    canonical_layout_sha256,
                    canonical_key_set_sha256,
                )

            (
                live_result,
                live_packet_audit,
                live_global_packet_count,
                canonical_tokens,
                canonical_values,
                live_key_order_sha256,
                live_key_set_local_sha256,
                source_provenance,
                source_definition_sha256,
                bare_f_operator_hash,
                canonical_layout_sha256,
                canonical_key_set_sha256,
            ) = _collective_contract_call(
                packet_comm,
                "live canonical packet validation and load provenance",
                live_packet_stage,
            )

            # The callback above is local contract work.  Do not put this
            # distributed hash inside it: if one rank fails validation, the
            # contract allgather must complete before every rank enters this
            # next collective hash check.
            require_full_state_unchanged("live canonical packet")

            def checked_exact_output_roundtrip() -> float:
                try:
                    roundtrip = float(
                        exact_output_canonical_roundtrip(
                            system,
                            canonical_tokens,
                            canonical_values.copy(),
                            full_state,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    raise ExactQualificationContractError(
                        "exact-output canonical roundtrip is not numeric"
                    ) from exc
                if (
                    not np.isfinite(roundtrip)
                    or roundtrip < 0.0
                    or roundtrip > 1.0e-12
                ):
                    raise ExactQualificationContractError(
                        "exact-output canonical roundtrip exceeds 1e-12: "
                        f"{roundtrip}"
                    )
                return roundtrip

            exact_output_roundtrip_relative = _collective_contract_call(
                packet_comm,
                "exact-output canonical roundtrip",
                checked_exact_output_roundtrip,
            )

            require_full_state_unchanged("exact-output canonical roundtrip")

            def lower_gamma_stage() -> tuple[np.ndarray, dict[str, Any]]:
                result = _canonical_gamma_values(
                    full_state,
                    lower_gamma_layout,
                    gamma_canonical_values_for_vector,
                    role="gamma_l_canonical",
                )
                return result

            def upper_gamma_stage() -> tuple[np.ndarray, dict[str, Any]]:
                result = _canonical_gamma_values(
                    full_state,
                    upper_gamma_layout,
                    gamma_canonical_values_for_vector,
                    role="gamma_u_canonical",
                )
                return result

            lower_canonical_values, lower_identity = _collective_contract_call(
                packet_comm,
                "lower Gamma canonical construction",
                lower_gamma_stage,
            )
            require_full_state_unchanged("lower Gamma canonical")

            upper_canonical_values, upper_identity = _collective_contract_call(
                packet_comm,
                "upper Gamma canonical construction",
                upper_gamma_stage,
            )
            require_full_state_unchanged("upper Gamma canonical")

            def _common_packet(role: str, value_sha256: str) -> dict[str, Any]:
                return {
                    "label": str(label),
                    "role": role,
                    "dtype": "complex128",
                    "rank": int(packet_comm.rank),
                    "mpi_size": int(packet_comm.size),
                    "value_sha256": str(value_sha256),
                    "source_definition_sha256": str(source_definition_sha256),
                    "bare_f_operator_hash": str(bare_f_operator_hash),
                    "canonical_layout_sha256": str(canonical_layout_sha256),
                    "canonical_key_set_sha256": str(canonical_key_set_sha256),
                    "source_provenance": source_provenance,
                }

            owner_first, owner_last = map(int, full_state.getOwnershipRange())
            packet_audit: dict[str, Any] = {
                "label": str(label),
                "accepted_iteration": checkpoint.get("iteration"),
                "full_residual_norm": residual_norm,
                "full_residual_relative": relative,
                "full_residual_tolerance": tolerance,
                "recovery": _compact_recovery_audit(recovery_audit),
                "source_definition_sha256": str(source_definition_sha256),
                "bare_f_operator_hash": str(bare_f_operator_hash),
                "canonical_layout_sha256": str(canonical_layout_sha256),
                "canonical_key_set_sha256": str(canonical_key_set_sha256),
                "source_provenance": source_provenance,
                "live_global_packet_count": live_global_packet_count,
                "numeric_allgather": False,
                "full_numeric_replica": False,
                "exact_output_canonical_roundtrip_relative": (
                    exact_output_roundtrip_relative
                ),
                "exact_output_canonical_roundtrip_pass": True,
                "packet_roles": list(_PACKET_WRITE_ROLES),
                "exact_output_canonical": {
                    **_common_packet(
                        "exact_output_canonical",
                        hash_array_bytes_sha256(canonical_values),
                    ),
                    "canonical_key_count_local": int(len(canonical_tokens)),
                    "global_active_size": int(full_state.getSize()),
                    "canonical_key_order_sha256": live_key_order_sha256,
                    "canonical_key_set_local_sha256": live_key_set_local_sha256,
                    "canonical_roundtrip_relative": (
                        exact_output_roundtrip_relative
                    ),
                },
                "exact_output_owner_rows": {
                    **_common_packet(
                        "exact_output_owner_rows",
                        hash_array_bytes_sha256(
                            np.asarray(full_state.array, dtype=np.complex128)
                        ),
                    ),
                    "local_size": int(full_state.getLocalSize()),
                    "global_size": int(full_state.getSize()),
                    "ownership_range": [owner_first, owner_last],
                    "owner_row_order": "petsc_current_ownership_range",
                },
                "gamma_l_canonical": {
                    **_common_packet(
                        "gamma_l_canonical", lower_identity["value_sha256"]
                    ),
                    **lower_identity,
                },
                "gamma_u_canonical": {
                    **_common_packet(
                        "gamma_u_canonical", upper_identity["value_sha256"]
                    ),
                    **upper_identity,
                },
            }
            packet_vectors = {
                "exact_output_active_state": full_state,
                "gamma_lower_raw": gamma_lower,
                "gamma_upper_raw": gamma_upper,
                "gamma_lower_canonical": lower_canonical_values,
                "gamma_upper_canonical": upper_canonical_values,
            }
            canonical_packet = {
                "tokens": canonical_tokens,
                "values": canonical_values,
                "audit": live_packet_audit,
            }
            def expected_identity_stage() -> dict[str, Any]:
                expected = expected_packet_identity_provider(
                    str(label),
                    packet_vectors,
                    packet_audit,
                    canonical_packet,
                )
                return _normalize_expected_packet_identities(str(label), expected)

            expected_packet_identities = _collective_contract_call(
                packet_comm,
                "live packet expected-identity construction",
                expected_identity_stage,
            )
            require_full_state_unchanged("live packet expected-identity")

            actual_packet_identities = _collective_contract_call(
                packet_comm,
                "live packet identity normalization",
                lambda: _normalize_expected_packet_identities(
                    str(label),
                    {
                        role: packet_audit[role]
                        for role in _PACKET_WRITE_ROLES
                    },
                ),
            )
            _collective_contract_call(
                packet_comm,
                "live packet identity comparison",
                lambda: [
                    _compare_packet_identity(
                        role,
                        actual_packet_identities[role],
                        expected_packet_identities[role],
                        context="live packet",
                    )
                    for role in _PACKET_WRITE_ROLES
                ],
            )
            packet_audit["expected_packet_identities"] = expected_packet_identities
            packet_audit["live_packet_identities"] = {
                role: actual_packet_identities[role]
                for role in _PACKET_WRITE_ROLES
            }

            vector_hashes_before = {
                key: hash_array_bytes_sha256(
                    np.asarray(vector.array, dtype=np.complex128)
                )
                for key, vector in packet_vectors.items()
                if isinstance(vector, PETSc.Vec)
            }
            array_hashes_before = {
                key: hash_array_bytes_sha256(np.asarray(values))
                for key, values in packet_vectors.items()
                if not isinstance(values, PETSc.Vec)
            }
            writer_audit: Mapping[str, Any] | None = None
            normalized_writer_audit: dict[str, Any] | None = None
            writer_error: str | None = None
            require_full_state_unchanged("packet writer before")
            try:
                writer_audit = packet_callback(
                    str(label),
                    checkpoint,
                    packet_vectors,
                    packet_audit,
                    {
                        "tokens": canonical_tokens,
                        "values": canonical_values,
                        "audit": (
                            live_result[2]
                            if len(live_result) > 2
                            and isinstance(live_result[2], Mapping)
                            else {}
                        ),
                    },
                )
                for key, vector in packet_vectors.items():
                    if isinstance(vector, PETSc.Vec):
                        if not bool(vector):
                            raise ValueError(
                                f"packet writer destroyed input vector {key}"
                            )
                        vector_hash_after = hash_array_bytes_sha256(
                            np.asarray(vector.array, dtype=np.complex128)
                        )
                        if vector_hash_after != vector_hashes_before[key]:
                            raise ValueError(
                                f"packet writer mutated input vector {key}"
                            )
                    else:
                        array_hash_after = hash_array_bytes_sha256(np.asarray(vector))
                        if array_hash_after != array_hashes_before[key]:
                            raise ValueError(
                                f"packet writer mutated input array {key}"
                            )
                if not isinstance(writer_audit, Mapping):
                    raise TypeError("exact packet writer must return a mapping audit")
                normalized_writer_audit = _validate_packet_write_audit(
                    str(label),
                    writer_audit,
                    expected_packet_identities=expected_packet_identities,
                )
            except Exception as exc:
                writer_error = f"{type(exc).__name__}: {exc}"
            writer_errors = packet_comm.allgather(writer_error)
            first_writer_error = next(
                (error for error in writer_errors if error is not None), None
            )
            if first_writer_error is not None:
                raise ExactQualificationContractError(
                    "collective exact packet callback failed: "
                    f"{first_writer_error}"
                )
            require_full_state_unchanged("packet writer")
            if normalized_writer_audit is None:
                raise ExactQualificationContractError(
                    "collective exact packet callback produced no validated audit"
                )
            packet_audit["packet_write"] = normalized_writer_audit
            return _json_safe_binding(packet_audit)
        finally:
            if gamma_upper is not None:
                gamma_upper.destroy()
            if gamma_lower is not None:
                gamma_lower.destroy()
            if interface_trace is not None:
                interface_trace.destroy()
            if residual is not None:
                residual.destroy()
            if full_state is not None:
                full_state.destroy()

    return consume


_PACKET_WRITE_ROLES = (
    "exact_output_canonical",
    "exact_output_owner_rows",
    "gamma_l_canonical",
    "gamma_u_canonical",
)


def _packet_identity_fields(role: str) -> tuple[str, ...]:
    """Return the non-artifact fields for one packet role.

    Canonical packets are keyed by a physical canonical order, not by a
    contiguous PETSc ownership range.  Only the owner-row role carries
    ``local_size``/``global_size``/``ownership_range``.
    """

    common = (
        "label",
        "role",
        "dtype",
        "rank",
        "mpi_size",
        "value_sha256",
        "source_definition_sha256",
        "bare_f_operator_hash",
        "canonical_layout_sha256",
        "canonical_key_set_sha256",
        "source_provenance",
    )
    if role == "exact_output_canonical":
        return common + (
            "canonical_key_count_local",
            "global_active_size",
            "canonical_key_order_sha256",
            "canonical_key_set_local_sha256",
            "canonical_roundtrip_relative",
        )
    if role == "exact_output_owner_rows":
        return common + (
            "local_size",
            "global_size",
            "ownership_range",
            "owner_row_order",
        )
    if role in ("gamma_l_canonical", "gamma_u_canonical"):
        return common + (
            "canonical_key_count_local",
            "canonical_global_size",
            "canonical_key_order_sha256",
            "canonical_key_set_local_sha256",
            "gamma_transform_sha256",
        )
    raise ValueError(f"unknown exact packet role: {role}")


def _compare_packet_identity(
    role: str,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    context: str,
) -> None:
    for field in _packet_identity_fields(role):
        if actual.get(field) != expected.get(field):
            raise ValueError(
                f"{context} {role} differs from expected identity for {field}"
            )


def _normalize_packet_identity(
    label: str,
    role: str,
    packet: Mapping[str, Any],
    *,
    require_writer_identity: bool,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    if not isinstance(packet, Mapping):
        raise TypeError(f"packet identity for {role} is not a mapping")
    if packet.get("label") != label:
        raise ValueError(f"packet identity {role} label does not match source")
    if packet.get("role") != role:
        raise ValueError(f"packet identity {role} role field is invalid")
    if packet.get("dtype") != "complex128":
        raise ValueError(f"packet identity {role} dtype must be complex128")
    try:
        packet_rank = int(packet["rank"])
        packet_mpi_size = int(packet["mpi_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"packet identity {role} rank/mpi_size is invalid") from exc
    if packet_rank < 0 or packet_mpi_size <= packet_rank:
        raise ValueError(f"packet identity {role} rank/mpi_size is invalid")
    for field in (
        "value_sha256",
        "source_definition_sha256",
        "bare_f_operator_hash",
        "canonical_layout_sha256",
        "canonical_key_set_sha256",
    ):
        if not _is_hex_sha256(packet.get(field)):
            raise ValueError(
                f"packet identity {role} {field} is not a SHA256 digest"
            )
    source_provenance = _packet_provenance(packet)
    normalized: dict[str, Any] = {
        "label": label,
        "role": role,
        "dtype": "complex128",
        "rank": packet_rank,
        "mpi_size": packet_mpi_size,
        "value_sha256": str(packet["value_sha256"]),
        "source_definition_sha256": str(packet["source_definition_sha256"]),
        "bare_f_operator_hash": str(packet["bare_f_operator_hash"]),
        "canonical_layout_sha256": str(packet["canonical_layout_sha256"]),
        "canonical_key_set_sha256": str(packet["canonical_key_set_sha256"]),
        "source_provenance": source_provenance,
    }
    if role == "exact_output_canonical":
        try:
            canonical_count = int(packet["canonical_key_count_local"])
            global_active_size = int(packet["global_active_size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"packet identity {role} canonical size is invalid"
            ) from exc
        if canonical_count < 0 or global_active_size <= 0:
            raise ValueError(f"packet identity {role} canonical size is invalid")
        normalized.update(
            {
                "canonical_key_count_local": canonical_count,
                "global_active_size": global_active_size,
                "canonical_key_order_sha256": str(
                    packet["canonical_key_order_sha256"]
                ),
                "canonical_key_set_local_sha256": str(
                    packet["canonical_key_set_local_sha256"]
                ),
                "canonical_roundtrip_relative": float(
                    packet["canonical_roundtrip_relative"]
                ),
            }
        )
        for field in (
            "canonical_key_order_sha256",
            "canonical_key_set_local_sha256",
        ):
            if not _is_hex_sha256(normalized[field]):
                raise ValueError(
                    f"packet identity {role} {field} is not a SHA256 digest"
                )
        if (
            not np.isfinite(normalized["canonical_roundtrip_relative"])
            or normalized["canonical_roundtrip_relative"] < 0.0
            or normalized["canonical_roundtrip_relative"] > 1.0e-12
        ):
            raise ValueError(
                f"packet identity {role} canonical roundtrip exceeds 1e-12"
            )
    elif role == "exact_output_owner_rows":
        try:
            local_size = int(packet["local_size"])
            global_size = int(packet["global_size"])
            ownership = tuple(int(value) for value in packet["ownership_range"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"packet identity {role} size is invalid") from exc
        if (
            local_size < 0
            or global_size <= 0
            or len(ownership) != 2
            or ownership[0] < 0
            or ownership[1] < ownership[0]
            or ownership[1] > global_size
            or ownership[1] - ownership[0] != local_size
        ):
            raise ValueError(f"packet identity {role} ownership range is invalid")
        owner_order = packet.get("owner_row_order")
        if owner_order != "petsc_current_ownership_range":
            raise ValueError(f"packet identity {role} owner-row order is invalid")
        normalized.update(
            {
                "local_size": local_size,
                "global_size": global_size,
                "ownership_range": [ownership[0], ownership[1]],
                "owner_row_order": owner_order,
            }
        )
    else:
        try:
            canonical_count = int(packet["canonical_key_count_local"])
            canonical_global_size = int(packet["canonical_global_size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"packet identity {role} canonical size is invalid") from exc
        if canonical_count < 0 or canonical_global_size <= 0:
            raise ValueError(f"packet identity {role} canonical size is invalid")
        normalized.update(
            {
                "canonical_key_count_local": canonical_count,
                "canonical_global_size": canonical_global_size,
                "canonical_key_order_sha256": str(
                    packet["canonical_key_order_sha256"]
                ),
                "canonical_key_set_local_sha256": str(
                    packet["canonical_key_set_local_sha256"]
                ),
                "gamma_transform_sha256": str(packet["gamma_transform_sha256"]),
            }
        )
        for field in (
            "canonical_key_order_sha256",
            "canonical_key_set_local_sha256",
            "gamma_transform_sha256",
        ):
            if not _is_hex_sha256(normalized[field]):
                raise ValueError(
                    f"packet identity {role} {field} is not a SHA256 digest"
                )
    path = packet.get("path")
    writer_identity = packet.get("writer_identity")
    if require_writer_identity and not isinstance(path, str):
        raise ValueError(f"packet writer {role} lacks a metadata path")
    if require_artifacts:
        for field in (
            "path",
            "array_path",
            "manifest_path",
            "array_sha256",
            "metadata_sha256",
            "shard_sha256",
            "manifest_sha256",
        ):
            if field == "path" or field.endswith("_path"):
                if not isinstance(packet.get(field), str) or not packet[field]:
                    raise ValueError(f"packet writer {role} {field} is missing")
            elif not _is_hex_sha256(packet.get(field)):
                raise ValueError(
                    f"packet writer {role} {field} is not a SHA256 digest"
                )
    if isinstance(path, str):
        normalized["path"] = path
    if isinstance(writer_identity, str):
        normalized["writer_identity"] = writer_identity
    if require_artifacts:
        normalized.update(
            {
                "array_path": str(packet["array_path"]),
                "manifest_path": str(packet["manifest_path"]),
                "array_sha256": str(packet["array_sha256"]),
                "metadata_sha256": str(packet["metadata_sha256"]),
                "shard_sha256": str(packet["shard_sha256"]),
                "manifest_sha256": str(packet["manifest_sha256"]),
            }
        )
    return normalized


def _normalize_expected_packet_identities(
    label: str, expected: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    if not isinstance(expected, Mapping):
        raise TypeError("expected packet identities must be a mapping")
    if set(expected) != set(_PACKET_WRITE_ROLES):
        raise ValueError("expected packet identities must contain exactly four roles")
    return {
        role: _normalize_packet_identity(
            label,
            role,
            expected[role],
            require_writer_identity=False,
            require_artifacts=False,
        )
        for role in _PACKET_WRITE_ROLES
    }


def _validate_written_packet_artifacts(
    label: str,
    role: str,
    packet: Mapping[str, Any],
) -> None:
    """Re-open a writer's four artifacts and recompute their file identities."""

    metadata_path = Path(str(packet["path"]))
    array_path = Path(str(packet["array_path"]))
    manifest_path = Path(str(packet["manifest_path"]))
    if not metadata_path.is_file() or not array_path.is_file() or not manifest_path.is_file():
        raise ValueError(f"packet writer {role} did not persist all artifacts")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"packet writer {role} artifact JSON is unreadable") from exc
    if not isinstance(metadata, Mapping) or not isinstance(manifest, Mapping):
        raise ValueError(f"packet writer {role} artifacts are not JSON objects")
    for artifact, name in ((metadata, "metadata"), (manifest, "manifest")):
        if artifact.get("label") != label or artifact.get("role") != role:
            raise ValueError(f"packet writer {role} {name} identity is wrong")
    for field in _packet_identity_fields(role):
        if metadata.get(field) != packet.get(field):
            raise ValueError(f"packet writer {role} metadata differs for {field}")
        if manifest.get(field) != packet.get(field):
            raise ValueError(f"packet writer {role} manifest differs for {field}")
    for artifact, name in ((metadata, "metadata"), (manifest, "manifest")):
        for field in ("path", "array_path", "manifest_path"):
            if artifact.get(field) != packet.get(field):
                raise ValueError(f"packet writer {role} {name} differs for {field}")
    expected_size = (
        packet["canonical_key_count_local"]
        if role != "exact_output_owner_rows"
        else packet["local_size"]
    )
    try:
        values = np.load(array_path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError(f"packet writer {role} array cannot be loaded") from exc
    values = np.asarray(values)
    if (
        values.ndim != 1
        or values.dtype != np.dtype(np.complex128)
        or values.size != int(expected_size)
        or not np.isfinite(values).all()
    ):
        raise ValueError(f"packet writer {role} array is not a finite vector")
    observed_value_sha256 = hash_array_bytes_sha256(values)
    if observed_value_sha256 != packet["value_sha256"]:
        raise ValueError(f"packet writer {role} value hash differs from array")
    if observed_value_sha256 != packet["array_sha256"]:
        raise ValueError(f"packet writer {role} array hash is inconsistent")
    if metadata.get("array_sha256") != packet["array_sha256"]:
        raise ValueError(f"packet writer {role} metadata array hash is inconsistent")
    if manifest.get("array_sha256") != packet["array_sha256"]:
        raise ValueError(f"packet writer {role} manifest array hash is inconsistent")
    observed_metadata_sha256 = hash_file_sha256(metadata_path)
    observed_shard_sha256 = hash_file_sha256(array_path)
    observed_manifest_sha256 = hash_file_sha256(manifest_path)
    if observed_metadata_sha256 != packet["metadata_sha256"]:
        raise ValueError(f"packet writer {role} metadata file hash differs")
    if observed_shard_sha256 != packet["shard_sha256"]:
        raise ValueError(f"packet writer {role} shard file hash differs")
    if observed_manifest_sha256 != packet["manifest_sha256"]:
        raise ValueError(f"packet writer {role} manifest file hash differs")
    if manifest.get("metadata_sha256") != packet["metadata_sha256"]:
        raise ValueError(f"packet writer {role} manifest metadata hash is inconsistent")
    if manifest.get("shard_sha256") != packet["shard_sha256"]:
        raise ValueError(f"packet writer {role} manifest shard hash is inconsistent")


def _validate_packet_write_audit(
    label: str,
    writer_audit: Mapping[str, Any],
    *,
    expected_packet_identities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate the small, JSON-safe contract returned by a packet writer."""

    if not isinstance(writer_audit, Mapping):
        raise TypeError("packet writer audit must be a mapping")
    if set(writer_audit) != set(_PACKET_WRITE_ROLES):
        raise ValueError("packet writer audit must contain exactly four roles")
    expected = None
    if expected_packet_identities is not None:
        expected = _normalize_expected_packet_identities(
            label, expected_packet_identities
        )
    packets: dict[str, Any] = {}
    for role in _PACKET_WRITE_ROLES:
        packet = writer_audit.get(role)
        packets[role] = _normalize_packet_identity(
            label,
            role,
            packet,
            require_writer_identity=True,
            require_artifacts=True,
        )
        if expected is not None:
            _compare_packet_identity(
                role,
                packets[role],
                expected[role],
                context="packet writer",
            )
        _validate_written_packet_artifacts(label, role, packets[role])
    return packets


def _collective_contract_call(
    comm: MPI.Intracomm,
    stage: str,
    callback: Callable[[], Any],
) -> Any:
    """Run one local contract stage and propagate failures before proceeding.

    The callback itself is deliberately small and must not diverge into a
    rank-dependent collective.  A caller can therefore use this guard after a
    PETSc/API operation or around local metadata validation: one rank's error
    is converted into the same controlled contract error on every rank before
    the next collective boundary.
    """

    value: Any = None
    local_error: str | None = None
    try:
        value = callback()
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    first = next((error for error in errors if error is not None), None)
    if first is not None:
        raise ExactQualificationContractError(
            f"collective packet contract failed at {stage}: {first}"
        )
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> str:
    """Write one JSON artifact atomically and return its file hash."""

    encoded = (
        json.dumps(
            _json_safe_binding(payload),
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return hash_file_sha256(path)


def _write_npy_atomic(path: Path, values: np.ndarray) -> None:
    """Persist an NPY array without exposing a partially written target."""

    temporary = path.with_name(f".{path.name}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
        stream.flush()
    temporary.replace(path)


def _ensure_packet_output_root(
    root: str | Path,
    forbidden_root: str | Path | None,
) -> Path:
    output_root = Path(root).resolve()
    if forbidden_root is not None:
        forbidden = Path(forbidden_root).resolve()
        try:
            output_root.relative_to(forbidden)
        except ValueError:
            try:
                forbidden.relative_to(output_root)
            except ValueError:
                pass
            else:
                raise ExactQualificationContractError(
                    "packet output root must be disjoint from the forbidden root"
                )
        else:
            raise ExactQualificationContractError(
                "packet output root must be disjoint from the forbidden root"
            )
    return output_root


def write_current_exact_solution_packet(
    *,
    root: str | Path,
    rank: int,
    label: str,
    packet_values: Mapping[str, np.ndarray],
    packet_identities: Mapping[str, Mapping[str, Any]],
    source_provenance: Mapping[str, Any] | None = None,
    forbidden_root: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Persist the four current-layout exact-output packet roles.

    ``packet_identities`` is independently produced by the live consumer and
    contains no writer-specific file hashes.  This function writes strict
    complex128 arrays, metadata, and per-role manifests, then reopens every
    artifact through the same validator used by the consumer.  Canonical
    roles never receive a fabricated PETSc ownership range.
    """

    output_root = _ensure_packet_output_root(root, forbidden_root)
    if not isinstance(label, str) or not label or "/" in label or "\\" in label:
        raise ExactQualificationContractError("packet label is not a safe path name")
    try:
        packet_rank = int(rank)
    except (TypeError, ValueError) as exc:
        raise ExactQualificationContractError("packet rank is not integral") from exc
    if packet_rank < 0:
        raise ExactQualificationContractError("packet rank is negative")
    if not isinstance(packet_values, Mapping) or set(packet_values) != set(
        _PACKET_WRITE_ROLES
    ):
        raise ExactQualificationContractError(
            "packet values must contain exactly four roles"
        )
    if not isinstance(packet_identities, Mapping) or set(packet_identities) != set(
        _PACKET_WRITE_ROLES
    ):
        raise ExactQualificationContractError(
            "packet identities must contain exactly four roles"
        )

    normalized: dict[str, dict[str, Any]] = {}
    for role in _PACKET_WRITE_ROLES:
        normalized_role = _normalize_packet_identity(
            label,
            role,
            packet_identities[role],
            require_writer_identity=False,
            require_artifacts=False,
        )
        if normalized_role["rank"] != packet_rank:
            raise ExactQualificationContractError(
                f"packet identity {role} rank does not match writer rank"
            )
        values = np.asarray(packet_values[role])
        if (
            values.ndim != 1
            or values.dtype != np.dtype(np.complex128)
            or not np.isfinite(values).all()
        ):
            raise ExactQualificationContractError(
                f"packet writer {role} requires a finite one-dimensional complex128 array"
            )
        expected_size = (
            normalized_role["canonical_key_count_local"]
            if role != "exact_output_owner_rows"
            else normalized_role["local_size"]
        )
        if values.size != int(expected_size):
            raise ExactQualificationContractError(
                f"packet writer {role} array length differs from identity"
            )
        observed_value_sha256 = hash_array_bytes_sha256(values)
        if observed_value_sha256 != normalized_role["value_sha256"]:
            raise ExactQualificationContractError(
                f"packet writer {role} values differ from expected identity"
            )
        normalized[role] = normalized_role

    expected_provenance = normalized[_PACKET_WRITE_ROLES[0]]["source_provenance"]
    if source_provenance is not None:
        supplied_provenance = _packet_provenance(
            {"source_provenance": source_provenance}
        )
        if supplied_provenance != expected_provenance:
            raise ExactQualificationContractError(
                "packet writer source provenance differs from packet identities"
            )
    if any(
        packet["source_provenance"] != expected_provenance
        for packet in normalized.values()
    ):
        raise ExactQualificationContractError(
            "packet roles do not share one source provenance"
        )

    role_root = output_root / f"rank{packet_rank:04d}" / label
    result: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for role in _PACKET_WRITE_ROLES:
        core = dict(normalized[role])
        role_stem = role
        array_path = role_root / f"{role_stem}.npy"
        metadata_path = role_root / f"{role_stem}.json"
        manifest_path = role_root / f"{role_stem}.manifest.json"
        role_paths = (str(array_path), str(metadata_path), str(manifest_path))
        if paths.intersection(role_paths):
            raise ExactQualificationContractError(
                "packet writer generated duplicate artifact paths"
            )
        paths.update(role_paths)
        values = np.asarray(packet_values[role])
        _write_npy_atomic(array_path, values)
        array_sha256 = hash_array_bytes_sha256(values)
        shard_sha256 = hash_file_sha256(array_path)
        record_base = {
            **core,
            "path": str(metadata_path),
            "array_path": str(array_path),
            "manifest_path": str(manifest_path),
            "array_sha256": array_sha256,
            "shard_sha256": shard_sha256,
            "writer_identity": "task040.v6.current_exact_packet_writer.v1",
        }
        metadata_sha256 = _write_json_atomic(metadata_path, record_base)
        manifest_sha256 = _write_json_atomic(
            manifest_path,
            {
                **record_base,
                "metadata_sha256": metadata_sha256,
            },
        )
        record = {
            **record_base,
            "metadata_sha256": metadata_sha256,
            "manifest_sha256": manifest_sha256,
        }
        normalized_record = _normalize_packet_identity(
            label,
            role,
            record,
            require_writer_identity=True,
            require_artifacts=True,
        )
        _validate_written_packet_artifacts(label, role, normalized_record)
        result[role] = normalized_record
    return result


def make_current_exact_packet_writer(
    *,
    root: str | Path,
    rank: int,
    forbidden_root: str | Path | None = None,
) -> Callable[..., Mapping[str, Any]]:
    """Build the formal callback that writes four roles from live vectors."""

    def callback(
        label: str,
        _checkpoint: Mapping[str, Any],
        vectors: Mapping[str, Any],
        packet_audit: Mapping[str, Any],
        canonical_packet: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        live_identities = {
            role: packet_audit.get(role) for role in _PACKET_WRITE_ROLES
        }
        if any(
            not isinstance(live_identities[role], Mapping)
            for role in _PACKET_WRITE_ROLES
        ):
            raise ExactQualificationContractError(
                "packet writer callback lacks live packet identities"
            )
        required_vectors = (
            "exact_output_active_state",
            "gamma_lower_canonical",
            "gamma_upper_canonical",
        )
        if any(key not in vectors for key in required_vectors):
            raise ExactQualificationContractError(
                "packet writer callback lacks live canonical packet values"
            )
        active_state = vectors["exact_output_active_state"]
        if not isinstance(active_state, PETSc.Vec):
            raise TypeError("packet writer exact active state is not a PETSc Vec")
        packet_comm = active_state.getComm().tompi4py()
        values = {
            "exact_output_canonical": np.asarray(canonical_packet["values"]),
            "exact_output_owner_rows": np.asarray(active_state.array).copy(),
            "gamma_l_canonical": np.asarray(vectors["gamma_lower_canonical"]),
            "gamma_u_canonical": np.asarray(vectors["gamma_upper_canonical"]),
        }
        local_result: Mapping[str, Any] | None = None
        local_error: str | None = None
        try:
            local_result = write_current_exact_solution_packet(
                root=root,
                rank=rank,
                label=label,
                packet_values=values,
                packet_identities=live_identities,
                source_provenance=packet_audit.get("source_provenance"),
                forbidden_root=forbidden_root,
            )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        errors = packet_comm.allgather(local_error)
        first_error = next((error for error in errors if error is not None), None)
        if first_error is not None:
            raise ExactQualificationContractError(
                f"collective exact packet writer failed: {first_error}"
            )
        if local_result is None:
            raise ExactQualificationContractError(
                "collective exact packet writer produced no result"
            )
        return local_result

    return callback


def aggregate_exact_packet_manifests(
    local_packets: Mapping[str, Mapping[str, Any]],
    *,
    root: str | Path,
    label: str,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    source_provenance: Mapping[str, Any] | None = None,
    qualification_source_provenance: Mapping[str, Any] | None = None,
    frozen_rhs_descriptor_metadata_sha256: Mapping[str, str] | None = None,
    expected_gamma_global_sizes: Mapping[str, int] | None = None,
    forbidden_root: str | Path | None = None,
) -> dict[str, Any]:
    """Gather only role metadata and write one all-rank manifest on root."""

    output_root: Path | None = None
    expected_provenance: dict[str, Any] | None = None
    qualification_provenance: dict[str, Any] | None = None
    descriptor_metadata_hashes: dict[str, str] | None = None
    preflight_error: str | None = None
    try:
        output_root = _ensure_packet_output_root(root, forbidden_root)
        if source_provenance is not None:
            expected_provenance = _packet_provenance(
                {"source_provenance": source_provenance}
            )
        if qualification_source_provenance is not None:
            qualification_provenance = _packet_provenance(
                {"source_provenance": qualification_source_provenance}
            )
        if (
            expected_provenance is not None
            and qualification_provenance is not None
            and any(
                expected_provenance[field] != qualification_provenance[field]
                for field in expected_provenance
                if field != "source_sha"
            )
        ):
            raise ExactQualificationContractError(
                "packet aggregate qualification and frozen provenance disagree"
            )
        if frozen_rhs_descriptor_metadata_sha256 is not None:
            if not isinstance(frozen_rhs_descriptor_metadata_sha256, Mapping):
                raise TypeError(
                    "packet aggregate frozen descriptor metadata hashes must be a mapping"
                )
            if tuple(str(label) for label in frozen_rhs_descriptor_metadata_sha256) != (
                "external_dtn_coupling",
                "fixed_random_repeat_0",
                "modal_traction_positive",
                "modal_traction_negative",
                "fixed_random_repeat_1",
            ):
                raise ValueError(
                    "packet aggregate descriptor metadata hashes have invalid label order"
                )
            descriptor_metadata_hashes = {}
            for source_label, digest in frozen_rhs_descriptor_metadata_sha256.items():
                if not isinstance(digest, str) or len(digest) != 64:
                    raise ValueError(
                        f"packet aggregate metadata hash is invalid for {source_label}"
                    )
                try:
                    int(digest, 16)
                except ValueError as exc:
                    raise ValueError(
                        f"packet aggregate metadata hash is invalid for {source_label}"
                    ) from exc
                descriptor_metadata_hashes[str(source_label)] = digest
    except Exception as exc:
        preflight_error = f"{type(exc).__name__}: {exc}"
    preflight_errors = comm.allgather(preflight_error)
    first_preflight_error = next(
        (error for error in preflight_errors if error is not None), None
    )
    if first_preflight_error is not None:
        raise ExactQualificationContractError(
            "collective packet aggregate preflight failed: "
            f"{first_preflight_error}"
        )
    assert output_root is not None
    qualification_chain = json.dumps(
        qualification_provenance,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(set(comm.allgather(qualification_chain))) != 1:
        raise ExactQualificationContractError(
            "packet aggregate qualification identity differs across ranks"
        )
    local_error: str | None = None
    normalized: dict[str, dict[str, Any]] | None = None
    try:
        if not isinstance(local_packets, Mapping) or set(local_packets) != set(
            _PACKET_WRITE_ROLES
        ):
            raise ExactQualificationContractError(
                "local packet manifest must contain exactly four roles"
            )
        normalized = {
            role: _normalize_packet_identity(
                label,
                role,
                local_packets[role],
                require_writer_identity=True,
                require_artifacts=True,
            )
            for role in _PACKET_WRITE_ROLES
        }
        for role, packet in normalized.items():
            if packet["rank"] != int(comm.rank) or packet["mpi_size"] != int(
                comm.size
            ):
                raise ExactQualificationContractError(
                    f"local packet {role} rank/mpi_size does not match communicator"
                )
            _validate_written_packet_artifacts(label, role, packet)
            if (
                expected_provenance is not None
                and packet["source_provenance"] != expected_provenance
            ):
                raise ExactQualificationContractError(
                    f"local packet {role} source provenance differs from aggregate"
                )
    except Exception as exc:
        local_error = f"rank {comm.rank}: {type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    first_error = next((error for error in errors if error is not None), None)
    if first_error is not None:
        raise ExactQualificationContractError(
            f"distributed packet artifact validation failed: {first_error}"
        )
    assert normalized is not None
    descriptor_hashes_by_rank = comm.gather(
        descriptor_metadata_hashes,
        root=0,
    )
    gathered = comm.gather(normalized, root=0)
    root_error: str | None = None
    result: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            if len(gathered) != int(comm.size):
                raise ExactQualificationContractError(
                    "rank manifest does not contain every communicator rank"
                )
            if descriptor_metadata_hashes is not None:
                if not isinstance(descriptor_hashes_by_rank, list) or len(
                    descriptor_hashes_by_rank
                ) != int(comm.size):
                    raise ExactQualificationContractError(
                        "descriptor metadata hash gather is incomplete"
                    )
                expected_descriptor_labels = (
                    "external_dtn_coupling",
                    "fixed_random_repeat_0",
                    "modal_traction_positive",
                    "modal_traction_negative",
                    "fixed_random_repeat_1",
                )
                for rank_hashes in descriptor_hashes_by_rank:
                    if not isinstance(rank_hashes, Mapping) or tuple(
                        str(label) for label in rank_hashes
                    ) != expected_descriptor_labels:
                        raise ExactQualificationContractError(
                            "descriptor metadata hash gather has an incomplete "
                            "five-label contract"
                        )
                    if any(
                        not isinstance(digest, str)
                        or len(digest) != 64
                        or any(character not in "0123456789abcdef" for character in digest)
                        for digest in rank_hashes.values()
                    ):
                        raise ExactQualificationContractError(
                            "descriptor metadata hash gather contains an invalid digest"
                        )
            elif any(item is not None for item in descriptor_hashes_by_rank):
                raise ExactQualificationContractError(
                    "descriptor metadata hash gather has an unexpected value"
                )
            rank_manifests: list[dict[str, Any]] = []
            seen_paths: set[str] = set()
            for expected_rank, rank_packets in enumerate(gathered):
                if not isinstance(rank_packets, Mapping) or set(rank_packets) != set(
                    _PACKET_WRITE_ROLES
                ):
                    raise ExactQualificationContractError(
                        "rank manifest has an incomplete four-role set"
                    )
                roles: dict[str, Any] = {}
                for role in _PACKET_WRITE_ROLES:
                    packet = rank_packets[role]
                    if packet["rank"] != expected_rank:
                        raise ExactQualificationContractError(
                            "rank manifest packet rank is not in communicator order"
                        )
                    for path_field in ("path", "array_path", "manifest_path"):
                        path = str(packet[path_field])
                        if path in seen_paths:
                            raise ExactQualificationContractError(
                                "rank manifest contains duplicate artifact paths"
                            )
                        seen_paths.add(path)
                    roles[role] = packet
                rank_manifests.append({"rank": expected_rank, "roles": roles})

            for role in _PACKET_WRITE_ROLES:
                role_packets = [item["roles"][role] for item in rank_manifests]
                if len(
                    {
                        json.dumps(packet["source_provenance"], sort_keys=True)
                        for packet in role_packets
                    }
                ) != 1:
                    raise ExactQualificationContractError(
                        f"{role} source provenance differs across ranks"
                    )
                for field in ("source_definition_sha256", "bare_f_operator_hash"):
                    if len({packet[field] for packet in role_packets}) != 1:
                        raise ExactQualificationContractError(
                            f"{role} {field} differs across ranks"
                        )
                if len(
                    {packet["canonical_key_set_sha256"] for packet in role_packets}
                ) != 1:
                    raise ExactQualificationContractError(
                        f"{role} canonical key-set identity differs across ranks"
                    )
                if (
                    expected_provenance is not None
                    and role_packets[0]["source_provenance"]
                    != expected_provenance
                ):
                    raise ExactQualificationContractError(
                        f"{role} source provenance differs from aggregate"
                    )
                if role == "gamma_l_canonical" and expected_gamma_global_sizes:
                    expected_size = expected_gamma_global_sizes.get(role)
                    if expected_size is not None and any(
                        int(packet["canonical_global_size"]) != int(expected_size)
                        for packet in role_packets
                    ):
                        raise ExactQualificationContractError(
                            "lower Gamma global size differs from layout authority"
                        )
                if role == "gamma_u_canonical" and expected_gamma_global_sizes:
                    expected_size = expected_gamma_global_sizes.get(role)
                    if expected_size is not None and any(
                        int(packet["canonical_global_size"]) != int(expected_size)
                        for packet in role_packets
                    ):
                        raise ExactQualificationContractError(
                            "upper Gamma global size differs from layout authority"
                        )
                if role == "exact_output_owner_rows":
                    global_sizes = {int(packet["global_size"]) for packet in role_packets}
                    if len(global_sizes) != 1:
                        raise ExactQualificationContractError(
                            "owner-row packet global sizes differ across ranks"
                        )
                    ranges = sorted(
                        (
                            int(packet["ownership_range"][0]),
                            int(packet["ownership_range"][1]),
                            int(packet["rank"]),
                        )
                        for packet in role_packets
                    )
                    cursor = 0
                    for start, end, _rank in ranges:
                        if start != cursor:
                            raise ExactQualificationContractError(
                                "owner-row ranges are not continuous"
                            )
                        cursor = end
                    if cursor != next(iter(global_sizes)):
                        raise ExactQualificationContractError(
                            "owner-row ranges do not cover the active vector"
                        )
                else:
                    global_counts = {
                        int(packet.get("global_active_size", packet.get("canonical_global_size")))
                        for packet in role_packets
                    }
                    local_count_total = sum(
                        int(packet["canonical_key_count_local"])
                        for packet in role_packets
                    )
                    if len(global_counts) != 1 or local_count_total != next(
                        iter(global_counts)
                    ):
                        raise ExactQualificationContractError(
                            f"{role} canonical counts do not cover its global identity"
                        )
            exact_packets = [
                item["roles"]["exact_output_canonical"]
                for item in rank_manifests
            ]
            owner_packets = [
                item["roles"]["exact_output_owner_rows"]
                for item in rank_manifests
            ]
            for field in (
                "canonical_key_set_sha256",
                "canonical_layout_sha256",
            ):
                if any(
                    exact[field] != owner[field]
                    for exact, owner in zip(
                        exact_packets, owner_packets, strict=True
                    )
                ):
                    raise ExactQualificationContractError(
                        "exact canonical and owner-row identities differ for "
                        f"{field}"
                    )
            if any(
                int(exact["global_active_size"]) != int(owner["global_size"])
                for exact, owner in zip(exact_packets, owner_packets, strict=True)
            ):
                raise ExactQualificationContractError(
                    "exact canonical and owner-row global sizes differ"
                )
            for expected_rank, rank_manifest in enumerate(rank_manifests):
                base = rank_manifest["roles"][_PACKET_WRITE_ROLES[0]]
                for role in _PACKET_WRITE_ROLES[1:]:
                    packet = rank_manifest["roles"][role]
                    for field in (
                        "source_definition_sha256",
                        "bare_f_operator_hash",
                        "source_provenance",
                    ):
                        if packet[field] != base[field]:
                            raise ExactQualificationContractError(
                                "packet roles on one rank do not share "
                                f"{field} (rank {expected_rank})"
                            )
            descriptor_binding_sha256 = hashlib.sha256(
                json.dumps(
                    descriptor_hashes_by_rank,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            rank_manifest_payload = {
                "schema": "task040.v6.current_exact_packet_rank_manifest.v1",
                "label": str(label),
                "mpi_size": int(comm.size),
                "source_provenance": rank_manifests[0]["roles"][
                    _PACKET_WRITE_ROLES[0]
                ]["source_provenance"],
                "qualification_source_provenance": qualification_provenance,
                "frozen_rhs_descriptor_metadata_sha256_by_rank": (
                    descriptor_hashes_by_rank
                ),
                "frozen_rhs_descriptor_metadata_binding_sha256": descriptor_binding_sha256,
                "rank_manifests": rank_manifests,
                "numeric_allgather": False,
                "full_numeric_replica": False,
            }
            manifest_path = output_root / f"{label}.rank-manifest.json"
            manifest_sha256 = _write_json_atomic(
                manifest_path, rank_manifest_payload
            )
            try:
                persisted_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExactQualificationContractError(
                    "aggregate rank manifest cannot be reread"
                ) from exc
            if (
                not isinstance(persisted_manifest, Mapping)
                or persisted_manifest.get("label") != str(label)
                or persisted_manifest.get("mpi_size") != int(comm.size)
                or hash_file_sha256(manifest_path) != manifest_sha256
                or persisted_manifest.get(
                    "frozen_rhs_descriptor_metadata_sha256_by_rank"
                )
                != descriptor_hashes_by_rank
                or persisted_manifest.get(
                    "frozen_rhs_descriptor_metadata_binding_sha256"
                )
                != descriptor_binding_sha256
                or [
                    item.get("rank")
                    for item in persisted_manifest.get("rank_manifests", [])
                ] != list(range(int(comm.size)))
                or any(
                    set(item.get("roles", {})) != set(_PACKET_WRITE_ROLES)
                    for item in persisted_manifest.get("rank_manifests", [])
                )
            ):
                raise ExactQualificationContractError(
                    "aggregate rank manifest reread validation failed"
                )
            result = {
                "path": str(manifest_path),
                "sha256": manifest_sha256,
                "mpi_size": int(comm.size),
                "rank_count": len(rank_manifests),
                "role_count_per_rank": 4,
                "qualification_source_provenance": qualification_provenance,
                "frozen_rhs_descriptor_metadata_sha256_by_rank": (
                    descriptor_hashes_by_rank
                ),
                "frozen_rhs_descriptor_metadata_binding_sha256": descriptor_binding_sha256,
                "numeric_allgather": False,
            }
        except Exception as exc:
            root_error = f"rank manifest aggregation failed: {type(exc).__name__}: {exc}"
    root_error = comm.bcast(root_error, root=0)
    if root_error is not None:
        raise ExactQualificationContractError(root_error)
    result = comm.bcast(result, root=0)
    assert result is not None
    return result


class _IdentityRightPreconditioner:
    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)


def _copy_vector(source: PETSc.Vec) -> PETSc.Vec:
    target = source.duplicate()
    source.copy(target)
    return target


def _distributed_vector_sha256(vector: PETSc.Vec) -> str:
    """Hash distributed Vec values without gathering numeric entries."""

    comm = vector.getComm().tompi4py()
    local_hash = hash_array_bytes_sha256(np.asarray(vector.array))
    gathered = comm.gather(local_hash, root=0)
    result = (
        hashlib.sha256("\n".join(gathered).encode("ascii")).hexdigest()
        if comm.rank == 0
        else None
    )
    return str(comm.bcast(result, root=0))


def _compact_recovery_audit(value: Any) -> Any:
    """Remove FE-sized arrays from a recovery record while retaining hashes."""

    if isinstance(value, np.ndarray):
        return {
            "count": int(value.size),
            "dtype": str(value.dtype),
            "sha256": hash_array_bytes_sha256(value),
        }
    if isinstance(value, Mapping):
        return {str(key): _compact_recovery_audit(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_compact_recovery_audit(item) for item in value]
    if isinstance(value, np.generic):
        return _compact_recovery_audit(value.item())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"recovery audit is not JSON-safe: {type(value)!r}")


def _finite_nonnegative(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)) and float(value) >= 0.0)
    except (TypeError, ValueError):
        return False


def _least_squares(hessenberg: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    values, _singular_values, _rank, _ = np.linalg.lstsq(
        np.asarray(hessenberg, dtype=np.complex128),
        np.asarray(rhs, dtype=np.complex128),
        rcond=None,
    )
    return np.asarray(values, dtype=np.complex128)


def _next_iteration_boundary(
    total_iterations: int,
    checkpoints: Sequence[int],
    conditional: Sequence[int],
    max_iterations: int,
) -> int:
    """Return the next recorded or authorized iteration boundary."""

    candidates = [
        int(value)
        for value in (int(checkpoints[-1]), *conditional, int(max_iterations))
        if int(value) > int(total_iterations)
    ]
    return min(candidates, default=int(max_iterations))


def _collective_conditional_decision(
    comm: MPI.Intracomm,
    *,
    stage: str,
    gate_input: Mapping[str, Any],
    authorize_conditional: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], bool]:
    """Collectively evaluate one conditional-extension decision.

    Resource and authorization callbacks are rank-local observations, so they
    must finish before the collective error exchange.  A callback exception or
    invalid return is therefore reported as one typed contract failure on all
    ranks.  A valid but divergent ``authorized`` result is checked in a second
    collective before any caller branches into another PETSc cycle.
    """

    def local_decision() -> dict[str, Any]:
        resource_snapshot: dict[str, Any] = {}
        if resource_callback is not None:
            observed_resource = resource_callback()
            if not isinstance(observed_resource, Mapping):
                raise TypeError("resource callback must return a mapping")
            resource_snapshot = dict(observed_resource)
        local_gate_input = dict(gate_input)
        local_gate_input["resource_snapshot"] = resource_snapshot
        gate_result: dict[str, Any] = {}
        if authorize_conditional is not None:
            observed_gate = authorize_conditional(local_gate_input)
            if not isinstance(observed_gate, Mapping):
                raise TypeError("conditional authorization must return a mapping")
            gate_result = dict(observed_gate)
        return {
            "gate_result": gate_result,
            "resource_snapshot": resource_snapshot,
        }

    local_result = _collective_contract_call(comm, stage, local_decision)
    if not isinstance(local_result, Mapping):
        raise ExactQualificationContractError(
            f"collective conditional decision returned no result at {stage}"
        )
    gate_result = local_result.get("gate_result")
    resource_snapshot = local_result.get("resource_snapshot")
    if not isinstance(gate_result, Mapping) or not isinstance(
        resource_snapshot, Mapping
    ):
        raise ExactQualificationContractError(
            f"collective conditional decision has invalid result at {stage}"
        )
    gate_result = dict(gate_result)
    resource_snapshot = dict(resource_snapshot)
    local_authorized = bool(gate_result.get("authorized", False))
    authorized_by_rank = tuple(bool(value) for value in comm.allgather(local_authorized))
    if len(set(authorized_by_rank)) != 1:
        raise ExactQualificationContractError(
            "conditional authorization decision differs across ranks at "
            f"{stage}: {list(authorized_by_rank)!r}"
        )
    gate_result["resource_snapshot"] = resource_snapshot
    gate_result["authorized_by_rank"] = list(authorized_by_rank)
    gate_result["authorization_consensus"] = True
    return gate_result, authorized_by_rank[0]


def run_exact_interface_fgmres(
    *,
    interface_operator: PETSc.Mat,
    schur_action: Any,
    bare_operator: PETSc.Mat,
    condensed_rhs: PETSc.Vec,
    active_rhs: PETSc.Vec,
    interior_rhs_by_group: Mapping[int, PETSc.Vec] | Sequence[PETSc.Vec],
    right_preconditioner: Any | None,
    label: str,
    restart: int = 32,
    mandatory_checkpoints: Sequence[int] = (16, 32, 64, 128),
    conditional_checkpoints: Sequence[int] = (256, 512),
    authorize_conditional: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    max_iterations: int | None = None,
    checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
    accepted_solution_callback: Callable[[Mapping[str, Any], PETSc.Vec], None]
    | None = None,
    full_residual_tolerance: float = 1.0e-9,
) -> dict[str, Any]:
    """Run a bounded restarted right-FGMRES exact qualification solve.

    ``schur_action`` must expose the public
    ``build_full_state_from_condensed_solution`` method.  Each checkpoint
    computes an independent explicit ``bare_operator * full_state`` residual;
    the original active RHS is never modified.  Only small Hessenberg data
    are handled by NumPy, while all vectors remain owner-local PETSc objects.
    """

    if not isinstance(interface_operator, PETSc.Mat) or not isinstance(
        bare_operator, PETSc.Mat
    ):
        raise TypeError("exact qualification requires PETSc interface and bare operators")
    if not isinstance(condensed_rhs, PETSc.Vec) or not isinstance(active_rhs, PETSc.Vec):
        raise TypeError("exact qualification RHS values must be PETSc Vec objects")
    if not callable(getattr(schur_action, "build_full_state_from_condensed_solution", None)):
        raise TypeError("schur_action lacks the public recovery API")
    op_rows, op_cols = map(int, interface_operator.getSize())
    bare_rows, bare_cols = map(int, bare_operator.getSize())
    if op_rows != op_cols or bare_rows != bare_cols:
        raise ValueError("exact qualification operators must be square")
    if condensed_rhs.getSize() != op_rows or active_rhs.getSize() != bare_rows:
        raise ValueError("exact qualification RHS/operator sizes do not match")
    if int(restart) <= 0:
        raise ValueError("FGMRES restart must be positive")
    checkpoints = tuple(sorted({int(value) for value in mandatory_checkpoints}))
    conditional = tuple(sorted({int(value) for value in conditional_checkpoints}))
    if not checkpoints or any(value <= 0 for value in checkpoints):
        raise ValueError("mandatory checkpoints must be positive")
    if any(value <= checkpoints[-1] for value in conditional):
        raise ValueError("conditional checkpoints must follow mandatory checkpoints")
    if max_iterations is None:
        max_iterations = conditional[-1] if conditional else checkpoints[-1]
    if int(max_iterations) < checkpoints[-1]:
        raise ValueError("max_iterations cannot end before the mandatory checkpoints")
    identity_preconditioner = right_preconditioner is None
    preconditioner = (
        _IdentityRightPreconditioner()
        if identity_preconditioner
        else right_preconditioner
    )
    if not callable(getattr(preconditioner, "apply", None)):
        raise TypeError("right preconditioner must expose apply")
    try:
        full_residual_tolerance = float(full_residual_tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("full residual tolerance must be numeric") from exc
    if not np.isfinite(full_residual_tolerance) or full_residual_tolerance <= 0.0:
        raise ValueError("full residual tolerance must be positive")

    full_rhs_norm = float(active_rhs.norm())
    interface_rhs_norm = float(condensed_rhs.norm())
    if not _finite_nonnegative(full_rhs_norm) or full_rhs_norm <= 0.0:
        raise ValueError("active exact-qualification RHS must be finite and nonzero")
    if not _finite_nonnegative(interface_rhs_norm) or interface_rhs_norm <= 0.0:
        raise ValueError("condensed exact-qualification RHS must be finite and nonzero")

    solution = interface_operator.createVecRight()
    solution.set(0.0)
    solution.assemble()
    checkpoints_out: dict[str, dict[str, Any]] = {}
    gate_observations: dict[str, Any] = {}
    total_iterations = 0
    authorized = {value: False for value in conditional}
    completed = {value: False for value in conditional}
    stopped_at_happy_breakdown = False
    final_record: dict[str, Any] | None = None
    early_final_record: dict[str, Any] | None = None
    accepted_solution: PETSc.Vec | None = None
    accepted_solution_iteration: int | None = None
    completed_normally = False
    active_rhs_initial_sha256 = _distributed_vector_sha256(active_rhs)
    condensed_rhs_initial_sha256 = _distributed_vector_sha256(condensed_rhs)
    checkpoint_history: list[dict[str, Any]] = []
    residual = interface_operator.createVecLeft()
    interface_residual = interface_operator.createVecLeft()
    full_residual = bare_operator.createVecLeft()

    def explicit_checkpoint(
        iteration: int,
        candidate: PETSc.Vec,
        *,
        checkpoint_kind: str,
    ) -> dict[str, Any]:
        nonlocal accepted_solution, accepted_solution_iteration
        interface_operator.mult(candidate, interface_residual)
        interface_residual.scale(PETSc.ScalarType(-1.0))
        interface_residual.axpy(PETSc.ScalarType(1.0), condensed_rhs)
        interface_norm = float(interface_residual.norm())
        full_state: PETSc.Vec | None = None
        try:
            full_state, recovery_audit = schur_action.build_full_state_from_condensed_solution(
                candidate,
                interior_rhs_by_group,
            )
            bare_operator.mult(full_state, full_residual)
            full_residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
            full_norm = float(full_residual.norm())
        finally:
            if full_state is not None:
                full_state.destroy()
        full_relative = full_norm / max(full_rhs_norm, 1.0e-30)
        interface_relative = interface_norm / max(interface_rhs_norm, 1.0e-30)
        row = {
            "label": str(label),
            "iteration": int(iteration),
            "restart": int(restart),
            "checkpoint_kind": checkpoint_kind,
            "interface_true_residual_norm": interface_norm,
            "interface_true_residual_relative": interface_relative,
            "full_true_residual_norm": full_norm,
            "full_true_residual_relative": full_relative,
            "full_residual_tolerance": float(full_residual_tolerance),
            "rhs_norm_denominator": full_rhs_norm,
            "interface_rhs_norm_denominator": interface_rhs_norm,
            "recovery": _compact_recovery_audit(recovery_audit),
            "finite": bool(
                np.isfinite(interface_norm)
                and np.isfinite(full_norm)
                and np.isfinite(full_relative)
                and np.isfinite(interface_relative)
                and full_relative >= 0.0
                and interface_relative >= 0.0
            ),
        }
        if full_relative <= full_residual_tolerance:
            new_accepted_solution = _copy_vector(candidate)
            try:
                if accepted_solution_callback is not None:
                    accepted_solution_callback(row, new_accepted_solution)
            except Exception:
                new_accepted_solution.destroy()
                raise
            if accepted_solution is not None:
                accepted_solution.destroy()
            accepted_solution = new_accepted_solution
            accepted_solution_iteration = int(iteration)
            row["accepted_full_solution"] = True
        else:
            row["accepted_full_solution"] = False
        if checkpoint_callback is not None:
            checkpoint_callback(row)
        return row

    try:
        while total_iterations < int(max_iterations):
            interface_operator.mult(solution, residual)
            residual.scale(PETSc.ScalarType(-1.0))
            residual.axpy(PETSc.ScalarType(1.0), condensed_rhs)
            beta = float(residual.norm())
            if not np.isfinite(beta):
                raise ValueError("FGMRES initial residual is nonfinite")
            if beta <= 1.0e-30:
                stopped_at_happy_breakdown = True
                break
            cycle_base = _copy_vector(solution)
            basis: list[PETSc.Vec] = []
            responses: list[PETSc.Vec] = []
            cycle_happy = False
            try:
                first = _copy_vector(residual)
                first.scale(PETSc.ScalarType(1.0 / beta))
                basis.append(first)
                hessenberg = np.zeros(
                    (int(restart) + 1, int(restart)), dtype=np.complex128
                )
                next_boundary = _next_iteration_boundary(
                    total_iterations,
                    checkpoints,
                    conditional,
                    int(max_iterations),
                )
                cycle_limit = min(
                    int(restart),
                    next_boundary - total_iterations,
                    int(max_iterations) - total_iterations,
                )
                if cycle_limit <= 0:
                    raise RuntimeError(
                        "FGMRES failed to advance to its next boundary"
                    )
                for column in range(cycle_limit):
                    response = interface_operator.createVecRight()
                    responses.append(response)
                    work: PETSc.Vec | None = None
                    candidate: PETSc.Vec | None = None
                    normalized: PETSc.Vec | None = None
                    try:
                        preconditioner.apply(basis[column], response)
                        work = interface_operator.createVecLeft()
                        interface_operator.mult(response, work)
                        for _pass in range(2):
                            for row_index in range(column + 1):
                                coefficient = basis[row_index].dot(work)
                                hessenberg[row_index, column] += coefficient
                                work.axpy(-coefficient, basis[row_index])
                        next_norm = float(work.norm())
                        hessenberg[column + 1, column] = next_norm
                        hbar = hessenberg[: column + 2, : column + 1]
                        rhs_small = np.zeros(column + 2, dtype=np.complex128)
                        rhs_small[0] = beta
                        coefficients = _least_squares(hbar, rhs_small)
                        candidate = _copy_vector(cycle_base)
                        for coefficient, response_vector in zip(
                            coefficients,
                            responses,
                            strict=True,
                        ):
                            candidate.axpy(
                                PETSc.ScalarType(coefficient), response_vector
                            )
                        candidate.copy(solution)
                        total_iterations += 1
                        if (
                            total_iterations in checkpoints
                            or total_iterations in conditional
                        ):
                            checkpoint_kind = (
                                "mandatory"
                                if total_iterations in checkpoints
                                else "conditional"
                            )
                            record = explicit_checkpoint(
                                total_iterations,
                                candidate,
                                checkpoint_kind=checkpoint_kind,
                            )
                            checkpoints_out[str(total_iterations)] = record
                            if total_iterations in conditional:
                                completed[total_iterations] = True
                            final_record = record
                            checkpoint_history.append(dict(record))
                        if (
                            next_norm <= 1.0e-30
                            and str(total_iterations) not in checkpoints_out
                        ):
                            early_final_record = explicit_checkpoint(
                                total_iterations,
                                candidate,
                                checkpoint_kind="early_final",
                            )
                            final_record = early_final_record
                            checkpoint_history.append(dict(early_final_record))
                        if next_norm <= 1.0e-30:
                            cycle_happy = True
                            break
                        normalized = interface_operator.createVecRight()
                        basis.append(normalized)
                        work.copy(normalized)
                        normalized.scale(PETSc.ScalarType(1.0 / next_norm))
                        normalized = None
                    finally:
                        if normalized is not None:
                            basis.pop()
                            normalized.destroy()
                        if candidate is not None:
                            candidate.destroy()
                        if work is not None:
                            work.destroy()
            finally:
                for vector in responses:
                    vector.destroy()
                for vector in basis:
                    vector.destroy()
                cycle_base.destroy()
            if cycle_happy:
                stopped_at_happy_breakdown = True
            if total_iterations == checkpoints[-1] and conditional:
                gate_input = dict(final_record or {})
                gate_input.update(
                    {
                        "label": str(label),
                        "checkpoint": int(total_iterations),
                        "formal_rhs_elapsed_iterations": int(total_iterations),
                        "checkpoint_history": [
                            dict(item) for item in checkpoint_history
                        ],
                    }
                )
                next_checkpoint = conditional[0]
                gate_result, next_authorized = _collective_conditional_decision(
                    interface_operator.getComm().tompi4py(),
                    stage=(
                        f"conditional_authorization_{total_iterations}_to_"
                        f"{next_checkpoint}"
                    ),
                    gate_input=gate_input,
                    authorize_conditional=authorize_conditional,
                    resource_callback=resource_callback,
                )
                gate_observations[str(total_iterations)] = gate_result
                authorized[next_checkpoint] = next_authorized
                if not authorized[next_checkpoint]:
                    break
            elif total_iterations in conditional:
                next_index = conditional.index(total_iterations) + 1
                if next_index < len(conditional):
                    gate_input = dict(final_record or {})
                    gate_input.update(
                        {
                            "label": str(label),
                            "checkpoint": int(total_iterations),
                            "checkpoint_history": [
                                dict(item) for item in checkpoint_history
                            ],
                        }
                    )
                    next_checkpoint = conditional[next_index]
                    gate_result, next_authorized = _collective_conditional_decision(
                        interface_operator.getComm().tompi4py(),
                        stage=(
                            f"conditional_authorization_{total_iterations}_to_"
                            f"{next_checkpoint}"
                        ),
                        gate_input=gate_input,
                        authorize_conditional=authorize_conditional,
                        resource_callback=resource_callback,
                    )
                    gate_observations[str(total_iterations)] = gate_result
                    authorized[next_checkpoint] = next_authorized
                    if not authorized[next_checkpoint]:
                        break
            if stopped_at_happy_breakdown:
                break
        completed_normally = True
    finally:
        full_residual.destroy()
        interface_residual.destroy()
        residual.destroy()
        solution.destroy()
        if not completed_normally and accepted_solution is not None:
            accepted_solution.destroy()
            accepted_solution = None

    for checkpoint in conditional:
        completed[checkpoint] = str(checkpoint) in checkpoints_out
    final_iteration = max(
        (int(value["iteration"]) for value in checkpoints_out.values()),
        default=total_iterations,
    )
    if final_record is None and total_iterations:
        final_record = {
            "iteration": int(total_iterations),
            "finite": True,
            "status": "no_requested_checkpoint_reached",
        }
    active_rhs_final_sha256 = _distributed_vector_sha256(active_rhs)
    condensed_rhs_final_sha256 = _distributed_vector_sha256(condensed_rhs)
    active_rhs_unchanged = active_rhs_final_sha256 == active_rhs_initial_sha256
    condensed_rhs_unchanged = (
        condensed_rhs_final_sha256 == condensed_rhs_initial_sha256
    )
    completed_normally = True
    return {
        "schema": "task040.v6.exact_interface_fgmres.v1",
        "label": str(label),
        "restart": int(restart),
        "mandatory_checkpoints": list(checkpoints),
        "conditional_checkpoints": list(conditional),
        "checkpoints": checkpoints_out,
        "final_iteration": int(final_iteration),
        "final_record": final_record,
        "early_final_record": early_final_record,
        "checkpoint_history": [dict(item) for item in checkpoint_history],
        "stopped_at_happy_breakdown": bool(stopped_at_happy_breakdown),
        "conditional_authorized": {
            str(key): bool(value) for key, value in authorized.items()
        },
        "conditional_completed": {
            str(key): bool(value) for key, value in completed.items()
        },
        "conditional_gate_observations": gate_observations,
        "conditional_256_authorized": bool(authorized.get(256, False)),
        "conditional_256_completed": bool(completed.get(256, False)),
        "conditional_512_authorized": bool(authorized.get(512, False)),
        "conditional_512_completed": bool(completed.get(512, False)),
        "full_residual_tolerance": float(full_residual_tolerance),
        "accepted_solution": accepted_solution,
        "accepted_solution_iteration": accepted_solution_iteration,
        "accepted_solution_ownership": (
            "caller_must_destroy" if accepted_solution is not None else None
        ),
        "full_rhs_norm": full_rhs_norm,
        "interface_rhs_norm": interface_rhs_norm,
        "active_rhs_initial_sha256": active_rhs_initial_sha256,
        "active_rhs_final_sha256": active_rhs_final_sha256,
        "active_rhs_unchanged": active_rhs_unchanged,
        "condensed_rhs_initial_sha256": condensed_rhs_initial_sha256,
        "condensed_rhs_final_sha256": condensed_rhs_final_sha256,
        "condensed_rhs_unchanged": condensed_rhs_unchanged,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "identity_preconditioner": identity_preconditioner,
    }
