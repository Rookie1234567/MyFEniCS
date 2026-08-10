"""Opt-in Task037 H2A-R2 constrained local factor store.

The builder consumes one transformed class matrix at a time.  It keeps only
deduplicated complex128 LU factors, one sparse expansion per class, and compact
cell references.  The cold artifact is a JSON manifest plus numeric ``.npy``
arrays; no Python object serialization or ordinary-solver integration is
provided here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from .hcurl_r2_constrained_local_block import H2AR2CellExpansion

__all__ = (
    "H2AR2ClassInput",
    "H2AR2CellReference",
    "H2AR2FactorStore",
    "build_h2a_r2_factor_store",
    "load_h2a_r2_factor_store",
    "write_h2a_r2_factor_store",
)

R2_FACTOR_SCHEMA = "task037.extra.h2a.r2.factor-store.v1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"R2 manifest contains non-finite JSON constant {token}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            raise TypeError("R2 manifest cannot contain object arrays")
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _tupleize(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tupleize(item) for item in value)
    if isinstance(value, dict):
        return {key: _tupleize(item) for key, item in value.items()}
    return value


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(contiguous).cast("B")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_sha256(value: Any, label: str) -> str:
    if not _valid_sha256(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return str(value)


def _reconstruct_lu(lu_values: np.ndarray, pivots: np.ndarray) -> np.ndarray:
    size = int(lu_values.shape[0])
    lower = np.tril(lu_values, -1) + np.eye(size, dtype=np.complex128)
    upper = np.triu(lu_values)
    permuted = lower @ upper
    reconstructed = np.array(permuted, dtype=np.complex128, copy=True, order="C")
    for row in range(size - 1, -1, -1):
        pivot = int(pivots[row])
        if pivot != row:
            reconstructed[[row, pivot], :] = reconstructed[[pivot, row], :]
    return reconstructed


def _relative_residual(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right) / max(float(np.linalg.norm(right)), 1.0e-30))


def _require_finite_nonnegative(value: Any, label: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def _deterministic_rhs(size: int) -> np.ndarray:
    return np.asarray(
        [1.0 + 0.031 * index + 1j * (0.17 - 0.009 * index) for index in range(size)],
        dtype=np.complex128,
    )


@dataclass(frozen=True)
class H2AR2ClassInput:
    """One streamed exact class and its borrowed transformed matrix."""

    class_id: int
    class_key_sha256: str
    constraint_pattern_sha256: str
    expansion_pattern_sha256: str
    expansion: H2AR2CellExpansion
    transformed_matrix: np.ndarray


@dataclass(frozen=True)
class H2AR2CellReference:
    """A retained cell reference: class id plus actual gather rows only."""

    class_id: int
    independent_global_rows: np.ndarray

    def __post_init__(self) -> None:
        rows = np.asarray(self.independent_global_rows, dtype=np.int64)
        if rows.ndim != 1 or np.unique(rows).size != rows.size:
            raise ValueError("R2 cell independent rows must be a unique 1-D array")
        rows = np.array(rows, dtype=np.int64, copy=True, order="C")
        rows.setflags(write=False)
        object.__setattr__(self, "class_id", int(self.class_id))
        object.__setattr__(self, "independent_global_rows", rows)


@dataclass(frozen=True)
class _H2AR2SparseClassExpansion:
    offsets: np.ndarray
    column_indices: np.ndarray
    coefficients: np.ndarray
    pattern_identity: tuple[Any, ...]
    pattern_sha256: str

    @classmethod
    def from_cell_expansion(
        cls, expansion: H2AR2CellExpansion
    ) -> "_H2AR2SparseClassExpansion":
        return cls(
            offsets=np.array(expansion.offsets, dtype=np.int32, copy=True),
            column_indices=np.array(
                expansion.column_indices, dtype=np.int32, copy=True
            ),
            coefficients=np.array(
                expansion.coefficients, dtype=np.complex128, copy=True
            ),
            pattern_identity=tuple(expansion.pattern_identity),
            pattern_sha256=str(expansion.pattern_sha256),
        )

    def __post_init__(self) -> None:
        offsets = np.asarray(self.offsets, dtype=np.int32)
        columns = np.asarray(self.column_indices, dtype=np.int32)
        coefficients = np.asarray(self.coefficients, dtype=np.complex128)
        if offsets.ndim != 1 or offsets.size == 0:
            raise ValueError("R2 class expansion offsets are invalid")
        if int(offsets[-1]) != columns.size or columns.size != coefficients.size:
            raise ValueError("R2 class expansion arrays do not close")
        independent_count = int(np.max(columns) + 1) if columns.size else 0
        dummy_rows = np.arange(independent_count, dtype=np.int64)
        H2AR2CellExpansion(
            offsets,
            columns,
            coefficients,
            dummy_rows,
            tuple(self.pattern_identity),
            str(self.pattern_sha256),
        )
        offsets = np.array(offsets, dtype=np.int32, copy=True, order="C")
        columns = np.array(columns, dtype=np.int32, copy=True, order="C")
        coefficients = np.array(coefficients, dtype=np.complex128, copy=True, order="C")
        offsets.setflags(write=False)
        columns.setflags(write=False)
        coefficients.setflags(write=False)
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "column_indices", columns)
        object.__setattr__(self, "coefficients", coefficients)

    @property
    def independent_count(self) -> int:
        return int(np.max(self.column_indices) + 1) if self.column_indices.size else 0


@dataclass(frozen=True)
class _H2AR2Factor:
    factor_id: int
    numeric_matrix_sha256: str
    numeric_matrix_shape: tuple[int, ...]
    numeric_matrix_dtype: str
    values: np.ndarray
    pivots: np.ndarray
    factorization_residual: float
    solve_residual: float
    finite: bool
    deterministic: bool

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=np.complex128)
        pivots = np.asarray(self.pivots, dtype=np.int32)
        if values.ndim != 2 or values.shape[0] != values.shape[1]:
            raise ValueError("R2 factor values must be square")
        if pivots.shape != (values.shape[0],):
            raise ValueError("R2 factor pivots do not match values")
        if not np.all(np.isfinite(values)) or not np.all(np.isfinite(pivots)):
            raise ValueError("R2 factors must be finite")
        factorization_residual = _require_finite_nonnegative(
            self.factorization_residual, "factorization_residual"
        )
        solve_residual = _require_finite_nonnegative(
            self.solve_residual, "solve_residual"
        )
        values = np.array(values, dtype=np.complex128, copy=True, order="C")
        pivots = np.array(pivots, dtype=np.int32, copy=True, order="C")
        values.setflags(write=False)
        pivots.setflags(write=False)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "pivots", pivots)
        object.__setattr__(self, "factor_id", int(self.factor_id))
        object.__setattr__(self, "factorization_residual", factorization_residual)
        object.__setattr__(self, "solve_residual", solve_residual)


@dataclass(frozen=True)
class _H2AR2ClassRecord:
    class_id: int
    class_key_sha256: str
    constraint_pattern_sha256: str
    expansion_pattern_sha256: str
    factor_id: int
    numeric_matrix_sha256: str
    numeric_matrix_shape: tuple[int, ...]
    numeric_matrix_dtype: str
    expansion: _H2AR2SparseClassExpansion
    factorization_residual: float
    solve_residual: float
    finite: bool
    deterministic: bool

    def __post_init__(self) -> None:
        _require_sha256(self.class_key_sha256, "class_key_sha256")
        _require_sha256(
            self.constraint_pattern_sha256, "constraint_pattern_sha256"
        )
        expansion_pattern_sha = _require_sha256(
            self.expansion_pattern_sha256, "expansion_pattern_sha256"
        )
        if expansion_pattern_sha != self.expansion.pattern_sha256:
            raise ValueError("R2 class expansion pattern SHA does not match")
        _require_finite_nonnegative(
            self.factorization_residual, "class factorization_residual"
        )
        _require_finite_nonnegative(self.solve_residual, "class solve_residual")


def _factorize(
    matrix: np.ndarray,
    factor_id: int,
    numeric_sha256: str,
) -> _H2AR2Factor:
    lu_values, pivots = lu_factor(matrix, check_finite=True)
    lu_values = np.ascontiguousarray(lu_values, dtype=np.complex128).copy()
    pivots = np.ascontiguousarray(pivots, dtype=np.int32).copy()
    reconstructed = _reconstruct_lu(lu_values, pivots)
    factorization_residual = _relative_residual(reconstructed, matrix)
    rhs = _deterministic_rhs(int(matrix.shape[0]))
    solved = lu_solve((lu_values, pivots), rhs, check_finite=True)
    solve_residual = float(
        np.linalg.norm(matrix @ solved - rhs) / max(float(np.linalg.norm(rhs)), 1.0e-30)
    )
    repeated_values, repeated_pivots = lu_factor(matrix, check_finite=True)
    repeated_values = np.ascontiguousarray(
        repeated_values, dtype=np.complex128
    ).copy()
    repeated_pivots = np.ascontiguousarray(repeated_pivots, dtype=np.int32).copy()
    deterministic = bool(
        np.array_equal(lu_values, repeated_values)
        and np.array_equal(pivots, repeated_pivots)
    )
    del repeated_values, repeated_pivots
    return _H2AR2Factor(
        factor_id=factor_id,
        numeric_matrix_sha256=numeric_sha256,
        numeric_matrix_shape=tuple(int(value) for value in matrix.shape),
        numeric_matrix_dtype=str(matrix.dtype),
        values=lu_values,
        pivots=pivots,
        factorization_residual=factorization_residual,
        solve_residual=solve_residual,
        finite=bool(
            np.all(np.isfinite(matrix))
            and np.all(np.isfinite(lu_values))
            and np.all(np.isfinite(pivots))
            and np.isfinite(factorization_residual)
            and np.isfinite(solve_residual)
        ),
        deterministic=deterministic,
    )


class H2AR2FactorStore:
    """In-memory unique factors and compact class/cell maps."""

    def __init__(
        self,
        factors: Sequence[_H2AR2Factor],
        classes: Sequence[_H2AR2ClassRecord],
        cells: Sequence[H2AR2CellReference],
        identity: Mapping[str, Any],
    ) -> None:
        self._factors = tuple(factors)
        self._classes = tuple(classes)
        self._cells = tuple(cells)
        for expected_id, record in enumerate(self._classes):
            if int(record.class_id) != expected_id:
                raise ValueError("R2 class ids must be continuous")
        for cell in self._cells:
            class_id = int(cell.class_id)
            if class_id < 0 or class_id >= len(self._classes):
                raise ValueError("R2 cell reference class id is out of range")
            expected_count = self._classes[class_id].expansion.independent_count
            if cell.independent_global_rows.size != expected_count:
                raise ValueError(
                    "R2 cell independent row count does not match class expansion"
                )
        self._identity = _jsonable(identity)
        self._audit = self._make_audit()

    @property
    def factors(self) -> tuple[_H2AR2Factor, ...]:
        return self._factors

    @property
    def classes(self) -> tuple[_H2AR2ClassRecord, ...]:
        return self._classes

    @property
    def cells(self) -> tuple[H2AR2CellReference, ...]:
        return self._cells

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._audit

    def solve(self, class_id: int, right_hand_side: np.ndarray) -> np.ndarray:
        record = self._classes[int(class_id)]
        factor = self._factors[int(record.factor_id)]
        return np.asarray(
            lu_solve((factor.values, factor.pivots), right_hand_side),
            dtype=np.complex128,
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "source_identity": self._identity.get("source_identity"),
            "config_identity": self._identity.get("config_identity"),
            "form_identity": self._identity.get("form_identity"),
            "cache_identity": self._identity.get("cache_identity"),
            "classes": [
                {
                    "class_id": int(record.class_id),
                    "class_key_sha256": record.class_key_sha256,
                    "constraint_pattern_sha256": record.constraint_pattern_sha256,
                    "expansion_pattern_sha256": record.expansion_pattern_sha256,
                    "factor_id": int(record.factor_id),
                    "numeric_matrix_sha256": record.numeric_matrix_sha256,
                    "numeric_matrix_shape": list(record.numeric_matrix_shape),
                    "numeric_matrix_dtype": record.numeric_matrix_dtype,
                    "numeric_matrix_nbytes": int(
                        np.prod(record.numeric_matrix_shape, dtype=np.int64)
                        * np.dtype(record.numeric_matrix_dtype).itemsize
                    ),
                    "pattern_identity": _jsonable(record.expansion.pattern_identity),
                    "factorization_residual": record.factorization_residual,
                    "solve_residual": record.solve_residual,
                    "finite": record.finite,
                    "deterministic": record.deterministic,
                    "determinism_method": "repeated_factorization_same_matrix",
                }
                for record in self._classes
            ],
            "factors": [
                {
                    "factor_id": int(factor.factor_id),
                    "numeric_matrix_sha256": factor.numeric_matrix_sha256,
                    "numeric_matrix_shape": list(factor.numeric_matrix_shape),
                    "numeric_matrix_dtype": factor.numeric_matrix_dtype,
                    "numeric_matrix_nbytes": int(
                        np.prod(factor.numeric_matrix_shape, dtype=np.int64)
                        * np.dtype(factor.numeric_matrix_dtype).itemsize
                    ),
                    "factorization_residual": factor.factorization_residual,
                    "solve_residual": factor.solve_residual,
                    "finite": factor.finite,
                    "deterministic": factor.deterministic,
                    "determinism_method": "repeated_factorization_same_matrix",
                }
                for factor in self._factors
            ],
            "cell_count": len(self._cells),
            "materialization_identity": {
                "per_cell_factor": False,
                "slab_factor": False,
                "global_matrix": False,
                "global_constraint_matrix": False,
                "schur": False,
            },
        }

    def _cell_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        class_ids = np.asarray(
            [int(cell.class_id) for cell in self._cells], dtype=np.int32
        )
        offsets = [0]
        rows: list[int] = []
        for cell in self._cells:
            rows.extend(int(value) for value in cell.independent_global_rows)
            offsets.append(len(rows))
        return (
            class_ids,
            np.asarray(offsets, dtype=np.int64),
            np.asarray(rows, dtype=np.int64),
        )

    def _make_audit(self) -> Mapping[str, Any]:
        class_ids, row_offsets, rows = self._cell_arrays()
        factor_values_bytes = sum(int(factor.values.nbytes) for factor in self._factors)
        factor_pivots_bytes = sum(int(factor.pivots.nbytes) for factor in self._factors)
        expansion_bytes = sum(
            int(record.expansion.offsets.nbytes)
            + int(record.expansion.column_indices.nbytes)
            + int(record.expansion.coefficients.nbytes)
            for record in self._classes
        )
        cell_bytes = int(class_ids.nbytes + row_offsets.nbytes + rows.nbytes)
        metadata_bytes = len(_json_bytes(self._metadata()))
        components = {
            "factor_values_bytes": factor_values_bytes,
            "factor_pivots_bytes": factor_pivots_bytes,
            "class_expansion_sparse_bytes": expansion_bytes,
            "cell_reference_bytes": cell_bytes,
            "metadata_bytes": metadata_bytes,
        }
        return {
            "schema": R2_FACTOR_SCHEMA,
            "class_count": len(self._classes),
            "unique_factor_count": len(self._factors),
            "numeric_hash_dedup_count": len(self._classes) - len(self._factors),
            "cell_count": len(self._cells),
            "retained_payload_components": components,
            "retained_payload_bytes": int(sum(components.values())),
            "factor_plus_metadata_bytes": int(
                sum(components.values())
            ),
            "factor_plus_metadata_basis": (
                "factor_values+pivots+class_expansion_sparse+cell_references+"
                "canonical_json_metadata"
            ),
            "factorization_residual_max": max(
                (factor.factorization_residual for factor in self._factors),
                default=0.0,
            ),
            "solve_residual_max": max(
                (factor.solve_residual for factor in self._factors),
                default=0.0,
            ),
            "finite": all(factor.finite for factor in self._factors)
            and all(record.finite for record in self._classes),
            "deterministic": all(factor.deterministic for factor in self._factors)
            and all(record.deterministic for record in self._classes),
            "per_cell_factor_count": 0,
            "slab_factor_count": 0,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "schur_materialized": False,
            "ordinary_default_changed": False,
        }


def build_h2a_r2_factor_store(
    class_inputs: Iterable[H2AR2ClassInput],
    cell_references: Sequence[H2AR2CellReference],
    *,
    identity: Mapping[str, Any],
    task037_extra_h2a_r2: bool = False,
) -> H2AR2FactorStore:
    """Stream one exact class at a time into a constrained factor store."""

    if not bool(task037_extra_h2a_r2):
        raise ValueError("R2 factor store requires explicit task037 opt-in")
    factors: list[_H2AR2Factor] = []
    factors_by_signature: dict[tuple[Any, ...], int] = {}
    classes: list[_H2AR2ClassRecord] = []
    seen_class_keys: set[str] = set()
    for expected_class_id, item in enumerate(class_inputs):
        if int(item.class_id) != expected_class_id:
            raise ValueError("R2 class ids must be continuous and stream ordered")
        class_key_sha = _require_sha256(item.class_key_sha256, "class_key_sha256")
        constraint_pattern_sha = _require_sha256(
            item.constraint_pattern_sha256, "constraint_pattern_sha256"
        )
        expansion_pattern_sha = _require_sha256(
            item.expansion_pattern_sha256, "expansion_pattern_sha256"
        )
        if class_key_sha in seen_class_keys:
            raise ValueError("R2 class key was submitted more than once")
        if expansion_pattern_sha != item.expansion.pattern_sha256:
            raise ValueError("R2 expansion pattern SHA does not match expansion")
        seen_class_keys.add(class_key_sha)
        matrix = np.asarray(item.transformed_matrix)
        if matrix.dtype != np.dtype(np.complex128) or matrix.ndim != 2:
            raise TypeError("R2 transformed matrices must be complex128 rank-2 arrays")
        if matrix.shape != (
            item.expansion.independent_count,
            item.expansion.independent_count,
        ):
            raise ValueError("R2 transformed matrix shape does not match expansion")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("R2 transformed matrix must be finite")
        matrix = np.ascontiguousarray(matrix)
        numeric_sha = _array_sha256(matrix)
        signature = (tuple(int(value) for value in matrix.shape), str(matrix.dtype), numeric_sha)
        factor_id = factors_by_signature.get(signature)
        if factor_id is None:
            factor_id = len(factors)
            factor = _factorize(matrix, factor_id, numeric_sha)
            factors.append(factor)
            factors_by_signature[signature] = factor_id
        else:
            factor = factors[factor_id]
        expansion = _H2AR2SparseClassExpansion.from_cell_expansion(item.expansion)
        classes.append(
            _H2AR2ClassRecord(
                class_id=int(item.class_id),
                class_key_sha256=class_key_sha,
                constraint_pattern_sha256=constraint_pattern_sha,
                expansion_pattern_sha256=expansion_pattern_sha,
                factor_id=int(factor_id),
                numeric_matrix_sha256=numeric_sha,
                numeric_matrix_shape=tuple(int(value) for value in matrix.shape),
                numeric_matrix_dtype=str(matrix.dtype),
                expansion=expansion,
                factorization_residual=factor.factorization_residual,
                solve_residual=factor.solve_residual,
                finite=factor.finite,
                deterministic=factor.deterministic,
            )
        )
        del matrix
    if not classes:
        raise ValueError("R2 factor store requires at least one class")
    cells = tuple(cell_references)
    for cell in cells:
        if int(cell.class_id) < 0 or int(cell.class_id) >= len(classes):
            raise ValueError("R2 cell reference class id is out of range")
    return H2AR2FactorStore(factors, classes, cells, identity)


def _write_array(root: Path, relative: str, array: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(array)
    if array.dtype == object:
        raise TypeError("R2 cold arrays cannot have object dtype")
    path = root / relative
    np.save(path, array, allow_pickle=False)
    return {
        "path": relative,
        "bytes": int(path.stat().st_size),
        "sha256": _file_sha256(path),
        "array_sha256": _array_sha256(array),
        "dtype": str(array.dtype),
        "shape": [int(value) for value in array.shape],
        "nbytes": int(array.nbytes),
    }


def write_h2a_r2_factor_store(
    store: H2AR2FactorStore,
    output_dir: str | Path,
    *,
    task037_extra_h2a_r2: bool = False,
) -> Path:
    """Write JSON plus numeric ``.npy`` arrays for one opted-in store."""

    if not bool(task037_extra_h2a_r2):
        raise ValueError("R2 factor artifact requires explicit task037 opt-in")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = {}
    factor_metadata: list[dict[str, Any]] = []
    for factor in store.factors:
        values_path = f"factor_{factor.factor_id}_values.npy"
        pivots_path = f"factor_{factor.factor_id}_pivots.npy"
        files[values_path] = _write_array(root, values_path, factor.values)
        files[pivots_path] = _write_array(root, pivots_path, factor.pivots)
        factor_metadata.append(
            {
                "factor_id": int(factor.factor_id),
                "numeric_matrix_sha256": factor.numeric_matrix_sha256,
                "numeric_matrix_shape": list(factor.numeric_matrix_shape),
                "numeric_matrix_dtype": factor.numeric_matrix_dtype,
                "numeric_matrix_nbytes": int(
                    np.prod(factor.numeric_matrix_shape, dtype=np.int64)
                    * np.dtype(factor.numeric_matrix_dtype).itemsize
                ),
                "values_path": values_path,
                "pivots_path": pivots_path,
                "factor_values_sha256": files[values_path]["array_sha256"],
                "factor_pivots_sha256": files[pivots_path]["array_sha256"],
                "determinism_method": "repeated_factorization_same_matrix",
                "factorization_residual": factor.factorization_residual,
                "solve_residual": factor.solve_residual,
                "finite": factor.finite,
                "deterministic": factor.deterministic,
            }
        )
    class_metadata: list[dict[str, Any]] = []
    for record in store.classes:
        prefix = f"class_{record.class_id}_expansion"
        offsets_path = f"{prefix}_offsets.npy"
        columns_path = f"{prefix}_columns.npy"
        coefficients_path = f"{prefix}_coefficients.npy"
        files[offsets_path] = _write_array(
            root, offsets_path, record.expansion.offsets
        )
        files[columns_path] = _write_array(
            root, columns_path, record.expansion.column_indices
        )
        files[coefficients_path] = _write_array(
            root, coefficients_path, record.expansion.coefficients
        )
        class_metadata.append(
            {
                "class_id": int(record.class_id),
                "class_key_sha256": record.class_key_sha256,
                "constraint_pattern_sha256": record.constraint_pattern_sha256,
                "expansion_pattern_sha256": record.expansion_pattern_sha256,
                "factor_id": int(record.factor_id),
                "numeric_matrix_sha256": record.numeric_matrix_sha256,
                "numeric_matrix_shape": list(record.numeric_matrix_shape),
                "numeric_matrix_dtype": record.numeric_matrix_dtype,
                "numeric_matrix_nbytes": int(
                    np.prod(record.numeric_matrix_shape, dtype=np.int64)
                    * np.dtype(record.numeric_matrix_dtype).itemsize
                ),
                "pattern_identity": _jsonable(record.expansion.pattern_identity),
                "offsets_path": offsets_path,
                "columns_path": columns_path,
                "coefficients_path": coefficients_path,
                "factorization_residual": record.factorization_residual,
                "solve_residual": record.solve_residual,
                "finite": record.finite,
                "deterministic": record.deterministic,
                "determinism_method": "repeated_factorization_same_matrix",
            }
        )
    cell_class_ids, cell_row_offsets, cell_rows = store._cell_arrays()
    cell_paths = {
        "class_ids_path": "cells_class_ids.npy",
        "row_offsets_path": "cells_row_offsets.npy",
        "independent_global_rows_path": "cells_independent_global_rows.npy",
    }
    files[cell_paths["class_ids_path"]] = _write_array(
        root, cell_paths["class_ids_path"], cell_class_ids
    )
    files[cell_paths["row_offsets_path"]] = _write_array(
        root, cell_paths["row_offsets_path"], cell_row_offsets
    )
    files[cell_paths["independent_global_rows_path"]] = _write_array(
        root, cell_paths["independent_global_rows_path"], cell_rows
    )
    metadata = {
        "source_identity": store._identity.get("source_identity"),
        "config_identity": store._identity.get("config_identity"),
        "form_identity": store._identity.get("form_identity"),
        "cache_identity": store._identity.get("cache_identity"),
        "factor_count": len(store.factors),
        "class_count": len(store.classes),
        "cell_count": len(store.cells),
        "factors": factor_metadata,
        "classes": class_metadata,
        "cells": cell_paths,
        "materialization_identity": {
            "per_cell_factor": False,
            "slab_factor": False,
            "global_matrix": False,
            "global_constraint_matrix": False,
            "schur": False,
        },
    }
    metadata_bytes = len(_json_bytes(metadata))
    factor_values_bytes = sum(int(factor.values.nbytes) for factor in store.factors)
    factor_pivots_bytes = sum(int(factor.pivots.nbytes) for factor in store.factors)
    expansion_bytes = sum(
        int(record.expansion.offsets.nbytes)
        + int(record.expansion.column_indices.nbytes)
        + int(record.expansion.coefficients.nbytes)
        for record in store.classes
    )
    cell_bytes = int(cell_class_ids.nbytes + cell_row_offsets.nbytes + cell_rows.nbytes)
    manifest = {
        "schema": R2_FACTOR_SCHEMA,
        "task037_extra_h2a_r2": True,
        "metadata": metadata,
        "files": files,
        "payload": {
            "components": {
                "factor_values_bytes": factor_values_bytes,
                "factor_pivots_bytes": factor_pivots_bytes,
                "class_expansion_sparse_bytes": expansion_bytes,
                "cell_reference_bytes": cell_bytes,
                "metadata_bytes": metadata_bytes,
            },
            "retained_payload_bytes": int(
                factor_values_bytes
                + factor_pivots_bytes
                + expansion_bytes
                + cell_bytes
                + metadata_bytes
            ),
            "factor_plus_metadata_bytes": int(
                factor_values_bytes
                + factor_pivots_bytes
                + expansion_bytes
                + cell_bytes
                + metadata_bytes
            ),
            "metadata_basis": "canonical_utf8_json_metadata",
            "factor_plus_metadata_basis": (
                "factor_values+pivots+class_expansion_sparse+cell_references+"
                "canonical_json_metadata"
            ),
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest) + b"\n")
    return manifest_path


def _relative_file_entry(root: Path, files: Mapping[str, Any], path: Any) -> dict[str, Any]:
    if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("R2 manifest array path must be relative")
    if path not in files or not isinstance(files[path], Mapping):
        raise ValueError("R2 manifest array cross-reference is missing")
    entry = dict(files[path])
    if entry.get("path") != path:
        raise ValueError("R2 manifest file path cross-reference differs")
    actual = root / path
    if not actual.is_file():
        raise FileNotFoundError(actual)
    if int(entry["bytes"]) != int(actual.stat().st_size):
        raise ValueError("R2 cold file byte count mismatch")
    if _file_sha256(actual) != _require_sha256(entry["sha256"], "file sha256"):
        raise ValueError("R2 cold file SHA mismatch")
    return entry


def _load_array(
    root: Path, files: Mapping[str, Any], path: Any
) -> np.ndarray:
    entry = _relative_file_entry(root, files, path)
    loaded = np.load(root / str(path), allow_pickle=False)
    if not isinstance(loaded, np.ndarray) or loaded.dtype == object:
        raise TypeError("R2 cold artifact must contain numeric .npy arrays")
    if str(loaded.dtype) != str(entry["dtype"]):
        raise ValueError("R2 cold array dtype mismatch")
    if list(loaded.shape) != [int(value) for value in entry["shape"]]:
        raise ValueError("R2 cold array shape mismatch")
    if int(loaded.nbytes) != int(entry["nbytes"]):
        raise ValueError("R2 cold array nbytes mismatch")
    if _array_sha256(loaded) != _require_sha256(
        entry["array_sha256"], "array sha256"
    ):
        raise ValueError("R2 cold array SHA mismatch")
    return np.ascontiguousarray(loaded)


def load_h2a_r2_factor_store(
    manifest_path: str | Path,
    *,
    task037_extra_h2a_r2: bool = False,
) -> H2AR2FactorStore:
    """Load and validate one JSON/``.npy`` R2 factor store into RAM."""

    if not bool(task037_extra_h2a_r2):
        raise ValueError("R2 factor artifact requires explicit task037 opt-in")
    manifest_path = Path(manifest_path)
    root = manifest_path.parent
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
    )
    if manifest.get("schema") != R2_FACTOR_SCHEMA or manifest.get(
        "task037_extra_h2a_r2"
    ) is not True:
        raise ValueError("R2 factor manifest schema/opt-in mismatch")
    metadata = manifest.get("metadata")
    files = manifest.get("files")
    payload = manifest.get("payload")
    if not isinstance(metadata, Mapping) or not isinstance(files, Mapping):
        raise ValueError("R2 factor manifest metadata/files are missing")
    if not isinstance(payload, Mapping):
        raise ValueError("R2 factor manifest payload is missing")
    factor_metadata = metadata.get("factors")
    class_metadata = metadata.get("classes")
    cells_metadata = metadata.get("cells")
    if not isinstance(factor_metadata, list) or not isinstance(class_metadata, list):
        raise ValueError("R2 factor/class metadata is missing")
    if not isinstance(cells_metadata, Mapping):
        raise ValueError("R2 cell metadata is missing")
    referenced_paths: set[str] = set()
    arrays: dict[str, np.ndarray] = {}
    for factor in factor_metadata:
        for key in ("values_path", "pivots_path"):
            path = factor[key]
            referenced_paths.add(str(path))
            arrays[str(path)] = _load_array(root, files, path)
    for record in class_metadata:
        for key in ("offsets_path", "columns_path", "coefficients_path"):
            path = record[key]
            referenced_paths.add(str(path))
            arrays[str(path)] = _load_array(root, files, path)
    for key in (
        "class_ids_path",
        "row_offsets_path",
        "independent_global_rows_path",
    ):
        path = cells_metadata[key]
        referenced_paths.add(str(path))
        arrays[str(path)] = _load_array(root, files, path)
    if set(str(path) for path in files) != referenced_paths:
        raise ValueError("R2 manifest file inventory is not closed")

    factors: list[_H2AR2Factor] = []
    for expected_id, item in enumerate(factor_metadata):
        if int(item["factor_id"]) != expected_id:
            raise ValueError("R2 factor ids are not continuous")
        values = arrays[str(item["values_path"])]
        pivots = arrays[str(item["pivots_path"])]
        if tuple(int(value) for value in values.shape) != tuple(
            int(value) for value in item["numeric_matrix_shape"]
        ) or str(values.dtype) != str(item["numeric_matrix_dtype"]):
            raise ValueError("R2 factor values do not match numeric matrix identity")
        expected_nbytes = int(
            np.prod(item["numeric_matrix_shape"], dtype=np.int64)
            * np.dtype(item["numeric_matrix_dtype"]).itemsize
        )
        if int(item["numeric_matrix_nbytes"]) != expected_nbytes:
            raise ValueError("R2 factor numeric matrix nbytes mismatch")
        if _array_sha256(values) != _require_sha256(
            item["factor_values_sha256"], "factor values sha256"
        ) or _array_sha256(pivots) != _require_sha256(
            item["factor_pivots_sha256"], "factor pivots sha256"
        ):
            raise ValueError("R2 factor array SHA cross-reference failed")
        if item["determinism_method"] != "repeated_factorization_same_matrix":
            raise ValueError("R2 factor determinism method is not recorded")
        factor = _H2AR2Factor(
            factor_id=expected_id,
            numeric_matrix_sha256=_require_sha256(
                item["numeric_matrix_sha256"], "numeric matrix sha256"
            ),
            numeric_matrix_shape=tuple(int(value) for value in item["numeric_matrix_shape"]),
            numeric_matrix_dtype=str(item["numeric_matrix_dtype"]),
            values=values,
            pivots=pivots,
            factorization_residual=float(item["factorization_residual"]),
            solve_residual=float(item["solve_residual"]),
            finite=item["finite"] if isinstance(item["finite"], bool) else False,
            deterministic=(
                item["deterministic"]
                if isinstance(item["deterministic"], bool)
                else False
            ),
        )
        if not isinstance(item["finite"], bool) or not isinstance(
            item["deterministic"], bool
        ):
            raise ValueError("R2 factor finite/deterministic fields must be bool")
        factors.append(factor)

    classes: list[_H2AR2ClassRecord] = []
    for expected_id, item in enumerate(class_metadata):
        if int(item["class_id"]) != expected_id:
            raise ValueError("R2 class ids are not continuous")
        factor_id = int(item["factor_id"])
        if factor_id < 0 or factor_id >= len(factors):
            raise ValueError("R2 class factor cross-reference is invalid")
        expansion = _H2AR2SparseClassExpansion(
            arrays[str(item["offsets_path"])],
            arrays[str(item["columns_path"])],
            arrays[str(item["coefficients_path"])],
            _tupleize(item["pattern_identity"]),
            _require_sha256(
                item["expansion_pattern_sha256"], "expansion pattern sha256"
            ),
        )
        factor = factors[factor_id]
        if item["numeric_matrix_sha256"] != factor.numeric_matrix_sha256:
            raise ValueError("R2 class/factor numeric hash mismatch")
        class_factorization_residual = _require_finite_nonnegative(
            item["factorization_residual"],
            "class factorization_residual",
        )
        class_solve_residual = _require_finite_nonnegative(
            item["solve_residual"],
            "class solve_residual",
        )
        if not isinstance(item["finite"], bool) or not isinstance(
            item["deterministic"], bool
        ):
            raise ValueError("R2 class finite/deterministic fields must be bool")
        if class_factorization_residual != factor.factorization_residual:
            raise ValueError("R2 class/factor factorization residual mismatch")
        if class_solve_residual != factor.solve_residual:
            raise ValueError("R2 class/factor solve residual mismatch")
        if item["finite"] != factor.finite:
            raise ValueError("R2 class/factor finite mismatch")
        if item["deterministic"] != factor.deterministic:
            raise ValueError("R2 class/factor deterministic mismatch")
        class_numeric_sha = _require_sha256(
            item["numeric_matrix_sha256"], "class numeric matrix sha256"
        )
        if tuple(int(value) for value in item["numeric_matrix_shape"]) != (
            factor.numeric_matrix_shape
        ) or str(item["numeric_matrix_dtype"]) != factor.numeric_matrix_dtype:
            raise ValueError("R2 class/factor numeric shape or dtype mismatch")
        expansion_pattern_sha = _require_sha256(
            item["expansion_pattern_sha256"], "expansion pattern sha256"
        )
        if expansion_pattern_sha != expansion.pattern_sha256:
            raise ValueError("R2 class expansion pattern hash mismatch")
        _require_sha256(
            item["constraint_pattern_sha256"], "constraint pattern sha256"
        )
        expected_nbytes = int(
            np.prod(item["numeric_matrix_shape"], dtype=np.int64)
            * np.dtype(item["numeric_matrix_dtype"]).itemsize
        )
        if int(item["numeric_matrix_nbytes"]) != expected_nbytes:
            raise ValueError("R2 class numeric matrix nbytes mismatch")
        if item["determinism_method"] != "repeated_factorization_same_matrix":
            raise ValueError("R2 class determinism method is not recorded")
        classes.append(
            _H2AR2ClassRecord(
                class_id=expected_id,
                class_key_sha256=_require_sha256(
                    item["class_key_sha256"], "class key sha256"
                ),
                constraint_pattern_sha256=_require_sha256(
                    item["constraint_pattern_sha256"],
                    "constraint pattern sha256",
                ),
                expansion_pattern_sha256=expansion_pattern_sha,
                factor_id=factor_id,
                numeric_matrix_sha256=class_numeric_sha,
                numeric_matrix_shape=factor.numeric_matrix_shape,
                numeric_matrix_dtype=factor.numeric_matrix_dtype,
                expansion=expansion,
                factorization_residual=class_factorization_residual,
                solve_residual=class_solve_residual,
                finite=item["finite"],
                deterministic=item["deterministic"],
            )
        )

    class_ids = arrays[str(cells_metadata["class_ids_path"])]
    row_offsets = arrays[str(cells_metadata["row_offsets_path"])]
    rows = arrays[str(cells_metadata["independent_global_rows_path"])]
    if class_ids.dtype != np.dtype(np.int32) or row_offsets.dtype != np.dtype(np.int64):
        raise ValueError("R2 cell index dtypes are invalid")
    if row_offsets.ndim != 1 or row_offsets.size != class_ids.size + 1:
        raise ValueError("R2 cell row offsets do not close")
    if int(row_offsets[-1]) != rows.size:
        raise ValueError("R2 cell row array does not close")
    cells = tuple(
        H2AR2CellReference(
            int(class_id),
            rows[int(row_offsets[index]) : int(row_offsets[index + 1])],
        )
        for index, class_id in enumerate(class_ids)
    )
    identity = {
        "source_identity": metadata.get("source_identity"),
        "config_identity": metadata.get("config_identity"),
        "form_identity": metadata.get("form_identity"),
        "cache_identity": metadata.get("cache_identity"),
    }
    store = H2AR2FactorStore(factors, classes, cells, identity)
    actual_metadata_bytes = len(_json_bytes(metadata))
    components = dict(payload["components"])
    actual_components = dict(store.audit["retained_payload_components"])
    actual_components["metadata_bytes"] = actual_metadata_bytes
    for key, value in actual_components.items():
        if int(components[key]) != int(value):
            raise ValueError("R2 manifest payload component closure failed")
    if int(payload["retained_payload_bytes"]) != sum(actual_components.values()):
        raise ValueError("R2 manifest retained payload closure failed")
    if payload["factor_plus_metadata_basis"] != (
        "factor_values+pivots+class_expansion_sparse+cell_references+"
        "canonical_json_metadata"
    ):
        raise ValueError("R2 manifest factor-plus-metadata basis is invalid")
    if int(payload["factor_plus_metadata_bytes"]) != sum(actual_components.values()):
        raise ValueError("R2 manifest factor-plus-metadata closure failed")
    loaded_audit = dict(store.audit)
    loaded_audit["retained_payload_components"] = actual_components
    loaded_audit["retained_payload_bytes"] = int(sum(actual_components.values()))
    loaded_audit["factor_plus_metadata_bytes"] = int(sum(actual_components.values()))
    store._audit = loaded_audit
    return store
