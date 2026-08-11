"""Bounded C1 canonical-congruence metadata and patch audit.

This module is deliberately research-only.  It consumes the approved C0
metadata carrier and one streamed patch at a time; it never factorizes, keeps
all dense neighborhood matrices, or constructs a global operator.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .hcurl_h2b_canonical_congruence import (
    CanonicalRowToken,
    MonomialTransform,
    MonomialTransformNotProven as C0MonomialTransformNotProven,
    build_monomial_transform,
    canonical_tokens_provenance_sha256,
    canonical_tokens_sha256,
)

__all__ = (
    "C1_CLOSURE_LIMIT",
    "C1_METADATA_LIMIT_BYTES",
    "C1_ORBIT_METADATA_ARRAY_NAMES",
    "C1CandidateAudit",
    "C1_PROBE_SEED",
    "C1_SCHEMA",
    "C1CandidateOrbitLimit",
    "C1MonomialTransformNotProven",
    "C1MetadataNotProven",
    "C1OrbitAudit",
    "C1PatchAudit",
    "audit_c1_patch",
    "build_c1_orbit_audit",
    "build_c1_candidate_audit",
    "c1_retained_metadata_bytes",
    "fixed_c1_probes",
    "load_c1_candidate_manifest",
    "load_c1_orbit_manifest",
    "write_c1_candidate_manifest",
    "write_c1_orbit_manifest",
)

C1_SCHEMA = "task037.extra.h2b.canonical-orbit.v1"
C1_CLOSURE_LIMIT = 1.0e-11
C1_METADATA_LIMIT_BYTES = 16_777_216
C1_PROBE_SEED = 2_026_0812
C1_ORBIT_METADATA_ARRAY_NAMES = (
    "neighborhood_ids",
    "orbit_ids",
    "representative_ids",
    "metadata_sha256",
    "provenance_sha256",
    "row_token_sha256",
    "row_provenance_sha256",
    "permutations",
    "phases",
    "transform_sha256",
    "repeat_transform_sha256",
)
_HEX = set("0123456789abcdef")


class C1MetadataNotProven(ValueError):
    """Metadata cannot prove a deterministic canonical orbit transform."""


class C1MonomialTransformNotProven(C1MetadataNotProven):
    """A bounded candidate exists, but its monomial transform is unproven."""


class C1CandidateOrbitLimit(ValueError):
    """Metadata-only candidate representative count exceeds the fixed limit."""

    def __init__(
        self,
        *,
        representative_count: int,
        limit: int = 32,
        candidate: "C1CandidateAudit | None" = None,
    ) -> None:
        self.representative_count = int(representative_count)
        self.limit = int(limit)
        self.candidate = candidate
        super().__init__("C1 candidate representative limit exceeded")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(contiguous).cast("B")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and set(value) <= _HEX
    )


def _ascii_hash(value: str) -> np.ndarray:
    if not _valid_sha(value):
        raise ValueError("C1 hash is invalid")
    return np.frombuffer(value.encode("ascii"), dtype=np.uint8).copy()


def c1_retained_metadata_bytes(
    manifest: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> int:
    """Count orbit metadata, excluding probes and patch evidence arrays."""

    if not isinstance(manifest, Mapping):
        raise ValueError("C1 manifest metadata is not a mapping")
    if not all(isinstance(array, np.ndarray) for array in arrays.values()):
        raise ValueError("C1 retained arrays are invalid")
    allowed = set(C1_ORBIT_METADATA_ARRAY_NAMES) | {"probes"}
    if any(name not in allowed and not name.startswith("patch_") for name in arrays):
        raise ValueError("C1 retained array inventory has an unknown name")
    orbit_arrays = tuple(
        arrays[name] for name in C1_ORBIT_METADATA_ARRAY_NAMES if name in arrays
    )
    if not orbit_arrays:
        raise ValueError("C1 orbit metadata arrays are missing")
    probe = dict(manifest)
    probe["evidence_sha256"] = "0" * 64
    value = 0
    for _ in range(4):
        probe["retained_metadata_bytes"] = value
        value = sum(int(array.nbytes) for array in orbit_arrays) + len(_json_bytes(probe))
    return int(value)


def _readonly_copy(value: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.array(value, dtype=dtype, copy=True, order="C")
    array.setflags(write=False)
    return array


def fixed_c1_probes(nloc: int) -> np.ndarray:
    """Return the two fixed complex Rademacher probes required by V10."""

    if type(nloc) is not int or nloc <= 0:
        raise ValueError("C1 probe length is invalid")
    rng = np.random.default_rng(C1_PROBE_SEED)
    signs = rng.integers(0, 2, size=(2, 2, nloc), dtype=np.int8) * 2 - 1
    probes = (
        signs[:, 0, :].astype(np.float64)
        + 1j * signs[:, 1, :].astype(np.float64)
    ) / np.sqrt(2.0)
    return _readonly_copy(probes, np.dtype(np.complex128))


def _token_hash_rows(tokens: Sequence[CanonicalRowToken]) -> np.ndarray:
    return np.asarray(
        [_ascii_hash(token.token_sha256) for token in tokens],
        dtype=np.uint8,
    )


def _provenance_hash_rows(tokens: Sequence[CanonicalRowToken]) -> np.ndarray:
    return np.asarray(
        [_ascii_hash(token.provenance_sha256) for token in tokens],
        dtype=np.uint8,
    )


def _validate_token_load(
    neighborhood_id: int,
    tokens: Sequence[CanonicalRowToken],
    nloc: int | None,
) -> tuple[tuple[CanonicalRowToken, ...], int]:
    values = tuple(tokens)
    if not values or not all(isinstance(item, CanonicalRowToken) for item in values):
        raise C1MetadataNotProven(
            f"neighborhood {neighborhood_id} has invalid C0 tokens"
        )
    length = len(values)
    if nloc is not None and length != nloc:
        raise C1MetadataNotProven(f"neighborhood {neighborhood_id} row count mismatch")
    if tuple(token.central_slot for token in values) != tuple(range(length)):
        raise C1MetadataNotProven(f"neighborhood {neighborhood_id} token slots are not canonical")
    return values, length


@dataclass(frozen=True)
class C1CandidateAudit:
    """Metadata-only candidate partition, before any T/probe construction."""

    neighborhood_ids: np.ndarray
    orbit_ids: np.ndarray
    representative_ids: np.ndarray
    metadata_sha256: np.ndarray
    provenance_sha256: np.ndarray
    row_token_sha256: np.ndarray
    row_provenance_sha256: np.ndarray
    representative_members: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        arrays = (
            _readonly_copy(self.neighborhood_ids, np.dtype(np.int32)),
            _readonly_copy(self.orbit_ids, np.dtype(np.int32)),
            _readonly_copy(self.representative_ids, np.dtype(np.int32)),
            _readonly_copy(self.metadata_sha256, np.dtype(np.uint8)),
            _readonly_copy(self.provenance_sha256, np.dtype(np.uint8)),
            _readonly_copy(self.row_token_sha256, np.dtype(np.uint8)),
            _readonly_copy(self.row_provenance_sha256, np.dtype(np.uint8)),
        )
        count = int(arrays[0].size)
        if count == 0 or tuple(arrays[0].tolist()) != tuple(range(count)):
            raise ValueError("C1 candidate neighborhood ids are not canonical")
        if any(array.shape != (count,) for array in arrays[1:3]):
            raise ValueError("C1 candidate mapping shape is invalid")
        if arrays[3].shape != (count, 64) or arrays[4].shape != (count, 64):
            raise ValueError("C1 candidate identity shape is invalid")
        if arrays[5].ndim != 3 or arrays[5].shape[0] != count or arrays[5].shape[2] != 64:
            raise ValueError("C1 candidate token shape is invalid")
        if arrays[6].shape != arrays[5].shape:
            raise ValueError("C1 candidate provenance shape is invalid")
        if len(self.representative_members) != len(set(arrays[1].tolist())):
            raise ValueError("C1 candidate representatives are incomplete")
        for name, array in zip(
            (
                "neighborhood_ids", "orbit_ids", "representative_ids",
                "metadata_sha256", "provenance_sha256", "row_token_sha256",
                "row_provenance_sha256",
            ),
            arrays,
            strict=True,
        ):
            object.__setattr__(self, name, array)
        object.__setattr__(
            self,
            "representative_members",
            tuple(tuple(int(value) for value in item) for item in self.representative_members),
        )

    @property
    def neighborhood_count(self) -> int:
        return int(self.neighborhood_ids.size)

    @property
    def row_count(self) -> int:
        return int(self.row_token_sha256.shape[1])

    @property
    def representative_count(self) -> int:
        return len(self.representative_members)

    def _array_bytes(self) -> int:
        return sum(
            int(array.nbytes)
            for array in (
                self.neighborhood_ids,
                self.orbit_ids,
                self.representative_ids,
                self.metadata_sha256,
                self.provenance_sha256,
                self.row_token_sha256,
                self.row_provenance_sha256,
            )
        )

    @property
    def retained_metadata_bytes(self) -> int:
        return int(self.jsonable()["retained_metadata_bytes"])

    def jsonable(self) -> dict[str, Any]:
        payload = {
            "schema": C1_SCHEMA,
            "state": "candidate_only",
            "neighborhood_count": self.neighborhood_count,
            "row_count": self.row_count,
            "representative_count": self.representative_count,
            "representative_members": [list(item) for item in self.representative_members],
            "neighborhood_ids_sha256": _array_sha256(self.neighborhood_ids),
            "orbit_ids_sha256": _array_sha256(self.orbit_ids),
            "representative_ids_sha256": _array_sha256(self.representative_ids),
            "metadata_sha256_sha256": _array_sha256(self.metadata_sha256),
            "provenance_sha256_sha256": _array_sha256(self.provenance_sha256),
            "row_token_sha256_sha256": _array_sha256(self.row_token_sha256),
            "row_provenance_sha256_sha256": _array_sha256(self.row_provenance_sha256),
            "retained_metadata_bytes": 0,
            "factorization_called": False,
            "factor_store_written": False,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "per_cell_factor": False,
            "per_cell_dense_tensor": False,
            "slab_factor": False,
        }
        payload["retained_metadata_bytes"] = self._array_bytes() + len(_json_bytes(payload))
        return payload


@dataclass(frozen=True)
class C1OrbitAudit:
    """Compact, immutable orbit metadata and all 84 metadata-only transforms."""

    neighborhood_ids: np.ndarray
    orbit_ids: np.ndarray
    representative_ids: np.ndarray
    metadata_sha256: np.ndarray
    provenance_sha256: np.ndarray
    row_token_sha256: np.ndarray
    row_provenance_sha256: np.ndarray
    permutations: np.ndarray
    phases: np.ndarray
    transform_sha256: np.ndarray
    repeat_transform_sha256: np.ndarray
    representative_members: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        ids = _readonly_copy(self.neighborhood_ids, np.dtype(np.int32))
        orbit_ids = _readonly_copy(self.orbit_ids, np.dtype(np.int32))
        reps = _readonly_copy(self.representative_ids, np.dtype(np.int32))
        metadata = _readonly_copy(self.metadata_sha256, np.dtype(np.uint8))
        provenance = _readonly_copy(self.provenance_sha256, np.dtype(np.uint8))
        row_tokens = _readonly_copy(self.row_token_sha256, np.dtype(np.uint8))
        row_provenance = _readonly_copy(self.row_provenance_sha256, np.dtype(np.uint8))
        permutations = _readonly_copy(self.permutations, np.dtype(np.int32))
        phases = _readonly_copy(self.phases, np.dtype(np.complex128))
        transforms = _readonly_copy(self.transform_sha256, np.dtype(np.uint8))
        repeat_transforms = _readonly_copy(self.repeat_transform_sha256, np.dtype(np.uint8))
        count = int(ids.size)
        if count == 0 or ids.ndim != 1 or tuple(ids.tolist()) != tuple(range(count)):
            raise ValueError("C1 neighborhood ids are not canonical")
        if any(array.shape != (count,) for array in (orbit_ids, reps)):
            raise ValueError("C1 orbit mapping shape is invalid")
        if metadata.shape != (count, 64) or provenance.shape != (count, 64):
            raise ValueError("C1 metadata hash shape is invalid")
        if row_tokens.ndim != 3 or row_tokens.shape[0] != count or row_tokens.shape[2] != 64:
            raise ValueError("C1 row token hash shape is invalid")
        if row_provenance.shape != row_tokens.shape or transforms.shape != (count, 64) or repeat_transforms.shape != transforms.shape:
            raise ValueError("C1 transform hash shape is invalid")
        if permutations.shape != (count, row_tokens.shape[1]) or phases.shape != permutations.shape:
            raise ValueError("C1 transform array shape is invalid")
        if not np.all(np.isfinite(phases)):
            raise ValueError("C1 phases are nonfinite")
        if len(self.representative_members) != len(set(orbit_ids.tolist())):
            raise ValueError("C1 orbit records are incomplete")
        object.__setattr__(self, "neighborhood_ids", ids)
        object.__setattr__(self, "orbit_ids", orbit_ids)
        object.__setattr__(self, "representative_ids", reps)
        object.__setattr__(self, "metadata_sha256", metadata)
        object.__setattr__(self, "provenance_sha256", provenance)
        object.__setattr__(self, "row_token_sha256", row_tokens)
        object.__setattr__(self, "row_provenance_sha256", row_provenance)
        object.__setattr__(self, "permutations", permutations)
        object.__setattr__(self, "phases", phases)
        object.__setattr__(self, "transform_sha256", transforms)
        object.__setattr__(self, "repeat_transform_sha256", repeat_transforms)
        object.__setattr__(self, "representative_members", tuple(tuple(item) for item in self.representative_members))

    @property
    def neighborhood_count(self) -> int:
        return int(self.neighborhood_ids.size)

    @property
    def row_count(self) -> int:
        return int(self.permutations.shape[1])

    @property
    def representative_count(self) -> int:
        return len(self.representative_members)

    def _retained_array_bytes(self) -> int:
        return sum(
            int(array.nbytes)
            for array in (
                self.neighborhood_ids,
                self.orbit_ids,
                self.representative_ids,
                self.metadata_sha256,
                self.provenance_sha256,
                self.row_token_sha256,
                self.row_provenance_sha256,
                self.permutations,
                self.phases,
                self.transform_sha256,
                self.repeat_transform_sha256,
            )
        )

    @property
    def retained_metadata_bytes(self) -> int:
        return int(self.jsonable()["retained_metadata_bytes"])

    def jsonable(self) -> dict[str, Any]:
        payload = {
            "schema": C1_SCHEMA,
            "neighborhood_count": self.neighborhood_count,
            "row_count": self.row_count,
            "representative_count": self.representative_count,
            "representative_members": [list(item) for item in self.representative_members],
            "neighborhood_ids_sha256": _array_sha256(self.neighborhood_ids),
            "orbit_ids_sha256": _array_sha256(self.orbit_ids),
            "representative_ids_sha256": _array_sha256(self.representative_ids),
            "metadata_sha256_sha256": _array_sha256(self.metadata_sha256),
            "provenance_sha256_sha256": _array_sha256(self.provenance_sha256),
            "row_token_sha256_sha256": _array_sha256(self.row_token_sha256),
            "row_provenance_sha256_sha256": _array_sha256(self.row_provenance_sha256),
            "permutations_sha256": _array_sha256(self.permutations),
            "phases_sha256": _array_sha256(self.phases),
            "transform_sha256_sha256": _array_sha256(self.transform_sha256),
            "repeat_transform_sha256_sha256": _array_sha256(self.repeat_transform_sha256),
            "retained_metadata_bytes": 0,
            "factorization_called": False,
            "factor_store_written": False,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "per_cell_factor": False,
            "per_cell_dense_tensor": False,
            "slab_factor": False,
        }
        payload["retained_metadata_bytes"] = self._retained_array_bytes() + len(
            _json_bytes(payload)
        )
        return payload


def build_c1_candidate_audit(
    neighborhood_ids: Sequence[int],
    token_loader: Callable[[int], Sequence[CanonicalRowToken]],
    *,
    task037_extra_h2b: bool = False,
) -> C1CandidateAudit:
    """Build only the candidate partition; no transform or probe is built."""

    if not task037_extra_h2b:
        raise ValueError("C1 requires explicit task037_extra_h2b opt-in")
    ids = tuple(int(value) for value in neighborhood_ids)
    if not ids or ids != tuple(range(len(ids))) or len(set(ids)) != len(ids):
        raise ValueError("C1 neighborhood ids must be contiguous canonical integers")
    metadata_sha: list[str] = []
    provenance_sha: list[str] = []
    row_token_arrays: list[np.ndarray] = []
    row_provenance_arrays: list[np.ndarray] = []
    nloc: int | None = None
    grouped: dict[str, list[int]] = {}
    for neighborhood_id in ids:
        tokens, nloc = _validate_token_load(neighborhood_id, token_loader(neighborhood_id), nloc)
        metadata = canonical_tokens_sha256(tokens)
        provenance = canonical_tokens_provenance_sha256(tokens)
        metadata_sha.append(metadata)
        provenance_sha.append(provenance)
        row_token_arrays.append(_token_hash_rows(tokens))
        row_provenance_arrays.append(_provenance_hash_rows(tokens))
        grouped.setdefault(metadata, []).append(neighborhood_id)
    representatives = tuple(
        tuple(sorted(grouped[key])) for key in sorted(grouped)
    )
    orbit_ids = np.empty(len(ids), dtype=np.int32)
    representative_ids = np.empty(len(ids), dtype=np.int32)
    for orbit_id, members in enumerate(representatives):
        representative = members[0]
        for member in members:
            orbit_ids[member] = orbit_id
            representative_ids[member] = representative
    if nloc is None:
        raise ValueError("C1 row count is missing")
    candidate = C1CandidateAudit(
        neighborhood_ids=np.asarray(ids, dtype=np.int32),
        orbit_ids=orbit_ids,
        representative_ids=representative_ids,
        metadata_sha256=np.asarray([_ascii_hash(value) for value in metadata_sha], dtype=np.uint8),
        provenance_sha256=np.asarray([_ascii_hash(value) for value in provenance_sha], dtype=np.uint8),
        row_token_sha256=np.asarray(row_token_arrays, dtype=np.uint8),
        row_provenance_sha256=np.asarray(row_provenance_arrays, dtype=np.uint8),
        representative_members=representatives,
    )
    if candidate.retained_metadata_bytes > C1_METADATA_LIMIT_BYTES:
        raise C1MetadataNotProven("C1 retained candidate metadata exceeds the fixed limit")
    return candidate


def build_c1_orbit_audit(
    neighborhood_ids: Sequence[int],
    token_loader: Callable[[int], Sequence[CanonicalRowToken]],
    *,
    task037_extra_h2b: bool = False,
    candidate: C1CandidateAudit | None = None,
) -> C1OrbitAudit:
    """Build metadata transforms only after the candidate count is bounded."""

    if not task037_extra_h2b:
        raise ValueError("C1 requires explicit task037_extra_h2b opt-in")
    ids = tuple(int(value) for value in neighborhood_ids)
    if candidate is None:
        candidate = build_c1_candidate_audit(
            neighborhood_ids, token_loader, task037_extra_h2b=task037_extra_h2b
        )
    elif not isinstance(candidate, C1CandidateAudit):
        raise TypeError("C1 orbit candidate has the wrong type")
    if tuple(int(value) for value in candidate.neighborhood_ids.tolist()) != ids:
        raise C1MetadataNotProven("C1 candidate ids do not match orbit ids")
    if candidate.representative_count > 32:
        raise C1CandidateOrbitLimit(
            representative_count=candidate.representative_count,
            limit=32,
            candidate=candidate,
        )
    nloc = candidate.row_count
    permutations = np.empty((len(ids), nloc), dtype=np.int32)
    phases = np.empty((len(ids), nloc), dtype=np.complex128)
    transform_sha: list[str] = [""] * len(ids)
    repeat_transform_sha: list[str] = [""] * len(ids)

    def candidate_binding(neighborhood_id: int, tokens: Sequence[CanonicalRowToken]) -> bool:
        return (
            canonical_tokens_sha256(tokens)
            == bytes(candidate.metadata_sha256[neighborhood_id].tolist()).decode("ascii")
            and canonical_tokens_provenance_sha256(tokens)
            == bytes(candidate.provenance_sha256[neighborhood_id].tolist()).decode("ascii")
            and np.array_equal(
                _token_hash_rows(tokens), candidate.row_token_sha256[neighborhood_id]
            )
            and np.array_equal(
                _provenance_hash_rows(tokens), candidate.row_provenance_sha256[neighborhood_id]
            )
        )
    for neighborhood_id in ids:
        member_tokens, _ = _validate_token_load(neighborhood_id, token_loader(neighborhood_id), nloc)
        repeat_tokens, _ = _validate_token_load(neighborhood_id, token_loader(neighborhood_id), nloc)
        if (
            tuple(token.token_sha256 for token in member_tokens)
            != tuple(token.token_sha256 for token in repeat_tokens)
            or tuple(token.provenance_sha256 for token in member_tokens)
            != tuple(token.provenance_sha256 for token in repeat_tokens)
            or not candidate_binding(neighborhood_id, member_tokens)
            or not candidate_binding(neighborhood_id, repeat_tokens)
        ):
            raise C1MetadataNotProven(f"neighborhood {neighborhood_id} token construction is nondeterministic")
        representative = int(candidate.representative_ids[neighborhood_id])
        representative_tokens, _ = _validate_token_load(
            representative, token_loader(representative), nloc
        )
        repeat_representative_tokens, _ = _validate_token_load(
            representative, token_loader(representative), nloc
        )
        if (
            not candidate_binding(representative, representative_tokens)
            or not candidate_binding(representative, repeat_representative_tokens)
        ):
            raise C1MetadataNotProven(
                f"neighborhood {neighborhood_id} representative tokens changed"
            )
        try:
            transform = build_monomial_transform(
                representative_tokens, member_tokens, task037_extra_h2b=True
            )
            repeat_transform = build_monomial_transform(
                repeat_representative_tokens,
                repeat_tokens,
                task037_extra_h2b=True,
            )
        except C0MonomialTransformNotProven as exc:
            raise C1MonomialTransformNotProven(
                f"neighborhood {neighborhood_id} monomial transform is unproven"
            ) from exc
        if (
            not np.array_equal(transform.permutation, repeat_transform.permutation)
            or not np.array_equal(transform.phases, repeat_transform.phases)
            or transform.transform_sha256 != repeat_transform.transform_sha256
        ):
            raise C1MetadataNotProven(
                f"neighborhood {neighborhood_id} transform construction is nondeterministic"
            )
        permutations[neighborhood_id] = transform.permutation
        phases[neighborhood_id] = transform.phases
        transform_sha[neighborhood_id] = transform.transform_sha256
        repeat_transform_sha[neighborhood_id] = repeat_transform.transform_sha256
    transform_array = np.asarray([_ascii_hash(value) for value in transform_sha], dtype=np.uint8)
    audit = C1OrbitAudit(
        neighborhood_ids=candidate.neighborhood_ids,
        orbit_ids=candidate.orbit_ids,
        representative_ids=candidate.representative_ids,
        metadata_sha256=candidate.metadata_sha256,
        provenance_sha256=candidate.provenance_sha256,
        row_token_sha256=candidate.row_token_sha256,
        row_provenance_sha256=candidate.row_provenance_sha256,
        permutations=permutations,
        phases=phases,
        transform_sha256=transform_array,
        repeat_transform_sha256=np.asarray(
            [_ascii_hash(value) for value in repeat_transform_sha], dtype=np.uint8
        ),
        representative_members=candidate.representative_members,
    )
    if audit.retained_metadata_bytes > C1_METADATA_LIMIT_BYTES:
        raise C1MetadataNotProven("C1 retained orbit metadata exceeds the fixed limit")
    return audit


def _validate_matrix(matrix: Any, label: str) -> np.ndarray:
    if (
        not isinstance(matrix, np.ndarray)
        or matrix.dtype != np.dtype(np.complex128)
        or matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or not matrix.flags.c_contiguous
    ):
        raise ValueError(f"C1 {label} matrix must be C-contiguous complex128 square")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"C1 {label} matrix is nonfinite")
    return matrix


def _validate_probes(probes: Any, size: int) -> np.ndarray:
    if (
        not isinstance(probes, np.ndarray)
        or probes.dtype != np.dtype(np.complex128)
        or probes.shape != (2, size)
        or not probes.flags.c_contiguous
        or not np.all(np.isfinite(probes))
    ):
        raise ValueError("C1 probes have the wrong shape or dtype")
    return probes


def _relative(numerator: float, denominator: float) -> float:
    if denominator <= 0.0 or not np.isfinite(denominator):
        raise ValueError("C1 closure denominator is not positive finite")
    return float(numerator / denominator)


@dataclass(frozen=True)
class C1PatchAudit:
    """One member's matrix/action evidence; dense matrices are not retained."""

    matrix_sha256: str
    repeat_matrix_sha256: str
    comparison_matrix_sha256: str
    congruence_row_numerator_squared: np.ndarray
    congruence_row_denominator_squared: np.ndarray
    hermitian_row_numerator_squared: np.ndarray
    member_patch_action: np.ndarray
    transformed_patch_action: np.ndarray
    member_exact_action: np.ndarray
    hermitian_error: float
    congruence_relative_error: float
    patch_action_relative_error: float
    exact_action_relative_error: float
    finite: bool
    deterministic: bool

    def __post_init__(self) -> None:
        arrays = (
            _readonly_copy(self.congruence_row_numerator_squared, np.dtype(np.float64)),
            _readonly_copy(self.congruence_row_denominator_squared, np.dtype(np.float64)),
            _readonly_copy(self.hermitian_row_numerator_squared, np.dtype(np.float64)),
            _readonly_copy(self.member_patch_action, np.dtype(np.complex128)),
            _readonly_copy(self.transformed_patch_action, np.dtype(np.complex128)),
            _readonly_copy(self.member_exact_action, np.dtype(np.complex128)),
        )
        if arrays[0].ndim != 1 or arrays[1].shape != arrays[0].shape or arrays[2].shape != arrays[0].shape:
            raise ValueError("C1 row closure arrays do not close")
        if arrays[3].shape != (2, arrays[0].size) or arrays[4].shape != arrays[3].shape:
            raise ValueError("C1 patch action arrays do not close")
        if arrays[5].shape != arrays[3].shape:
            raise ValueError("C1 full action arrays do not close")
        if not all(_valid_sha(value) for value in (
            self.matrix_sha256,
            self.repeat_matrix_sha256,
            self.comparison_matrix_sha256,
        )):
            raise ValueError("C1 patch hashes are invalid")
        if not all(np.all(np.isfinite(array)) for array in arrays):
            raise ValueError("C1 patch audit arrays are nonfinite")
        for name, value in (
            ("hermitian_error", self.hermitian_error),
            ("congruence_relative_error", self.congruence_relative_error),
            ("patch_action_relative_error", self.patch_action_relative_error),
            ("exact_action_relative_error", self.exact_action_relative_error),
        ):
            if not np.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"C1 {name} is invalid")
        for name, value in zip(
            (
                "congruence_row_numerator_squared",
                "congruence_row_denominator_squared",
                "hermitian_row_numerator_squared",
                "member_patch_action",
                "transformed_patch_action",
                "member_exact_action",
            ),
            arrays,
            strict=True,
        ):
            object.__setattr__(self, name, value)

    def jsonable(self) -> dict[str, Any]:
        return {
            "matrix_sha256": self.matrix_sha256,
            "repeat_matrix_sha256": self.repeat_matrix_sha256,
            "comparison_matrix_sha256": self.comparison_matrix_sha256,
            "congruence_row_numerator_squared_sha256": _array_sha256(self.congruence_row_numerator_squared),
            "congruence_row_denominator_squared_sha256": _array_sha256(self.congruence_row_denominator_squared),
            "hermitian_row_numerator_squared_sha256": _array_sha256(self.hermitian_row_numerator_squared),
            "member_patch_action_sha256": _array_sha256(self.member_patch_action),
            "transformed_patch_action_sha256": _array_sha256(self.transformed_patch_action),
            "member_exact_action_sha256": _array_sha256(self.member_exact_action),
            "hermitian_error": float(self.hermitian_error),
            "congruence_relative_error": float(self.congruence_relative_error),
            "patch_action_relative_error": float(self.patch_action_relative_error),
            "exact_action_relative_error": float(self.exact_action_relative_error),
            "finite": bool(self.finite),
            "deterministic": bool(self.deterministic),
            "matrix_materialized": False,
            "factorization_called": False,
        }


