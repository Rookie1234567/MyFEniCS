"""Fixed W8A z-bubble enrichment over the frozen W6A range carrier.

The old 390 ``A Z`` columns stay in their frozen positional file.  W8A owns
only a second 140-column positional file for the new bubbles; a small reader
combines the two files for Gram and projection operations.
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
    _array_meta,
    _array_sha256,
    _file_sha256,
    _json_bytes,
    _json_sha256,
)
from src.solvers.hcurl_m6b_w6a_multi_order_range import (
    W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
    W6A_SCHEMA,
    W6A_TOTAL_COLUMNS,
    W6ASparseColumn,
    _load_manifest_array,
    fixed_w6a_column_specs,
    w6a_actual_z_planes,
    w6a_phase,
)

__all__ = [
    "W8A_SCHEMA",
    "W8A_LEGACY_COLUMNS",
    "W8A_BUBBLE_ORDERS",
    "W8A_BUBBLE_COMPONENT",
    "W8A_INTERVALS",
    "W8A_BUBBLE_DEGREES",
    "W8A_ADDED_COLUMNS",
    "W8A_TOTAL_COLUMNS",
    "W8A_REPEAT_COLUMNS",
    "W8A_NORMAL_CLOSURE_LIMIT",
    "W8AColumnSpec",
    "w8a_bubble_basis",
    "w8a_bubble_value",
    "fixed_w8a_column_specs",
    "build_w8a_bubble_columns_from_fe",
    "load_w6a_legacy_for_w8a",
    "W8AMultiOrderRangeDiagnostic",
    "validate_w8a_store",
]


W8A_SCHEMA = "task037.extra.m6b.w8a.z-bubble-range.v1"
W8A_LEGACY_COLUMNS = W6A_TOTAL_COLUMNS
W8A_BUBBLE_ORDERS = (-7, -6)
W8A_BUBBLE_COMPONENT = 1
W8A_INTERVALS = 14
W8A_BUBBLE_DEGREES = (2, 3, 4, 5, 6)
W8A_ADDED_COLUMNS = len(W8A_BUBBLE_ORDERS) * W8A_INTERVALS * len(W8A_BUBBLE_DEGREES)
W8A_TOTAL_COLUMNS = W8A_LEGACY_COLUMNS + W8A_ADDED_COLUMNS
W8A_REPEAT_COLUMNS = (390, 459, 529)
W8A_NORMAL_CLOSURE_LIMIT = 1.0e-11
_COMPLEX128 = np.dtype(np.complex128)
_INDEX_DTYPE = np.dtype(np.int32)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class W8AColumnSpec:
    column_index: int
    family: str
    order_m: int
    interval: int
    bubble_degree: int
    component: int


def fixed_w8a_column_specs() -> tuple[W8AColumnSpec, ...]:
    result = tuple(
        W8AColumnSpec(spec.column_index, "legacy_w6a", spec.order_m, -1, 0, spec.component)
        for spec in fixed_w6a_column_specs()
    )
    added: list[W8AColumnSpec] = []
    index = W8A_LEGACY_COLUMNS
    for order_m in W8A_BUBBLE_ORDERS:
        for interval in range(W8A_INTERVALS):
            for degree in W8A_BUBBLE_DEGREES:
                added.append(
                    W8AColumnSpec(
                        index, "z_bubble_n0", order_m, interval, degree, W8A_BUBBLE_COMPONENT
                    )
                )
                index += 1
    output = result + tuple(added)
    _require(len(output) == W8A_TOTAL_COLUMNS, "W8A fixed column count is invalid")
    return output


def w8a_bubble_basis(xi: np.ndarray | float) -> np.ndarray:
    """Return fixed ``P_k-P_(k-2)`` bubbles for k=2..6."""

    values = np.asarray(xi, dtype=np.float64)
    flat = values.reshape(-1)
    _require(np.all(np.isfinite(flat)), "W8A bubble coordinates are nonfinite")
    polynomials = [np.ones_like(flat), flat.copy()]
    for degree in range(2, 7):
        polynomials.append(
            ((2.0 * degree - 1.0) * flat * polynomials[-1]
             - (degree - 1.0) * polynomials[-2])
            / degree
        )
    output = np.stack(
        [polynomials[degree] - polynomials[degree - 2] for degree in W8A_BUBBLE_DEGREES]
    )
    endpoint = (values == -1.0) | (values == 1.0)
    output[:, endpoint.reshape(-1)] = 0.0
    return output.reshape((len(W8A_BUBBLE_DEGREES),) + values.shape)


def w8a_bubble_value(
    z: np.ndarray | float,
    planes: np.ndarray,
    interval: int,
    degree: int,
) -> np.ndarray:
    values = np.asarray(z, dtype=np.float64)
    planes = np.asarray(planes, dtype=np.float64)
    _require(
        planes.ndim == 1
        and planes.size == W8A_INTERVALS + 1
        and np.all(np.isfinite(planes))
        and np.all(np.diff(planes) > 0.0),
        "W8A z planes are invalid",
    )
    if type(interval) is not int or not 0 <= interval < W8A_INTERVALS:
        raise ValueError("W8A interval is invalid")
    if degree not in W8A_BUBBLE_DEGREES:
        raise ValueError("W8A bubble degree is invalid")
    flat = values.reshape(-1)
    result = np.zeros_like(flat, dtype=np.float64)
    left, right = float(planes[interval]), float(planes[interval + 1])
    inside = (flat > left) & (flat < right)
    if np.any(inside):
        xi = 2.0 * (flat[inside] - left) / (right - left) - 1.0
        result[inside] = w8a_bubble_basis(xi)[degree - 2]
    return result.reshape(values.shape)


def build_w8a_bubble_columns_from_fe(
    function_space: Any,
    mesh_data: Any,
    floquet: Any,
    template: Any,
    cfg: Any,
    *,
    ownership_range: tuple[int, int],
) -> tuple[tuple[W6ASparseColumn, ...], dict[str, Any]]:
    """Build the 140 fixed bubbles through interpolate/MPC/compress."""

    from dolfinx import fem
    from src.solvers.physical_slab_two_level import compress_petsc_vector

    start, end = map(int, ownership_range)
    _require(start == 0 and end == int(template.getSize()), "W8A FE ownership is not MPI1")
    planes = w6a_actual_z_planes(mesh_data, cfg)
    _require(planes.size == W8A_INTERVALS + 1, "W8A requires fifteen mesh planes")
    period_x = float(cfg.period_x)
    _require(np.isfinite(period_x) and period_x > 0.0, "W8A period_x is invalid")
    field = fem.Function(function_space)
    vector = template.duplicate()
    columns: list[W6ASparseColumn] = []
    column_audit: list[dict[str, Any]] = []
    try:
        for spec in fixed_w8a_column_specs()[W8A_LEGACY_COLUMNS:]:

            def value(x, *, spec=spec):
                envelope = w8a_bubble_value(x[2], planes, spec.interval, spec.bubble_degree)
                phase = w6a_phase(
                    x[0], x[1], kx=complex(cfg.kx), ky=complex(cfg.ky),
                    period_x=period_x, order_m=spec.order_m,
                )
                result = np.zeros((3, x.shape[1]), dtype=np.complex128)
                result[W8A_BUBBLE_COMPONENT, :] = envelope * phase
                return result

            field.interpolate(value)
            floquet.mpc.homogenize(field)
            source = np.asarray(field.x.petsc_vec.getArray(readonly=True), dtype=np.complex128)
            target = vector.getArray()
            _require(source.size >= target.size, "W8A FE/MPC owned prefix is too short")
            np.copyto(target, source[: target.size])
            vector.assemble()
            compressed = compress_petsc_vector(vector)
            indices = np.asarray(compressed.indices, dtype=_INDEX_DTYPE)
            values = np.asarray(compressed.values, dtype=_COMPLEX128)
            norm = float(np.linalg.norm(values))
            _require(
                np.isfinite(norm) and norm > 0.0 and abs(norm - 1.0) <= 1.0e-11
                and np.all(np.isfinite(values)),
                "W8A compressed FE column is not normalized",
            )
            columns.append(W6ASparseColumn(indices.copy(), values.copy()))
            column_audit.append({
                "column_index": spec.column_index,
                "order_m": spec.order_m,
                "interval": spec.interval,
                "bubble_degree": spec.bubble_degree,
                "component": spec.component,
                "nnz": int(indices.size),
                "norm": norm,
                "indices_array_sha256": _array_sha256(indices),
                "values_array_sha256": _array_sha256(values),
            })
    finally:
        vector.destroy()
        del field
    return tuple(columns), {
        "z_planes": planes.tolist(),
        "domain_z_min": float(cfg.domain_z_min),
        "domain_z_max": float(cfg.domain_z_max),
        "z_planes_array_sha256": _array_sha256(planes),
        "column_audit": column_audit,
        "column_count": len(columns),
        "fixed_order": True,
        "dense_candidates_retained": False,
        "component": W8A_BUBBLE_COMPONENT,
        "diffraction_orders": list(W8A_BUBBLE_ORDERS),
        "bubble_degrees": list(W8A_BUBBLE_DEGREES),
    }


class _CompositeAZReader:
    """Read old W6A columns or new W8A columns without copying either file."""

    def __init__(self, old_store: RawPositionalColumnStore, new_store: RawPositionalColumnStore):
        self.old_store = old_store
        self.new_store = new_store

    def read_column(self, index: int, target: np.ndarray) -> None:
        if index < W8A_LEGACY_COLUMNS:
            self.old_store.read_column(index, target)
        else:
            self.new_store.read_column(index - W8A_LEGACY_COLUMNS, target)

    def audit(self) -> dict[str, Any]:
        return {"old": self.old_store.audit(), "new": self.new_store.audit()}


def _factor_audit(gram: np.ndarray, r_factor: np.ndarray) -> dict[str, Any]:
    norm = max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
    singular = np.linalg.svd(r_factor, compute_uv=False)
    threshold = float(128.0 * np.finfo(float).eps * max(1.0, singular[0]))
    return {
        "rank": int(np.count_nonzero(singular > threshold)),
        "rank_threshold": threshold,
        "gram_hermitian_defect": float(np.linalg.norm(gram - gram.conjugate().T) / norm),
        "normal_closure": float(np.linalg.norm(r_factor.conjugate().T @ r_factor - gram) / norm),
        "normal_closure_limit": W8A_NORMAL_CLOSURE_LIMIT,
        "r_singular_max": float(singular[0]),
        "r_singular_min": float(singular[-1]),
        "condition_estimate": float(singular[0] / singular[-1]),
        "r_upper_triangular": bool(np.array_equal(r_factor, np.triu(r_factor))),
        "r_positive_diagonal": bool(np.all(np.real(np.diag(r_factor)) > 0.0)),
    }


def load_w6a_legacy_for_w8a(
    legacy_store_dir: Path,
) -> tuple[dict[str, Any], dict[str, np.ndarray], RawPositionalColumnStore]:
    """Load W6A arrays and its frozen AZ scratch without making copies."""

    root = Path(legacy_store_dir).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(manifest.get("schema") == W6A_SCHEMA, "W8A W6A schema differs")
    _require(
        manifest.get("evidence_sha256")
        == _json_sha256({key: value for key, value in manifest.items() if key != "evidence_sha256"}),
        "W8A W6A evidence differs",
    )
    arrays = {
        name: _load_manifest_array(root, name, manifest["arrays"][name])
        for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")
    }
    _require(
        arrays["z_data"].dtype == _COMPLEX128
        and arrays["z_indices"].dtype == _INDEX_DTYPE
        and arrays["z_indptr"].dtype == _INDEX_DTYPE
        and arrays["z_indptr"].shape == (W8A_LEGACY_COLUMNS + 1,)
        and arrays["z_data"].size == arrays["z_indices"].size == int(arrays["z_indptr"][-1])
        and arrays["gram"].shape == (W8A_LEGACY_COLUMNS, W8A_LEGACY_COLUMNS)
        and arrays["r_factor"].shape == arrays["gram"].shape,
        "W8A W6A arrays are invalid",
    )
    hashes = manifest.get("column_sha256")
    _require(
        isinstance(hashes, list)
        and len(hashes) == W8A_LEGACY_COLUMNS
        and _json_sha256(hashes[:75]) == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE
        and _json_sha256(hashes) == manifest.get("az_column_sha256_aggregate"),
        "W8A W6A AZ hash authority differs",
    )
    scratch = manifest["az_scratch"]
    scratch_path = Path(scratch["path"]).resolve()
    _require(
        scratch_path.is_file()
        and scratch_path.stat().st_size == scratch["bytes"]
        and _file_sha256(scratch_path) == scratch["sha256"]
        and scratch["rows"] == manifest["global_rows"]
        and scratch["capacity"] == W8A_LEGACY_COLUMNS,
        "W8A W6A AZ scratch authority differs",
    )
    store = RawPositionalColumnStore.open_readonly(
        scratch_path, int(manifest["global_rows"]), W8A_LEGACY_COLUMNS
    )
    return {
        "manifest_file_sha256": _file_sha256(manifest_path),
        "column_sha256": tuple(hashes),
        "az_column_sha256_aggregate": manifest["az_column_sha256_aggregate"],
        "az_scratch": {
            "path": str(scratch_path),
            "bytes": int(scratch["bytes"]),
            "sha256": scratch["sha256"],
            "rows": int(scratch["rows"]),
            "capacity": int(scratch["capacity"]),
        },
    }, arrays, store


class W8AMultiOrderRangeDiagnostic:
    """Composite 530-column range carrier with only the new AZ on disk."""

    def __init__(
        self,
        *,
        specs: tuple[W8AColumnSpec, ...],
        z_data: np.ndarray,
        z_indices: np.ndarray,
        z_indptr: np.ndarray,
        gram: np.ndarray,
        r_factor: np.ndarray,
        old_az_store: RawPositionalColumnStore,
        new_az_store: RawPositionalColumnStore,
        global_rows: int,
        identity: Mapping[str, Any],
        column_sha256: tuple[str, ...],
        legacy_z_identity: Mapping[str, Any],
        action_counts: Mapping[str, int],
        repeat_column_sha256: Mapping[str, str],
    ) -> None:
        _require(tuple(specs) == fixed_w8a_column_specs(), "W8A column specs differ")
        _require(
            z_data.dtype == _COMPLEX128 and z_indices.dtype == _INDEX_DTYPE
            and z_indptr.dtype == _INDEX_DTYPE and z_indptr.shape == (W8A_TOTAL_COLUMNS + 1,)
            and z_data.size == z_indices.size == int(z_indptr[-1]),
            "W8A sparse arrays differ",
        )
        _require(gram.shape == (W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS) and r_factor.shape == gram.shape, "W8A factor shape differs")
        _require(
            dict(action_counts) == {"frozen_legacy": 0, "new_base": 140, "selected_repeat": 3, "total": 143},
            "W8A action counts differ",
        )
        self.specs = tuple(specs)
        self.z_data, self.z_indices, self.z_indptr = z_data, z_indices, z_indptr
        self.gram, self.r_factor = gram, r_factor
        self.old_az_store, self.new_az_store = old_az_store, new_az_store
        self.az_reader = _CompositeAZReader(old_az_store, new_az_store)
        self.global_rows = int(global_rows)
        self.local_rows = self.global_rows
        self.ownership_range = (0, self.global_rows)
        self.identity = dict(identity)
        self.column_sha256 = tuple(column_sha256)
        self.legacy_z_identity = dict(legacy_z_identity)
        self.action_counts = dict(action_counts)
        self.repeat_column_sha256 = dict(repeat_column_sha256)
        self.repeat_exact = all(
            self.repeat_column_sha256.get(str(column)) == self.column_sha256[column]
            for column in W8A_REPEAT_COLUMNS
        )
        _require(self.repeat_exact, "W8A repeat hashes differ")
        self.factor_audit = _factor_audit(self.gram, self.r_factor)
        self._manifest_path: Path | None = None

    @classmethod
    def from_legacy_and_added(
        cls,
        legacy: Mapping[str, Any],
        added_columns: Sequence[W6ASparseColumn],
        action: Callable[[np.ndarray], np.ndarray],
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        scratch_dir: Path,
        identity: Mapping[str, Any],
        progress: Callable[[str, int, int], None] | None = None,
    ) -> "W8AMultiOrderRangeDiagnostic":
        if not callable(action):
            raise TypeError("W8A action must be callable")
        _require(tuple(map(int, ownership_range)) == (0, int(global_rows)), "W8A ownership is not MPI1")
        _require(len(added_columns) == W8A_ADDED_COLUMNS, "W8A requires 140 added columns")
        old_data, old_indices, old_indptr = legacy["z_data"], legacy["z_indices"], legacy["z_indptr"]
        old_gram = legacy["gram"]
        added = tuple(added_columns)
        for index, column in enumerate(added, W8A_LEGACY_COLUMNS):
            _require(isinstance(column, W6ASparseColumn), f"W8A column {index} is invalid")
            _require(column.indices.size == 0 or int(column.indices[-1]) < global_rows, f"W8A column {index} is outside ownership")
        added_nnz = np.asarray([column.indices.size for column in added], dtype=np.int64)
        indptr = np.empty(W8A_TOTAL_COLUMNS + 1, dtype=_INDEX_DTYPE)
        indptr[: W8A_LEGACY_COLUMNS + 1] = old_indptr
        indptr[W8A_LEGACY_COLUMNS + 1 :] = (int(old_indptr[-1]) + np.cumsum(added_nnz)).astype(_INDEX_DTYPE)
        added_indices = np.concatenate([column.indices for column in added]).astype(_INDEX_DTYPE, copy=False)
        added_data = np.concatenate([column.values for column in added]).astype(_COMPLEX128, copy=False)
        z_indices = np.concatenate((old_indices, added_indices)).astype(_INDEX_DTYPE, copy=False)
        z_data = np.concatenate((old_data, added_data)).astype(_COMPLEX128, copy=False)
        scratch_dir = Path(scratch_dir)
        if scratch_dir.exists():
            raise FileExistsError(f"W8A new AZ scratch already exists: {scratch_dir}")
        scratch_dir.mkdir(parents=True)
        new_store = RawPositionalColumnStore(
            scratch_dir / "new_columns.bin", global_rows, W8A_ADDED_COLUMNS
        )
        old_store = legacy["az_store"]
        old_hashes = tuple(legacy["column_sha256"])
        old_buffer = np.empty(global_rows, dtype=_COMPLEX128)
        new_buffer = np.empty_like(old_buffer)
        column_hashes = list(old_hashes)
        repeat_hashes: dict[str, str] = {}
        vector = np.zeros(global_rows, dtype=_COMPLEX128)
        try:
            for column in range(W8A_LEGACY_COLUMNS):
                old_store.read_column(column, old_buffer)
                _require(
                    _array_sha256(old_buffer) == old_hashes[column],
                    "W8A frozen W6A AZ column differs",
                )
            for column in range(W8A_LEGACY_COLUMNS, W8A_TOTAL_COLUMNS):
                first, last = int(indptr[column]), int(indptr[column + 1])
                vector.fill(0.0)
                vector[z_indices[first:last]] = z_data[first:last]
                observed = np.asarray(action(vector))
                _require(observed.dtype == _COMPLEX128 and observed.shape == (global_rows,) and np.all(np.isfinite(observed)), f"W8A AZ column {column} is invalid")
                new_store.write_column(column - W8A_LEGACY_COLUMNS, np.ascontiguousarray(observed))
                column_hashes.append(_array_sha256(observed))
                if progress is not None:
                    progress("column_progress", column - W8A_LEGACY_COLUMNS + 1, W8A_ADDED_COLUMNS)
            for column in W8A_REPEAT_COLUMNS:
                first, last = int(indptr[column]), int(indptr[column + 1])
                vector.fill(0.0)
                vector[z_indices[first:last]] = z_data[first:last]
                observed = np.asarray(action(vector))
                _require(observed.dtype == _COMPLEX128 and observed.shape == (global_rows,) and np.all(np.isfinite(observed)), f"W8A repeat {column} is invalid")
                repeat_hashes[str(column)] = _array_sha256(observed)
                if progress is not None:
                    progress("repeat_ready", column, len(repeat_hashes))
            del vector
            _require(_json_sha256(column_hashes[:75]) == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE, "W8A W1A AZ authority differs")
            _require(_json_sha256(column_hashes[:W8A_LEGACY_COLUMNS]) == legacy["az_column_sha256_aggregate"], "W8A W6A AZ authority differs")
            _require(all(repeat_hashes[str(column)] == column_hashes[column] for column in W8A_REPEAT_COLUMNS), "W8A repeats are not exact")
            if progress is not None:
                progress("az_ready", W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS)
            reader = _CompositeAZReader(old_store, new_store)
            gram = np.zeros((W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS), dtype=_COMPLEX128)
            gram[:W8A_LEGACY_COLUMNS, :W8A_LEGACY_COLUMNS] = old_gram
            for column in range(W8A_LEGACY_COLUMNS, W8A_TOTAL_COLUMNS):
                reader.read_column(column, old_buffer)
                for previous in range(column + 1):
                    reader.read_column(previous, new_buffer)
                    value = np.vdot(old_buffer, new_buffer)
                    if column == previous:
                        value = complex(value.real, 0.0)
                    gram[column, previous] = value
                    gram[previous, column] = np.conjugate(value)
            r_factor = np.asarray(np.linalg.cholesky(gram).conjugate().T, dtype=_COMPLEX128)
            factor = _factor_audit(gram, r_factor)
            _require(factor["rank"] == W8A_TOTAL_COLUMNS and factor["normal_closure"] <= W8A_NORMAL_CLOSURE_LIMIT and factor["gram_hermitian_defect"] <= W8A_NORMAL_CLOSURE_LIMIT, "W8A factor Gate failed")
            result = cls(
                specs=fixed_w8a_column_specs(), z_data=z_data, z_indices=z_indices, z_indptr=indptr,
                gram=gram, r_factor=r_factor, old_az_store=old_store, new_az_store=new_store,
                global_rows=global_rows, identity=identity, column_sha256=tuple(column_hashes),
                legacy_z_identity={
                    "manifest_file_sha256": legacy["manifest_file_sha256"],
                    "az_column_sha256_aggregate": legacy["az_column_sha256_aggregate"],
                    "combined_az_column_sha256_aggregate": _json_sha256(column_hashes),
                    "z_data_array_sha256": _array_sha256(old_data),
                    "z_indices_array_sha256": _array_sha256(old_indices),
                    "z_indptr_array_sha256": _array_sha256(old_indptr),
                    "az_scratch": dict(legacy["az_scratch"]),
                },
                action_counts={"frozen_legacy": 0, "new_base": W8A_ADDED_COLUMNS, "selected_repeat": len(W8A_REPEAT_COLUMNS), "total": W8A_ADDED_COLUMNS + len(W8A_REPEAT_COLUMNS)},
                repeat_column_sha256=repeat_hashes,
            )
            if progress is not None:
                progress("gram_ready", W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS)
            return result
        except Exception:
            new_store.close()
            raise
        finally:
            del old_buffer, new_buffer

    @property
    def audit(self) -> dict[str, Any]:
        vector_bytes = self.global_rows * 16
        z_bytes = int(self.z_data.nbytes + self.z_indices.nbytes + self.z_indptr.nbytes)
        r_bytes = int(self.r_factor.nbytes)
        return {
            "schema": W8A_SCHEMA,
            "global_rows": self.global_rows,
            "ownership_range": [0, self.global_rows],
            "columns": W8A_TOTAL_COLUMNS,
            "legacy_columns": W8A_LEGACY_COLUMNS,
            "added_columns": W8A_ADDED_COLUMNS,
            "bubble_orders": list(W8A_BUBBLE_ORDERS),
            "bubble_component": W8A_BUBBLE_COMPONENT,
            "intervals": W8A_INTERVALS,
            "bubble_degrees": list(W8A_BUBBLE_DEGREES),
            "action_counts": dict(self.action_counts),
            "repeat_columns": list(W8A_REPEAT_COLUMNS),
            "repeat_column_sha256": dict(self.repeat_column_sha256),
            "repeat_exact": self.repeat_exact,
            "combined_az_column_sha256_aggregate": _json_sha256(list(self.column_sha256)),
            "legacy_az_column_sha256_aggregate": self.legacy_z_identity["az_column_sha256_aggregate"],
            "z_retained_bytes": z_bytes,
            "r_retained_bytes": r_bytes,
            "retained_z_r_bytes": z_bytes + r_bytes,
            "retained_z_r_gate": z_bytes + r_bytes <= int(0.20 * 1024**3),
            "az_builder_only": True,
            "az_production_retained": False,
            "old_az_production_retained": False,
            "new_az_scratch_bytes": self.new_az_store.allocated_bytes,
            "new_az_scratch_mmap": False,
            "old_az_read_count": self.old_az_store.read_count,
            "new_az_read_count": self.new_az_store.read_count,
            "new_az_write_count": self.new_az_store.write_count,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "phase_full_vector_buffers": {"construction": 2, "gram": 2, "projection": 5},
            "max_full_vector_buffers": 5,
            "bounded_work_bytes": int(5 * vector_bytes),
            "full_vector_work_bytes": int(5 * vector_bytes),
            "column_order": "frozen_w6a_390_then_m_minus7_minus6_component1_interval_ascending_degree_2_to_6",
            "legacy_z_identity": dict(self.legacy_z_identity),
        }

    def _coefficients(self, values: np.ndarray, column_count: int) -> tuple[np.ndarray, float, float]:
        values = np.asarray(values)
        _require(values.dtype == _COMPLEX128 and values.shape == (self.global_rows,) and np.all(np.isfinite(values)), "W8A residual is invalid")
        _require(column_count in (W8A_LEGACY_COLUMNS, W8A_TOTAL_COLUMNS), "W8A projection count is invalid")
        h = np.empty(column_count, dtype=_COMPLEX128)
        az = np.empty(self.global_rows, dtype=_COMPLEX128)
        for column in range(column_count):
            self.az_reader.read_column(column, az)
            h[column] = np.vdot(az, values)
        factor = self.r_factor[:column_count, :column_count]
        y = solve_triangular(factor, h, trans="C", lower=False, check_finite=False)
        coefficients = solve_triangular(factor, y, lower=False, check_finite=False)
        gram = self.gram[:column_count, :column_count]
        normal = float(np.linalg.norm(gram @ coefficients - h) / max(float(np.linalg.norm(h)), np.finfo(float).tiny))
        captured = float(np.real(np.vdot(h, coefficients)))
        rhs_norm_sq = float(np.vdot(values, values).real)
        _require(np.isfinite(normal) and normal <= W8A_NORMAL_CLOSURE_LIMIT and np.isfinite(captured) and captured >= -1.0e-11 * max(rhs_norm_sq, 1.0), "W8A projection closure failed")
        return coefficients, max(captured, 0.0), normal

    def project_residual(self, values: np.ndarray, *, column_count: int) -> dict[str, Any]:
        coefficients, captured, normal = self._coefficients(values, column_count)
        del coefficients
        rhs_norm_sq = float(np.vdot(values, values).real)
        rho = float(np.sqrt(max(rhs_norm_sq - captured, 0.0) / rhs_norm_sq))
        _require(np.isfinite(rho), "W8A projected residual is nonfinite")
        return {
            "column_count": column_count,
            "rho": rho,
            "captured_energy": captured,
            "captured_energy_ratio": captured / rhs_norm_sq,
            "normal_closure": normal,
            "finite": True,
        }

    def compare_range_orders(self, values: np.ndarray) -> dict[str, Any]:
        legacy = self.project_residual(values, column_count=W8A_LEGACY_COLUMNS)
        nested = self.project_residual(values, column_count=W8A_TOTAL_COLUMNS)
        return {
            "rho390": legacy["rho"],
            "rho530": nested["rho"],
            "relative_improvement": float(1.0 - nested["rho"] / legacy["rho"]),
            "legacy_normal_closure": legacy["normal_closure"],
            "nested_normal_closure": nested["normal_closure"],
            "normal_closure": max(legacy["normal_closure"], nested["normal_closure"]),
            "legacy": legacy,
            "nested": nested,
        }

    def save(self, directory: Path) -> Path:
        directory = Path(directory)
        if directory.exists():
            raise FileExistsError(f"W8A store refuses existing directory: {directory}")
        directory.mkdir(parents=True)
        arrays = {"z_data": self.z_data, "z_indices": self.z_indices, "z_indptr": self.z_indptr, "gram": self.gram, "r_factor": self.r_factor}
        for name, value in arrays.items():
            np.save(directory / f"{name}.npy", np.ascontiguousarray(value), allow_pickle=False)
        descriptors = {name: _array_meta(directory / f"{name}.npy", value) for name, value in arrays.items()}
        payload = {
            "schema": W8A_SCHEMA,
            "global_rows": self.global_rows,
            "ownership_range": [0, self.global_rows],
            "columns": W8A_TOTAL_COLUMNS,
            "column_specs": [spec.__dict__ for spec in self.specs],
            "identity": self.identity,
            "factor_audit": self.factor_audit,
            "action_counts": dict(self.action_counts),
            "repeat_columns": list(W8A_REPEAT_COLUMNS),
            "repeat_column_sha256": dict(self.repeat_column_sha256),
            "repeat_exact": self.repeat_exact,
            "column_sha256": list(self.column_sha256),
            "combined_az_column_sha256_aggregate": _json_sha256(list(self.column_sha256)),
            "legacy_z_identity": dict(self.legacy_z_identity),
            "arrays": descriptors,
            "az_scratch_old": dict(self.legacy_z_identity.get("az_scratch", {})),
            "az_scratch_new": {"path": str(self.new_az_store.path.resolve()), "bytes": self.new_az_store.allocated_bytes, "sha256": _file_sha256(self.new_az_store.path), "rows": self.global_rows, "capacity": W8A_ADDED_COLUMNS},
            "mmap": False,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "az_builder_only": True,
            "az_production_retained": False,
        }
        payload["evidence_sha256"] = _json_sha256(payload)
        manifest_path = directory / "manifest.json"
        manifest_path.write_bytes(_json_bytes(payload) + b"\n")
        self._manifest_path = manifest_path
        return manifest_path

    @classmethod
    def load(cls, manifest_path: Path, *, legacy_store_dir: Path) -> "W8AMultiOrderRangeDiagnostic":
        validation = validate_w8a_store(manifest_path, legacy_store_dir=legacy_store_dir)
        if validation.get("pass") is not True:
            raise ValueError("W8A store validation failed")
        manifest_path = Path(manifest_path).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        directory = manifest_path.parent
        arrays = {name: _load_manifest_array(directory, name, manifest["arrays"][name]) for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")}
        legacy_root = Path(legacy_store_dir).resolve()
        legacy_manifest = json.loads((legacy_root / "manifest.json").read_text(encoding="utf-8"))
        old_scratch = legacy_manifest["az_scratch"]
        old_store = RawPositionalColumnStore.open_readonly(
            Path(old_scratch["path"]).resolve(),
            int(old_scratch["rows"]),
            W8A_LEGACY_COLUMNS,
        )
        scratch = manifest["az_scratch_new"]
        new_store = RawPositionalColumnStore.open_readonly(Path(scratch["path"]), int(scratch["rows"]), int(scratch["capacity"]))
        try:
            result = cls(
                specs=tuple(W8AColumnSpec(**item) for item in manifest["column_specs"]),
                z_data=arrays["z_data"], z_indices=arrays["z_indices"], z_indptr=arrays["z_indptr"],
                gram=arrays["gram"], r_factor=arrays["r_factor"], old_az_store=old_store,
                new_az_store=new_store, global_rows=int(manifest["global_rows"]), identity=manifest["identity"],
                column_sha256=tuple(manifest["column_sha256"]), legacy_z_identity=manifest["legacy_z_identity"],
                action_counts=manifest["action_counts"], repeat_column_sha256=manifest["repeat_column_sha256"],
            )
            return result
        except Exception:
            new_store.close()
            old_store.close()
            raise

    def close(self) -> None:
        self.new_az_store.close()
        self.old_az_store.close()


def validate_w8a_store(manifest_path: Path, *, legacy_store_dir: Path) -> dict[str, Any]:
    """Fail-closed store/old-authority/factor validation for formal checking."""

    old_store = new_store = None
    try:
        manifest_path = Path(manifest_path).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _require(manifest.get("schema") == W8A_SCHEMA, "W8A schema is invalid")
        _require(manifest.get("evidence_sha256") == _json_sha256({key: value for key, value in manifest.items() if key != "evidence_sha256"}), "W8A evidence is invalid")
        _require(manifest.get("columns") == W8A_TOTAL_COLUMNS and manifest.get("ownership_range") == [0, manifest.get("global_rows")], "W8A shape/ownership is invalid")
        _require(tuple(manifest.get("column_specs", ())) == tuple(spec.__dict__ for spec in fixed_w8a_column_specs()), "W8A specs are invalid")
        directory = manifest_path.parent
        expected_files = {"manifest.json", "z_data.npy", "z_indices.npy", "z_indptr.npy", "gram.npy", "r_factor.npy"}
        _require({path.name for path in directory.iterdir()} == expected_files, "W8A store file set is invalid")
        arrays = {name: _load_manifest_array(directory, name, manifest["arrays"][name]) for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")}
        _require(arrays["z_indptr"].shape == (W8A_TOTAL_COLUMNS + 1,) and arrays["z_data"].size == arrays["z_indices"].size == int(arrays["z_indptr"][-1]) and arrays["gram"].shape == (W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS) and arrays["r_factor"].shape == arrays["gram"].shape and np.all(np.isfinite(arrays["z_data"])) and np.all(np.isfinite(arrays["gram"])) and np.all(np.isfinite(arrays["r_factor"])), "W8A arrays are invalid")
        old_identity, old_arrays, old_store = load_w6a_legacy_for_w8a(legacy_store_dir)
        legacy_identity = manifest.get("legacy_z_identity")
        old_nnz = int(old_arrays["z_indptr"][-1])
        _require(isinstance(legacy_identity, Mapping) and legacy_identity.get("manifest_file_sha256") == old_identity["manifest_file_sha256"] and legacy_identity.get("az_column_sha256_aggregate") == old_identity["az_column_sha256_aggregate"] and np.array_equal(arrays["z_data"][:old_nnz], old_arrays["z_data"]) and np.array_equal(arrays["z_indices"][:old_nnz], old_arrays["z_indices"]) and np.array_equal(arrays["z_indptr"][: W8A_LEGACY_COLUMNS + 1], old_arrays["z_indptr"]), "W8A old Z identity differs")
        scratch = manifest["az_scratch_new"]
        new_path = Path(scratch["path"]).resolve()
        _require(new_path.is_file() and new_path.stat().st_size == scratch["bytes"] and _file_sha256(new_path) == scratch["sha256"] and scratch["rows"] == manifest["global_rows"] and scratch["capacity"] == W8A_ADDED_COLUMNS, "W8A new AZ scratch differs")
        new_store = RawPositionalColumnStore.open_readonly(new_path, int(scratch["rows"]), W8A_ADDED_COLUMNS)
        old_buffer = np.empty(int(manifest["global_rows"]), dtype=_COMPLEX128)
        new_buffer = np.empty_like(old_buffer)
        hashes: list[str] = []
        for column in range(W8A_LEGACY_COLUMNS):
            old_store.read_column(column, old_buffer)
            actual = _array_sha256(old_buffer)
            _require(actual == old_identity["column_sha256"][column], "W8A old AZ hash differs")
            hashes.append(actual)
        for column in range(W8A_ADDED_COLUMNS):
            new_store.read_column(column, new_buffer)
            hashes.append(_array_sha256(new_buffer))
        _require(hashes == manifest.get("column_sha256") and _json_sha256(hashes[:75]) == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE and _json_sha256(hashes[:W8A_LEGACY_COLUMNS]) == old_identity["az_column_sha256_aggregate"] and manifest.get("combined_az_column_sha256_aggregate") == _json_sha256(hashes), "W8A AZ hashes differ")
        repeats = manifest.get("repeat_column_sha256")
        _require(manifest.get("repeat_columns") == list(W8A_REPEAT_COLUMNS) and manifest.get("repeat_exact") is True and isinstance(repeats, Mapping) and all(repeats[str(column)] == hashes[column] for column in W8A_REPEAT_COLUMNS), "W8A repeat identity differs")
        reader = _CompositeAZReader(old_store, new_store)
        gram = np.zeros((W8A_TOTAL_COLUMNS, W8A_TOTAL_COLUMNS), dtype=_COMPLEX128)
        gram[:W8A_LEGACY_COLUMNS, :W8A_LEGACY_COLUMNS] = old_arrays["gram"]
        for column in range(W8A_LEGACY_COLUMNS, W8A_TOTAL_COLUMNS):
            reader.read_column(column, old_buffer)
            for previous in range(column + 1):
                reader.read_column(previous, new_buffer)
                value = np.vdot(old_buffer, new_buffer)
                if column == previous:
                    value = complex(value.real, 0.0)
                gram[column, previous] = value
                gram[previous, column] = np.conjugate(value)
        _require(np.array_equal(gram, arrays["gram"]), "W8A Gram differs")
        factor = _factor_audit(gram, arrays["r_factor"])
        _require(factor["rank"] == W8A_TOTAL_COLUMNS and factor["normal_closure"] <= W8A_NORMAL_CLOSURE_LIMIT and factor["gram_hermitian_defect"] <= W8A_NORMAL_CLOSURE_LIMIT and np.array_equal(arrays["r_factor"], np.triu(arrays["r_factor"])) and np.all(np.real(np.diag(arrays["r_factor"])) > 0.0), "W8A factor Gate failed")
        recorded = manifest.get("factor_audit")
        _require(isinstance(recorded, Mapping) and recorded.get("rank") == factor["rank"] and np.isclose(recorded.get("normal_closure"), factor["normal_closure"], rtol=64 * np.finfo(float).eps, atol=0.0) and np.isclose(recorded.get("gram_hermitian_defect"), factor["gram_hermitian_defect"], rtol=64 * np.finfo(float).eps, atol=0.0), "W8A factor audit differs")
        return {"pass": True, "schema": W8A_SCHEMA, "columns": W8A_TOTAL_COLUMNS, "rank": factor["rank"], "normal_closure": factor["normal_closure"], "gram_hermitian_defect": factor["gram_hermitian_defect"], "old_az_reads": old_store.read_count, "new_az_reads": new_store.read_count}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}
    finally:
        if new_store is not None:
            new_store.close()
        if old_store is not None:
            old_store.close()
