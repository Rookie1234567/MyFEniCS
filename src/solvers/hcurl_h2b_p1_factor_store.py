"""Opt-in H2B-P1 neighborhood discovery and bounded factor ledger.

This slice consumes already-qualified constrained R2 cell blocks.  It never
reapplies a cell expansion: a reconstructed ``C^H B_c C`` block is scattered
by that cell's independent global rows into one central row-complete patch.
No global matrix, per-cell factor, or slab factor is retained.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any

import numpy as np

from .hcurl_h2b_block_smoother import (
    H2BP0Factor,
    factorize_h2b_p0_patch,
    measure_h2b_p0_patch_direction,
)

__all__ = (
    "H2B_P1_ANCHOR_SOURCE_LABELS",
    "H2BP1ClassBlockAuthority",
    "H2BP1FactorLedger",
    "H2BP1Neighborhood",
    "canonical_h2b_p1_neighborhood_key",
    "build_h2b_p1_class_block_authority",
    "discover_h2b_p1_neighborhoods",
    "h2b_p1_live_set_audit",
    "measure_h2b_p1_anchor_sources",
    "stream_h2b_p1_neighborhood",
)


H2B_P1_NEIGHBORHOOD_SCHEMA = "task037.extra.h2b.p1.neighborhood.v1"
H2B_P1_ANCHOR_SOURCE_LABELS = (
    "gradient-dominated",
    "curl-dominated",
    "mixed",
    "checkerboard/high-frequency",
    "physical-RHS-like",
)
_SHA_HEX = frozenset("0123456789abcdef")


def _require_opt_in(task037_extra_h2b: bool) -> None:
    if not bool(task037_extra_h2b):
        raise ValueError("H2B-P1 requires explicit task037_extra_h2b opt-in")


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            raise TypeError("H2B-P1 identity cannot contain object arrays")
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and set(value) <= _SHA_HEX
    )


def _reference_rows(reference: Any) -> np.ndarray:
    value = (
        reference.get("independent_global_rows")
        if isinstance(reference, Mapping)
        else getattr(reference, "independent_global_rows", None)
    )
    rows = np.asarray(value, dtype=np.int64)
    if rows.ndim != 1 or rows.size == 0 or np.unique(rows).size != rows.size:
        raise ValueError("H2B-P1 cell reference rows are invalid")
    return np.ascontiguousarray(rows, dtype=np.int64)


def _reference_class_id(reference: Any) -> int:
    value = (
        reference.get("class_id")
        if isinstance(reference, Mapping)
        else getattr(reference, "class_id", None)
    )
    if type(value) is not int or value < 0:
        raise ValueError("H2B-P1 cell reference class id is invalid")
    return int(value)


def _class_label(
    record: Any,
    inventory: Mapping[int, Mapping[str, Any]],
    operator_identity: Mapping[str, Any],
) -> dict[str, Any]:
    class_id = _reference_class_id(record)
    item = inventory.get(class_id)
    if not isinstance(item, Mapping):
        raise ValueError("H2B-P1 R0 class inventory is incomplete")
    required = (
        "class_key_sha256",
        "constraint_pattern_sha256",
        "material_tag",
        "material_identity",
        "cell_widths",
        "orientation",
        "constraint_pattern_entry_count",
        "constraint_pattern_kinds",
    )
    if any(key not in item for key in required):
        raise ValueError("H2B-P1 class inventory lacks identity fields")
    for key in ("class_key_sha256", "constraint_pattern_sha256"):
        if not _valid_sha(item[key]) or str(getattr(record, key)) != item[key]:
            raise ValueError(f"H2B-P1 {key} authority mismatch")
    expansion_sha = str(getattr(record, "expansion_pattern_sha256", ""))
    inventory_expansion_sha = item.get("expansion_pattern_sha256")
    if not _valid_sha(expansion_sha):
        raise ValueError("H2B-P1 expansion pattern authority mismatch")
    if inventory_expansion_sha is not None and (
        not _valid_sha(inventory_expansion_sha)
        or expansion_sha != inventory_expansion_sha
    ):
        raise ValueError("H2B-P1 expansion pattern authority mismatch")
    numeric_sha = str(getattr(record, "numeric_matrix_sha256", ""))
    if not _valid_sha(numeric_sha):
        raise ValueError("H2B-P1 numeric class authority mismatch")
    expansion = getattr(record, "expansion", None)
    pattern_identity = getattr(expansion, "pattern_identity", None)
    return {
        "class_key_sha256": str(item["class_key_sha256"]),
        "constraint_pattern_sha256": str(item["constraint_pattern_sha256"]),
        "expansion_pattern_sha256": expansion_sha,
        "numeric_matrix_sha256": numeric_sha,
        "numeric_matrix_shape": tuple(int(value) for value in record.numeric_matrix_shape),
        "numeric_matrix_dtype": str(record.numeric_matrix_dtype),
        "pattern_identity": pattern_identity,
        "material_tag": item["material_tag"],
        "material_identity": item["material_identity"],
        "cell_widths": item["cell_widths"],
        "orientation": item["orientation"],
        "constraint_pattern_entry_count": item["constraint_pattern_entry_count"],
        "constraint_pattern_kinds": item["constraint_pattern_kinds"],
        "operator_identity": operator_identity,
    }


@dataclass(frozen=True)
class H2BP1ClassBlockAuthority:
    """Immutable P1 view of verified R2 class blocks.

    Only class/factor bindings, verified numeric SHAs, and one read-only
    reconstructed matrix per unique R2 factor are retained.  Class expansion
    metadata and the source factor store remain outside this object.
    """

    class_to_factor: np.ndarray
    factor_numeric_shas: tuple[str, ...]
    reconstructed_matrices: Iterable[np.ndarray]

    def __post_init__(self) -> None:
        class_to_factor = np.asarray(self.class_to_factor, dtype=np.int32)
        if class_to_factor.ndim != 1 or class_to_factor.size == 0:
            raise ValueError("H2B-P1 class/factor binding is invalid")
        shas = tuple(str(value) for value in self.factor_numeric_shas)
        matrices: list[np.ndarray] = []
        matrix_iter = iter(self.reconstructed_matrices)
        for factor_id, sha in enumerate(shas):
            try:
                matrix = next(matrix_iter)
            except StopIteration as exc:
                raise ValueError("H2B-P1 factor matrix stream is short") from exc
            if not _valid_sha(sha):
                raise ValueError("H2B-P1 factor numeric SHA is invalid")
            values = np.asarray(matrix)
            if (
                values.dtype != np.dtype(np.complex128)
                or values.ndim != 2
                or values.shape[0] != values.shape[1]
                or not np.all(np.isfinite(values))
            ):
                raise ValueError(f"H2B-P1 factor {factor_id} matrix is invalid")
            values = np.array(values, dtype=np.complex128, copy=True, order="C")
            values.setflags(write=False)
            matrices.append(values)
            del matrix
        try:
            extra_matrix = next(matrix_iter)
        except StopIteration:
            pass
        else:
            del extra_matrix
            raise ValueError("H2B-P1 factor matrix stream is long")
        if np.any(class_to_factor < 0) or np.any(class_to_factor >= len(matrices)):
            raise ValueError("H2B-P1 class/factor binding is out of range")
        class_to_factor = np.array(class_to_factor, dtype=np.int32, copy=True, order="C")
        class_to_factor.setflags(write=False)
        components = {
            "reconstructed_matrix_bytes": sum(int(value.nbytes) for value in matrices),
            "class_to_factor_bytes": int(class_to_factor.nbytes),
            "factor_numeric_sha256_bytes": sum(len(value.encode("ascii")) for value in shas),
        }
        audit = {
            "schema": "task037.extra.h2b.p1.class-block-authority.v1",
            "factor_count": len(matrices),
            "class_count": int(class_to_factor.size),
            "reconstruction_count": len(matrices),
            "retained_payload_components": MappingProxyType(components),
            "retained_payload_bytes": int(sum(components.values())),
            "finite": True,
            "immutable": True,
            "class_expansion_retained": False,
            "per_cell_factor": False,
            "global_matrix_materialized": False,
            "slab_factor": False,
        }
        object.__setattr__(self, "class_to_factor", class_to_factor)
        object.__setattr__(self, "factor_numeric_shas", shas)
        object.__setattr__(self, "reconstructed_matrices", tuple(matrices))
        object.__setattr__(self, "_audit", MappingProxyType(audit))

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._audit

    def factor_id_for_class(self, class_id: int) -> int:
        if type(class_id) is not int or not 0 <= class_id < self.class_to_factor.size:
            raise ValueError("H2B-P1 class id is out of range")
        return int(self.class_to_factor[class_id])

    def numeric_sha_for_factor(self, factor_id: int) -> str:
        if type(factor_id) is not int or not 0 <= factor_id < len(self.factor_numeric_shas):
            raise ValueError("H2B-P1 factor id is out of range")
        return self.factor_numeric_shas[factor_id]

    def matrix_for_factor(self, factor_id: int) -> np.ndarray:
        if type(factor_id) is not int or not 0 <= factor_id < len(self.reconstructed_matrices):
            raise ValueError("H2B-P1 factor id is out of range")
        return self.reconstructed_matrices[factor_id]


def build_h2b_p1_class_block_authority(
    factor_store: Any, *, task037_extra_h2b: bool = False
) -> H2BP1ClassBlockAuthority:
    """Build the one-time immutable R2 class-block view for P1."""

    _require_opt_in(task037_extra_h2b)
    classes = tuple(factor_store.classes)
    if not classes:
        raise ValueError("H2B-P1 needs at least one R2 class")
    class_to_factor = np.empty(len(classes), dtype=np.int32)
    factor_ids: set[int] = set()
    for expected_class_id, record in enumerate(classes):
        if type(record.class_id) is not int or record.class_id != expected_class_id:
            raise ValueError("H2B-P1 R2 class ids are not continuous")
        if type(record.factor_id) is not int or record.factor_id < 0:
            raise ValueError("H2B-P1 R2 factor binding is invalid")
        class_to_factor[expected_class_id] = record.factor_id
        factor_ids.add(record.factor_id)
    if factor_ids != set(range(len(factor_ids))):
        raise ValueError("H2B-P1 R2 factor ids are not continuous")
    shas = tuple(
        factor_store.factor_numeric_matrix_sha256(factor_id)
        for factor_id in range(len(factor_ids))
    )
    def matrix_stream():
        for factor_id in range(len(factor_ids)):
            matrix = factor_store.reconstruct_numeric_matrix(factor_id)
            try:
                yield matrix
            finally:
                del matrix
    for record in classes:
        factor_id = int(record.factor_id)
        if record.numeric_matrix_sha256 != shas[factor_id]:
            raise ValueError("H2B-P1 class/factor numeric SHA binding failed")
    return H2BP1ClassBlockAuthority(class_to_factor, shas, matrix_stream())


@dataclass(frozen=True)
class H2BP1Neighborhood:
    """One canonical neighborhood and its gather/scatter-only references."""

    neighborhood_id: int
    key_sha256: str
    representative_cell: int
    cell_ordinals: tuple[int, ...]
    central_class_id: int
    patch_rows: np.ndarray
    touching_cell_ordinals: tuple[int, ...]
    touching_class_ids: tuple[int, ...]
    numeric_accumulation_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.neighborhood_id) is not int or self.neighborhood_id < 0:
            raise ValueError("H2B-P1 neighborhood id is invalid")
        if not _valid_sha(self.key_sha256):
            raise ValueError("H2B-P1 neighborhood SHA is invalid")
        rows = np.asarray(self.patch_rows, dtype=np.int64)
        if rows.ndim != 1 or rows.size == 0 or np.unique(rows).size != rows.size:
            raise ValueError("H2B-P1 patch rows are invalid")
        if len(self.touching_cell_ordinals) == 0:
            raise ValueError("H2B-P1 neighborhood has no touching cells")
        if len(self.touching_class_ids) != len(self.touching_cell_ordinals):
            raise ValueError("H2B-P1 touching class/cell records do not close")
        numeric_order = tuple(self.numeric_accumulation_order)
        touching = tuple(int(value) for value in self.touching_cell_ordinals)
        if (
            len(numeric_order) != len(touching)
            or any(type(value) is not int for value in numeric_order)
            or len(set(numeric_order)) != len(numeric_order)
            or set(numeric_order) != set(touching)
        ):
            raise ValueError("H2B-P1 numeric accumulation order does not close")
        rows = np.array(rows, dtype=np.int64, copy=True, order="C")
        rows.setflags(write=False)
        object.__setattr__(self, "patch_rows", rows)
        object.__setattr__(self, "cell_ordinals", tuple(int(x) for x in self.cell_ordinals))
        object.__setattr__(
            self,
            "touching_cell_ordinals",
            touching,
        )
        object.__setattr__(
            self, "touching_class_ids", tuple(int(x) for x in self.touching_class_ids)
        )
        object.__setattr__(self, "numeric_accumulation_order", numeric_order)

    @property
    def touching_cell_count(self) -> int:
        return len(self.touching_cell_ordinals)

    @property
    def touching_class_count(self) -> int:
        return len(set(self.touching_class_ids))

    @property
    def numeric_accumulation_order_sha256(self) -> str:
        return _sha256(self.numeric_accumulation_order)


def canonical_h2b_p1_neighborhood_key(
    central_ordinal: int,
    cell_references: Sequence[Any],
    class_records: Sequence[Any],
    class_inventory: Sequence[Mapping[str, Any]],
    operator_identity: Mapping[str, Any],
    *,
    task037_extra_h2b: bool = False,
) -> tuple[
    str,
    dict[str, Any],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
]:
    """Build a row-renumbering-invariant neighborhood key.

    Absolute rows are used only to create each local-slot to central-slot map;
    the returned payload contains no global row, owner, cell ordinal, or
    coordinate.  The touching ordinals and class sequence are returned
    separately for gather/scatter and audit output.
    """

    _require_opt_in(task037_extra_h2b)
    if type(central_ordinal) is not int or not 0 <= central_ordinal < len(cell_references):
        raise ValueError("H2B-P1 central cell ordinal is invalid")
    if not isinstance(operator_identity, Mapping):
        raise ValueError("H2B-P1 operator identity is invalid")
    records_by_id = {}
    for record in class_records:
        class_id = _reference_class_id(record)
        if class_id in records_by_id:
            raise ValueError("H2B-P1 class records repeat a class id")
        records_by_id[class_id] = record
    inventory_by_id = {}
    for item in class_inventory:
        if not isinstance(item, Mapping) or type(item.get("class_id")) is not int:
            raise ValueError("H2B-P1 R0 inventory class id is invalid")
        class_id = int(item["class_id"])
        if class_id in inventory_by_id:
            raise ValueError("H2B-P1 R0 inventory repeats a class id")
        inventory_by_id[class_id] = item
    rows = [_reference_rows(reference) for reference in cell_references]
    central_rows = rows[central_ordinal]
    central_slots = {int(row): index for index, row in enumerate(central_rows.tolist())}
    touching: list[int] = []
    tokens: list[dict[str, Any]] = []
    class_sequence: list[int] = []
    numeric_tokens: list[tuple[str, tuple[int, ...], int]] = []
    for ordinal, cell_rows in enumerate(rows):
        relative = tuple(central_slots.get(int(row), -1) for row in cell_rows.tolist())
        if not any(slot >= 0 for slot in relative):
            continue
        class_id = _reference_class_id(cell_references[ordinal])
        record = records_by_id.get(class_id)
        if record is None:
            raise ValueError("H2B-P1 cell class record is missing")
        label = _class_label(record, inventory_by_id, operator_identity)
        tokens.append({"label": label, "relative_row_incidence": relative})
        numeric_tokens.append((str(label["numeric_matrix_sha256"]), relative, ordinal))
        touching.append(ordinal)
        class_sequence.append(class_id)
    if not touching or central_ordinal not in touching:
        raise ValueError("H2B-P1 central cell is absent from its neighborhood")
    payload = {
        "schema": H2B_P1_NEIGHBORHOOD_SCHEMA,
        "central_class": _class_label(
            records_by_id[_reference_class_id(cell_references[central_ordinal])],
            inventory_by_id,
            operator_identity,
        ),
        "touching": sorted(tokens, key=_json_bytes),
    }
    numeric_order = tuple(
        ordinal
        for _numeric_sha, _relative, ordinal in sorted(
            numeric_tokens,
            key=lambda item: (item[0], item[1], item[2]),
        )
    )
    return _sha256(payload), payload, tuple(touching), tuple(class_sequence), numeric_order


def discover_h2b_p1_neighborhoods(
    cell_references: Sequence[Any],
    class_records: Sequence[Any],
    class_inventory: Sequence[Mapping[str, Any]],
    operator_identity: Mapping[str, Any],
    *,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Discover and canonically number all cell neighborhoods."""

    _require_opt_in(task037_extra_h2b)
    grouped: dict[
        str,
        list[
            tuple[
                int,
                tuple[int, ...],
                tuple[int, ...],
                tuple[int, ...],
                dict[str, Any],
            ]
        ],
    ] = {}
    payload_by_sha: dict[str, bytes] = {}
    for ordinal in range(len(cell_references)):
        key_sha, payload, touching, class_sequence, numeric_order = canonical_h2b_p1_neighborhood_key(
            ordinal,
            cell_references,
            class_records,
            class_inventory,
            operator_identity,
            task037_extra_h2b=True,
        )
        encoded = _json_bytes(payload)
        if key_sha in payload_by_sha and payload_by_sha[key_sha] != encoded:
            raise ValueError("H2B-P1 neighborhood SHA collision")
        payload_by_sha[key_sha] = encoded
        grouped.setdefault(key_sha, []).append(
            (ordinal, touching, class_sequence, numeric_order, payload)
        )
    neighborhoods: list[H2BP1Neighborhood] = []
    cell_ids = np.full(len(cell_references), -1, dtype=np.int32)
    for neighborhood_id, key_sha in enumerate(sorted(grouped)):
        members = grouped[key_sha]
        representative = min(members, key=lambda item: item[0])
        representative_cell, touching, class_sequence, numeric_order, _ = representative
        for ordinal, _, _, _, _ in members:
            cell_ids[ordinal] = neighborhood_id
        neighborhoods.append(
            H2BP1Neighborhood(
                neighborhood_id=neighborhood_id,
                key_sha256=key_sha,
                representative_cell=int(representative_cell),
                cell_ordinals=tuple(sorted(item[0] for item in members)),
                central_class_id=_reference_class_id(
                    cell_references[representative_cell]
                ),
                patch_rows=_reference_rows(cell_references[representative_cell]),
                touching_cell_ordinals=tuple(touching),
                touching_class_ids=tuple(class_sequence),
                numeric_accumulation_order=tuple(numeric_order),
            )
        )
    if np.any(cell_ids < 0):
        raise ValueError("H2B-P1 neighborhood mapping is incomplete")
    cell_ids.setflags(write=False)
    return {
        "schema": H2B_P1_NEIGHBORHOOD_SCHEMA,
        "neighborhoods": tuple(neighborhoods),
        "cell_neighborhood_ids": cell_ids,
        "unique_neighborhood_count": len(neighborhoods),
        "neighborhood_digest": _array_sha256(cell_ids),
        "cell_count": len(cell_references),
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "per_cell_factor": False,
        "slab_factor": False,
    }


