"""Metadata-only C0 carrier for the Task037 H2B congruence route.

This research-only module turns constrained-cell incidence and verified class
metadata into immutable row tokens.  It can then prove a permutation plus
unit-modulus diagonal phase between two token sets and apply that local
monomial transform to vectors.  No patch matrix, factor, global matrix, or
solver object is accepted or retained here; ordinary solver imports do not
use this module.  The CSR orientation has already been applied exactly once
by the verified R2 authority; C0 does not apply or reinterpret orientation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

import numpy as np

__all__ = (
    "CANONICAL_CONGRUENCE_SCHEMA",
    "CanonicalRowToken",
    "MonomialTransform",
    "MonomialTransformNotProven",
    "build_canonical_row_tokens",
    "build_monomial_transform",
    "canonical_tokens_sha256",
    "canonical_tokens_provenance_sha256",
)


CANONICAL_CONGRUENCE_SCHEMA = "task037.extra.h2b.canonical-congruence.c0.v1"
UNITARY_TOLERANCE = 1.0e-14
PHASE_CONSISTENCY_TOLERANCE = 1.0e-14
_SHA_HEX = frozenset("0123456789abcdef")


class MonomialTransformNotProven(ValueError):
    """The supplied metadata does not prove a permitted monomial transform."""


def _require_opt_in(task037_extra_h2b: bool) -> None:
    if task037_extra_h2b is not True:
        raise ValueError("canonical congruence requires task037_extra_h2b=True")


def _freeze(value: Any) -> Any:
    """Return a small, hashable, finite representation of JSON-like metadata."""

    if isinstance(value, np.generic):
        return _freeze(value.item())
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            raise ValueError("canonical metadata cannot contain object arrays")
        return (
            "ndarray",
            str(value.dtype),
            tuple(int(size) for size in value.shape),
            tuple(_freeze(item) for item in value.tolist()),
        )
    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(
                (str(key), _freeze(item))
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            ),
        )
    if isinstance(value, (tuple, list)):
        return ("sequence", tuple(_freeze(item) for item in value))
    if isinstance(value, complex):
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise ValueError("canonical metadata complex values must be finite")
        return ("complex", float(value.real), float(value.imag))
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("canonical metadata floats must be finite")
        return float(value)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    raise TypeError(f"unsupported canonical metadata value {type(value)!r}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(contiguous).cast("B")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and set(value) <= _SHA_HEX
    )


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{label} must be an integer")
    return int(value)


def _pair(value: complex) -> tuple[float, float]:
    value = complex(value)
    if not np.isfinite(value.real) or not np.isfinite(value.imag):
        raise ValueError("canonical CSR coefficients must be finite")
    real = 0.0 if value.real == 0.0 else float(value.real)
    imag = 0.0 if value.imag == 0.0 else float(value.imag)
    return real, imag


def _complex(pair: tuple[float, float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def _validate_identity(cell: Mapping[str, Any]) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    keys = (
        "class_key_sha256",
        "constraint_pattern_sha256",
        "expansion_pattern_sha256",
        "numeric_matrix_sha256",
        "orientation_identity",
        "material_identity",
        "operator_identity",
        "cell_metric_identity",
    )
    if any(key not in cell for key in keys):
        raise ValueError("canonical cell metadata is missing an identity field")
    for key in keys[:4]:
        if not _valid_sha(cell[key]):
            raise ValueError(f"{key} must be a lowercase SHA-256")
    raw_identity = tuple((key, _freeze(cell[key])) for key in keys)
    if "orientation_monomial_map" in cell:
        raise MonomialTransformNotProven(
            "orientation_monomial_map is not supported by C0"
        )
    orientation_match = (
        "orientation_identity",
        _freeze(cell["orientation_identity"]),
    )
    match_identity = (
        ("numeric_matrix_sha256", str(cell["numeric_matrix_sha256"])),
        ("material_identity", _freeze(cell["material_identity"])),
        ("operator_identity", _freeze(cell["operator_identity"])),
        ("cell_metric_identity", _freeze(cell["cell_metric_identity"])),
        ("orientation", orientation_match),
    )
    return raw_identity, match_identity


def _contributions_for_cell(
    cell: Mapping[str, Any],
    slot_by_label: Mapping[int, int],
) -> dict[
    int,
    list[
        tuple[
            tuple[Any, ...],
            tuple[float, float],
            tuple[tuple[int, tuple[float, float]], ...],
            tuple[Any, ...],
        ]
    ],
]:
    raw_identity, match_identity = _validate_identity(cell)
    offsets = np.asarray(cell.get("csr_offsets"), dtype=np.int64)
    columns = np.asarray(cell.get("csr_columns"), dtype=np.int64)
    coefficients = np.asarray(cell.get("coefficients"), dtype=np.complex128)
    if "independent_global_rows" in cell:
        independent_rows = np.asarray(
            cell["independent_global_rows"], dtype=np.int64
        )
        if independent_rows.ndim != 1 or np.unique(independent_rows).size != independent_rows.size:
            raise ValueError("canonical independent_global_rows are invalid")
        column_slots = tuple(
            slot_by_label.get(int(row), -1) for row in independent_rows.tolist()
        )
    elif "column_patch_slots" in cell:
        column_slots = tuple(
            _strict_int(value, "column_patch_slots entry")
            for value in cell["column_patch_slots"]
        )
        if any(value < -1 or value >= len(slot_by_label) for value in column_slots):
            raise ValueError("column_patch_slots contains an invalid slot")
        mapped_slots = tuple(value for value in column_slots if value != -1)
        if len(set(mapped_slots)) != len(mapped_slots):
            raise ValueError("column_patch_slots maps multiple columns to one slot")
    else:
        raise ValueError(
            "canonical cell metadata lacks independent_global_rows or column_patch_slots"
        )
    if offsets.ndim != 1 or offsets.size < 2:
        raise ValueError("canonical CSR offsets are invalid")
    if columns.ndim != 1 or coefficients.ndim != 1 or columns.size != coefficients.size:
        raise ValueError("canonical CSR arrays do not close")
    if int(offsets[0]) != 0 or int(offsets[-1]) != columns.size:
        raise ValueError("canonical CSR offsets do not close")
    if np.any(np.diff(offsets) < 0) or np.any(columns < 0) or np.any(columns >= len(column_slots)):
        raise ValueError("canonical CSR indices are invalid")
    if not np.all(np.isfinite(coefficients)):
        raise ValueError("canonical CSR coefficients must be finite")

    entries_by_column: list[list[tuple[int, int, complex]]] = [
        [] for _ in column_slots
    ]
    for local_row in range(offsets.size - 1):
        start, stop = int(offsets[local_row]), int(offsets[local_row + 1])
        for position in range(start, stop):
            column = int(columns[position])
            entries_by_column[column].append(
                (local_row, position, complex(coefficients[position]))
            )

    contributions: dict[
        int,
        list[
            tuple[
                tuple[Any, ...],
                tuple[float, float],
                tuple[tuple[int, tuple[float, float]], ...],
                tuple[Any, ...],
            ]
        ],
    ] = {}
    for column, slot in enumerate(column_slots):
        if slot == -1:
            continue
        entries = entries_by_column[column]
        active = [entry for entry in entries if entry[2] != 0.0 + 0.0j]
        if not active:
            raise ValueError("a patch-touching expansion column has no nonzero contribution")
        active.sort(key=lambda entry: (entry[0], entry[1]))
        anchor = active[0][2]
        normalized = tuple(
            (
                int(local_row),
                _pair(value / anchor),
            )
            for local_row, _position, value in active
        )
        touching_local_columns = tuple(
            sorted(
                int(local_column)
                for local_column, local_slot in enumerate(column_slots)
                if local_slot != -1
            )
        )
        structural = (
            ("identity", match_identity),
            ("touching_local_columns", touching_local_columns),
            ("local_column", int(column)),
            ("csr_support", tuple(int(local_row) for local_row, _ in normalized)),
        )
        contributions.setdefault(slot, []).append(
            (structural, _pair(anchor), normalized, ("raw_identity", raw_identity))
        )
    return contributions


@dataclass(frozen=True)
class CanonicalRowToken:
    """Hashable metadata token for one central patch slot."""

    central_slot: int
    structural_key: tuple[Any, ...]
    phase_anchors: tuple[tuple[float, float], ...]
    phase_profiles: tuple[tuple[tuple[int, tuple[float, float]], ...], ...]
    token_sha256: str
    provenance_sha256: str

    def __post_init__(self) -> None:
        slot = _strict_int(self.central_slot, "central_slot")
        if slot < 0 or not isinstance(self.structural_key, tuple):
            raise ValueError("canonical row token is invalid")
        anchors = tuple(
            (float(pair[0]), float(pair[1])) for pair in self.phase_anchors
        )
        if not anchors or any(not np.all(np.isfinite(pair)) for pair in anchors):
            raise ValueError("canonical row token phase anchors are invalid")
        profiles = tuple(
            tuple(
                (
                    _strict_int(local_row, "phase profile row"),
                    (float(pair[0]), float(pair[1])),
                )
                for local_row, pair in profile
            )
            for profile in self.phase_profiles
        )
        if len(profiles) != len(anchors) or any(
            not profile
            or tuple(local_row for local_row, _ in profile)
            != tuple(sorted(local_row for local_row, _ in profile))
            or len({local_row for local_row, _ in profile}) != len(profile)
            or any(not np.all(np.isfinite(pair)) for _local_row, pair in profile)
            for profile in profiles
        ):
            raise ValueError("canonical row token phase profiles are invalid")
        expected = _sha256((CANONICAL_CONGRUENCE_SCHEMA, self.structural_key))
        if self.token_sha256 != expected:
            raise ValueError("canonical row token SHA mismatch")
        if not _valid_sha(self.provenance_sha256):
            raise ValueError("canonical row token provenance SHA is invalid")
        object.__setattr__(self, "central_slot", slot)
        object.__setattr__(self, "structural_key", self.structural_key)
        object.__setattr__(self, "phase_anchors", anchors)
        object.__setattr__(self, "phase_profiles", profiles)
        object.__setattr__(self, "provenance_sha256", self.provenance_sha256)


def build_canonical_row_tokens(
    central_patch_slots: Sequence[Any],
    touching_cells: Sequence[Mapping[str, Any]],
    *,
    task037_extra_h2b: bool = False,
) -> tuple[CanonicalRowToken, ...]:
    """Build deterministic row tokens using only local metadata and CSR data.

    Each touching-cell mapping must contain the eight identity fields accepted
    by ``_validate_identity``, ``independent_global_rows`` (or equivalent
    ``column_patch_slots``), ``csr_offsets``, ``csr_columns`` and
    ``coefficients``.  Global rows are used only to map each expansion column
    to a central slot.  The token contains the reverse-collected column
    signatures, not the global labels or local-row coordinate as a patch row.
    Cell order and absolute row labels are deliberately not included in the
    token; contributions are sorted by their structural metadata.
    """

    _require_opt_in(task037_extra_h2b)
    labels = tuple(_strict_int(value, "central_patch_slots entry") for value in central_patch_slots)
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("central_patch_slots must be unique and nonempty")
    if not isinstance(touching_cells, Sequence) or not touching_cells:
        raise ValueError("touching_cells must be a nonempty sequence")
    slot_by_label = {label: slot for slot, label in enumerate(labels)}
    by_slot: dict[
        int,
        list[
            tuple[
                tuple[Any, ...],
                tuple[float, float],
                tuple[tuple[int, tuple[float, float]], ...],
                tuple[Any, ...],
            ]
        ],
    ] = {}
    for cell in touching_cells:
        if not isinstance(cell, Mapping):
            raise ValueError("touching cell metadata must be a mapping")
        for slot, items in _contributions_for_cell(cell, slot_by_label).items():
            by_slot.setdefault(slot, []).extend(items)

    tokens: list[CanonicalRowToken] = []
    for slot in range(len(labels)):
        items = by_slot.get(slot, [])
        if not items:
            raise ValueError("central patch slot has no metadata contribution")
        items = sorted(items, key=lambda item: _json_bytes(item[0]))
        if len({item[0] for item in items}) != len(items):
            raise MonomialTransformNotProven(
                "row correspondence is not unique for repeated structural contribution"
            )
        structural_key = (
            ("schema", CANONICAL_CONGRUENCE_SCHEMA),
            ("contributions", tuple(item[0] for item in items)),
        )
        provenance_key = (
            ("schema", CANONICAL_CONGRUENCE_SCHEMA),
            (
                "provenance",
                tuple((item[3], item[1], item[2]) for item in items),
            ),
        )
        tokens.append(
            CanonicalRowToken(
                central_slot=slot,
                structural_key=structural_key,
                phase_anchors=tuple(item[1] for item in items),
                phase_profiles=tuple(item[2] for item in items),
                token_sha256=_sha256((CANONICAL_CONGRUENCE_SCHEMA, structural_key)),
                provenance_sha256=_sha256(provenance_key),
            )
        )
    return tuple(tokens)


def canonical_tokens_sha256(tokens: Sequence[CanonicalRowToken]) -> str:
    """Hash a token set without depending on cell enumeration or row order."""

    values = tuple(
        sorted(
            (token.token_sha256 for token in tokens),
        )
    )
    return _sha256((CANONICAL_CONGRUENCE_SCHEMA, values))


def canonical_tokens_provenance_sha256(
    tokens: Sequence[CanonicalRowToken],
) -> str:
    """Hash raw source identities without entering the matching key."""

    values = tuple(
        sorted((token.token_sha256, token.provenance_sha256) for token in tokens)
    )
    return _sha256((CANONICAL_CONGRUENCE_SCHEMA, "provenance", values))


def _validate_token_set(tokens: Sequence[CanonicalRowToken]) -> tuple[CanonicalRowToken, ...]:
    values = tuple(tokens)
    if not values or not all(isinstance(token, CanonicalRowToken) for token in values):
        raise MonomialTransformNotProven("row tokens are missing or invalid")
    slots = tuple(token.central_slot for token in values)
    if set(slots) != set(range(len(values))):
        raise MonomialTransformNotProven("row token central slots are not bijective")
    return values


@dataclass(frozen=True)
class MonomialTransform:
    """A read-only member-to-reference permutation and diagonal phase."""

    permutation: np.ndarray
    phases: np.ndarray
    reference_metadata_sha256: str
    member_metadata_sha256: str
    reference_provenance_sha256: str
    member_provenance_sha256: str
    transform_sha256: str

    def __post_init__(self) -> None:
        permutation = np.asarray(self.permutation)
        phases = np.asarray(self.phases)
        if permutation.dtype != np.dtype(np.int32) or phases.dtype != np.dtype(np.complex128):
            raise MonomialTransformNotProven("T arrays have the wrong dtype")
        if not _valid_sha(self.reference_metadata_sha256) or not _valid_sha(
            self.member_metadata_sha256
        ):
            raise MonomialTransformNotProven("T metadata SHA is invalid")
        if not _valid_sha(self.reference_provenance_sha256) or not _valid_sha(
            self.member_provenance_sha256
        ):
            raise MonomialTransformNotProven("T provenance SHA is invalid")
        if permutation.ndim != 1 or phases.ndim != 1 or permutation.size != phases.size:
            raise MonomialTransformNotProven("T arrays do not have a common vector shape")
        if set(int(value) for value in permutation.tolist()) != set(range(permutation.size)):
            raise MonomialTransformNotProven("T permutation is not bijective")
        if not np.all(np.isfinite(phases)):
            raise MonomialTransformNotProven("T phases are nonfinite")
        unitary_error = float(np.max(np.abs(np.abs(phases) ** 2 - 1.0)))
        if unitary_error > UNITARY_TOLERANCE:
            raise MonomialTransformNotProven("T phase is not unitary")
        permutation = np.array(permutation, dtype=np.int32, copy=True, order="C")
        phases = np.array(phases, dtype=np.complex128, copy=True, order="C")
        permutation.setflags(write=False)
        phases.setflags(write=False)
        expected = _transform_sha(
            self.reference_metadata_sha256,
            self.member_metadata_sha256,
            self.reference_provenance_sha256,
            self.member_provenance_sha256,
            permutation,
            phases,
        )
        if self.transform_sha256 != expected:
            raise MonomialTransformNotProven("T SHA mismatch")
        object.__setattr__(self, "permutation", permutation)
        object.__setattr__(self, "phases", phases)

    @property
    def phase_unit_error(self) -> float:
        return float(np.max(np.abs(np.abs(self.phases) - 1.0)))

    @property
    def unitary_error(self) -> float:
        return float(np.max(np.abs(np.abs(self.phases) ** 2 - 1.0)))

    def _vector(self, vector: np.ndarray) -> np.ndarray:
        if (
            not isinstance(vector, np.ndarray)
            or vector.dtype != np.dtype(np.complex128)
            or vector.ndim != 1
            or vector.size != self.permutation.size
            or not vector.flags.c_contiguous
        ):
            raise ValueError("T application requires a C-contiguous complex128 vector")
        return vector

    def apply_t(self, vector: np.ndarray) -> np.ndarray:
        """Apply T: member coordinates to reference coordinates."""

        vector = self._vector(vector)
        result = np.empty_like(vector)
        result[self.permutation] = self.phases * vector
        return result

    def apply_t_h(self, vector: np.ndarray) -> np.ndarray:
        """Apply T^H: reference coordinates to member coordinates."""

        vector = self._vector(vector)
        return np.asarray(np.conj(self.phases) * vector[self.permutation], dtype=np.complex128)

    def audit(self) -> dict[str, Any]:
        """Return JSON-safe, independently checkable C0 transform metadata."""

        return {
            "schema": CANONICAL_CONGRUENCE_SCHEMA,
            "row_count": int(self.permutation.size),
            "reference_metadata_sha256": self.reference_metadata_sha256,
            "member_metadata_sha256": self.member_metadata_sha256,
            "reference_provenance_sha256": self.reference_provenance_sha256,
            "member_provenance_sha256": self.member_provenance_sha256,
            "permutation_sha256": _array_sha256(self.permutation),
            "phases_sha256": _array_sha256(self.phases),
            "transform_sha256": self.transform_sha256,
            "phase_unit_error": self.phase_unit_error,
            "unitary_error": self.unitary_error,
            "finite": bool(np.all(np.isfinite(self.phases))),
            "bijection": True,
            "matrix_materialized": False,
        }


def _transform_sha(
    reference_sha: str,
    member_sha: str,
    reference_provenance_sha: str,
    member_provenance_sha: str,
    permutation: np.ndarray,
    phases: np.ndarray,
) -> str:
    return _sha256(
        (
            CANONICAL_CONGRUENCE_SCHEMA,
            reference_sha,
            member_sha,
            reference_provenance_sha,
            member_provenance_sha,
            tuple(int(value) for value in permutation.tolist()),
            tuple(_pair(value) for value in phases.tolist()),
        )
    )


def build_monomial_transform(
    reference_tokens: Sequence[CanonicalRowToken],
    member_tokens: Sequence[CanonicalRowToken],
    *,
    task037_extra_h2b: bool = False,
) -> MonomialTransform:
    """Prove and return T from member metadata coordinates to reference ones."""

    _require_opt_in(task037_extra_h2b)
    reference = _validate_token_set(reference_tokens)
    member = _validate_token_set(member_tokens)
    if len(reference) != len(member):
        raise MonomialTransformNotProven("token sets have different row counts")
    reference_by_key: dict[tuple[Any, ...], CanonicalRowToken] = {}
    for token in reference:
        if token.structural_key in reference_by_key:
            raise MonomialTransformNotProven("reference tokens are not unique")
        reference_by_key[token.structural_key] = token
    member_keys = {token.structural_key for token in member}
    if len(member_keys) != len(member) or member_keys != set(reference_by_key):
        raise MonomialTransformNotProven("metadata does not prove a row bijection")

    permutation = np.empty(len(member), dtype=np.int32)
    phases = np.empty(len(member), dtype=np.complex128)
    for member_token in member:
        reference_token = reference_by_key[member_token.structural_key]
        if len(reference_token.phase_anchors) != len(member_token.phase_anchors):
            raise MonomialTransformNotProven("row contribution counts differ")
        if len(reference_token.phase_profiles) != len(member_token.phase_profiles):
            raise MonomialTransformNotProven("row profile counts differ")
        for reference_profile, member_profile in zip(
            reference_token.phase_profiles,
            member_token.phase_profiles,
            strict=True,
        ):
            if len(reference_profile) != len(member_profile):
                raise MonomialTransformNotProven("normalized profile support differs")
            for reference_entry, member_entry in zip(
                reference_profile,
                member_profile,
                strict=True,
            ):
                reference_row, reference_pair = reference_entry
                member_row, member_pair = member_entry
                if reference_row != member_row:
                    raise MonomialTransformNotProven(
                        "normalized profile support differs"
                    )
                reference_value = _complex(reference_pair)
                member_value = _complex(member_pair)
                if abs(member_value - reference_value) > (
                    PHASE_CONSISTENCY_TOLERANCE
                    * max(abs(member_value), abs(reference_value))
                ):
                    raise MonomialTransformNotProven(
                        "normalized coefficient profile conflict"
                    )
        ratios: list[complex] = []
        for reference_pair, member_pair in zip(
            reference_token.phase_anchors,
            member_token.phase_anchors,
            strict=True,
        ):
            reference_anchor = _complex(reference_pair)
            if reference_anchor == 0.0 + 0.0j:
                raise MonomialTransformNotProven("row phase anchor is zero")
            ratio = _complex(member_pair) / reference_anchor
            if not np.isfinite(ratio.real) or not np.isfinite(ratio.imag):
                raise MonomialTransformNotProven("row phase ratio is nonfinite")
            ratios.append(ratio)
        if not ratios or any(
            abs(ratio - ratios[0])
            > PHASE_CONSISTENCY_TOLERANCE
            * max(1.0, abs(ratio), abs(ratios[0]))
            for ratio in ratios[1:]
        ):
            raise MonomialTransformNotProven("row contribution phases conflict")
        permutation[member_token.central_slot] = reference_token.central_slot
        phases[member_token.central_slot] = ratios[0]

    reference_sha = canonical_tokens_sha256(reference)
    member_sha = canonical_tokens_sha256(member)
    reference_provenance_sha = canonical_tokens_provenance_sha256(reference)
    member_provenance_sha = canonical_tokens_provenance_sha256(member)
    transform_sha = _transform_sha(
        reference_sha,
        member_sha,
        reference_provenance_sha,
        member_provenance_sha,
        permutation,
        phases,
    )
    return MonomialTransform(
        permutation=permutation,
        phases=phases,
        reference_metadata_sha256=reference_sha,
        member_metadata_sha256=member_sha,
        reference_provenance_sha256=reference_provenance_sha,
        member_provenance_sha256=member_provenance_sha,
        transform_sha256=transform_sha,
    )
