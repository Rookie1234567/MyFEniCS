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
    "load_owner_local_vector",
    "load_owner_local_vector_collective",
    "LoadedExactQualificationRHS",
    "load_and_condense_exact_rhs",
    "run_exact_qualification_family",
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
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _is_hex_commit(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


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
        if not np.isfinite(relative) or relative > tolerance:
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
        if not np.isfinite(roundtrip) or roundtrip > float(
            canonical_roundtrip_tolerance
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
            "active_rhs_vec_retained": not self._destroyed,
            "gamma_rhs_vec_retained": not self._destroyed,
            "condensed_rhs_vec_retained": not self._destroyed,
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
            [str, Mapping[str, Any], PETSc.Vec, LoadedExactQualificationRHS], None
        ]
        | None
    ) = None,
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

    def run_source(label: str) -> dict[str, Any]:
        bundle: LoadedExactQualificationRHS | None = None
        accepted: PETSc.Vec | None = None
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
            if accepted is not None and accepted_solution_consumer is not None:
                accepted_solution_consumer(
                    label,
                    accepted_row,
                    accepted,
                    bundle,
                )
                accepted_solution_consumed = True
            full_residuals = [
                float(row["full_true_residual_relative"])
                for row in checkpoint_rows
                if _finite_nonnegative(row.get("full_true_residual_relative"))
            ]
            best_full_residual = min(full_residuals, default=float("inf"))
            return {
                "label": label,
                "adapter": bundle.compact_audit(),
                "fgmres": {
                    **_json_safe_binding(fgmres),
                    "accepted_solution_present": accepted is not None,
                    "accepted_solution_released_by_driver": accepted is not None,
                    "accepted_solution_consumed": accepted_solution_consumed,
                },
                "best_full_true_residual_relative": best_full_residual,
                "full_residual_gate_pass": bool(
                    np.isfinite(best_full_residual)
                    and best_full_residual <= float(full_residual_tolerance)
                ),
            }
        finally:
            if accepted is not None:
                accepted.destroy()
            if bundle is not None:
                bundle.destroy()

    for label in ordered_labels[:2]:
        source_records.append(run_source(label))
    initial_pair_pass = all(
        bool(record["full_residual_gate_pass"]) for record in source_records
    )
    skipped_labels: list[str] = []
    if initial_pair_pass:
        for label in ordered_labels[2:]:
            source_records.append(run_source(label))
    else:
        skipped_labels.extend(ordered_labels[2:])
    all_sources_gate_pass = bool(
        initial_pair_pass
        and len(source_records) == len(ordered_labels)
        and all(bool(record["full_residual_gate_pass"]) for record in source_records)
    )
    return {
        "schema": "task040.v6.exact_qualification_family.v1",
        "status": (
            "completed_initial_pair_and_remaining_sources"
            if all_sources_gate_pass
            else (
                "stopped_before_remaining_sources"
                if skipped_labels
                else "completed_all_sources_gate_negative"
            )
        ),
        "classification": (
            "V6_EXACT_QUALIFICATION_READY"
            if all_sources_gate_pass
            else "V6_EXACT_QUALIFICATION_GATE_FAIL"
        ),
        "initial_labels": list(guarded),
        "ordered_labels": list(ordered_labels),
        "source_records": source_records,
        "skipped_labels": skipped_labels,
        "initial_pair_gate_pass": initial_pair_pass,
        "all_sources_gate_pass": all_sources_gate_pass,
        "full_residual_tolerance": float(full_residual_tolerance),
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }


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
        if full_relative <= 1.0e-9:
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
                resource_snapshot = (
                    {}
                    if resource_callback is None
                    else dict(resource_callback())
                )
                gate_input.update(
                    {
                        "label": str(label),
                        "checkpoint": int(total_iterations),
                        "formal_rhs_elapsed_iterations": int(total_iterations),
                        "checkpoint_history": [
                            dict(item) for item in checkpoint_history
                        ],
                        "resource_snapshot": resource_snapshot,
                    }
                )
                gate_result = (
                    {}
                    if authorize_conditional is None
                    else dict(authorize_conditional(gate_input))
                )
                gate_observations[str(total_iterations)] = gate_result
                next_checkpoint = conditional[0]
                authorized[next_checkpoint] = bool(gate_result.get("authorized", False))
                if not authorized[next_checkpoint]:
                    break
            elif total_iterations in conditional:
                next_index = conditional.index(total_iterations) + 1
                if next_index < len(conditional):
                    gate_input = dict(final_record or {})
                    resource_snapshot = (
                        {}
                        if resource_callback is None
                        else dict(resource_callback())
                    )
                    gate_input.update(
                        {
                            "label": str(label),
                            "checkpoint": int(total_iterations),
                            "checkpoint_history": [
                                dict(item) for item in checkpoint_history
                            ],
                            "resource_snapshot": resource_snapshot,
                        }
                    )
                    gate_result = (
                        {}
                        if authorize_conditional is None
                        else dict(authorize_conditional(gate_input))
                    )
                    gate_observations[str(total_iterations)] = gate_result
                    next_checkpoint = conditional[next_index]
                    authorized[next_checkpoint] = bool(
                        gate_result.get("authorized", False)
                    )
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
