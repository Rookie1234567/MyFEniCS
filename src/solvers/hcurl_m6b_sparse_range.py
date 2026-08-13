"""Sparse least-squares range carrier for the fixed 75D W1 diagnostic.

The persistent carrier stores only owner-local CSC columns of ``Z`` and the
75-by-75 upper Cholesky factor ``R`` of ``(A Z)^H (A Z)``.  The forward
``A Z`` columns are builder-only transient data.  Applying the carrier uses
the explicit ``A^H`` action to form ``Z^H A^H r`` and returns only ``Z c``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import solve_triangular
from mpi4py import MPI

__all__ = (
    "M6B_W1_RANGE_STORE_SCHEMA",
    "M6B_W1_RANGE_COLUMNS",
    "M6B_W1_NORMAL_CLOSURE_LIMIT",
    "M6B_W1_W0_BASIS_MANIFEST_SHA256",
    "M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE",
    "M6B_W1_W0_ORACLE_OUTPUT_SHA256",
    "M6B_W1_W0_RESIDUAL_SOURCE_SHA",
    "M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA",
    "basis_manifest_from_vectors",
    "validate_w0_authority",
    "SparseM6BRangeCarrier",
    "load_sparse_m6b_range_carrier",
)


M6B_W1_RANGE_STORE_SCHEMA = "task037.extra.m6b.sparse-range-store.v2"
M6B_W1_RANGE_COLUMNS = 75
M6B_W1_NORMAL_CLOSURE_LIMIT = 1.0e-11
M6B_W1_W0_BASIS_MANIFEST_SHA256 = (
    "ce3e38f7fa8be3dc704163d744eee8cecc3265b5872664d893b990c2845b765c"
)
M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE = (
    "4eaee22f49fcac7546e93fdc59237949579e93c20af604eefd396c4f7fedccce"
)
M6B_W1_W0_ORACLE_OUTPUT_SHA256 = (
    "acef3e163057fb60db50e9362d9303a8275555a93027258bfbbbc4b001ff3568"
)
M6B_W1_W0_RESIDUAL_SOURCE_SHA = "d98254fecddc41940f50f72753ec9f0f80407793"
M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA = (
    "5e7f9d42eaf994440655fde9f79eb85e2f2745b9"
)
_COMPLEX128 = np.dtype(np.complex128)
_INDEX_DTYPE = np.dtype(np.int32)
_RANK_THRESHOLD_FACTOR = 128.0
_ARRAY_NAMES = (
    "z_data",
    "z_indices",
    "z_indptr",
    "r_factor",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
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
    digest = hashlib.sha256()
    digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
    digest.update(str(array.dtype).encode("utf-8"))
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_meta(path: Path, value: np.ndarray) -> dict[str, Any]:
    return {
        "path": path.name,
        "bytes": int(path.stat().st_size),
        "nbytes": int(value.nbytes),
        "shape": [int(item) for item in value.shape],
        "dtype": str(value.dtype),
        "array_sha256": _array_sha256(value),
        "file_sha256": _file_sha256(path),
    }


def _validate_identity(
    identity: Mapping[str, Any], basis_manifest: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    _require(isinstance(identity, Mapping), "W1 carrier identity is missing")
    result = dict(identity)
    for key in ("source_sha", "operator_identity", "basis_manifest_sha256"):
        _require(isinstance(result.get(key), str) and result[key], f"W1 identity {key} is missing")
    manifest = result.get("basis_manifest")
    _require(
        isinstance(manifest, list) and len(manifest) == M6B_W1_RANGE_COLUMNS,
        "W1 basis manifest is missing or incomplete",
    )
    for index, item in enumerate(manifest):
        _require(
            isinstance(item, Mapping)
            and set(item) == {"mode_index", "nnz", "storage_bytes", "vector_sha256"}
            and item["mode_index"] == index
            and type(item["nnz"]) is int
            and item["nnz"] >= 0
            and type(item["storage_bytes"]) is int
            and item["storage_bytes"] >= 0
            and isinstance(item["vector_sha256"], str)
            and len(item["vector_sha256"]) == 64,
            f"W1 basis manifest entry {index} is invalid",
        )
    expected = _json_sha256(list(basis_manifest))
    _require(result["basis_manifest_sha256"] == expected, "W1 basis manifest SHA mismatch")
    _require(manifest == list(basis_manifest), "W1 basis manifest identity mismatch")
    return _jsonable(result)


def basis_manifest_from_vectors(basis: Sequence[Any]) -> list[dict[str, Any]]:
    """Create the frozen W0 basis identity from sparse owner-local vectors."""

    _require(len(basis) == M6B_W1_RANGE_COLUMNS, "W1 basis column count is not 75")
    manifest: list[dict[str, Any]] = []
    for index, vector in enumerate(basis):
        indices = np.asarray(getattr(vector, "indices", None), dtype=np.int64)
        values = np.asarray(getattr(vector, "values", None), dtype=np.complex128)
        raw_storage_bytes = getattr(vector, "storage_bytes", None)
        _require(
            indices.ndim == values.ndim == 1
            and indices.size == values.size
            and indices.dtype == np.dtype(np.int64)
            and values.dtype == _COMPLEX128
            and isinstance(raw_storage_bytes, (int, np.integer)),
            f"W1 basis vector {index} is invalid",
        )
        storage_bytes = int(raw_storage_bytes)
        _require(storage_bytes >= 0, f"W1 basis vector {index} storage is invalid")
        vector_sha256 = _json_sha256(
            {
                "indices_sha256": _array_sha256(indices),
                "values_sha256": _array_sha256(values),
                "storage_bytes": storage_bytes,
            }
        )
        manifest.append(
            {
                "mode_index": index,
                "nnz": int(indices.size),
                "storage_bytes": storage_bytes,
                "vector_sha256": vector_sha256,
            }
        )
    return manifest


def validate_w0_authority(
    identity: Mapping[str, Any], az_column_sha256_aggregate: str
) -> None:
    """Require the fixed W0 range(AZ) diagnostic identity."""

    _require(
        identity.get("basis_manifest_sha256") == M6B_W1_W0_BASIS_MANIFEST_SHA256,
        "W1 basis identity differs from frozen W0 authority",
    )
    _require(
        az_column_sha256_aggregate == M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
        "W1 AZ column identity differs from frozen W0 authority",
    )
    for key, expected in (
        (
            "w0_az_column_sha256_aggregate",
            M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
        ),
        ("w0_oracle_output_sha256", M6B_W1_W0_ORACLE_OUTPUT_SHA256),
        ("w0_residual_source_sha", M6B_W1_W0_RESIDUAL_SOURCE_SHA),
        ("w0_oracle_execution_source_sha", M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA),
    ):
        _require(identity.get(key) == expected, f"W1 {key} is not W0-bound")


def _validate_local_column(value: Any, local_rows: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    _require(
        array.dtype == _COMPLEX128
        and array.ndim == 1
        and array.size == local_rows
        and np.all(np.isfinite(array)),
        f"W1 {name} column has invalid layout",
    )
    return np.asarray(array, dtype=np.complex128)


def _basis_columns(
    basis: Sequence[Any], ownership_range: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    start, end = ownership_range
    indices_parts: list[np.ndarray] = []
    data_parts: list[np.ndarray] = []
    indptr = np.zeros(M6B_W1_RANGE_COLUMNS + 1, dtype=_INDEX_DTYPE)
    _require(len(basis) == M6B_W1_RANGE_COLUMNS, "W1 basis column count is not 75")
    for column, vector in enumerate(basis):
        indices = np.asarray(getattr(vector, "indices", None))
        values = np.asarray(getattr(vector, "values", None))
        _require(
            indices.dtype.kind in "iu"
            and values.dtype == _COMPLEX128
            and indices.ndim == values.ndim == 1
            and indices.size == values.size,
            f"W1 basis column {column} is invalid",
        )
        indices = np.asarray(indices, dtype=_INDEX_DTYPE)
        values = np.asarray(values, dtype=np.complex128)
        _require(
            not indices.size
            or (indices[0] >= start and indices[-1] < end),
            f"W1 basis column {column} is outside ownership",
        )
        _require(
            not indices.size or np.all(indices[1:] > indices[:-1]),
            f"W1 basis column {column} is not strictly ordered",
        )
        indices_parts.append(indices - start)
        data_parts.append(values.copy())
        indptr[column + 1] = indptr[column] + indices.size
    indices = (
        np.concatenate(indices_parts).astype(_INDEX_DTYPE, copy=False)
        if indices_parts and indptr[-1]
        else np.empty(0, dtype=_INDEX_DTYPE)
    )
    data = (
        np.concatenate(data_parts).astype(np.complex128, copy=False)
        if data_parts and indptr[-1]
        else np.empty(0, dtype=np.complex128)
    )
    return data, indices, indptr


def _validate_csc_arrays(
    data: np.ndarray,
    indices: np.ndarray,
    indptr: np.ndarray,
    local_rows: int,
    name: str,
) -> None:
    _require(
        data.dtype == _COMPLEX128
        and data.ndim == 1
        and np.all(np.isfinite(data)),
        f"W1 {name} data is invalid",
    )
    _require(
        indices.dtype == _INDEX_DTYPE
        and indices.ndim == 1
        and np.all((indices >= 0) & (indices < local_rows)),
        f"W1 {name} indices are invalid",
    )
    _require(
        indptr.dtype == _INDEX_DTYPE
        and indptr.ndim == 1
        and indptr.size == M6B_W1_RANGE_COLUMNS + 1
        and indptr[0] == 0
        and indptr[-1] == data.size
        and np.all(indptr[1:] >= indptr[:-1]),
        f"W1 {name} indptr is invalid",
    )
    for first, last in zip(indptr[:-1], indptr[1:], strict=True):
        column_indices = indices[int(first) : int(last)]
        _require(
            not column_indices.size
            or np.all(column_indices[1:] > column_indices[:-1]),
            f"W1 {name} column indices are not ordered",
        )


def _validate_factor_audit(
    factor_audit: Any, r_factor: np.ndarray
) -> None:
    required = {
        "rank",
        "rank_threshold",
        "gram_hermitian_defect",
        "normal_closure",
        "normal_closure_limit",
        "r_singular_max",
        "r_singular_min",
        "condition_estimate",
        "r_upper_triangular",
        "r_positive_diagonal",
    }
    _require(isinstance(factor_audit, Mapping), "W1 factor audit is missing")
    _require(required.issubset(factor_audit), "W1 factor audit is incomplete")
    _require(factor_audit["rank"] == M6B_W1_RANGE_COLUMNS, "W1 factor rank is not 75")
    for key in (
        "rank_threshold",
        "gram_hermitian_defect",
        "normal_closure",
        "r_singular_max",
        "r_singular_min",
        "condition_estimate",
    ):
        _require(
            isinstance(factor_audit[key], (int, float))
            and np.isfinite(float(factor_audit[key])),
            f"W1 factor audit {key} is nonfinite",
        )
    _require(
        factor_audit["rank_threshold"] > 0.0
        and factor_audit["gram_hermitian_defect"] >= 0.0
        and factor_audit["normal_closure"] >= 0.0
        and factor_audit["normal_closure"] <= M6B_W1_NORMAL_CLOSURE_LIMIT
        and factor_audit["normal_closure_limit"] == M6B_W1_NORMAL_CLOSURE_LIMIT
        and factor_audit["r_singular_max"] > 0.0
        and factor_audit["r_singular_min"] > 0.0
        and factor_audit["condition_estimate"] >= 1.0,
        "W1 factor audit violates fixed Gate",
    )
    _require(
        factor_audit["r_upper_triangular"] is True
        and factor_audit["r_positive_diagonal"] is True,
        "W1 factor triangular/diagonal audit is invalid",
    )
    _require(
        np.array_equal(r_factor, np.triu(r_factor)),
        "W1 R factor is not upper triangular",
    )
    diagonal = np.diag(r_factor)
    _require(
        np.all(np.isfinite(diagonal))
        and np.all(diagonal.real > 0.0)
        and np.array_equal(diagonal.imag, np.zeros_like(diagonal.imag)),
        "W1 R factor diagonal is not positive",
    )
    singular_values = np.linalg.svd(r_factor, compute_uv=False)
    rank_threshold = float(
        _RANK_THRESHOLD_FACTOR * np.finfo(float).eps * singular_values[0]
    )
    _require(
        int(np.count_nonzero(singular_values > rank_threshold)) == M6B_W1_RANGE_COLUMNS,
        "W1 R factor numerical rank is not 75",
    )
    expected_spectral = {
        "rank_threshold": rank_threshold,
        "r_singular_max": float(singular_values[0]),
        "r_singular_min": float(singular_values[-1]),
        "condition_estimate": float(singular_values[0] / singular_values[-1]),
    }
    spectral_rtol = 64.0 * np.finfo(float).eps
    for key, expected in expected_spectral.items():
        _require(
            np.isclose(
                float(factor_audit[key]),
                expected,
                rtol=spectral_rtol,
                atol=0.0,
                equal_nan=False,
            ),
            f"W1 factor audit {key} does not match R",
        )


class SparseM6BRangeCarrier:
    """Owner-local sparse ``Z`` carrier with exact ``A^H`` least-squares apply."""

    def __init__(
        self,
        *,
        z_data: np.ndarray,
        z_indices: np.ndarray,
        z_indptr: np.ndarray,
        r_factor: np.ndarray,
        global_rows: int,
        ownership_range: tuple[int, int],
        comm: Any,
        manifest: Mapping[str, Any],
        hermitian_action: Callable[[np.ndarray], np.ndarray],
        manifest_path: Path | None = None,
    ) -> None:
        _require(type(global_rows) is int and global_rows > 0, "W1 global row count is invalid")
        _require(isinstance(manifest, Mapping), "W1 carrier manifest is missing")
        _require(int(comm.Get_size()) == 1 and int(comm.Get_rank()) == 0, "W1 store is fixed to MPI1")
        _require(len(ownership_range) == 2, "W1 ownership range is invalid")
        start, end = (int(ownership_range[0]), int(ownership_range[1]))
        _require(0 <= start < end <= global_rows, "W1 ownership range is invalid")
        local_rows = end - start
        _validate_csc_arrays(z_data, z_indices, z_indptr, local_rows, "Z")
        _require(callable(hermitian_action), "W1 A^H action is missing")
        _require(
            r_factor.dtype == _COMPLEX128
            and r_factor.shape == (M6B_W1_RANGE_COLUMNS, M6B_W1_RANGE_COLUMNS)
            and np.all(np.isfinite(r_factor)),
            "W1 R factor is invalid",
        )
        identity = manifest.get("identity")
        _require(isinstance(identity, Mapping), "W1 carrier identity is missing")
        basis_manifest = identity.get("basis_manifest")
        _require(isinstance(basis_manifest, list), "W1 basis manifest is missing")
        _validate_identity(identity, basis_manifest)
        _require(manifest.get("mpi_scope") == "MPI1", "W1 MPI scope is not MPI1")
        _require(manifest.get("mpi_size") == 1 and manifest.get("rank") == 0, "W1 MPI binding differs")
        _require(tuple(manifest["ownership_range"]) == (start, end), "W1 ownership binding differs")
        factor_audit = manifest.get("factor_audit")
        _validate_factor_audit(factor_audit, r_factor)
        az_column_sha256 = manifest.get("az_column_sha256")
        _require(
            isinstance(az_column_sha256, list)
            and len(az_column_sha256) == M6B_W1_RANGE_COLUMNS
            and all(isinstance(item, str) and len(item) == 64 for item in az_column_sha256),
            "W1 AZ column identity is incomplete",
        )
        _require(
            manifest.get("az_column_sha256_aggregate") == _json_sha256(az_column_sha256),
            "W1 AZ column identity aggregate mismatch",
        )
        _require(
            manifest.get("az_v_retained") is False
            and manifest.get("retained_az_bytes") == 0
            and manifest.get("dense_nrows_x_columns_retained") is False,
            "W1 AZ retention contract is invalid",
        )
        self.z_data = z_data
        self.z_indices = z_indices
        self.z_indptr = z_indptr
        self.r_factor = r_factor
        self.global_rows = global_rows
        self.ownership_range = (start, end)
        self.local_rows = local_rows
        self.comm = comm
        self._manifest = dict(manifest)
        self._manifest_path = manifest_path
        self._manifest_file_bytes = (
            int(manifest_path.stat().st_size) if manifest_path is not None else 0
        )
        self._factor_audit = dict(factor_audit)
        self._numerical_rank = int(factor_audit["rank"])
        self._normal_closure = float(factor_audit["normal_closure"])
        self._hermitian_action = hermitian_action

    @classmethod
    def from_action(
        cls,
        basis: Sequence[Any],
        action: Callable[[Any], np.ndarray],
        *,
        hermitian_action: Callable[[np.ndarray], np.ndarray],
        global_rows: int,
        ownership_range: tuple[int, int],
        comm: Any,
        identity: Mapping[str, Any],
    ) -> "SparseM6BRangeCarrier":
        if not callable(action):
            raise TypeError("W1 forward action must be callable")
        if not callable(hermitian_action):
            raise TypeError("W1 A^H action must be callable")
        _require(
            int(comm.Get_size()) == 1 and int(comm.Get_rank()) == 0,
            "W1 store is fixed to MPI1",
        )
        basis = tuple(basis)
        start, end = (int(ownership_range[0]), int(ownership_range[1]))
        local_rows = end - start
        z_data, z_indices, z_indptr = _basis_columns(basis, (start, end))
        indices_parts: list[np.ndarray] = []
        data_parts: list[np.ndarray] = []
        az_indptr = np.zeros(M6B_W1_RANGE_COLUMNS + 1, dtype=_INDEX_DTYPE)
        column_sha256: list[str] = []
        for column, vector in enumerate(basis):
            observed = _validate_local_column(action(vector), local_rows, f"AZ[{column}]")
            column_sha256.append(_array_sha256(observed))
            positions = np.flatnonzero(observed != 0.0).astype(_INDEX_DTYPE, copy=False)
            indices_parts.append(positions)
            data_parts.append(np.asarray(observed[positions], dtype=np.complex128).copy())
            az_indptr[column + 1] = az_indptr[column] + positions.size
        az_indices = (
            np.concatenate(indices_parts).astype(_INDEX_DTYPE, copy=False)
            if az_indptr[-1]
            else np.empty(0, dtype=_INDEX_DTYPE)
        )
        az_data = (
            np.concatenate(data_parts).astype(np.complex128, copy=False)
            if az_indptr[-1]
            else np.empty(0, dtype=np.complex128)
        )
        del indices_parts, data_parts
        identity_json = _validate_identity(identity, identity["basis_manifest"])
        import scipy.sparse as sp

        az_matrix = sp.csc_matrix(
            (az_data, az_indices, az_indptr),
            shape=(local_rows, M6B_W1_RANGE_COLUMNS),
            copy=False,
        )
        gram = np.asarray(az_matrix.conjugate().transpose().dot(az_matrix).toarray(), dtype=np.complex128)
        del az_matrix
        del az_data, az_indices, az_indptr
        gram_hermitian_defect = float(
            np.linalg.norm(gram - gram.conjugate().T)
            / max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
        )
        _require(np.isfinite(gram_hermitian_defect), "W1 Gram defect is nonfinite")
        gram = 0.5 * (gram + gram.conjugate().T)
        lower = np.linalg.cholesky(gram)
        r_factor = np.asarray(lower.conjugate().T, dtype=np.complex128)
        singular_values = np.linalg.svd(r_factor, compute_uv=False)
        rank_threshold = float(_RANK_THRESHOLD_FACTOR * np.finfo(float).eps * singular_values[0])
        numerical_rank = int(np.count_nonzero(singular_values > rank_threshold))
        _require(numerical_rank == M6B_W1_RANGE_COLUMNS, "W1 represented range rank is not 75")
        normal_closure = float(
            np.linalg.norm(r_factor.conjugate().T @ r_factor - gram)
            / max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
        )
        factor_audit = {
            "rank": numerical_rank,
            "rank_threshold": rank_threshold,
            "gram_hermitian_defect": gram_hermitian_defect,
            "normal_closure": normal_closure,
            "normal_closure_limit": M6B_W1_NORMAL_CLOSURE_LIMIT,
            "r_singular_max": float(singular_values[0]),
            "r_singular_min": float(singular_values[-1]),
            "condition_estimate": float(singular_values[0] / singular_values[-1]),
            "r_upper_triangular": True,
            "r_positive_diagonal": True,
        }
        manifest = {
            "schema": M6B_W1_RANGE_STORE_SCHEMA,
            "global_rows": int(global_rows),
            "ownership_range": [start, end],
            "local_rows": local_rows,
            "columns": M6B_W1_RANGE_COLUMNS,
            "mpi_scope": "MPI1",
            "mpi_size": 1,
            "rank": 0,
            "identity": identity_json,
            "factor_audit": factor_audit,
            "az_column_sha256": column_sha256,
            "az_column_sha256_aggregate": _json_sha256(column_sha256),
            "az_v_retained": False,
            "retained_az_bytes": 0,
            "dense_nrows_x_columns_retained": False,
        }
        return cls(
            z_data=z_data,
            z_indices=z_indices,
            z_indptr=z_indptr,
            r_factor=r_factor,
            global_rows=global_rows,
            ownership_range=(start, end),
            comm=comm,
            manifest=manifest,
            hermitian_action=hermitian_action,
        )

    @property
    def rank(self) -> int:
        return self._numerical_rank

    @property
    def normal_closure(self) -> float:
        return self._normal_closure

    @property
    def audit(self) -> dict[str, Any]:
        numeric_payload = int(
            self.z_data.nbytes
            + self.z_indices.nbytes
            + self.z_indptr.nbytes
            + self.r_factor.nbytes
        )
        bounded_components = {
            "two_local_output_vectors_bytes": int(2 * self.local_rows * _COMPLEX128.itemsize),
            "three_75d_solver_vectors_bytes": int(3 * M6B_W1_RANGE_COLUMNS * _COMPLEX128.itemsize),
        }
        max_z_column_nnz = int(np.max(np.diff(self.z_indptr)))
        bounded_components["two_max_sparse_column_temporaries_bytes"] = int(
            2 * max_z_column_nnz * _COMPLEX128.itemsize
        )
        bounded_work = int(sum(bounded_components.values()))
        retained = int(numeric_payload + self._manifest_file_bytes)
        return {
            "schema": M6B_W1_RANGE_STORE_SCHEMA,
            "global_rows": self.global_rows,
            "local_rows": self.local_rows,
            "ownership_range": list(self.ownership_range),
            "columns": M6B_W1_RANGE_COLUMNS,
            "mpi_scope": "MPI1",
            "rank": self._numerical_rank,
            "factor_audit": dict(self._factor_audit),
            "source_sha": self._manifest["identity"]["source_sha"],
            "operator_identity": self._manifest["identity"]["operator_identity"],
            "basis_manifest_sha256": self._manifest["identity"]["basis_manifest_sha256"],
            "az_column_sha256_aggregate": self._manifest["az_column_sha256_aggregate"],
            "az_column_count": M6B_W1_RANGE_COLUMNS,
            "az_v_retained": False,
            "retained_az_bytes": 0,
            "forward_az_action_persisted": False,
            "hermitian_action_required": True,
            "operator_hermitian_assumed": False,
            "represented_action_retained": False,
            "mpi_size": 1,
            "mmap_readonly": bool(
                self._manifest_file_bytes > 0
                and all(
                    isinstance(value, np.memmap)
                    and not value.flags.writeable
                    for value in (self.z_data, self.z_indices, self.z_indptr, self.r_factor)
                )
            ),
            "retained_components": {
                "z_csc_arrays_bytes": int(
                    self.z_data.nbytes + self.z_indices.nbytes + self.z_indptr.nbytes
                ),
                "r_factor_bytes": int(self.r_factor.nbytes),
                "manifest_file_bytes": self._manifest_file_bytes,
            },
            "max_z_column_nnz": max_z_column_nnz,
            "retained_numeric_payload_bytes": numeric_payload,
            "retained_total_bytes": retained,
            "bounded_work_components": bounded_components,
            "bounded_work_bytes": bounded_work,
            "retained_plus_work_bytes": int(retained + bounded_work),
            "dense_nrows_x_columns_retained": False,
            "dense_nrows_x_columns_bytes": 0,
            "explicit_global_matrix_materialized": False,
        }

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        values = _validate_local_column(rhs, self.local_rows, "RHS")
        adjoint_values = _validate_local_column(
            self._hermitian_action(values), self.local_rows, "A^H RHS"
        )
        h = np.empty(M6B_W1_RANGE_COLUMNS, dtype=np.complex128)
        for column, (first, last) in enumerate(zip(self.z_indptr[:-1], self.z_indptr[1:], strict=True)):
            first_index = int(first)
            last_index = int(last)
            h[column] = np.vdot(
                self.z_data[first_index:last_index],
                adjoint_values[self.z_indices[first_index:last_index]],
            )
        self.comm.Allreduce(MPI.IN_PLACE, h, op=MPI.SUM)
        y = solve_triangular(
            self.r_factor,
            h,
            trans="C",
            lower=False,
            check_finite=False,
        )
        coefficients = solve_triangular(
            self.r_factor, y, lower=False, check_finite=False
        )
        correction = np.zeros(self.local_rows, dtype=np.complex128)
        for column, (first, last) in enumerate(zip(self.z_indptr[:-1], self.z_indptr[1:], strict=True)):
            first_index = int(first)
            last_index = int(last)
            indices = self.z_indices[first_index:last_index]
            correction[indices] += self.z_data[first_index:last_index] * coefficients[column]
        _require(np.all(np.isfinite(correction)), "W1 correction is nonfinite")
        return correction

    def save(self, directory: Path) -> Path:
        directory = Path(directory)
        if directory.exists():
            raise FileExistsError(f"W1 store refuses existing directory: {directory}")
        directory.mkdir(parents=True)
        arrays = {
            "z_data": self.z_data,
            "z_indices": self.z_indices,
            "z_indptr": self.z_indptr,
            "r_factor": self.r_factor,
        }
        descriptors: dict[str, Any] = {}
        for name, value in arrays.items():
            path = directory / f"{name}.npy"
            np.save(path, np.ascontiguousarray(value), allow_pickle=False)
            descriptors[name] = _array_meta(path, value)
        payload = dict(self._manifest)
        payload["arrays"] = descriptors
        payload["manifest_file"] = "manifest.json"
        payload["evidence_sha256"] = None
        payload["evidence_sha256"] = _json_sha256(
            {key: value for key, value in payload.items() if key != "evidence_sha256"}
        )
        manifest_path = directory / "manifest.json"
        manifest_path.write_bytes(_json_bytes(payload) + b"\n")
        self._manifest = payload
        self._manifest_path = manifest_path
        self._manifest_file_bytes = int(manifest_path.stat().st_size)
        return manifest_path


def _load_array(directory: Path, entry: Mapping[str, Any], name: str) -> np.ndarray:
    _require(entry.get("path") == f"{name}.npy", f"W1 {name} path is invalid")
    path = directory / entry["path"]
    _require(path.is_file(), f"W1 {name} array is missing")
    _require(_file_sha256(path) == entry.get("file_sha256"), f"W1 {name} file SHA mismatch")
    value = np.load(path, allow_pickle=False, mmap_mode="r")
    _require(isinstance(value, np.memmap), f"W1 {name} is not mmap-backed")
    _require(not value.flags.writeable, f"W1 {name} mmap is writable")
    _require(tuple(value.shape) == tuple(entry.get("shape", ())), f"W1 {name} shape mismatch")
    _require(str(value.dtype) == entry.get("dtype"), f"W1 {name} dtype mismatch")
    _require(int(value.nbytes) == entry.get("nbytes"), f"W1 {name} nbytes mismatch")
    _require(_array_sha256(value) == entry.get("array_sha256"), f"W1 {name} array SHA mismatch")
    return value


def load_sparse_m6b_range_carrier(
    manifest_path: Path,
    *,
    comm: Any = MPI.COMM_WORLD,
    hermitian_action: Callable[[np.ndarray], np.ndarray],
) -> SparseM6BRangeCarrier:
    """Load the Z/R arrays as read-only mmap views for an explicit ``A^H`` action."""

    manifest_path = Path(manifest_path)
    _require(manifest_path.name == "manifest.json", "W1 manifest name is fixed")
    directory = manifest_path.parent
    _require(manifest_path.is_file(), "W1 manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(manifest, Mapping), "W1 manifest must be an object")
    _require(manifest.get("schema") == M6B_W1_RANGE_STORE_SCHEMA, "W1 manifest schema mismatch")
    _require(
        manifest.get("evidence_sha256")
        == _json_sha256({key: value for key, value in manifest.items() if key != "evidence_sha256"}),
        "W1 manifest evidence SHA mismatch",
    )
    _require(set(manifest.get("arrays", {})) == set(_ARRAY_NAMES), "W1 manifest array set is incomplete")
    expected_files = {"manifest.json", *(f"{name}.npy" for name in _ARRAY_NAMES)}
    actual_files = {path.name for path in directory.iterdir()}
    _require(actual_files == expected_files, "W1 store file set is not exact")
    _require(
        all((directory / name).is_file() for name in expected_files),
        "W1 store file set contains a non-file entry",
    )
    arrays = {
        name: _load_array(directory, manifest["arrays"][name], name) for name in _ARRAY_NAMES
    }
    return SparseM6BRangeCarrier(
        z_data=arrays["z_data"],
        z_indices=arrays["z_indices"],
        z_indptr=arrays["z_indptr"],
        r_factor=arrays["r_factor"],
        global_rows=int(manifest["global_rows"]),
        ownership_range=tuple(manifest["ownership_range"]),
        comm=comm,
        manifest=manifest,
        hermitian_action=hermitian_action,
        manifest_path=manifest_path,
    )