def audit_c1_patch(
    representative_matrix: np.ndarray,
    member_matrix: np.ndarray,
    repeat_matrix_sha256: str,
    transform: MonomialTransform,
    probes: np.ndarray,
    *,
    embed_member: Callable[[np.ndarray], np.ndarray],
    exact_action: Callable[[np.ndarray], np.ndarray],
    restrict_member: Callable[[np.ndarray], np.ndarray],
    lifecycle_observer: Callable[[int], None] | None = None,
) -> C1PatchAudit:
    """Audit one streamed member against its representative and exact action."""

    representative = _validate_matrix(representative_matrix, "representative")
    member = _validate_matrix(member_matrix, "member")
    if not _valid_sha(repeat_matrix_sha256):
        raise ValueError("C1 repeat matrix SHA is invalid")
    if representative.shape != member.shape:
        raise ValueError("C1 patch matrix shapes do not close")
    probes = _validate_probes(probes, member.shape[0])
    if transform.permutation.size != member.shape[0]:
        raise ValueError("C1 transform and patch sizes do not close")
    comparison = np.empty_like(member)
    row_numerator = np.zeros(member.shape[0], dtype=np.float64)
    row_denominator = np.zeros(member.shape[0], dtype=np.float64)
    hermitian_row_numerator = np.zeros(member.shape[0], dtype=np.float64)
    hermitian_denominator = 0.0
    for row in range(member.shape[0]):
        comparison[row, :] = (
            np.conj(transform.phases[row])
            * representative[transform.permutation[row], transform.permutation]
            * transform.phases
        )
        difference = member[row, :] - comparison[row, :]
        row_numerator[row] = float(np.sum(np.abs(difference) ** 2, dtype=np.float64))
        row_denominator[row] = float(np.sum(np.abs(member[row, :]) ** 2, dtype=np.float64))
        hermitian_difference = member[row, :] - np.conj(member[:, row])
        hermitian_row_numerator[row] = float(
            np.sum(np.abs(hermitian_difference) ** 2, dtype=np.float64)
        )
    if not np.all(np.isfinite(comparison)):
        raise ValueError("C1 comparison matrix is nonfinite")
    if lifecycle_observer is not None:
        lifecycle_observer(3)
    congruence = _relative(float(np.sum(row_numerator)), float(np.sum(row_denominator))) ** 0.5
    hermitian_error = _relative(
        float(np.sum(hermitian_row_numerator, dtype=np.float64)),
        float(np.sum(row_denominator, dtype=np.float64)),
    ) ** 0.5
    member_actions: list[np.ndarray] = []
    transformed_actions: list[np.ndarray] = []
    member_exact_actions: list[np.ndarray] = []
    for probe in probes:
        member_action = np.asarray(member @ probe, dtype=np.complex128)
        transformed_action = np.asarray(comparison @ probe, dtype=np.complex128)
        member_exact = np.asarray(
            restrict_member(exact_action(embed_member(probe))),
            dtype=np.complex128,
        )
        member_actions.append(member_action)
        transformed_actions.append(transformed_action)
        member_exact_actions.append(member_exact)
    member_patch_action_array = np.ascontiguousarray(member_actions, dtype=np.complex128)
    transformed_patch_action_array = np.ascontiguousarray(transformed_actions, dtype=np.complex128)
    member_exact_action_array = np.ascontiguousarray(member_exact_actions, dtype=np.complex128)
    patch_action_relative = _relative(
        float(np.linalg.norm(member_patch_action_array - transformed_patch_action_array)),
        float(np.linalg.norm(member_patch_action_array)),
    )
    exact_action_relative = _relative(
        float(np.linalg.norm(member_patch_action_array - member_exact_action_array)),
        float(np.linalg.norm(member_patch_action_array)),
    )
    return C1PatchAudit(
        matrix_sha256=_array_sha256(member),
        repeat_matrix_sha256=repeat_matrix_sha256,
        comparison_matrix_sha256=_array_sha256(comparison),
        congruence_row_numerator_squared=row_numerator,
        congruence_row_denominator_squared=row_denominator,
        hermitian_row_numerator_squared=hermitian_row_numerator,
        member_patch_action=member_patch_action_array,
        transformed_patch_action=transformed_patch_action_array,
        member_exact_action=member_exact_action_array,
        hermitian_error=hermitian_error,
        congruence_relative_error=congruence,
        patch_action_relative_error=patch_action_relative,
        exact_action_relative_error=exact_action_relative,
        finite=True,
        deterministic=_array_sha256(member) == repeat_matrix_sha256,
    )


