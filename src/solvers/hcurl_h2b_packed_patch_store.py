"""Opt-in packed HPD patch factors for the M3Y research lane.

This module retains only one-dimensional lower packed Cholesky factors and
the already-qualified P1 neighborhood/cell maps.  It does not retain a
square factor, pivots, patch matrices, QL/QH transforms, or a global matrix.
The store is deliberately separate from the historical P1 LU schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import lapack

from .hcurl_h2b_p1_factor_store import _deep_freeze, _jsonable, _valid_sha

__all__ = (
    "H2B_M3Y_PACKED_STORE_SCHEMA",
    "H2B_M3Y_PACKED_FACTOR_LIMIT",
    "H2B_M3Y_RETAINED_BYTES_LIMIT",
    "H2BM3YPackedCholeskyFactor",
    "H2BM3YPackedPatchStore",
    "build_h2b_m3y_packed_factor",
    "build_h2b_m3y_packed_patch_store",
    "write_h2b_m3y_packed_patch_store",
    "load_h2b_m3y_packed_patch_store",
    "packed_factor_nbytes",
)


H2B_M3Y_PACKED_STORE_SCHEMA = "task037.extra.h2b.m3y.packed-factor-store.v1"
H2B_M3Y_PACKED_FACTOR_LIMIT = 96
H2B_M3Y_RETAINED_BYTES_LIMIT = 560_000_000
_SHA_HEX = frozenset("0123456789abcdef")


def _require_opt_in(task037_extra_h2b: bool) -> None:
    if task037_extra_h2b is not True:
        raise ValueError("H2B-M3Y requires explicit task037_extra_h2b opt-in")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_relative_path(relative: Any, files: Mapping[str, Any]) -> bool:
    if not isinstance(relative, str):
        return False
    path = Path(relative)
    return not path.is_absolute() and ".." not in path.parts and relative in files


def packed_factor_nbytes(n: int) -> int:
    """Return bytes for one complex128 lower packed factor of order ``n``."""

    if type(n) is not int or n <= 0:
        raise ValueError("packed factor order is invalid")
    return n * (n + 1) // 2 * np.dtype(np.complex128).itemsize


@dataclass(frozen=True)
class H2BM3YPackedCholeskyFactor:
    """One immutable lower packed ``complex128`` Cholesky factor."""

    packed_values: np.ndarray
    n: int
    matrix_sha256: str | None = None
    factor_sha256: str | None = None
    factorization_info: int = 0
    finite: bool = True
    deterministic: bool = True

    def __post_init__(self) -> None:
        if type(self.n) is not int or self.n <= 0:
            raise ValueError("packed factor order is invalid")
        packed = np.asarray(self.packed_values)
        expected = self.n * (self.n + 1) // 2
        if (
            packed.dtype != np.dtype(np.complex128)
            or packed.ndim != 1
            or packed.size != expected
            or not packed.flags.c_contiguous
            or not np.all(np.isfinite(packed))
        ):
            raise ValueError("packed factor array is invalid")
        if packed.flags.writeable:
            packed = np.array(packed, dtype=np.complex128, order="C", copy=True)
        packed.setflags(write=False)
        if not _valid_sha(self.matrix_sha256):
            raise ValueError("packed factor source matrix SHA is invalid")
        digest = _array_sha256(packed)
        if self.factor_sha256 is not None and (
            not _valid_sha(self.factor_sha256) or self.factor_sha256 != digest
        ):
            raise ValueError("packed factor SHA mismatch")
        if type(self.factorization_info) is not int or self.factorization_info != 0:
            raise ValueError("packed factor LAPACK info is invalid")
        if type(self.finite) is not bool or type(self.deterministic) is not bool:
            raise ValueError("packed factor audit flags are invalid")
        if not self.finite or not self.deterministic:
            raise ValueError("packed factor audit flags must be true")
        object.__setattr__(self, "packed_values", packed)
        object.__setattr__(self, "factor_sha256", digest)

    @property
    def packed_nbytes(self) -> int:
        return int(self.packed_values.nbytes)

    def audit_jsonable(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "packed_length": int(self.packed_values.size),
            "packed_dtype": str(self.packed_values.dtype),
            "packed_nbytes": self.packed_nbytes,
            "matrix_sha256": self.matrix_sha256,
            "factor_sha256": self.factor_sha256,
            "factorization_info": self.factorization_info,
            "finite": self.finite,
            "deterministic": self.deterministic,
            "full_dense_factor_retained": False,
            "pivots_retained": False,
        }

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        rhs = np.asarray(right_hand_side)
        if (
            rhs.dtype != np.dtype(np.complex128)
            or rhs.ndim not in (1, 2)
            or rhs.shape[0] != self.n
            or not np.all(np.isfinite(rhs))
        ):
            raise ValueError("packed solve right-hand side is invalid")
        vector = rhs.ndim == 1
        work = np.array(
            rhs[:, None] if vector else rhs,
            dtype=np.complex128,
            order="F",
            copy=True,
        )
        pptrs = lapack.get_lapack_funcs(("pptrs",), (self.packed_values,))[0]
        solution, info = pptrs(
            self.n,
            self.packed_values,
            work,
            lower=1,
            overwrite_b=1,
        )
        if int(info) != 0:
            raise np.linalg.LinAlgError(f"zpptrs failed with info={int(info)}")
        result = np.asarray(solution)
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("packed solve returned nonfinite values")
        if vector:
            return np.array(result[:, 0], dtype=np.complex128, order="C", copy=True)
        return np.array(result, dtype=np.complex128, order="C", copy=True)


def build_h2b_m3y_packed_factor(
    matrix: np.ndarray,
    *,
    task037_extra_h2b: bool = False,
) -> H2BM3YPackedCholeskyFactor:
    """Factor one row-complete HPD patch using SciPy LAPACK packed storage."""

    _require_opt_in(task037_extra_h2b)
    values = np.asarray(matrix)
    if (
        values.dtype != np.dtype(np.complex128)
        or values.ndim != 2
        or values.shape[0] != values.shape[1]
        or not values.flags.c_contiguous
        or not np.all(np.isfinite(values))
    ):
        raise ValueError("H2B-M3Y patch matrix is invalid")
    n = int(values.shape[0])
    packed = np.empty(n * (n + 1) // 2, dtype=np.complex128)
    cursor = 0
    for column in range(n):
        next_cursor = cursor + n - column
        packed[cursor:next_cursor] = values[column:, column]
        cursor = next_cursor
    pptrf = lapack.get_lapack_funcs(("pptrf",), (packed,))[0]
    factored, info = pptrf(n, packed, lower=1, overwrite_ap=1)
    if int(info) != 0:
        raise np.linalg.LinAlgError(f"zpptrf failed with info={int(info)}")
    return H2BM3YPackedCholeskyFactor(
        np.asarray(factored, dtype=np.complex128),
        n,
        matrix_sha256=_array_sha256(values),
        factorization_info=int(info),
    )


def _validate_mapping(
    neighborhoods: tuple[Mapping[str, Any], ...],
    cell_ids: np.ndarray,
    offsets: np.ndarray,
    rows: np.ndarray,
    factor_count: int,
    factor_orders: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if (
        cell_ids.dtype != np.dtype(np.int32)
        or offsets.dtype != np.dtype(np.int64)
        or rows.dtype != np.dtype(np.int64)
        or cell_ids.ndim != 1
        or offsets.ndim != 1
        or rows.ndim != 1
        or offsets.size != cell_ids.size + 1
        or offsets.size <= 1
        or int(offsets[0]) != 0
        or int(offsets[-1]) != rows.size
        or np.any(np.diff(offsets) <= 0)
        or np.any(cell_ids < 0)
        or np.any(cell_ids >= len(neighborhoods))
        or np.any(rows < 0)
    ):
        raise ValueError("H2B-M3Y cell mapping arrays do not close")
    for cell_id in range(cell_ids.size):
        start, stop = int(offsets[cell_id]), int(offsets[cell_id + 1])
        if np.unique(rows[start:stop]).size != stop - start:
            raise ValueError("H2B-M3Y cell rows are not unique")
        neighborhood_id = int(cell_ids[cell_id])
        factor_id = int(neighborhoods[neighborhood_id]["factor_id"])
        if stop - start != factor_orders[factor_id]:
            raise ValueError("H2B-M3Y cell rows do not match factor order")
    members: list[list[int]] = [[] for _ in neighborhoods]
    for cell_id, neighborhood_id in enumerate(cell_ids.tolist()):
        members[int(neighborhood_id)].append(cell_id)
    for expected_id, record in enumerate(neighborhoods):
        if (
            not isinstance(record, Mapping)
            or type(record.get("neighborhood_id")) is not int
            or record["neighborhood_id"] != expected_id
            or not _valid_sha(record.get("key_sha256"))
            or type(record.get("factor_id")) is not int
            or not 0 <= record["factor_id"] < factor_count
            or not isinstance(record.get("cell_ordinals"), (list, tuple))
            or any(type(value) is not int for value in record["cell_ordinals"])
            or type(record.get("multiplicity")) is not int
            or record["multiplicity"] != len(record["cell_ordinals"])
            or tuple(members[expected_id]) != tuple(record["cell_ordinals"])
        ):
            raise ValueError("H2B-M3Y neighborhood/cell mapping is invalid")
    return cell_ids, offsets, rows


@dataclass(frozen=True)
class H2BM3YPackedPatchStore:
    """Retained packed factors plus direct global-row cell maps."""

    factors: tuple[H2BM3YPackedCholeskyFactor, ...]
    neighborhoods: tuple[Mapping[str, Any], ...]
    cell_neighborhood_ids: np.ndarray
    cell_row_offsets: np.ndarray
    cell_independent_global_rows: np.ndarray
    identity: Mapping[str, Any]

    def __post_init__(self) -> None:
        factors = tuple(self.factors)
        neighborhoods = tuple(_deep_freeze(dict(item)) for item in self.neighborhoods)
        if not factors or not neighborhoods:
            raise ValueError("H2B-M3Y store needs factors and neighborhoods")
        if len(factors) > H2B_M3Y_PACKED_FACTOR_LIMIT:
            raise ValueError("H2B-M3Y packed factor count exceeds fixed limit")
        orders = {factor.n for factor in factors}
        if len(orders) != 1:
            raise ValueError("H2B-M3Y factors have inconsistent orders")
        cell_ids = np.asarray(self.cell_neighborhood_ids)
        offsets = np.asarray(self.cell_row_offsets)
        rows = np.asarray(self.cell_independent_global_rows)
        cell_ids = np.array(cell_ids, dtype=np.int32, order="C", copy=True)
        offsets = np.array(offsets, dtype=np.int64, order="C", copy=True)
        rows = np.array(rows, dtype=np.int64, order="C", copy=True)
        _validate_mapping(
            neighborhoods,
            cell_ids,
            offsets,
            rows,
            len(factors),
            tuple(factor.n for factor in factors),
        )
        identity = _deep_freeze(self.identity)
        if not isinstance(identity, Mapping):
            raise ValueError("H2B-M3Y store identity is invalid")
        cell_ids.setflags(write=False)
        offsets.setflags(write=False)
        rows.setflags(write=False)
        object.__setattr__(self, "factors", factors)
        object.__setattr__(self, "neighborhoods", neighborhoods)
        object.__setattr__(self, "cell_neighborhood_ids", cell_ids)
        object.__setattr__(self, "cell_row_offsets", offsets)
        object.__setattr__(self, "cell_independent_global_rows", rows)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "_audit", _deep_freeze(self._make_audit()))

    def _make_audit(self) -> dict[str, Any]:
        components = {
            "packed_factor_bytes": sum(factor.packed_nbytes for factor in self.factors),
            "neighborhood_metadata_bytes": len(_json_bytes(self.neighborhoods)),
            "cell_neighborhood_mapping_bytes": int(self.cell_neighborhood_ids.nbytes),
            "cell_reference_bytes": int(
                self.cell_row_offsets.nbytes + self.cell_independent_global_rows.nbytes
            ),
            "identity_metadata_bytes": len(_json_bytes(self.identity)),
        }
        retained_total = int(sum(components.values()))
        materialization = {
            "patch_matrices": False,
            "full_dense_factor_count": 0,
            "pivots": False,
            "global_matrix": False,
            "global_constraint_matrix": False,
            "static_condensation": False,
            "trace_slab": False,
            "slab_factor": False,
            "schur": False,
            "ql_qh_transform": False,
            "per_cell_factor": False,
        }
        return {
            "schema": H2B_M3Y_PACKED_STORE_SCHEMA,
            "packed_cholesky": True,
            "packed_factor_count": len(self.factors),
            "neighborhood_count": len(self.neighborhoods),
            "cell_count": int(self.cell_neighborhood_ids.size),
            "packed_factor_bytes": components["packed_factor_bytes"],
            "metadata_mapping_bytes": retained_total
            - components["packed_factor_bytes"],
            "retained_total_bytes": retained_total,
            "retained_total_limit_bytes": H2B_M3Y_RETAINED_BYTES_LIMIT,
            "retained_total_gate": retained_total <= H2B_M3Y_RETAINED_BYTES_LIMIT,
            "retained_payload_components": components,
            "full_dense_factor_count": 0,
            "pivots_retained": False,
            "factorization_info_max": max(
                factor.factorization_info for factor in self.factors
            ),
            "finite": all(factor.finite for factor in self.factors),
            "deterministic": all(factor.deterministic for factor in self.factors),
            "materialization_identity": materialization,
            "ordinary_default_changed": False,
        }

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._audit

    def audit_jsonable(self) -> dict[str, Any]:
        return _jsonable(self._audit)

    def factor_for_cell(self, cell_id: int) -> H2BM3YPackedCholeskyFactor:
        if type(cell_id) is not int or not 0 <= cell_id < self.cell_neighborhood_ids.size:
            raise ValueError("H2B-M3Y cell id is out of range")
        neighborhood_id = int(self.cell_neighborhood_ids[cell_id])
        factor_id = int(self.neighborhoods[neighborhood_id]["factor_id"])
        return self.factors[factor_id]

    def cell_rows(self, cell_id: int) -> np.ndarray:
        if type(cell_id) is not int or not 0 <= cell_id < self.cell_neighborhood_ids.size:
            raise ValueError("H2B-M3Y cell id is out of range")
        start = int(self.cell_row_offsets[cell_id])
        stop = int(self.cell_row_offsets[cell_id + 1])
        return self.cell_independent_global_rows[start:stop]

    def gather(self, full_vector: np.ndarray, cell_id: int) -> np.ndarray:
        values = np.asarray(full_vector)
        rows = self.cell_rows(cell_id)
        if (
            values.dtype != np.dtype(np.complex128)
            or values.ndim != 1
            or not values.flags.c_contiguous
            or np.any(rows >= values.size)
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("H2B-M3Y gather vector is invalid")
        return np.array(values[rows], dtype=np.complex128, order="C", copy=True)

    def solve(self, cell_id: int, right_hand_side: np.ndarray) -> np.ndarray:
        return self.factor_for_cell(cell_id).solve(right_hand_side)


def build_h2b_m3y_packed_patch_store(
    factors: tuple[H2BM3YPackedCholeskyFactor, ...],
    neighborhoods: tuple[Mapping[str, Any], ...],
    cell_neighborhood_ids: np.ndarray,
    cell_row_offsets: np.ndarray,
    cell_independent_global_rows: np.ndarray,
    *,
    identity: Mapping[str, Any],
    task037_extra_h2b: bool = False,
) -> H2BM3YPackedPatchStore:
    _require_opt_in(task037_extra_h2b)
    return H2BM3YPackedPatchStore(
        factors,
        neighborhoods,
        cell_neighborhood_ids,
        cell_row_offsets,
        cell_independent_global_rows,
        identity,
    )


def _write_array(root: Path, relative: str, array: np.ndarray) -> dict[str, Any]:
    values = np.asarray(array)
    if values.dtype == np.dtype(object) or not values.flags.c_contiguous:
        raise ValueError("H2B-M3Y cold array is not C-contiguous numeric data")
    path = root / relative
    np.save(path, values, allow_pickle=False)
    return {
        "path": relative,
        "bytes": int(path.stat().st_size),
        "sha256": _file_sha256(path),
        "array_sha256": _array_sha256(values),
        "dtype": str(values.dtype),
        "shape": [int(value) for value in values.shape],
        "nbytes": int(values.nbytes),
    }


def write_h2b_m3y_packed_patch_store(
    store: H2BM3YPackedPatchStore,
    directory: str | Path,
    *,
    task037_extra_h2b: bool = False,
) -> Path:
    _require_opt_in(task037_extra_h2b)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    factor_metadata: list[dict[str, Any]] = []
    for factor_id, factor in enumerate(store.factors):
        relative = f"factor_{factor_id}_packed.npy"
        files[relative] = _write_array(root, relative, factor.packed_values)
        factor_metadata.append(
            {
                "factor_id": factor_id,
                "n": factor.n,
                "packed_path": relative,
                "packed_length": int(factor.packed_values.size),
                "packed_dtype": str(factor.packed_values.dtype),
                "packed_nbytes": factor.packed_nbytes,
                "packed_array_sha256": _array_sha256(factor.packed_values),
                "matrix_sha256": factor.matrix_sha256,
                "factor_sha256": factor.factor_sha256,
                "factorization_info": factor.factorization_info,
                "finite": factor.finite,
                "deterministic": factor.deterministic,
            }
        )
    cells = {
        "neighborhood_ids_path": "cell_neighborhood_ids.npy",
        "row_offsets_path": "cell_row_offsets.npy",
        "independent_global_rows_path": "cell_independent_global_rows.npy",
    }
    arrays = {
        cells["neighborhood_ids_path"]: store.cell_neighborhood_ids,
        cells["row_offsets_path"]: store.cell_row_offsets,
        cells["independent_global_rows_path"]: store.cell_independent_global_rows,
    }
    for relative, array in arrays.items():
        files[relative] = _write_array(root, relative, array)
    metadata = {
        "identity": _jsonable(store.identity),
        "factor_count": len(store.factors),
        "neighborhood_count": len(store.neighborhoods),
        "cell_count": int(store.cell_neighborhood_ids.size),
        "factors": factor_metadata,
        "cells": cells,
    }
    manifest: dict[str, Any] = {
        "schema": H2B_M3Y_PACKED_STORE_SCHEMA,
        "task037_extra_h2b": True,
        "metadata": metadata,
        "neighborhoods": [_jsonable(item) for item in store.neighborhoods],
        "files": files,
        "payload": {
            "components": store.audit["retained_payload_components"],
            "retained_total_bytes": store.audit["retained_total_bytes"],
            "retained_total_limit_bytes": H2B_M3Y_RETAINED_BYTES_LIMIT,
        },
        "materialization_identity": store.audit["materialization_identity"],
    }
    manifest["evidence_sha256"] = _json_sha256(manifest)
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest) + b"\n")
    return manifest_path


def _validate_file_entry(
    root: Path, files: Mapping[str, Any], relative: Any
) -> tuple[Path, Mapping[str, Any]]:
    if not _valid_relative_path(relative, files) or not isinstance(files[relative], Mapping):
        raise ValueError("H2B-M3Y cold array path is invalid")
    entry = files[relative]
    path = root / relative
    if not path.is_file() or int(entry.get("bytes", -1)) != int(path.stat().st_size):
        raise ValueError("H2B-M3Y cold array file size is invalid")
    if _file_sha256(path) != entry.get("sha256"):
        raise ValueError("H2B-M3Y cold array file SHA mismatch")
    return path, entry


def _load_array(
    root: Path, files: Mapping[str, Any], relative: Any, *, mmap: bool = True
) -> np.ndarray:
    path, entry = _validate_file_entry(root, files, relative)
    loaded = np.load(path, allow_pickle=False, mmap_mode="r" if mmap else None)
    if (
        not isinstance(loaded, np.ndarray)
        or loaded.dtype == np.dtype(object)
        or not loaded.flags.c_contiguous
        or str(loaded.dtype) != entry.get("dtype")
        or list(loaded.shape) != entry.get("shape")
        or int(loaded.nbytes) != int(entry.get("nbytes", -1))
        or _array_sha256(loaded) != entry.get("array_sha256")
    ):
        raise ValueError("H2B-M3Y cold array identity mismatch")
    loaded.setflags(write=False)
    return loaded


def load_h2b_m3y_packed_patch_store(
    manifest_path: str | Path,
    *,
    task037_extra_h2b: bool = False,
) -> H2BM3YPackedPatchStore:
    """Validate a cold store while mmap-loading each retained factor."""

    _require_opt_in(task037_extra_h2b)
    manifest_file = Path(manifest_path)
    manifest = json.loads(
        manifest_file.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value}")
        ),
    )
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != H2B_M3Y_PACKED_STORE_SCHEMA
        or manifest.get("task037_extra_h2b") is not True
        or manifest.get("evidence_sha256") != _json_sha256(
            {key: value for key, value in manifest.items() if key != "evidence_sha256"}
        )
    ):
        raise ValueError("H2B-M3Y manifest schema/evidence is invalid")
    metadata = manifest.get("metadata")
    neighborhoods = manifest.get("neighborhoods")
    files = manifest.get("files")
    payload = manifest.get("payload")
    if not isinstance(metadata, Mapping) or not isinstance(neighborhoods, list) or not isinstance(files, Mapping) or not isinstance(payload, Mapping):
        raise ValueError("H2B-M3Y manifest sections are missing")
    identity = metadata.get("identity")
    factor_metadata = metadata.get("factors")
    cells = metadata.get("cells")
    if not isinstance(identity, Mapping) or not isinstance(factor_metadata, list) or not isinstance(cells, Mapping):
        raise ValueError("H2B-M3Y manifest metadata is incomplete")
    if metadata.get("factor_count") != len(factor_metadata) or metadata.get("neighborhood_count") != len(neighborhoods):
        raise ValueError("H2B-M3Y manifest counts are invalid")
    if len(factor_metadata) > H2B_M3Y_PACKED_FACTOR_LIMIT:
        raise ValueError("H2B-M3Y packed factor count exceeds fixed limit")
    factors: list[H2BM3YPackedCholeskyFactor] = []
    referenced: list[str] = []
    for expected_id, item in enumerate(factor_metadata):
        if not isinstance(item, Mapping) or item.get("factor_id") != expected_id:
            raise ValueError("H2B-M3Y factor metadata is invalid")
        relative = item.get("packed_path")
        if not _valid_relative_path(relative, files):
            raise ValueError("H2B-M3Y packed factor path is invalid")
        packed = _load_array(manifest_file.parent, files, relative)
        factor_order = item.get("n")
        if (
            type(factor_order) is not int
            or factor_order <= 0
            or packed.dtype != np.dtype(np.complex128)
            or packed.ndim != 1
            or packed.size != factor_order * (factor_order + 1) // 2
            or item.get("packed_length") != int(packed.size)
            or item.get("packed_dtype") != str(packed.dtype)
            or item.get("packed_nbytes") != int(packed.nbytes)
            or item.get("packed_array_sha256") != _array_sha256(packed)
            or not _valid_sha(item.get("matrix_sha256"))
            or not _valid_sha(item.get("factor_sha256"))
            or item.get("factor_sha256") != _array_sha256(packed)
            or item.get("factorization_info") != 0
            or item.get("finite") is not True
            or item.get("deterministic") is not True
        ):
            raise ValueError("H2B-M3 packed factor identity is invalid")
        factors.append(
            H2BM3YPackedCholeskyFactor(
                packed,
                factor_order,
                matrix_sha256=item["matrix_sha256"],
                factor_sha256=item["factor_sha256"],
                factorization_info=0,
                finite=True,
                deterministic=True,
            )
        )
        referenced.append(relative)
    cell_paths = (
        cells.get("neighborhood_ids_path"),
        cells.get("row_offsets_path"),
        cells.get("independent_global_rows_path"),
    )
    if any(not _valid_relative_path(relative, files) for relative in cell_paths):
        raise ValueError("H2B-M3Y cell array paths are invalid")
    cell_ids = _load_array(manifest_file.parent, files, cell_paths[0])
    offsets = _load_array(manifest_file.parent, files, cell_paths[1])
    rows = _load_array(manifest_file.parent, files, cell_paths[2])
    referenced.extend(cell_paths)
    if set(referenced) != set(files) or len(referenced) != len(set(referenced)):
        raise ValueError("H2B-M3Y file inventory is not closed")
    store = H2BM3YPackedPatchStore(
        tuple(factors),
        tuple(neighborhoods),
        cell_ids,
        offsets,
        rows,
        identity,
    )
    if (
        metadata.get("cell_count") != store.cell_neighborhood_ids.size
        or payload.get("components") != store.audit["retained_payload_components"]
        or payload.get("retained_total_bytes") != store.audit["retained_total_bytes"]
        or manifest.get("materialization_identity") != store.audit["materialization_identity"]
    ):
        raise ValueError("H2B-M3Y retained payload audit mismatch")
    return store
