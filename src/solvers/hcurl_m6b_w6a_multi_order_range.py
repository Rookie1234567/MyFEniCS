"""Fixed 390-column W6A multi-diffraction-order range diagnostic.

The first 75 columns are the frozen W1 ``m=0`` carrier.  W6A appends the
fixed ``n=0, m=-7..-1`` columns on 15 z-planes and three components.  The
forward ``A Z`` columns live only in a positional raw scratch file while the
persistent sparse carrier keeps ``Z`` and the small Cholesky factor ``R``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import solve_triangular

from src.solvers.disk_backed_flexible_gmres import RawPositionalColumnStore
from src.solvers.hcurl_m6b_sparse_range import (
    M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
    M6B_W1_W0_BASIS_MANIFEST_SHA256,
    _array_meta,
    _array_sha256,
    _file_sha256,
    _json_bytes,
    _json_sha256,
    _jsonable,
    load_sparse_m6b_range_carrier,
)

__all__ = [
    "W6A_SCHEMA",
    "W6A_LEGACY_COLUMNS",
    "W6A_DIFFRACTION_ORDERS",
    "W6A_Z_PLANES",
    "W6A_COMPONENTS",
    "W6A_ADDED_COLUMNS",
    "W6A_TOTAL_COLUMNS",
    "W6A_REPEAT_COLUMNS",
    "W6A_LEGACY_BASIS_MANIFEST_SHA256",
    "W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE",
    "W6A_NORMAL_CLOSURE_LIMIT",
    "W6AColumnSpec",
    "W6ASparseColumn",
    "fixed_w6a_column_specs",
    "w6a_phase",
    "build_w6a_added_columns",
    "load_w1a_legacy_basis",
    "W6AMultiOrderRangeDiagnostic",
    "validate_w6a_store",
]


W6A_SCHEMA = "task037.extra.m6b.w6a.multi-order-range.v1"
W6A_LEGACY_COLUMNS = 75
W6A_DIFFRACTION_ORDERS = (-7, -6, -5, -4, -3, -2, -1)
W6A_Z_PLANES = 15
W6A_COMPONENTS = 3
W6A_ADDED_COLUMNS = len(W6A_DIFFRACTION_ORDERS) * W6A_Z_PLANES * W6A_COMPONENTS
W6A_TOTAL_COLUMNS = W6A_LEGACY_COLUMNS + W6A_ADDED_COLUMNS
W6A_LEGACY_BASIS_MANIFEST_SHA256 = M6B_W1_W0_BASIS_MANIFEST_SHA256
W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE = M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE
W6A_REPEAT_COLUMNS = (0, 74, 75, 389)
W6A_NORMAL_CLOSURE_LIMIT = 1.0e-11
_COMPLEX128 = np.dtype(np.complex128)
_INDEX_DTYPE = np.dtype(np.int32)
_RANK_THRESHOLD_FACTOR = 128.0


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class W6AColumnSpec:
    column_index: int
    family: str
    order_m: int
    z_plane: int
    component: int


@dataclass(frozen=True)
class W6ASparseColumn:
    indices: np.ndarray
    values: np.ndarray

    def __post_init__(self) -> None:
        indices = np.asarray(self.indices)
        values = np.asarray(self.values)
        _require(
            indices.ndim == values.ndim == 1
            and indices.size == values.size
            and indices.dtype == _INDEX_DTYPE
            and values.dtype == _COMPLEX128
            and (indices.size == 0 or np.all(indices >= 0))
            and np.all(np.isfinite(values))
            and np.all(values != 0.0),
            "W6A sparse column arrays are invalid",
        )
        _require(
            indices.size == 0 or np.all(indices[1:] > indices[:-1]),
            "W6A sparse column indices must be sorted and unique",
        )


def fixed_w6a_column_specs() -> tuple[W6AColumnSpec, ...]:
    specs = [
        W6AColumnSpec(index, "legacy_m0", 0, index // W6A_COMPONENTS, index % W6A_COMPONENTS)
        for index in range(W6A_LEGACY_COLUMNS)
    ]
    index = W6A_LEGACY_COLUMNS
    for order_m in W6A_DIFFRACTION_ORDERS:
        for z_plane in range(W6A_Z_PLANES):
            for component in range(W6A_COMPONENTS):
                specs.append(W6AColumnSpec(index, "diffraction_n0", order_m, z_plane, component))
                index += 1
    result = tuple(specs)
    _require(len(result) == W6A_TOTAL_COLUMNS, "W6A fixed column count is invalid")
    return result


def w6a_phase(
    x: np.ndarray | float,
    y: np.ndarray | float,
    *,
    kx: complex,
    ky: complex,
    period_x: float,
    order_m: int,
) -> np.ndarray:
    if not isinstance(order_m, int) or not np.isfinite(period_x) or period_x <= 0.0:
        raise ValueError("W6A phase parameters are invalid")
    return np.exp(
        1j
        * ((complex(kx) + 2.0 * np.pi * order_m / float(period_x)) * x + complex(ky) * y)
    )


def build_w6a_added_columns(
    make_column: Callable[[W6AColumnSpec], W6ASparseColumn],
) -> tuple[W6ASparseColumn, ...]:
    if not callable(make_column):
        raise TypeError("W6A column builder must be callable")
    return tuple(make_column(spec) for spec in fixed_w6a_column_specs()[W6A_LEGACY_COLUMNS:])


def _validate_column_specs(specs: Sequence[W6AColumnSpec]) -> tuple[W6AColumnSpec, ...]:
    result = tuple(specs)
    expected = fixed_w6a_column_specs()
    _require(result == expected, "W6A column order/specification is not fixed")
    return result


def _validate_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    _require(isinstance(identity, Mapping), "W6A identity is missing")
    _require(
        identity.get("legacy_basis_manifest_sha256")
        == W6A_LEGACY_BASIS_MANIFEST_SHA256,
        "W6A legacy 75-column authority differs",
    )
    _require(identity.get("legacy_column_count") == W6A_LEGACY_COLUMNS, "W6A legacy count differs")
    for key in ("source_sha", "operator_identity"):
        _require(isinstance(identity.get(key), str) and identity[key], f"W6A identity {key} is missing")
    return _jsonable(dict(identity))


def _validate_sparse_column(column: Any, local_rows: int, index: int) -> W6ASparseColumn:
    if not isinstance(column, W6ASparseColumn):
        column = W6ASparseColumn(
            np.asarray(getattr(column, "indices", None), dtype=_INDEX_DTYPE),
            np.asarray(getattr(column, "values", None), dtype=_COMPLEX128),
        )
    _require(
        column.indices.size == 0 or int(column.indices[-1]) < local_rows,
        f"W6A column {index} is outside local ownership",
    )
    return column


def load_w1a_legacy_basis(store_dir: Path) -> dict[str, Any]:
    """Load and bind the frozen 75-column W1A sparse carrier."""

    store_dir = Path(store_dir)
    manifest_path = store_dir / "manifest.json"
    carrier = load_sparse_m6b_range_carrier(
        manifest_path,
        hermitian_action=lambda values: values,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    basis_manifest_sha256 = manifest["identity"]["basis_manifest_sha256"]
    _require(
        basis_manifest_sha256 == W6A_LEGACY_BASIS_MANIFEST_SHA256,
        "W1A basis manifest differs",
    )
    _require(
        manifest.get("az_column_sha256_aggregate")
        == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
        "W1A AZ authority differs",
    )
    return {
        "basis_manifest_sha256": basis_manifest_sha256,
        "az_column_sha256_aggregate": manifest["az_column_sha256_aggregate"],
        "manifest_file_sha256": _file_sha256(manifest_path),
        "z_data": carrier.z_data,
        "z_indices": carrier.z_indices,
        "z_indptr": carrier.z_indptr,
    }


class W6AMultiOrderRangeDiagnostic:
    """Bounded builder-only ``Z``/``A Z`` range diagnostic."""

    def __init__(
        self,
        *,
        specs: tuple[W6AColumnSpec, ...],
        z_data: np.ndarray,
        z_indices: np.ndarray,
        z_indptr: np.ndarray,
        gram: np.ndarray,
        r_factor: np.ndarray,
        az_store: RawPositionalColumnStore,
        global_rows: int,
        ownership_range: tuple[int, int],
        identity: Mapping[str, Any],
        column_sha256: tuple[str, ...],
        legacy_z_identity: Mapping[str, Any],
        base_action_count: int,
        repeat_action_count: int,
        repeat_column_sha256: Mapping[str, str],
    ) -> None:
        self.specs = _validate_column_specs(specs)
        self.z_data = z_data
        self.z_indices = z_indices
        self.z_indptr = z_indptr
        self.gram = gram
        self.r_factor = r_factor
        self.az_store = az_store
        self.global_rows = int(global_rows)
        self.ownership_range = tuple(int(value) for value in ownership_range)
        self.local_rows = self.ownership_range[1] - self.ownership_range[0]
        self.identity = _validate_identity(identity)
        self.column_sha256 = tuple(column_sha256)
        self.legacy_z_identity = _jsonable(dict(legacy_z_identity))
        self.action_counts = {
            "base": int(base_action_count),
            "selected_repeat": int(repeat_action_count),
            "total": int(base_action_count) + int(repeat_action_count),
        }
        self.repeat_column_sha256 = _jsonable(dict(repeat_column_sha256))
        self.repeat_exact = all(
            self.repeat_column_sha256.get(str(column)) == self.column_sha256[column]
            for column in W6A_REPEAT_COLUMNS
        )
        _require(
            self.action_counts == {"base": 390, "selected_repeat": 4, "total": 394}
            and self.repeat_exact,
            "W6A selected repeat audit is invalid",
        )
        self.factor_audit = self._factor_audit()
        self._manifest_path: Path | None = None
        self._manifest_file_bytes = 0

    def _factor_audit(self) -> dict[str, Any]:
        singular = np.linalg.svd(self.r_factor, compute_uv=False)
        threshold = float(_RANK_THRESHOLD_FACTOR * np.finfo(float).eps * max(1.0, singular[0]))
        rank = int(np.count_nonzero(singular > threshold))
        closure = float(
            np.linalg.norm(self.r_factor.conjugate().T @ self.r_factor - self.gram)
            / max(float(np.linalg.norm(self.gram)), np.finfo(float).tiny)
        )
        return {
            "rank": rank,
            "rank_threshold": threshold,
            "gram_hermitian_defect": float(
                np.linalg.norm(self.gram - self.gram.conjugate().T)
                / max(float(np.linalg.norm(self.gram)), np.finfo(float).tiny)
            ),
            "normal_closure": closure,
            "normal_closure_limit": W6A_NORMAL_CLOSURE_LIMIT,
            "r_singular_max": float(singular[0]),
            "r_singular_min": float(singular[-1]),
            "condition_estimate": float(singular[0] / singular[-1]),
            "r_upper_triangular": bool(np.array_equal(self.r_factor, np.triu(self.r_factor))),
            "r_positive_diagonal": bool(np.all(np.real(np.diag(self.r_factor)) > 0.0)),
        }

    @classmethod
    def from_columns(
        cls,
        columns: Sequence[W6ASparseColumn],
        action: Callable[[np.ndarray], np.ndarray],
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        scratch_dir: Path,
        identity: Mapping[str, Any],
        specs: Sequence[W6AColumnSpec] | None = None,
        legacy_basis: Mapping[str, Any] | None = None,
    ) -> "W6AMultiOrderRangeDiagnostic":
        if not callable(action):
            raise TypeError("W6A forward action must be callable")
        start, end = (int(ownership_range[0]), int(ownership_range[1]))
        local_rows = end - start
        _require(
            start == 0 and end == int(global_rows),
            "W6A builder is fixed MPI1 full ownership",
        )
        columns = tuple(_validate_sparse_column(column, local_rows, index) for index, column in enumerate(columns))
        _require(len(columns) == W6A_TOTAL_COLUMNS, "W6A column count is not 390")
        specs = _validate_column_specs(specs or fixed_w6a_column_specs())
        identity = _validate_identity(identity)

        indptr = np.zeros(W6A_TOTAL_COLUMNS + 1, dtype=_INDEX_DTYPE)
        index_parts: list[np.ndarray] = []
        data_parts: list[np.ndarray] = []
        for column, sparse in enumerate(columns):
            index_parts.append(sparse.indices)
            data_parts.append(sparse.values)
            indptr[column + 1] = indptr[column] + sparse.indices.size
        indices = (
            np.concatenate(index_parts).astype(_INDEX_DTYPE, copy=False)
            if indptr[-1]
            else np.empty(0, dtype=_INDEX_DTYPE)
        )
        data = (
            np.concatenate(data_parts).astype(_COMPLEX128, copy=False)
            if indptr[-1]
            else np.empty(0, dtype=_COMPLEX128)
        )
        del index_parts, data_parts
        if not isinstance(legacy_basis, Mapping):
            raise ValueError("W6A frozen legacy basis arrays are required")
        legacy_data = np.asarray(legacy_basis["z_data"])
        legacy_indices = np.asarray(legacy_basis["z_indices"])
        legacy_indptr = np.asarray(legacy_basis["z_indptr"])
        _require(
            legacy_data.dtype == _COMPLEX128
            and legacy_indices.dtype == _INDEX_DTYPE
            and legacy_indptr.dtype == _INDEX_DTYPE
            and legacy_indptr.shape == (W6A_LEGACY_COLUMNS + 1,),
            "W6A legacy basis arrays are invalid",
        )
        legacy_nnz = int(legacy_indptr[-1])
        _require(
            np.array_equal(indptr[: W6A_LEGACY_COLUMNS + 1], legacy_indptr)
            and np.array_equal(indices[:legacy_nnz], legacy_indices)
            and np.array_equal(data[:legacy_nnz], legacy_data),
            "W6A first 75 columns differ from W1A authority",
        )
        legacy_z_identity = {
            "basis_manifest_sha256": legacy_basis.get("basis_manifest_sha256"),
            "manifest_file_sha256": legacy_basis.get("manifest_file_sha256"),
            "z_data_array_sha256": _array_sha256(legacy_data),
            "z_indices_array_sha256": _array_sha256(legacy_indices),
            "z_indptr_array_sha256": _array_sha256(legacy_indptr),
            "nnz": legacy_nnz,
        }
        _require(
            legacy_z_identity["basis_manifest_sha256"] == W6A_LEGACY_BASIS_MANIFEST_SHA256
            and isinstance(legacy_z_identity["manifest_file_sha256"], str)
            and len(legacy_z_identity["manifest_file_sha256"]) == 64,
            "W6A legacy manifest authority differs",
        )

        scratch_dir = Path(scratch_dir)
        if scratch_dir.exists():
            raise FileExistsError(f"W6A scratch directory already exists: {scratch_dir}")
        scratch_dir.mkdir(parents=True)
        az_store = RawPositionalColumnStore(scratch_dir / "az_columns.bin", local_rows, W6A_TOTAL_COLUMNS)
        vector = np.zeros(local_rows, dtype=_COMPLEX128)
        base_action_count = 0
        column_sha256: list[str] = []
        repeat_column_sha256: dict[str, str] = {}
        repeat_action_count = 0
        try:
            for column in range(W6A_TOTAL_COLUMNS):
                first, last = int(indptr[column]), int(indptr[column + 1])
                vector.fill(0.0)
                vector[indices[first:last]] = data[first:last]
                observed = np.asarray(action(vector))
                if (
                    observed.ndim != 1
                    or observed.shape[0] != local_rows
                    or observed.dtype != _COMPLEX128
                    or not np.all(np.isfinite(observed))
                ):
                    raise TypeError(f"W6A AZ column {column} is invalid")
                az_store.write_column(column, np.ascontiguousarray(observed))
                column_sha256.append(_array_sha256(observed))
                base_action_count += 1
                del observed
                if column == W6A_LEGACY_COLUMNS - 1:
                    legacy_z_identity["az_column_sha256_aggregate"] = _json_sha256(
                        column_sha256
                    )
                    _require(
                        legacy_z_identity["az_column_sha256_aggregate"]
                        == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
                        "W6A first 75 AZ authority differs",
                    )

            for column in W6A_REPEAT_COLUMNS:
                first, last = int(indptr[column]), int(indptr[column + 1])
                vector.fill(0.0)
                vector[indices[first:last]] = data[first:last]
                observed = np.asarray(action(vector))
                if (
                    observed.ndim != 1
                    or observed.shape[0] != local_rows
                    or observed.dtype != _COMPLEX128
                    or not np.all(np.isfinite(observed))
                ):
                    raise TypeError(f"W6A repeated AZ column {column} is invalid")
                repeat_column_sha256[str(column)] = _array_sha256(observed)
                repeat_action_count += 1
                del observed
            _require(
                all(
                    repeat_column_sha256[str(column)] == column_sha256[column]
                    for column in W6A_REPEAT_COLUMNS
                ),
                "W6A selected AZ repeats are not exact",
            )
            del vector
            gram = np.zeros((W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS), dtype=_COMPLEX128)
            left = np.empty(local_rows, dtype=_COMPLEX128)
            right = np.empty(local_rows, dtype=_COMPLEX128)
            for column in range(W6A_TOTAL_COLUMNS):
                az_store.read_column(column, left)
                for previous in range(column + 1):
                    az_store.read_column(previous, right)
                    value = np.vdot(left, right)
                    if column == previous:
                        value = complex(value.real, 0.0)
                    gram[column, previous] = value
                    gram[previous, column] = np.conjugate(value)
            del left, right
            cholesky = np.linalg.cholesky(gram)
            r_factor = np.asarray(cholesky.conjugate().T, dtype=_COMPLEX128)
            singular = np.linalg.svd(r_factor, compute_uv=False)
            threshold = _RANK_THRESHOLD_FACTOR * np.finfo(float).eps * max(1.0, singular[0])
            if int(np.count_nonzero(singular > threshold)) != W6A_TOTAL_COLUMNS:
                raise ValueError("W6A Gram rank is not 390")
            closure = np.linalg.norm(r_factor.conjugate().T @ r_factor - gram) / max(
                float(np.linalg.norm(gram)), np.finfo(float).tiny
            )
            if not np.isfinite(closure) or closure > W6A_NORMAL_CLOSURE_LIMIT:
                raise ValueError("W6A factor normal closure failed")
            return cls(
                specs=specs,
                z_data=data,
                z_indices=indices,
                z_indptr=indptr,
                gram=gram,
                r_factor=r_factor,
                az_store=az_store,
                global_rows=global_rows,
                ownership_range=(start, end),
                identity=identity,
                column_sha256=tuple(column_sha256),
                legacy_z_identity=legacy_z_identity,
                base_action_count=base_action_count,
                repeat_action_count=repeat_action_count,
                repeat_column_sha256=repeat_column_sha256,
            )
        except Exception:
            az_store.close()
            raise

    @property
    def audit(self) -> dict[str, Any]:
        z_bytes = int(self.z_data.nbytes + self.z_indices.nbytes + self.z_indptr.nbytes)
        r_bytes = int(self.r_factor.nbytes)
        vector_bytes = int(self.local_rows * _COMPLEX128.itemsize)
        return {
            "schema": W6A_SCHEMA,
            "global_rows": self.global_rows,
            "local_rows": self.local_rows,
            "ownership_range": list(self.ownership_range),
            "columns": W6A_TOTAL_COLUMNS,
            "legacy_columns": W6A_LEGACY_COLUMNS,
            "added_columns": W6A_ADDED_COLUMNS,
            "mpi_scope": "MPI1",
            "identity": self.identity,
            "factor_audit": dict(self.factor_audit),
            "action_counts": dict(self.action_counts),
            "repeat_columns": list(W6A_REPEAT_COLUMNS),
            "repeat_column_sha256": dict(self.repeat_column_sha256),
            "repeat_exact": self.repeat_exact,
            "az_column_count": len(self.column_sha256),
            "az_column_sha256_aggregate": _json_sha256(list(self.column_sha256)),
            "z_retained_bytes": z_bytes,
            "r_retained_bytes": r_bytes,
            "retained_z_r_bytes": z_bytes + r_bytes,
            "retained_z_r_gate": z_bytes + r_bytes <= 0.20 * 1024**3,
            "az_builder_only": True,
            "az_production_retained": False,
            "az_scratch_bytes": self.az_store.allocated_bytes,
            "az_scratch_mmap": False,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "phase_full_vector_buffers": {
                "construction": 2,
                "projection": 5,
            },
            "max_full_vector_buffers": 5,
            "full_vector_work_bytes": int(5 * vector_bytes),
            "bounded_work_bytes": int(5 * vector_bytes),
            "column_order": "legacy75_then_m_ascending_z_ascending_component_0_1_2",
            "legacy_z_identity": self.legacy_z_identity,
        }

    def _coefficients(self, values: np.ndarray, column_count: int) -> np.ndarray:
        values = np.asarray(values)
        if values.ndim != 1 or values.shape[0] != self.local_rows or values.dtype != _COMPLEX128:
            raise TypeError("W6A residual must be a complex128 local vector")
        if not np.all(np.isfinite(values)):
            raise ValueError("W6A residual is nonfinite")
        az = np.empty(self.local_rows, dtype=_COMPLEX128)
        h = np.empty(column_count, dtype=_COMPLEX128)
        for column in range(column_count):
            self.az_store.read_column(column, az)
            h[column] = np.vdot(az, values)
        factor = self.r_factor[:column_count, :column_count]
        y = solve_triangular(factor, h, trans="C", lower=False, check_finite=False)
        return solve_triangular(factor, y, lower=False, check_finite=False)

    def project_residual(
        self, values: np.ndarray, *, column_count: int = W6A_TOTAL_COLUMNS
    ) -> dict[str, Any]:
        if column_count not in (W6A_LEGACY_COLUMNS, W6A_TOTAL_COLUMNS):
            raise ValueError("W6A projection column count is not fixed")
        values = np.asarray(values)
        coefficients = self._coefficients(values, column_count)
        represented = np.zeros(self.local_rows, dtype=_COMPLEX128)
        az = np.empty(self.local_rows, dtype=_COMPLEX128)
        correction = np.zeros(self.local_rows, dtype=_COMPLEX128)
        for column, (first, last) in enumerate(
            zip(self.z_indptr[: column_count], self.z_indptr[1 : column_count + 1], strict=True)
        ):
            first_index, last_index = int(first), int(last)
            correction[self.z_indices[first_index:last_index]] += (
                self.z_data[first_index:last_index] * coefficients[column]
            )
            self.az_store.read_column(column, az)
            represented += coefficients[column] * az
        residual = values - represented
        norm = float(np.linalg.norm(values))
        rho = float(np.linalg.norm(residual) / max(norm, np.finfo(float).tiny))
        if not np.all(np.isfinite(correction)) or not np.isfinite(rho):
            raise ValueError("W6A projection is nonfinite")
        result = {
            "rho": rho,
            "column_count": column_count,
            "correction_sha256": _array_sha256(correction),
            "represented_action_sha256": _array_sha256(represented),
            "residual_sha256": _array_sha256(residual),
        }
        del az, correction, represented, residual, coefficients
        return result

    def compare_range_orders(self, values: np.ndarray) -> dict[str, Any]:
        legacy = self.project_residual(values, column_count=W6A_LEGACY_COLUMNS)
        nested = self.project_residual(values, column_count=W6A_TOTAL_COLUMNS)
        if not np.isfinite(legacy["rho"]) or legacy["rho"] <= 0.0:
            raise ValueError("W6A legacy range norm is invalid")
        return {
            "rho75": legacy["rho"],
            "rho390": nested["rho"],
            "relative_improvement": float(1.0 - nested["rho"] / legacy["rho"]),
            "legacy": legacy,
            "nested": nested,
        }

    def save(self, directory: Path) -> Path:
        directory = Path(directory)
        if directory.exists():
            raise FileExistsError(f"W6A store refuses existing directory: {directory}")
        directory.mkdir(parents=True)
        arrays = {
            "z_data": self.z_data,
            "z_indices": self.z_indices,
            "z_indptr": self.z_indptr,
            "gram": self.gram,
            "r_factor": self.r_factor,
        }
        descriptors: dict[str, Any] = {}
        for name, value in arrays.items():
            path = directory / f"{name}.npy"
            np.save(path, np.ascontiguousarray(value), allow_pickle=False)
            descriptors[name] = _array_meta(path, value)
        payload = {
            "schema": W6A_SCHEMA,
            "global_rows": self.global_rows,
            "ownership_range": list(self.ownership_range),
            "columns": W6A_TOTAL_COLUMNS,
            "column_specs": [spec.__dict__ for spec in self.specs],
            "identity": self.identity,
            "factor_audit": self.factor_audit,
            "action_counts": dict(self.action_counts),
            "repeat_columns": list(W6A_REPEAT_COLUMNS),
            "repeat_column_sha256": dict(self.repeat_column_sha256),
            "repeat_exact": self.repeat_exact,
            "column_sha256": list(self.column_sha256),
            "az_column_sha256_aggregate": _json_sha256(list(self.column_sha256)),
            "legacy_z_identity": self.legacy_z_identity,
            "arrays": descriptors,
            "az_scratch": {
                "path": str(self.az_store.path.resolve()),
                "bytes": self.az_store.allocated_bytes,
                "sha256": _file_sha256(self.az_store.path),
                "rows": self.local_rows,
                "capacity": W6A_TOTAL_COLUMNS,
            },
            "mmap": False,
            "dense_z_retained": False,
            "dense_az_retained": False,
        }
        payload["evidence_sha256"] = _json_sha256(payload)
        manifest_path = directory / "manifest.json"
        manifest_path.write_bytes(_json_bytes(payload) + b"\n")
        self._manifest_path = manifest_path
        self._manifest_file_bytes = int(manifest_path.stat().st_size)
        return manifest_path

    @classmethod
    def load(
        cls, manifest_path: Path, *, legacy_store_dir: Path
    ) -> "W6AMultiOrderRangeDiagnostic":
        validation = validate_w6a_store(
            manifest_path, legacy_store_dir=legacy_store_dir
        )
        if validation["pass"] is not True:
            raise ValueError("W6A store validation failed")
        manifest_path = Path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        directory = manifest_path.parent
        arrays = {
            name: _load_manifest_array(directory, name, manifest["arrays"][name])
            for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")
        }
        scratch = manifest["az_scratch"]
        az_store = RawPositionalColumnStore.open_readonly(
            Path(scratch["path"]), int(scratch["rows"]), int(scratch["capacity"])
        )
        try:
            return cls(
                specs=tuple(W6AColumnSpec(**item) for item in manifest["column_specs"]),
                z_data=arrays["z_data"],
                z_indices=arrays["z_indices"],
                z_indptr=arrays["z_indptr"],
                gram=arrays["gram"],
                r_factor=arrays["r_factor"],
                az_store=az_store,
                global_rows=int(manifest["global_rows"]),
                ownership_range=tuple(manifest["ownership_range"]),
                identity=manifest["identity"],
                column_sha256=tuple(manifest["column_sha256"]),
                legacy_z_identity=manifest["legacy_z_identity"],
                base_action_count=int(manifest["action_counts"]["base"]),
                repeat_action_count=int(manifest["action_counts"]["selected_repeat"]),
                repeat_column_sha256=manifest["repeat_column_sha256"],
            )
        except Exception:
            az_store.close()
            raise

    def close(self) -> None:
        self.az_store.close()


def _load_manifest_array(directory: Path, name: str, entry: Mapping[str, Any]) -> np.ndarray:
    if entry.get("path") != f"{name}.npy":
        raise ValueError(f"W6A {name} path is invalid")
    path = directory / entry["path"]
    if not path.is_file() or _file_sha256(path) != entry.get("file_sha256"):
        raise ValueError(f"W6A {name} file identity is invalid")
    value = np.load(path, allow_pickle=False, mmap_mode="r")
    if str(value.dtype) != entry.get("dtype") or list(value.shape) != entry.get("shape"):
        raise ValueError(f"W6A {name} shape/dtype is invalid")
    if _array_sha256(value) != entry.get("array_sha256"):
        raise ValueError(f"W6A {name} array identity is invalid")
    return value


def validate_w6a_store(
    manifest_path: Path, *, legacy_store_dir: Path
) -> dict[str, Any]:
    """Recompute the stored Gram/factor evidence from Z and raw AZ."""

    try:
        manifest_path = Path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, Mapping) or manifest.get("schema") != W6A_SCHEMA:
            raise ValueError("W6A manifest schema is invalid")
        if manifest.get("evidence_sha256") != _json_sha256(
            {key: value for key, value in manifest.items() if key != "evidence_sha256"}
        ):
            raise ValueError("W6A manifest evidence SHA is invalid")
        if tuple(manifest.get("column_specs", ())) != tuple(
            spec.__dict__ for spec in fixed_w6a_column_specs()
        ):
            raise ValueError("W6A column specification is invalid")
        if manifest.get("columns") != W6A_TOTAL_COLUMNS:
            raise ValueError("W6A column count is invalid")
        if manifest.get("ownership_range") != [0, manifest.get("global_rows")]:
            raise ValueError("W6A store is not MPI1 full ownership")
        directory = manifest_path.parent
        if set(manifest.get("arrays", {})) != {"z_data", "z_indices", "z_indptr", "gram", "r_factor"}:
            raise ValueError("W6A store array set is invalid")
        arrays = {
            name: _load_manifest_array(directory, name, manifest["arrays"][name])
            for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")
        }
        z_data = np.asarray(arrays["z_data"])
        z_indices = np.asarray(arrays["z_indices"])
        z_indptr = np.asarray(arrays["z_indptr"])
        gram_array = np.asarray(arrays["gram"])
        r_factor_array = np.asarray(arrays["r_factor"])
        if (
            z_data.ndim != 1
            or z_indices.ndim != 1
            or z_indptr.ndim != 1
            or z_data.dtype != _COMPLEX128
            or z_indices.dtype != _INDEX_DTYPE
            or z_indptr.dtype != _INDEX_DTYPE
            or z_indptr.shape != (W6A_TOTAL_COLUMNS + 1,)
            or int(z_indptr[0]) != 0
            or int(z_indptr[-1]) != z_data.size
            or z_data.size != z_indices.size
            or np.any(z_indptr[1:] < z_indptr[:-1])
            or np.any(z_indices < 0)
            or np.any(z_indices >= int(manifest["global_rows"]))
            or gram_array.shape != (W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS)
            or r_factor_array.shape != (W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS)
        ):
            raise ValueError("W6A array structure is invalid")
        action_counts = manifest.get("action_counts")
        if action_counts != {"base": 390, "selected_repeat": 4, "total": 394}:
            raise ValueError("W6A action counts are invalid")
        if manifest.get("repeat_columns") != list(W6A_REPEAT_COLUMNS):
            raise ValueError("W6A repeat columns are invalid")
        repeat_hashes = manifest.get("repeat_column_sha256")
        if (
            not isinstance(repeat_hashes, Mapping)
            or set(repeat_hashes) != {str(column) for column in W6A_REPEAT_COLUMNS}
            or any(
                not isinstance(repeat_hashes[key], str) or len(repeat_hashes[key]) != 64
                for key in repeat_hashes
            )
            or manifest.get("repeat_exact") is not True
        ):
            raise ValueError("W6A repeat audit is invalid")
        column_manifest_hashes = manifest.get("column_sha256")
        if (
            not isinstance(column_manifest_hashes, list)
            or len(column_manifest_hashes) != W6A_TOTAL_COLUMNS
            or any(
                not isinstance(item, str) or len(item) != 64
                for item in column_manifest_hashes
            )
        ):
            raise ValueError("W6A column hash list is invalid")
        scratch = manifest["az_scratch"]
        scratch_path = Path(scratch["path"])
        if (
            not scratch_path.is_file()
            or scratch_path.stat().st_size != scratch["bytes"]
            or _file_sha256(scratch_path) != scratch["sha256"]
            or scratch["rows"] != manifest["global_rows"]
            or scratch["capacity"] != W6A_TOTAL_COLUMNS
        ):
            raise ValueError("W6A AZ scratch identity is invalid")
        rows = int(scratch["rows"])
        az_store = RawPositionalColumnStore.open_readonly(
            scratch_path, rows, int(scratch["capacity"])
        )
        az_reads = 0
        try:
            gram = np.zeros((W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS), dtype=_COMPLEX128)
            left = np.empty(rows, dtype=_COMPLEX128)
            right = np.empty(rows, dtype=_COMPLEX128)
            column_hashes: list[str] = []
            for column in range(W6A_TOTAL_COLUMNS):
                az_store.read_column(column, left)
                column_hashes.append(_array_sha256(left))
                for previous in range(column + 1):
                    az_store.read_column(previous, right)
                    value = np.vdot(left, right)
                    if column == previous:
                        value = complex(value.real, 0.0)
                    gram[column, previous] = value
                    gram[previous, column] = np.conjugate(value)
            az_reads = az_store.read_count
        finally:
            az_store.close()
        if (
            _json_sha256(column_hashes[:W6A_LEGACY_COLUMNS])
            != W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE
        ):
            raise ValueError("W6A raw first 75 AZ authority differs")
        if not np.array_equal(gram, np.asarray(arrays["gram"])):
            raise ValueError("W6A Gram recomputation differs")
        if manifest.get("column_sha256") != column_hashes:
            raise ValueError("W6A AZ column identity differs")
        if any(
            repeat_hashes[str(column)] != column_hashes[column]
            for column in W6A_REPEAT_COLUMNS
        ):
            raise ValueError("W6A selected AZ repeat identity differs")
        if manifest.get("az_column_sha256_aggregate") != _json_sha256(column_hashes):
            raise ValueError("W6A AZ column aggregate differs")
        authority = load_w1a_legacy_basis(legacy_store_dir)
        legacy_z_identity = manifest.get("legacy_z_identity")
        if not isinstance(legacy_z_identity, Mapping):
            raise ValueError("W6A legacy Z identity is missing")
        legacy_nnz = int(np.asarray(arrays["z_indptr"])[W6A_LEGACY_COLUMNS])
        if (
            legacy_z_identity.get("basis_manifest_sha256")
            != W6A_LEGACY_BASIS_MANIFEST_SHA256
            or legacy_z_identity.get("manifest_file_sha256")
            != authority["manifest_file_sha256"]
            or legacy_z_identity.get("az_column_sha256_aggregate")
            != authority["az_column_sha256_aggregate"]
            or legacy_z_identity.get("nnz") != legacy_nnz
            or legacy_z_identity.get("z_data_array_sha256")
            != _array_sha256(np.asarray(arrays["z_data"])[:legacy_nnz])
            or legacy_z_identity.get("z_indices_array_sha256")
            != _array_sha256(np.asarray(arrays["z_indices"])[:legacy_nnz])
            or legacy_z_identity.get("z_indptr_array_sha256")
            != _array_sha256(np.asarray(arrays["z_indptr"])[: W6A_LEGACY_COLUMNS + 1])
        ):
            raise ValueError("W6A first 75 Z identity differs")
        if (
            not np.array_equal(
                np.asarray(arrays["z_data"])[:legacy_nnz], authority["z_data"]
            )
            or not np.array_equal(
                np.asarray(arrays["z_indices"])[:legacy_nnz], authority["z_indices"]
            )
            or not np.array_equal(
                np.asarray(arrays["z_indptr"])[: W6A_LEGACY_COLUMNS + 1],
                authority["z_indptr"],
            )
        ):
            raise ValueError("W6A first 75 Z arrays differ from W1A store")
        r_factor = np.asarray(arrays["r_factor"])
        factor_audit = manifest.get("factor_audit")
        if not isinstance(factor_audit, Mapping):
            raise ValueError("W6A factor audit is missing")
        if (
            r_factor.shape != (W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS)
            or r_factor.dtype != _COMPLEX128
            or not np.all(np.isfinite(r_factor))
            or not np.array_equal(r_factor, np.triu(r_factor))
            or not np.all(np.real(np.diag(r_factor)) > 0.0)
        ):
            raise ValueError("W6A factor shape or triangularity is invalid")
        closure = float(
            np.linalg.norm(r_factor.conjugate().T @ r_factor - gram)
            / max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
        )
        if not np.isfinite(closure) or closure > W6A_NORMAL_CLOSURE_LIMIT:
            raise ValueError("W6A factor normal closure differs")
        gram_defect = float(
            np.linalg.norm(gram - gram.conjugate().T)
            / max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
        )
        if not np.isfinite(gram_defect) or gram_defect > W6A_NORMAL_CLOSURE_LIMIT:
            raise ValueError("W6A Gram Hermitian defect failed")
        singular = np.linalg.svd(r_factor, compute_uv=False)
        threshold = float(
            _RANK_THRESHOLD_FACTOR * np.finfo(float).eps * max(1.0, singular[0])
        )
        rank = int(np.count_nonzero(singular > threshold))
        if rank != W6A_TOTAL_COLUMNS:
            raise ValueError("W6A factor rank is invalid")
        if float(factor_audit["rank"]) != rank:
            raise ValueError("W6A factor audit rank differs")
        for key, actual in (
            ("rank_threshold", threshold),
            ("r_singular_max", float(singular[0])),
            ("r_singular_min", float(singular[-1])),
            ("condition_estimate", float(singular[0] / singular[-1])),
        ):
            recorded = factor_audit[key]
            if not np.isfinite(recorded) or not np.isclose(
                float(recorded), actual, rtol=64.0 * np.finfo(float).eps, atol=0.0
            ):
                raise ValueError(f"W6A factor audit {key} differs")
        if float(factor_audit["normal_closure"]) > W6A_NORMAL_CLOSURE_LIMIT:
            raise ValueError("W6A recorded normal closure gate failed")
        if not np.isclose(
            float(factor_audit["normal_closure"]),
            closure,
            rtol=64.0 * np.finfo(float).eps,
            atol=0.0,
        ) or not np.isclose(
            float(factor_audit["gram_hermitian_defect"]),
            gram_defect,
            rtol=64.0 * np.finfo(float).eps,
            atol=0.0,
        ):
            raise ValueError("W6A recorded Gram/factor audit differs")
        expected_files = {
            "manifest.json",
            "z_data.npy",
            "z_indices.npy",
            "z_indptr.npy",
            "gram.npy",
            "r_factor.npy",
        }
        if {path.name for path in directory.iterdir()} != expected_files:
            raise ValueError("W6A store file set is invalid")
        return {
            "pass": True,
            "schema": W6A_SCHEMA,
            "columns": W6A_TOTAL_COLUMNS,
            "rank": rank,
            "normal_closure": closure,
            "az_reads": az_reads,
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}