def _array_entry(path: Path, array: np.ndarray) -> dict[str, Any]:
    np.save(path, array, allow_pickle=False)
    return {
        "path": path.name,
        "sha256": _file_sha256(path),
        "bytes": int(path.stat().st_size),
        "dtype": str(array.dtype),
        "shape": [int(value) for value in array.shape],
        "nbytes": int(array.nbytes),
    }


def write_c1_candidate_manifest(
    root: Path,
    candidate: C1CandidateAudit,
    *,
    identity: Mapping[str, Any],
) -> Path:
    """Write the candidate-only state without T, probes, or patch arrays."""

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    arrays = {
        "neighborhood_ids": candidate.neighborhood_ids,
        "orbit_ids": candidate.orbit_ids,
        "representative_ids": candidate.representative_ids,
        "metadata_sha256": candidate.metadata_sha256,
        "provenance_sha256": candidate.provenance_sha256,
        "row_token_sha256": candidate.row_token_sha256,
        "row_provenance_sha256": candidate.row_provenance_sha256,
    }
    files = {
        name: _array_entry(root / f"{name}.npy", array)
        for name, array in arrays.items()
    }
    manifest = {
        "schema": C1_SCHEMA,
        "state": "candidate_only",
        "identity": dict(identity),
        "audit": candidate.jsonable(),
        "files": files,
        "patch_audits": [],
        "factorization_called": False,
        "factor_store_written": False,
        "retained_metadata_bytes": 0,
        "evidence_sha256": None,
    }
    manifest["retained_metadata_bytes"] = c1_retained_metadata_bytes(manifest, arrays)
    manifest["evidence_sha256"] = hashlib.sha256(
        _json_bytes({key: value for key, value in manifest.items() if key != "evidence_sha256"})
    ).hexdigest()
    path = root / "c1_manifest.json"
    path.write_bytes(_json_bytes(manifest))
    return path


