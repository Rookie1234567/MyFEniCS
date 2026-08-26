"""Pure canonical packet and coefficient-comparison kernel.

The packet key is physical rather than PETSc ownership-order based. Mesh and
constraint-specific extraction deliberately lives outside this kernel. Active
trace expansion, real Basix/DOLFINx orientation extraction, full-FE recovery,
and trace-mass/H(curl) norms remain not qualified in this slice.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
import hashlib
import json
import math
from typing import Any

import numpy as np


CanonicalKey = tuple[Any, ...]
CanonicalPacket = tuple[CanonicalKey, complex]
CANONICAL_SOURCE_SCHEMA = "task038.v13.c0.physical-canonical-source.v1"

_ROLES = frozenset({"active_trace", "full_fe", "full_fe_dual"})


def canonical_key(
    *,
    role: str,
    entity_dimension: int,
    physical_entity: Iterable[Iterable[int]],
    entity_local_basis_index: int,
    orientation_state: Hashable,
    floquet_master: Hashable | None = None,
    floquet_coefficient: complex = 1.0 + 0.0j,
) -> CanonicalKey:
    """Build the physical identity used to order one canonical coefficient."""

    if role not in _ROLES:
        raise ValueError(f"unsupported canonical vector role: {role!r}")
    dimension = int(entity_dimension)
    if dimension not in {1, 2, 3}:
        raise ValueError("canonical hexahedron entities have dimensions 1, 2, 3")
    entity = tuple(
        sorted(
            tuple(int(component) for component in point) for point in physical_entity
        )
    )
    coefficient = complex(floquet_coefficient)
    if not np.isfinite(coefficient.real) or not np.isfinite(coefficient.imag):
        raise ValueError("Floquet coefficient must be finite")
    return (
        role,
        dimension,
        entity,
        int(entity_local_basis_index),
        orientation_state,
        floquet_master,
        (float(coefficient.real), float(coefficient.imag)),
    )


def canonicalize_coefficients(
    values: Iterable[complex],
    orientation_to_canonical: np.ndarray | None = None,
) -> np.ndarray:
    """Apply an explicit Basix-to-canonical coefficient transform."""

    coefficients = np.asarray(tuple(values), dtype=np.complex128)
    if orientation_to_canonical is None:
        return coefficients.copy()
    transform = np.asarray(orientation_to_canonical, dtype=np.complex128)
    if transform.shape != (coefficients.size, coefficients.size):
        raise ValueError("orientation transform must be square over the packet block")
    return np.ascontiguousarray(transform @ coefficients)


def canonical_packet(key: CanonicalKey, value: complex) -> CanonicalPacket:
    """Return one finite key/value packet after coefficient normalization."""

    coefficient = complex(value)
    if not np.isfinite(coefficient.real) or not np.isfinite(coefficient.imag):
        raise ValueError("canonical coefficient must be finite")
    return key, coefficient


def _source_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_source_jsonable(item) for item in value]}
    if isinstance(value, list):
        return [_source_jsonable(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical source identity contains a non-finite float")
        return {"float_hex": value.hex()}
    raise TypeError(
        "unsupported canonical source identity value: "
        f"{type(value).__name__}"
    )


def canonical_source_payload(
    *,
    role: str,
    physical_entity: Iterable[Iterable[int]],
    entity_dimension: int,
    entity_local_basis_index: int,
    orientation_state: Hashable,
    floquet_master: Hashable | None,
    floquet_phase_state: Hashable,
    fixed_seed: str,
) -> dict[str, Any]:
    """Return the exact physical identity used by the C0 source hash.

    The payload intentionally has no PETSc, rank, local-row, ownership, or
    iteration-order input.  Geometry points are sorted only as an identity
    normalization; coefficient ordering remains the caller's canonical key.
    """

    if role not in {"full_fe", "full_fe_dual"}:
        raise ValueError(f"unsupported physical source role: {role!r}")
    dimension = int(entity_dimension)
    if dimension not in {1, 2, 3}:
        raise ValueError("physical source entity dimension must be 1, 2, or 3")
    entity = tuple(
        sorted(
            tuple(int(component) for component in point)
            for point in physical_entity
        )
    )
    if not entity or any(len(point) != 3 for point in entity):
        raise ValueError("physical source geometry key must contain 3D points")
    if not isinstance(fixed_seed, str) or not fixed_seed:
        raise ValueError("physical source fixed seed must be a non-empty string")
    return {
        "schema": CANONICAL_SOURCE_SCHEMA,
        "role": role,
        "physical_entity_geometry_key": _source_jsonable(entity),
        "entity_dimension": dimension,
        "entity_local_basis_index": int(entity_local_basis_index),
        "canonical_orientation_state": _source_jsonable(orientation_state),
        "floquet_master_phase_state": {
            "master": _source_jsonable(floquet_master),
            "phase": _source_jsonable(floquet_phase_state),
        },
        "fixed_seed": fixed_seed,
    }


def canonical_source_coefficient(
    *,
    role: str,
    physical_entity: Iterable[Iterable[int]],
    entity_dimension: int,
    entity_local_basis_index: int,
    orientation_state: Hashable,
    floquet_master: Hashable | None,
    floquet_phase_state: Hashable,
    fixed_seed: str,
) -> tuple[np.complex128, str, dict[str, Any]]:
    """Derive one nonzero complex128 source coefficient from a physical key."""

    payload = canonical_source_payload(
        role=role,
        physical_entity=physical_entity,
        entity_dimension=entity_dimension,
        entity_local_basis_index=entity_local_basis_index,
        orientation_state=orientation_state,
        floquet_master=floquet_master,
        floquet_phase_state=floquet_phase_state,
        fixed_seed=fixed_seed,
    )
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    digest_bytes = bytes.fromhex(digest)
    real = 0.5 + int.from_bytes(digest_bytes[:8], "big") / float(1 << 64)
    imag = -0.5 + int.from_bytes(digest_bytes[8:16], "big") / float(1 << 64)
    coefficient = np.complex128(real + 1j * imag)
    return coefficient, digest, payload


def canonical_source_coefficient_from_key(
    key: CanonicalKey, *, fixed_seed: str
) -> tuple[np.complex128, str, dict[str, Any]]:
    """Derive a C0 coefficient from one existing canonical packet key."""

    if len(key) != 7:
        raise ValueError("canonical source key must have seven fields")
    role, dimension, entity, basis, orientation, master, phase = key
    return canonical_source_coefficient(
        role=str(role),
        physical_entity=entity,
        entity_dimension=int(dimension),
        entity_local_basis_index=int(basis),
        orientation_state=orientation,
        floquet_master=master,
        floquet_phase_state=phase,
        fixed_seed=fixed_seed,
    )


def compare_canonical_packets(
    left: Iterable[CanonicalPacket],
    right: Iterable[CanonicalPacket],
    *,
    relative_tolerance: float = 1.0e-5,
) -> dict[str, Any]:
    """Compare sorted physical packets and report missing/duplicate identities."""

    left_rows = tuple(canonical_packet(key, value) for key, value in left)
    right_rows = tuple(canonical_packet(key, value) for key, value in right)
    left_keys = tuple(key for key, _value in left_rows)
    right_keys = tuple(key for key, _value in right_rows)
    left_unique = set(left_keys)
    right_unique = set(right_keys)
    duplicate_left = len(left_keys) - len(left_unique)
    duplicate_right = len(right_keys) - len(right_unique)
    missing = right_unique - left_unique
    extra = left_unique - right_unique
    left_by_key = {key: value for key, value in left_rows}
    right_by_key = {key: value for key, value in right_rows}
    common = tuple(sorted(left_unique & right_unique, key=repr))
    left_values = np.asarray([left_by_key[key] for key in common], dtype=np.complex128)
    right_values = np.asarray(
        [right_by_key[key] for key in common], dtype=np.complex128
    )
    difference = left_values - right_values
    relative_l2 = float(
        np.linalg.norm(difference)
        / max(np.linalg.norm(right_values), np.finfo(float).tiny)
    )
    max_abs = float(np.max(np.abs(difference), initial=0.0))
    passed = (
        not duplicate_left
        and not duplicate_right
        and not missing
        and not extra
        and relative_l2 <= float(relative_tolerance)
    )
    return {
        "pass": bool(passed),
        "left_shape": [len(left_rows)],
        "right_shape": [len(right_rows)],
        "dtype": "complex128",
        "duplicate_left_count": int(duplicate_left),
        "duplicate_right_count": int(duplicate_right),
        "missing_key_count": int(len(missing)),
        "extra_key_count": int(len(extra)),
        "common_key_count": int(len(common)),
        "relative_coefficient_l2": relative_l2,
        "max_abs_coefficient_error": max_abs,
        "relative_tolerance": float(relative_tolerance),
        "trace_mass_norm": "not_qualified",
        "hcurl_norm": "not_qualified",
    }


__all__ = (
    "CANONICAL_SOURCE_SCHEMA",
    "CanonicalKey",
    "CanonicalPacket",
    "canonical_key",
    "canonical_packet",
    "canonicalize_coefficients",
    "canonical_source_coefficient",
    "canonical_source_coefficient_from_key",
    "canonical_source_payload",
    "compare_canonical_packets",
)
