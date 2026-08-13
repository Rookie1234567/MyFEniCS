"""Research-only cold storage for the fixed ``beta=1`` M6B patch operator.

The shifted local operator is complex and generally non-Hermitian.  It is
therefore stored as a SciPy/LAPACK ``zgetrf`` LU factor with int32 pivots,
not as the packed Cholesky representation used by M3Y.  Factors are written
one file at a time by the builder and loaded read-only through ``np.memmap``.
No source patch matrix, global matrix, Schur complement, or per-cell factor is
retained here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
from scipy.linalg import lapack

__all__ = (
    "M6B_SHIFTED_LU_STORE_SCHEMA",
    "M6B_SHIFTED_BETA",
    "M6B_SHIFTED_FACTOR_COUNT",
    "M6B_SHIFTED_CELL_COUNT",
    "M6B_SHIFTED_NLOC",
    "M6B_SHIFTED_FACTOR_PAYLOAD_BYTES",
    "M6B_SHIFTED_RETAINED_LIMIT_BYTES",
    "H2BM6BShiftedLUFactor",
    "H2BM6BShiftedLUPatchStore",
    "build_h2b_m6b_shifted_lu_factor",
    "build_h2b_m6b_shifted_lu_patch_store",
    "write_h2b_m6b_shifted_lu_patch_store",
    "stream_write_h2b_m6b_shifted_lu_patch_store",
    "load_h2b_m6b_shifted_lu_patch_store",
    "shifted_lu_factor_nbytes",
)


M6B_SHIFTED_LU_STORE_SCHEMA = "task037.extra.h2b.m6b.shifted-lu-store.v1"
M6B_SHIFTED_BETA = 1.0
M6B_SHIFTED_FACTOR_COUNT = 84
M6B_SHIFTED_CELL_COUNT = 252
M6B_SHIFTED_NLOC = 882
M6B_SHIFTED_RETAINED_LIMIT_BYTES = 1_100_000_000
_COMPLEX128_BYTES = np.dtype(np.complex128).itemsize
_SHA_HEX = frozenset("0123456789abcdef")


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        if value.dtype == np.dtype(object):
            raise TypeError("M6B identity cannot contain object arrays")
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


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _factor_sha256(lu: np.ndarray, pivots: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(memoryview(np.ascontiguousarray(lu)).cast("B"))
    digest.update(memoryview(np.ascontiguousarray(pivots)).cast("B"))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and set(value) <= _SHA_HEX
    )


def _valid_relative_path(relative: Any, files: Mapping[str, Any]) -> bool:
    if not isinstance(relative, str):
        return False
    path = Path(relative)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and relative in files
    )


def shifted_lu_factor_nbytes(n: int) -> int:
    """Bytes for one complex128 square LU and one int32 pivot vector."""

    if type(n) is not int or n <= 0:
        raise ValueError("M6B LU order is invalid")
    return n * n * _COMPLEX128_BYTES + n * np.dtype(np.int32).itemsize


M6B_SHIFTED_FACTOR_PAYLOAD_BYTES = (
    M6B_SHIFTED_FACTOR_COUNT * shifted_lu_factor_nbytes(M6B_SHIFTED_NLOC)
)


@dataclass(frozen=True)
class H2BM6BShiftedLUFactor:
    """One immutable ``zgetrf`` factor with its int32 pivot vector."""

    lu: np.ndarray
    pivots: np.ndarray
    n: int
    beta: float = M6B_SHIFTED_BETA
    matrix_sha256: str | None = None
    factor_sha256: str | None = None
    factorization_info: int = 0

    def __post_init__(self) -> None:
        lu = np.asarray(self.lu)
        pivots = np.asarray(self.pivots)
        if (
            type(self.n) is not int
            or self.n <= 0
            or lu.dtype != np.dtype(np.complex128)
            or lu.ndim != 2
            or lu.shape != (self.n, self.n)
            or not lu.flags.c_contiguous
            or not np.all(np.isfinite(lu))
            or pivots.dtype != np.dtype(np.int32)
            or pivots.ndim != 1
            or pivots.size != self.n
            or not pivots.flags.c_contiguous
            or np.any(pivots < 0)
            or np.any(pivots >= self.n)
        ):
            raise ValueError("M6B shifted LU factor arrays are invalid")
        if float(self.beta) != M6B_SHIFTED_BETA:
            raise ValueError("M6B shifted factor beta is not the fixed beta=1")
        if not _valid_sha(self.matrix_sha256):
            raise ValueError("M6B source matrix SHA is invalid")
        if type(self.factorization_info) is not int or self.factorization_info != 0:
            raise ValueError("M6B zgetrf info must be exactly zero")
        digest = _factor_sha256(lu, pivots)
        if self.factor_sha256 is not None and self.factor_sha256 != digest:
            raise ValueError("M6B shifted LU factor SHA mismatch")
        lu.setflags(write=False)
        pivots.setflags(write=False)
        object.__setattr__(self, "lu", lu)
        object.__setattr__(self, "pivots", pivots)
        object.__setattr__(self, "factor_sha256", digest)

    @property
    def factor_nbytes(self) -> int:
        return int(self.lu.nbytes + self.pivots.nbytes)

    @property
    def mmap_loaded(self) -> bool:
        return isinstance(self.lu.base, np.memmap) and isinstance(
            self.pivots.base, np.memmap
        )

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        rhs = np.asarray(right_hand_side)
        if (
            rhs.dtype != np.dtype(np.complex128)
            or rhs.ndim not in (1, 2)
            or rhs.shape[0] != self.n
            or not np.all(np.isfinite(rhs))
        ):
            raise ValueError("M6B shifted LU RHS is invalid")
        vector = rhs.ndim == 1
        work = np.array(
            rhs[:, None] if vector else rhs,
            dtype=np.complex128,
            order="F",
            copy=True,
        )
        # SciPy's zgetrs wrapper may pass a read-only memmap through to a
        # writable Fortran work argument and segfault.  Copy only the one
        # factor being solved; the cold store retains the mmap and never a
        # second factor.  The caller's bounded workspace audit accounts for
        # this transient LU copy.
        lu_work = np.array(self.lu, dtype=np.complex128, order="F", copy=True)
        pivot_work = np.array(self.pivots, dtype=np.int32, order="C", copy=True)
        getrs = lapack.get_lapack_funcs(("getrs",), (lu_work,))[0]
        solution, info = getrs(
            lu_work,
            pivot_work,
            work,
            trans=0,
            overwrite_b=1,
        )
        del lu_work
        del pivot_work
        if int(info) != 0:
            raise np.linalg.LinAlgError(f"zgetrs failed with info={int(info)}")
        result = np.asarray(solution)
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("M6B shifted LU solve returned nonfinite values")
        return np.array(
            result[:, 0] if vector else result,
            dtype=np.complex128,
            order="C",
            copy=True,
        )

    def audit_jsonable(self) -> dict[str, Any]:
        return {
            "n": int(self.n),
            "beta": float(self.beta),
            "lu_shape": [int(self.n), int(self.n)],
            "lu_dtype": str(self.lu.dtype),
            "pivot_shape": [int(self.n)],
            "pivot_dtype": str(self.pivots.dtype),
            "factor_nbytes": self.factor_nbytes,
            "matrix_sha256": self.matrix_sha256,
            "factor_sha256": self.factor_sha256,
            "factorization_info": int(self.factorization_info),
            "finite": True,
            "full_dense_patch_matrix_retained": False,
            "pivots_retained": True,
            "mmap_loaded": self.mmap_loaded,
        }


def build_h2b_m6b_shifted_lu_factor(
    matrix: np.ndarray,
    *,
    beta: float = M6B_SHIFTED_BETA,
    matrix_sha256: str | None = None,
    task037_extra_m6b: bool = False,
) -> H2BM6BShiftedLUFactor:
    """Factor one exact row-complete shifted patch with SciPy ``zgetrf``."""

    if task037_extra_m6b is not True:
        raise ValueError("M6B shifted LU requires explicit research opt-in")
    values = np.asarray(matrix)
    if (
        values.dtype != np.dtype(np.complex128)
        or values.ndim != 2
        or values.shape[0] != values.shape[1]
        or not values.flags.c_contiguous
        or not np.all(np.isfinite(values))
    ):
        raise ValueError("M6B shifted patch matrix is invalid")
    observed_matrix_sha = _array_sha256(values)
    if matrix_sha256 is not None and matrix_sha256 != observed_matrix_sha:
        raise ValueError("M6B shifted matrix SHA does not match matrix bytes")
    getrf = lapack.get_lapack_funcs(("getrf",), (values,))[0]
    factor_values, pivots, info = getrf(
        np.array(values, dtype=np.complex128, order="C", copy=True),
        overwrite_a=1,
    )
    if int(info) != 0:
        raise np.linalg.LinAlgError(f"zgetrf failed with info={int(info)}")
    return H2BM6BShiftedLUFactor(
        np.asarray(factor_values, dtype=np.complex128, order="C"),
        np.asarray(pivots, dtype=np.int32, order="C"),
        int(values.shape[0]),
        beta=float(beta),
        matrix_sha256=observed_matrix_sha,
        factorization_info=int(info),
    )


def _validate_mapping(
    neighborhoods: tuple[Mapping[str, Any], ...],
    cell_ids: np.ndarray,
    offsets: np.ndarray,
    rows: np.ndarray,
    factor_count: int,
    factor_orders: tuple[int, ...],
) -> None:
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
        raise ValueError("M6B cell mapping arrays do not close")
    members: list[list[int]] = [[] for _ in neighborhoods]
    for cell_id, neighborhood_id in enumerate(cell_ids.tolist()):
        start, stop = int(offsets[cell_id]), int(offsets[cell_id + 1])
        if np.unique(rows[start:stop]).size != stop - start:
            raise ValueError("M6B cell rows are not unique")
        record = neighborhoods[int(neighborhood_id)]
        factor_id = record.get("factor_id")
        if type(factor_id) is not int or not 0 <= factor_id < factor_count:
            raise ValueError("M6B cell factor mapping is invalid")
        if stop - start != factor_orders[factor_id]:
            raise ValueError("M6B cell rows do not match LU order")
        members[int(neighborhood_id)].append(cell_id)
    for expected_id, record in enumerate(neighborhoods):
        if (
            not isinstance(record, Mapping)
            or record.get("neighborhood_id") != expected_id
            or not _valid_sha(record.get("key_sha256"))
            or type(record.get("factor_id")) is not int
            or not isinstance(record.get("cell_ordinals"), (list, tuple))
            or tuple(members[expected_id]) != tuple(record["cell_ordinals"])
            or record.get("multiplicity") != len(record["cell_ordinals"])
        ):
            raise ValueError("M6B neighborhood mapping is invalid")


@dataclass(frozen=True)
class H2BM6BShiftedLUPatchStore:
    """Read-only LU factors shared by deterministic cell row mappings."""

    factors: tuple[H2BM6BShiftedLUFactor, ...]
    neighborhoods: tuple[Mapping[str, Any], ...]
    cell_neighborhood_ids: np.ndarray
    cell_row_offsets: np.ndarray
    cell_independent_global_rows: np.ndarray
    identity: Mapping[str, Any]

    def __post_init__(self) -> None:
        factors = tuple(self.factors)
        neighborhoods = tuple(dict(item) for item in self.neighborhoods)
        if not factors or not neighborhoods:
            raise ValueError("M6B shifted store needs factors and neighborhoods")
        orders = tuple(factor.n for factor in factors)
        if len({factor.beta for factor in factors}) != 1:
            raise ValueError("M6B shifted factors have inconsistent beta")
        cell_ids = np.asarray(self.cell_neighborhood_ids)
        offsets = np.asarray(self.cell_row_offsets)
        rows = np.asarray(self.cell_independent_global_rows)
        if cell_ids.dtype != np.dtype(np.int32):
            cell_ids = np.array(cell_ids, dtype=np.int32, order="C", copy=True)
        if offsets.dtype != np.dtype(np.int64):
            offsets = np.array(offsets, dtype=np.int64, order="C", copy=True)
        if rows.dtype != np.dtype(np.int64):
            rows = np.array(rows, dtype=np.int64, order="C", copy=True)
        if not cell_ids.flags.c_contiguous or cell_ids.flags.writeable:
            cell_ids = np.array(cell_ids, dtype=np.int32, order="C", copy=True)
        if not offsets.flags.c_contiguous or offsets.flags.writeable:
            offsets = np.array(offsets, dtype=np.int64, order="C", copy=True)
        if not rows.flags.c_contiguous or rows.flags.writeable:
            rows = np.array(rows, dtype=np.int64, order="C", copy=True)
        _validate_mapping(neighborhoods, cell_ids, offsets, rows, len(factors), orders)
        identity = dict(self.identity)
        cell_ids.setflags(write=False)
        offsets.setflags(write=False)
        rows.setflags(write=False)
        object.__setattr__(self, "factors", factors)
        object.__setattr__(self, "neighborhoods", tuple(neighborhoods))
        object.__setattr__(self, "cell_neighborhood_ids", cell_ids)
        object.__setattr__(self, "cell_row_offsets", offsets)
        object.__setattr__(self, "cell_independent_global_rows", rows)
        object.__setattr__(self, "identity", MappingProxyType(identity))
        object.__setattr__(self, "_audit", MappingProxyType(self._make_audit()))

    def _make_audit(self) -> dict[str, Any]:
        factor_lu_bytes = int(sum(factor.lu.nbytes for factor in self.factors))
        factor_pivot_bytes = int(sum(factor.pivots.nbytes for factor in self.factors))
        components = {
            "factor_lu_bytes": factor_lu_bytes,
            "factor_pivot_bytes": factor_pivot_bytes,
            "neighborhood_metadata_bytes": len(_json_bytes(self.neighborhoods)),
            "cell_mapping_bytes": int(
                self.cell_neighborhood_ids.nbytes
                + self.cell_row_offsets.nbytes
                + self.cell_independent_global_rows.nbytes
            ),
            "identity_metadata_bytes": len(_json_bytes(self.identity)),
        }
        retained = int(sum(components.values()))
        materialization = {
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab": False,
            "schur": False,
            "slab_factor": False,
        }
        cell_count = int(self.cell_neighborhood_ids.size)
        return {
            "schema": M6B_SHIFTED_LU_STORE_SCHEMA,
            "beta": float(self.factors[0].beta),
            "factor_order": int(self.factors[0].n),
            "factor_count": len(self.factors),
            "neighborhood_count": len(self.neighborhoods),
            "cell_count": cell_count,
            "factor_lu_bytes": factor_lu_bytes,
            "factor_pivot_bytes": factor_pivot_bytes,
            "factor_payload_bytes": factor_lu_bytes + factor_pivot_bytes,
            "max_transient_solve_factor_bytes": max(
                factor.factor_nbytes for factor in self.factors
            ),
            "metadata_mapping_bytes": retained - factor_lu_bytes - factor_pivot_bytes,
            "retained_total_bytes": retained,
            "retained_total_limit_bytes": M6B_SHIFTED_RETAINED_LIMIT_BYTES,
            "retained_total_gate": retained <= M6B_SHIFTED_RETAINED_LIMIT_BYTES,
            "retained_payload_components": components,
            "factor_reuse_count": cell_count - len(self.factors),
            "factor_copy_count": 0,
            "full_dense_patch_matrix_retained": False,
            "pivots_retained": True,
            "mmap_readonly": all(
                not factor.lu.flags.writeable
                and not factor.pivots.flags.writeable
                for factor in self.factors
            ),
            "mmap_loaded": all(factor.mmap_loaded for factor in self.factors),
            "factorization_info_max": max(
                factor.factorization_info for factor in self.factors
            ),
            "finite": all(
                np.all(np.isfinite(factor.lu))
                and np.all(np.isfinite(factor.pivots))
                for factor in self.factors
            ),
            "deterministic": None,
            "determinism_evidence": "factor_sha256_bound; repeat measured by builder/PC",
            "max_live_patch_matrix_count": 1,
            "max_live_lu_factor_count": 1,
            "materialization_identity": materialization,
            "ordinary_default_changed": False,
        }

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._audit

    def audit_jsonable(self) -> dict[str, Any]:
        return _jsonable(dict(self._audit))

    def factor_for_cell(self, cell_id: int) -> H2BM6BShiftedLUFactor:
        if type(cell_id) is not int or not 0 <= cell_id < self.cell_neighborhood_ids.size:
            raise ValueError("M6B cell id is out of range")
        neighborhood_id = int(self.cell_neighborhood_ids[cell_id])
        factor_id = int(self.neighborhoods[neighborhood_id]["factor_id"])
        return self.factors[factor_id]

    def cell_rows(self, cell_id: int) -> np.ndarray:
        if type(cell_id) is not int or not 0 <= cell_id < self.cell_neighborhood_ids.size:
            raise ValueError("M6B cell id is out of range")
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
            raise ValueError("M6B gather vector is invalid")
        return np.array(values[rows], dtype=np.complex128, order="C", copy=True)

    def solve(self, cell_id: int, right_hand_side: np.ndarray) -> np.ndarray:
        return self.factor_for_cell(cell_id).solve(right_hand_side)


def build_h2b_m6b_shifted_lu_patch_store(
    factors: tuple[H2BM6BShiftedLUFactor, ...],
    neighborhoods: tuple[Mapping[str, Any], ...],
    cell_neighborhood_ids: np.ndarray,
    cell_row_offsets: np.ndarray,
    cell_independent_global_rows: np.ndarray,
    *,
    identity: Mapping[str, Any],
    task037_extra_m6b: bool = False,
) -> H2BM6BShiftedLUPatchStore:
    if task037_extra_m6b is not True:
        raise ValueError("M6B shifted store requires explicit research opt-in")
    return H2BM6BShiftedLUPatchStore(
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
        raise ValueError("M6B cold array is not C-contiguous numeric data")
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


def write_h2b_m6b_shifted_lu_patch_store(
    store: H2BM6BShiftedLUPatchStore,
    directory: str | Path,
    *,
    task037_extra_m6b: bool = False,
) -> Path:
    if task037_extra_m6b is not True:
        raise ValueError("M6B shifted store requires explicit research opt-in")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    factors: list[dict[str, Any]] = []
    for factor_id, factor in enumerate(store.factors):
        lu_path = f"factor_{factor_id}_lu.npy"
        pivot_path = f"factor_{factor_id}_pivots.npy"
        files[lu_path] = _write_array(root, lu_path, factor.lu)
        files[pivot_path] = _write_array(root, pivot_path, factor.pivots)
        factors.append(
            {
                "factor_id": factor_id,
                "n": int(factor.n),
                "beta": float(factor.beta),
                "lu_path": lu_path,
                "pivot_path": pivot_path,
                "matrix_sha256": factor.matrix_sha256,
                "factor_sha256": factor.factor_sha256,
                "factorization_info": int(factor.factorization_info),
                "factor_nbytes": factor.factor_nbytes,
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
    manifest: dict[str, Any] = {
        "schema": M6B_SHIFTED_LU_STORE_SCHEMA,
        "task037_extra_m6b": True,
        "beta": M6B_SHIFTED_BETA,
        "identity": _jsonable(store.identity),
        "factors": factors,
        "neighborhoods": [_jsonable(item) for item in store.neighborhoods],
        "cells": cells,
        "files": files,
        "audit": store.audit_jsonable(),
        "materialization_identity": store.audit["materialization_identity"],
    }
    manifest["evidence_sha256"] = _json_sha256(manifest)
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest) + b"\n")
    return manifest_path


def stream_write_h2b_m6b_shifted_lu_patch_store(
    matrix_records: Any,
    directory: str | Path,
    cell_neighborhood_ids: np.ndarray,
    cell_row_offsets: np.ndarray,
    cell_independent_global_rows: np.ndarray,
    *,
    neighborhoods: Any,
    identity: Mapping[str, Any],
    expected_factor_count: int | None = None,
    expected_neighborhood_count: int | None = None,
    task037_extra_m6b: bool = False,
) -> Path:
    """Write one streamed row-complete matrix at a time.

    ``matrix_records`` yields ``(neighborhood_record, matrix)``.  Only the
    current dense patch and its current LU factor are live; the manifest keeps
    compact factor/mapping metadata and the loader later opens the numeric
    arrays read-only through mmap.
    """

    if task037_extra_m6b is not True:
        raise ValueError("M6B shifted store requires explicit research opt-in")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    records = tuple(dict(item) for item in neighborhoods)
    if expected_neighborhood_count is not None and len(records) != int(expected_neighborhood_count):
        raise ValueError("M6B shifted neighborhood count is not the fixed authority")
    cell_ids = np.ascontiguousarray(np.asarray(cell_neighborhood_ids, dtype=np.int32))
    offsets = np.ascontiguousarray(np.asarray(cell_row_offsets, dtype=np.int64))
    rows = np.ascontiguousarray(np.asarray(cell_independent_global_rows, dtype=np.int64))
    files: dict[str, dict[str, Any]] = {}
    factor_records: list[dict[str, Any]] = []
    observed_records: list[dict[str, Any]] = []
    max_live_patch_matrix_count = 0
    max_live_lu_factor_count = 0

    for neighborhood_record, matrix in matrix_records:
        record = dict(neighborhood_record)
        neighborhood_id = record.get("neighborhood_id")
        if type(neighborhood_id) is not int or not 0 <= neighborhood_id < len(records):
            raise ValueError("M6B streamed neighborhood id is invalid")
        values = np.asarray(matrix)
        if (
            values.dtype != np.dtype(np.complex128)
            or values.ndim != 2
            or values.shape != (values.shape[0], values.shape[0])
            or not values.flags.c_contiguous
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("M6B streamed shifted patch matrix is invalid")
        if values.shape[0] != M6B_SHIFTED_NLOC:
            raise ValueError("M6B streamed shifted patch order is not 882")
        max_live_patch_matrix_count = max(max_live_patch_matrix_count, 1)
        matrix_sha = _array_sha256(values)
        expected_matrix_sha = record.get("expected_matrix_sha256")
        if expected_matrix_sha is not None and expected_matrix_sha != matrix_sha:
            raise ValueError("M6B streamed matrix SHA does not match repeat authority")
        factor = build_h2b_m6b_shifted_lu_factor(
            values,
            matrix_sha256=matrix_sha,
            task037_extra_m6b=True,
        )
        factor_id = len(factor_records)
        max_live_lu_factor_count = max(max_live_lu_factor_count, 1)
        lu_path = f"factor_{factor_id}_lu.npy"
        pivot_path = f"factor_{factor_id}_pivots.npy"
        files[lu_path] = _write_array(root, lu_path, factor.lu)
        files[pivot_path] = _write_array(root, pivot_path, factor.pivots)
        factor_records.append(
            {
                "factor_id": factor_id,
                "n": int(factor.n),
                "beta": float(factor.beta),
                "lu_path": lu_path,
                "pivot_path": pivot_path,
                "matrix_sha256": matrix_sha,
                "factor_sha256": factor.factor_sha256,
                "factorization_info": int(factor.factorization_info),
                "factor_nbytes": factor.factor_nbytes,
            }
        )
        factor_sha = factor.factor_sha256
        del factor
        expected_factor_sha = record.get("expected_factor_sha256")
        if expected_factor_sha is not None and expected_factor_sha != factor_sha:
            raise ValueError("M6B streamed factor SHA does not match repeat authority")
        repeat_factor_sha = record.get("repeat_factor_sha256")
        if repeat_factor_sha is not None and repeat_factor_sha != expected_factor_sha:
            raise ValueError("M6B repeat factor SHA binding is inconsistent")
        record["factor_id"] = int(factor_id)
        record["matrix_sha256"] = matrix_sha
        record["factor_sha256"] = factor_sha
        observed_records.append(record)
        del values, matrix

    if expected_factor_count is not None and len(factor_records) != int(expected_factor_count):
        raise ValueError("M6B streamed factor count is not the fixed authority")
    if len(observed_records) != len(records):
        raise ValueError("M6B streamed neighborhood records are incomplete")
    observed_records.sort(key=lambda item: int(item["neighborhood_id"]))
    if [item.get("neighborhood_id") for item in observed_records] != list(range(len(records))):
        raise ValueError("M6B streamed neighborhood order is not contiguous")
    if tuple(item.get("key_sha256") for item in observed_records) != tuple(
        item.get("key_sha256") for item in records
    ):
        raise ValueError("M6B streamed neighborhood identity changed")
    cells = {
        "neighborhood_ids_path": "cell_neighborhood_ids.npy",
        "row_offsets_path": "cell_row_offsets.npy",
        "independent_global_rows_path": "cell_independent_global_rows.npy",
    }
    for relative, array in (
        (cells["neighborhood_ids_path"], cell_ids),
        (cells["row_offsets_path"], offsets),
        (cells["independent_global_rows_path"], rows),
    ):
        files[relative] = _write_array(root, relative, array)
    if offsets.size != cell_ids.size + 1 or int(offsets[-1]) != rows.size:
        raise ValueError("M6B streamed cell mapping does not close")
    factor_lu_bytes = int(sum(int(item["factor_nbytes"]) - M6B_SHIFTED_NLOC * 4 for item in factor_records))
    factor_pivot_bytes = int(sum(M6B_SHIFTED_NLOC * 4 for _item in factor_records))
    materialization = {
        "global_matrix": False,
        "global_constraint_matrix": False,
        "patch_matrices": False,
        "per_cell_factor": False,
        "static_condensation": False,
        "trace_slab": False,
        "schur": False,
        "slab_factor": False,
    }
    components = {
        "factor_lu_bytes": factor_lu_bytes,
        "factor_pivot_bytes": factor_pivot_bytes,
        "neighborhood_metadata_bytes": len(_json_bytes(tuple(observed_records))),
        "cell_mapping_bytes": int(cell_ids.nbytes + offsets.nbytes + rows.nbytes),
        "identity_metadata_bytes": len(_json_bytes(identity)),
    }
    audit = {
        "schema": M6B_SHIFTED_LU_STORE_SCHEMA,
        "beta": M6B_SHIFTED_BETA,
        "factor_order": M6B_SHIFTED_NLOC,
        "factor_count": len(factor_records),
        "neighborhood_count": len(observed_records),
        "cell_count": int(cell_ids.size),
        "factor_lu_bytes": factor_lu_bytes,
        "factor_pivot_bytes": factor_pivot_bytes,
        "factor_payload_bytes": factor_lu_bytes + factor_pivot_bytes,
        "max_transient_solve_factor_bytes": shifted_lu_factor_nbytes(M6B_SHIFTED_NLOC),
        "metadata_mapping_bytes": int(sum(components.values()) - factor_lu_bytes - factor_pivot_bytes),
        "retained_total_bytes": int(sum(components.values())),
        "retained_total_limit_bytes": M6B_SHIFTED_RETAINED_LIMIT_BYTES,
        "retained_total_gate": int(sum(components.values())) <= M6B_SHIFTED_RETAINED_LIMIT_BYTES,
        "retained_payload_components": components,
        "factor_reuse_count": int(cell_ids.size - len(factor_records)),
        "factor_copy_count": 0,
        "full_dense_patch_matrix_retained": False,
        "pivots_retained": True,
        "mmap_readonly": False,
        "mmap_loaded": False,
        "factorization_info_max": 0,
        "finite": True,
        "deterministic": None,
        "determinism_evidence": "factor_sha256_bound; repeat measured by builder/PC",
        "max_live_patch_matrix_count": max_live_patch_matrix_count,
        "max_live_lu_factor_count": max_live_lu_factor_count,
        "materialization_identity": materialization,
        "ordinary_default_changed": False,
    }
    manifest: dict[str, Any] = {
        "schema": M6B_SHIFTED_LU_STORE_SCHEMA,
        "task037_extra_m6b": True,
        "beta": M6B_SHIFTED_BETA,
        "identity": _jsonable(identity),
        "factors": factor_records,
        "neighborhoods": [_jsonable(item) for item in observed_records],
        "cells": cells,
        "files": files,
        "audit": audit,
        "materialization_identity": materialization,
    }
    manifest["evidence_sha256"] = _json_sha256(manifest)
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest) + b"\n")
    return manifest_path


def _validate_file(
    root: Path, files: Mapping[str, Any], relative: Any
) -> tuple[Path, Mapping[str, Any]]:
    if not _valid_relative_path(relative, files) or not isinstance(files[relative], Mapping):
        raise ValueError("M6B cold file path is invalid")
    entry = files[relative]
    path = root / relative
    if not path.is_file() or int(entry.get("bytes", -1)) != int(path.stat().st_size):
        raise ValueError("M6B cold file size is invalid")
    if _file_sha256(path) != entry.get("sha256"):
        raise ValueError("M6B cold file SHA mismatch")
    return path, entry


def _load_array(
    root: Path, files: Mapping[str, Any], relative: Any, *, mmap: bool = True
) -> np.ndarray:
    path, entry = _validate_file(root, files, relative)
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
        raise ValueError("M6B cold array identity mismatch")
    loaded.setflags(write=False)
    return loaded


def load_h2b_m6b_shifted_lu_patch_store(
    manifest_path: str | Path,
    *,
    task037_extra_m6b: bool = False,
) -> H2BM6BShiftedLUPatchStore:
    if task037_extra_m6b is not True:
        raise ValueError("M6B shifted store requires explicit research opt-in")
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != M6B_SHIFTED_LU_STORE_SCHEMA
        or manifest.get("task037_extra_m6b") is not True
        or manifest.get("beta") != M6B_SHIFTED_BETA
        or manifest.get("evidence_sha256")
        != _json_sha256(
            {
                key: value
                for key, value in manifest.items()
                if key != "evidence_sha256"
            }
        )
    ):
        raise ValueError("M6B shifted manifest schema/evidence is invalid")
    root = manifest_file.parent
    files = manifest.get("files")
    factor_records = manifest.get("factors")
    neighborhoods = manifest.get("neighborhoods")
    cells = manifest.get("cells")
    identity = manifest.get("identity")
    if (
        not isinstance(files, Mapping)
        or not isinstance(factor_records, list)
        or not isinstance(neighborhoods, list)
        or not isinstance(cells, Mapping)
        or not isinstance(identity, Mapping)
    ):
        raise ValueError("M6B shifted manifest sections are incomplete")
    factors: list[H2BM6BShiftedLUFactor] = []
    referenced: list[str] = []
    for expected_id, record in enumerate(factor_records):
        if not isinstance(record, Mapping) or record.get("factor_id") != expected_id:
            raise ValueError("M6B shifted factor metadata is invalid")
        lu = _load_array(root, files, record.get("lu_path"))
        pivots = _load_array(root, files, record.get("pivot_path"))
        n = record.get("n")
        if (
            type(n) is not int
            or n <= 0
            or record.get("beta") != M6B_SHIFTED_BETA
            or lu.shape != (n, n)
            or lu.dtype != np.dtype(np.complex128)
            or pivots.shape != (n,)
            or pivots.dtype != np.dtype(np.int32)
            or record.get("factor_nbytes") != int(lu.nbytes + pivots.nbytes)
            or not _valid_sha(record.get("matrix_sha256"))
            or not _valid_sha(record.get("factor_sha256"))
            or record.get("factorization_info") != 0
            or record["factor_sha256"] != _factor_sha256(lu, pivots)
        ):
            raise ValueError("M6B shifted factor identity is invalid")
        factors.append(
            H2BM6BShiftedLUFactor(
                lu,
                pivots,
                n,
                beta=M6B_SHIFTED_BETA,
                matrix_sha256=record["matrix_sha256"],
                factor_sha256=record["factor_sha256"],
                factorization_info=0,
            )
        )
        referenced.extend([record["lu_path"], record["pivot_path"]])
    cell_paths = (
        cells.get("neighborhood_ids_path"),
        cells.get("row_offsets_path"),
        cells.get("independent_global_rows_path"),
    )
    if any(not _valid_relative_path(path, files) for path in cell_paths):
        raise ValueError("M6B shifted cell array paths are invalid")
    cell_ids = _load_array(root, files, cell_paths[0])
    offsets = _load_array(root, files, cell_paths[1])
    rows = _load_array(root, files, cell_paths[2])
    if (
        cell_ids.dtype != np.dtype(np.int32)
        or offsets.dtype != np.dtype(np.int64)
        or rows.dtype != np.dtype(np.int64)
    ):
        raise ValueError("M6B shifted cell array dtypes are invalid")
    referenced.extend(cell_paths)
    if set(referenced) != set(files) or len(referenced) != len(set(referenced)):
        raise ValueError("M6B shifted file inventory is not closed")
    store = H2BM6BShiftedLUPatchStore(
        tuple(factors),
        tuple(neighborhoods),
        cell_ids,
        offsets,
        rows,
        identity,
    )
    expected_audit = dict(manifest.get("audit", {}))
    observed_audit = store.audit_jsonable()
    expected_audit["mmap_loaded"] = observed_audit["mmap_loaded"]
    expected_audit["mmap_readonly"] = observed_audit["mmap_readonly"]
    if expected_audit != observed_audit or manifest.get("materialization_identity") != store.audit[
        "materialization_identity"
    ]:
        raise ValueError("M6B shifted retained audit mismatch")
    return store