def load_c1_candidate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Load and hash-check the candidate-only compact state."""

    path = path.resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if (
        manifest.get("schema") != C1_SCHEMA
        or manifest.get("state") != "candidate_only"
        or not _valid_sha(manifest.get("evidence_sha256"))
    ):
        raise ValueError("C1 candidate manifest schema/evidence is invalid")
    expected = hashlib.sha256(
        _json_bytes({key: value for key, value in manifest.items() if key != "evidence_sha256"})
    ).hexdigest()
    if manifest["evidence_sha256"] != expected:
        raise ValueError("C1 candidate evidence SHA mismatch")
    required = {
        "neighborhood_ids", "orbit_ids", "representative_ids",
        "metadata_sha256", "provenance_sha256", "row_token_sha256",
        "row_provenance_sha256",
    }
    files = manifest.get("files")
    if not isinstance(files, Mapping) or set(files) != required:
        raise ValueError("C1 candidate array inventory is incomplete")
    arrays: dict[str, np.ndarray] = {}
    for name, item in files.items():
        if not isinstance(item, Mapping) or item.get("path") != f"{name}.npy":
            raise ValueError("C1 candidate array path is invalid")
        array_path = path.parent / str(item["path"])
        if not array_path.is_file() or _file_sha256(array_path) != item.get("sha256"):
            raise ValueError("C1 candidate array SHA mismatch")
        array = np.load(array_path, allow_pickle=False)
        if (
            str(array.dtype) != item.get("dtype")
            or list(array.shape) != item.get("shape")
            or int(array.nbytes) != item.get("nbytes")
            or int(array_path.stat().st_size) != item.get("bytes")
        ):
            raise ValueError("C1 candidate array metadata mismatch")
        arrays[name] = array
    return manifest, arrays


def write_c1_orbit_manifest(
    root: Path,
    audit: C1OrbitAudit,
    probes: np.ndarray,
    *,
    identity: Mapping[str, Any],
    patch_audits: Sequence[Mapping[str, Any]] = (),
    patch_arrays: Mapping[str, np.ndarray] | None = None,
) -> Path:
    """Write compact fixed-width C1 arrays and a hash-closed manifest."""

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    probes = _validate_probes(probes, audit.row_count)
    arrays = {
        "neighborhood_ids": audit.neighborhood_ids,
        "orbit_ids": audit.orbit_ids,
        "representative_ids": audit.representative_ids,
        "metadata_sha256": audit.metadata_sha256,
        "provenance_sha256": audit.provenance_sha256,
        "row_token_sha256": audit.row_token_sha256,
        "row_provenance_sha256": audit.row_provenance_sha256,
        "permutations": audit.permutations,
        "phases": audit.phases,
        "transform_sha256": audit.transform_sha256,
        "repeat_transform_sha256": audit.repeat_transform_sha256,
        "probes": probes,
    }
    if patch_arrays is not None:
        for name, array in patch_arrays.items():
            if not isinstance(name, str) or not name.startswith("patch_") or name in arrays:
                raise ValueError("C1 patch array name is invalid")
            arrays[name] = np.asarray(array)
    files = {
        name: _array_entry(root / f"{name}.npy", array)
        for name, array in arrays.items()
    }
    patch_records = [dict(item) for item in patch_audits]
    manifest = {
        "schema": C1_SCHEMA,
        "identity": dict(identity),
        "audit": audit.jsonable(),
        "probe_seed": C1_PROBE_SEED,
        "probe_sha256": _array_sha256(probes),
        "files": files,
        "patch_audits": patch_records,
        "factorization_called": False,
        "factor_store_written": False,
        "retained_metadata_bytes": 0,
        "evidence_sha256": None,
    }
    manifest["retained_metadata_bytes"] = c1_retained_metadata_bytes(manifest, arrays)
    manifest["evidence_sha256"] = hashlib.sha256(
        _json_bytes({key: value for key, value in manifest.items() if key != "evidence_sha256"})
    ).hexdigest()
    path = root / "c1_manifest.json"
    path.write_bytes(_json_bytes(manifest))
    return path


def load_c1_orbit_manifest(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Validate and load C1 compact arrays without any factorization."""

    path = path.resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if manifest.get("schema") != C1_SCHEMA or not _valid_sha(manifest.get("evidence_sha256")):
        raise ValueError("C1 manifest schema/evidence is invalid")
    expected = hashlib.sha256(
        _json_bytes({key: value for key, value in manifest.items() if key != "evidence_sha256"})
    ).hexdigest()
    if manifest["evidence_sha256"] != expected:
        raise ValueError("C1 manifest evidence SHA mismatch")
    files = manifest.get("files")
    required_files = {
        "neighborhood_ids",
        "orbit_ids",
        "representative_ids",
        "metadata_sha256",
        "provenance_sha256",
        "row_token_sha256",
        "row_provenance_sha256",
        "permutations",
        "phases",
        "transform_sha256",
        "repeat_transform_sha256",
        "probes",
    }
    if (
        not isinstance(files, Mapping)
        or not required_files <= set(files)
        or any(not str(name).startswith("patch_") for name in set(files) - required_files)
    ):
        raise ValueError("C1 manifest array inventory is incomplete")
    arrays: dict[str, np.ndarray] = {}
    for name, item in files.items():
        if not isinstance(item, Mapping) or item.get("path") != f"{name}.npy":
            raise ValueError("C1 manifest array path is invalid")
        array_path = path.parent / str(item["path"])
        if not array_path.is_file() or _file_sha256(array_path) != item.get("sha256"):
            raise ValueError("C1 array file SHA mismatch")
        array = np.load(array_path, allow_pickle=False)
        if (
            str(array.dtype) != item.get("dtype")
            or [int(value) for value in array.shape] != item.get("shape")
            or int(array.nbytes) != item.get("nbytes")
            or int(array_path.stat().st_size) != item.get("bytes")
        ):
            raise ValueError("C1 array metadata mismatch")
        if np.issubdtype(array.dtype, np.inexact) and not np.all(np.isfinite(array)):
            raise ValueError("C1 array is nonfinite")
        arrays[name] = np.ascontiguousarray(array)
    if arrays["probes"].shape != (2, arrays["permutations"].shape[1]):
        raise ValueError("C1 probe shape mismatch")
    if manifest.get("probe_sha256") != _array_sha256(arrays["probes"]):
        raise ValueError("C1 probe SHA mismatch")
    return manifest, arrays