def stream_h2b_p1_neighborhood(
    neighborhood: H2BP1Neighborhood,
    cell_references: Sequence[Any],
    class_block_authority: H2BP1ClassBlockAuthority,
    *,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Stream immutable reconstructed R2 blocks into one row-complete patch."""

    _require_opt_in(task037_extra_h2b)
    patch_rows = np.asarray(neighborhood.patch_rows, dtype=np.int64)
    patch_index = {int(row): index for index, row in enumerate(patch_rows.tolist())}
    patch = np.zeros((patch_rows.size, patch_rows.size), dtype=np.complex128)
    actual_class_ids = tuple(
        _reference_class_id(cell_references[ordinal])
        for ordinal in neighborhood.touching_cell_ordinals
    )
    if actual_class_ids != neighborhood.touching_class_ids:
        raise ValueError("H2B-P1 touching class authority mismatch")
    if _reference_class_id(cell_references[neighborhood.representative_cell]) != (
        neighborhood.central_class_id
    ):
        raise ValueError("H2B-P1 central class authority mismatch")
    seen: set[int] = set()
    for ordinal in neighborhood.numeric_accumulation_order:
        if type(ordinal) is not int or ordinal in seen or ordinal < 0 or ordinal >= len(cell_references):
            raise ValueError("H2B-P1 touching cell ordinal is invalid")
        reference = cell_references[ordinal]
        class_id = _reference_class_id(reference)
        factor_id = class_block_authority.factor_id_for_class(class_id)
        block = class_block_authority.matrix_for_factor(factor_id)
        rows = _reference_rows(reference)
        if block.shape != (rows.size, rows.size):
            raise ValueError("H2B-P1 constrained block shape does not match rows")
        positions = np.asarray(
            [patch_index.get(int(row), -1) for row in rows.tolist()], dtype=np.int32
        )
        selected = np.flatnonzero(positions >= 0)
        if selected.size:
            patch[np.ix_(positions[selected], positions[selected])] += block[
                np.ix_(selected, selected)
            ]
        seen.add(ordinal)
    required = set(neighborhood.touching_cell_ordinals)
    if seen != required:
        raise ValueError("H2B-P1 stream omitted a touching cell")
    return {
        "schema": H2B_P1_NEIGHBORHOOD_SCHEMA,
        "matrix": patch,
        "matrix_sha256": _array_sha256(patch),
        "matrix_shape": tuple(int(value) for value in patch.shape),
        "matrix_dtype": str(patch.dtype),
        "matrix_nbytes": int(patch.nbytes),
        "r2_factor_reconstruction_count": class_block_authority.audit[
            "reconstruction_count"
        ],
        "r2_factor_authority_bytes": class_block_authority.audit[
            "retained_payload_bytes"
        ],
        "touching_cell_count": neighborhood.touching_cell_count,
        "touching_class_count": neighborhood.touching_class_count,
        "numeric_accumulation_order": neighborhood.numeric_accumulation_order,
        "numeric_accumulation_order_sha256": neighborhood.numeric_accumulation_order_sha256,
        "max_live_patch_matrix_count": 1,
        "per_cell_factor": False,
        "per_cell_dense_tensor": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "slab_factor": False,
    }


class H2BP1FactorLedger:
    """Exact-SHA deduplicated P1 LU factors with the 32-factor ceiling."""

    def __init__(self, *, max_unique_factors: int = 32, task037_extra_h2b: bool = False) -> None:
        _require_opt_in(task037_extra_h2b)
        if type(max_unique_factors) is not int or max_unique_factors <= 0:
            raise ValueError("H2B-P1 factor ceiling is invalid")
        self._max_unique_factors = max_unique_factors
        self._by_matrix_sha: dict[str, int] = {}
        self._factors: list[H2BP0Factor] = []

    @property
    def factors(self) -> tuple[H2BP0Factor, ...]:
        return tuple(self._factors)

    def accept(self, matrix: np.ndarray, *, task037_extra_h2b: bool = False) -> int:
        _require_opt_in(task037_extra_h2b)
        values = np.asarray(matrix)
        if (
            values.dtype != np.dtype(np.complex128)
            or not values.flags.c_contiguous
            or values.ndim != 2
            or values.shape[0] != values.shape[1]
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("H2B-P1 patch matrix is invalid")
        matrix_sha = _array_sha256(values)
        existing = self._by_matrix_sha.get(matrix_sha)
        if existing is not None:
            return existing
        if len(self._factors) >= self._max_unique_factors:
            raise ValueError("H2B-P1 unique numeric factor limit exceeded")
        factor = factorize_h2b_p0_patch(values, task037_extra_h2b=True)
        factor_id = len(self._factors)
        self._factors.append(factor)
        self._by_matrix_sha[matrix_sha] = factor_id
        return factor_id

    def audit(
        self,
        *,
        neighborhood_count: int,
        cell_count: int,
        metadata_bytes: int,
        cell_reference_bytes: int,
        neighborhood_mapping_bytes: int,
        class_expansion_sparse_bytes: int,
        task037_extra_h2b: bool = False,
    ) -> dict[str, Any]:
        _require_opt_in(task037_extra_h2b)
        for name, value in (
            ("neighborhood_count", neighborhood_count),
            ("cell_count", cell_count),
            ("metadata_bytes", metadata_bytes),
            ("class_expansion_sparse_bytes", class_expansion_sparse_bytes),
            ("cell_reference_bytes", cell_reference_bytes),
            ("neighborhood_mapping_bytes", neighborhood_mapping_bytes),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"H2B-P1 {name} is invalid")
        components = {
            "factor_values_bytes": sum(int(f.values.nbytes) for f in self._factors),
            "factor_pivots_bytes": sum(int(f.pivots.nbytes) for f in self._factors),
            "canonical_json_metadata_bytes": metadata_bytes,
            "class_expansion_sparse_bytes": class_expansion_sparse_bytes,
            "cell_reference_bytes": cell_reference_bytes,
            "neighborhood_mapping_bytes": neighborhood_mapping_bytes,
        }
        if any(type(value) is not int or value < 0 for value in components.values()):
            raise ValueError("H2B-P1 payload component is invalid")
        total = int(sum(components.values()))
        return {
            "unique_factor_count": len(self._factors),
            "neighborhood_count": int(neighborhood_count),
            "cell_count": int(cell_count),
            "factor_plus_metadata_bytes": total,
            "factor_plus_metadata_limit_bytes": 500_000_000,
            "factor_plus_metadata_gate": total <= 500_000_000,
            "retained_payload_components": components,
            "factorization_residual_max": max(
                (float(f.factorization_residual) for f in self._factors), default=0.0
            ),
            "solve_residual_max": max(
                (float(f.solve_residual) for f in self._factors), default=0.0
            ),
            "finite": all(bool(f.finite) for f in self._factors),
            "deterministic": all(bool(f.deterministic) for f in self._factors),
            "per_cell_factor_count": 0,
            "per_cell_dense_tensor": False,
            "slab_factor_count": 0,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "schur_materialized": False,
            "ordinary_default_changed": False,
        }


def h2b_p1_live_set_audit(
    *,
    reconstruction_stage: Mapping[str, int],
    factor_stage: Mapping[str, int],
    limit_bytes: int = 1_700_000_000,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    _require_opt_in(task037_extra_h2b)
    required = {
        "reconstruction": (
            "mesh_action_runtime_bytes",
            "r2_lu_bytes",
            "reconstructed_cache_bytes",
            "reconstruction_lower_workspace_bytes",
            "reconstruction_upper_workspace_bytes",
            "reconstruction_permuted_workspace_bytes",
            "reconstruction_output_workspace_bytes",
            "reconstruction_pivots_bytes",
            "authority_copy_source_bytes",
            "authority_copy_destination_bytes",
            "metadata_work_bytes",
            "runtime_reserve_bytes",
        ),
        "factor": (
            "mesh_action_runtime_bytes",
            "reconstructed_cache_bytes",
            "accepted_factor_bytes",
            "current_patch_matrix_bytes",
            "current_lu_workspace_bytes",
            "factorization_original_copy_bytes",
            "factorization_first_lu_bytes",
            "factorization_repeated_lu_bytes",
            "factorization_lower_workspace_bytes",
            "factorization_upper_workspace_bytes",
            "factorization_reconstructed_workspace_bytes",
            "factorization_pivots_workspace_bytes",
            "factorization_condition_workspace_bytes",
            "metadata_work_bytes",
            "runtime_reserve_bytes",
        ),
    }
    inputs = {"reconstruction": reconstruction_stage, "factor": factor_stage}
    stages: dict[str, Any] = {}
    for name, components in inputs.items():
        if not isinstance(components, Mapping) or any(
            key not in components for key in required[name]
        ):
            raise ValueError(f"H2B-P1 {name} live-set components are incomplete")
        if any(type(value) is not int or value < 0 for value in components.values()):
            raise ValueError(f"H2B-P1 {name} live-set component is invalid")
        stages[name] = {
            "components": dict(components),
            "predicted_live_set_bytes": int(sum(components.values())),
        }
    if type(limit_bytes) is not int or limit_bytes <= 0:
        raise ValueError("H2B-P1 live-set limit is invalid")
    predicted = max(
        stages["reconstruction"]["predicted_live_set_bytes"],
        stages["factor"]["predicted_live_set_bytes"],
    )
    return {
        "stages": stages,
        "predicted_live_set_bytes": predicted,
        "predicted_live_set_limit_bytes": limit_bytes,
        "predicted_live_set_gate": predicted <= limit_bytes,
        "predicted_live_set_scope": "max(reconstruction_stage,factor_stage)",
        "workspace_accounting": {
            "reconstruction_internal_dense_matrices": 4,
            "authority_copy_dense_matrices": 2,
            "authority_copy_phase_mutually_exclusive": True,
            "factor_reconstruction_internal_dense_matrices": 3,
            "named_workspace_sum_is_conservative": True,
        },
        "r2_store_released_before_factor_stage": True,
    }


def measure_h2b_p1_anchor_sources(
    rhs_by_label: Mapping[str, np.ndarray],
    patch_matrix: np.ndarray,
    factor: H2BP0Factor,
    patch_rows: object,
    exact_action: Any,
    *,
    authority: Mapping[str, Any],
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Run the five fixed source oracle on a reconstructed P0 anchor.

    The caller supplies source vectors produced by the qualified B0 worker and
    the existing exact full-space action.  This helper performs no mesh, JIT,
    or source construction and is therefore suitable for the focused anchor
    diagnostic without creating formal evidence.
    """

    _require_opt_in(task037_extra_h2b)
    if tuple(rhs_by_label) != H2B_P1_ANCHOR_SOURCE_LABELS:
        raise ValueError("H2B-P1 anchor source order is not the frozen five-source order")
    required_authority = (
        "r0_source",
        "r1_source",
        "r2_factor_manifest_sha256",
        "r2_record_sha256",
        "r2_record_evidence_sha256",
    )
    if not isinstance(authority, Mapping) or any(
        key not in authority for key in required_authority
    ):
        raise ValueError("H2B-P1 anchor authority is missing")
    if any(
        not isinstance(authority[key], str)
        or len(authority[key]) not in (40, 64)
        or authority[key] != authority[key].lower()
        or not set(authority[key]) <= _SHA_HEX
        for key in required_authority
    ):
        raise ValueError("H2B-P1 anchor authority is invalid")
    sources = {
        label: measure_h2b_p0_patch_direction(
            np.asarray(rhs_by_label[label]),
            patch_matrix,
            factor,
            patch_rows,
            exact_action,
            closure_matrix=patch_matrix,
            task037_extra_h2b=True,
        )
        for label in H2B_P1_ANCHOR_SOURCE_LABELS
    }
    return {
        "schema": "task037.extra.h2b.p1.anchor.v1",
        "authority": _jsonable(authority),
        "sources": sources,
        "source_order": list(H2B_P1_ANCHOR_SOURCE_LABELS),
        "finite": all(
            np.isfinite(float(item["full_space_rho_star"]))
            for item in sources.values()
        ),
    }
